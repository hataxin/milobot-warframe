# 更新日志

## 1.0.1

- **兼容性验证更新**：完成 MaiBot `1.4.5` 实测验证，将 `_manifest.json` `host_application.max_version` 调整为 `1.4.99`。
- **功能调整**：移除 `/紫卡分析` 本地推算指令与旧文档，统一提示「暂未添加紫卡分析功能」；保留 `/wr`、`/cd`、`/xt` 基于 `warframe.market` v2 词典的在线拍卖检索与 R8 偏差计算。
- **仓库精简**：合并冗余说明至 [README.md](README.md) 与 [NOTICE.md](NOTICE.md)。

## 1.0.0

- **MaiBot 原生插件正式发布**：提供国际服 PC Warframe 世界状态卡片、效率工具、市场查价、私聊生成、订阅推送与铸造提醒（支持 `/` 指令与 `@Tool` 调用）。
