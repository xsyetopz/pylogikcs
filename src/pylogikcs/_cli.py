"""CLI for pylogikcs - inspect and edit .logikcs presets from the terminal."""

from __future__ import annotations

import argparse
import sys


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        prog="pylogikcs",
        description="Inspect and edit Logic Pro .logikcs key-command presets.",
    )
    sub = parser.add_subparsers(dest="command")

    p_inspect = sub.add_parser("inspect", help="Print preset summary")
    p_inspect.add_argument("file", help="Path to .logikcs file")

    p_list = sub.add_parser("list", help="List all key bindings")
    p_list.add_argument("file", help="Path to .logikcs file")

    p_color = sub.add_parser("set-color", help="Set a command's colour")
    p_color.add_argument("file", help="Path to .logikcs file")
    p_color.add_argument("command_id", help="Command ID (e.g. 1012)")
    p_color.add_argument("color", type=int, help="Colour index")
    p_color.add_argument("-o", "--output", help="Output path (default: overwrite input)")

    p_bind = sub.add_parser("set-binding", help="Modify a key binding")
    p_bind.add_argument("file", help="Path to .logikcs file")
    p_bind.add_argument("index", type=int, help="Binding index (0-based)")
    p_bind.add_argument("--key-code", type=lambda x: int(x, 0), help="Key code (hex ok)")
    p_bind.add_argument("--flags", type=lambda x: int(x, 0), help="Flags byte (hex ok)")
    p_bind.add_argument("-o", "--output", help="Output path (default: overwrite input)")

    args = parser.parse_args(argv)

    if args.command is None:
        parser.print_help()
        sys.exit(1)

    from . import load

    preset = load(args.file)

    if args.command == "inspect":
        _cmd_inspect(preset)
    elif args.command == "list":
        _cmd_list(preset)
    elif args.command == "set-color":
        preset.colors[args.command_id] = args.color
        preset.save(args.output or args.file)
        print(f"Set colour of command {args.command_id} to {args.color}")
    elif args.command == "set-binding":
        kb = preset.bindings[args.index]
        if args.key_code is not None:
            kb.key_code = args.key_code
        if args.flags is not None:
            kb.flags = args.flags
        preset.save(args.output or args.file)
        print(f"Updated binding {args.index}")


def _cmd_inspect(preset) -> None:
    from ._model import LogikcsFile

    assert isinstance(preset, LogikcsFile)
    print(f"Content:    {preset.content}")
    print(f"Version:    {preset.version}")
    print(f"Colors:     {len(preset.colors)} entries")
    print(f"ShortNames: {len(preset.short_names)} entries")
    print(f"Bindings:   {len(preset.bindings)} entries")
    if preset.source_path:
        print(f"Source:     {preset.source_path}")


def _cmd_list(preset) -> None:
    for i, kb in enumerate(preset.bindings):
        name = preset.short_names.get(str(kb.command_index), "")
        name_str = f"  ({name})" if name else ""
        print(
            f"[{i:3d}] cmd={kb.command_index:5d}  "
            f"key=0x{kb.key_code:02x}  flags=0x{kb.flags:02x}{name_str}"
        )


if __name__ == "__main__":
    main()
