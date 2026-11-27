#!/usr/bin/env python3
"""把官方 reference 站点的全部内容并入知识图谱（幂等）。

来源：docs/ 下站点 reference 集合的 69 页（概念 / 生成参考 / Cordis API /
Cookbook / 子系统）+ 三份生成式目录（config-catalog、tool-catalog、
persistence-catalog / experimental-persistence-catalog）+ capability-seams 服务表。

新增节点：
  doc:reference/*          页面
  docsec:reference/*#a     页面内 H2/H3 章节
  service:ctx.*            上下文服务键（角色 / 所属包 / 实现 / 消费方）
  event:*                  持久化会话事件 + 实时扩展点事件
  record:*                 实验性插件记录
  tool:*                   模型可见工具（含参数名）
  plugin-config:*          插件配置声明；plugin-config:*#field 为其顶层字段

新增边：contains / documents / declares / implements / consumes / provides / emits / related

用法：python apply_reference_sync.py [--dry]
"""
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

UA = Path(__file__).resolve().parent
ROOT = UA.parent
DOCS = ROOT / "docs"
SITE = "https://deepseek-harness.github.io/deepseek-harness"
DRY = "--dry" in sys.argv

# ---------------------------------------------------------------- 页面清单
PAGES = [
    ("architecture", "reference/index", "概念"),
    ("cordis-primer", "reference/cordis-primer", "概念"),
    ("capability-seams", "reference/capability-seams", "概念"),
    ("agent-lifecycle", "reference/agent-lifecycle", "概念"),
    ("tool-execution-pipeline", "reference/tool-execution-pipeline", "概念"),
    ("api-gateway", "reference/api-gateway", "概念"),
    ("config-catalog", "reference/config-catalog", "生成参考"),
    ("tool-catalog", "reference/tool-catalog", "生成参考"),
    ("persistence-catalog", "reference/persistence-catalog", "生成参考"),
    ("experimental-persistence-catalog", "reference/experimental-persistence-catalog", "生成参考"),
    ("cordis-api/context", "reference/cordis-api/context", "Cordis API"),
    ("cordis-api/events", "reference/cordis-api/events", "Cordis API"),
    ("cordis-api/fiber", "reference/cordis-api/fiber", "Cordis API"),
    ("cordis-api/registry", "reference/cordis-api/registry", "Cordis API"),
    ("cordis-api/service", "reference/cordis-api/service", "Cordis API"),
    ("cordis-api/inherited", "reference/cordis-api/inherited", "Cordis API"),
    ("cookbook/adding-a-package", "reference/cookbook/adding-a-package", "Cookbook"),
    ("cookbook/adding-a-tool", "reference/cookbook/adding-a-tool", "Cookbook"),
    ("cookbook/contributing-system-messages", "reference/cookbook/contributing-system-messages", "Cookbook"),
    ("cookbook/adding-an-llm-adapter", "reference/cookbook/adding-an-llm-adapter", "Cookbook"),
    ("cookbook/adding-a-settings-card", "reference/cookbook/adding-a-settings-card", "Cookbook"),
    ("cookbook/extension-cookbook", "reference/cookbook/extension-cookbook", "Cookbook"),
]
SUBSYSTEM_GROUPS = [
    ("子系统总览", ["README"]),
    ("内核与作用域", ["core", "scope"]),
    ("会话与持久化", ["session", "session-query", "session-reference", "session-title",
                "session-projection", "persistence", "spill", "session-telemetry"]),
    ("模型与上下文", ["llm-streaming", "token-meter", "system-prompt", "compaction"]),
    ("执行与工具", ["tools", "shell", "subprocess", "terminal", "jobs", "filesystem",
               "lsp", "ptc-runtime", "web", "skills", "workflow", "subagent"]),
    ("策略与交互", ["approval", "permission-presets", "sandbox", "plan", "user-questions",
               "commands", "goal", "schedule"]),
    ("平台与接入", ["web-server", "web-client", "client-modules", "slots", "client-resources",
               "sidebar-right", "conversation", "typert", "storage", "workspace",
               "settings", "credentials"]),
]
for _g, _files in SUBSYSTEM_GROUPS:
    for _f in _files:
        _route = "reference/subsystems/index" if _f == "README" else f"reference/subsystems/{_f}"
        PAGES.append((f"subsystems/{_f}", _route, _g))

