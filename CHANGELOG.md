# 更新日志

## 1.0.0

- **MaiBot 原生插件正式发布**：提供国际服 PC《星际战甲》（Warframe）世界状态查询、效率工具、市场拍卖查价、游戏内私聊生成、订阅推送与个人铸造提醒。
- **双通道接入**：完整支持聊天 `/` 斜杠指令与麦麦自然语言 `@Tool`（`warframe_world_query`、`warframe_market_query`）；紫卡分析暂未实现 OCR 识图功能，当前支持纯文本参数计算。
- **图文卡片与分页**：统一「相变临界」白底浅纹理卡片排版，支持 `-1` / `-w` 纯文本、`-en` 英文市场输出以及 `-页码` 翻页。
- **资源隔离与本地持久化**：基于 `ctx.paths.data_dir/milobot.sqlite3` 维护只读缓存、按会话独立去重的订阅规则与个人铸造到期提醒。
- **Manifest 与配置规范化**：支持 `_manifest.json`（Manifest v2）严格校验、`dependencies` 自动依赖解析及 WebUI 强类型配置表单。
