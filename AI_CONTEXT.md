# NewsFlow 项目上下文

## 项目概述

**NewsFlow** v4.2.0 — 多来源 AI 筛选的每日新闻快报系统。从全球多个权威媒体采集新闻，经 AI 智能筛选去重后，按话题分类并翻译为中文，生成简洁的每日简报。

| 维度 | 详情 |
|------|------|
| Python | 3.12+ |
| 入口 | `main.py`（argparse CLI，实际委托 click） |
| 配置 | `src/config/config.py`（Pydantic Settings）+ `api_config.env` |
| 数据库 | SQLite `data/news.db`（5 张表：news, news_sources, filter_rules, newsletters, event_fingerprints） |
| AI SDK | `openai` 库，多提供商兼容（openai/deepseek/gemini/zhipu/groq/qwen） |
| Web | FastAPI + Uvicorn（管理后台） |
| 调度 | APScheduler，每日 6:00 |
| 包管理 | `uv sync` |

## 项目结构

```
src/
├── collector/collector.py   # 采集（RSS + 网页抓取）+ 10 个源并行，ThreadPoolExecutor(4)
├── storage/storage.py       # SQLite 存储（CRUD + 统计）
├── filter/filter.py         # AIClient + AIFilter + AITranslator（~1200行，核心）
├── newsletter/newsletter.py # HTML 简报生成，chat-bubble 风格
├── notifier/notifier.py     # SMTP SSL:465 邮件推送
├── scheduler/scheduler.py   # APScheduler，_daily_task() 8 步流水线
├── web/app.py               # FastAPI 管理后台
├── web/static/index.html    # Web 前端 (vanilla HTML/CSS/JS)
├── cli/cli.py               # Click CLI 命令入口
└── config/config.py         # Pydantic BaseSettings（自动加载 api_config.env）

api_config.env               # API 密钥 + 代理配置（不入 Git）
main.py                      # 入口脚本
README.md                    # 用户文档
data/news.db                 # SQLite（gitignored）
output/newsletter_*.html     # 生成文件（gitignored）
.venv/                       # uv venv（gitignored）
start.bat                    # Windows 启动器
setup_autostart.bat          # Windows 计划任务设置
```

---

## 流水线：8 步时序

```
Step 1 collect → Step 2 save → Step 3 filter → Step 4 translate → Step 5 dedup → Step 6 generate → Step 7 email → Step 8 clean
```

