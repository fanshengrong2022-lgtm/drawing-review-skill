# -*- coding: utf-8 -*-
"""轴网对齐 / 叠图基准（grid_align）—— 解决「叠图」这一步没有工具、只能现写代码的问题

用法:
    # 1) 先扫一遍，看哪几张图有轴号（判断这套图能不能做叠图）
    python grid_align.py --scan <目录> [--out 轴网扫描.md]

    # 2) 两张图对齐，报偏差
    python grid_align.py <图A.dxf> <图B.dxf> [--out 偏差报告.md] [--tol 1.0]

    # 3) 批量：以某张图为基准，逐个比
    python grid_align.py --base <基准图.dxf> --batch <目录> [--out 偏差报告.md]

三种判定结果（报告会明确写出）:
    [配对模式]  两图都有轴号 → 按轴号配对，报 应比/实比/偏差非0
    [间距模式]  只有轴线没有轴号 → 输出轴线坐标与间距序列，需人工确认（不做自动配对）
    [无轴网]    连轴线都没找到 → 明确写「本套图无轴网，无法做轴网级叠图」

为什么要有「无轴网」这一档:
    实测某酒店项目 231 张图，轴号在 DXF 里根本不存在（只有 3 根轴线 LINE）。
    如果不区分这种情况，AI 会误以为「自己做不了」，用户也会误以为「工具坏了」。
"""
import os
import re
import sys
import json
import math
import argparse
from collections import defaultdict, Counter

try:
    import ezdxf
except ImportError:
    print('❌ 需要 ezdxf：pip install ezdxf')
    sys.exit(1)

# ---------- 轴号识别 ----------
# 字母轴：A~Z（含 AA/AB 这类），排除常见非轴号双字母（图例缩写）
LETTER_RE = re.compile(r'^[A-Z]{1,2}$')
NUMBER_RE = re.compile(r'^\d{1,2}$')
# 图例里常见的假轴号（两个字母且不是轴号的双字母轴）
FAKE_DOUBLE = {'SD', 'QD', 'RD', 'JF', 'PY', 'PL', 'YG', 'LB', 'MT', 'PT', 'ST',
               'GL', 'WD', 'CT', 'AL', 'SS', 'TL', 'TM', 'TR', 'CP', 'FT', 'MR',
               'FB', 'FL', 'MJ', 'AB', 'BC', 'CD', 'DE', 'EF'}
# 轴网相关图层关键字
AXIS_LAYER_KW = ['GRID', 'AXIS', '轴', 'AXL', '柱网', 'DOTE', 'CENTER-LINE']


def is_axis_label(s):
    """可能是轴号吗"""
    s = (s or '').strip().upper()
    if not s or len(s) > 2:
        return False
    if NUMBER_RE.match(s):
        return True
    if LETTER_RE.match(s):
        return s not in FAKE_DOUBLE
    return False


def is_axis_layer(name):
    n = (name or '').upper()
    return any(k.upper() in n for k in AXIS_LAYER_KW)


# ---------- 块内递归 ----------
def texts_in_block(doc, block_name, depth=0, seen=None, max_depth=5):
    """递归读取块定义内部的 TEXT / MTEXT

    为什么必须做：实测某项目立面图上的轴号，既不是顶层文字、也不是块属性，
    而是藏在「轴号圆圈」块定义内部的 TEXT。不递归就一个都读不到。

    返回 [(文字, (x, y))]，坐标为块定义内的相对坐标
    """
    if depth > max_depth:
        return []
    if seen is None:
        seen = set()
    if block_name in seen:          # 防循环引用
        return []
    seen.add(block_name)
    try:
        blk = doc.blocks.get(block_name)
    except Exception:
        return []

    out = []
    for e in blk:
        t = e.dxftype()
        try:
            if t == 'TEXT':
                out.append((e.dxf.text, (e.dxf.insert.x, e.dxf.insert.y)))
            elif t == 'MTEXT':
                out.append((e.text, (e.dxf.insert.x, e.dxf.insert.y)))
            elif t == 'ATTDEF':          # 块定义里的属性默认值
                out.append((e.dxf.text, (e.dxf.insert.x, e.dxf.insert.y)))
            elif t == 'INSERT':
                base = e.dxf.insert
                for txt, (px, py) in texts_in_block(doc, e.dxf.name, depth + 1, seen, max_depth):
                    out.append((txt, (base.x + px, base.y + py)))
        except Exception:
            continue
    return out


