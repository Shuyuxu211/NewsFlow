# 每日新闻流系统

多来源 AI 筛选的每日新闻快报系统。从全球多个权威媒体采集新闻，经 AI 智能筛选去重后，按话题分类并翻译为中文，生成简洁的每日简报。

## 功能特点

- **多来源采集**：默认启用国内（新华社、财联社、财经杂志、财新网）和国际（BBC、纽约时报、Financial Times、Reuters、半岛电视台）来源；Reuters 当前使用直接 RSS Feed，不是官方 API 或网页识别；Bloomberg 已配置但默认禁用。财联社通过 RSSHub 电报 Feed 采集，并与其他来源一起进入通用筛选，详见 [`docs/cls-rsshub-integration.md`](docs/cls-rsshub-integration.md)
- **AI 智能筛选**：以财经、宏观、产业和科技为核心，按“日期准入→规则粗筛→AI/关键词评估→统一去重→备用候选→组合选稿”处理，自动排除低信息量内容并评估市场影响与信息增量
- **组合式选稿**：按政策监管、财经市场、科技产业和国际局势控制版面配额，同时限制单一来源与同一长期故事占比
- **自动翻译**：英文新闻标题和实际展示摘要（包括 AI 生成的 `ai_summary`）自动翻译为简体中文，失败自动逐条回退重试
- **Web 后台管理**：可视化配置新闻源、筛选规则、AI 模型、邮件推送
- **定时任务**：每日 6:00 自动执行完整流程
- **简报输出**：生成 HTML 简报，支持邮件推送

## 快速开始

### 1. 环境准备

```powershell
Set-Location C:\path\to\NewsFlow
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

项目当前使用 `requirements.txt` 管理依赖，没有 `pyproject.toml` 或 `uv.lock`，因此不要使用 `uv sync` 作为安装入口。已有 `.venv` 时可跳过创建步骤。

### 2. 配置 AI API

在项目根目录创建 `api_config.env` 文件，填入以下配置：

```env
AI_PROVIDER=deepseek
AI_API_KEY=你的 API 密钥
AI_MODEL=deepseek-v4-flash
AI_TRANSLATE_ENABLED=true
HTTP_PROXY=http://127.0.0.1:7890
CLS_RSS_URL=http://rsshub:1200/cls/telegraph
```

**配置说明：**

| 配置项 | 必填 | 说明 |
|--------|------|------|
| `AI_PROVIDER` | 是 | 推荐并经过生产验证：`deepseek`；其他值仅保留兼容适配 |
| `AI_API_KEY` | 是 | 你的 API Key |
| `AI_API_BASE` | 否 | API Base URL，留空使用默认值 |
| `AI_MODEL` | 否 | 模型名称，留空使用默认模型 |
| `AI_TRANSLATE_ENABLED` | 否 | 翻译功能开关：`true` / `false` |
| `HTTP_PROXY` | 否 | HTTP 代理（用于访问国外 RSS 源），留空不使用代理 |
| `CLS_RSS_URL` | 否 | 财联社 RSSHub Feed；默认值适用于当前 AstrBot Docker 网络，宿主机独立运行时应改为本机可访问且不对公网暴露的地址 |

**AI 兼容性状态：**

| 模式 | `AI_PROVIDER` | 状态 |
|------|---------------|------|
| DeepSeek | `deepseek` | 当前唯一经过连续生产流水线验证的推荐模式，默认模型 `deepseek-v4-flash` |
| OpenAI 兼容端点 | `openai` | 保留通用兼容入口，未做持续回归测试 |
| 硅基流动/Qwen | `qwen` | 实验性适配，可能受思考模式、上下文和速率限制影响 |
| Gemini | `gemini` | 实验性适配，JSON 行为和限流未持续验证 |
| 智谱 | `zhipu` | 实验性适配，内容策略和接口行为未持续验证 |
| Groq | `groq` | 实验性适配，批量大小和速率限制可能不足以完成全量流水线 |

当前筛选提示词、10 条批次、4000 tokens 输出上限、JSON mode、DeepSeek 思考关闭参数及请求节奏均按 DeepSeek 的实际运行结果调校。配置项中存在某个提供商只表示代码保留适配路径，不等于该提供商达到生产支持等级。模型可用性、内容策略、价格和速率限制会变化，切换模型前应完成结构化筛选、翻译、长批次和地缘政治样本的兼容性验证。

### 3. 启动服务

```powershell
# 方式1：双击 start.bat（使用项目虚拟环境启动）
# 方式2：命令行手动激活
.\.venv\Scripts\Activate.ps1
python main.py web --port 8000

# 方式3：不激活虚拟环境直接运行
.\.venv\Scripts\python.exe main.py web --port 8000

