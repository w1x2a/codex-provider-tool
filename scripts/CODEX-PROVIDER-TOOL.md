# CLI 使用说明

本说明对应 v1.0.9 源码与 Windows CLI。图形界面下载、功能概览和常见问题见 [项目 README](../README.md)。

## 入口与目录

完整包中使用 `CodexProviderTool-cli.exe`；源码运行使用 `python .\scripts\codex_provider_tool.py`。仓库中没有 `Invoke-CodexProviderTool.ps1`。

以下示例在仓库根目录的 PowerShell 7 中执行：

```powershell
$ErrorActionPreference = 'Stop'
$PSNativeCommandUseErrorActionPreference = $true

python .\scripts\codex_provider_tool.py --help
python .\scripts\codex_provider_tool.py --codex-home "D:\some\codex-home" check
```

目录解析顺序：

1. 显式 `--codex-home`。
2. 环境变量 `CODEX_HOME`。
3. 优先检查用户目录的 `.codex`，再检查当前目录的 `.codex`；选择存在 `config.toml` 或 `auth.json` 的目录。
4. 均不存在时，默认用户目录的 `.codex`。

不要仅凭 EXE 的存放位置推断正在修改哪个 Codex 配置。全局参数 `--codex-home` 必须放在子命令前。

## 命令速查

| 命令 | 行为 | 是否写入 |
| --- | --- | --- |
| `check` / `check --json` | 配置、供应商和脱敏 Key 状态 | 否 |
| `check --remote` | 额外检测当前中转的 `/models` | 否，发送网络请求 |
| `models [provider_id]` | 列出目标中转返回的模型 ID | 否，发送网络请求 |
| `add <provider_id>` | 添加/更新供应商，可选激活 | 是 |
| `use <provider_id>` | 切换供应商或官方登录 | 是 |
| `model <model_id>` | 只设置顶层 `model` | 是 |
| `login` | 启动 Codex 登录，由 Codex 保存认证 | 是，交互式登录 |

网络检测只请求 `GET /models`，不发送生成回复请求。它不能验证模型实际可用性、账单归属或 WebSocket 流式传输。

## 检查与读取模型

```powershell
$ErrorActionPreference = 'Stop'
$PSNativeCommandUseErrorActionPreference = $true

python .\scripts\codex_provider_tool.py check
python .\scripts\codex_provider_tool.py check --json
python .\scripts\codex_provider_tool.py check --remote --timeout 10
python .\scripts\codex_provider_tool.py models relay_a --timeout 10
```

`models` 支持临时 `--api-key`、`--api-key-env`、`--timeout`。`check --remote` 支持后两项。只读探测的 Key 选择顺序是：

1. `models --api-key` 显式提供的值。
2. `--api-key-env` 指定的进程环境变量，默认 `OPENAI_API_KEY`。
3. `auth.json` 中同名字段；必要时回退到 `OPENAI_API_KEY`。

探测非当前中转前，要确认使用的是那家中转的 Key；工具不会自动替每家供应商查找独立的探测凭据。`check --json` 脱敏 Key，但仍含本地路径和供应商信息，分享前也应检查。

## 添加与启用中转

先保存定义，不激活、不写入 Key：

```powershell
$ErrorActionPreference = 'Stop'
$PSNativeCommandUseErrorActionPreference = $true

python .\scripts\codex_provider_tool.py add relay_a --label "我的中转" --base-url "https://relay.example/v1" --model "gpt-6-astra" --wire-api responses
```

`relay.example` 只是占位地址，请替换成你自己的服务。Provider ID 只允许字母、数字、下划线、连字符，不能使用保留 ID `openai`。

| 参数 | 说明 |
| --- | --- |
| `--base-url` | 必填；会补齐 `/v1`、去掉重复末尾 `/v1` |
| `--model` | 必填；配合激活时写入顶层模型，仅保存定义时不切换当前模型 |
| `--label` | 可选显示名称 |
| `--wire-api` | `responses`（默认）或 `chat`；内置 `openai` 中转路线仅支持前者 |
| `--requires-openai-auth` | 默认开启；已有内置 `openai` 路线需要保持开启 |
| `--no-requires-openai-auth` | 自定义供应商选项，不适用于保持内置 `openai` 身份的中转路线 |
| `--activate` | 保存后立即应用 |
| `--api-key`、`--write-auth` | 显式保存该供应商专属 Key；可不带 `--activate`，此时不修改当前 `auth.json`，以后切换时再激活 |