# ---------- 采集 ----------
def collect_axes(doc):
    """采集轴号 → 坐标列表

    返回 dict: {
        'labels': {轴号: [(x, y, 来源)]},
        'lines':  {'v': [x...], 'h': [y...]},   # 竖轴/横轴线的坐标
        'sources': {来源: 条数}
    }
    """
    msp = doc.modelspace()
    labels = defaultdict(list)
    sources = Counter()

    # ① 块属性（最可靠：商业项目 GMARK 块走这条）
    #    ⚠️ 属性 tag 不一定叫 GRID-NO —— 实测有图用 tag='A' 装轴号，
    #    所以「块本身在轴网层上」也算合格来源，不强制 tag 名。
    for e in msp.query('INSERT'):
        try:
            attribs = list(e.attribs)
        except Exception:
            continue
        on_axis_layer = is_axis_layer(e.dxf.layer)
        for a in attribs:
            tag = (a.dxf.tag or '').upper()
            val = (a.dxf.text or '').strip()
            if not is_axis_label(val):
                continue
            tag_ok = ('GRID' in tag or 'AXIS' in tag or '轴' in tag)
            if tag_ok or on_axis_layer:
                p = a.dxf.insert
                labels[val].append((float(p.x), float(p.y), 'attrib'))
                sources['块属性'] += 1

    # ② 轴网层上的 TEXT / MTEXT
    for e in msp.query('TEXT MTEXT'):
        if not is_axis_layer(e.dxf.layer):
            continue
        val = (e.dxf.text if e.dxftype() == 'TEXT' else e.text) or ''
        val = val.strip()
        if not is_axis_label(val):
            continue
        p = e.dxf.insert
        labels[val].append((float(p.x), float(p.y), 'text'))
        sources['轴网层文字'] += 1

    # ②b 轴号块内部的文字（★ 立面图靠这条：SL-轴号 这类块，文字在块定义里）
    for e in msp.query('INSERT'):
        if not is_axis_layer(e.dxf.layer):
            continue
        base = e.dxf.insert
        for txt, (px, py) in texts_in_block(doc, e.dxf.name):
            val = (txt or '').strip()
            if not is_axis_label(val):
                continue
            labels[val].append((float(base.x + px), float(base.y + py), 'block'))
            sources['块内文字'] += 1

    # ③ 轴线（LINE 在轴网层上）
    v_lines, h_lines = [], []
    for e in msp.query('LINE'):
        if not is_axis_layer(e.dxf.layer):
            continue
        s, t = e.dxf.start, e.dxf.end
        dx, dy = abs(t.x - s.x), abs(t.y - s.y)
        if dy > dx * 5:          # 竖线
            v_lines.append(round((s.x + t.x) / 2, 1))
        elif dx > dy * 5:        # 横线
            h_lines.append(round((s.y + t.y) / 2, 1))
        sources['轴线'] += 1

    return {'labels': dict(labels),
            'lines': {'v': sorted(set(v_lines)), 'h': sorted(set(h_lines))},
            'sources': dict(sources)}