# 访问 http://127.0.0.1:8000
```

AstrBot 插件在容器内通过 Playwright 调用 Chromium，将简报渲染为高清 PNG。Playwright 浏览器缓存由 Compose 配置持久化到 `/AstrBot/data/playwright_browsers`；独立 Web 服务的渲染端点仅供宿主机运行模式使用。

> 安全提示：`api_config.env` 仅存放在本机，已被 Git 忽略。不要将 API 密钥、SMTP 授权码、AstrBot 会话配置或数据库提交到 GitHub。

## 命令行操作

| 命令 | 描述 |
|------|------|
| `python main.py status` | 查看系统状态 |
| `python main.py collect` | 立即采集新闻 |
| `python main.py run` | 执行完整每日任务（采集→筛选→翻译→简报→推送） |
| `python main.py filter` | 使用 AI 筛选新闻 |
| `python main.py translate` | 翻译英文新闻 |
| `python main.py generate` | 生成今日简报 |
| `python main.py clean --days 7` | 清理旧新闻 |
| `python main.py list-news` | 查看最近的新闻 |
| `python main.py web --port 8000` | 启动 Web 管理后台 |

完整命令清单以 `python main.py --help` 为准。

## 测试与验证

仓库包含不访问网络或外部服务的结构契约测试：

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
.\.venv\Scripts\python.exe -c "import ast, pathlib; [ast.parse(p.read_text(encoding='utf-8')) for p in [pathlib.Path('main.py'), *pathlib.Path('src').rglob('*.py'), *pathlib.Path('tests').rglob('*.py')]]"
.\.venv\Scripts\python.exe main.py --help
```

新闻源可达性、AI、SMTP、Chrome/Playwright 和 AstrBot 推送属于集成验证，需要对应运行环境与配置。详见 [`docs/pipeline.md`](docs/pipeline.md)。

## 定时任务

启动 Web 服务后，调度器自动在每日 6:00 执行完整流程。关闭终端窗口则停止调度。

如需开机自动启动，运行 `setup_autostart.bat` 并按提示启用。

## AI 筛选规则

### 排除的内容（非新闻）
- 礼节性会见/访问（"某某会见某某"无实质声明）
- 视察调研类（"领导视察某村/某企业"）
- 农事/乡村振兴（"春耕""秋收""县域经济"）
- 城市宣传/旅游推广
- 人物特写/好人好事/劳模表彰
- 革命历史/红色故事
- 纯表态性报道（无具体政策、数据、行动）
- 学校招生/典礼
- 体育/娱乐八卦

### 保留的内容（实质新闻）
- 宏观数据、货币财政政策、贸易与金融监管
- 利率、汇率、股票、债券、商品和金融机构的重要变化
- 公司产能、供应链、并购、业绩、融资和重大管理层变化
- AI、半导体、能源技术、汽车、医药和航天等产业进展
- 具有重大升级或明确能源、航运、制裁、供应链等市场传导的地缘政治

### 评分与版面约束
AI 分别评估市场/产业影响、信息增量、决策相关性、事实具体度、来源可靠性和时效性。普通战况、口头威胁、实时滚动和无新事实的观点文章必须降级。

默认 20 条简报采用以下目标配额：政策监管 5、财经市场 4、科技产业 8、国际局势 3；同一长期故事最多 2 条，单一来源通常最多 4 条，软性最低目标为 16 条。候选池先扩展至最终条数的 3 倍；AI 结构化响应必须覆盖批次全部索引，非法或不完整 JSON 会自动拆半重试，仍失败的条目进入有日志的关键词回退。去重后不足最低目标时，仅从 AI 已评分的非“其他”备用候选中补位，并再次执行事件、链接和标题去重。

DeepSeek 默认每批 10 条，筛选输出上限为 4000 tokens。跨简报去重同时检查稳定 `event_key` 与去除跟踪参数后的规范化 URL；数据库读取的发布时间带本地时区标记，避免外媒时间被重复增加 8 小时。

## 话题分类

| 分类 | 说明 |
|------|------|
| 国际局势 | 地缘冲突、制裁、外交、军事动态 |
| 政策监管 | 政策文件、监管新规、利率调整、贸易政策 |
| 财经市场 | 股市、油价、汇率、IPO、财报 |
| 科技产业 | 芯片、AI、科技突破、电动车、航天 |
| 其他 | 未归入以上分类的新闻 |

## 简报格式

每条新闻以“来源名称 + 主题标签 + 发布时间 + AI 一句话摘要”的形式展示，摘要包含核心事实、具体影响和关键数据，约30-50字。点击摘要可跳转原文。

简报按**时间倒序**排列（最新在前），主题标签用于直接观察版面结构。

## 系统结构

```
src/
├── collector/    # 新闻采集（RSS + 网页抓取）
├── storage/      # SQLite 数据存储
├── filter/       # AI 筛选、去重、分类、翻译
├── newsletter/   # 简报生成（HTML）
├── notifier/     # 邮件推送
├── scheduler/    # 定时任务（APScheduler）
├── web/          # Web 后台（FastAPI）
└── config/       # 配置管理
```

## 架构与维护

NewsFlow 同时提供独立服务和 AstrBot 插件适配，两者复用同一套新闻采集、筛选、存储与简报生成核心。当前的运行目录、推荐的单一源码策略、GitHub 分发方式与热重载边界见 [`docs/architecture.md`](docs/architecture.md)。

## 常见问题

