# 知识图谱 × 官方参考文档 对齐记录

对照来源：<https://deepseek-harness.github.io/deepseek-harness/reference/>（架构总览）、
`/reference/capability-seams`、`/reference/tool-execution-pipeline`、`/reference/agent-lifecycle`、
`/reference/subsystems/{core,session,system-prompt,tools,llm-streaming,scope,subagent}`。
对齐时间：2026-11-26。

## 一、修正（原文与文档冲突）

| # | 位置 | 原文表述 | 官方表述 / 修正后 |
|---|---|---|---|
| 1 | 分层 `会话、上下文与压缩层` | 「Session 事件持久化（JSONL/SQLite）」 | 持久化只有 JSONL（`session-persistence-jsonl`）；SQLite 是 `session-query` 的查询索引 Provider（`ctx.sessionQuery`），不是持久化载体 |
| 2 | 分层 `产品入口与配置档层` | 只列 web-app / headless / sdk / acp 四个 bundle | 组合包共 6 个：`dsh-base`（web/headless/sdk/acp 的共享第一层）、`dsh-web-app`、`dsh-headless`、`dsh-sdk-app`、`dsh-acp-app`、`dsh-sdk-minimal`（刻意不应用 base） |
| 3 | 导览第 12 步 | 「同一份 CLI 能承载 web、headless、sdk、acp 多个 profile」 | 随发行版交付 5 个 profile：`web`、`headless`、`sdk`、`sdk-minimal`、`acp`；`plugin` 是管理子命令，同名 profile 必须 `--profile plugin` |
| 4 | 分层 `核心运行时` / 第 3 步 | 把 `core/scope` 当作与其他核心包同级的服务 | `core/scope` 是零依赖注册原语库，**官方核心包表中它不提供 ctx 键**；5 个核心 ctx 键为 `ctx.sessions`、`ctx.systemPrompt`、`ctx.tools`、`ctx.agents`、`ctx.agentLoop` |
| 5 | 分层 `宿主装载与插件生态` | 「profile/bundle/patch 层叠」但未给顺序 | 按序应用：profile 中有序组合包 → 其 `cordis.patch.yml` → home patch → `--patch` overlay；一条 patch 按 id 定位条目并替换整个 config；二者在 `package.json` 的 `dsh.profile` / `dsh.bundle` 声明 |
| 6 | 导览第 1 步 | 第三个节点为 `SAFETY.md`，讲解却在讲 `pnpm-workspace.yaml` | 节点换为 `pnpm-workspace.yaml`，三份文件（AGENTS.md / package.json / pnpm-workspace.yaml）与讲解一致 |

## 二、补充（文档有、图谱缺）

1. **步骤与轮次的正式定义**（第 4 步）：step = 一次模型请求 + 其工具调用；turn = 0..n 个 step，领取首条输入前开启、不再欠工作时关闭；并补入 `turn/start → agent/pre-step → step/start → agent/request → llm/stream → tool/* → step/end → agent/turn-stopping → turn/end` 事件序列。
2. **工具流水线的守卫顺序**（第 6 步）：`tools/pre-execute` → 单调守卫（不可重排序的所有者策略）→ `tools/execute` → `tools/post-execute`；`projectContent` 在后置策略之前、`finalizeContent` 与 `tools/result` 在之后；`ctx.approval` 在单调守卫之前处理询问。
3. **Session 日志的 settlement 语义**（第 5 步）：`assistant/message` 内嵌精确紧凑带时间 stream；无 surface message 的失败/重试/取消记为 `assistant/attempt` 且不进入模型历史；v0 `session.jsonl`、v1+ `session.vN.jsonl`，相邻迁移包各负责一步。
4. **seam 三角与规模**（第 8 步、能力 seam 层）：Service Definition / Provider / Consumer 三角，官方共 35 个 seam；文件系统与进程 Provider 共享同一执行世界，换 Provider 即整体迁移 Bash/PTY/LSP。
5. **子代理 Provider 家族**（第 10 步）：spawn-in-process、fork-in-process、acp、codex、claude-code、dsh-sdk。
6. **Python 运行时形态**（第 13 步）：wheel 将 dsh CLI 打成 `deepseek-harness-sdk-runtime-<platform>-<arch>`，默认 `dsh --profile sdk`；Python 只暴露 profile 与有序 patch 文件，不暴露完整 Cordis 树。
7. **新增第 15 步「扩展点归属：新行为加在哪里」**：把官方「新行为的归属位置」表压缩成可执行判断（ctx.llm / ctx.tools / ctx.shell / ctx.terminals / ctx.commands / ctx.jobs / ctx.fs / ctx.sandbox / agent.* / SessionEventMap），并点明事件三域（会话事件、Agent 事件、能力事件）。
8. **每层 / 每步的官方文档入口**：10 个分层 + 15 个导览步骤均加 `doc` 链接；界面在讲解卡片底部提供「官方文档 · <小节> ↗」按钮，分层图例行尾提供 `↗`。
9. **范围声明**：`project.scope` 明确「UI 层（packages/client、apps/web、apps/desktop）不在图谱内」，避免把官方文档中的 Desktop 应用与 Web Client 误认为漏采。