# 站点尚未发布（404）但仓库内已存在的页面 → 指向 GitHub 源码
UNPUBLISHED = {
    "reference/cookbook/contributing-system-messages":
        "https://github.com/deepseek-ai/deepseek-harness/blob/master/docs/cookbook/contributing-system-messages.zh.md",
}

GENERATED = {"config-catalog", "tool-catalog", "persistence-catalog", "experimental-persistence-catalog"}

# ---------------------------------------------------------------- 文本工具
LINK = re.compile(r"\[([^\]]*)\]\([^)]*\)")
CODE = re.compile(r"`([^`]*)`")
TAG = re.compile(r"<[^>]+>")
BOLD = re.compile(r"(\*\*|__)(.*?)\1")


def clean(s: str) -> str:
    s = LINK.sub(r"\1", s)
    s = CODE.sub(r"\1", s)
    s = TAG.sub("", s)
    s = BOLD.sub(r"\2", s)
    return re.sub(r"\s+", " ", s.replace("\u200b", "")).strip()


def clip(s: str, n: int = 190) -> str:
    s = s.strip()
    if len(s) <= n:
        return s
    cut = max(s.rfind("。", 0, n), s.rfind("；", 0, n), s.rfind("，", 0, n))
    return s[: cut + 1] if cut > n * 0.5 else s[:n] + "…"


def first_para(lines, start, limit=320):
    buf, fence = [], False
    for ln in lines[start:]:
        if ln.startswith("```"):
            fence = not fence
            continue
        if fence:
            continue
        t = ln.strip()
        if re.match(r"^#{1,6} ", t):
            break
        if not t:
            if buf:
                break
            continue
        if t.startswith(("|", "<!--", "- `", "* `", ">", "  ")):
            if t.startswith(("- `", "* `")):
                continue
            if buf:
                break
            continue
        if t.startswith(("[English]", "[中文]")):
            continue
        buf.append(t)
        if len(" ".join(buf)) > limit:
            break
    return clip(clean(" ".join(buf)))


def sentences(text):
    return [s for s in re.split(r"(?<=[。！？；\n])", text) if s.strip()]


def sentence_about(text, token, n=170):
    for s in sentences(text):
        if token in s and not s.strip().startswith("|"):
            return clip(clean(s), n)
    return ""


def doc_path(stem):
    zh = DOCS / f"{stem}.zh.md"
    return zh if zh.exists() else DOCS / f"{stem}.md"


def rel_file(stem):
    return f"docs/{stem}.{'zh.md' if (DOCS / f'{stem}.zh.md').exists() else 'md'}"


# ---------------------------------------------------------------- 包名 → 目录
pkg_dir, dir_pkg = {}, {}
for pj in list((ROOT / "packages").glob("*/*/package.json")) + list((ROOT / "apps").glob("*/package.json")):
    try:
        data = json.loads(pj.read_text(encoding="utf-8"))
    except Exception:
        continue
    name = data.get("name")
    if name and name.startswith("@deepseek-ai/"):
        d = str(pj.parent.relative_to(ROOT)).replace("\\", "/")
        pkg_dir[name] = d
        dir_pkg[d] = name

# ---------------------------------------------------------------- 页面与章节
def parse_page(stem, route, group):
    raw = doc_path(stem).read_text(encoding="utf-8")
    lines = raw.splitlines()
    title = None
    for ln in lines:
        if ln.startswith("# "):
            title = clean(ln[2:])
            break
    if stem == "subsystems/README":
        title = "子系统总览"
    page = {
        "id": f"doc:{route}",
        "type": "document",
        "name": title or stem,
        "filePath": rel_file(stem),
        "summary": first_para(lines, 0) or f"{group} · 官方 reference 页面。",
        "tags": ["reference", group, "official-docs"],
        "complexity": "reference",
        "doc": f"{SITE}/reference/" if route == "reference/index" else f"{SITE}/{route}",
        "group": group,
        "route": route,
    }
    sections, anchor = [], None
    for i, ln in enumerate(lines):
        m = re.match(r'^<a id="([^"]+)"></a>\s*$', ln.strip())
        if m:
            anchor = m.group(1)
            continue
        m = re.match(r"^(#{2,3}) (.+)$", ln)
        if not m:
            continue
        level = len(m.group(1))
        text = clean(m.group(2)).rstrip("#").strip()
        if not text:
            continue
        # 生成式目录的包名/事件族标题已由实体节点承载
        if stem in GENERATED:
            if text.startswith("`") or re.fullmatch(r"[@\w./-]+", text, re.ASCII):
                anchor = None
                continue
            if stem == "persistence-catalog" and level == 3:
                anchor = None
                continue
        body = []
        for ln2 in lines[i + 1:]:
            if re.match(r"^#{2,3} ", ln2):
                break
            body.append(ln2)
        sections.append({
            "id": f"docsec:{route}#{anchor or len(sections) + 1}",
            "type": "doc-section",
            "name": text,
            "filePath": rel_file(stem),
            "summary": first_para(lines, i + 1) or f"{page['name']} · {text}",
            "tags": ["reference", group, f"H{level}"],
            "complexity": "reference",
            "level": level,
            "doc": f"{SITE}/{route}" + (f"#{anchor}" if anchor else ""),
            "page": page["id"],
            "_body": "\n".join(body),
        })
        anchor = None
    return page, sections


