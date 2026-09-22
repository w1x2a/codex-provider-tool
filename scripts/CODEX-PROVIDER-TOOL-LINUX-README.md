# Codex Provider Tool · Linux x64 说明

仓库提供 Linux x86_64 构建脚本，但 **v1.0.9 Release 没有重新构建的 Linux 附件**。历史 Linux 包不能视为包含本版全部功能。

本页供从对应源码自行构建后的使用参考，不代表本次已完成 Linux 图形界面或真实中转验证。

[项目说明](https://github.com/w1x2a/codex-provider-tool) · [版本与实际附件](https://github.com/w1x2a/codex-provider-tool/releases)

## 构建前置

- Linux x86_64、Python 3.11+、PyInstaller。
- GUI 需要 Tkinter、Tcl/Tk 和可用的图形显示环境；服务器无显示环境时使用 CLI。
- 登录需要安装 Codex CLI，并使 `codex` 可从 PATH 找到。
- 构建入口为仓库内 `scripts/Build-CodexProviderTool-Linux.sh`。它调用 `python3`、PyInstaller、`sha256sum` 与 `tar`，必须在适配的 Linux 构建环境执行，不能把 Windows EXE 改名当作 Linux 产物。

预期输出是 `dist/CodexProviderTool-linux-x64.tar.gz`，包含 `CodexProviderTool`、`CodexProviderTool-cli`、README 和 SHA-256 校验文件。

## 使用

下面示例在 Linux 上的 PowerShell 7 中执行，工作目录为解压后的包目录：

```powershell
$ErrorActionPreference = 'Stop'
$PSNativeCommandUseErrorActionPreference = $true

chmod +x ./CodexProviderTool ./CodexProviderTool-cli
./CodexProviderTool-cli --help
./CodexProviderTool-cli check
./CodexProviderTool-cli models
sha256sum -c SHA256SUMS.txt
```

GUI 入口为 `./CodexProviderTool`。无图形桌面时使用 CLI；目录打开、官方浏览器登录等交互依赖本机环境，不能根据 Windows 测试结果判断 Linux 已可用。

默认读取 `CODEX_HOME` 或用户目录的 `.codex`，也可用 `--codex-home` 显式指定。切换或修改模型后，结束运行中的任务，再完全退出并重开 Codex。

## 与当前源码对应的功能

- 不绑定特定中转站；支持 OpenAI 兼容的 `/models` 探测。
- 当前中转可刷新模型列表并应用模型 ID；不会自动同步 Codex 桌面自己的模型目录。
- 普通供应商切换保持活动身份；自定义身份交换完整供应商及嵌套认证表。
- 内置 `openai` 路线通过地址覆盖与 API-key 登录连接中转。
- 官方登录卡片和 `login` 命令；文件型官方登录状态可从先前快照恢复。

旧 Linux 包是否支持某项功能，必须以那个包对应的源码与 `--help` 为准。

## 备份与边界

备份在实际 Codex 配置目录中，与原文件同目录，例如：

- `config.toml.bak-provider-tool-<时间戳>`
- `auth.json.bak-provider-tool-official-auth-<时间戳>`
- `auth.json.bak-provider-tool-relay-<ID>-<时间戳>`

官方恢复会读取已有文件型快照并恢复 `auth.json`，不是“不覆盖认证文件”。系统凭据库不在备份范围内；无快照或过期时需重新官方登录。“Cookie”不表示支持导入浏览器 Cookie。

认证备份含敏感凭据，不能上传或随包分发。工具不编辑 Codex SQLite、会话 JSONL 或聊天正文；“修复官方旧会话”只恢复错误的配置身份，不是消息恢复工具。
