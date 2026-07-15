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
```

默认读取 `$CODEX_HOME` 或 `~/.codex`。切换供应商时会保持活动 `model_provider` 会话标识，因此已有聊天记录不会因为中转站切换而被隐藏。

添加供应商窗口中的 **Anxiii 中转站 · 打开官网** 按钮会直接打开 `https://anxiii.com/`。

## 校验

```bash
sha256sum -c SHA256SUMS.txt
```

包内不包含用户配置、API Key、Cookie 或登录状态。