pages, sections = [], []
page_text = {}
for stem, route, group in PAGES:
    p, secs = parse_page(stem, route, group)
    pages.append(p)
    sections.extend(secs)
    page_text[route] = doc_path(stem).read_text(encoding="utf-8")

for _p in pages:
    if _p["route"] in UNPUBLISHED:
        _p["doc"] = UNPUBLISHED[_p["route"]]
for _s in sections:
    if _s["page"].endswith("/contributing-system-messages"):
        _s["doc"] = UNPUBLISHED["reference/cookbook/contributing-system-messages"]

# ---------------------------------------------------------------- 服务（seam 表）
seam_raw = (DOCS / "capability-seams.zh.md").read_text(encoding="utf-8")
seam_text = seam_raw[seam_raw.index("| ctx 键 | 角色 |"):]


def pkg_links(cell):
    return re.findall(r"\[`([^`]+)`\]\(\.\./(packages/[^)]+)\)", cell)


services = {}
for row in seam_text.splitlines():
    if not row.startswith("| `ctx."):
        continue
    cells = [c.strip() for c in row.strip().strip("|").split(" | ")]
    if len(cells) < 7:
        continue
    key, role = clean(cells[0]), clean(cells[1])
    owner, impls, consumers, plugins = pkg_links(cells[2]), pkg_links(cells[3]), pkg_links(cells[4]), pkg_links(cells[5])
    services[key] = {
        "id": f"service:{key}",
        "type": "service",
        "name": key,
        "filePath": f"docs/capability-seams/{owner[0][1].split('/')[1] if owner else 'services'}",
        "summary": clip(f"[{role}] {clean(cells[6])}", 240),
        "tags": ["reference", "seam", role],
        "complexity": role,
        "owner": owner[0][1] if owner else "",
        "ownerName": owner[0][0] if owner else "",
        "impls": [p for _, p in impls],
        "consumers": [p for _, p in consumers],
        "plugins": [p for _, p in plugins],
        "doc": f"{SITE}/reference/capability-seams",
    }

CTX = re.compile(r"`(ctx\.[A-Za-z][\w]*(?:\.[A-Za-z][\w]*)?)`")
for p in pages:
    if p["route"].endswith("capability-seams"):
        continue
    for key in CTX.findall(page_text[p["route"]]):
        if key in services or key.count(".") > 2:
            continue
        services[key] = {
            "id": f"service:{key}",
            "type": "service",
            "name": key,
            "filePath": "docs/capability-seams/mentioned",
            "summary": clip(sentence_about(page_text[p["route"]], key) or f"官方文档提及的上下文服务键 {key}。"),
            "tags": ["reference", "ctx-key", "mentioned"],
            "complexity": "mentioned",
            "owner": "", "ownerName": "", "impls": [], "consumers": [], "plugins": [],
            "doc": f"{SITE}/{p['route']}",
        }

