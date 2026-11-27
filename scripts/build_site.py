#!/usr/bin/env python3
"""构建 DSH 知识图谱网站（kg.agidsh.com）。

产物 .ua/site/：
  index.html       知识图谱首页（由 dashboard HTML 注入站点导航与文档链接）
  docs/            69 页静态文档站，标题带真实 id 锚点
  assets/          站点样式
  data/            图谱数据（供文档页「在图谱中查看」使用）

设计要点：
  - 文档站每页自动生成 H2/H3 锚点 id（与 docsec 节点的 #anchor 对齐）
  - 交互面板的「原网页 ↗」与悬浮卡片锚点指向站内文档页，彻底解决锚点失效
  - 全站静态、零 CDN、可离线预览
"""
import html
import json
import re
import shutil
from pathlib import Path

UA = Path(__file__).resolve().parent
SITE = UA / "site"
DOCS = SITE / "docs"
ASSETS = SITE / "assets"
SITE_BASE = "https://deepseek-harness.github.io/deepseek-harness"
KG_ORIGIN = "https://kg.agidsh.com"


def slug(text: str) -> str:
    """生成与官网一致的标题锚点（保留中文、空格转连字符）。"""
    s = re.sub(r"[`*_\[\]()]", "", text)
    s = re.sub(r"\s+", "-", s.strip())
    s = re.sub(r"-+", "-", s)
    return s


def md_to_html(md: str, anchors=None):
    """Markdown → HTML，标题带可定位 id。anchors: {标题文本小写: [官网锚点, ...]}。"""
    anchors = anchors or {}
    lines = md.split("\n")
    out, toc, in_code, code = [], [], False, []
    list_type, table = None, None

    def inline(s):
        s = html.escape(s, quote=False)
        # 保留源文档里的锚点 <a id="..."></a> 作为真实 HTML（不转义）
        s = re.sub(r'&lt;a\s+id="([^"&]+)"&gt;&lt;/a&gt;',
                   r'<a id="\1" class="anch"></a>', s)
        s = re.sub(r"`([^`]+)`", r"<code>\1</code>", s)
        s = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", s)
        s = re.sub(r"\[([^\]]+)\]\(([^)]+)\)",
                   lambda m: f'<a href="{html.escape(m.group(2), quote=True)}">{m.group(1)}</a>', s)
        return s

    def flush_list():
        nonlocal list_type
        if list_type:
            out.append(f"</{list_type}>")
            list_type = None

    def flush_table():
        nonlocal table
        if table:
            head = table[0] if table else []
            rows = table[1:]
            if head and rows and re.fullmatch(r"[\s:|-]+", "|".join(rows[0]) or "x"):
                rows = rows[1:]
                out.append("<table><thead><tr>" + "".join(f"<th>{inline(c)}</th>" for c in head)
                           + "</tr></thead><tbody>"
                           + "".join("<tr>" + "".join(f"<td>{inline(r[i] if i < len(r) else '')}</td>"
                                                       for i in range(len(head))) + "</tr>" for r in rows)
                           + "</tbody></table>")
            else:
                out.append("<p>" + "<br>".join(inline(" · ".join(r)) for r in table) + "</p>")
            table = None

    for raw in lines:
        ln = raw.rstrip()
        if ln.startswith("```"):
            if in_code:
                out.append("<pre><code>" + html.escape("\n".join(code)) + "</code></pre>")
                code, in_code = [], False
            else:
                flush_list(); flush_table(); in_code = True
            continue
        if in_code:
            code.append(raw); continue
        if ln.startswith("|") and ln.endswith("|"):
            flush_list()
            cells = [c.strip() for c in ln[1:-1].split("|")]
            if table is None:
                table = []
            table.append(cells)
            continue
        flush_table()
        m = re.match(r"^(#{1,6})\s+(.*)$", ln)
        if m:
            flush_list()
            lv = len(m.group(1))
            title = re.sub(r"[`*_]", "", m.group(2)).strip()
            anchor = slug(title)
            # 官网 docsec 的 name 与标题文本可能不完全一致，用包含关系宽松匹配
            extra = []
            for key, vals in anchors.items():
                if key and (key in title.lower() or title.lower() in key):
                    extra.extend(vals)
            extra = list(dict.fromkeys(a for a in extra if a != anchor))
            # 主 id 给 slug；官网锚点用空 span 承载，保证 #old-anchor 也能精确定位
            spans = "".join(f'<span id="{html.escape(a, quote=True)}" class="anch"></span>' for a in extra)
            out.append(f'<h{lv} id="{html.escape(anchor, quote=True)}">{spans}{inline(m.group(2))}</h{lv}>')
            if lv in (2, 3):
                toc.append((lv, title, anchor))
            continue
        if re.match(r"^\s*[-*+]\s+", ln):
            if list_type != "ul":
                flush_list(); out.append("<ul>"); list_type = "ul"
            out.append("<li>" + inline(re.sub(r"^\s*[-*+]\s+", "", ln)) + "</li>")
            continue
        if re.match(r"^\s*\d+\.\s+", ln):
            if list_type != "ol":
                flush_list(); out.append("<ol>"); list_type = "ol"
            out.append("<li>" + inline(re.sub(r"^\s*\d+\.\s+", "", ln)) + "</li>")
            continue
        if ln.startswith(">"):
            flush_list()
            out.append("<blockquote>" + inline(ln.lstrip("> ")) + "</blockquote>")
            continue
        if not ln.strip():
            flush_list(); continue
        flush_list()
        out.append("<p>" + inline(ln) + "</p>")
    flush_list(); flush_table()
    if in_code and code:
        out.append("<pre><code>" + html.escape("\n".join(code)) + "</code></pre>")
    return "\n".join(out), toc


