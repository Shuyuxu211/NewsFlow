# NewsFlow 架构与发布

## 当前架构

NewsFlow 不是两套独立的新闻业务程序，而是一个新闻核心加两个运行适配层：

| 组件 | 实际位置 | 职责 | 版本控制状态 |
| --- | --- | --- | --- |
| NewsFlow 核心 | `F:\Project\NewsFlow` | 采集、筛选、SQLite 存储、简报生成、FastAPI 控制台、本地 Chrome 图片渲染 | 独立 Git 仓库：`Shuyuxu211/NewsFlow` |
| AstrBot 插件适配层 | `F:\AstrBot\data\plugins\astrbot_plugin_newsflow` | 聊天命令、Cron 主动推送、Plugin Page、AstrBot 配置与消息发送 | 独立 Git 仓库，同时是 AstrBot 的插件部署目录 |
| AstrBot 运行时 | Docker 容器 `astrbot` | 加载插件、保存会话/插件配置、提供 WebUI 与消息平台连接 | AstrBot 官方仓库/镜像 |

Docker 将 `F:\Project\NewsFlow` 挂载到容器 `/NewsFlow`。插件通过该挂载导入 `src.*`；本机的 `127.0.0.1:8000` FastAPI 服务通过 `host.docker.internal:8000` 给插件提供 Chrome 图片渲染端点。

因此，运行时仍需要两个进程：AstrBot 容器负责机器人能力，宿主机 NewsFlow 服务负责本机 Chrome 渲染与独立控制台。但新闻业务核心只应维护一份源码。

## 当前边界

- `F:\Project\NewsFlow` 与 `F:\AstrBot\data\plugins\astrbot_plugin_newsflow` 分别受独立 Git 仓库管理。
- 插件目录位于 AstrBot 的 `data/plugins/` 下是官方推荐的加载位置，同时也是插件源码工作树；它不再是 AstrBot 主仓库的未版本化散落文件。
- 不存在“把插件代码复制到核心仓库再同步回部署目录”的流程。核心功能改核心仓库，AstrBot 适配功能改插件仓库；跨边界需求才会有两个有意的、不同职责的提交。
- 插件仍以顶层 `src.*` 与 `bridge.*` 导入。AstrBot 的“重载插件”只清理 `data.plugins.astrbot_plugin_newsflow.*` 模块，不会清除这些顶层模块缓存。

## 已采用的维护方式

采用“核心仓库 + 独立插件仓库”的无重复组件模式：

1. `F:\Project\NewsFlow` 是核心应用的唯一源码仓库。
2. `F:\AstrBot\data\plugins\astrbot_plugin_newsflow` 是插件适配层的唯一源码目录，并初始化为独立 Git 仓库。
3. AstrBot 直接从该目录加载插件，这是官方开发文档推荐的 `data/plugins/<插件名>` 结构；不再创建目录联接或复制第二份插件源码。
4. Docker 继续挂载 `F:\Project\NewsFlow:/NewsFlow`，供插件复用核心业务模块；插件目录由已有 `F:\AstrBot\data:/AstrBot/data` 挂载提供给容器。
5. 当前插件依赖外部 `/NewsFlow` 挂载与宿主机 Chrome 渲染服务，因此只能用于本机配套部署，不能直接作为可独立安装的公开插件发布。

这不是手工同步的两份代码：新闻业务核心只位于 NewsFlow 仓库，AstrBot 适配代码只位于插件仓库。一次需求若只影响核心或插件，只修改对应仓库；跨边界需求会同时修改两个组件，但不存在需要复制粘贴同步的同一文件。

AstrBot 的 GitHub 安装器只能下载整个 GitHub 仓库或一个分支，不能从核心仓库的子目录安装。要发布给其他用户，必须先构建独立运行包：将 NewsFlow 核心模块与本地渲染能力一起包含在插件发行包中，或将核心作为可安装依赖发布。完成前，不应在 `metadata.yaml` 设置公开 `repo`，也不应提交市场。

两个仓库都用于源码与变更历史归档。公开插件仓库仅记录 AstrBot 适配层，不表示该仓库可被单独安装或通过 AstrBot 更新；其 README 必须保留这一限制说明。

## 本地开发与重载