# ---------------------------------------------------------------- 持久化事件
persist_raw = (DOCS / "persistence-catalog.zh.md").read_text(encoding="utf-8")
events = {}
for m in re.finditer(r'<a id="([^"]+)"></a>\s*\n+#### `([^`]+)` — (surface|log-only)', persist_raw):
    anchor, name, kind = m.group(1), m.group(2), m.group(3)
    chunk = persist_raw[m.end():].split("#### ")[0].split("\n### ")[0]
    js = re.search(r"```ts persistence-catalog\n(.*?)```", chunk, re.S)
    doc_text = ""
    if js:
        block = js.group(1)
        c = re.match(r"\s*/\*\*(.*?)\*/", block, re.S)
        if c:
            doc_text = clean(re.sub(r"^\s*\*?\s?", "", c.group(1), flags=re.M))
        else:
            doc_text = clip(clean(block.strip().splitlines()[0]), 120)
    src = re.search(r"来源：\[`([^`]+)`\]", chunk)
    events[name] = {
        "id": f"event:{name}",
        "type": "event",
        "name": name,
        "filePath": "docs/persistence-catalog/events",
        "summary": clip(f"{kind} 持久化会话事件。" + (f" {doc_text}" if doc_text else ""), 240),
        "tags": ["reference", "persistent-event", kind],
        "complexity": kind,
        "source": src.group(1).split(":")[0] if src else "",
        "anchor": anchor,
        "_block": js.group(1) if js else "",
        "doc": f"{SITE}/reference/persistence-catalog#{anchor}",
    }

# ---------------------------------------------------------------- 实验性记录
exp_raw = (DOCS / "experimental-persistence-catalog.zh.md").read_text(encoding="utf-8")
records = {}
for row in exp_raw.splitlines():
    if not row.startswith("| `plugin:"):
        continue
    cells = [c.strip() for c in row.strip().strip("|").split(" | ")]
    name, pkg, use = clean(cells[0]), clean(cells[1]), clean(cells[2])
    src = re.search(r"\[`([^`]+)`\]", cells[3])
    records[name] = {
        "id": f"record:{name}",
        "type": "record",
        "name": name,
        "filePath": "docs/experimental-persistence-catalog/records",
        "summary": clip(f"实验性插件记录（ignorable、仅日志）· 所属包 {pkg} · {use}", 240),
        "tags": ["reference", "plugin-record", "experimental"],
        "complexity": "log-only",
        "source": src.group(1) if src else "",
        "doc": f"{SITE}/reference/experimental-persistence-catalog",
    }

# ---------------------------------------------------------------- 实时事件
LIVE_PREFIX = (
    "turn/", "step/", "session/", "agent/", "llm/", "tool/", "tools/", "fs/",
    "telemetry/", "request/", "approval/", "plan/", "goal/", "job/", "hook/",
    "compaction/", "sandbox/", "model/", "permission/", "todo/", "team/",
    "workflow/", "deliverables/", "command/", "image/", "feedback/", "schedule/",
    "action-cards/", "agent-preset/", "developer/", "spill/", "system-prompt/",
)
LIVE = re.compile(r"`([a-z][a-z0-9-]*/[A-Za-z0-9/*.-]+)`")
live_events = {}
for p in pages:
    if p["route"].endswith("persistence-catalog"):
        continue
    text = page_text[p["route"]]
    for raw_name in LIVE.findall(text):
        name = raw_name.strip(".")
        if name in events or name in live_events or not name.startswith(LIVE_PREFIX):
            continue
        if "/" not in name or len(name) < 5 or "." in name or name.endswith((".md", ".ts", ".yml")):
            continue
        seg = name.split("/")
        if f"packages/{seg[0]}/{seg[1]}" in dir_pkg:
            continue                              # 形如 llm/llm 的包名，不是事件
        summary = sentence_about(text, name)
        if not summary or summary.startswith("|"):
            continue
        live_events[name] = {
            "id": f"event:{name}",
            "type": "event",
            "name": name,
            "filePath": "docs/reference-events/live",
            "summary": summary,
            "tags": ["reference", "live-event", "extension-point"],
            "complexity": "live",
            "source": "",
            "anchor": "",
            "doc": f"{SITE}/{p['route']}",
        }

