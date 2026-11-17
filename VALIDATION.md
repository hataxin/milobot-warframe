# Milo bot · Warframe 助手验证记录

- 版本：`1.0.0`（正式版：Milo bot 品牌统一、开源与素材合规完善、全量工具与紧凑卡片）
- 目标宿主与环境：插件 SDK `2.21.0` · Python `3.12` · 运行依赖 `httpx==0.28.1`、`pillow==13.0.0`
- 适用范围：仅国际服 PC（含开启跨平台联机的拍卖行挂单）；按命令及 `@Tool` 按需查询公共数据，提供效率工具计算、紧凑分组与分页卡片、事件订阅时段/单次控制及个人本地铸造提醒，不接触聊天平台私密状态与宿主主库

## 离线质量门禁与依赖审计

在独立 `.venv` 中执行（`pyproject.toml` 启用 Ruff 复杂度与 docstring 规则、`ty` 全量 `error` 级别、Pytest 将所有 warning 视为错误）：

- `ruff format --check .`：通过（`44 files already formatted`）
- `ruff check .`：通过（`All checks passed!`）
- `ty check`：通过（`All checks passed!`）
- `python -m pytest -q`：通过（`197 passed`）
- `python -m pip_audit --disable-pip --require-hashes -r requirements.lock.txt`：通过（`No known vulnerabilities found`）

## 专项验证覆盖

- **品牌统一与包结构（`milo_core/`、`_manifest.json`）**：
  - 插件名设定为 `Milo bot · Warframe 助手`（`github.hataxin.milobot-warframe`），核心包为 `milo_core`，卡片左下角页脚渲染为 `Warframe × Milo bot`，SQLite 数据库为 `milobot.sqlite3`。
  - 全部面向用户的图文输出、帮助菜单、状态文本、错误提示与 SDK `@Command` 注册名（`wf_dispatch`、`wf_market`、`wf_riven`、`wf_lich`、`wf_sister`、`wf_whisper`）均保持统一。
- **通用命令标志与分页（`milo_core/command_flags.py`）**：
  - 校验 `-1`/`-w`/`--text` 强制纯文本回复、`/wm` 支持 `-en` 英文输出、`-2`/`-3` 翻页及 `page_caption`，并保留 `MK1-Braton` 连字符武器名与 `/紫卡分析` 中的负数值（如 `-2`）。
- **紧凑分组排版与视觉重构（`milo_core/render.py`、`milo_core/worldstate.py`、`milo_core/arbitration.py`）**：
  - `/裂缝` 改为紧凑 3 列（「派系 / 任务」+ 颜色编码派系简写 + `§古纪 (T1)` 纪元分组条）并支持关键词筛选与翻页；`/仲裁表` 紧凑分页（含 `所有`）；`/紫卡分析` 中位偏差列增加横轴区间进度条；`/帮助` 改为「相变临界」主题图片菜单卡片。
- **效率工具、市场增强、世界状态扩展与铸造提醒**：
  - 覆盖 `/翻译`、`/融合`、`/升级消耗`、`/开核桃`、`/铜垃圾`、`/wm` 48h/90d 统计与 `/w 1` 预览、`/wr` 黑话筛选与 R8 Omega 偏差、`/瓦奇娅`、`/科研`（全量 `CONQUEST_MODIFIER_NAMES` 中文化）、`/新闻`、`/时效`、`/订阅` 时段与单次控制，以及 `/铸造提醒` 到期自动推送。
  - 全部能力已同步开放给 Milo bot 的 `warframe_world_query` 与 `warframe_market_query` `@Tool`。
