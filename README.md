# 每日新闻流系统

多来源 AI 筛选的每日新闻快报系统。从全球多个权威媒体采集新闻，经 AI 智能筛选去重后，按话题分类并翻译为中文，生成简洁的每日简报。

## 功能特点

- **多来源采集**：国内（新华社、财联社、财经杂志、财新网）+ 国际（BBC、纽约时报、Financial Times、Bloomberg、Reuters、半岛电视台）
- **AI 智能筛选**：自动识别并排除宣传通稿、礼节性报道等低信息量内容，保留实质性新闻
- **话题分类**：国际局势、政策监管、财经市场、科技产业、其他，按主题组织内容
- **自动翻译**：英文新闻自动翻译为简体中文，翻译失败自动逐条回退重试
- **Web 后台管理**：可视化配置新闻源、筛选规则、AI 模型、邮件推送
- **定时任务**：每日 6:00 自动执行完整流程
- **简报输出**：生成 HTML 简报，支持邮件推送

## 快速开始

### 1. 环境准备

```powershell
cd NewsFlow
pip install uv
uv sync
```

### 2. 配置 AI API

在项目根目录创建 `api_config.env` 文件，填入以下配置：

```env
AI_PROVIDER=qwen
AI_API_KEY=你的 API 密钥
AI_MODEL=Qwen/Qwen3-8B
AI_TRANSLATE_ENABLED=true
HTTP_PROXY=http://127.0.0.1:7890
```

**配置说明：**

| 配置项 | 必填 | 说明 |
|--------|------|------|
| `AI_PROVIDER` | 是 | AI 提供商：`qwen` / `gemini` / `zhipu` / `groq` / `openai` / `deepseek` |
| `AI_API_KEY` | 是 | 你的 API Key |
| `AI_API_BASE` | 否 | API Base URL，留空使用默认值 |
| `AI_MODEL` | 否 | 模型名称，留空使用默认模型 |
| `AI_TRANSLATE_ENABLED` | 否 | 翻译功能开关：`true` / `false` |
| `HTTP_PROXY` | 否 | HTTP 代理（用于访问国外 RSS 源），留空不使用代理 |

**支持的 AI 提供商：**

| 提供商 | AI_PROVIDER | AI_MODEL | 说明 |
|--------|-------------|----------|------|
| 硅基流动 | `qwen` | `Qwen/Qwen3-8B` | 推荐，免费，1000 RPM |
| Google Gemini | `gemini` | `gemini-3.1-flash-lite` | 免费，15 RPM |
| 智谱 AI | `zhipu` | `glm-4-flash` | 按量付费 |
| Groq | `groq` | `llama-3.3-70b-versatile` | 免费，有速率限制 |
| DeepSeek | `deepseek` | `deepseek-chat` | 按量付费 |
| OpenAI | `openai` | `gpt-4o-mini` | 按量付费 |

### 3. 启动服务

```powershell
# 方式1：双击 start.bat（自动激活虚拟环境并启动）
# 方式2：命令行手动激活
.\.venv\Scripts\Activate.ps1
python main.py web --port 8000

# 方式3：不激活虚拟环境直接运行
.\.venv\Scripts\python.exe main.py web --port 8000

# 访问 http://127.0.0.1:8000
```

启动 Web 服务后，AstrBot 插件会通过 `http://host.docker.internal:8000/api/render/newsletter`
调用本机 Chrome，将简报稳定渲染为高清 PNG。该服务只监听本机回环地址，不对局域网开放。

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

## 定时任务

启动 Web 服务后，调度器自动在每日 6:00 执行完整流程。关闭终端窗口则停止调度。

如需开机自动启动，以管理员身份运行 `setup_autostart.bat`。

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
- 具体数据/政策/法规
- 冲突/战争/制裁进展
- 国际关系实质性变化
- 重大经济数据/市场变化
- 科技突破/公司重大事件
- 严肃外媒的地缘政治/经济报道

### 评分标准
| 分数 | 级别 | 示例 |
|------|------|------|
| 10 | 重大事件 | 战争、制裁、央行大幅降息/加息 |
| 8-9 | 重要 | 重大政策发布、地缘风险升级、科技突破 |
| 6-7 | 中等 | 有信号意义的政策动向、行业趋势变化 |
| 4-5 | 一般 | 信息增量有限但有参考价值 |
| 1-3 | 排除 | 上述非新闻类内容 |

## 话题分类

| 分类 | 说明 |
|------|------|
| 国际局势 | 地缘冲突、制裁、外交、军事动态 |
| 政策监管 | 政策文件、监管新规、利率调整、贸易政策 |
| 财经市场 | 股市、油价、汇率、IPO、财报 |
| 科技产业 | 芯片、AI、科技突破、电动车、航天 |
| 其他 | 未归入以上分类的新闻 |

## 简报格式

每条新闻以"来源名称 + 发布时间 + AI 一句话摘要"的形式展示，摘要包含核心事实、具体影响和关键数据，约30-50字。点击摘要可跳转原文。

