"""Codec for the ``LogicBinaryPreferences`` binary blob.

Two format eras exist, autodetected by sentinel scanning:

**LPX format (Logic Pro 10.0-12.3)**
    f7-terminated 6-byte records: ``[u16 LE][u16 LE][0xF7 0x00]``.
    Scanned by sentinel.  Format A header entries coexist at fixed offsets.

**Pre-LPX format (Logic Pro 7.x-9.1.1)**
    Contiguous 6-byte records starting at offset 0x01c8, no sentinels:
    ``[byte0][byte1][u32 LE]``.  Byte0/byte1 encode either a key binding
    (``key_code + flags``) or an internal command index (``u16 LE``).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ._model import HeaderBinding, KeyBinding


_SENTINEL = b"\xf7\x00"
_RECORD_PAYLOAD = 4
_RECORD_LEN = _RECORD_PAYLOAD + 2

_PRE_LPX_RECORD_LEN = 6
_PRE_LPX_RECORD_START = 0x01C8

_HEADER_COPY1_RANGE = (0x0000, 0x0300)
_HEADER_COPY2_RANGE = (0x3300, 0x3700)


def _is_lpx_format(raw: bytes) -> bool:
    """True if the blob contains ``0xF7 0x00`` sentinels (LPX format)."""
    return _SENTINEL in raw


def _decode_lpx(raw: bytes) -> tuple[list[KeyBinding], bytes]:
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


def _encode_lpx(raw_blob: bytes, bindings: list[KeyBinding]) -> bytes:
    data = bytearray(raw_blob)
    for kb in bindings:
        if not kb.is_modified:
            continue
        offset = getattr(kb, "_offset", -1)
        if offset < 0 or offset + _RECORD_LEN > len(data):
            continue
        data[offset : offset + _RECORD_LEN] = kb.to_bytes()
    return bytes(data)


def _decode_pre_lpx(raw: bytes) -> tuple[list[KeyBinding], bytes]:
    from ._model import KeyBinding

    if not raw or len(raw) < _PRE_LPX_RECORD_START + _PRE_LPX_RECORD_LEN:
        return [], b""

    bindings: list[KeyBinding] = []
    offset = _PRE_LPX_RECORD_START
    zero_run = 0
    MAX_ZERO_RUN = 96

    while offset + _PRE_LPX_RECORD_LEN <= len(raw):
        chunk = raw[offset : offset + _PRE_LPX_RECORD_LEN]

        if chunk == b"\x00\x00\x00\x00\x00\x00":
            zero_run += _PRE_LPX_RECORD_LEN
            if zero_run >= MAX_ZERO_RUN:
                break
            offset += _PRE_LPX_RECORD_LEN
            continue

        zero_run = 0
        raw_cmd = int.from_bytes(chunk[0:2], "little")
        # Bytes 0-1: [key_code][flags].  Arrange value so that key_code
        # (hi byte) and flags (lo byte) properties match LPX convention.
        key_code = chunk[0]
        flags = chunk[1]
        value = (key_code << 8) | flags
        kb = KeyBinding(command_index=raw_cmd, value=value)
        kb._offset = offset
        bindings.append(kb)
        offset += _PRE_LPX_RECORD_LEN

    return bindings, bytes(raw)


def _encode_pre_lpx(raw_blob: bytes, bindings: list[KeyBinding]) -> bytes:
    data = bytearray(raw_blob)
    for kb in bindings:
        if not kb.is_modified:
            continue
        offset = getattr(kb, "_offset", -1)
        if offset < 0 or offset + _PRE_LPX_RECORD_LEN > len(data):
            continue
        rec = bytes([kb.key_code, kb.flags]) + b"\x00\x00\x00\x00"
        data[offset : offset + _PRE_LPX_RECORD_LEN] = rec
    return bytes(data)


def decode_commands(raw: bytes) -> tuple[list[KeyBinding], bytes]:
    """Decode binary blob into ``(bindings, raw_blob)``.

    Format is autodetected: LPX if ``0xF7 0x00`` sentinels present,
    otherwise pre-LPX.
    """
    if _is_lpx_format(raw):
        return _decode_lpx(raw)
    return _decode_pre_lpx(raw)


def encode_commands(raw_blob: bytes, bindings: list[KeyBinding]) -> bytes:
    """Splice modified bindings back into *raw_blob*.

    Format is autodetected from *raw_blob*.
    """
    if _is_lpx_format(raw_blob):
        return _encode_lpx(raw_blob, bindings)
    return _encode_pre_lpx(raw_blob, bindings)


def _is_format_a(data: bytes, i: int) -> bool:
    return data[i] != 0 and data[i + 2] == 0x00 and data[i] == data[i + 3]


def decode_header_entries(raw: bytes) -> list[HeaderBinding]:
    """Find all Format A entries.

    For LPX: entries at offset *off* in copy 1 have a mirror at roughly
    ``off + 0x31bc`` in copy 2.  For pre-LPX: search the entire blob
    since there is no fixed mirror region.
    """
    from ._model import HeaderBinding

    if not raw:
        return []

    is_lpx = _is_lpx_format(raw)
    search_ranges = [_HEADER_COPY1_RANGE, _HEADER_COPY2_RANGE] if is_lpx else [(0, len(raw))]

    all_entries: list[tuple[int, int, int]] = []
    for start, _end in search_ranges:
        r_start = max(0, start)
        r_end = min(len(raw) - 4, _end)
        for i in range(r_start, r_end):
            if _is_format_a(raw, i):
                all_entries.append((i, raw[i], raw[i + 1]))

    if not is_lpx:
        entries = [
            HeaderBinding(key_code=k, flags=f, _offset1=off, _offset2=-1)
            for off, k, f in all_entries
        ]
        entries.sort(key=lambda hb: hb._offset1)
        return entries

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
        entries.append(HeaderBinding(key_code=k, flags=f, _offset1=off1, _offset2=matched))

    for off2, k, f in copy2:
        if off2 not in used_c2:
            entries.append(HeaderBinding(key_code=k, flags=f, _offset1=off2, _offset2=-1))

    entries.sort(key=lambda hb: hb._offset1)
    return entries


def encode_header_entries(raw_blob: bytes, entries: list[HeaderBinding]) -> bytes:
    data = bytearray(raw_blob)
    for hb in entries:
        if not hb.is_modified:
            continue
        encoded = hb.to_bytes()
        for off in (hb._offset1, hb._offset2):
            if off >= 0 and off + 4 <= len(data):
                data[off : off + 4] = encoded
    return bytes(data)