## 三、全量补齐（第二轮：不设刻意范围）

按用户要求，将 reference 站点全部页面无保留入图，原先"刻意保留"的三项已全部取消：

| 项目 | 此前 | 现在 |
|---|---|---|
| `config-catalog` 生成式配置目录 | 不收录逐字段 | 181 个 config-schema + 867 个 config-field 节点，逐字段摘要、默认值、类型、来源包路径均可检索 |
| `experimental-*` seam | 排除目录，未进图 | `ctx.forge`、`ctx.forgeSession`、`ctx.worktrees`、`ctx.browserUse`、`ctx.computerUse`、`ctx.speechController` 等已入图；experimental 页 18 条 `plugin:*` 记录一并收录 |
| 持久化类型逐项 | 仅页面级说明 | 413 个 ptype 节点（SHA-256 + 属性表摘要），与事件节点建立 `references` 关系 109 条 |

新增数据来源：`website/docs.ts` 的 reference 路由表（69 个页面）+ `docs/*.zh.md` 正文解析。

## 四、本轮成果

- 图谱规模：**9,350 实体 / 15,153 关系**（原 6,841 / 10,585），新增 11 个实体类型。
- reference 文档层（独立一簇岛）：69 个页面节点 + 598 个 doc-section + 413 ptype + 155 service + 132 event + 76 tool + 181 config-schema + 867 config-field + 18 record，共 **2,509 节点**，占全部图层的 1 层。
- 新增导览第 16 步「官方参考文档层：文档拆成可连接的实体」；16 步导览与 11 层节点在画布中 100% 可定位。
- 所有文档实体（ptype / service / event / tool / config-schema / config-field / record / doc-section）**100% 携带官方文档链接**，详情页提供「官方文档 ↗」入口。
- 站点 404 的 1 个页面（`cookbook/contributing-system-messages`）改指向 GitHub 源码，链接可达性实测 69/69 全部 200 或 301。
- 统计口径：侧栏显示图谱全量 9,350 / 15,153，并注明画布渲染 4,799 个文件级节点（class/function 细粒度节点不入画布，避免视觉密度爆炸）；全量实体仍可通过图谱 JSON 检索。
- 布局：代码岛与文档岛分离，文档岛缩放 0.66 并降低不透明度，簇标签带避让与阈值，默认视图不被文档层挤压。

## 五、官方文档本地化与悬浮展开（第三轮）

按用户要求「Download 官方文档到本地，链接跳转改为悬浮展开文档内容」：

- **本地化**：`.ua/build_doc_payload.py` 将 69 页 reference 文档（`docs/<stem>.zh.md`，缺失时回退英文 `.md`）复制到 `.ua/docs-local/`，并生成 `.ua/doc-payload.json`（route → 标题 / 分组 / 正文 / 本地路径 / 原网页 URL），共 2.05 MB。
- **悬浮展开**：面板内所有官方入口（导览讲解卡片、分层图例、节点详情面板）由点击跳转改为 hover 展开 `.docpop` 卡片——展示分组、标题、Markdown 渲染正文（标题 / 列表 / 表格 / 代码块 / 加粗 / 链接）、底部本地文件路径；卡片内保留「原网页 ↗」次级链接，点击入口仍可新标签打开。正文超 60k 字符时截断并提示查看本地全文。
- **离线自足**：文档正文随 payload 内联进单文件 HTML（2.87 → 4.93 MB），悬浮无需联网；本地副本保留在 `.ua/docs-local/` 便于直接查阅。
- **覆盖校验**：937 个唯一文档 URL 全部可映射到 payload，0 失效；3 个入口均挂 `data-doc` 事件委托。