# ---------------------------------------------------------------- 工具
tool_raw = (DOCS / "tool-catalog.zh.md").read_text(encoding="utf-8")
tool_lines = tool_raw.splitlines()
tools, cur_pkg = {}, None
for i, ln in enumerate(tool_lines):
    m = re.match(r"^## `([^`]+)`", ln)
    if m:
        cur_pkg = m.group(1)
        continue
    m = re.match(r"^### `([^`]+)`", ln)
    if not (m and cur_pkg):
        continue
    name = m.group(1)
    desc = first_para(tool_lines, i + 1)
    schema = re.search(r"```json\n(.*?)```", "\n".join(tool_lines[i:i + 500]), re.S)
    params = []
    if schema:
        try:
            params = list(json.loads(schema.group(1)).get("properties", {}).keys())
        except Exception:
            params = re.findall(r'^    "([A-Za-z_][\w]*)": \{', schema.group(1), re.M)
    group = pkg_dir.get(cur_pkg, "").split("/")
    group = group[1] if len(group) > 2 else "tools"
    tools[name] = {
        "id": f"tool:{name}",
        "type": "tool",
        "name": name,
        "filePath": f"docs/tool-catalog/{group}",
        "summary": clip(desc + (f"（参数：{', '.join(params)}）" if params else ""), 250),
        "tags": ["reference", "model-tool", cur_pkg.replace("@deepseek-ai/", "")],
        "complexity": "tool",
        "pkg": cur_pkg,
        "params": params,
        "doc": f"{SITE}/reference/tool-catalog",
    }

# ---------------------------------------------------------------- 插件配置
cfg_raw = (DOCS / "config-catalog.zh.md").read_text(encoding="utf-8")
configs, fields = {}, []
for pkg, body in re.findall(
    r"<!-- BEGIN GENERATED config-catalog:(@[^ ]+) -->(.*?)<!-- END GENERATED config-catalog:\1 -->",
    cfg_raw, re.S,
):
    inject = re.search(r"- `inject`: (.+)", body)
    refs = re.search(r"- `refs`: (.+)", body)
    src = re.search(r"- `source`: \[`([^`]+)`\]", body)
    src_path = src.group(1).split(":")[0] if src else ""
    anchor = re.search(r'<a id="([^"]+)"></a>', body)
    ts = re.search(r"```ts config-catalog\n(.*?)```", body, re.S)
    iface, fl = "", []
    if ts:
        text = ts.group(1)
        m = re.search(r"(?:export )?(?:interface|type) (\w+)(?: extends [^{]+)?(?: =)? \{", text)
        iface = m.group(1) if m else ""
        doc_buf = []
        for ln in text.splitlines():
            stripped = ln.strip()
            if stripped.startswith("/**"):
                doc_buf = [stripped.lstrip("/**").rstrip("*/").strip()]
                continue
            if doc_buf and stripped.startswith("*"):
                doc_buf.append(stripped.lstrip("*").strip())
                continue
            m = re.match(r"^  ([A-Za-z_$][\w$]*)(\??):\s*(.+?)\s*$", ln)
            if m:
                doc = clean(" ".join(x for x in doc_buf if x))
                doc_buf = []
                fl.append((m.group(1), m.group(2) or "", m.group(3), doc))
                continue
            if stripped and not stripped.startswith(("*", "//")):
                doc_buf = []
    grp = "misc"
    if src_path.startswith("packages/"):
        grp = src_path.split("/")[1]
    short = pkg.replace("@deepseek-ai/", "")
    configs[pkg] = {
        "id": f"plugin-config:{pkg}",
        "type": "config-schema",
        "name": pkg,
        "filePath": f"docs/config-catalog/{grp}",
        "summary": clip(
            "插件配置声明"
            + (f" · inject {clean(inject.group(1))}" if inject else "")
            + (f" · {len(fl)} 个顶层字段" if fl else "")
            + (f" · {iface}" if iface else "")
        , 230),
        "tags": ["reference", "config-catalog", short, grp],
        "complexity": "config",
        "source": src_path,
        "inject": clean(inject.group(1)) if inject else "",
        "refs": clean(refs.group(1)) if refs else "",
        "fields": [f[0] for f in fl],
        "doc": f"{SITE}/reference/config-catalog" + (f"#{anchor.group(1)}" if anchor else ""),
    }
    for fname, opt, ftype, doc in fl:
        fields.append({
            "id": f"plugin-config:{pkg}#{fname}",
            "type": "config-field",
            "name": f"{short}.{fname}",
            "filePath": f"docs/config-catalog/{grp}",
            "summary": clip(f"`{fname}{opt}: {ftype}`" + (f" — {doc}" if doc else ""), 230),
            "tags": ["reference", "config-field", short],
            "complexity": "field",
            "parent": f"plugin-config:{pkg}",
            "doc": f"{SITE}/reference/config-catalog",
        })

