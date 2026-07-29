"""Codec for the ``LogicBinaryPreferences`` binary blob.

Two record types coexist:

1. **f7-terminated records** (6 bytes): ``[u16 LE][u16 LE][0xF7 0x00]``
   Scanned by sentinel.  Used for internal command definitions.

2. **Format A header entries** (4 bytes): ``[key_code][flags][0x00][key_code_dup]``
   Found in two mirrored copies at fixed byte offsets in the header region.
   These encode the actual key assignments.  Mutations are spliced in at
   their recorded offsets (both copies).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ._model import HeaderBinding, KeyBinding


_SENTINEL = b"\xf7\x00"
_RECORD_PAYLOAD = 4
_RECORD_LEN = _RECORD_PAYLOAD + 2

# Header Format A entry regions.
_HEADER_COPY1_RANGE = (0x0000, 0x0300)
_HEADER_COPY2_RANGE = (0x3300, 0x3700)  # extended to catch record-gap entries


# ---------------------------------------------------------------------------
# f7-terminated records
# ---------------------------------------------------------------------------


def decode_commands(raw: bytes) -> tuple[list[KeyBinding], bytes]:
    from ._model import KeyBinding

    if not raw:
        return [], b""

    bindings: list[KeyBinding] = []
    i = 0
    while i < len(raw) - 1:
        if raw[i] == 0xF7 and raw[i + 1] == 0x00:
            record_start = i - _RECORD_PAYLOAD
            if record_start >= 0:
                record_bytes = raw[record_start : i + 2]
                try:
                    kb = KeyBinding.from_bytes(record_bytes)
                    kb._offset = record_start
                    bindings.append(kb)
                except ValueError:
                    pass
        i += 1

    return bindings, bytes(raw)


def encode_commands(raw_blob: bytes, bindings: list[KeyBinding]) -> bytes:
    data = bytearray(raw_blob)
    for kb in bindings:
        if not kb.is_modified:
            continue
        offset = getattr(kb, "_offset", -1)
        if offset < 0 or offset + _RECORD_LEN > len(data):
            continue
        data[offset : offset + _RECORD_LEN] = kb.to_bytes()
    return bytes(data)


# ---------------------------------------------------------------------------
# Format A header entries
# ---------------------------------------------------------------------------


def _is_format_a(data: bytes, i: int) -> bool:
    """True if ``data[i:i+4]`` matches ``[k][f][0x00][k]`` with k != 0."""
    return (
        data[i] != 0
        and data[i + 2] == 0x00
        and data[i] == data[i + 3]
    )


def decode_header_entries(raw: bytes) -> list[HeaderBinding]:
    """Find all Format A entries in both header copies.

    Entries at offset *off* in copy 1 have a mirror at offset roughly
    ``off + 0x31bc`` in copy 2.  We pair them by proximity.
    """
    from ._model import HeaderBinding

    if not raw:
        return []

    all_entries: list[tuple[int, int, int]] = []  # (offset, key, flags)
    for start, _end in (_HEADER_COPY1_RANGE, _HEADER_COPY2_RANGE):
        r_start = max(0, start)
        r_end = min(len(raw) - 4, _end)
        for i in range(r_start, r_end):
            if _is_format_a(raw, i):
                all_entries.append((i, raw[i], raw[i + 1]))

    copy1 = [(off, k, f) for off, k, f in all_entries if off < _HEADER_COPY2_RANGE[0]]
    copy2 = {(off, k, f) for off, k, f in all_entries if off >= _HEADER_COPY2_RANGE[0]}

    MIRROR_DELTA = 0x31BC
    MIRROR_TOLERANCE = 8
    entries: list[HeaderBinding] = []
    used_c2: set[int] = set()

    for off1, k, f in copy1:
        expected = off1 + MIRROR_DELTA
        matched = -1
        for off2, _k2, _f2 in copy2:
            if abs(off2 - expected) <= MIRROR_TOLERANCE and off2 not in used_c2:
                matched = off2
                used_c2.add(off2)
                break
        hb = HeaderBinding(key_code=k, flags=f, _offset1=off1, _offset2=matched)
        entries.append(hb)

    for off2, k, f in copy2:
        if off2 not in used_c2:
            hb = HeaderBinding(key_code=k, flags=f, _offset1=off2, _offset2=-1)
            entries.append(hb)

    entries.sort(key=lambda hb: hb._offset1)
    return entries


def encode_header_entries(raw_blob: bytes, entries: list[HeaderBinding]) -> bytes:
    """Splice modified header entries back into both mirrored positions."""
    data = bytearray(raw_blob)
    for hb in entries:
        if not hb.is_modified:
            continue
        encoded = hb.to_bytes()
        for off in (hb._offset1, hb._offset2):
            if off >= 0 and off + 4 <= len(data):
                data[off : off + 4] = encoded
    return bytes(data)
