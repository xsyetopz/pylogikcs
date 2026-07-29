"""Plist I/O adapter.

On load we keep copies of the raw plist dict sections for
``KeyCommandColors`` and ``KeyCommandShortNames``.  On save we start
from those raw dicts and overlay in-memory edits.  This preserves
entries we don't understand (e.g. ``"New Child"`` -> ``""``).
"""

from __future__ import annotations

import contextlib
import copy
import plistlib
from typing import TYPE_CHECKING

from ._binary import decode_commands, decode_header_entries, encode_commands, encode_header_entries
from ._touchbar import decode_touchbar, encode_touchbar

if TYPE_CHECKING:
    from ._model import LogikcsFile


_PASSTHROUGH_KEYS = frozenset(
    {
        "Content",
        "Version",
        "LogicBinaryPreferences",
        "TouchBarAssignments",
    }
)


def _stable_key(k: object) -> str:
    """Coerce a dict key to ``str`` to avoid mixed-type sort errors in plistlib."""
    return str(k)


def read_plist(path: str) -> LogikcsFile:
    from ._model import CONTENT_TYPE, ColorMap, LogikcsFile, ShortNameMap

    with open(path, "rb") as fh:
        try:
            raw: dict = plistlib.load(fh)
        except plistlib.InvalidFileException:
            # Pre-LPX .pro file: the file *is* the raw binary blob.
            # No plist wrapper, no colors, no short names.
            fh.seek(0)
            binary_raw = fh.read()
            bindings, binary_blob = decode_commands(binary_raw)
            header_bindings = decode_header_entries(binary_blob)
            return LogikcsFile(
                version="7.x",
                content=CONTENT_TYPE,
                bindings=bindings,
                header_bindings=header_bindings,
                _binary_blob=binary_blob,
                _is_raw=True,
                source_path=path,
            )

    content = raw.get("Content", "")
    version = raw.get("Version", "")

    raw_colors: dict = copy.deepcopy(raw.get("KeyCommandColors", {}))
    colors = ColorMap()
    for k, v in raw_colors.items():
        with contextlib.suppress(ValueError, TypeError):
            colors[str(k)] = int(v)

    raw_names: dict = copy.deepcopy(raw.get("KeyCommandShortNames", {}))
    short_names = ShortNameMap()
    for k, v in raw_names.items():
        short_names[str(k)] = str(v)

    binary_raw: bytes = raw.get("LogicBinaryPreferences", b"")
    bindings, binary_blob = decode_commands(binary_raw)
    header_bindings = decode_header_entries(binary_blob)

    touchbar_raw: bytes = raw.get("TouchBarAssignments", b"")
    touchbar_decompressed = decode_touchbar(touchbar_raw)

    unknown = {}
    for k, v in raw.items():
        if k not in _PASSTHROUGH_KEYS and k not in ("KeyCommandColors", "KeyCommandShortNames"):
            unknown[k] = v

    return LogikcsFile(
        version=version,
        content=content,
        colors=colors,
        short_names=short_names,
        bindings=bindings,
        header_bindings=header_bindings,
        _binary_blob=binary_blob,
        _touchbar_raw=touchbar_decompressed,
        _unknown_plist=unknown,
        _raw_colors=raw_colors,
        _raw_short_names=raw_names,
        source_path=path,
    )


def write_plist(preset: LogikcsFile, path: str) -> None:
    binary_bytes = encode_commands(preset._binary_blob, preset.bindings)
    binary_bytes = encode_header_entries(binary_bytes, preset.header_bindings)

    if preset._is_raw:
        with open(path, "wb") as fh:
            fh.write(binary_bytes)
        return
    touchbar_bytes = encode_touchbar(preset._touchbar_raw)

    out: dict = {}
    out.update(preset._unknown_plist)
    out["Content"] = preset.content
    out["Version"] = preset.version

    color_dict: dict = {}
    for k, v in preset._raw_colors.items():
        color_dict[_stable_key(k)] = v
    for k, v in preset.colors.items():
        color_dict[_stable_key(k)] = v
    out["KeyCommandColors"] = color_dict

    name_dict: dict = {}
    for k, v in preset._raw_short_names.items():
        name_dict[_stable_key(k)] = v
    for k, v in preset.short_names.items():
        name_dict[_stable_key(k)] = v
    out["KeyCommandShortNames"] = name_dict

    out["LogicBinaryPreferences"] = binary_bytes
    out["TouchBarAssignments"] = touchbar_bytes

    with open(path, "wb") as fh:
        plistlib.dump(out, fh, fmt=plistlib.FMT_XML)
