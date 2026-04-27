# 每日新闻流系统

多来源 AI 筛选的每日新闻快报系统。从全球多个权威媒体采集新闻，经 AI 智能筛选去重后，按话题分类并翻译为中文，生成简洁的每日简报。

## 功能特点

- **多来源采集**：国内（新华社、财联社、财经杂志、财新网）+ 国际（BBC、纽约时报、Financial Times、Bloomberg、Reuters、半岛电视台）
- **AI 智能筛选**：自动识别并排除宣传通稿、礼节性报道等低信息量内容，保留实质性新闻
- **话题分类**：国际局势、政策监管、财经市场、科技产业、其他，按主题组织内容
- **自动翻译**：英文新闻自动翻译为简体中文
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

复制 `api_config.env.example` 为 `api_config.env`：

```powershell
copy api_config.env.example api_config.env
```

编辑 `api_config.env`，填入你的 API Key：

```env
AI_PROVIDER=qwen
AI_API_KEY=你的 API 密钥
AI_MODEL=Qwen/Qwen3-8B
AI_TRANSLATE_ENABLED=true
HTTP_PROXY=http://127.0.0.1:7897
```

**支持的 AI 提供商：**

| 提供商 | AI_PROVIDER | AI_MODEL | 说明 |
|--------|-------------|----------|------|
| 硅基流动 | `qwen` | `Qwen/Qwen3-8B` | 推荐，免费，1000 RPM |
| Google Gemini | `gemini` | `gemini-3.1-flash-lite` | 免费，15 RPM |
| 智谱 AI | `zhipu` | `glm-4-flash` | 按量付费 |
| Groq | `groq` | `llama-3.1-8b-instant` | 免费，有速率限制 |
| DeepSeek | `deepseek` | `deepseek-chat` | 按量付费 |
| OpenAI | `openai` | `gpt-4o-mini` | 按量付费 |

### 3. 启动服务

```powershell
# 方式1：双击 start.bat（自动激活虚拟环境）
# 方式2：命令行
.venv\Scripts\activate.bat
python main.py web --port 8000

# 访问 http://127.0.0.1:8000
```

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

## 常见问题

1. **英文源采集失败** — 配置 `HTTP_PROXY` 使用代理访问 BBC/NYT/Financial Times/Bloomberg/Reuters/半岛电视台 RSS
2. **AI 返回空结果** — Qwen3-8B 可能触发思考模式导致超时，确认 `enable_thinking: False` 已生效
3. **简报格式不对** — 重启 Web 服务后刷新页面
4. **端口冲突** — `python main.py web --port 8001`
5. **邮件发送失败** — 检查 SMTP 配置和授权码
6. **某来源无内容** — 检查该源 RSS URL 是否有效，可在 Web 后台查看采集日志

## 版本历史

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
