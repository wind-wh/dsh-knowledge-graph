#!/usr/bin/env python3
"""按官方参考文档（reference/）校正并补充知识图谱的分层与导览文案。

- 修正：与 docs 冲突的事实（profile/bundle 清单、SQLite 归属、core/scope 无 ctx 键等）
- 补充：官方术语（组合包、轮次/步骤、事件三域、seam 三角、工具流水线顺序）
- 新增：每层/每步的官方文档链接；第 15 步「扩展点归属」
"""
import json
import shutil
from pathlib import Path

UA = Path(__file__).resolve().parent
KG = UA / "knowledge-graph.json"
backup = UA / "knowledge-graph.pre-docs.json"

R = "https://deepseek-harness.github.io/deepseek-harness/reference"

LAYERS = {
    "layer:core-runtime": {
        "description": "官方「核心包」表里的 5 个 core 包与通用基元：会话事件日志（ctx.sessions）、"
        "系统提示词与工具 schema 组装（ctx.systemPrompt）、作用域化工具注册表与执行管线（ctx.tools）、"
        "Agent 接口与活跃注册表（ctx.agents）、默认驱动器（ctx.agentLoop）。core/scope 是零依赖的作用域原语库，"
        "不提供 ctx 键。另含被全仓复用的 deque、timeout、crypto、ripgrep 等基元。",
        "doc": R + "/subsystems/core",
        "docTitle": "核心包与 Agent",
    },
    "layer:llm": {
        "description": "Message / ContentBlock / StreamChunk 的公共词汇表与适配器 seam（ctx.llm）；Provider 为 "
        "llm-deepseek、llm-pi-ai 与仅用于回放的 llm-replay，DeepSeek 专有扩展走 ctx.deepseekLlmApiExtensions。"
        "另有 token 计量与重试策略。官方把 llm/llm 与 5 个 core 包并列列入「核心包」。",
        "doc": R + "/subsystems/llm-streaming",
        "docTitle": "LLM 与流式协议",
    },
    "layer:session-context": {
        "description": "会话日志是模型上下文的唯一来源（「模型可见即已记录」）：JSONL 持久化（v0 用 session.jsonl，"
        "v1 及以后用 session.vN.jsonl，每个相邻迁移包只负责一步 vN→vN+1）、deriveMessages() 投影历史、"
        "ctx.sessionProjections 投影 seam，以及 session-query 的 SQLite 索引与导出。另含上下文注入与引用、"
        "KV/JSON/SQLite 存储、spill 与压缩（ctx.compaction）。SQLite 属查询索引，不是持久化载体。",
        "doc": R + "/subsystems/session",
        "docTitle": "Session 事件日志",
    },
    "layer:capability-providers": {
        "description": "按 Service Definition / Provider / Consumer 三角组织的可替换能力，官方 seam 参考页共列出 35 个："
        "fs、shell、terminals、subprocess、sandbox、ssh、MCP（ctx.mcpResources）、LSP、web、Office 文档、"
        "browser-use、computer-use、attachments、credentials、authorization、storage、directory-picker，"
        "以及 user-questions、user-approval、commands 等交互 seam。替换一个 Provider 即可整体迁移执行世界。",
        "doc": R + "/capability-seams",
        "docTitle": "能力 seam 参考",
    },
    "layer:orchestration": {
        "description": "子代理 seam（ctx.subagents）与 Provider 家族（spawn-in-process、fork-in-process、acp、codex、"
        "claude-code、dsh-sdk）、subagent 控制工具、Agent Teams 的共享任务板、Workflow 引擎（ctx.workflowEngine）"
        "与 PTC 运行时（ctx.ptcRuntime）、skill 装载（ctx.skills）、goal/plan/todo、guard 策略、"
        "后台作业（ctx.jobs）与结果交付。",
        "doc": R + "/subsystems/subagent",
        "docTitle": "Subagent 子系统",
    },
    "layer:host-boot": {
        "description": "运行中的 dsh 是由 profile（Harness home 中的具名组装）逐层叠加组合包（bundle）得到的插件树："
        "profile 列出的有序组合包 → 其 cordis.patch.yml → home patch → --patch overlay；一条 patch 按 id 定位条目"
        "并整体替换其 config。profile 与 bundle 各自在 package.json 的 dsh 字段声明（dsh.profile / dsh.bundle）。"
        "另含 plugin-manager / plugin-market、host 侧目录选择与静态前端、preset 组合、Cordis 动态插件扩展、"
        "遥测、反馈与匿名身份。",
        "doc": R + "/",
        "docTitle": "架构参考 · Profile 与组合包",
    },
    "layer:api-transport": {
        "description": "面向 Web 客户端与外部程序的传输面：session / terminal / workspace / job / settings 控制器与 "
        "gateway、Typert Remote 的描述符校验与流式 RPC、Remote 事件源装配，以及 ACP 服务器与 dsh JS SDK 基于 "
        "stdio 的 JSON-RPC 客户端与服务端。",
        "doc": R + "/",
        "docTitle": "架构参考 · 事件与扩展点",
    },
    "layer:app-entry": {
        "description": "dsh 启动器与随发行版交付的产品组装：`dsh --profile <web|headless|sdk|sdk-minimal|acp>` 或 "
        "`dsh <name>`；plugin 是管理子命令，同名 profile 需用 `--profile plugin` 选择。组合包为 dsh-base"
        "（web/headless/sdk/acp 的共享第一层）、dsh-web-app、dsh-headless、dsh-sdk-app、dsh-acp-app，"
        "以及刻意不应用 base 的 dsh-sdk-minimal。`--dump-config` 在不启动插件树的前提下打印合成配置。",
        "doc": R + "/",
        "docTitle": "架构参考 · 应用启动",
    },
    "layer:language-bindings": {
        "description": "面向 Python 用户的同步 SDK（高层 API、stdio JSON-RPC client、pydantic 协议 models、Office 调用），"
        "以及把普通 dsh CLI 打成 deepseek-harness-sdk-runtime-<platform>-<arch> 的运行时 wheel；"
        "客户端默认以显式 Harness home 启动 `dsh --profile sdk`。",
        "doc": R + "/",
        "docTitle": "架构参考 · Python SDK",
    },
    "layer:dev-tooling": {
        "description": "构建/生成/校验/发布脚本、Typert 类型生成器、native launcher 发布脚本与根级配置"
        "（pnpm workspace、vitest、oxlint、CI），以及 AGENTS/贡献/安全等仓库文档。"
        "verify-application-entrypoints.ts 把每个 bin、可执行源码与根脚本归类，并拒绝绕过 `dsh` 的 Node 应用路径。",
        "doc": R + "/",
        "docTitle": "架构参考",
    },
}