| 改动范围 | 当前操作 | 是否重启整个 AstrBot |
| --- | --- | --- |
| `pages/dashboard/*.html`、`*.css`、`*.js` | 刷新 Plugin Page | 否 |
| 插件的 `main.py`、插件内部模块、`metadata.yaml`、`_conf_schema.json` | WebUI 插件菜单选择「重载插件」 | 否 |
| `requirements.txt` | 确认依赖已安装后重载插件 | 通常否；依赖安装或加载失败时按错误处理 |
| 当前 `F:\Project\NewsFlow\src\*.py` | 重启 AstrBot 容器 | 是，当前顶层模块缓存不会由插件重载清除 |
| `src/web/app.py` | 重启宿主机 NewsFlow Web 服务 | 是，仅重启该服务即可 |

AstrBot 官方文档说明，开发时可在 WebUI 的插件菜单选择「重载插件」，无需重启整个程序。命令行开发模式可使用 `astrbot run --reload` 自动监视插件 Python 文件；现有 Docker 部署没有默认启用该模式。

未来完成源码收敛后，应让核心模块以插件命名空间加载，或在插件重载时显式清理其私有核心模块缓存。完成前，不应把“保存 `src/` 后自动生效”当作已支持能力。

## 归档安全

- 核心仓库不提交 `api_config.env`、`*.env`、数据库、生成的简报、日志、本地任务计划与代理设置。
- 插件仓库不提交 AstrBot 的插件数据、运行时配置、会话 UMO、渲染出的图片、Python 缓存或本地测试文件。
- API 密钥和 SMTP 授权码仅通过本机环境文件或 AstrBot 插件配置保存。提交前必须检查暂存区，而不是只依赖 `.gitignore`。

## GitHub 与插件市场

### 私有/自用分发

不需要 AstrBot 官方审核，但插件必须可以独立运行。

在 AstrBot WebUI 的「插件」页点击 `+`，可通过 URL 或文件上传手动安装。当前安装器接受公开 GitHub 仓库 URL，格式为：

```text
https://github.com/<owner>/<repo>
https://github.com/<owner>/<repo>.git
https://github.com/<owner>/<repo>/tree/<branch>
```

未指定分支时，AstrBot 更新器优先下载最新 GitHub Release；没有可用 Release 时回退下载 `master` 分支。用于正式用户时应发布带语义化版本标签的 GitHub Release，并在 `metadata.yaml` 中维护 `version` 与 `repo` 字段。当前 NewsFlow 插件尚不满足独立运行条件，因此不应设置公开远程仓库地址。

手动 URL 安装的插件不需要官方审核，但用户需要自行信任该仓库。插件更新会删除旧插件目录后解压新包，因此本机开发时不要对目录联接或 Git 工作树使用 WebUI 的“更新/强制更新”功能；开发场景应使用 `git pull` 后执行「重载插件」。

### 官方插件市场

需要经过市场发布流程。官方文档要求先将插件推送到 GitHub 仓库，再进入 `https://plugins.astrbot.app` 点击 `+` 填写信息并选择「提交到 GITHUB」。该操作会跳转到 `AstrBotDevs/AstrBot` 的插件发布 Issue；创建 Issue 后由 AstrBot 维护流程处理。

市场发布包限制为 16 MB。发布前需移除 `.git`、`__pycache__`、`node_modules`、开发配置和其他非运行文件，并确认插件完成测试、不含恶意代码。市场收录与自用 URL 安装是两条独立路径：前者需要发布 Issue 和审核处理，后者不需要。

## 参考依据

- AstrBot WebUI 插件安装与重载：`F:\AstrBot\docs\zh\use\webui.md`
- AstrBot 插件开发与手动重载：`F:\AstrBot\docs\zh\dev\star\plugin-new.md`
- AstrBot 官方市场发布流程：`F:\AstrBot\docs\zh\dev\star\plugin-publish.md`
- GitHub 仓库 URL 规则与 Release 下载顺序：`F:\AstrBot\astrbot\core\zip_updator.py`
- 插件更新会替换整个部署目录：`F:\AstrBot\astrbot\core\star\updator.py`
- 当前 Docker `/NewsFlow` 挂载：`F:\AstrBot\compose.yml`
