# Codex Provider Tool

一个不绑定任何中转站的 Codex 供应商切换工具。提供 Windows 便携 EXE 和命令行入口，可切换中转与官方登录、获取中转模型列表，并在修改配置前自动备份。

普通切换保持活动 `model_provider` 会话标识不变，减少因 Provider ID 改变导致旧聊天不可见的问题。工具不编辑 Codex SQLite、会话 JSONL 或聊天正文，也不提供通用聊天记录修复功能。

[下载 Windows EXE](https://github.com/w1x2a/codex-provider-tool/releases/download/v1.0.9/CodexProviderTool.exe) · [下载完整 ZIP](https://github.com/w1x2a/codex-provider-tool/releases/download/v1.0.9/CodexProviderTool-windows-x64.zip) · [所有版本](https://github.com/w1x2a/codex-provider-tool/releases) · [更新记录](CHANGELOG.md)

## 下载与运行

下载链接固定到当前已发布版本 **v1.0.9**；`main` 分支还可能包含尚未创建 Release 的修复，具体见[更新记录](CHANGELOG.md)。

| 文件 | 用途 |
| --- | --- |
| [CodexProviderTool.exe](https://github.com/w1x2a/codex-provider-tool/releases/download/v1.0.9/CodexProviderTool.exe) | 图形界面，下载后双击，无需安装 Python |
| [CodexProviderTool-cli.exe](https://github.com/w1x2a/codex-provider-tool/releases/download/v1.0.9/CodexProviderTool-cli.exe) | 命令行检查、切换和模型设置 |
| [CodexProviderTool-windows-x64.zip](https://github.com/w1x2a/codex-provider-tool/releases/download/v1.0.9/CodexProviderTool-windows-x64.zip) | GUI、CLI、PowerShell 包装脚本、说明与校验文件 |
| [SHA256SUMS.txt](https://github.com/w1x2a/codex-provider-tool/releases/download/v1.0.9/SHA256SUMS.txt) | 对照检查 EXE 的 SHA-256 |

要求：Windows x64。工具可以查看配置，但官方登录与中转 API-key 登录仍需要可用的 Codex CLI；Windows 的“官方登录”还需要 PowerShell 7，且 `codex`、`pwsh` 可从 PATH 找到。

本版发布附件只有 Windows 产物。仓库保留 Linux 构建脚本，但旧 Linux 包不包含本版全部新功能，不能当作 v1.0.9 使用。

## 新功能一览

| 功能 | 实际行为 |
| --- | --- |
| 中转模型同步 | 当前中转卡片新增“模型”，请求该中转的 `/models`，选择后仅修改顶层 `model` |
| GPT-6 模型选择 | 保留当前仍有效的模型；需要推荐新模型时优先考虑 `gpt-6-astra`、`gpt-6`，也允许手动填写中转支持的 ID |
| 官方登录入口 | 固定显示“OpenAI 官方（ChatGPT/Cookie 登录）”，可切回官方或启动 `codex login` |
| 官方登录恢复 | 切换内置 `openai` 到中转 API Key 前，备份文件型官方登录状态；切回时恢复已有快照 |
| 现有官方聊天走中转 | 保持 `openai` 身份，通过 `openai_base_url` 指向中转，使用 Codex 的 API-key 登录流程 |
| 完整供应商配置交换 | 自定义会话身份之间交换整个供应商配置，包括嵌套 `auth` 表 |
| 中转 Key 隔离 | API Key 快照按供应商名称与 Base URL 绑定；切换时不会拿当前中转的 Key 代替目标中转缺失的 Key |
| 旧官方身份修复 | 提供需确认的“修复官方旧会话”，仅处理旧版切换导致的配置身份错误 |
| 通用接入与自动备份 | 无中转预设、官网推广或渠道监控绑定；自动规范化 URL、备份配置，并修复已知旧版 TOML 表头损坏 |

“Cookie 登录”指 Codex 自己管理的 ChatGPT 登录状态，不是导入浏览器 Cookie；工具不会索取浏览器 Cookie 字符串。

## 三步接入中转

1. 打开工具，确认顶部 Codex 配置目录指向实际使用的目录。
2. 点击“添加供应商”，填写 Provider ID、名称、Base URL、Model 和中转 API Key。使用已有官方 `openai` 身份时，保留 `responses` 和“需要 OpenAI auth”。可以只勾选保存 Key，稍后切换；需要立刻应用时再勾选“保存后立即启用”。
3. 保存后，等正在运行的任务结束，**完全退出 Codex（包括后台进程），再重新打开**。发送一条测试消息，同时核对中转后台请求日志。

Provider ID 使用字母、数字、下划线或连字符，例如 `relay_a`；不要用内置保留 ID `openai` 创建中转。

Base URL 缺少 `/v1` 时会自动补齐，重复的 `/v1/v1/` 会合并。建议使用 HTTPS，避免 API Key 在明文 HTTP 中传输。

**配置已保存 ≠ Codex 已重新加载 ≠ 中转真实请求已验证。** 工具的“检测”只请求 `GET /models`，不会验证生成回复或 WebSocket 流式传输。

## 切换模型，包括 GPT-6

- 在当前中转卡片点击“模型”，等待列表刷新，选择后点击“应用模型”。
- 添加/编辑供应商时，修改 Base URL 或 API Key 也会重新获取模型，支持点击“获取模型”手动刷新。
- 模型下拉框可编辑；只有中转实际支持的 ID 才能使用。`gpt-6` 可能是中转别名，不能假定与 `gpt-6-astra` 等价。
- 修改后完全退出并重新打开 Codex，再检查实际任务使用的模型。

### 工具有 GPT-6，为什么 Codex 菜单没有？

这里有两个列表：**本工具显示的中转 `/models` 列表**，以及 **Codex 桌面端自己的模型菜单**。

自 v1.0.8 起，工具负责获取前者和写入顶层 `model`，没有实现桌面模型目录的自动同步，也不会自动配置 `model_catalog_json`。因此不能承诺中转返回的每个模型都会出现在 Codex 菜单里，或已有任务都会自动换模型。

若重启后仍缺少模型，需要单独核对当前 Codex 的模型目录、菜单筛选和任务设置。某台电脑单独配置的模型目录不属于本 EXE 的内置功能；不要为了补菜单而修改聊天数据库或 JSONL。

## 切回官方 / 恢复登录

1. 在“OpenAI 官方（ChatGPT/Cookie 登录）”卡片点击“切换”。
2. 工具会尝试恢复此前保存的官方 `auth.json` 快照；内置 `openai` 路由会移除中转地址覆盖。
3. 若提示没有快照，先点“官方登录”，完成后再切换到官方；若已切回官方但登录过期，在官方配置下重新登录即可，不要再次恢复过期快照。
4. 完全退出并重新打开 Codex。

备份恢复针对本地 `auth.json`。操作系统凭据库由 Codex 管理，本工具不会导出或备份整个系统凭据库，也不能保证已过期的快照仍能登录。

自定义会话身份切回官方时，工具在该身份下交换官方认证配置；中转配置仍保留。内置 `openai` 中转路线只支持本工具认可的 Responses/API-key 配置；遇到不能兼容的嵌套认证或其他选项会拒绝切换，而不是丢弃这些选项。

## 备份在哪里？

备份保存在**被修改文件的同一目录**，不是 EXE 所在目录。通常是 `%USERPROFILE%\.codex`；指定了 `CODEX_HOME` 或工具目录时，以实际选择为准。

| 文件名形式 | 内容 |
| --- | --- |
| `config.toml.bak-provider-tool-<时间戳>` | 修改前的供应商或模型配置 |
| `auth.json.bak-provider-tool-official-auth-<时间戳>` | 切到中转前的文件型官方登录快照 |
| `auth.json.bak-provider-tool-relay-profile-<摘要>-<时间戳>` | 仅保存对应供应商的 API-key 认证快照；摘要由名称与 Base URL 生成 |
| `config.toml.bak-provider-tool-auto-repair-<时间戳>` | 修复已知旧版 TOML 表头损坏前的配置 |

只有原文件存在且相应操作发生时才会产生备份。CLI 会打印具体备份路径；GUI 可通过“打开目录”查看。

恢复前先完全退出 Codex，另存当前配置，再选择对应时间点的备份恢复原文件名。配置与认证应匹配同一目标供应商；不要只恢复旧地址却保留另一家的 Key。认证备份含敏感凭据，不能上传到 GitHub、截图公开或随安装包分发。

## 常见问题

| 现象 | 应检查什么 |
| --- | --- |
| 切换后中转后台没有请求 | 配置目录是否正确、是否完整退出并重开、当前任务是否已加载新路由；再用真实回复请求核对日志 |
| `/models` 返回 401/403 | API Key、授权范围以及是否选错中转；以返回的真实错误为准 |
| 提示目标中转没有自己的 Key | 编辑该供应商，重新填写它自己的 API Key 并勾选保存；可立即启用，也可稍后切换，工具不会复用另一个中转的 Key |
| `/models` 返回 404 | Base URL 与中转是否提供该接口；不能直接据此判断回复接口一定不可用 |
| “重新连接 5/5”或流提前断开 | 检查中转 Responses/WebSocket 支持和网关日志；模型列表可访问不能证明流式链路正常 |
| 提示找不到官方登录备份 | 使用“官方登录”重新登录，再应用官方配置 |
| 切换后旧聊天不可见 | 先核对原来的 Provider ID；仅原先为官方 `openai`、被旧版工具改过身份的情况适合“修复官方旧会话” |
| 对话中间的消息缺失 | 不属于本工具的修复范围；保留原始数据，单独排查历史索引/加载问题 |

“修复官方旧会话”是普通切换之外的**显式例外**：它会把配置中的 `model_provider` 恢复为 `openai`，再应用所选中转。不修改聊天文件、不合并不同身份的历史，也不保证修复所有记录显示问题。原本就是自定义身份的用户不要随意使用。

## 命令行

在完整包解压目录中，用 PowerShell 7 执行：

```powershell
$ErrorActionPreference = 'Stop'
$PSNativeCommandUseErrorActionPreference = $true

.\CodexProviderTool-cli.exe check
.\CodexProviderTool-cli.exe check --remote
.\CodexProviderTool-cli.exe models
```

常用命令：

| 命令 | 用途 |
| --- | --- |
| `model gpt-6-astra` | 仅修改顶层模型；不会检查该模型是否能实际生成回复 |
| `use relay_a` | 应用已配置中转；内置官方身份需有可用中转 API Key |
| `use openai` | 应用官方配置并尝试恢复官方登录 |
| `login` | 启动 Codex 官方登录流程 |
| `--codex-home "D:\some\codex-home" check` | 查看指定目录；全局参数放在子命令前 |

详细参数、密钥注意事项和源码运行方式见 [CLI 使用说明](scripts/CODEX-PROVIDER-TOOL.md)。

## 从源码运行与构建

需要 Python 3.11+；GUI 还需要 Tkinter。以下命令从仓库根目录执行：

```powershell
$ErrorActionPreference = 'Stop'
$PSNativeCommandUseErrorActionPreference = $true

python .\scripts\codex_provider_gui.py
```

Windows 打包需要 PyInstaller：

```powershell
$ErrorActionPreference = 'Stop'
$PSNativeCommandUseErrorActionPreference = $true

python -m pip install pyinstaller
pwsh -NoProfile -File .\scripts\Build-CodexProviderTool.ps1
```

产物：`dist/CodexProviderTool-windows-x64.zip`。打包会复制 [Windows 包内说明](scripts/CODEX-PROVIDER-TOOL-PACKAGE-README.md)，仅修改仓库文档不会更新已经发布的 ZIP。

回归测试：

```powershell
$ErrorActionPreference = 'Stop'
$PSNativeCommandUseErrorActionPreference = $true

python -m unittest discover -s scripts -p "test_*.py"
```

GUI 测试需要桌面/Tk 环境。测试使用临时配置和本地模拟接口，不代表某个真实中转或用户的 Codex 菜单已经验证。

Linux 构建与限制见 [Linux 说明](scripts/CODEX-PROVIDER-TOOL-LINUX-README.md)。

## 数据边界

工具只围绕供应商配置、选择的模型和登录状态工作，不修改 Codex 程序文件，不编辑 SQLite/JSONL，不迁移聊天。发布包不包含用户配置、API Key、Cookie、个人模型目录或登录备份。