# ---------------------------------------------------------------- 已解析持久化类型
type_chapter = persist_raw[persist_raw.index("## 已解析的持久化类型"):]
ptypes = {}
raw_blocks = re.split(r"\n(?=### )", type_chapter)
for blk in raw_blocks[1:]:
    m = re.match(r'### `([^`]+)`\s*\n+SHA-256: `([0-9a-f]+)`', blk)
    if not m:
        continue
    name, sha = m.group(1), m.group(2)
    if name.startswith('"') or re.fullmatch(r"[\d\s|&.()\[\]]+", name):
        continue                                    # 字面量联合分支不是类型
    lines = [l.strip() for l in blk[m.end():].splitlines()]
    body, rows = "", []
    for l in lines:
        if not l or l.startswith(("来源", "<a id")):
            continue
        if l.startswith("|---"):
            rows = []                       # 表头之后开始收集属性行
            continue
        if l.startswith("|"):
            cells = [x.strip() for x in l.strip("|").split("|")]
            if cells and cells[0] == "属性":
                continue
            rows.append("/".join(c.strip("` ") for c in cells[:3]))
            continue
        if rows:
            break
        body = l
        break
    if rows:
        body = f"{len(rows)} 个属性：" + "、".join(rows[:6]) + ("…" if len(rows) > 6 else "")
    anchor = re.search(r'id="(persistence-type-sha256-[0-9a-f]+)"', blk)
    ptypes[name] = {
        "id": f"ptype:{name}",
        "type": "ptype",
        "name": name,
        "filePath": "docs/persistence-catalog/types",
        "summary": clip(f"持久化类型 `{name}` · SHA-256 {sha[:12]}… · {clean(body)}", 230),
        "tags": ["reference", "persistence-type", "schema"],
        "complexity": "type",
        "sha": sha,
        "doc": f"{SITE}/reference/persistence-catalog"
        + (f"#{anchor.group(1)}" if anchor else ""),
    }

# ---------------------------------------------------------------- 节点汇总
new_nodes = pages + sections + list(services.values()) + list(events.values()) + \
    list(live_events.values()) + list(records.values()) + list(tools.values()) + \
    list(configs.values()) + fields + list(ptypes.values())

# ---------------------------------------------------------------- 装边
kg = json.loads((UA / "knowledge-graph.json").read_text(encoding="utf-8"))
old_prefixes = ("doc:reference/", "docsec:reference/", "service:", "event:", "record:",
                "tool:", "plugin-config:", "ptype:")

kg["nodes"] = [n for n in kg["nodes"] if not n["id"].startswith(old_prefixes)]
base_ids = {n["id"] for n in kg["nodes"]}
kg["edges"] = [e for e in kg["edges"] if e["source"] in base_ids and e["target"] in base_ids]
kept_ids = base_ids | {n["id"] for n in new_nodes}
kg["edges"] = [e for e in kg["edges"] if e["source"] in kept_ids and e["target"] in kept_ids]
kg["layers"] = [l for l in kg["layers"] if l["id"] != "layer:reference-docs"]
kg["tour"] = [s for s in kg["tour"] if not s.get("referenceAtlas")]

dir_nodes = defaultdict(list)
for n in kg["nodes"]:
    fp = n.get("filePath", "")
    seg = fp.split("/")
    if seg[0] == "packages" and len(seg) >= 3:
        dir_nodes["/".join(seg[:3])].append(n)
    elif seg[0] == "apps" and len(seg) >= 2:
        dir_nodes["/".join(seg[:2])].append(n)


def index_of(d):
    cands = [n for n in dir_nodes.get(d, []) if n["type"] in ("file", "config")]
    if not cands:
        return None
    pref = [n for n in cands if re.search(r"src/index\.[tj]sx?$", n["filePath"])]
    pool = pref or cands
    return max(pool, key=lambda n: len(n.get("summary", "")))["id"]


edges, seen = [], {(e["source"], e["target"], e["type"]) for e in kg["edges"]}


def add_edge(s, t, typ, w=1):
    if not s or not t or s == t or s not in kept_ids or t not in kept_ids:
        return
    k = (s, t, typ)
    if k in seen:
        return
    seen.add(k)
    edges.append({"source": s, "target": t, "type": typ, "direction": "forward", "weight": w})