编排在 [scheduler.py:L50-L122](file:///f:/Project/NewsFlow/src/scheduler/scheduler.py#L50-L122)。

### Step 1: Collect [collector.py](file:///f:/Project/NewsFlow/src/collector/collector.py)
- `NewsCollector.collect_news()` — `ThreadPoolExecutor(4)`，并行采集
- 中文源 (web scrape): 新华社, 财联社, 财经杂志, 财新网
- 英文源 (RSS): BBC, NYT, FT, Reuters, 半岛电视台（Bloomberg 禁用）
- 输出: `List[Dict]` 含 `title|summary|link|source|published|category|content_hash`

### Step 2: Save [storage.py](file:///f:/Project/NewsFlow/src/storage/storage.py)
- `NewsStorage.save_news()` — 去重后 `INSERT`，`translated=0`
- `content_hash` = `MD5(title + url)`，非文章正文内容

### Step 3: Filter [filter.py:L336-L348](file:///f:/Project/NewsFlow/src/filter/filter.py#L336-L348)
`AIFilter.filter_news()` → `_two_round_filter()` [filter.py:L473-L510](file:///f:/Project/NewsFlow/src/filter/filter.py#L473-L510):
1. `_filter_by_date()` — 24h 窗口
2. `_coarse_filter()` — 关键词排除（硬编码黑名单 + DB rules + title ≤5 字符）
3. `_ai_semantic_filter()` [filter.py:L789-L811](file:///f:/Project/NewsFlow/src/filter/filter.py#L789-L811) — 批量调用 AI，prompt 要求 JSON `{keep, score, reason, summary(中文)}`，保留 `keep=1 && score>=5`
4. Fill-back: 结果不足 `max(max_news//2, 8)` 时从 coarse 结果补充
5. 去重: `_event_deduplicate()+_title_deduplicate()`（groq/qwen）；`_deduplicate_similar()+_event_deduplicate()`（其他）
6. `_categorize_by_topic()` — 分类 + 配额，按 `category_order` 排序
7. 按 score 降序，截断至 `max_news`（默认 20）
- 输出: `List[Dict]` 含 `ai_summary|relevance_score|topic`

### Step 4: Translate [filter.py:L1049-L1063](file:///f:/Project/NewsFlow/src/filter/filter.py#L1049-L1063)
`AITranslator.translate_news()`:
- 过滤: `category=='英文' && not translated`
- `_translate_batch_text()` [filter.py:L1081-L1138](file:///f:/Project/NewsFlow/src/filter/filter.py#L1081-L1138): batch=5，按 `\n\n` 分割
- 有 `ai_summary` 时仅翻译 title（ai_summary 已是 Step 3 生成的中文）
- 无 `ai_summary` 时翻译 title+summary
- 保存原文到 `title_original|summary_original`，设 `translated=1`
- 解析失败 → `_translate_single_fallback()` [filter.py:L1140-L1178](file:///f:/Project/NewsFlow/src/filter/filter.py#L1140-L1178): 逐条重试
- 通过 `Storage.update_translation()` 回写

### Step 5-8
- **Dedup**: `_event_deduplicate()` 对翻译后列表处理
- **Generate**: `NewsletterGenerator.generate()` → `output/newsletter_*.html`，渲染 `ai_summary`
- **Email**: `EmailSender.send_newsletter()` SMTP
- **Clean**: `clean_old_news(days=7)`

---

## 数据 Schema

### `news` 表
```sql
id INTEGER PK, title TEXT, summary TEXT, link TEXT UNIQUE, source TEXT,
published DATETIME, collected_at DATETIME, content_hash TEXT UNIQUE,
category TEXT,              -- "中文"|"英文"|"财经"
relevance_score INTEGER,    -- 1-10，Step 3 设置
ai_summary TEXT,            -- 中文摘要，Step 3 AI 生成
filter_reason TEXT,         -- Step 3 设置
topic TEXT,                 -- 国际局势|政策监管|财经市场|科技产业|其他
title_original TEXT,        -- 翻译前标题，Step 4 设置
summary_original TEXT,      -- 翻译前摘要，Step 4 设置
translated INTEGER DEFAULT 0  -- 0/1，Step 4 设置
```

### 其他表
- `news_sources` — `id|name|url|enabled|category`
- `filter_rules` — `id|name|type(include/exclude)|value|priority`
- `newsletters` — `id|date|title|content(HTML)|generated_at`
- `event_fingerprints` — `id|event_key|first_seen|last_seen|kept_source|kept_title|kept_link|event_date`

---

## News Dict 字段生命周期

| 字段 | Step1 | Step3 | Step4 | Step6 使用 |
|------|-------|-------|-------|------------|
| `title` | EN 原文 | 不变 | **→ 中文**（翻译后） | 不渲染 |
| `summary` | EN 原文 | 不变 | **→ 中文**（无 ai_summary 时） | 兜底 |
| `ai_summary` | - | **中文**（AI 生成） | 不变 | **主要展示** |
| `category` | "中文"/"英文"/"财经" | - | 翻译过滤键 | - |
| `title_original` | - | - | 保存 EN 标题 | - |
| `summary_original` | - | - | 保存 EN 摘要 | - |
| `translated` | 0 | - | → 1 | - |

关键：`ai_summary` 是 Step 3 生成的中文。简报 [newsletter.py:L107](file:///f:/Project/NewsFlow/src/newsletter/newsletter.py#L107) 渲染 `ai_summary || _generate_simple_summary()`。`title` 字段绝不出现在简报中。

---

## AI Provider 配置

| Provider | `AI_PROVIDER` | Default Base URL | Default Model | batch_size | delay | json_mode |
|----------|--------------|-----------------|---------------|------------|-------|-----------|
| 硅基流动 | `qwen` | `api.siliconflow.cn/v1` | `Qwen/Qwen3-8B` | 10 | 1s | `response_format` |
| Gemini | `gemini` | `generativelanguage.googleapis.com` | `gemini-3.1-flash-lite` | 5 | 5s | prompt instr |
| 智谱 | `zhipu` | `open.bigmodel.cn/api/paas/v4` | `glm-4-flash` | 10 | 3s | `response_format` |
| Groq | `groq` | `api.groq.com/openai/v1` | `llama-3.3-70b-versatile` | 5 | 12s | prompt instr |
| DeepSeek | `deepseek` | `api.deepseek.com` | `deepseek-v4-flash` | 20 | 0.5s | `response_format` |
| OpenAI | `openai` | `api.openai.com/v1` | `gpt-4o-mini` | 15 | 2s | `response_format` |

全部在 `AIClient.__init__()` [filter.py:L80-L131](file:///f:/Project/NewsFlow/src/filter/filter.py#L80-L131)。

---

## 代码位置索引

| 内容 | 文件 | 行号 |
|------|------|------|
| `AIClient` — provider 路由、API 调用、重试 | [filter.py](file:///f:/Project/NewsFlow/src/filter/filter.py) | L77-L255 |
| Qwen3 thinking 关闭 (chat_template_kwargs) | [filter.py](file:///f:/Project/NewsFlow/src/filter/filter.py) | L186-L187 |
| `<think>` 正则清理 | [filter.py](file:///f:/Project/NewsFlow/src/filter/filter.py) | L202-L207 |
| `AIFilter.filter_news()` 入口 | [filter.py](file:///f:/Project/NewsFlow/src/filter/filter.py) | L336-L348 |
| `_two_round_filter()` | [filter.py](file:///f:/Project/NewsFlow/src/filter/filter.py) | L473-L510 |
| `_ai_semantic_filter()` | [filter.py](file:///f:/Project/NewsFlow/src/filter/filter.py) | L789-L811 |
| `_ai_filter_batch()` — AI prompt + 解析 | [filter.py](file:///f:/Project/NewsFlow/src/filter/filter.py) | L837-L904 |
| `AITranslator.translate_news()` 入口 | [filter.py](file:///f:/Project/NewsFlow/src/filter/filter.py) | L1049-L1063 |
| `_translate_batch_text()` 同步 | [filter.py](file:///f:/Project/NewsFlow/src/filter/filter.py) | L1081-L1138 |
| `_translate_single_fallback()` 逐条重试 | [filter.py](file:///f:/Project/NewsFlow/src/filter/filter.py) | L1140-L1178 |
| `_translate_batch_text_async()` | [filter.py](file:///f:/Project/NewsFlow/src/filter/filter.py) | L1180-L1237 |
| `NewsScheduler._daily_task()` 流水线 | [scheduler.py](file:///f:/Project/NewsFlow/src/scheduler/scheduler.py) | L50-L122 |
| `NewsletterGenerator._generate_html()` | [newsletter.py](file:///f:/Project/NewsFlow/src/newsletter/newsletter.py) | L91-L163 |
| 简报兜底 `_generate_simple_summary()` | [newsletter.py](file:///f:/Project/NewsFlow/src/newsletter/newsletter.py) | L72-L89 |
| `NewsStorage` — save/get/update/clean | [storage.py](file:///f:/Project/NewsFlow/src/storage/storage.py) | all |
| `NewsCollector` — RSS+scrape 并行 | [collector.py](file:///f:/Project/NewsFlow/src/collector/collector.py) | all |
| `Settings` — Pydantic 默认值 | [config.py](file:///f:/Project/NewsFlow/src/config/config.py) | L1-L147 |

---

## 已知 Bug 模式

### 1. Translate Silent Skip（已修复 2026-04-29）
- 症状：英文文本遗留在最终简报中
- 根因：`_translate_batch_text()` 按 `\n\n` 分割产出的块数少于条目数，或块为空 → 无日志，静默跳过
- 修复：对所有跳过情况添加 WARNING 日志 + `_translate_single_fallback()` 逐条重试

### 2. Qwen3 Thinking 模式（已修复 2026-04-29）
- 症状：API 响应 30s+，输出含 `<think>` 块，格式混乱
- 根因：裸 `enable_thinking: False` 被硅基流动忽略（非 OpenAI 标准参数）
- 修复：改为 `chat_template_kwargs: {"enable_thinking": False}`（SGLang/vLLM 标准）
- 兜底：`re.sub(r'<think[\s\S]*?</think\s*>', '', content)` [filter.py:L205](file:///f:/Project/NewsFlow/src/filter/filter.py#L205)

### 3. ai_summary ↔ Translation 交互
- Step 3 prompt 要求 `summary` 用**中文** → `ai_summary` 已是中文
- Step 4: 有 `ai_summary` 时只翻译 title；无 `ai_summary` 时翻译 title+summary
- 简报渲染 `ai_summary` 优先；两者都没有时兜底英文 summary 首句

### 4. Filter Truncation Before Translation
- `_ai_semantic_filter()` 返回 `all_results[:max_news]`（默认 20）
- 靠后批次的条目可能在到达翻译步骤前被截断

---

## 去重机制

两层去重：

| 层级 | 位置 | 方式 | 说明 |
|------|------|------|------|
| 采集层 | `collector._deduplicate_news()` | `content_hash` (MD5 of title+url) | 同批次内去重 |
| 存储层 | `storage.save_news()` | 先查 `content_hash`，再靠 `UNIQUE` 约束 | 跨批次去重 |

采集 183 条只保存 26 条是正常行为：157 条 title+url 与 DB 已有记录相同。`save_news()` 返回 `tuple[int, int]` = `(saved_count, skipped_count)`。

---

## CLI 命令

```powershell
python main.py status              # 系统状态
python main.py collect             # 采集新闻 → "新增 X 条, 跳过 Y 条重复"
python main.py run                 # 完整流水线
python main.py filter-cmd          # AI 筛选
python main.py translate           # 翻译
python main.py generate            # 生成简报
python main.py clean --days 7      # 清理旧数据
python main.py list-news           # 查看新闻
python main.py web --port 8000     # 启动 Web 管理后台
```

---

## 当前配置状态

- **AI Provider**: deepseek（DeepSeek 官方 API）
- **AI Model**: deepseek-v4-flash（非思考模式）
- **翻译**: 已启用
- **代理**: `http://127.0.0.1:7897`
- **新闻源**: 10 个（4 中文 scrape + 6 英文 RSS，Bloomberg 禁用）
- **定时**: 每日 6:00

---

## 变更记录

### 2026-04-30
- `fix(filter.py)`: DeepSeek json_mode 返回空 content → 自动回退关闭 json_mode 重试（含 prompt 补充 JSON 格式要求）
- `fix(filter.py)`: `_keyword_filter` 结果 <5 条时放宽条件补充（从已过 exclude 但未匹配 include 的新闻中取 top）
- `note`: Reuters RSS feed (`feeds.reuters.com`) 不可达（TCP 超时 + SSL EOF），Reuters 2020 年已停更 RSS，需考虑关闭该源

### 2026-04-29 (3)
- `migrate`: 从硅基流动 Qwen3-8B 迁移至 DeepSeek V4 Flash 非思考模式
- `feat(filter.py)`: `extra_body = {"thinking": {"type": "disabled"}}` 关闭思考
- `feat(filter.py)`: 空响应自动重试（JSON Output 已知问题兜底）
- `opt(filter.py)`: deepseek 超时 30s、batch_size 20、delay 0.5s
- `fix(filter.py)`: deepseek base_url 去掉了多余的 /v1
- `config`: api_config.env 切换为 deepseek/deepseek-v4-flash

### 2026-04-29 (2)
- `fix(collector.py)`: `_collect_by_rss()` L100 元组解包遗漏（`_fetch_full_content` 返回 tuple 未解包）
- `feat(storage.py)`: `save_news()` 返回值 `int` → `tuple[int, int]`，新增 skipped_count
- `feat(cli/scheduler/web)`: 同步适配 `save_news()` 新返回值，输出含跳过数
- `docs`: 合并 DEVELOPMENT.md → AI_CONTEXT.md，保留 README.md

### 2026-04-29 (更早)
- `fix(filter.py)`: `_translate_batch_text[_async]()` — 解析失败添加 WARNING 日志
- `feat(filter.py)`: 添加 `_translate_single_fallback()` 逐条重试
- `fix(filter.py)`: Qwen3 thinking 关闭参数修正为 `chat_template_kwargs`
- `docs`: 重构 README.md + DEVELOPMENT.md

### 4.1.0
- 添加 Reuters + 半岛电视台 RSS 源
- 简报排序：分类块 → 时间降序
- 每源 `exclude_keywords` RSS 过滤

### 4.0.0
- AI 模型 → Qwen3-8B (硅基流动)
- 重构 filter prompt，话题分类替代语言分类
- 翻译后置到筛选之后
- HTTP 代理支持

---

### 待处理 🟡

3. **海外 RSS 源超时**（BBC/NYT/Reuters）— `api_config.env` 中 `HTTP_PROXY=http://127.0.0.1:7897`。需确认代理端口。

---

## 已修复 ✅

### 2026-05-01
- `fix(setup_autostart.bat)`: 开机自启快捷方式 Argument 引号转义错误
  - **根因**：第37行在 PowerShell 命令中使用 `\"` 嵌入双引号，但 cmd.exe 的转义字符是 `^` 而非 `\`，导致 `\"` 被当作字面 `\` + `"`，Arguments 字符串中路径被插入多余反斜杠，快捷方式启动时 cmd.exe 找不到 `start.bat`
  - **修复**：移除脆弱的 `TargetPath='cmd.exe'` + `Arguments` 间接传递方案，改为直接将 `TargetPath` 指向 start.bat，配合 `WorkingDirectory` 保持工作目录正确，保留 `WindowStyle=7` 最小化运行
  - **影响**：开机后报"找不到.bat"错误的问题消除
  - **后续步骤**：用户需先通过脚本的"Disable"选项移除旧的错误快捷方式，再重新"Enable"

---

## 下一步计划

1. 🔴 用户填写 `api_config.env` 中的 `AI_API_KEY`（https://platform.deepseek.com/api_keys）
2. 🟡 确认代理端口：检查 Clash Verge 是否在 7897 端口运行
3. 运行 `python main.py status` 确认 AI 连接正常
