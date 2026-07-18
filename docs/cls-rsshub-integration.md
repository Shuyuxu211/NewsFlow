# 财联社 RSSHub 接入

> 状态日期：2026-07-19（Asia/Shanghai）
> 当前状态：NewsFlow 核心接入、容器网络持久化、真实 Feed 读取、重启和生产流水线复测均已完成。

## 结论

财联社不再抓取动态网页 `https://www.cls.cn/telegraph`，改为读取 RSSHub 的财联社电报 Feed。财联社只具有采集协议上的特殊配置，不具有单独的内容筛选规则：成功入库后，它与其他来源一起进入 NewsFlow 的通用日期、规则、AI、去重和组合选稿流程。

## 接口与运行时配置

AstrBot 容器内默认使用：

```text
http://rsshub:1200/cls/telegraph
```

对应配置项为：

```env
CLS_RSS_URL=http://rsshub:1200/cls/telegraph
```

`Settings.cls_rss_url` 会覆盖财联社新闻源中的默认 URL；`NewsCollector`、CLI 状态页和 Web 新闻源页面使用解析后的运行时地址。

当前 RSSHub Compose 只加入 Docker 网络 `astrbot_network`，没有向宿主机发布 1200 端口。因此：

- AstrBot 容器内运行的 NewsFlow 核心可以直接解析 `rsshub`；
- 宿主机独立运行时必须把 `CLS_RSS_URL` 改为宿主机可访问的入口；
- 若发布宿主机端口，应只绑定本机，不得把 RSSHub 暴露到公网。

## 代理边界

财联社源配置使用 `proxy_mode: "bypass"`。采集器为该类内部源创建 `trust_env = False` 的独立 Requests Session，因此不会读取 `HTTP_PROXY`、`HTTPS_PROXY` 等环境代理。其他外部 RSS 和网页源继续使用 NewsFlow 的通用代理配置。

RSS 请求统一由 Requests 显式完成。HTTP 非 200、无法解析且没有条目时会产生明确错误；不再通过 `feedparser.parse(url)` 发起不可观察的隐式网络回退。空 Feed 会记录警告。

## RSS 字段映射

2026-07-19 使用固定 RSSHub 镜像 `ghcr.io/diygod/rsshub:2026-07-18` 实测：

| RSS 字段 | 当前内容 | NewsFlow 映射 |
| --- | --- | --- |
| `title` | 电报标题 | `title` |
| `description` | 完整电报正文 | 清理 HTML 后映射为 `summary` |
| `guid` | 当前与标题相同，`isPermaLink=false` | 稳定身份输入 |
| `pubDate` | RFC 822/HTTP 日期，GMT | 解析为带时区的 `published` |
| `category` | 财联社主题分类 | 暂不改变 NewsFlow 顶层来源分类 |
| `link` | 当前为空 | 生成内部稳定标识 |

当前每次返回 20 条只是上游路由的当前行为，不作为永久契约；NewsFlow 仍使用源级 `max_articles` 独立限制读取数量。

## 空链接与稳定身份

数据库的 `news.link` 为 `UNIQUE NOT NULL`。对于允许空链接的 RSS 源，采集器使用以下内容计算 SHA-256：

1. `guid`，缺失时使用标题；
2. 解析后的带时区发布时间；
3. 规范化空白后的正文。

财联社生成：

```text
urn:newsflow:cls:<sha256>
```

该值同时提供稳定去重身份，但不是财联社原文 URL。HTML 简报和 Web 新闻列表只把 `http://`、`https://` 渲染为可点击链接；`urn:` 仅显示文本。

财联社配置 `fetch_full_content: false`，RSSHub 正文不会因长度不足触发财联社网页抓取。

## 通用筛选语义

财联社不使用来源专属筛选。所有来源共用以下阶段：