TOUR = {
    1: {
        "title": "项目定位与仓库布局",
        "description": "DeepSeek Harness（dsh）是一个遵循「Everything is a Plugin」的 agent harness：没有特权内核，"
        "所有能力都是插件向共享 context 贡献的 service、类型化事件与可逆副作用，因此模型适配器、工具注册表、"
        "会话日志乃至 agent loop 本身都可以从配置替换。AGENTS.md 交代架构约束、目录布局与评审规则，"
        "package.json 给出 pnpm workspace 的包划分与构建/类型检查/测试/打包入口。"
        "本图谱覆盖核心运行时，UI 层（packages/client、apps/web、apps/desktop）不在范围内，"
        "因此官方文档描述的 Desktop 应用与 Web Client 不体现在图中。",
        "doc": R + "/",
        "docTitle": "架构参考",
    },
    2: {
        "title": "Cordis 插件树：profile、组合包与 patch 层叠",
        "description": "运行中的 dsh 不是写死的 main，而是由 profile 逐层叠加组合包（bundle）得到的一棵 Cordis 插件树。"
        "profile 是存放在 Harness home 中的具名组装，列出自己叠放的组合包、树外插件与用户的 cordis.patch.yml；"
        "组合包是「Cordis 配置项 + 挂载代码」的分发格式，插入的内容始终可被上层 patch。二者分别在 package.json 的 "
        "dsh.profile / dsh.bundle 字段声明。各层按序应用在空条目列表上：profile 中有序的组合包 → cordis.patch.yml → "
        "home patch → --patch overlay，一条 patch 按 id 定位条目并替换其整个 config。app-boot 负责解析 profile、"
        "叠加补丁并驱动 Loader 直到插件树稳定；`dsh --profile web --dump-config` 可打印合成结果。",
        "doc": R + "/",
        "docTitle": "架构参考 · Profile 与组合包",
    },
    3: {
        "title": "作用域上下文与系统提示词",
        "description": "Cordis 的共享 context 不是全局单例：scope 原语为每个子作用域创建带不透明身份标记的上下文，"
        "让注册视图沿链继承、事件准入沿链上溯，store 再按 global → 祖先链 → 自身 的顺序解析命名与匿名条目。"
        "注意 core/scope 是零依赖的注册原语库，官方核心包表中它不提供 ctx 键。system-prompt 站在这套机制之上，"
        "把有序提示段落、动态上下文快照、工具 schema 与提示变量经 waterfall 组装后写入会话的 system 消息"
        "（ctx.systemPrompt）；第 2 步的插件树之所以能让多个 Agent 复用同一批插件而互不串扰，靠的就是作用域隔离。",
        "doc": R + "/subsystems/system-prompt",
        "docTitle": "System Prompt 子系统",
    },
    4: {
        "title": "Agent 主循环：turn 与 step",
        "description": "官方定义：一个步骤（step）是一次模型请求加上它调用的工具；一个轮次（turn）包含零个或多个步骤，"
        "在领取首条输入之前打开，在不再欠任何工作时关闭。事件顺序为 turn/start → 领取输入 → agent/pre-step → "
        "step/start → agent/request（prepareCall）→ 提交 system/user 消息 → llm/stream → assistant/assistant-stream "
        "→ tool/call → tools/pre-execute → tools/execute → tools/post-execute → tool/result → step/end → "
        "agent/turn-stopping → turn/end。ReactLoopAgent 负责推进这些边界，inbox 提供驱动自有的持久收件箱作为输入闸门，"
        "agent 服务本身只保留活跃注册表与工厂委托。",
        "doc": R + "/agent-lifecycle",
        "docTitle": "轮次与步骤生命周期",
    },
    5: {
        "title": "Session 追加式事件日志",
        "description": "Session 是事件溯源的：所有事实以追加式日志记录，「模型可见即已记录」，消息历史只是由 "
        "deriveMessages() 从日志投影出的视图。每个 assistant/message 都内嵌产生它的精确紧凑带时间 stream；"
        "失败、重试、取消或 stream error 到达 settlement 时若没有 surface message，则记为 assistant/attempt，"
        "且不进入模型历史。JSONL 持久化是订阅事件的插件：v0 用 session.jsonl，v1 及以后用 session.vN.jsonl，"
        "每个相邻迁移包只负责一步 vN→vN+1，已提交 generation 路径绝不重命名或删除。存储可替换，日志语义不变。",
        "doc": R + "/subsystems/session",
        "docTitle": "Session 子系统",
    },
    6: {
        "title": "工具注册表与受保护执行管线",
        "description": "ToolsService 按作用域层级合并注册与限制，派生出模型可见的工具视图，并在工具可用性变化时通知模型；"
        "执行统一走 ctx.tools.execute：tools/pre-execute 瀑布先执行，然后是单调守卫（不得重排序的所有者策略），"
        "再是 tools/execute 与 tools/post-execute 瀑布——三个瀑布都可转换调用。定义的 projectContent 在后置策略之前"
        "安装准备好的内容，finalizeContent 与 tools/result 在之后执行；审批（ctx.approval）在单调守卫之前处理询问。"
        "batch.ts 负责单步内调度：独占调用形成屏障，并发调用进入有界滚动池。工具作者只需声明 schema 与 handler。",
        "doc": R + "/tool-execution-pipeline",
        "docTitle": "工具执行流水线",
    },
    7: {
        "title": "LLM 抽象与流式适配",
        "description": "llm 包把模型调用收敛成可替换的适配器 seam（ctx.llm）：Message / ContentBlock / StreamChunk 是"
        "公共词汇，LlmRuntime 管理适配器注册、路由与模型解析，并以 waterfall 暴露可拦截的流式调用。"
        "官方 Provider 有 llm-deepseek、llm-pi-ai 与仅用于回放的 llm-replay，DeepSeek 专有扩展走 "
        "ctx.deepseekLlmApiExtensions。一次请求由 prepareCall 绑定适配件后发出：未变化的恢复延续请求序列，"
        "而 surface 替换与图片省略会开启新序列。BlockAssembler 把增量 chunk 装配成完整 assistant 消息块并记录 usage。",
        "doc": R + "/subsystems/llm-streaming",
        "docTitle": "LLM 流式子系统",
    },
    8: {
        "title": "能力 seam：文件系统与沙箱",
        "description": "seam 由三种角色构成：声明接口的 Service Definition、实现它的 Provider、使用它的 Consumer"
        "（通常是面向模型的工具）；单独一个角色不构成 seam。官方参考页共列出 35 个 seam。fs 是典型例子："
        "ctx.fs 声明目标身份、包含性检查与原子变更，fs-local / fs-sandbox / fs-ssh 提供实现，tool-fs 是消费方。"
        "文件系统与进程提供方共享同一个执行世界，因此把它们指向远程沙箱，也就同时把 Bash、PTY 与 LSP 搬了过去，"
        "无需提供方专用 fork。",
        "doc": R + "/capability-seams",
        "docTitle": "能力 seam 参考（35 个）",
    },
    9: {
        "title": "MCP 外部工具接入",
        "description": "MCP 让外部服务器的工具进入同一张工具表：seam 声明为 ctx.mcpResources（mcp-resources 包），"
        "Provider 是 mcp-client，消费方即 resources 自身。mcp-client 以 mcp__<server>__<raw> 的公共名把工具注册到 "
        "ctx.tools，host 服务为管理多服务器的插件提供校验、挂载、探测与授权。connection.ts 持有单个实例的 "
        "client/transport 代际，断线时按有界指数退避重启，使工具注册表始终跟随活代际；diagnostic.ts 把上游错误"
        "归类并脱敏密钥，第 6 步的失败结果因此保持一致的错误语义。",
        "doc": R + "/capability-seams",
        "docTitle": "能力 seam 参考 · MCP",
    },
    10: {
        "title": "子代理与多智能体编排",
        "description": "ctx.subagents 是一个命名提供方注册表加能力校验的异步启动 API，官方 Provider 包括 "
        "spawn-in-process、fork-in-process、acp、codex、claude-code 与 dsh-sdk——同一个接口后面可以是从新建子 agent"
        "到把整个轮次委派给另一个产品的巨大差异。SubagentRuntime 暴露消息、中断、目录与容量控制，manager.ts 用"
        "子代理锁与激活表统一容量、所有权与释放并支持冷恢复。Agent Teams 在根 Session 开启后提供任务策略与共享任务板；"
        "workflow-ptc 把工作流 VM 放进沙箱 PTC 执行器中编排多个子代理。",
        "doc": R + "/subsystems/subagent",
        "docTitle": "Subagent 子系统",
    },
    11: {
        "title": "API 传输：Gateway 与 Session Remote",
        "description": "Host 与浏览器或远程客户端之间只有一层 Typert Remote：gateway 通过 Cordis Service 与已注册 provider "
        "解析描述符、严格校验参数、承接流式 RPC，并管理转发事件的登记、下发、取消与结算；remotes 把允许转发的 "
        "Cordis 事件注册为事件源，用队列把同步 listener 桥接成 AsyncIterable。session-controller 在其上组装历史、状态、"
        "列表与 Web 控制器，客户端 Session 对象持有事件窗口与可观察快照。接口与实现分离后，同一套控制器可以同时服务"
        "本地 Web、远程访问与 SDK。",
        "doc": R + "/",
        "docTitle": "架构参考 · 事件域",
    },
    12: {
        "title": "CLI 入口与启动链路",
        "description": "dsh 命令行的 main 很薄：bin.ts 装配运行环境与参数解析后，把 profile、patch 与 config dump 之外的 "
        "token 原样交给被启动的应用树。受支持的 Node 应用只能通过具名 profile 启动——随发行版交付 5 个："
        "web、headless、sdk、sdk-minimal、acp，可用 `--profile <name>` 或 `dsh <name>` 选择；plugin 是管理子命令，"
        "同名 profile 必须写 `--profile plugin`。scripts/verify-application-entrypoints.ts 会把每个 bin 与可执行源码"
        "归类，并拒绝任何绕过 dsh 的 Node 应用路径。profile-boot.ts 是各表面共享的启动流程，process-shutdown.ts 让"
        "正常完成与信号共享同一个 disposer。",
        "doc": R + "/",
        "docTitle": "架构参考 · 应用启动",
    },
    13: {
        "title": "Python SDK 与 stdio JSON-RPC",
        "description": "Python SDK 把 dsh 当成子进程使用：client.py 通过 stdio 讲 JSON-RPC，负责 initialize、session/prompt、"
        "通知订阅与用户提问回调；api.py 在其上提供同步高层 API，封装 runtime 生命周期、Session 句柄与 RunResult。"
        "其运行时 wheel 把普通 dsh CLI 打成 deepseek-harness-sdk-runtime-<platform>-<arch>，客户端默认以显式 "
        "Harness home 启动 `dsh --profile sdk`，极简示例选择 sdk-minimal。Node 侧 packages/sdk/server 是这条链的另一端。"
        "Python 只暴露 profile 选择与有序 patch 文件，不暴露完整 Cordis 树；持久外部插件通过 `dsh plugin` 安装。",
        "doc": R + "/",
        "docTitle": "架构参考 · Python SDK",
    },
    14: {
        "title": "工程脚本与仓库门禁",
        "description": "最后看仓库如何自我约束：scripts/AGENTS.md 规定 gate 脚本以 shell-free 方式调用 pnpm、入库前把路径"
        "规范化为 /；translation-pairing.ts 校验中英文档成对且结构签名一致，markdown.ts 提供文档门禁共用的 Markdown "
        "解析与 HTML 注释区间判断；verify-application-entrypoints.ts 守住启动入口，禁止绕过 dsh 的 Node 应用路径。"
        "lefthook.yml 把这些检查挂到 pre-commit 与 pre-push，让第 1 步读到的约定变成强制门禁。",
        "doc": R + "/",
        "docTitle": "架构参考",
    },
    15: {
        "title": "扩展点归属：新行为加在哪里",
        "description": "官方给出了一张「新行为归属」映射，这是改代码前的第一判断：添加模型提供方在 ctx.llm 注册适配器；"
        "添加面向模型的能力在 ctx.tools 注册，schema 自动进入提示词组装；添加 shell 执行注册 ctx.shell 后端"
        "（本地后端通过 ctx.subprocess spawn）；添加持久终端注册 ctx.terminals；添加用户命令用 ctx.commands；"
        "后台任务用 ctx.jobs；文件系统访问或策略用 ctx.fs 或监听 fs/* 事件；限制所启动进程用 ctx.sandbox，"
        "消费方在启动前包装 argv；拦截请求、工具或轮次用相应的 agent/* 或 tools/* 事件；添加模型可见上下文调用 "
        "agent.inject()；持久会话状态则扩展 SessionEventMap。共同点是：事件在三个域内提供扩展点——会话事件是可重放"
        "的持久事实，Agent 事件承载进行中的协调，能力事件让策略挂到 seam 上而无需导入循环。",
        "doc": R + "/",
        "docTitle": "架构参考 · 新行为的归属位置",
        "nodeIds": [
            "file:packages/core/session/src/index.ts",
            "file:packages/core/tools/src/index.ts",
            "file:packages/fs/fs/src/index.ts",
            "file:packages/llm/llm/src/index.ts",
            "file:packages/boot/app-boot/src/profile.ts",
        ],
    },
}


