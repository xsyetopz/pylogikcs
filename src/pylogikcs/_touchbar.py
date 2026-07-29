"""Codec for the ``TouchBarAssignments`` zlib-compressed blob.

Plistlib base64-decodes the ``<data>`` element to raw bytes.  We
zlib-decompress on load and re-compress on save.
"""

from __future__ import annotations

import zlib


def decode_touchbar(raw: bytes) -> bytes:
    if not raw:
        return b""
    return zlib.decompress(raw)


def encode_touchbar(data: bytes) -> bytes:
    if not data:
        return b""
    return zlib.compress(data)
