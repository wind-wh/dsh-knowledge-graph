#!/usr/bin/env python3
"""deepseek-harness 知识图谱 · 文件级布局（分层簇团 + 圆盘打包）

1) 按包聚合为簇，簇按架构层排序；
2) 簇内节点按度数做向日葵（phyllotaxis）排布 —— 均匀、无重叠；
3) 簇按圆盘打包（贪心螺线搜索）摆放到画布，保证簇与簇不交叠；
4) 整体归一化。
"""
import json, math, sys
from collections import Counter
from pathlib import Path

UA = Path(__file__).resolve().parent
kg = json.loads((UA / "knowledge-graph.json").read_text(encoding="utf-8"))
OUT = UA / "intermediate" / "layout-file-level.json"

FILE_TYPES = ("file", "config", "document", "service", "pipeline",
              "doc-section", "config-schema", "config-field", "ptype",
              "event", "tool", "record")
nodes = [n for n in kg["nodes"] if n["type"] in FILE_TYPES]
idx = {n["id"]: i for i, n in enumerate(nodes)}
N = len(nodes)

layer_of, layer_rank = {}, {}
for k, lay in enumerate(kg["layers"]):
    layer_rank[lay["id"]] = k
    for nid in lay["nodeIds"]:
        layer_of[nid] = lay["id"]

edges, seen = [], set()
for e in kg["edges"]:
    s, t = e["source"], e["target"]
    if s in idx and t in idx and s != t:
        key = (min(s, t), max(s, t), e["type"])
        if key in seen:
            continue
        seen.add(key)
        edges.append({"s": idx[s], "t": idx[t], "type": e["type"]})

deg = [0] * N
for e in edges:
    deg[e["s"]] += 1
    deg[e["t"]] += 1


def cluster_key(p):
    seg = p.split("/")
    if seg[0] == "docs":
        # 文档层：一页一簇；生成式目录的实体路径（docs/<page>/<组>）按组再拆
        s = p[:-6] if p.endswith(".zh.md") else p
        parts = s.split("/")
        return "/".join(parts[:3]) if len(parts) >= 3 else s
    if seg[0] == "packages" and len(seg) > 2:
        return "/".join(seg[:2])
    if seg[0] == "apps" and len(seg) > 1:
        return "/".join(seg[:2])
    return seg[0]


groups = {}
for i, n in enumerate(nodes):
    groups.setdefault(cluster_key(n["filePath"]), []).append(i)

c_layer = {}
for c, mem in groups.items():
    c_layer[c] = Counter(layer_of.get(nodes[i]["id"], "") for i in mem).most_common(1)[0][0]

# 根目录散文件合并成一个虚拟簇，避免四周零散噪声
ROOT_FILES = [c for c in groups if "/" not in c]
if len(ROOT_FILES) > 1:
    merged = []
    for c in ROOT_FILES:
        merged.extend(groups.pop(c))
    groups["(root)"] = merged
    c_layer["(root)"] = layer_rank and Counter(layer_of.get(nodes[i]["id"], "") for i in merged).most_common(1)[0][0]

# 簇内半径：留出节点半径与标签空间
def node_r(d):
    # 与前端渲染半径口径保持一致（世界坐标下），上限 11 避免巨型枢纽
    return min(3.2 + 2.6 * math.log1p(d), 11.0)

DOC_SCALE = 0.66          # 文档岛整体收紧：参考材料占更少画布
cluster_radius = {}
for c, mem in groups.items():
    rr = max((node_r(deg[i]) for i in mem), default=6)
    n = len(mem)
    f = DOC_SCALE if c.startswith("docs/") else 1.0
    cluster_radius[c] = ((max(2.6 * rr, 16) * math.sqrt(n)) + 34) * f

# 打包顺序：层优先，其次簇规模降序；文档层单独成岛，不与代码簇混排
order = sorted(groups, key=lambda c: (layer_rank.get(c_layer[c], 99), -len(groups[c])))
code_order = [c for c in order if not c.startswith("docs/")]
doc_order = [c for c in order if c.startswith("docs/")]