实际 Key 建议在 GUI 中填写。把真实 Key 直接放到命令参数里可能进入终端历史或进程参数；工具不输出原始 Key，不代表命令行本身没有泄露风险。

需要全局 OpenAI API-key 认证的普通供应商会调用 Codex 的 `login --with-api-key`，通过标准输入传递目标供应商自己的 Key；这也适用于保持自定义 `model_provider` 会话身份的配置交换。带嵌套 `auth`、`env_key`、静态 bearer token 或明确不需要认证的供应商只交换完整配置表，不覆盖全局登录。

## 切换供应商与官方登录

以下是独立操作示例，按需要选择执行：

```powershell
$ErrorActionPreference = 'Stop'
$PSNativeCommandUseErrorActionPreference = $true

python .\scripts\codex_provider_tool.py use relay_a
```

`use` 可选 `--model`、`--api-key`。工具优先使用显式 Key，其次使用按供应商名称与 Base URL 绑定的认证快照；仅当目标与当前是同一逻辑供应商时才可继续使用当前 `auth.json` 的 Key。目标中转没有自己的 Key 时会拒绝切换，避免把 A 的 Key 发给 B。旧版按 Provider ID 保存的快照只在不会交换表 ID 的内置 `openai` 路线兼容读取。

切回官方：

```powershell
$ErrorActionPreference = 'Stop'
$PSNativeCommandUseErrorActionPreference = $true

python .\scripts\codex_provider_tool.py use openai
```

如果提示没有官方登录快照，先重新登录，再应用官方配置：

```powershell
$ErrorActionPreference = 'Stop'
$PSNativeCommandUseErrorActionPreference = $true

python .\scripts\codex_provider_tool.py login
python .\scripts\codex_provider_tool.py use openai
```

如果存在快照但已过期，应先 `use openai` 切回官方配置，再执行 `login` 更新认证；不要重新恢复那个过期快照。

Windows 官方登录要求 PATH 中存在 `codex` 和 `pwsh`。登录使用选定的 `CODEX_HOME`。官方状态恢复面向文件型 `auth.json`，不会备份或导出系统凭据库，也不导入浏览器 Cookie。

普通切换保持已有 Provider ID。自定义身份会交换完整供应商表及嵌套 `auth`；内置 `openai` 身份使用 `openai_base_url`，不能兼容的高级选项会报错。修改前生成备份；API-key 登录失败时恢复修改前配置和文件型认证状态。

## 只修改模型

```powershell
$ErrorActionPreference = 'Stop'
$PSNativeCommandUseErrorActionPreference = $true

python .\scripts\codex_provider_tool.py model gpt-6-astra
```

该命令只校验 ID 非空、备份配置并写入顶层 `model`，不验证权限或真实回复，也不改变 `model_provider`。必须使用你的中转支持的准确 ID。

GUI 的“模型”功能会先读取中转 `/models`；CLI 的 `model` 不会。两者都不自动改写 Codex 桌面模型目录，不保证桌面菜单立即出现全部中转模型。

## 旧官方会话身份修复：谨慎使用

仅当原来的任务使用 `openai`、旧工具把全局身份改为其他 ID 时，才考虑：

```powershell
$ErrorActionPreference = 'Stop'
$PSNativeCommandUseErrorActionPreference = $true

python .\scripts\codex_provider_tool.py use relay_a --restore-official-identity
```

这不是普通切换：它会明确把全局身份恢复为 `openai` 并应用所选中转。它不改聊天数据库、不合并不同身份的历史，不修复消息缺页或索引损坏。原本就使用自定义身份的任务不应盲目使用此选项。

## 备份、重启与错误

- 配置备份：目标目录下 `config.toml.bak-provider-tool-<时间戳>`。
- 官方认证备份：`auth.json.bak-provider-tool-official-auth-<时间戳>`。
- 中转认证快照：`auth.json.bak-provider-tool-relay-profile-<摘要>-<时间戳>`，摘要由供应商名称与规范化 Base URL 生成。
- GUI 旧版表头修复备份：`config.toml.bak-provider-tool-auto-repair-<时间戳>`。

备份仅在原文件存在且相应操作发生时生成；认证快照与 Key 同样敏感。完整恢复说明见 [README](../README.md)。

修改路由或模型后，先结束运行中的任务，再完全退出 Codex 后重开。不要把配置保存成功、模型列表可访问与真实回复成功混为一谈。

正常命令成功返回 `0`；探测失败返回 `1`；工具参数/配置错误通常返回 `2`。`login` 返回 Codex 登录进程的退出码。保留 HTTP 状态和具体错误用于排查，不要公开错误中可能包含的敏感信息。