def split_by_direction(labels, tol=1.0):
    """把轴号分成竖轴组（数字轴，取 X）和横轴组（字母轴，取 Y）

    判据：同组轴号共享同一个 Y（竖轴）或同一个 X（横轴）
    """
    if not labels:
        return {}, {}, {}

    # 先按"数字/字母"分（最稳的直觉判据：数字轴一般是竖轴）
    num_lab = {k: v for k, v in labels.items() if NUMBER_RE.match(k)}
    let_lab = {k: v for k, v in labels.items() if LETTER_RE.match(k)}

    def pick_coord(items, axis):
        """一个轴号可能有多簇坐标（局部放大图），取出现最多的"""
        idx = 0 if axis == 'x' else 1
        vals = [round(it[idx], 1) for it in items]
        if not vals:
            return None
        c = Counter(vals)
        return c.most_common(1)[0][0], len(c)

    vertical, horizontal, multi = {}, {}, {}
    for k, items in num_lab.items():
        r = pick_coord(items, 'x')
        if r:
            vertical[k] = r[0]
            if r[1] > 1:
                multi[k] = f'{r[1]} 簇'
    for k, items in let_lab.items():
        r = pick_coord(items, 'y')
        if r:
            horizontal[k] = r[0]
            if r[1] > 1:
                multi[k] = f'{r[1]} 簇'

    return vertical, horizontal, multi