for s in sections:
    add_edge(s["page"], s["id"], "contains")

ENTITY_BY_PAGE = {
    "reference/capability-seams": list(services.values()),
    "reference/config-catalog": list(configs.values()) + fields,
    "reference/tool-catalog": list(tools.values()),
    "reference/persistence-catalog": list(events.values()),
    "reference/experimental-persistence-catalog": list(records.values()),
}
for route, ents in ENTITY_BY_PAGE.items():
    for e in ents:
        add_edge(f"doc:{route}", e["id"], "documents")

by_name_ctx = {k: v["id"] for k, v in services.items()}
by_name_event = {**{k: v["id"] for k, v in events.items()},
                 **{k: v["id"] for k, v in live_events.items()}}
tool_tokens = sorted(tools, key=len, reverse=True)
for s in sections:
    body = s.get("_body", "")
    if not body:
        continue
    hit = 0
    for key, sid in by_name_ctx.items():
        if hit >= 4:
            break
        if f"`{key}`" in body:
            add_edge(s["id"], sid, "documents")
            hit += 1
    for name, eid in by_name_event.items():
        if hit >= 8:
            break
        if f"`{name}`" in body:
            add_edge(s["id"], eid, "documents")
            hit += 1
    for tname in tool_tokens:
        if hit >= 10:
            break
        if re.search(rf"`{re.escape(tname)}[`(]", body):
            add_edge(s["id"], tools[tname]["id"], "documents")
            hit += 1

for key, svc in services.items():
    add_edge(index_of(svc["owner"]), svc["id"], "declares", 2)
    for d in svc["impls"]:
        add_edge(index_of(d), svc["id"], "implements", 2)
    for d in svc["consumers"]:
        add_edge(index_of(d), svc["id"], "consumes")

for t in tools.values():
    add_edge(index_of(pkg_dir.get(t["pkg"], "")), t["id"], "provides", 2)
for c in configs.values():
    add_edge(index_of(pkg_dir.get(c["name"], "")), c["id"], "declares", 2)
for f in fields:
    add_edge(f["parent"], f["id"], "contains")

by_file = {}
for n in kg["nodes"]:
    if n["type"] in ("file", "config", "document") and n.get("filePath"):
        by_file.setdefault(n["filePath"], n["id"])
for e in list(events.values()) + list(records.values()):
    src = by_file.get(e.get("source", ""))
    if src:
        add_edge(src, e["id"], "emits", 2)

for name, t in ptypes.items():
    add_edge("doc:reference/persistence-catalog", t["id"], "documents")

_type_pat = re.compile(
    r"(?<![\w$])(" + "|".join(map(re.escape, sorted(ptypes, key=len, reverse=True))) + r")(?![\w$])")
for ev in events.values():
    for hit in set(_type_pat.findall(ev.get("_block", ""))):
        add_edge(ev["id"], ptypes[hit]["id"], "references")

for p in pages:
    stem = p["route"].rsplit("/", 1)[-1]
    if stem == "index":
        continue
    hits = [d for d in dir_nodes if d.rsplit("/", 1)[-1] in (stem, f"{stem}-{stem}")]
    if not hits:
        continue
    best = max(hits, key=lambda d: len(dir_nodes[d]))
    add_edge(p["id"], index_of(best), "documents", 2)

route_of_file = {rel_file(stem): route for stem, route, _ in PAGES}
for p in pages:
    for r in re.findall(r"\]\(([^)]+\.md)(?:#[^)]*)?\)", page_text[p["route"]])[:8]:
        target = r.split("#")[0].split("/")[-1]
        for f, route in route_of_file.items():
            if f.split("/")[-1] == target or f == "docs/" + r.split("#")[0]:
                add_edge(p["id"], f"doc:{route}", "related")
                break

stats = {
    "pages": len(pages), "sections": len(sections), "services": len(services),
    "events_persist": len(events), "events_live": len(live_events), "records": len(records),
    "tools": len(tools), "configs": len(configs), "fields": len(fields),
    "ptypes": len(ptypes),
    "new_nodes": len(new_nodes), "new_edges": len(edges),
    "services_by_role": dict(Counter(s["complexity"] for s in services.values())),
}
print(json.dumps(stats, ensure_ascii=False))

