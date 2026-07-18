# NewsFlow 流水线、配置与验证

本文记录可由当前代码直接验证的运行知识。临时排查过程、个人环境值和暂停中的远期设想不写入本文。

## 入口与职责

| 入口 | 实现 | 用途 |
| --- | --- | --- |
| `python main.py <command>` | `main.py` → `src/cli/cli.py` | 独立 CLI |
| `python main.py web --host 127.0.0.1 --port 8000` | `src/web/app.py` | FastAPI 管理后台、定时调度与独立渲染端点 |
| `NewsScheduler._daily_task()` | `src/scheduler/scheduler.py` | 独立运行时的每日流水线 |
| AstrBot 适配层 | 见 `docs/architecture.md` | 聊天命令、Plugin Page、主动推送与容器内图片渲染 |

## 独立运行流水线

当前 `NewsScheduler._daily_task()` 按以下顺序执行：

1. `NewsCollector.collect_news()`：并行采集启用的 RSS 和网页源。
2. `NewsStorage.save_news()`：按 `content_hash` 和数据库约束跳过重复项。
3. `AIFilter.filter_news()`：日期准入、统一规则粗筛、AI/关键词评估、文章/事件去重、合格备用候选补位，以及故事、来源和主题组合约束。
4. `AITranslator.translate_news()`：在启用且配置 AI 时翻译英文新闻，并保存原文/译文；稳定的 `event_key`/`story_key` 不随翻译标题变化。
5. `NewsletterGenerator.generate()`：生成 HTML、写入 `newsletters` 表，并仅为实际发布条目记录事件记忆。
6. `EmailSender.send_newsletter()`：仅在 SMTP 配置完整时发送。
7. `NewsStorage.clean_old_news(days=7)`：清理旧新闻。

独立调度器与 AstrBot 适配层均复用上述核心筛选语义，翻译后不得再次按标题文本去重。默认配额和上限来自 `Settings.filter_settings`：最终上限 20、软性最低目标 16、候选池倍率 3、单一来源最多 4、同一故事最多 2，政策监管/财经市场/科技产业/国际局势目标条数分别为 5/4/8/3。

AI 精筛默认要求结构化结果覆盖批次全部索引。DeepSeek 每批 10 条，输出上限 4000 tokens；响应为空时关闭 JSON mode 重试，响应为非法或不完整 JSON 时最多拆半两层重试。拆分后仍无法解析的条目仅在命中现有包含规则且通过统一粗筛时进入显式关键词回退；已经得到有效 AI 结论但被排除的条目不会因候选数量不足而重新加入。主候选完成文章和事件去重后，若少于软性目标 16 条，只从已完成 AI 评分、综合分不低于 4 且分类不是“其他”的备用候选补位。AI 文章去重只在明确同一事件、同一具体动作或同一链接时移除；对不同公司的业绩、融资、回购和产能新闻，若没有高置信度重复证据会保护性恢复。AI 模式和无 AI 的关键词模式最终共用同一套事件去重、来源上限、故事上限和主题组合选稿，不再执行无条件粗筛补位或国内来源保底。英文新闻翻译同时覆盖最终会展示的 `ai_summary`，不再只翻译标题而留下英文摘要。

事件记忆仅在简报成功生成并落库后写入。跨简报去重同时比较规范化 `event_key` 和去除常见跟踪参数的规范化 URL，避免同一链接因模型生成的事件键变化而重复发布。数据库读取结果使用 `_published_timezone` 标记已经转换为 Asia/Shanghai 的无时区展示字符串，日期过滤不得再次把该字符串解释为 UTC。

## 配置来源

- 默认配置定义在 `src/config/config.py` 的 `Settings`。
- 本机覆盖值从根目录 `api_config.env` 加载；该文件被 Git 忽略。
- AI 客户端在 `src/filter/filter.py` 中按 `AI_PROVIDER` 选择兼容端点、默认模型、批量大小和重试策略。
- 新闻源列表来自 `Settings.news_sources`。源是否启用以配置中的 `enabled` 为准，README 不应把已配置但禁用的源描述为默认启用。
- 财联社使用可由 `CLS_RSS_URL` 覆盖的 RSSHub Feed，默认容器地址为 `http://rsshub:1200/cls/telegraph`。该源按配置绕过外网代理，空原文链接会转换为不可点击的稳定 `urn:newsflow:cls:<sha256>` 内部标识，并作为普通财经源进入通用筛选。部署边界和验收记录见 [`cls-rsshub-integration.md`](cls-rsshub-integration.md)。
- Reuters 当前配置为 `https://feeds.reuters.com/reuters/topNews` 的直接 RSS，不使用官方 API，也不使用网页识别。2026-07-19 当前容器实测该 Feed 出现 SSL EOF；自建 RSSHub 已注册 Reuters 路由，但 `business`、`markets` 和 `world` 路由同日返回 HTTP 503，因此暂不切换到 RSSHub，避免把当前可观察的单源网络问题变成固定的上游路由失败。
- 数据库默认路径是 `data/news.db`；简报默认写入 `output/`。

不要在文档中记录本机 API Key、代理端口、SMTP 凭据或当前账户套餐。提供商价格、免费额度、模型可用性等外部事实会变化，应以提供商当前文档和账户控制台为准。

## SQLite 数据

`src/storage/storage.py` 当前初始化以下表：

- `news`：新闻正文、来源、发布时间、分类、哈希、原文/译文状态。
- `news_sources`：可管理的新闻源。
- `filter_rules`：包含、排除和最大条数等筛选规则。
- `newsletters`：按日期保存生成的 HTML 简报。
- `event_fingerprints`：事件级去重记忆。

Schema 以 `NewsStorage._init_database()` 的 `CREATE TABLE` 和迁移语句为准；文档不复制易漂移的完整列清单。

## CLI 命令

Click 当前注册的命令为：

- `collect`
- `run`
- `filter`
- `translate`
- `generate`
- `web`
- `status`
- `clean`
- `list-news`

以 `python main.py --help` 为最终事实。新增或重命名命令时，应同步更新 README 和契约测试。

## 测试与验证边界

仓库提供无外部副作用的结构与行为测试，覆盖 CLI 契约、财联社空链接 RSS、稳定内部身份、按源代理绕过、RSS 条数上限、候选池、统一关键词准入、分类/来源/故事约束、非法 JSON 拆批恢复、去重后备用候选补位、规范化 URL 事件去重、合成链接展示、外媒时间过滤、翻译前缀清理、发布后事件记忆和独立/AstrBot 去重一致性。运行：

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

语法检查：

```powershell
.\.venv\Scripts\python.exe -c "import ast, pathlib; [ast.parse(p.read_text(encoding='utf-8')) for p in [pathlib.Path('main.py'), *pathlib.Path('src').rglob('*.py'), *pathlib.Path('tests').rglob('*.py')]]"
```

新闻源、DeepSeek 筛选与翻译、Docker 挂载、AstrBot 重启、Cron 运行和容器内 Playwright 渲染已在 2026-07-16 至 2026-07-18 的实际流水线中验证。SMTP、其他 AI 提供商和主动消息平台的自动化集成矩阵当前不在本阶段范围内；现有单元测试不能替代这些外部系统验证。