def main():
    kg = json.loads(KG.read_text(encoding="utf-8"))
    if not backup.exists():
        shutil.copy2(KG, backup)

    ids = {n["id"] for n in kg["nodes"]}

    for layer in kg["layers"]:
        patch = LAYERS.get(layer["id"])
        if patch:
            layer.update(patch)

    touched = 0
    for step in kg["tour"]:
        patch = TOUR.get(step["order"])
        if not patch:
            continue
        for key, value in patch.items():
            if key == "nodeIds":
                missing = [i for i in value if i not in ids]
                assert not missing, f"step {step['order']} missing nodes: {missing}"
                step["nodeIds"] = value
            else:
                step[key] = value
        touched += 1

    existing = {s["order"] for s in kg["tour"]}
    if 15 not in existing:
        patch = TOUR[15]
        missing = [i for i in patch["nodeIds"] if i not in ids]
        assert not missing, f"step 15 missing nodes: {missing}"
        kg["tour"].append({
            "order": 15,
            "title": patch["title"],
            "description": patch["description"],
            "nodeIds": patch["nodeIds"],
            "doc": patch["doc"],
            "docTitle": patch["docTitle"],
        })

    kg["project"]["description"] = (
        "DeepSeek Harness (dsh) — DeepSeek 开源的 agent harness：运行中的 dsh 是由 profile 逐层叠加组合包（bundle）"
        "得到的 Cordis 插件树，没有特权内核，模型适配器、工具注册表、会话日志与 agent loop 本身都是可从配置替换的插件；"
        "pnpm 单仓，含 core/agent-loop、session、llm、capability seams、编排与 CLI/Web/SDK 产品组装。"
    )
    kg["project"]["scope"] = (
        "核心运行时与插件生态（已排除 UI 层：packages/client、packages/experimental、apps/web、apps/desktop）。"
        "官方文档描述的 Desktop 应用与 Web Client 不在本图谱范围内。"
    )

    KG.write_text(json.dumps(kg, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"layers patched: {sum(1 for l in kg['layers'] if 'doc' in l)}/{len(kg['layers'])}")
    print(f"tour steps: {len(kg['tour'])} (patched {touched}, appended 15={15 not in existing})")
    print(f"written {KG}  ({KG.stat().st_size/1024:.0f} KB)")


if __name__ == "__main__":
    main()