简报按**时间倒序**排列（最新在前），分类信息保留在后台不展示。

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
2. **英文源采集失败** — 配置 `HTTP_PROXY` 使用代理访问 BBC/NYT/Financial Times/Bloomberg/Reuters/半岛电视台 RSS
3. **AI 返回空结果** — Qwen3-8B 可能触发思考模式导致超时，系统已自动禁用思考模式并清除 `<think>` 标签
4. **简报出现英文** — 翻译队列偶尔会遗漏个别条目，系统已加入逐条回退重试机制，关注日志中的 WARNING 可排查
5. **端口冲突** — `python main.py web --port 8001`
6. **邮件发送失败** — 检查 SMTP 配置和授权码
7. **某来源无内容** — 检查该源 RSS URL 是否有效，可在 Web 后台查看采集日志

## 版本历史

### 4.2.0 (2026-04-29)
- **修复**：翻译批次解析失败时自动逐条回退重试，避免英文残留
- **修复**：Qwen3 思考模式禁用方式修正为官方 `chat_template_kwargs` 格式
- **优化**：翻译解析失败新增 WARNING 日志，方便排查

### 4.1.0
- 新增 Reuters 和半岛电视台 RSS 源
- 简报排序方式由分类区块改为时间倒序（最新在前）
- 分类信息保留在后台，不再前台展示
- RSS 源支持独立 exclude_keywords 配置，在采集阶段过滤体育/娱乐内容

### 4.0.0
- 切换 AI 模型至 Qwen3-8B（硅基流动）
- 重构筛选 prompt，排除宣传通稿类内容
- 话题分类替代语言分类（国际局势/政策监管/财经市场/科技产业）
- 中英新闻统一评估，最后翻译
- 简报格式改为来源+时间+AI摘要的消息流风格
- 新增 HTTP 代理支持
- 新增 start.bat / setup_autostart.bat

## AstrBot 插件（Docker 部署）

NewsFlow 同时以 **AstrBot 插件** 形态提供，随 AstrBot 的 Docker 容器运行，支持 QQ/Telegram 等平台通过聊天命令获取简报。

### 安装

当前运行中的插件目录为 `F:\AstrBot\data\plugins\astrbot_plugin_newsflow\`。该目录已作为独立插件 Git 仓库初始化，同时也是 AstrBot 官方约定的部署目录。NewsFlow 核心与插件适配层按职责分仓维护，不存在需要复制同步的同一份插件代码。详见 [`docs/architecture.md`](docs/architecture.md)。

### 配置

在 AstrBot WebUI 的"插件配置"中填写以下必填项：

| 配置项 | 必填 | 说明 |
|--------|------|------|
| `ai_api_key` | ✅ | AI API 密钥（DeepSeek 等） |
| `ai_provider` | ❌ | 默认 `deepseek` |
| `http_proxy` | ❌ | 海外 RSS 采集代理 |
| `cron_expression` | ❌ | 默认 `0 6 * * *`（每日 6:00） |
| `target_sessions` | ❌ | Cron 自动推送的目标群/会话 |
| `render_service_url` | ❌ | 本地高清图片渲染服务，Docker 默认 `http://host.docker.internal:8000/api/render/newsletter` |

`target_sessions` 的会话候选由 AstrBot 的会话历史动态提供。进入插件详情页的「控制台」→「推送」，在目标群或私聊先向机器人发送一条消息，再刷新并多选目标会话后保存。AstrBot 4.24.5 的标准插件配置页不提供动态会话选择器，配置页中的该字段保留为手动 UMO 录入入口。

### 命令

在聊天窗口发送：

```
/简报              → 今日简报（本机 Chrome 渲染为高清 PNG）
/简报 2026-05-19   → 指定日期简报（本机 Chrome 渲染为高清 PNG）
/简报 状态          → 系统状态（新闻数、AI 连接等）
/简报 运行          → 手动触发流水线（约 3-5 分钟）
```

### Docker 注意事项

- **新闻采集约 3-5 分钟**：通过 `asyncio.to_thread` 在后台线程执行，不阻塞消息收发
- **容器关闭**：正在执行的采集线程将被操作系统终止，SQLite 的 WAL 模式保证数据不会损坏
- **数据持久化**：`compose.yml` 已将宿主机 `./data` 挂载至容器 `/AstrBot/data`，插件数据存储在 `data/plugin_data/newsflow/`，重建容器不会丢失
- **本地渲染服务**：发送图片或执行定时推送前，需保持 NewsFlow Web 服务在宿主机 `127.0.0.1:8000` 运行；插件不再调用 AstrBot 的远程 HTML 转图片服务
- **插件重载**：修改插件 Python、`metadata.yaml` 或 `_conf_schema.json` 后，可在 AstrBot WebUI 的插件菜单执行「重载插件」，无需重启整个 AstrBot。修改 `pages/dashboard/` 下的已有静态资源后刷新页面即可。
- **核心代码变更**：当前插件以 `src.*` 顶层模块导入 `/NewsFlow` 核心代码，AstrBot 的插件重载不会清除这部分模块缓存；修改 `src/` 后仍需要重启 AstrBot，或按 [`docs/architecture.md`](docs/architecture.md) 的目标架构完成模块归属收敛后再消除该限制。

### Git 归档

- 核心应用归档：`https://github.com/Shuyuxu211/NewsFlow`
- AstrBot 适配层归档：独立公开仓库 `astrbot_plugin_newsflow`。它仅用于配套部署和版本留档，依赖本机 `/NewsFlow` 挂载与 Chrome 渲染服务，不能单独通过 AstrBot 安装。
- 两个仓库不包含 `api_config.env`、数据库、简报输出、AstrBot 运行数据、API 密钥、SMTP 凭据或本地代理配置。