1. 24 小时日期准入；
2. 统一排除规则和基础字段粗筛；
3. AI 结构化评分，或未配置 AI 时的关键词评估；
4. 文章级、事件级和历史发布事件去重；
5. 已完成 AI 评分且达到备用阈值的候选补位；
6. 主题目标、国际局势硬上限、单一故事上限和单一来源上限；
7. 来源不足时只小幅放宽来源上限，不放宽故事和国际局势上限。

以下旧补丁已取消：

- AI 保留数量不足时，从粗筛结果无条件补回；
- 关键词结果不足时，从原始新闻无条件补回；
- 财联社、财经杂志、财新网的国内财经源保底。

AI 返回有效排除结论的条目不会因为版面数量不足重新进入。拆分重试后仍无法解析的条目，只有在通过统一粗筛且命中现有包含规则时，才进入显式关键词回退。

## 自动化验证

当前测试覆盖：

- 财联社默认配置为普通 RSS 源；
- 有标题、正文和时间但空 `link` 的条目可以解析；
- 同一条目重复解析得到相同内部身份；
- 同标题但发布时间或正文不同的电报得到不同身份；
- `pubDate` 保留明确时区；
- `max_articles` 生效；
- 财联社不触发网页全文抓取；
- 内部 Feed 绕过环境代理；
- 无效 XML 产生显式失败；
- `urn:` 不被简报渲染成外部链接；
- 财联社与其他来源共用通用筛选和来源上限。

## 容器集成验收

2026-07-19 按运维手册重启时，Docker Desktop/WSL 一度出现 Windows 宿主盘挂载路径异常；执行 `wsl.exe --shutdown` 后容器恢复。强制重建还暴露出 AstrBot Compose 只声明默认网络、未持久加入 `astrbot_network` 的问题，导致容器内无法解析 `rsshub`。现已在 AstrBot 部署目录的 `compose.yml` 中让 `astrbot` 同时加入默认网络和外部 `astrbot_network`，并通过 `docker compose config --quiet` 验证；运行容器与 `rsshub` 也已确认处于同一网络。不得只依赖临时 `docker network connect`，否则下次重建仍会丢失连接。

网络恢复后，通过插件实际使用的 `bridge.pipeline.run_pipeline()` 再执行完整流水线：

- 财联社 Feed 返回 20 条并接受 20 条；
- 全部来源合计采集 137 条；Reuters 直接 Feed 本轮仍因 SSL EOF 失败；
- 新增保存 11 条，筛选发布 8 条，其中财联社 5 条；
- AI 文章去重提出的 11 条低置信度移除均被保护性恢复，实际未误删不同公司的同类新闻；
- 最终 8 条主要受当天前序运行已写入的历史事件记忆约束，不是放宽标准或再次无条件补位；
- 3 条英文新闻完成标题和最终展示摘要翻译；
- 成功生成 `每日新闻简报 - 2026-07-19`，邮件因未配置而跳过。

最终 HTML 复核结果：8 条 `.brief-summary` 均包含中文，不含“早知道”；5 条财联社卡片全部使用 `<span class="brief-summary">`，没有把内部 URN 渲染为可点击链接。

重复采集身份与不重复入库由稳定 URN/content hash 单元测试覆盖；生产数据库中的事件记忆未为复测而清空，避免破坏跨简报去重语义。

本次直接调用核心流水线入口，没有通过聊天命令发送 QQ/Telegram 主动消息。宿主机独立模式在配置可访问的 `CLS_RSS_URL` 前不视为已完成集成验证。

## 既有外部验证记录

2026-07-19 在 NewsFlow 接入前已验证：

- AstrBot 容器访问 RSSHub Feed 返回 HTTP 200；
- RSS 可解析，实测返回 20 条，标题和正文完整；
- AstrBot RSS 插件曾建立 Feed ID `2`、订阅 ID `2`；
- 首轮跳过历史，没有批量推送旧电报；
- 测试期间共保留 6 条成功推送记录；
- 订阅 ID `2` 随后已停用，不再进行 QQ 推送。

AstrBot RSS 插件曾把空链接合成为不存在的财联社地址。NewsFlow 没有沿用该行为，而是使用明确不可点击的内部 URN。
