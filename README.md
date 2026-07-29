# pylogikcs

Read, edit, and write Logic Pro `.logikcs` key-command preset files.
Zero dependencies - Python 3.11+ stdlib only.

Tested with Logic Pro 12.3 (`assets/Default.logikcs`).

## Install

```bash
pipx install -e .
```

## Quick start

```python
import pylogikcs

preset = pylogikcs.load("assets/Default.logikcs")

# Inspect
print(preset.version)          # "12.3.0"
print(len(preset.bindings))    # 201

# Edit a key binding
kb = preset.bindings[4]
kb.key_code = 0x06   # change key
kb.flags = 0x08      # change modifiers

# Edit colours and names
preset.colors["1012"] = 3
preset.short_names["1012"] = "ReadOff"

# Write back
preset.save("MyPreset.logikcs")
```

## CLI

```bash
# Inspect a preset
python -m pylogikcs._cli inspect assets/Default.logikcs

# List all key bindings
python -m pylogikcs._cli list assets/Default.logikcs

# Edit a colour
python -m pylogikcs._cli set-color assets/Default.logikcs 1012 7 -o Modified.logikcs

# Edit a binding
python -m pylogikcs._cli set-binding assets/Default.logikcs 4 --key-code 0x06 --flags 0x08 -o Modified.logikcs
```

Or use the `justfile`:

```bash
just inspect assets/Default.logikcs
just list assets/Default.logikcs
just test
```

## API

### `pylogikcs.load(path) -> LogikcsFile`

Parse a `.logikcs` file.

### `LogikcsFile`

| Attribute | Type | Description |
| --- | --- | --- |
| `version` | `str` | Logic Pro version (e.g. `"12.3.0"`) |
| `content` | `str` | Content type identifier |
| `colors` | `ColorMap` | Command ID -> colour index |
| `short_names` | `ShortNameMap` | Command ID -> display name |
| `bindings` | `list[KeyBinding]` | 201 key-binding records |
| `save(path)` | - | Write to file |

### `KeyBinding`

| Attribute | Type | Description |
| --- | --- | --- |
| `command_index` | `int` | Internal command index |
| `value` | `int` | Raw 16-bit payload |
| `key_code` | `int` | Virtual key code (0–255), r/w |
| `flags` | `int` | Modifier flags (0–255), r/w |
| `is_modified` | `bool` | True if mutated since load |

### `ColorMap` / `ShortNameMap`

`dict` subclasses with type validation. Keys are command ID strings.

## File format

`.logikcs` files are Apple plist XML (v1.0) containing:

- `Content` / `Version` - metadata
- `KeyCommandColors` - `{command_id: colour_index}`
- `KeyCommandShortNames` - `{command_id: display_name}`
- `LogicBinaryPreferences` - base64-encoded binary blob (6-byte records:
`[payload × 4][0xF7 0x00]`)
- `TouchBarAssignments` - base64-encoded zlib-compressed data

The binary blob is partially reverse-engineered. Unmodified records are
preserved byte-for-byte on write; mutated records are spliced in at their
original offsets.

## Test

```bash
python -m unittest tests.test_logikcs -v
```

30 tests covering: KeyBinding parse/encode, ColorMap/ShortNameMap validation,
load, round-trip fidelity, mutation persistence, and edge cases.

## License

[MIT](LICENSE)
