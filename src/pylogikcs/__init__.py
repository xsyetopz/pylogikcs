"""Public API for pylogikcs - Logic Pro .logikcs read/write library.

Usage::

    import pylogikcs

    preset = pylogikcs.load("Default.logikcs")
    print(preset.version)
    for kb in preset.bindings:
        print(f"cmd={kb.command_index} key={kb.key_code:#04x} flags={kb.flags:#04x}")

    preset.colors["1012"] = 3
    preset.short_names["1012"] = "RdOff"
    preset.bindings[0].key_code = 0x31
    preset.save("Modified.logikcs")
"""

from ._model import ColorMap, KeyBinding, LogikcsFile, ShortNameMap


def load(path: str) -> LogikcsFile:
    return LogikcsFile.load(path)


__all__ = [
    "ColorMap",
    "KeyBinding",
    "LogikcsFile",
    "ShortNameMap",
    "load",
]
