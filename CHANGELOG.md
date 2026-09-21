# 更新记录

功能以对应版本源码为准，二进制支持平台以该版本 Release 附件为准。[全部发布版本](https://github.com/w1x2a/codex-provider-tool/releases)

## 未发布 · 文档整理与认证隔离

- 中文化项目首页、CLI 和 Windows 包内说明，补充已发布的新功能与直接下载入口。
- 补齐官方登录恢复、备份文件位置、重启生效要求及真实请求验证步骤。
- 说明工具中转模型列表与 Codex 桌面菜单的区别，不再暗示获取 `/models` 就能自动更新桌面菜单。
- 明确旧官方身份修复的例外行为、文件型认证恢复边界及 Linux 未重建状态。
- 修复中转之间切换时可能沿用当前供应商 API Key 的问题；Key 快照改为按供应商名称与 Base URL 绑定。
- 自定义稳定 `model_provider` 身份下，普通 API-key 供应商也会切换 Codex 登录认证；自带嵌套 `auth`、`env_key` 或静态令牌的配置仍按完整供应商表交换。
- 登录没有实际落入目标 Key 时回滚配置与文件型认证，旧版按 Provider ID 保存的快照仅在不会交换表 ID 的内置 `openai` 路线兼容读取。
- 已重新构建并验证本地 Windows 包；这里仍是未发布变更，不代表已经创建新的 GitHub Release。

## [v1.0.8](https://github.com/w1x2a/codex-provider-tool/releases/tag/v1.0.8) · 中转模型选择

- 当前中转卡片新增“模型”，读取中转返回的完整模型列表并应用选择。
- 当前模型仍有效时保留；需推荐时优先考虑 GPT-6 相关 ID，保留中转返回的别名，也允许手动输入。
- 新增 `model <model_id>` 命令，仅修改顶层 `model` 并备份，不更改 Provider ID。
- 修改后提示完全退出并重新打开 Codex。
- 此版不包含桌面模型目录自动同步，不保证所有中转模型自动出现在 Codex 菜单。

## [v1.0.7](https://github.com/w1x2a/codex-provider-tool/releases/tag/v1.0.7) · 官方旧会话路由与认证

- 原本使用内置 `openai` 的聊天保持该身份，通过 `openai_base_url` 使用中转。
- 中转 API Key 交给 Codex 的 API-key 登录流程，官方文件型登录状态先备份、切回时恢复。
- 增加显式“修复官方旧会话”选项，纠正旧版造成的配置身份变化。
- 不兼容的高级供应商选项拒绝切换；登录失败时回滚配置和文件型认证状态。
- 明确区分配置保存、重启加载与实际中转流量验证。

## [v1.0.6](https://github.com/w1x2a/codex-provider-tool/releases/tag/v1.0.6) · 官方登录入口

- 固定显示“OpenAI 官方（ChatGPT/Cookie 登录）”卡片。
- 新增“官方登录”按钮和 `login` 命令，启动 Codex 官方登录。
- 在已有自定义会话身份下交换官方配置，保留原中转配置以便切回。
- 此版本的登录复用与后续 v1.0.7 的认证快照恢复不同，使用方法以对应版本为准。

## [v1.0.5](https://github.com/w1x2a/codex-provider-tool/releases/tag/v1.0.5) · 无中转绑定

- 移除特定中转站的预设、官网入口和渠道监控绑定。
- 普通切换保持活动 `model_provider`，交换完整供应商表及嵌套认证配置。
- 无法安全保持现有身份时拒绝切换，而不是直接改 ID。

## 发布边界

v1.0.5–v1.0.8 发布的是重新构建的 Windows 产物；不要把历史 Linux 附件视为这些版本。上述工具功能均不编辑 Codex SQLite、会话 JSONL 或聊天正文；单机历史索引修复、个人模型目录配置和服务端网关调整没有打包进本工具。