DOC_HTML = """<!doctype html>
<html lang="zh-CN"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{title} · DSH 知识图谱文档站</title>
<link rel="stylesheet" href="/assets/site.css">
</head><body>
<header class="top">
  <a class="brand" href="/">DSH 知识图谱</a>
  <nav><a href="/">图谱首页</a><a href="/docs/">文档站</a><a href="{github}" target="_blank">GitHub ↗</a></nav>
</header>
<div class="wrap">
  <aside class="side">
    <div class="side-h">本页目录</div>
    <nav class="toc">{toc}</nav>
  </aside>
  <main class="doc">
    <div class="crumb"><a href="/docs/">文档站</a> / {title}</div>
    <h1>{title}</h1>
    <div class="meta">分组：{group} · 本地副本：{file}</div>
    <div class="body">{body}</div>
    <div class="back"><a href="/?focus={route}">← 返回图谱并聚焦该文档</a></div>
  </main>
</div>
<script>
// 锚点：用原生 id 定位；哈希变化时补一次滚动，兼容静态托管
function jump(){{
  const id = decodeURIComponent(location.hash.slice(1));
  if(!id) return;
  let el = document.getElementById(id);
  if(!el){{
    const cands = [...document.querySelectorAll('[id]')];
    el = cands.find(x => x.id.toLowerCase() === id.toLowerCase());
  }}
  if(el) requestAnimationFrame(()=>el.scrollIntoView({{block:'start'}}));
}}
addEventListener('hashchange', jump); addEventListener('load', jump);
</script>
</body></html>"""


