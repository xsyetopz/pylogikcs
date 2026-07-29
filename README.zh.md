# pylogikcs

读写 Logic Pro `.logikcs` 快捷键预设文件。零依赖，仅需 Python 3.11+ 标准库。

已在 Logic Pro 12.3 `Default.logikcs`（`assets/Default.logikcs`）上验证。

## 安装

```bash
pipx install -e .
```

## 快速开始

```python
import pylogikcs

preset = pylogikcs.load("assets/Default.logikcs")

# 查看
print(preset.version)          # "12.3.0"
print(len(preset.bindings))    # 201

# 修改按键绑定
kb = preset.bindings[4]
kb.key_code = 0x06   # 修改按键
kb.flags = 0x08      # 修改修饰键

# 修改颜色和名称
preset.colors["1012"] = 3
preset.short_names["1012"] = "ReadOff"

# 保存
preset.save("MyPreset.logikcs")
```

## 命令行

```bash
# 查看预设信息
python -m pylogikcs._cli inspect assets/Default.logikcs

# 列出所有按键绑定
python -m pylogikcs._cli list assets/Default.logikcs

# 修改颜色
python -m pylogikcs._cli set-color assets/Default.logikcs 1012 7 -o Modified.logikcs

# 修改绑定
python -m pylogikcs._cli set-binding assets/Default.logikcs 4 --key-code 0x06 --flags 0x08 -o Modified.logikcs
```

也可以用 `justfile`：

```bash
just inspect assets/Default.logikcs
just list assets/Default.logikcs
just test
```

## API

### `pylogikcs.load(path) -> LogikcsFile`

解析 `.logikcs` 文件。

### `LogikcsFile`

| 属性 | 类型 | 说明 |
| --- | --- | --- |
| `version` | `str` | Logic Pro 版本（如 `"12.3.0"`） |
| `content` | `str` | 内容类型标识 |
| `colors` | `ColorMap` | 命令 ID -> 颜色索引 |
| `short_names` | `ShortNameMap` | 命令 ID -> 显示名称 |
| `bindings` | `list[KeyBinding]` | 201 条按键绑定记录 |
| `save(path)` | - | 写入文件 |

### `KeyBinding`

| 属性 | 类型 | 说明 |
| --- | --- | --- |
| `command_index` | `int` | 内部命令索引 |
| `value` | `int` | 原始 16 位数据 |
| `key_code` | `int` | 虚拟键码（0–255），可读写 |
| `flags` | `int` | 修饰键标志（0–255），可读写 |
| `is_modified` | `bool` | 加载后是否被修改 |

### `ColorMap` / `ShortNameMap`

`dict` 子类，带类型校验。键为命令 ID 字符串。

## 文件格式

`.logikcs` 文件为 Apple plist XML (v1.0)，包含：

- `Content` / `Version` - 元数据
- `KeyCommandColors` - `{命令ID: 颜色索引}`
- `KeyCommandShortNames` - `{命令ID: 显示名称}`
- `LogicBinaryPreferences` - base64 编码的二进制数据（6 字节记录：`[4字节载荷][0xF7 0x00]`）
- `TouchBarAssignments` - base64 编码的 zlib 压缩数据

二进制数据已部分逆向。未修改的记录在写入时逐字节保留；已修改的记录在其原始偏移位置拼接替换。

## 测试

```bash
python -m unittest tests.test_logikcs -v
```

30 个测试，覆盖：KeyBinding 解析/编码、ColorMap/ShortNameMap 校验、加载、往返保真、修改持久化、边界情况。

## 许可证

[MIT](LICENSE)
