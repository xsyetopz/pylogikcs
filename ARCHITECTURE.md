# Architecture: pylogikcs

## System overview

`pylogikcs` is a zero-dependency Python library that reads, edits, and writes
Logic Pro `.logikcs` key-command preset files.  The file format is an Apple
plist XML envelope containing binary key-binding records that require partial
reverse-engineering.

```mermaid
flowchart LR
    subgraph Public API
        load["pylogikcs.load()"]
        save["preset.save()"]
    end

    subgraph Domain Model
        LF["LogikcsFile"]
        KB["list[KeyBinding]"]
        CM["ColorMap"]
        SM["ShortNameMap"]
    end

    subgraph Adapters
        PLIST["_plist.py<br/>plistlib wrapper"]
        BIN["_binary.py<br/>record codec"]
        TB["_touchbar.py<br/>zlib codec"]
    end

    subgraph External
        FILE[(".logikcs file")]
    end

    load --> PLIST --> FILE
    PLIST --> BIN --> KB
    PLIST --> TB
    PLIST --> LF
    LF --> CM
    LF --> SM
    LF --> KB
    save --> PLIST
```

## File format

```mermaid
flowchart TD
    LOGIKCS[".logikcs file"] --> PLIST["Apple plist XML v1.0"]
    PLIST --> META["Content · Version"]
    PLIST --> COLORS["KeyCommandColors<br/>{command_id: color_index}"]
    PLIST --> NAMES["KeyCommandShortNames<br/>{command_id: display_name}"]
    PLIST --> BINARY["LogicBinaryPreferences<br/>base64-encoded binary"]
    PLIST --> TOUCH["TouchBarAssignments<br/>base64-encoded zlib"]
    BINARY --> HEADER["Variable-length header"]
    BINARY --> RECORDS["6-byte records"]
    RECORDS --> REC["[u16 LE][u16 LE][0xF7 0x00]"]
    TOUCH --> ZLIB["zlib-decompressed<br/>touch bar layout"]
```

## Load pipeline

The binary blob is partially reverse-engineered.  Records are identified by
scanning for the sentinel `0xF7 0x00`; the 4 preceding bytes form the record
payload.  Unknown regions (header, gaps, trailer) are preserved verbatim.

```mermaid
flowchart LR
    BYTES["Raw bytes from plistlib"] --> SCAN["Scan for 0xF7 0x00 sentinels"]
    SCAN --> SPLIT["Split at 4-byte record boundaries"]
    SPLIT -->|"valid 6-byte record"| PARSE["KeyBinding.from_bytes()"]
    SPLIT -->|"no sentinel found"| TRAIL["Opaque trailer"]
    PARSE -->|"records stored with<br/>byte offset recorded"| KB["list[KeyBinding]"]
    TRAIL -->|"preserved verbatim"| BLOB["_binary_blob"]
```

### Record structure

Each 6-byte record has this layout (little-endian):

```text
┌──────────┬──────────┬──────────┬──────────┬──────────┬──────────┐
│  byte 0  │  byte 1  │  byte 2  │  byte 3  │   0xF7   │   0x00   │
├──────────┴──────────┼──────────┴──────────┼──────────┴──────────┤
│   command_index     │       value         │     sentinel        │
│      (u16 LE)       │     (u16 LE)        │                      │
└─────────────────────┴─────────────────────┴─────────────────────┘
```

The `value` field encodes the key assignment across two sub-fields:

```text
value (u16 LE) = [key_code: u8 hi] [flags: u8 lo]
```

## Save pipeline

Modified records are spliced back into the original blob at their recorded
offsets.  Unmodified records and all non-record regions pass through unchanged.

```mermaid
flowchart LR
    KBIN["list[KeyBinding]"] --> SPLICE{"kb.is_modified?"}
    BLOB["_binary_blob<br/>(original bytes)"] --> SPLICE
    SPLICE -->|"yes"| REENC["kb.to_bytes()"]
    SPLICE -->|"no"| KEEP["Keep original bytes"]
    REENC --> MERGE["Write at kb._offset"]
    KEEP --> MERGE
    MERGE --> OUT["Reassembled blob<br/>byte-identical where unmodified"]
```

## Plist round-trip strategy

The `_plist.py` adapter keeps deep copies of the raw `KeyCommandColors` and
`KeyCommandShortNames` dicts from the original plist.  On write, it overlays
in-memory edits onto those raw copies.  This preserves entries that don't
fit the typed model (e.g., `"New Child" -> ""` in the colours dict).

```mermaid
sequenceDiagram
    participant File
    participant Plist as _plist.py
    participant Model as LogikcsFile
    participant Codec as _binary.py

    File->>Plist: plistlib.load()
    Plist->>Plist: deepcopy raw colors & names dicts
    Plist->>Codec: decode_commands(binary_raw)
    Codec-->>Plist: (bindings, blob_copy)
    Plist->>Model: LogikcsFile(raw_copies, bindings, blob)

    Note over Model: User mutates colors / short_names / bindings

    Model->>Plist: save(path)
    Plist->>Plist: overlay edits onto raw dicts
    Plist->>Codec: encode_commands(blob, bindings)
    Codec-->>Plist: spliced binary bytes
    Plist->>File: plistlib.dump()
```

## Component contracts

| Module | Responsibility | State owned |
| --- | --- | --- |
| `_model.py` | Domain types, validation, no I/O | `LogikcsFile`, `KeyBinding`, `ColorMap`, `ShortNameMap` |
| `_plist.py` | Plist XML I/O, raw-dict overlay | None (pure functions) |
| `_binary.py` | Sentinel scan, record decode/encode, splice | None (pure functions) |
| `_touchbar.py` | Zlib decompress/compress | None (pure functions) |
| `__init__.py` | Public API re-exports | None |
| `_cli.py` | argparse CLI | None |

Dependency direction: `__init__` -> `_model` ← `_plist` -> `_binary`, `_touchbar`.
No circular imports; `_model` imports nothing from the package.

## Key decisions

1. **Opaque blob + typed overlay** — binary sections are kept as raw bytes;
   typed records are parsed from known positions.  On write, modified records
   are spliced in; everything else passes through.  This accepts partial
   format understanding in exchange for guaranteed round-trip fidelity.
2. **Position-based splice** — each `KeyBinding` records its byte offset in
   the original blob.  Encoding writes only modified records at their exact
   positions, leaving gaps and unmodified records byte-identical.
3. **Raw dict copies for plist sections** — the `KeyCommandColors` and
   `KeyCommandShortNames` raw dicts are deep-copied on load.  Edits are
   overlaid on save.  This preserves non-standard entries (e.g., the
   `"New Child"` key with an empty string value) that break typed models.
4. **Zero dependencies** — Python 3.11+ stdlib only.  `plistlib` handles XML;
   `base64` and `zlib` handle binary codecs.

## Tradeoffs

| Decision | Benefit | Cost |
| --- | --- | --- |
| Sentinel-based record parsing | Works without full format spec | Wrong if `0xF7 0x00` appears in payload |
| Position-based splice | Guarantees unmodified bytes survive | Requires storing `_offset` per record |
| Raw dict copies | Non-standard plist entries preserved | Two representations (raw + typed) per section |
| No external deps | Zero install friction | Slower plist writing (stdlib `plistlib` is pure Python) |
