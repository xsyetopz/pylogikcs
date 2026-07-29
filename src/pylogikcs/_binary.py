"""Codec for the ``LogicBinaryPreferences`` binary blob.

Each 6-byte record is ``[4 payload bytes][0xF7 0x00]``.
The sentinel ``0xF7 0x00`` terminates every record.  Records are parsed
by scanning for sentinels; modified records are spliced back at their
original byte offsets so unmodified data passes through unchanged.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ._model import KeyBinding


_SENTINEL = b"\xf7\x00"
_RECORD_PAYLOAD = 4
_RECORD_LEN = _RECORD_PAYLOAD + 2


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