# ---------- 比对 ----------
def median(vals):
    v = sorted(vals)
    n = len(v)
    if n == 0:
        return 0.0
    return v[n // 2] if n % 2 else (v[n // 2 - 1] + v[n // 2]) / 2


def compare_two(a_map, b_map, tol):
    """同方向轴号配对 —— 先做整体平移归一，再判残差

    为什么要归一：两张图坐标系原点常常不同（实测商业项目两图整体差 311887.6mm），
    直接比原始坐标会全部判"不一致"。正确做法是求两图的中位偏移，
    减掉它以后看"残差"——残差才是真正的绘图误差。

    返回 dict:
        n_union / n_matched / only_a / only_b / offset / rows / n_residual / gaps_a / gaps_b / gap_diff
    """
    common = sorted(set(a_map) & set(b_map), key=lambda k: (len(k), k))
    only_a = sorted(set(a_map) - set(b_map), key=lambda k: (len(k), k))
    only_b = sorted(set(b_map) - set(a_map), key=lambda k: (len(k), k))

    if not common:
        return {'n_union': len(set(a_map) | set(b_map)), 'n_matched': 0,
                'only_a': only_a, 'only_b': only_b, 'offset': None,
                'rows': [], 'n_residual': 0, 'gaps_a': [], 'gaps_b': [], 'gap_diff': 0}

    deltas = [b_map[k] - a_map[k] for k in common]
    offset = round(median(deltas), 1)          # 主偏移（中位数，抗离群）

    rows = []
    for k in common:
        d = b_map[k] - a_map[k]
        residual = round(d - offset, 1)
        rows.append((k, a_map[k], b_map[k], round(d, 1), offset, residual,
                     abs(residual) <= tol))

    n_residual = sum(1 for r in rows if not r[6])

    # 轴距序列比对（与原点无关，最硬的判据）
    ka = sorted(common, key=lambda k: a_map[k])
    gaps_a = [round(a_map[ka[i + 1]] - a_map[ka[i]], 1) for i in range(len(ka) - 1)]
    gaps_b = [round(b_map[ka[i + 1]] - b_map[ka[i]], 1) for i in range(len(ka) - 1)]
    gap_diff = sum(1 for x, y in zip(gaps_a, gaps_b) if abs(x - y) > tol)

    return {'n_union': len(set(a_map) | set(b_map)), 'n_matched': len(common),
            'only_a': only_a, 'only_b': only_b, 'offset': offset,
            'rows': rows, 'n_residual': n_residual,
            'gaps_a': gaps_a, 'gaps_b': gaps_b, 'gap_diff': gap_diff}


# ---------- 单文件分析 ----------
def analyze_file(path):
    try:
        doc = ezdxf.readfile(path)
    except Exception as ex:
        return {'path': path, 'error': str(ex)}

    info = collect_axes(doc)
    v, h, multi = split_by_direction(info['labels'])

    # 判定门槛：至少 3 个轴号、且某个方向至少 2 个，才认为「可配对」
    # 为什么要有门槛：图例表里会混进单个字符（如层说明「BS-GRID 轴线」旁边的编号），
    # 1 个"轴号"配不了对，判成配对模式是假阳性。
    n_lab = len(v) + len(h)
    if n_lab >= 3 and (len(v) >= 2 or len(h) >= 2):
        mode = 'pairing'
    elif info['lines']['v'] or info['lines']['h']:
        mode = 'spacing'
    else:
        mode = 'none'

    return {'path': path, 'mode': mode, 'vertical': v, 'horizontal': h,
            'multi': multi, 'lines': info['lines'], 'sources': info['sources'],
            'n_labels': len(info['labels'])}


def short(p, n=52):
    s = os.path.basename(p)
    return s if len(s) <= n else s[:n - 3] + '...'


# ---------- 报告 ----------
def write_scan_report(results, out):
    pairing = [r for r in results if r.get('mode') == 'pairing']
    spacing = [r for r in results if r.get('mode') == 'spacing']
    none = [r for r in results if r.get('mode') == 'none']
    err = [r for r in results if r.get('error')]

    L = []
    L.append('# 轴网扫描报告\n')
    L.append(f'> 共扫描 {len(results)} 个 DXF 文件\n')
    L.append('| 判定 | 文件数 | 含义 |')
    L.append('|---|:-:|---|')
    L.append(f'| **配对模式** | **{len(pairing)}** | 有轴号，可做轴号级叠图 |')
    L.append(f'| 间距模式 | {len(spacing)} | 只有轴线无线号，只能比间距，需人工确认 |')
    L.append(f'| 无轴网 | {len(none)} | 图上没有轴网，**这套图做不了轴网级叠图** |')
    if err:
        L.append(f'| 读取失败 | {len(err)} | 文件损坏或版本过高 |')
    L.append('')

    if not pairing:
        L.append('## ⚠️ 结论：本套图**无法做轴号级叠图**\n')
        L.append('全套图里没有任何一张能提取到轴号。可能原因：\n')
        L.append('1. 出图时把轴网放在外部参照里，且参照未随图交付')
        L.append('2. 室内装修图本身不画轴网（只画定位尺寸）')
        L.append('3. 轴号用的是图形块（圆圈+文字），文字未炸开且在块定义内部')
        L.append('')
        L.append('**这不等于「审图工具坏了」**——是这套图没有可比对的基准。')
        L.append('这种情况下，叠图应改为「按房间名/轴线描述文字对位」，或直接标注「本套图不做轴网叠图」。\n')
    else:
        L.append(f'## ✅ 可以做轴号级叠图：{len(pairing)} 张图有轴号\n')

    if pairing:
        L.append('### 有轴号的文件\n')
        L.append('| 文件 | 竖轴(数字) | 横轴(字母) | 多簇轴号 | 来源 |')
        L.append('|---|---:|---:|---|---|')
        for r in pairing[:60]:
            L.append(f"| {short(r['path'])} | {len(r['vertical'])} | "
                     f"{len(r['horizontal'])} | {len(r['multi']) or '—'} | "
                     f"{r['sources']} |")
        L.append('')

    if spacing:
        L.append('### 只有轴线、没有轴号的文件（间距模式）\n')
        L.append('| 文件 | 竖线 | 横线 |')
        L.append('|---|---:|---:|')
        for r in spacing[:30]:
            L.append(f"| {short(r['path'])} | {len(r['lines']['v'])} | "
                     f"{len(r['lines']['h'])} |")
        L.append('')

    if err:
        L.append('### 读取失败\n')
        for r in err[:20]:
            L.append(f"- {short(r['path'])}：{r['error'][:80]}")
        L.append('')

    txt = '\n'.join(L)
    open(out, 'w', encoding='utf-8').write(txt)
    return txt


def write_pair_report(a, b, tol, out):
    L = []
    L.append('# 轴网叠图偏差报告\n')
    L.append(f'- 图A（基准）：`{a["path"]}`')
    L.append(f'- 图B（对比）：`{b["path"]}`')
    L.append(f'- 容差：{tol} mm\n')

    # 多簇提示（一个轴号在图上有多处坐标 → 局部放大图/分图，选簇可能影响结果）
    ma, mb = a.get('multi', {}), b.get('multi', {})
    if ma or mb:
        L.append('> ⚠️ **多簇轴号**（同一轴号在图上出现多处坐标，多半是局部放大图）：')
        if ma:
            L.append(f'> - 图A：{ma}')
        if mb:
            L.append(f'> - 图B：{mb}')
        L.append('> 本报告取「出现次数最多」的那一簇。**这几条偏差请人工复核选簇是否正确。**\n')

    # 模式判定
    if a['mode'] != 'pairing' and b['mode'] != 'pairing':
        if a['mode'] == 'spacing' or b['mode'] == 'spacing':
            L.append('## 判定：**只有轴线没有轴号，只能比间距**\n')
            for tag, r in (('图A', a), ('图B', b)):
                v, h = r['lines']['v'], r['lines']['h']
                L.append(f'### {tag} 轴线坐标\n')
                L.append(f'- 竖线 X：{v[:20]}{" ..." if len(v) > 20 else ""}')
                L.append(f'- 横线 Y：{h[:20]}{" ..." if len(h) > 20 else ""}')
                if len(v) > 1:
                    gaps = [round(v[i + 1] - v[i], 1) for i in range(len(v) - 1)]
                    L.append(f'- 竖轴间距序列：{gaps[:20]}')
                if len(h) > 1:
                    gaps = [round(h[i + 1] - h[i], 1) for i in range(len(h) - 1)]
                    L.append(f'- 横轴间距序列：{gaps[:20]}')
                L.append('')
            L.append('> 没有轴号就无法自动配对，上面的间距序列请人工比对。')
            txt = '\n'.join(L)
            open(out, 'w', encoding='utf-8').write(txt)
            return txt, 'spacing'
        L.append('## 判定：**两图都没有轴网，无法叠图**\n')
        L.append('说明：本套图不画轴网，不能做轴号级叠图。请改用「按房间/部位名对位」。')
        txt = '\n'.join(L)
        open(out, 'w', encoding='utf-8').write(txt)
        return txt, 'none'

    # 有一边轴号太少（不够配对）
    if a['mode'] != 'pairing' or b['mode'] != 'pairing':
        weak = '图A' if a['mode'] != 'pairing' else '图B'
        L.append(f'## 判定：**{weak} 轴号不足，无法配对**\n')
        L.append(f'- 图A 轴号：竖 {len(a.get("vertical", {}))} / 横 {len(a.get("horizontal", {}))}'
                 f'（模式 {a["mode"]}）')
        L.append(f'- 图B 轴号：竖 {len(b.get("vertical", {}))} / 横 {len(b.get("horizontal", {}))}'
                 f'（模式 {b["mode"]}）')
        L.append('\n> 配对至少要 3 个轴号、且某一方向 ≥2 个。轴号太少时请改用「间距模式」或人工比对。')
        txt = '\n'.join(L)
        open(out, 'w', encoding='utf-8').write(txt)
        return txt, 'spacing'

    # 配对模式
    total_union = total_matched = total_residual = total_gapdiff = 0
    L.append('> 判读方法：先求两图的**中位偏移**并归一（不同图原点不同），')
    L.append('> 再判**残差**是否超出容差。轴距序列与原点无关，是最硬的旁证。\n')
    for title, key in (('一、竖轴（数字轴）', 'vertical'), ('二、横轴（字母轴）', 'horizontal')):
        L.append(f'## {title}\n')
        amap, bmap = a.get(key, {}), b.get(key, {})
        if not amap and not bmap:
            L.append('（两图都没有）\n')
            continue
        r = compare_two(amap, bmap, tol)
        total_union += r['n_union']
        total_matched += r['n_matched']
        total_residual += r['n_residual']
        total_gapdiff += r['gap_diff']

        if r['n_matched'] == 0:
            L.append('（两图没有共同轴号，无法配对）\n')
            continue

        L.append(f"- 应比 N（两图轴号并集）：{r['n_union']}")
        L.append(f"- **实比 M（两图都有）：{r['n_matched']}**")
        L.append(f"- 无法核 K（只有一边有）：{len(r['only_a']) + len(r['only_b'])}"
                 f"{'　A独有：' + str(r['only_a']) if r['only_a'] else ''}"
                 f"{'　B独有：' + str(r['only_b']) if r['only_b'] else ''}")
        L.append(f"- **主偏移（中位）：{r['offset']:+.1f} mm** ← 两图坐标系原点差，已归一")
        L.append(f"- **归一后残差超 {tol}mm 的：{r['n_residual']} 个**")
        L.append(f"- 轴距序列：共 {len(r['gaps_a'])} 对，**不一致 {r['gap_diff']} 对**\n")

        if r['rows']:
            L.append('| 轴号 | 图A | 图B | 原始差 | 减主偏移后残差 | 判定 |')
            L.append('|---|---:|---:|---:|---:|:-:|')
            for k, av, bv, d, off, res, ok in r['rows'][:80]:
                L.append(f'| {k} | {av} | {bv} | {d:+.1f} | {res:+.1f} | '
                         f'{"一致" if ok else "**不一致**"} |')
            if len(r['rows']) > 80:
                L.append(f"| … | 共 {len(r['rows'])} 行 | | | | |")
        L.append('')

    L.append('\n## 三、汇总\n')
    L.append(f'- 应比合计：{total_union}')
    L.append(f'- **实比合计：{total_matched}**')
    L.append(f'- **归一后残差非 0：{total_residual} 个**')
    L.append(f'- **轴距不一致：{total_gapdiff} 对**\n')
    if total_residual == 0 and total_matched > 0:
        L.append(f'### ✅ 结论：两图轴网一致'
                 f'（{total_matched} 组全部对上，归一后偏差全部在 {tol}mm 内）')
        if total_gapdiff:
            L.append(f'\n> ⚠️ 但有 {total_gapdiff} 对相邻轴距不一致 —— 需复核')
    elif total_residual > 0:
        L.append(f'### ⚠️ 结论：**存在 {total_residual} 处轴网偏差**，'
                 f'需确认是设计意图（如楼层退台）还是绘图误差')

    txt = '\n'.join(L)
    open(out, 'w', encoding='utf-8').write(txt)
    return txt, 'pairing'


# ---------- CLI ----------
def main():
    ap = argparse.ArgumentParser(description='轴网对齐 / 叠图基准')
    ap.add_argument('a', nargs='?', help='图A（或 --scan 的目录）')
    ap.add_argument('b', nargs='?', help='图B')
    ap.add_argument('--scan', metavar='DIR', help='批量扫描目录，判断这套图能不能做叠图')
    ap.add_argument('--base', metavar='DXF', help='批量模式：基准图')
    ap.add_argument('--batch', metavar='DIR', help='批量模式：对比目录')
    ap.add_argument('--out', default=None, help='输出报告路径（默认自动命名）')
    ap.add_argument('--tol', type=float, default=1.0, help='偏差容差 mm（默认 1.0）')
    ap.add_argument('--json', action='store_true', help='同时输出 JSON')
    args = ap.parse_args()

    # 模式 1：扫描
    if args.scan:
        d = args.scan
        if not os.path.isdir(d):
            print(f'❌ 目录不存在: {d}')
            sys.exit(1)
        files = []
        for root, _, fs in os.walk(d):
            for f in fs:
                if f.lower().endswith('.dxf'):
                    files.append(os.path.join(root, f))
        if not files:
            print(f'❌ 目录下没有 .dxf: {d}')
            sys.exit(1)
        print(f'扫描 {len(files)} 个 DXF…')
        results = []
        for i, p in enumerate(files, 1):
            print(f'  [{i}/{len(files)}] {os.path.basename(p)[:50]}', end='\r')
            results.append(analyze_file(p))
        print(' ' * 70, end='\r')
        out = args.out or os.path.join(d, '轴网扫描报告.md')
        txt = write_scan_report(results, out)
        n_pair = sum(1 for r in results if r.get('mode') == 'pairing')
        print(f'\n完成。配对模式 {n_pair} / 间距模式 '
              f'{sum(1 for r in results if r.get("mode") == "spacing")} / '
              f'无轴网 {sum(1 for r in results if r.get("mode") == "none")}')
        print(f'报告：{out}')
        sys.exit(0 if n_pair else 3)

    # 模式 2：批量
    if args.base and args.batch:
        if not os.path.exists(args.base):
            print(f'❌ 基准图不存在: {args.base}')
            sys.exit(1)
        base = analyze_file(args.base)
        files = []
        for root, _, fs in os.walk(args.batch):
            for f in fs:
                if f.lower().endswith('.dxf'):
                    files.append(os.path.join(root, f))
        print(f'基准：{os.path.basename(args.base)}')
        print(f'对比 {len(files)} 个文件…')
        lines = [f'# 批量轴网对比（基准：{os.path.basename(args.base)}）\n',
                 '| 文件 | 模式 | 实比 | 偏差非0 | 结论 |', '|---|---|:-:|:-:|---|']
        nbad = 0
        for p in files:
            res = analyze_file(p)
            if res.get('error') or res.get('mode') != 'pairing' or base.get('mode') != 'pairing':
                lines.append(f"| {short(p)} | {res.get('mode', 'error')} | — | — | 无法配对 |")
                continue
            matched = 0
            diff = 0
            gapdiff = 0
            for key in ('vertical', 'horizontal'):
                cmp = compare_two(base.get(key, {}), res.get(key, {}), args.tol)
                matched += cmp['n_matched']
                diff += cmp['n_residual']
                gapdiff += cmp['gap_diff']
            if diff or gapdiff:
                nbad += 1
            lines.append(f"| {short(p)} | 配对 | {matched} | {diff} | "
                         f"{'✅ 一致' if (diff == 0 and gapdiff == 0) else '⚠️ 有偏差'} |")
        lines.append('')
        lines.append(f'**汇总**：{len(files)} 个文件中，{nbad} 个存在轴网偏差。')
        out = args.out or os.path.join(args.batch, '批量轴网对比.md')
        open(out, 'w', encoding='utf-8').write('\n'.join(lines))
        print(f'\n完成。{nbad} 个文件有偏差。报告：{out}')
        sys.exit(0)

    # 模式 3：两图对比
    if not (args.a and args.b):
        ap.print_help()
        sys.exit(1)
    for p in (args.a, args.b):
        if not os.path.exists(p):
            print(f'❌ 文件不存在: {p}')
            sys.exit(1)

    a = analyze_file(args.a)
    b = analyze_file(args.b)
    if a.get('error') or b.get('error'):
        print(f'❌ 读取失败: {a.get("error") or b.get("error")}')
        sys.exit(1)

    out = args.out or os.path.join(os.path.dirname(args.a) or '.', '轴网偏差报告.md')
    txt, mode = write_pair_report(a, b, args.tol, out)

    print(f'模式: {mode}')
    print(txt[:1500])
    print(f'\n报告已写入: {out}')
    sys.exit({'pairing': 0, 'spacing': 3, 'none': 3}.get(mode, 1))


if __name__ == '__main__':
    main()
