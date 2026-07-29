# 架构: pylogikcs

## 系统概览

`pylogikcs` 是一个零依赖的 Python 库，用于读写 Logic Pro `.logikcs` 快捷键预设文件。文
件格式为 Apple plist XML 封装，内含需要部分逆向的二进制按键绑定记录。

```mermaid
flowchart LR
    subgraph 公共API
        load["pylogikcs.load()"]
        save["preset.save()"]
    end

    subgraph 领域模型
        LF["LogikcsFile"]
        KB["list[KeyBinding]"]
        CM["ColorMap"]
        SM["ShortNameMap"]
    end

    subgraph 适配器
        PLIST["_plist.py<br/>plistlib 封装"]
        BIN["_binary.py<br/>记录编解码"]
        TB["_touchbar.py<br/>zlib 编解码"]
    end

    subgraph 外部
        FILE[(".logikcs 文件")]
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

## 文件格式

```mermaid
flowchart TD
    LOGIKCS[".logikcs 文件"] --> PLIST["Apple plist XML v1.0"]
    PLIST --> META["Content · Version"]
    PLIST --> COLORS["KeyCommandColors<br/>{命令ID: 颜色索引}"]
    PLIST --> NAMES["KeyCommandShortNames<br/>{命令ID: 显示名称}"]
    PLIST --> BINARY["LogicBinaryPreferences<br/>base64 编码的二进制"]
    PLIST --> TOUCH["TouchBarAssignments<br/>base64 编码的 zlib"]
    BINARY --> HEADER["变长头"]
    BINARY --> RECORDS["6 字节记录"]
    RECORDS --> REC["[u16 LE][u16 LE][0xF7 0x00]"]
    TOUCH --> ZLIB["zlib 解压后的<br/>Touch Bar 布局"]
```

## 加载流程

二进制数据已部分逆向。通过扫描哨兵 `0xF7 0x00` 识别记录；哨兵前 4 字节为记录载荷。未知区域（文件头、间隙、尾部）原样保留。

```mermaid
flowchart LR
    BYTES["plistlib 返回的原始字节"] --> SCAN["扫描 0xF7 0x00 哨兵"]
    SCAN --> SPLIT["按 4 字节载荷 + 2 字节哨兵边界切分"]
    SPLIT -->|"合法的 6 字节记录"| PARSE["KeyBinding.from_bytes()"]
    SPLIT -->|"未找到哨兵"| TRAIL["不透明尾部数据"]
    PARSE -->|"记录附带<br/>字节偏移量存储"| KB["list[KeyBinding]"]
    TRAIL -->|"原样保留"| BLOB["_binary_blob"]
```

### 记录结构

每条记录 6 字节（小端序）：

```text
┌──────────┬──────────┬──────────┬──────────┬──────────┬──────────┐
│  byte 0  │  byte 1  │  byte 2  │  byte 3  │   0xF7   │   0x00   │
├──────────┴──────────┼──────────┴──────────┼──────────┴──────────┤
│   command_index     │       value         │     哨兵            │
│      (u16 LE)       │     (u16 LE)        │                      │
└─────────────────────┴─────────────────────┴─────────────────────┘
```

`value` 字段编码按键分配，包含两个子字段：

```text
value (u16 LE) = [key_code: 高 8 位] [flags: 低 8 位]
```

## 保存流程

已修改的记录在原 blob 的对应偏移位置拼接替换。未修改的记录和所有非记录区域原样通过。

```mermaid
flowchart LR
    KBIN["list[KeyBinding]"] --> SPLICE{"kb.is_modified?"}
    BLOB["_binary_blob<br/>（原始字节）"] --> SPLICE
    SPLICE -->|"是"| REENC["kb.to_bytes()"]
    SPLICE -->|"否"| KEEP["保留原始字节"]
    REENC --> MERGE["写入 kb._offset 位置"]
    KEEP --> MERGE
    MERGE --> OUT["重组后的 blob<br/>未修改部分逐字节一致"]
```

## Plist 往返策略

`_plist.py` 适配器在加载时深拷贝原始的 `KeyCommandColors` 和
`KeyCommandShortNames` 字典。写入时，将内存中的编辑覆盖到原始副本上。这保
留了不符合类型模型的条目（如颜色字典中的 `"New Child" -> ""`）。

```mermaid
sequenceDiagram
    participant File
    participant Plist as _plist.py
    participant Model as LogikcsFile
    participant Codec as _binary.py

    File->>Plist: plistlib.load()
    Plist->>Plist: deepcopy 原始颜色和名称字典
    Plist->>Codec: decode_commands(binary_raw)
    Codec-->>Plist: (bindings, blob_copy)
    Plist->>Model: LogikcsFile(raw_copies, bindings, blob)

    Note over Model: 用户修改颜色 / 名称 / 按键绑定

    Model->>Plist: save(path)
    Plist->>Plist: 将编辑覆盖到原始字典上
    Plist->>Codec: encode_commands(blob, bindings)
    Codec-->>Plist: 拼接后的二进制字节
    Plist->>File: plistlib.dump()
```

## 组件契约

| 模块 | 职责 | 持有状态 |
| --- | --- | --- |
| `_model.py` | 领域类型、校验、无 I/O | `LogikcsFile`, `KeyBinding`, `ColorMap`, `ShortNameMap` |
| `_plist.py` | Plist XML I/O、原始字典覆盖 | 无（纯函数） |
| `_binary.py` | 哨兵扫描、记录编解码、拼接 | 无（纯函数） |
| `_touchbar.py` | Zlib 解压/压缩 | 无（纯函数） |
| `__init__.py` | 公共 API 重导出 | 无 |
| `_cli.py` | argparse CLI | 无 |

依赖方向：`__init__` -> `_model` ← `_plist` -> `_binary`, `_touchbar`。
无循环导入；`_model` 不从本包导入任何模块。

## 关键决策

1. **不透明 blob + 类型化覆盖** — 二进制区域保留为原始字节；类型化记录从已知位置
   解析。写入时，已修改记录拼接替换；其余原样通过。以部分格式理解为代价，换取
   确定的往返保真。
2. **基于位置的拼接** — 每条 `KeyBinding` 记录其在原始 blob 中的字节偏移。编码时
   仅将已修改的记录写入其精确位置，间隙和未修改记录保持逐字节一致。
3. **Plist 区域的原始字典副本** — 加载时深拷贝 `KeyCommandColors` 和
   `KeyCommandShortNames` 的原始字典。保存时覆盖编辑。这保留了不符合类型模型的
   条目（如 `"New Child"` 键对应空字符串值）。
4. **零依赖** — 仅使用 Python 3.11+ 标准库。`plistlib` 处理 XML；`base64` 和
   `zlib` 处理二进制编解码。

## 权衡

| 决策 | 收益 | 代价 |
| --- | --- | --- |
| 哨兵扫描解析记录 | 无需完整格式规范 | 若 `0xF7 0x00` 出现在载荷中则出错 |
| 位置拼接 | 保证未修改字节完整保留 | 每条记录需存储 `_offset` |
| 原始字典副本 | 非标准 plist 条目得以保留 | 每区域两份表示（原始 + 类型化） |
| 无外部依赖 | 零安装成本 | plist 写入较慢（stdlib `plistlib` 为纯 Python） |
