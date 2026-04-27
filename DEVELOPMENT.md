# 开发文档

## 项目概述

每日新闻流系统是一个多来源的 AI 筛选新闻自动化系统。系统每日自动从全球多个权威媒体采集新闻，通过 AI 模型进行智能筛选、去重、分类和翻译，最终生成结构化的每日新闻简报。

## 系统架构

```
┌──────────────────────────────────────────────────────────────────────┐
│                           系统架构图                                   │
├──────────────────────────────────────────────────────────────────────┤
│  ┌─────────────┐    ┌──────────────┐    ┌────────────────────────┐  │
│  │   定时调度   │───▶│  新闻采集器   │───▶│    内容存储层           │  │
│  │(APScheduler)│    │(RSS+爬虫并行) │    │     (SQLite)          │  │
│  └─────────────┘    └──────────────┘    └────────────────────────┘  │
│                                                     │                │
│                                                     ▼                │
│  ┌─────────────┐    ┌──────────────┐    ┌────────────────────────┐  │
│  │  邮件推送    │◀───│  简报生成器   │◀───│  AI 筛选 + AI 翻译     │  │
│  │  (SMTP)     │    │  (HTML)      │    │(Qwen/Gemini/Zhipu/Groq)│  │
│  └─────────────┘    └──────────────┘    └────────────────────────┘  │
│                             ▲                                        │
│                             │                                        │
│  ┌────────────────────────────────────────────────────────────────┐  │
│  │                    管理后台 (FastAPI Web UI)                    │  │
│  │  ┌──────┐ ┌──────┐ ┌──────┐ ┌──────┐ ┌──────┐ ┌──────┐      │  │
│  │  │ 概览  │ │新闻流│ │历史  │ │规则  │ │AI配置│ │邮件  │      │  │
│  │  └──────┘ └──────┘ └──────┘ └──────┘ └──────┘ └──────┘      │  │
│  └────────────────────────────────────────────────────────────────┘  │
└──────────────────────────────────────────────────────────────────────┘
```

## 当前实现状态

### 已实现功能

| 模块 | 状态 | 说明 |
|------|------|------|
| 新闻采集 | ✅ 完成 | RSS 解析 + 网页爬虫，支持 10 个新闻源，并行采集 |
| 数据存储 | ✅ 完成 | SQLite 数据库，新闻、规则、任务状态管理 |
| 定时调度 | ✅ 完成 | APScheduler，每日 6:00 自动执行 |
| AI 筛选 | ✅ 完成 | 支持 Qwen、Gemini、Zhipu、Groq、OpenAI、DeepSeek |
| AI 翻译 | ✅ 完成 | 英文新闻自动翻译为简体中文 |
| 去重 | ✅ 完成 | 基于标题相似度的去重机制 |
| 话题分类 | ✅ 完成 | 国际局势、政策监管、财经市场、科技产业、其他 |
| 简报生成 | ✅ 完成 | HTML 格式简报，按时间倒序排列 |
| 邮件推送 | ✅ 完成 | SMTP 邮件发送，支持自定义收件人 |
| Web 后台 | ✅ 完成 | FastAPI + 原生 HTML/CSS/JS，可视化配置 |
| 命令行 | ✅ 完成 | 支持手动执行各模块功能 |
| 开机自启 | ✅ 完成 | Windows 计划任务自动启动 |

### 未实现/规划中功能

| 模块 | 状态 | 说明 |
|------|------|------|
| PDF 简报生成 | ❌ 未实现 | 原计划使用 WeasyPrint，当前仅支持 HTML |
| 多用户系统 | ❌ 未实现 | 当前为单用户本地部署 |
| 容器化部署 | ❌ 未实现 | 支持本地部署，Docker 化待开发 |
| Vue3 前端 | ❌ 未实现 | 当前使用原生 HTML，第二版计划升级 |
| QQ 群推送 | ❌ 未实现 | 原计划支持，当前仅支持邮件推送 |

## 技术栈

| 组件 | 方案 | 版本 |
|------|------|------|
| 编程语言 | Python | 3.12+ |
| 后端框架 | FastAPI + Uvicorn | - |
| 任务调度 | APScheduler | - |
| 数据库 | SQLite | - |
| AI 模型 | 多提供商支持 | Qwen3-8B (推荐) |
| 新闻采集 | feedparser + BeautifulSoup | - |
| 前端 UI | 原生 HTML/CSS/JS | - |
| 邮件推送 | SMTP (smtplib) | - |
| 依赖管理 | uv | - |

## 数据源配置

### 国内中文源（网页爬虫）
- 新华社
- 财联社
- 财经杂志
- 财新网

### 国际外文源（RSS）
- BBC
- 纽约时报 (NYT)
- Financial Times
- Bloomberg
- Reuters
- 半岛电视台 (Al Jazeera)

> 注意：外文源需要配置 HTTP 代理才能正常访问。

## 详细工作流

### 阶段一：新闻采集（每日 6:00 触发）

1. 定时任务启动（APScheduler）
2. 并行采集各来源新闻（ThreadPoolExecutor, 4 workers）
   - 中文源：新华社、财联社、财经杂志、财新网（网页爬虫）
   - 外文源：BBC、NYT、Financial Times、Bloomberg、Reuters、半岛电视台（RSS）
3. 内容预处理
   - 去重（基于标题+URL哈希）
   - 关键词过滤（RSS 源独立 exclude_keywords 配置）
   - 元数据提取（发布时间、来源、链接）
4. 存储到 SQLite 数据库

### 阶段二：AI 筛选（6:05 执行）

