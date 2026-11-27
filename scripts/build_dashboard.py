#!/usr/bin/env python3
"""把布局数据 + 导览注入模板，产出单文件离线 Dashboard。"""
import json
from collections import Counter
from pathlib import Path

UA = Path(__file__).resolve().parent
layout = json.loads((UA / "intermediate" / "layout-file-level.json").read_text(encoding="utf-8"))
kg = json.loads((UA / "knowledge-graph.json").read_text(encoding="utf-8"))

tour = []
for s in kg["tour"]:
    item = {
        "order": s["order"],
        "title": s["title"],
        "description": s["description"],
        "nodeIds": s["nodeIds"],
    }
    if s.get("languageLesson"):
        item["languageLesson"] = s["languageLesson"]
    if s.get("doc"):
        item["doc"] = s["doc"]
        item["docTitle"] = s.get("docTitle") or "官方文档"
    tour.append(item)

doc_payload = json.loads((UA / "doc-payload.json").read_text(encoding="utf-8"))

data = {
    "docs": doc_payload,
    "nodes": layout["nodes"],
    "edges": layout["edges"],
    "layers": [{"id": l["id"], "name": l["name"], "description": l["description"],
                "doc": l.get("doc"), "docTitle": l.get("docTitle"),
                "nodeIds": l["nodeIds"]} for l in kg["layers"]],
    "tour": tour,
    "clusters": layout.get("clusters", []),
    # 图谱全量口径：画布只渲染文件级实体，统计需反映真正的收录规模
    "meta": {
        "allNodes": len(kg["nodes"]),
        "allEdges": len(kg["edges"]),
        "canvasNodes": len(layout["nodes"]),
        "canvasEdges": len(layout["edges"]),
        "byType": dict(Counter(n["type"] for n in kg["nodes"])),
    },
}

tpl = (UA / "dashboard_template.html").read_text(encoding="utf-8")
app = (UA / "dashboard_app.js").read_text(encoding="utf-8")

html = tpl.replace("/*__DATA__*/", json.dumps(data, ensure_ascii=False, separators=(",", ":")))
html = html.replace("/*__V2__*/", app)

out = UA / "dashboard" / "deepseek-harness-knowledge-graph.html"
out.parent.mkdir(parents=True, exist_ok=True)
out.write_text(html, encoding="utf-8")
print(f"dashboard -> {out}  ({out.stat().st_size/1048576:.2f} MB)")
print(f"nodes={len(data['nodes'])} edges={len(data['edges'])} layers={len(data['layers'])} tour={len(data['tour'])}")
