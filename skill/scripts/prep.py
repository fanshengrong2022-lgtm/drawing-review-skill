#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""prep.py —— 审图一键预处理

一条命令做完五件事：DWG→DXF → 文字提取 → 图纸体检 → 分母统计 → 输出报告

用法：
    python scripts/prep.py --src "D:\\图纸目录" --out "D:\\输出目录"

产出：
    <out>\\_dxf\\...                      转换后的 DXF（保持原目录结构）
    <out>\\_data\\text\\*.json             每张图的文字项（含坐标/图层/块名）
    <out>\\_data\\stats.json              每张图的实体统计
    <out>\\_data\\denominator.json        六类单元分母
    <out>\\00_预处理报告.md               人看的汇总

设计原则：
    · 只读源图，不改原文件
    · 转换失败要显式报出来，不许静默跳过
    · 提取必须递归进块（有些图的正文全塞在块里）
"""
import argparse
import json
import os
import re
import subprocess
import sys
import time
from collections import Counter, defaultdict

ODA_DEFAULT = r"C:\Program Files\ODA\ODAFileConverter 27.1.0\ODAFileConverter.exe"
SKIP_DIRS = {"__pycache__", "$RECYCLE.BIN", "System Volume Information"}


# ---------------------------------------------------------------- 基础
def log(msg):
    print(msg, flush=True)


def find_dwg(root, skip_names=(), only=""):
    """递归找所有 DWG。返回 [(绝对路径, 相对目录)]"""
    out = []
    for dp, dns, fns in os.walk(root):
        dns[:] = [d for d in dns if d not in SKIP_DIRS]
        rel = os.path.relpath(dp, root)
        rel = "" if rel == "." else rel
        for f in fns:
            if not f.lower().endswith(".dwg") or f in skip_names:
                continue
            if only and only not in os.path.join(rel, f):
                continue
            out.append((os.path.join(dp, f), rel))
    return sorted(out)


# ---------------------------------------------------------------- 转换
def convert(root, out_dxf, oda, only="", reuse=True):
    """按目录分批调用 ODAFileConverter。返回 (成功数, 失败列表)

    reuse=True 时，已存在同名 DXF 的直接跳过（断点续跑）。
    """
    if not os.path.isfile(oda):
        raise SystemExit("找不到 ODAFileConverter：%s\n请用 --oda 指定路径" % oda)

    # 按子目录分组（ODA 不递归）
    groups = defaultdict(list)
    n_reuse = 0
    for path, rel in find_dwg(root, only=only):
        base = os.path.splitext(os.path.basename(path))[0]
        dst = os.path.join(out_dxf, rel, base + ".dxf") if rel else os.path.join(out_dxf, base + ".dxf")
        if reuse and os.path.isfile(dst):
            n_reuse += 1
            continue
        groups[rel].append(path)

    if n_reuse:
        log("  已有 DXF 可复用：%d 张" % n_reuse)

    ok, fail = n_reuse, []
    for rel, paths in sorted(groups.items()):
        src_dir = os.path.dirname(paths[0])
        dst_dir = os.path.join(out_dxf, rel) if rel else out_dxf
        os.makedirs(dst_dir, exist_ok=True)
        log("  转换 %-46s %2d 张" % ((rel or "(根目录)")[:46], len(paths)))
        try:
            subprocess.run([oda, src_dir, dst_dir, "ACAD2018", "DXF", "0", "1", "*.dwg"],
                           timeout=1200, capture_output=True)
        except subprocess.TimeoutExpired:
            fail.extend(p for p in paths)
            log("    ! 超时")
            continue
        # 逐个核对产物
        for p in paths:
            base = os.path.splitext(os.path.basename(p))[0]
            if os.path.isfile(os.path.join(dst_dir, base + ".dxf")):
                ok += 1
            else:
                fail.append(p)
    return ok, fail


# ---------------------------------------------------------------- 提取
def _walk_block(blk, depth, seen, out, blkname):
    """递归遍历块定义，收集文字。防循环引用。"""
    if depth > 4:
        return
    for e in blk:
        t = e.dxftype()
        try:
            if t == "TEXT":
                out.append({"ty": "TEXT", "tx": e.dxf.text, "ly": str(e.dxf.layer),
                            "blk": blkname, "x": round(e.dxf.insert.x, 1), "y": round(e.dxf.insert.y, 1)})
            elif t == "MTEXT":
                out.append({"ty": "MTEXT", "tx": e.text, "ly": str(e.dxf.layer),
                            "blk": blkname, "x": round(e.dxf.insert.x, 1), "y": round(e.dxf.insert.y, 1)})
            elif t == "ATTDEF":
                out.append({"ty": "ATTDEF", "tx": e.dxf.text, "ly": str(e.dxf.layer),
                            "blk": blkname, "x": 0, "y": 0})
            elif t == "INSERT":
                name = e.dxf.name
                if name in seen:
                    continue
                try:
                    sub = e.doc.blocks.get(name)
                except Exception:
                    sub = None
                if sub is not None:
                    _walk_block(sub, depth + 1, seen | {name}, out, name)
                for a in getattr(e, "attribs", []):
                    out.append({"ty": "ATTRIB", "tx": a.dxf.text, "ly": str(a.dxf.layer),
                                "blk": name, "x": 0, "y": 0})
                # 匿名块里也可能有文字
                try:
                    for ve in e.virtual_entities():
                        if ve.dxftype() in ("TEXT", "MTEXT"):
                            tx = ve.dxf.text if ve.dxftype() == "TEXT" else ve.text
                            out.append({"ty": ve.dxftype(), "tx": tx, "ly": str(ve.dxf.layer),
                                        "blk": name, "x": 0, "y": 0})
                except Exception:
                    pass
        except Exception:
            continue


def _referenced_blocks(doc):
    """图上真正被插入的块（递归），用来区分「放在图上」和「孤立块」。"""
    seen = set()

    def rec(name, depth=0):
        if name in seen or depth > 6:
            return
        seen.add(name)
        try:
            blk = doc.blocks.get(name)
        except Exception:
            return
        if blk is None:
            return
        for e in blk:
            if e.dxftype() == "INSERT":
                rec(e.dxf.name, depth + 1)

    for e in doc.modelspace():
        if e.dxftype() == "INSERT":
            rec(e.dxf.name)
    return seen


def _block_texts(blk, blockname, limit=6000):
    """收一个块内的文字（不递归，只本层）。"""
    out = []
    for e in blk:
        if len(out) >= limit:
            break
        t = e.dxftype()
        try:
            if t == "TEXT":
                out.append({"ty": "TEXT", "tx": e.dxf.text, "ly": str(e.dxf.layer),
                            "blk": blockname, "x": 0, "y": 0})
            elif t == "MTEXT":
                out.append({"ty": "MTEXT", "tx": e.text, "ly": str(e.dxf.layer),
                            "blk": blockname, "x": 0, "y": 0})
        except Exception:
            continue
    return out


def extract_one(dxf_path):
    """提一张图的文字 + 统计。

    返回 (items, unused, stat)
      items  —— 图上可见的文字（主口径，判据只认这个）
      unused —— 未被插入的孤立块里的文字（可疑内容，要人确认，不算证据）
    """
    import ezdxf
    stat = {"file": "", "err": None}
    items = []
    unused = []
    try:
        doc = ezdxf.readfile(dxf_path)
    except Exception as e:
        stat["err"] = "%s: %s" % (type(e).__name__, str(e)[:80])
        return items, unused, stat

    msp = doc.modelspace()
    c = Counter(e.dxftype() for e in msp)
    stat.update({
        "model_ents": len(msp),
        "insert": c.get("INSERT", 0),
        "text": c.get("TEXT", 0),
        "mtext": c.get("MTEXT", 0),
        "hatch": c.get("HATCH", 0),
        "dim": c.get("DIMENSION", 0),
        "paper_ents": sum(len(ps) for ps in doc.layouts if ps.name != "Model"),
        "blocks": len(list(doc.blocks)),
        "layers": len(list(doc.layers)),
        "xrefs": len(list(doc.blocks)) and sum(1 for b in doc.blocks if b.block_record.is_xref),
    })

    # 顶层
    for e in msp:
        t = e.dxftype()
        try:
            if t == "TEXT":
                items.append({"ty": "TEXT", "tx": e.dxf.text, "ly": str(e.dxf.layer), "blk": "",
                              "x": round(e.dxf.insert.x, 1), "y": round(e.dxf.insert.y, 1)})
            elif t == "MTEXT":
                items.append({"ty": "MTEXT", "tx": e.text, "ly": str(e.dxf.layer), "blk": "",
                              "x": round(e.dxf.insert.x, 1), "y": round(e.dxf.insert.y, 1)})
            elif t == "INSERT":
                name = e.dxf.name
                try:
                    blk = e.doc.blocks.get(name)
                except Exception:
                    blk = None
                if blk is not None:
                    _walk_block(blk, 0, {name}, items, name)
                for a in getattr(e, "attribs", []):
                    items.append({"ty": "ATTRIB", "tx": a.dxf.text, "ly": str(a.dxf.layer),
                                  "blk": name, "x": 0, "y": 0})
        except Exception:
            continue

    # 孤立块：有内容但没被插入到图上（可能是废稿，也可能是正文没放置）
    used = _referenced_blocks(doc)
    orphan = []
    for b in doc.blocks:
        name = b.name
        if name.startswith("*") or name in used:
            continue
        # 图框类块不算孤立内容（它们是图框定义，正常就该在块表里）
        low = name.lower()
        if any(k in name for k in ("图框", "标准框", "标题栏")) or low in ("tk", "a0", "a1", "a2", "a3", "a4"):
            continue
        try:
            n = len(list(b))
        except Exception:
            continue
        if n < 200:
            continue
        tx = _block_texts(b, name)
        chars = sum(len(i.get("tx") or "") for i in tx)
        if chars >= 20:          # 只报"有文字但没放上图"的块；纯图形块不算
            orphan.append({"blk": name, "ents": n, "texts": len(tx), "chars": chars})
            for i in tx:
                i["orphan"] = 1
            unused.extend(tx)
    if orphan:
        stat["orphan_blocks"] = orphan

    # 超大块（内容塞进主图，可能是备份副本）
    # 注意：*Model_Space / *Paper_Space 是布局本身，不算"内容块"，必须排除
    big = []
    for b in doc.blocks:
        name = b.name
        if name.startswith("*"):
            continue
        try:
            n = len(list(b))
        except Exception:
            continue
        if n > 5000:
            big.append({"blk": name, "ents": n})
    if big:
        stat["big_blocks"] = big

    # 字体
    fonts = set()
    for s in doc.styles:
        if s.dxf.font:
            fonts.add(s.dxf.font)
    if fonts:
        stat["fonts"] = sorted(fonts)[:12]

    stat["texts_total"] = len(items)
    stat["unused_total"] = len(unused)
    return items, unused, stat


# ---------------------------------------------------------------- 分母
RE_DWGNO = re.compile(r"\b(DL|QL|P|SGPS|JT|LH|JK|YL)[-_]?\d{2,3}\b", re.I)
RE_STATION = re.compile(r"K\d+\+\d{2,3}(?:\.\d+)?")
RE_WELL = re.compile(r"\b([WY])[-\u2010-\u2015]?([1-9]\d{0,2})\b")   # 排除 W0 / Y0 这类误匹配
# 混凝土等级只认 C15~C89（排除 C03 / C800 这类编号误判）
RE_MAT = re.compile(r"\b(C(?:1[5-9]|[2-8]\d)|HRB\d{3}|HPB\d{3}|DN\d{2,4}|De\d{2,4}|Φ\d{1,3}|φ\d{1,3})\b")


def build_denominator(texts):
    """六类单元分母：图号 / 桩号 / 井号 / 材料代号 / 标高 / 图层"""
    acc = {k: Counter() for k in ("dwgno", "station", "well", "material")}
    per_file = defaultdict(lambda: defaultdict(set))
    elev = 0
    for fname, items in texts.items():
        for it in items:
            s = it.get("tx") or ""
            if not s:
                continue
            for m in RE_DWGNO.findall(s):
                pass
            for m in RE_DWGNO.finditer(s):
                key = m.group(0).upper()
                acc["dwgno"][key] += 1
                per_file["dwgno"][key].add(fname)
            for m in RE_STATION.finditer(s):
                acc["station"][m.group(0)] += 1
            for m in RE_WELL.finditer(s):
                acc["well"][m.group(0).upper()] += 1
            for m in RE_MAT.finditer(s):
                acc["material"][m.group(0).upper()] += 1
            if re.match(r"^-?\d+\.\d{2,3}$", s.strip()) and -50 < float(s) < 200:
                elev += 1

    out = {}
    for k, counter in acc.items():
        out[k] = {
            "唯一数": len(counter),
            "出现次数": sum(counter.values()),
            "明细": dict(counter.most_common(40)),
        }
    out["标高数字"] = {"数量": elev}
    return out


# ---------------------------------------------------------------- 报告
def write_report(out_dir, root, res):
    p = os.path.join(out_dir, "00_预处理报告.md")
    L = []
    A = L.append
    A("# 预处理报告（一键生成）")
    A("")
    A("> 源目录：`%s`  " % root)
    A("> 生成时间：%s  " % time.strftime("%Y-%m-%d %H:%M"))
    A("> 耗时：%d 秒" % res["elapsed"])
    A("")
    A("## 一、结论")
    A("")
    A("| 项 | 结果 |")
    A("|---|---|")
    A("| DWG 总数 | **%d** |" % res["n_dwg"])
    A("| 转换成功 | **%d** |" % res["n_ok"])
    A("| 转换失败 | **%d** %s |" % (len(res["fail"]), "⚠️" if res["fail"] else "✅"))
    A("| 可读 DXF | **%d** |" % res["n_read"])
    A("| 提取文字项 | **%d** 条 |" % res["n_items"])
    A("| 文字总字数 | **%d** |" % res["n_chars"])
    A("")
    if res["fail"]:
        A("### 转换失败清单（必须处理，不许当没有）")
        A("")
        for f in res["fail"]:
            A("- `%s`" % f)
        A("")
    A("## 二、逐册分布")
    A("")
    A("| 册/目录 | 张数 | 文字项 | 字数 |")
    A("|---|---:|---:|---:|")
    for book, v in res["by_book"].items():
        A("| %s | %d | %d | %d |" % (book[:40], v["n"], v["items"], v["chars"]))
    A("")
    A("## 三、图纸体检")
    A("")
    h = res["health"]
    A("| 项 | 结果 |")
    A("|---|---|")
    A("| 读取失败 | %d 张 %s |" % (len(h["read_fail"]), "⚠️" if h["read_fail"] else "✅"))
    A("| 外部参照（文件数） | %d |" % h["n_xref_file"])
    A("| 超大块（>5000 实体） | %d 处 |" % len(h["big_blocks"]))
    A("| **孤立块（有内容但没插到图上）** | **%d 处** %s |" % (
        len(h["orphan"]), "⚠️ 需人工确认" if h["orphan"] else "✅"))
    A("| 使用字体（%d 种，未做缺失检测） | `%s` |" % (len(h["fonts"]), "` `".join(h["fonts"][:6])))
    A("")
    if h["read_fail"]:
        A("### 读取失败")
        A("")
        for x in h["read_fail"]:
            A("- `%s` — %s" % (x["file"], x["err"]))
        A("")
    if h["big_blocks"]:
        A("### 超大块（内容被塞进主图，可能是备份副本，也可能是正文）")
        A("")
        A("| 文件 | 块名 | 实体数 |")
        A("|---|---|---:|")
        for b in h["big_blocks"][:20]:
            A("| %s | `%s` | %d |" % (b["file"][-50:], b["blk"], b["ents"]))
        A("")
    if h["orphan"]:
        A("### 孤立块（有内容但没被插到图上）")
        A("")
        A("> **这些块里的文字不算图上证据**——它们没被放置到图纸上。")
        A("> 可能是废稿/备份，也可能是设计方漏放。判据核对时**不要引用**，")
        A("> 但如果某条判据本应在此图体现而图上没有，这里可能就是原因，需人工确认。")
        A("> 原始内容在 `_data/unused/*.json`。")
        A("")
        A("| 文件 | 块名 | 实体数 | 块内文字 | 字数 |")
        A("|---|---|---:|---:|---:|")
        for b in h["orphan"][:20]:
            A("| %s | `%s` | %d | %d | %d |" % (b["file"][-46:], b["blk"], b["ents"], b["texts"], b["chars"]))
        A("")
    A("## 四、六类单元分母（立分母用）")
    A("")
    d = res["denom"]
    for k, label in (("dwgno", "图号"), ("station", "桩号"), ("well", "井号"), ("material", "材料/规格代号")):
        A("### %s —— 唯一 %d 个，出现 %d 次" % (label, d[k]["唯一数"], d[k]["出现次数"]))
        A("")
        items = list(d[k]["明细"].items())[:30]
        if items:
            A("`" + "`  `".join("%s×%d" % (a, b) for a, b in items) + "`")
        A("")
    A("标高数字：**%d** 个" % d["标高数字"]["数量"])
    A("")
    A("## 五、下一步")
    A("")
    A("预处理已完成。接下来按 SKILL.md 第三节：开工必取三件套 → 分线 → 逐线推进。")
    A("")
    A("> 提取的文字在 `_data/text/*.json`，每条含 `ty/tx/ly/blk/x/y`，")
    A("> 需要按位置聚类或按块归属时用得上。")
    open(p, "w", encoding="utf-8").write("\n".join(L))
    return p


# ---------------------------------------------------------------- 主流程
def main():
    ap = argparse.ArgumentParser(description="审图一键预处理")
    ap.add_argument("--src", required=True, help="图纸根目录（含 DWG）")
    ap.add_argument("--out", required=True, help="输出目录")
    ap.add_argument("--oda", default=ODA_DEFAULT, help="ODAFileConverter 路径")
    ap.add_argument("--skip", default="", help="跳过含这些词的文件名，逗号分隔")
    ap.add_argument("--only", default="", help="只处理路径含该词的 DWG（单册试跑用）")
    ap.add_argument("--no-reuse", action="store_true", help="不复用已有 DXF，强制重转")
    a = ap.parse_args()

    root = os.path.abspath(a.src)
    out = os.path.abspath(a.out)
    if not os.path.isdir(root):
        raise SystemExit("源目录不存在：%s" % root)
    out_dxf = os.path.join(out, "_dxf")
    out_txt = os.path.join(out, "_data", "text")
    out_unused = os.path.join(out, "_data", "unused")
    os.makedirs(out_dxf, exist_ok=True)
    os.makedirs(out_txt, exist_ok=True)
    os.makedirs(out_unused, exist_ok=True)
    skip = tuple(s.strip() for s in a.skip.split(",") if s.strip())

    t0 = time.time()
    log("=" * 66)
    log("审图一键预处理")
    log("=" * 66)

    dwgs = find_dwg(root, skip, a.only)
    log("\n[1/5] 找到 %d 个 DWG" % len(dwgs))
    if not dwgs:
        raise SystemExit("没找到 DWG，检查 --src")

    log("\n[2/5] 转 DXF（%s）" % os.path.basename(os.path.dirname(a.oda)))
    n_ok, fail = convert(root, out_dxf, a.oda, only=a.only, reuse=not a.no_reuse)
    log("  成功 %d / %d" % (n_ok, len(dwgs)))

    log("\n[3/5] 提文字（递归进块）")
    texts, stats = {}, []
    n_unused = 0
    for path, rel in dwgs:
        base = os.path.splitext(os.path.basename(path))[0]
        dxf = os.path.join(out_dxf, rel, base + ".dxf") if rel else os.path.join(out_dxf, base + ".dxf")
        if not os.path.isfile(dxf):
            continue
        items, unused, st = extract_one(dxf)
        st["file"] = os.path.join(rel, base + ".dxf") if rel else base + ".dxf"
        stats.append(st)
        key = (rel.replace("\\", "__") + "__" + base) if rel else base
        texts[key] = items
        with open(os.path.join(out_txt, key + ".json"), "w", encoding="utf-8") as f:
            json.dump(items, f, ensure_ascii=False)
        if unused:
            n_unused += len(unused)
            with open(os.path.join(out_unused, key + ".json"), "w", encoding="utf-8") as f:
                json.dump(unused, f, ensure_ascii=False)
        if len(texts) % 10 == 0:
            log("  已提 %d / %d" % (len(texts), n_ok))

    with open(os.path.join(out, "_data", "stats.json"), "w", encoding="utf-8") as f:
        json.dump(stats, f, ensure_ascii=False, indent=1)

    n_items = sum(len(v) for v in texts.values())
    n_chars = sum(len(it.get("tx") or "") for v in texts.values() for it in v)
    log("  共 %d 条文字项 / %d 字" % (n_items, n_chars))

    log("\n[4/5] 体检 + 分母")
    read_fail = [{"file": s["file"], "err": s["err"]} for s in stats if s.get("err")]
    big = []
    for s in stats:
        for b in s.get("big_blocks", []):
            big.append({"file": s["file"], "blk": b["blk"], "ents": b["ents"]})
    orphan = []
    for s in stats:
        for b in s.get("orphan_blocks", []):
            orphan.append({"file": s["file"], "blk": b["blk"], "ents": b["ents"],
                           "texts": b["texts"], "chars": b["chars"]})
    fonts = sorted({f for s in stats for f in s.get("fonts", [])})
    health = {
        "read_fail": read_fail,
        "n_xref_file": sum(1 for s in stats if s.get("xrefs")),
        "big_blocks": big,
        "orphan": orphan,
        "fonts": fonts,
    }
    denom = build_denominator(texts)
    with open(os.path.join(out, "_data", "denominator.json"), "w", encoding="utf-8") as f:
        json.dump(denom, f, ensure_ascii=False, indent=1)

    by_book = defaultdict(lambda: {"n": 0, "items": 0, "chars": 0})
    for k, v in texts.items():
        book = k.split("__")[0] if "__" in k else "(根目录)"
        b = by_book[book]
        b["n"] += 1
        b["items"] += len(v)
        b["chars"] += sum(len(it.get("tx") or "") for it in v)

    res = {
        "elapsed": int(time.time() - t0),
        "n_dwg": len(dwgs), "n_ok": n_ok, "fail": [os.path.relpath(p, root) for p in fail],
        "n_read": len(stats), "n_items": n_items, "n_chars": n_chars, "n_unused": n_unused,
        "by_book": dict(sorted(by_book.items())),
        "health": health, "denom": denom,
    }

    log("\n[5/5] 写报告")
    rp = write_report(out, root, res)
    log("  %s" % rp)

    log("\n" + "=" * 66)
    log("完成：%d 张 / %d 字 / 耗时 %d 秒" % (len(stats), n_chars, res["elapsed"]))
    log("=" * 66)

    # ---- 输出目录锁：后续所有产出必须写到这里，不许另建目录 ----
    out_abs = os.path.abspath(out).replace("\\", "/")
    try:
        with open(os.path.join(out, "OUT_DIR.txt"), "w", encoding="utf-8") as f:
            f.write(out_abs + "\n")
    except Exception:
        pass
    log("")
    log("【输出目录锁】OUT_DIR=%s" % out_abs)
    log("本条之后的全部产出（报告 / 清单 / 表格 / 中间件）一律写到上面这个目录；")
    log("不许在会话临时目录、文档目录另建「审图输出」之类的目录。")
    return 0 if not fail else 2


if __name__ == "__main__":
    sys.exit(main())