1. 加载用户配置的筛选规则
2. 日期过滤（默认 36 小时内的新闻）
3. 粗筛（关键词排除）
4. AI 精筛
   - 批量调用 AI API
   - 输入：新闻标题 + 摘要
   - 输出：评分（1-10）+ 一句话摘要
   - 限制：仅返回筛选结果，不修改原文
5. 去重（标题相似度）
6. 话题分类（国际局势/政策监管/财经市场/科技产业/其他）

### 阶段三：翻译与简报（6:15 执行）

1. AI 翻译（如开启）
   - 翻译标题和摘要为简体中文
   - 保留原文数据
2. 生成 HTML 简报
   - 按时间倒序排列（最新在前）
   - 每条新闻：来源 + 发布时间 + AI 摘要
   - 点击摘要可跳转原文
3. 保存简报到 output 目录

### 阶段四：推送与清理（6:20 执行）

1. 邮件推送（如配置 SMTP）
2. 清理旧新闻（根据配置的保留天数）

## 数据结构

### news 表

| 字段 | 类型 | 说明 |
|------|------|------|
| id | INTEGER | 主键 |
| title | TEXT | 新闻标题 |
| summary | TEXT | 新闻摘要 |
| link | TEXT | 原文链接 |
| source | TEXT | 新闻来源 |
| published | DATETIME | 发布时间 |
| collected_at | DATETIME | 采集时间 |
| category | TEXT | 话题分类 |
| ai_score | INTEGER | AI 评分（1-10） |
| ai_summary | TEXT | AI 生成摘要 |
| title_original | TEXT | 原始标题（翻译前） |
| summary_original | TEXT | 原始摘要（翻译前） |

### filter_rules 表

| 字段 | 类型 | 说明 |
|------|------|------|
| id | INTEGER | 主键 |
| name | TEXT | 规则名称 |
| type | TEXT | 规则类型（include/exclude） |
| value | TEXT | 规则值 |
| priority | INTEGER | 优先级 |

### newsletters 表

| 字段 | 类型 | 说明 |
|------|------|------|
| id | INTEGER | 主键 |
| date | DATE | 简报日期 |
| title | TEXT | 简报标题 |
| content | TEXT | 简报内容（HTML） |
| generated_at | DATETIME | 生成时间 |

## 目录结构

```
news/
├── src/
│   ├── cli/           # 命令行界面
│   │   └── cli.py
│   ├── collector/     # 新闻采集（RSS + 网页抓取）
│   │   └── collector.py
│   ├── config/        # 配置管理
│   │   └── config.py
│   ├── filter/        # AI 筛选、去重、分类、翻译
│   │   ├── __init__.py
│   │   └── filter.py
│   ├── newsletter/    # 简报生成（HTML）
│   │   ├── __init__.py
│   │   └── newsletter.py
│   ├── notifier/      # 邮件推送
│   │   ├── __init__.py
│   │   └── notifier.py
│   ├── scheduler/     # 定时任务（APScheduler）
│   │   └── scheduler.py
│   ├── storage/       # 数据存储（SQLite）
│   │   └── storage.py
│   └── web/           # Web 后台（FastAPI）
│       ├── static/
│       │   └── index.html
│       ├── __init__.py
│       └── app.py
├── data/              # 数据库文件（git 忽略）
│   └── news.db
├── output/            # 简报输出（git 忽略）
│   └── newsletter_*.html
├── .venv/             # 虚拟环境（git 忽略）
├── api_config.env     # AI 配置（git 忽略）
├── api_config.env.example  # 配置模板
├── main.py            # 入口文件
├── requirements.txt   # 依赖列表
├── start.bat          # 启动脚本
├── setup_autostart.bat  # 开机自启脚本
├── .gitignore         # Git 忽略规则
├── README.md          # 使用文档
└── DEVELOPMENT.md     # 开发文档（本文档）
```

## AI 筛选规则

### 排除的内容（评分 1-3）
- 礼节性会见/访问（"某某会见某某"无实质声明）
- 视察调研类（"领导视察某村/某企业"）
- 农事/乡村振兴（"春耕""秋收""县域经济"）
- 城市宣传/旅游推广
- 人物特写/好人好事/劳模表彰
- 革命历史/红色故事
- 纯表态性报道（无具体政策、数据、行动）
- 学校招生/典礼
- 体育/娱乐八卦

### 保留的内容（评分 4-10）
- 具体数据/政策/法规
- 冲突/战争/制裁进展
- 国际关系实质性变化
- 重大经济数据/市场变化
- 科技突破/公司重大事件
- 严肃外媒的地缘政治/经济报道

## 开发指南

### 环境搭建

```powershell
# 1. 克隆仓库
git clone <repository-url>
cd NewsFlow

# 2. 安装依赖
pip install uv
uv sync

# 3. 配置环境变量
copy api_config.env.example api_config.env
# 编辑 api_config.env 填入 API Key

# 4. 启动服务
python main.py web --port 8000
```

### 常用命令

| 命令 | 说明 |
|------|------|
| `python main.py collect` | 测试新闻采集 |
| `python main.py filter` | 测试 AI 筛选 |
| `python main.py run` | 测试完整流程 |
| `python main.py web` | 启动 Web 服务 |

### 扩展新闻源

在 `src/collector/collector.py` 中添加新的采集器：
- RSS 源：添加 RSS URL 到外文源列表
- 网页爬虫：实现新的爬取函数，返回标准化的新闻数据格式

### 添加 AI 提供商

在 `src/filter/filter.py` 的 AI 客户端配置中添加新的提供商：
- 设置 API Base URL
- 配置默认模型
- 添加对应的提示词模板