def main():
    # 覆盖写而非删除目录（安全策略禁止递归删除）
    SITE.mkdir(parents=True, exist_ok=True)
    DOCS.mkdir(parents=True, exist_ok=True)
    ASSETS.mkdir(parents=True, exist_ok=True)

    payload = json.loads((UA / "doc-payload.json").read_text(encoding="utf-8"))
    kg = json.loads((UA / "knowledge-graph.json").read_text(encoding="utf-8"))

    # 官网锚点映射：所有带 #anchor 的节点 name → #anchor，用于站内精确定位
    # 覆盖 doc-section(210) / ptype(412) / config-schema(181) / event(65)
    anchor_map = {}
    for n in kg["nodes"]:
        if not (n.get("doc") and "#" in n["doc"]):
            continue
        title = re.sub(r"[`*_]", "", n.get("name", "")).strip().lower()
        if not title:
            continue
        page = n.get("page")
        if not page:
            # ptype / config-schema 等无 page 字段：从 doc URL 的 route 推导
            m = re.search(r"/reference/([^#]+?)/?(?:#|$)", n["doc"])
            if m:
                page = "doc:reference/" + m.group(1).rstrip("/")
        if not page:
            continue
        anchor_map.setdefault(page, {}).setdefault(title, []).append(n["doc"].split("#", 1)[1])

    # 文档页（页面内锚点由 md_to_html 的 dict.fromkeys 去重）
    for route, d in payload.items():
        body, toc = md_to_html(d["md"], anchor_map.get(f"doc:{route}", {}))
        github_url = "https://github.com/deepseek-ai/deepseek-harness"
        toc_html = "".join(
            f'<a class="t{t[0]}" href="#{html.escape(t[2], quote=True)}">{html.escape(t[1])}</a>'
            for t in toc)
        page = DOC_HTML.format(
            title=html.escape(d["title"]), group=html.escape(d["group"]),
            file=html.escape(d["file"]), body=body, toc=toc_html or '<span class="none">无章节</span>',
            route=html.escape(route, quote=True), github=html.escape(github_url, quote=True))
        rel = route.replace("reference/", "", 1) + ".html"
        dest = DOCS / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(page, encoding="utf-8")

    # 文档站首页
    groups = {}
    for route, d in payload.items():
        groups.setdefault(d["group"], []).append((route, d))
    idx = ['<!doctype html><html lang="zh-CN"><head><meta charset="utf-8">',
           '<meta name="viewport" content="width=device-width,initial-scale=1">',
           '<title>文档站 · DSH 知识图谱</title><link rel="stylesheet" href="/assets/site.css"></head><body>',
           '<header class="top"><a class="brand" href="/">DSH 知识图谱</a><nav>',
           '<a href="/">图谱首页</a><a href="/docs/">文档站</a></nav></header>',
           '<div class="wrap"><main class="doc"><h1>官方参考文档站</h1>',
           '<p>共 69 页官方文档，标题带可点击锚点，支持浏览器前进后退与精确跳转。</p>']
    for g, items in groups.items():
        idx.append(f'<h2 id="{html.escape(slug(g))}">{html.escape(g)} <small>{len(items)} 页</small></h2><ul>')
        for route, d in sorted(items):
            rel = route.replace("reference/", "", 1) + ".html"
            idx.append(f'<li><a href="/docs/{html.escape(rel, quote=True)}">{html.escape(d["title"])}</a>'
                       f'<span class="rp">{html.escape(route)}</span></li>')
        idx.append("</ul>")
    idx.append("</main></div></body></html>")
    (DOCS / "index.html").write_text("".join(idx), encoding="utf-8")

    # 站点样式
    (ASSETS / "site.css").write_text("""\
*{box-sizing:border-box}
body{margin:0;background:#0d1117;color:#c9d1d9;font-family:-apple-system,"Noto Sans SC","Microsoft YaHei",sans-serif;font-size:14px;line-height:1.75}
a{color:#58a6ff;text-decoration:none}a:hover{text-decoration:underline}
.top{height:52px;display:flex;align-items:center;gap:22px;padding:0 22px;border-bottom:1px solid #26313f;background:#111823;position:sticky;top:0;z-index:10}
.top .brand{font-weight:700;color:#e6edf3;font-size:15px}
.top nav{display:flex;gap:16px;margin-left:auto;font-size:13px}
.wrap{display:flex;max-width:1360px;margin:0 auto;padding:22px;gap:24px}
.side{width:238px;flex:0 0 238px;position:sticky;top:74px;align-self:flex-start;max-height:calc(100vh - 94px);overflow:auto;border-right:1px solid #26313f;padding-right:14px}
.side-h{font-size:11px;color:#7d8590;text-transform:uppercase;letter-spacing:.8px;margin-bottom:10px}
.toc{display:flex;flex-direction:column;gap:3px}
.toc a{font-size:12px;color:#9aa7b4;padding:3px 6px;border-radius:4px;display:block;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.toc a:hover{background:#1b2430;color:#cfe6ff;text-decoration:none}
.toc a.t3{padding-left:18px;color:#7f8c99}
.doc{flex:1;min-width:0;max-width:920px}
.crumb{font-size:12px;color:#7d8590;margin-bottom:10px}
.meta{font-size:11px;color:#7d8590;border-bottom:1px solid #26313f;padding-bottom:12px;margin-bottom:18px}
h1{font-size:25px;color:#e6edf3;margin:6px 0 14px}
h2{font-size:19px;color:#e6edf3;margin:28px 0 10px;border-bottom:1px solid #26313f;padding-bottom:6px}
h3{font-size:16px;color:#d6e2ee;margin:22px 0 8px}
h4{font-size:14px;color:#b9c6d3;margin:18px 0 6px}
.body p{margin:9px 0}.body ul,.body ol{padding-left:22px}.body li{margin:3px 0}
code{background:#1b2430;color:#a9d3f5;border-radius:3px;padding:1px 5px;font-size:12.5px}
pre{background:#080e15;border:1px solid #26313f;border-radius:7px;padding:12px 14px;overflow:auto}
pre code{background:none;padding:0;color:#b9c9d8;font-size:12px}
table{border-collapse:collapse;width:100%;margin:12px 0;font-size:12.5px;display:block;overflow:auto}
th,td{border:1px solid #303b4a;padding:6px 9px;text-align:left;vertical-align:top}
th{background:#182231;color:#e6edf3}
blockquote{margin:12px 0;padding:6px 12px;border-left:3px solid #3b6b96;background:#121c28;color:#9aa7b4}
.back{margin-top:36px;border-top:1px solid #26313f;padding-top:16px}
small{color:#7d8590;font-weight:400;font-size:12px}
.rp{color:#5c6774;font-size:11px;margin-left:12px}
.none{color:#5c6774;font-size:12px}
@media(max-width:860px){.side{display:none}.wrap{padding:14px}}
""", encoding="utf-8")

    # 首页：复制面板，注入站点导航（锚点链接改为站内文档站）
    dash = (UA / "dashboard" / "deepseek-harness-knowledge-graph.html").read_text(encoding="utf-8")
    # 把 payload 中的原网页链接改为官方镜像路径（与官网路径一致，VitePress SPA 才能正确路由）
    for route in payload:
        dash = dash.replace(f'"url":"{SITE_BASE}/{route}"',
                            f'"url":"/deepseek-harness/{route.strip("/")}"')
    # 注入顶部导航样式与条
    nav_css = """\
<style>
.kg-nav{position:absolute;top:54px;right:14px;z-index:5;display:flex;gap:8px;
  background:#0d1117;border:1px solid #2b3d52;border-radius:8px;padding:5px 7px;
  box-shadow:0 6px 22px rgba(0,0,0,.6)}
.kg-nav a{color:#9dc0e0;background:#16202c;border:1px solid #35506b;border-radius:6px;
  padding:4px 10px;font-size:11px;text-decoration:none;line-height:1.2}
.kg-nav a:hover{background:#1d2c3d;color:#d6e8fa;border-color:#4d6f92}
</style>"""
    dash = dash.replace("</head>", nav_css + "</head>")
    dash = dash.replace("<main>", '<main><div class="kg-nav"><a href="/deepseek-harness/reference/">文档站</a>'
                        '<a href="https://github.com/deepseek-ai/deepseek-harness" target="_blank">GitHub ↗</a></div>')
    (SITE / "index.html").write_text(dash, encoding="utf-8")

    print(f"site -> {SITE}")
    print(f"  pages={len(payload)} html={len(list(DOCS.rglob('*.html')))}")
    print(f"  index={(SITE / 'index.html').stat().st_size/1048576:.2f} MB")


if __name__ == "__main__":
    main()
