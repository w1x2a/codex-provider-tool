# Codex Provider Tool · Windows 使用说明

Windows x64 便携工具，不绑定任何中转站，不需要安装 Python。双击 `CodexProviderTool.exe` 打开图形界面；命令行使用 `CodexProviderTool-cli.exe`。

[项目说明](https://github.com/w1x2a/codex-provider-tool) · [版本下载](https://github.com/w1x2a/codex-provider-tool/releases)

## 当前构建功能（v1.0.8 后续修复）

- 当前中转卡片的“模型”按钮：获取中转完整 `/models` 列表，应用所选模型。
- 保留当前可用模型；需要推荐新模型时优先考虑 `gpt-6-astra`、`gpt-6`，支持手动输入真实中转模型 ID。
- 固定显示“OpenAI 官方（ChatGPT/Cookie 登录）”，支持官方登录与文件型登录快照恢复。
- 普通切换保持活动 `model_provider`；内置 `openai` 使用中转地址覆盖，自定义身份交换完整供应商表及嵌套认证表。
- 中转 API Key 按供应商名称与 Base URL 独立保存；目标缺少 Key 时拒绝切换，不复用当前中转 Key。
- 修改前自动备份；支持已知旧版 TOML 表头修复和需确认的“修复官方旧会话”。
- Base URL 自动补齐 `/v1`、合并重复结尾；新增供应商直接进入通用表单。

## 快速使用

1. 确认工具顶部的 Codex 配置目录。
2. 添加供应商，输入 Base URL、Model、API Key 等信息。已有官方身份使用 `responses`，保留“需要 OpenAI auth”，勾选保存 Key 和立即启用。
3. 保存后等当前任务结束，完全退出 Codex（包括后台）并重新打开。
4. 发送测试消息，对照中转后台日志确认请求确实经过目标中转。

工具“检测”只发送 `GET /models`。检测通过不能证明回复请求、WebSocket、计费或已有任务路由已生效。

## 切回官方与 Cookie 恢复

在官方卡片点击“切换”。工具尝试恢复此前的官方 `auth.json` 快照，并在内置 `openai` 路线移除中转地址覆盖。没有快照时，先“官方登录”再切换；已有快照但已过期时，先切回官方配置再重新登录，不要再次恢复过期快照。完成后重开 Codex。

“Cookie”是 Codex 管理的登录状态，不是浏览器 Cookie 导入。本工具不备份整个系统凭据库；系统凭据库或过期登录请交由 Codex 重新认证。

官方登录需要 PATH 中的 `codex` 和 PowerShell 7（`pwsh`）。中转 API-key 激活也需要可用的 Codex CLI。内置 `openai` 路线无法保留的高级供应商选项会被拒绝，不会静默忽略。

## 模型列表与 GPT-6

在当前中转卡片点击“模型”，选择后应用，再完全退出并重新打开 Codex。中转别名 `gpt-6` 与 `gpt-6-astra` 不保证等价，以中转提供的 ID 为准。

本工具的模型下拉框与 Codex 桌面菜单是两套列表。v1.0.8 只读取中转列表并修改顶层 `model`，不自动维护桌面模型目录或 `model_catalog_json`。重启后 Codex 仍不显示模型时，应单独排查客户端模型目录与任务设置；不要修改聊天数据来补菜单。

## 备份在哪里？

在当前选定的 Codex 配置目录中，通常为 `%USERPROFILE%\.codex`，不是程序目录。GUI 的“打开目录”可查看，CLI 会打印具体路径。

| 文件名形式 | 备份内容 |
| --- | --- |
| `config.toml.bak-provider-tool-<时间戳>` | 修改前的配置 |
| `auth.json.bak-provider-tool-official-auth-<时间戳>` | 文件型官方登录状态 |
| `auth.json.bak-provider-tool-relay-profile-<摘要>-<时间戳>` | 对应供应商的 API-key 认证快照 |
| `config.toml.bak-provider-tool-auto-repair-<时间戳>` | 自动修复旧表头前的配置 |

原文件存在且相应操作发生才有备份。恢复前先退出 Codex、另存当前文件，选择正确时间点的配置/认证备份，恢复为原文件名。不要混用不同供应商的地址与 Key。认证备份不能公开或随包分享。

## 旧聊天相关说明

普通切换保持身份，不编辑 SQLite、会话 JSONL 或聊天正文。

“修复官方旧会话”仅用于原来的 `openai` 身份被旧版工具改掉的情况。这个显式操作会恢复配置中的 `openai` 身份，不是通用聊天恢复，也不修复对话中间缺失的消息。原本就是自定义身份时不要随意使用。

## 命令行与校验

在解压目录的 PowerShell 7 中执行以下只读检查：

```powershell
$ErrorActionPreference = 'Stop'
$PSNativeCommandUseErrorActionPreference = $true

.\CodexProviderTool-cli.exe check
.\CodexProviderTool-cli.exe models
Get-FileHash -LiteralPath .\CodexProviderTool.exe -Algorithm SHA256
Get-FileHash -LiteralPath .\CodexProviderTool-cli.exe -Algorithm SHA256
```

将输出哈希与同版本 `SHA256SUMS.txt` 对照，不匹配时停止运行。

另可按需使用 `model gpt-6-astra`、`use openai`、`login`；指定目录用 `--codex-home "D:\some\codex-home" check`。包装脚本 `CodexProviderTool.ps1` 为可选入口。

包内不包含任何用户配置、API Key、Cookie、个人模型目录或登录备份。