def spiral_pack(names):
    """阿基米德螺线贪心打包，返回 {簇: 中心}。"""
    out, placed = {}, []
    for c in names:
        R = cluster_radius[c]
        if not placed:
            x, y = 0.0, 0.0
        else:
            best, t = None, 0.0
            while t < 9000:
                rad = 12 + 9.5 * t
                ang = t * 0.62
                x, y = rad * math.cos(ang), rad * math.sin(ang)
                ok = True
                for (px, py, pr) in placed:
                    if math.hypot(x - px, y - py) < (R + pr + 26):
                        ok = False
                        break
                if ok:
                    best = (x, y)
                    break
                t += 0.35
            x, y = best if best else (0.0, 0.0)
        out[c] = (x, y)
        placed.append((x, y, R))
    return out


centers = spiral_pack(code_order)
if doc_order:
    doc_centers = spiral_pack(doc_order)

    def bbox(cs):
        xs = [cs[c][0] for c in cs]
        ys = [cs[c][1] for c in cs]
        rs = [cluster_radius[c] for c in cs]
        return (min(x - r for x, r in zip(xs, rs)), max(x + r for x, r in zip(xs, rs)),
                min(y - r for y, r in zip(ys, rs)), max(y + r for y, r in zip(ys, rs)))

    cminx, cmaxx, cminy, cmaxy = bbox(centers)
    dminx, dmaxx, dminy, dmaxy = bbox(doc_centers)
    gap = 260
    dx = cmaxx + gap - dminx
    dy = (cminy + cmaxy) / 2 - (dminy + dmaxy) / 2
    for c, (x, y) in doc_centers.items():
        centers[c] = (x + dx, y + dy)

# 簇内向日葵排布
pos = [None] * N
GOLD = math.pi * (3 - math.sqrt(5))
for c, mem in groups.items():
    mem.sort(key=lambda i: -deg[i])
    cx, cy = centers[c]
    n = len(mem)
    rr = max((node_r(deg[i]) for i in mem), default=6)
    spacing = max(3.0 * rr, 30.0) * (DOC_SCALE if c.startswith("docs/") else 1.0)
    for k, i in enumerate(mem):
        rad = spacing * math.sqrt(k + 0.55)
        ang = k * GOLD
        pos[i] = (cx + rad * math.cos(ang), cy + rad * math.sin(ang))

xs = [p[0] for p in pos]; ys = [p[1] for p in pos]
minx, maxx, miny, maxy = min(xs), max(xs), min(ys), max(ys)
# 归一化到 2000 x 1400 画布比例（保持纵横比）
spanx, spany = maxx - minx, maxy - miny
s = 2000.0 / max(spanx, spany * 1.42)
cx, cy = (minx + maxx) / 2, (miny + maxy) / 2

out_nodes = []
for i, n in enumerate(nodes):
    x = (pos[i][0] - cx) * s
    y = (pos[i][1] - cy) * s
    out_nodes.append({
        "id": n["id"], "name": n["name"], "p": n["filePath"], "t": n["type"],
        "l": layer_of.get(n["id"], ""), "c": n.get("complexity", ""),
        "g": n.get("tags", [])[:5], "s": n.get("summary", ""),
        "doc": n.get("doc", ""),
        "d": deg[i], "k": cluster_key(n["filePath"]),
        "x": round(x, 1), "y": round(y, 1),
    })

cl_out = []
for c, mem in groups.items():
    xs2 = [out_nodes[i]["x"] for i in mem]; ys2 = [out_nodes[i]["y"] for i in mem]
    if len(mem) >= 3:
        cx2, cy2 = sum(xs2)/len(xs2), sum(ys2)/len(ys2)
        rad = max((math.hypot(out_nodes[i]["x"] - cx2, out_nodes[i]["y"] - cy2) for i in mem), default=0)
        cl_out.append({"k": c, "n": len(mem), "r": round(rad, 1),
                       "x": round(cx2, 1), "y": round(cy2, 1)})

OUT.write_text(json.dumps({"nodes": out_nodes, "edges": edges, "layers": kg["layers"], "clusters": cl_out},
                          ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
print(f"packed layout: {N} nodes / {len(edges)} edges / {len(groups)} clusters -> {OUT}")
big = sorted(groups.items(), key=lambda kv: -len(kv[1]))[:8]
print("largest clusters:", ", ".join(f"{c}({len(m)})" for c, m in big))
