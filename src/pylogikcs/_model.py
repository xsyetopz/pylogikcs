"""Domain types for Logic Pro .logikcs key-command presets.

Zero I/O dependencies — pure data model with validation.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class KeyBinding:
    """A single f7-terminated record from LogicBinaryPreferences.

    Usage::

        kb = KeyBinding.from_bytes(b"\\x0b\\x00\\x00\\x2c\\xf7\\x00")
        kb.key_code = 0x06
        kb.flags = 0x08
        raw = kb.to_bytes()
    """

    command_index: int
    value: int
    _modified: bool = field(default=False, repr=False)
    _offset: int = field(default=-1, repr=False)

    TERMINATOR: bytes = b"\xf7\x00"
    RECORD_LEN: int = 6

    @classmethod
    def from_bytes(cls, data: bytes) -> KeyBinding:
        if len(data) != cls.RECORD_LEN:
            raise ValueError(f"KeyBinding record must be {cls.RECORD_LEN} bytes, got {len(data)}")
        if data[4:6] != cls.TERMINATOR:
            raise ValueError(
                f"KeyBinding terminator mismatch: expected {cls.TERMINATOR.hex()}, "
                f"got {data[4:6].hex()}"
            )
        return cls(
            command_index=int.from_bytes(data[0:2], "little"),
            value=int.from_bytes(data[2:4], "little"),
        )

    def to_bytes(self) -> bytes:
        return (
            self.command_index.to_bytes(2, "little")
            + self.value.to_bytes(2, "little")
            + self.TERMINATOR
        )

    @property
    def key_code(self) -> int:
        """High byte of *value* — the virtual key code."""
        return (self.value >> 8) & 0xFF

    @key_code.setter
    def key_code(self, v: int) -> None:
        if not 0 <= v <= 255:
            raise ValueError(f"key_code must be 0-255, got {v}")
        self.value = (self.value & 0xFF) | ((v & 0xFF) << 8)
        self._modified = True

    @property
    def flags(self) -> int:
        """Low byte of *value* — modifier / flags byte."""
        return self.value & 0xFF

    @flags.setter
    def flags(self, v: int) -> None:
        if not 0 <= v <= 255:
            raise ValueError(f"flags must be 0-255, got {v}")
        self.value = (self.value & 0xFF00) | (v & 0xFF)
        self._modified = True

    @property
    def is_modified(self) -> bool:
        return self._modified

    def mark_clean(self) -> None:
        self._modified = False


@dataclass
class HeaderBinding:
    """A 4-byte keyed entry from the header's Format A binding table.

    Format: ``[key_code: u8] [flags: u8] [0x00] [key_code_dup: u8]``

    Each entry appears at two mirrored byte offsets in the binary blob.
    Setting *key_code* or *flags* marks both copies as modified; on save
    both positions are updated.
    """

    key_code: int
    flags: int
    _offset1: int = field(default=-1, repr=False)
    _offset2: int = field(default=-1, repr=False)
    _modified: bool = field(default=False, repr=False)

    ENTRY_LEN: int = 4

    @classmethod
    def from_bytes(cls, data: bytes, offset: int = -1) -> HeaderBinding:
        if len(data) != cls.ENTRY_LEN:
            raise ValueError(f"HeaderBinding must be {cls.ENTRY_LEN} bytes, got {len(data)}")
        if data[2] != 0x00:
            raise ValueError(f"HeaderBinding byte 2 must be 0x00, got 0x{data[2]:02x}")
        return cls(key_code=data[0], flags=data[1], _offset1=offset)

    def to_bytes(self) -> bytes:
        return bytes([self.key_code, self.flags, 0x00, self.key_code])

    @property
    def key_char(self) -> str:
        """ASCII character for printable keys, else hex notation."""
        if 32 <= self.key_code < 127:
            return chr(self.key_code)
        return f"0x{self.key_code:02x}"

    @property
    def name(self) -> str:
        """Human-readable command name from the Logic Pro registry, or ''."""
        return keybinding_name(self.key_code, self.flags)

    @property
    def is_modified(self) -> bool:
        return self._modified

    def mark_clean(self) -> None:
        self._modified = False

    # ---- mutation ----------------------------------------------------------

    def set_key(self, v: int) -> None:
        if not 0 <= v <= 255:
            raise ValueError(f"key_code must be 0-255, got {v}")
        self.key_code = v
        self._modified = True

    def set_flags(self, v: int) -> None:
        if not 0 <= v <= 255:
            raise ValueError(f"flags must be 0-255, got {v}")
        self.flags = v
        self._modified = True


class _ValidatedDict(dict[str, str | int]):
    """Dict that coerces string keys and validates values on set."""

    _value_type: type = str

    def __setitem__(self, key: str, value: str | int) -> None:
        key = str(key)
        if not isinstance(value, self._value_type):
            raise TypeError(
                f"Value must be {self._value_type.__name__}, got {type(value).__name__}"
            )
        super().__setitem__(key, value)


class ColorMap(_ValidatedDict):
    _value_type = int


class ShortNameMap(_ValidatedDict):
    _value_type = str


CONTENT_TYPE = "com.apple.logic.keycommand"

# Lazy-loaded command registry from Logic Pro preferences.
_registry: dict | None = None


def _load_registry() -> dict:
    global _registry
    if _registry is None:
        import json
        from pathlib import Path

        path = Path(__file__).parent / "_registry.json"
        with open(path) as f:
            _registry = json.load(f)
    assert _registry is not None
    return _registry


def command_name(command_id: int) -> str:
    """Return the human-readable name for a Logic command ID, or '' if unknown."""
    reg = _load_registry()
    return reg.get("id_to_name", {}).get(str(command_id), "")


def keybinding_name(key_code: int, flags: int) -> str:
    """Return the command name matching a (key_code, flags) pair, or ''."""
    reg = _load_registry()
    for cid, info in reg.get("commands", {}).items():
        if info.get("key") == key_code and info.get("modifier") == flags:
            name = reg.get("id_to_name", {}).get(cid, "")
            if name:
                return name
    return ""


@dataclass
class LogikcsFile:
    """In-memory representation of a ``.logikcs`` key-command preset.

    Usage::

        preset = LogikcsFile.load("Default.logikcs")
        preset.colors["1012"] = 3
        preset.short_names["1012"] = "RdOff"
        preset.header_bindings[0].set_key(0x70)
        preset.header_bindings[0].set_flags(0x20)
        preset.save("Modified.logikcs")
    """

    version: str = "12.3.0"
    content: str = CONTENT_TYPE

    colors: ColorMap = field(default_factory=ColorMap)
    short_names: ShortNameMap = field(default_factory=ShortNameMap)
    bindings: list[KeyBinding] = field(default_factory=list)
    header_bindings: list[HeaderBinding] = field(default_factory=list)

    # Raw copies preserved so unchanged entries survive round-trip.
    _binary_blob: bytes = field(default=b"", repr=False)
    _touchbar_raw: bytes = field(default=b"", repr=False)
    _unknown_plist: dict = field(default_factory=dict, repr=False)
    _raw_colors: dict = field(default_factory=dict, repr=False)
    _raw_short_names: dict = field(default_factory=dict, repr=False)

    source_path: str | None = field(default=None, repr=False)
    _is_raw: bool = field(default=False, repr=False)  # True for .pro files (no plist wrapper)

    @classmethod
    def load(cls, path: str) -> LogikcsFile:
        from ._plist import read_plist

        return read_plist(path)

    def save(self, path: str) -> None:
        from ._plist import write_plist

        write_plist(self, path)