1. **PowerShell 无法激活虚拟环境** — 运行 `Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser` 允许脚本执行，或使用方式3直接运行
2. **英文源采集失败** — 检查源是否启用、RSS URL 是否仍可用，并按本机网络环境配置 `HTTP_PROXY`
3. **AI 返回空结果** — 检查 Provider、Base URL、模型名与账户权限；部分 Provider 的 JSON 输出或思考模式会触发代码中的重试/清理逻辑
4. **简报出现英文** — 翻译队列偶尔会遗漏个别条目，系统已加入逐条回退重试机制，关注日志中的 WARNING 可排查
5. **端口冲突** — `python main.py web --port 8001`
6. **邮件发送失败** — 检查 SMTP 配置和授权码
7. **某来源无内容** — 检查该源 RSS URL 是否有效，可在 Web 后台查看采集日志

## 版本与变更

当前应用版本由 `src/config/config.py` 的 `settings.system_version` 统一提供，FastAPI 元数据也引用该值。仓库尚未建立正式 Release/Tag 与独立 CHANGELOG；历史变更以 Git 提交记录为准，不在 README 复制无法持续校验的版本叙述。

## AstrBot 插件（Docker 部署）

NewsFlow 同时以 **AstrBot 插件** 形态提供，随 AstrBot 的 Docker 容器运行，支持 QQ/Telegram 等平台通过聊天命令获取简报。

### 安装

当前运行中的插件目录为 `<AstrBot部署目录>\data\plugins\astrbot_plugin_newsflow\`。该目录已作为独立插件 Git 仓库初始化，同时也是 AstrBot 官方约定的部署目录。NewsFlow 核心与插件适配层按职责分仓维护，不存在需要复制同步的同一份插件代码。详见 [`docs/architecture.md`](docs/architecture.md)。

### 配置

在 AstrBot WebUI 的"插件配置"中填写以下必填项：

| 配置项 | 必填 | 说明 |
|--------|------|------|
| `ai_api_key` | ✅ | AI API 密钥（DeepSeek 等） |
| `ai_provider` | ❌ | 默认 `deepseek` |
| `http_proxy` | ❌ | 海外 RSS 采集代理 |
| `cron_expression` | ❌ | 默认 `0 6 * * *`（每日 6:00） |
| `target_sessions` | ❌ | Cron 自动推送的目标群/会话 |

`target_sessions` 的会话候选由 AstrBot 的会话历史动态提供。进入插件详情页的「控制台」→「推送」，在目标群或私聊先向机器人发送一条消息，再刷新并多选目标会话后保存。当前部署的 AstrBot 4.26.5 标准插件配置页不提供动态会话选择器，配置页中的该字段保留为手动 UMO 录入入口。

AstrBot Compose 为容器设置 `PLAYWRIGHT_BROWSERS_PATH=/AstrBot/data/playwright_browsers`，让所有采用 Playwright 默认浏览器解析逻辑的插件共享并持久化 Chromium 缓存。

### 命令

在聊天窗口发送：

```
/简报              → 今日简报（容器内 Playwright/Chromium 渲染为高清 PNG）
/简报 2026-05-19   → 指定日期简报（容器内 Playwright/Chromium 渲染为高清 PNG）
/简报 状态          → 系统状态（新闻数、AI 连接等）
/简报 运行          → 手动触发流水线（约 3-5 分钟）
```

### Docker 注意事项

- **新闻采集约 3-5 分钟**：通过 `asyncio.to_thread` 在后台线程执行，不阻塞消息收发
- **容器关闭**：正在执行的采集线程将被操作系统终止；避免在任务执行期间强制关闭容器
- **数据持久化**：`compose.yml` 已将宿主机 `./data` 挂载至容器 `/AstrBot/data`，插件数据存储在 `data/plugin_data/newsflow/`，重建容器不会丢失
- **本地图片渲染**：发送图片或执行定时推送时，插件直接使用容器内 Playwright/Chromium；首次缺少对应浏览器版本时会自动安装到持久化共享目录，不调用宿主机 `127.0.0.1:8000`
- **插件重载**：修改插件 Python、`metadata.yaml` 或 `_conf_schema.json` 后，可在 AstrBot WebUI 的插件菜单执行「重载插件」，无需重启整个 AstrBot。修改 `pages/dashboard/` 下的已有静态资源后刷新页面即可。
- **核心代码变更**：当前插件以 `src.*` 顶层模块导入 `/NewsFlow` 核心代码，AstrBot 的插件重载不会清除这部分模块缓存；修改 `src/` 后仍需要重启 AstrBot，或按 [`docs/architecture.md`](docs/architecture.md) 的目标架构完成模块归属收敛后再消除该限制。

### Git 归档

- 核心应用归档：`https://github.com/Shuyuxu211/NewsFlow`
- AstrBot 适配层归档：独立公开仓库 `astrbot_plugin_newsflow`。它仅用于配套部署和版本留档，依赖 `/NewsFlow` 挂载与 AstrBot 容器内 Playwright/Chromium 运行时，不能单独通过 AstrBot 安装。
- 两个仓库不包含 `api_config.env`、数据库、简报输出、AstrBot 运行数据、API 密钥、SMTP 凭据或本地代理配置。
