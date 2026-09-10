# Codex Provider Tool for Linux x64

这是 Linux x86_64 便携版本，不需要安装 Python。

## 图形界面

解压后运行：

```bash
chmod +x CodexProviderTool CodexProviderTool-cli
./CodexProviderTool
```

需要图形桌面环境和可用的 `DISPLAY`/Wayland 会话。无图形界面的服务器请使用 CLI。

## 命令行

```bash
./CodexProviderTool-cli check
./CodexProviderTool-cli check --remote
./CodexProviderTool-cli models
./CodexProviderTool-cli use openai
./CodexProviderTool-cli login
```

默认读取 `$CODEX_HOME` 或 `~/.codex`。列表会固定显示“OpenAI 官方（ChatGPT/Cookie 登录）”；切换过去会复用 Codex 自己保存的 Cookie/登录缓存，不复制或覆盖令牌内容。切换供应商时会保持活动 `model_provider` 会话标识，因此已有聊天记录不会因为供应商切换而被隐藏。

## 校验

```bash
sha256sum -c SHA256SUMS.txt
```

包内不包含用户配置、API Key、Cookie 或登录状态；切换不会修改 SQLite、会话 JSONL 或已有聊天数据。