if DRY:
    print("\n-- sections per page (top 12) --")
    for k, v in Counter(s["page"] for s in sections).most_common(12):
        print("  ", k, v)
    print("\n-- live events:", ", ".join(list(live_events)))
    print("\n-- sections with no summary:", sum(1 for s in sections if len(s["summary"]) < 10))
    print("-- empty node summary:", sum(1 for n in new_nodes if len(n["summary"]) < 10))
    print("-- edge types:", Counter(e["type"] for e in edges))
    print("-- sample edges:")
    for e in edges[:8]:
        print("  ", e["source"], "-", e["type"], "->", e["target"])
    sys.exit(0)

for n in new_nodes:
    for k in [k for k in n if k.startswith("_")]:
        n.pop(k)

# ---------------------------------------------------------------- 写入
layer = {
    "id": "layer:reference-docs",
    "name": "官方参考文档层（reference/*）",
    "description": (
        "官方 reference 站点全部 69 页的可检索投影：6 篇概念页（架构总览、Cordis 入门、能力 seams、"
        "Agent 生命周期、工具流水线、API Gateway）、4 份生成式目录（插件配置、工具 schema、"
        "持久化事件、实验性记录）、Cordis Core API 6 页、Cookbook 6 篇与 47 篇子系统页。"
        "页面与章节节点还原文档骨架；服务 / 事件 / 工具 / 配置节点把正文里的具名条目抽成可连接实体，"
        "再与代码侧的包、声明文件互连，因此既可按文档导航，也可从代码跳到对应章节。"
    ),
    "doc": f"{SITE}/reference/",
    "docTitle": "架构总览",
    "nodeIds": [n["id"] for n in new_nodes],
}
kg["nodes"].extend(new_nodes)
kg["edges"].extend(edges)
kg["layers"].append(layer)

step = {
    "order": 16,
    "title": "官方参考文档层：文档拆成可连接的实体",
    "description": (
        "第 16 步进入新增的「官方参考文档层」：reference 站点的 69 页被拆成三层结构——页面、章节（H2/H3）、"
        "以及正文中的具名实体。实体分五类：服务键 ctx.*（取自能力 seams 表，带角色 service/core/seam/bundle、"
        "所属包、实现包与消费方，三角关系直接变成 declares / implements / consumes 三条边）、持久化事件"
        "（surface 与 log-only 两类，带声明文件与 JSDoc）、实时扩展点事件（agent/*、tools/*、fs/* 等，不进日志）、"
        "模型工具（含参数名，来自工具目录）、插件配置声明与顶层字段（来自配置目录）。每个实体都连回代码位置："
        "服务的所属包、工具的插件包、事件的声明文件。所以这张图有两个入口——按文档读（页面→章节→条目），"
        "或按代码找（包→服务→官方说明）。实验性插件记录（plugin:*）也在这一层，它们只进日志、不进已知事件集合。"
    ),
    "nodeIds": [
        "doc:reference/index",
        "doc:reference/capability-seams",
        "service:ctx.sessions",
        "service:ctx.tools",
        "service:ctx.subagents",
        "doc:reference/config-catalog",
        "plugin-config:@deepseek-ai/dsh-acp",
        "doc:reference/tool-catalog",
        "doc:reference/persistence-catalog",
        "event:turn/start",
        "event:tool/result",
        "doc:reference/subsystems/session",
        "doc:reference/cookbook/adding-a-tool",
    ],
    "doc": f"{SITE}/reference/",
    "docTitle": "架构总览",
    "referenceAtlas": True,
}
kg["tour"].append(step)
kg["project"]["scope"] = (
    "核心运行时与插件生态（已排除 UI 层：packages/client、packages/experimental、apps/web、apps/desktop）。"
    "官方 reference 站点的 69 页文档已全量投影为「官方参考文档层」：页面 / 章节 / 服务 / 事件 / 工具 / 配置实体，"
    "并与代码侧的包、声明文件互连；未发布的 subsystems 页（mcp、forge 等）与仓库内其他 docs 不在该层。"
)

(UA / "knowledge-graph.json").write_text(
    json.dumps(kg, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
print(f"nodes={len(kg['nodes'])} edges={len(kg['edges'])} layers={len(kg['layers'])} tour={len(kg['tour'])}")