## 六、文档内源码链接修复（第四轮）

问题：文档正文里的「来源：`packages/.../index.ts:41`」链接原为相对路径 `../packages/...`，在离线面板中按相对目录解析，点开为空文件。

- 用户选定方案：跳转 GitHub 在线源码。
- `.ua/build_doc_payload.py` 新增 `rewrite_links()` / `gh_url()`：把 Markdown 内联链接与尖括号链接按源文件位置解析为 `https://github.com/deepseek-ai/deepseek-harness/blob/master/<path>`，并从链接文本末尾 `:N` 提取行号拼成 `#L41`；文档间相对链接同样改为 GitHub blob URL；页内 `#` 锚点保持原样。
- 本地副本 `.ua/docs-local/*.md` 同步改写，payload 与面板（5.07 MB）均使用改写后的正文。
- 结果：2,456 个 GitHub 链接，其中 589 个带精确行号锚点；0 个失效的 `../packages` 相对链接。实测 `packages/interaction/user-approval/src/index.ts:41` → `.../index.ts#L41`，锚点指向 `approval/policy` 定义处，与文档描述一致。
- 残留 5 个 `../../../../.agents/notes/...` 链接未改写：上游文档层级写多（从 `docs/subsystems/` 到仓库根只需 `../../`），在官网亦为失效链接，属上游问题。

## 七、网站上线（kg.agidsh.com）

按用户要求完成 DSH 知识图谱网站设计建设并部署上线。

- **域名**：`https://kg.agidsh.com`（DNS 已解析至 43.163.199.12；证书由用户提供，`kg.agidsh.com_nginx.zip`，SAN=kg.agidsh.com，有效期至 2027-02-25）。
- **服务器**：Windows Server 2022 + Nginx，站点目录 `C:\wwwroot\kg`，证书 `C:\nginx\conf\certs\kg\`，Nginx 配置备份在 `C:\backup\nginx-conf-*.bak`。
- **网站结构**：
  - `/` — 知识图谱交互首页（5.07 MB 单文件，含右上角「文档站」「GitHub」导航）
  - `/docs/` — 文档站首页（69 页按 6 个分组列出）
  - `/docs/<route>.html` — 69 页静态文档，左侧章节目录，标题带真实 `id`
  - `/assets/site.css` — 站点样式（暗色主题）
- **锚点问题解决**：所有面板里的官方文档入口 `url` 由官网改为站内 `/docs/<route>.html`；悬浮卡片中的 `#锚点` 链接自动拼成 `/docs/<route>.html#anchor`；文档站为 1,232 个官网锚点（含 412 个 `persistence-type-sha256-*`、181 个 config-schema、65 个 event）生成可定位的 `<span id>` 与 `<a id>`；源 md 中的原始 `<a id="...">` 标签保留为真实 HTML 而非转义文本。实测 `persistence-catalog.html#persistence-type-sha256-9a930...` 可精确滚动定位。
- **构建产物**：`.ua/site/`（8.1 MB，71 个文件）；构建脚本 `.ua/build_site.py`；部署脚本 `.ua_deploy.py`；Nginx 配置块 `.ua_nginx_block.txt`。
- **验证**：TLS 握手通过（SAN=kg.agidsh.com）；HTTP 301 → HTTPS；`/`、`/docs/`、文档页、`/assets/site.css` 全部 200；浏览器实测首页图谱渲染、导览、文档站锚点跳转正常。

## 八、文档站 UI 改用官方 VitePress（第六轮）

按用户要求「文档页 UI 直接用相同 reference/」，文档站改为官方站点的完整镜像：

- `.ua/mirror_official_docs.py`：从 `https://deepseek-harness.github.io/deepseek-harness/` 下载 69 页 HTML + 50 个资源（CSS/JS/字体/图标）+ 68 个页面内容 chunk（`*.md.*.lean.js`，VitePress SPA 路由必需），产物在 `.ua/site/deepseek-harness/`（17.7 MB）。
- CSS 中 `url(/assets/*.woff2)` 改写为 `url(/deepseek-harness/assets/*.woff2)`；每页注入右下角「← 返回知识图谱」浮动入口。
- 官网 404 的 `cookbook/contributing-system-messages` 用自建文档页兜底。
- 访问路径与官方一致：`/deepseek-harness/reference/<page>`，VitePress SPA 才能正确路由；首页「文档站」按钮指向 `/deepseek-harness/reference/`；图谱节点 `doc.url` 同步改为该前缀。
- Nginx：`location /deepseek-harness/` 用 `try_files $uri $uri/index.html =404`；旧 `/docs/` 与 `/reference/` 保留兼容。
- 验证：首页、子页、带 SHA-256 锚点子页全部 200 且官方 UI 完整；锚点 `#persistence-type-sha256-9a930...` 精确滚动定位；图谱首页「文档站」按钮跳转正确。

## 九、入门页与开发页入站（第七轮）

按用户要求「入门页和开发页也放上去」：

- 从 `website/docs.ts` 路由表提取 guide（11 页）与 develop（10 页）共 21 页，加入镜像范围。
- 镜像规模：90 页 HTML（88 页官网可达 + 2 页 404 兜底）、88 个内容 chunk、50 个资源，共 19.7 MB。
- 兜底：`guide/session-control` 与 `reference/cookbook/contributing-system-messages` 官网未发布，前者用仓库 `docs/user/session-control.md` 生成简易页，后者沿用自建文档页。
- 验证：`/deepseek-harness/guide/quickstart`、`/guide/providers`、`/guide/python-sdk`、`/develop/basic/index`、`/develop/framework/service`、`/develop/practice/llm-adapter`、`/guide/session-control` 全部 200；页面标题正确、VitePress UI 完整、返回图谱入口存在。

## 十一、404 修复与中英双语（第八轮）

**404 根因与修复**：用户反馈入门/开发页报 404。服务端 HTTP 200 且内容正确，是 VitePress SPA 客户端路由问题——导航「入门」指向 `/guide/`、`开发` 指向 `/develop/basic/`，但 `/guide/` 目录无 index 页（官网把 quickstart 作为 landing）。修复：
- Nginx 加 4 条精确 301：`/guide/` → `/guide/quickstart`、`/develop/` → `/develop/basic/`，英文同理。
- 目录级 landing 页也复制首篇内容作兜底。
- 浏览器实测标题从「404」变为「使用 Web UI」，404 消除。

**中英双语**：官网本身有双语，镜像英文全系列 `/en/reference/`、`/en/guide/`、`/en/develop/` 共 90 页 + 88 个英文 chunk。VitePress 顶栏原生「English / 简体中文」切换按钮直接可用：中文页链到 `/en/...`，英文页链回中文路径。
- 镜像规模：180 页 HTML（176 可达 + 4 未发布兜底）、176 chunk、50 资源，共 34.8 MB。
- 验证：`/en/reference/`、`/en/guide/quickstart`、`/en/develop/basic/index`、`/en/reference/persistence-catalog` 全部 200 且标题为英文；语言切换链接双向正确。

## 十二、源码仓库（第九轮）

按用户要求建新仓库存放网站源码：

- 仓库：`https://github.com/wind-wh/dsh-knowledge-graph`（public，默认分支 main）
- 服务器 Git 凭据：SSH key（`git@github.com:wind-wh`，已在服务器 `~/.ssh/id_ed25519`），GitHub 账户 `wind-wh`；API token 由用户提供用于创建仓库。
- 仓库结构：`scripts/`（构建脚本 + 面板前端源码）、`data/doc-payload.json`、`docs/docs-sync-report.md`、`site/`（可直接部署的静态站点）、`README.md`、`.gitignore`。
- 首次提交：`90c16af Initial commit DSH KG site`，493 个文件，39,914 行插入；远程 HEAD 与本地一致。
- 本地源码目录：`D:\work\DSH\dsh-knowledge-graph`；服务器源码目录：`C:\wwwroot\kg-src`。
- 本地代理：`D:\work\DSH\socks_proxy.py`（SOCKS5 127.0.0.1:1080，经服务器 SSH 转发），用于本地无法直连 GitHub 时访问；实际推送走服务器 SSH 直连。

## 十三、仍未处理

- UI 层源码（`packages/client`、`apps/web`、`apps/desktop`）不在源码分析范围（`project.scope` 已声明）；reference 站点中描述这些子系统的页面本身已全部入图。
- 悬浮卡片正文仍截断至 60k 字符（性能取舍）；完整正文可在文档站查看。
- 官方镜像依赖上游站点内容更新；上游改版后需重跑 `mirror_official_docs.py`。
- 图谱首页本身仍为中文界面；双语切换覆盖的是 VitePress 文档站（官网原生能力）。
