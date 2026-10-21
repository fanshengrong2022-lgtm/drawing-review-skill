# -*- coding: utf-8 -*-
"""报告质量自检 v2 —— 检查 AI 交的审图报告「有没有假装审完了」，并给出档位判定

用法:
    python report_check.py <报告文件.md>
        [--prev 上一轮 条目数÷图纸数]
        [--strict]          要求必须达到 A 档，B 档也算不通过

识别报告里这一行（AI 必须提供）：
    【质量自证】应读=N 实读=M | Model=A Paper=B 文字=C 块=D 图层=E Xref=F | 总条数=G 零条目图纸=H 图纸数=I

档位定义（v2 新增）:
    A 档 · 深度审图 —— 六处齐 + 零条目≤70% + 叠图已完成 + 五问有记录
    B 档 · 表层审图 —— 数据读了、但叠图/尺寸比对没做（可用作体检，不可用于会审）
    C 档 · 不通过   —— 没自证 / 六处有 0 / 零条目>70%

退出码:
    0 = A 档    1 = C 档    2 = 无自证行    3 = B 档
"""
import os
import re
import sys
import argparse


def get_args():
    ap = argparse.ArgumentParser()
    ap.add_argument('report', help='报告文件路径（.md）')
    ap.add_argument('--prev', type=float, default=None,
                    help='上一轮 条目数÷图纸数（用于对比骤降）')
    ap.add_argument('--strict', action='store_true',
                    help='要求必须 A 档，B 档也算不通过')
    return ap.parse_args()


# ---------- 叠图判定 ----------
NEG_WORDS = ['未做', '未完成', '未执行', '没做', '未开展', '无法完成', '跳过',
             '未建立', '不适用', '本次未', '本轮未']
POS_WORDS = ['已完成', '完成', '✅', '已做', '成功', '偏差全部', '偏差为 0', '偏差为0']


def detect_overlay(txt):
    """判断报告里的『叠图』是完成 / 未完成 / 未声明

    返回 (状态, 命中的原文行)
    状态取值: 'done' / 'not_done' / 'unstated'
    """
    hits = []
    for line in txt.split('\n'):
        if '叠图' in line or '轴网基准' in line:
            hits.append(line.strip())

    if not hits:
        return 'unstated', ''

    # 先找否定（否定信号更强，优先采信）
    for line in hits:
        if any(w in line for w in NEG_WORDS):
            # 排除“未发现问题”这类与叠图无关的否定
            if any(k in line for k in ['叠图', '轴网基准']):
                return 'not_done', line[:150]

    # 再找肯定
    for line in hits:
        if any(w in line for w in POS_WORDS):
            return 'done', line[:150]

    return 'unstated', hits[0][:150]


# ---------- 未执行清单里有没有把叠图列进去 ----------
def overlay_in_unexecuted(txt):
    """未执行清单里，**项名那一列**是否就是叠图/尺寸比对

    只认表格第 2 列（项名），不做整行匹配 —— 否则「因做叠图而没做标高核验」
    这种正确表述会被误判成「叠图没做」。
    """
    m = re.search(r'(未执行清单|没做什么|未做的项)[^\n]*\n(.{0,4000})', txt, re.S)
    if not m:
        return None
    seg = m.group(2)
    cut = re.search(r'\n#{1,2} ', seg)
    if cut:
        seg = seg[:cut.start()]

    KEY = ['叠图', '尺寸比对', '逐格比对', '轴网基准']
    for line in seg.split('\n'):
        t = line.strip()
        if not t.startswith('|'):
            continue
        cells = [c.strip() for c in t.split('|')[1:-1]]
        if len(cells) < 2:
            continue
        item_name = cells[1]          # 第 2 列 = 项名
        if any(k in item_name for k in KEY):
            return item_name[:120]
    return None


# ---------- 五问过滤记录 ----------
def has_review_record(txt):
    """有没有五问过滤的逐条记录

    两种写法都认：
    ① 显式的「我最终怎么定 / 为什么不一样」逐条表
    ② 有「五问」章节 + 提到「云端」判定 + 有表格行（说明逐条过了）
    """
    for kw in ['我最终怎么定', '为什么不一样', '最终怎么定', '为什么不同']:
        if kw in txt:
            return True

    # 退一步：有五问章节 + 提到云端 + 表格行数够
    if '五问' in txt and '云端' in txt:
        seg_start = txt.find('五问')
        seg = txt[seg_start:seg_start + 6000]
        rows = [l for l in seg.split('\n')
                if l.strip().startswith('|') and len(l.split('|')) >= 4]
        if len(rows) >= 3:
            return True
    return False


# ---------- 证据强度 ----------
def count_weak(txt):
    """统计报告里标为『弱』的证据强度条数（粗略）"""
    n = 0
    for line in txt.split('\n'):
        if not line.strip().startswith('|'):
            continue
        cells = [c.strip() for c in line.split('|')]
        # 只数『弱』单独成格的情况，避免把“弱电/弱化”算进去
        if any(c in ('**弱**', '弱', '*弱*') for c in cells):
            n += 1
    return n


def main():
    a = get_args()
    if not os.path.exists(a.report):
        print(f'❌ 报告文件不存在: {a.report}')
        sys.exit(1)
    txt = open(a.report, encoding='utf-8', errors='ignore').read()

    print(f'报告: {os.path.basename(a.report)}  ({len(txt)} 字)')
    print('=' * 60)

    problems = []   # 致命，判 C 档
    downgrade = []  # 降档，判 B 档
    warns = []      # 提示

    # ===== 1) 质量自证行 =====
    m = re.search(r'【质量自证】(.+)', txt)
    if not m:
        print('❌ 未找到【质量自证】行（未自证）')
        print('   报告必须包含一行：')
        print('   【质量自证】应读=N 实读=M | Model=A Paper=B 文字=C 块=D 图层=E Xref=F '
              '| 总条数=G 零条目图纸=H 图纸数=I')
        print('\n=== 档位判定 ===\n   C 档 · 不通过（缺少质量自证）')
        sys.exit(2)

    line = m.group(1).strip()
    print(f'自证行: {line}\n')
    nums = {}
    for k, v in re.findall(
            r'(应读|实读|Model|Paper|文字|块|图层|Xref|总条数|零条目图纸|图纸数)=(\d+)', line):
        nums[k] = int(v)

    need = ['应读', '实读', 'Model', 'Paper', '文字', '块', '图层',
            'Xref', '总条数', '零条目图纸', '图纸数']
    missing = [k for k in need if k not in nums]
    if missing:
        problems.append(f'自证行缺字段: {missing}')

    print('解析到的数字:')
    for k in need:
        print(f'   {k:8s} = {nums.get(k)}')

    # ===== 2) 六处读取量 =====
    print('\n— 检查 1 · 六处读取量 —')
    zero_fields = [k for k in ['Model', 'Paper', '文字', '块', '图层', 'Xref']
                   if nums.get(k) == 0]
    if zero_fields:
        problems.append(f'六处中 {zero_fields} 为 0 —— 大概率那处没读到（读不到 ≠ 没有）')
        print(f'   ❌ {zero_fields} 为 0')
    elif not missing:
        print('   ✅ 六处均有数据')

    # 实读 vs 应读
    if nums.get('应读') and nums.get('实读') is not None:
        if nums['实读'] < nums['应读']:
            warns.append(f'实读 {nums["实读"]} < 应读 {nums["应读"]} —— 少读的必须在报告里逐个写原因')

    # ===== 3) 零条目占比 / 条目数 =====
    print('\n— 检查 2 · 条目数合理性 —')
    G, H, I = nums.get('总条数'), nums.get('零条目图纸'), nums.get('图纸数')
    if I and H is not None:
        ratio0 = H / I
        print(f'   零条目图纸占比 = {H}/{I} = {ratio0:.0%}')
        if ratio0 > 0.70:
            problems.append(f'零条目图纸占比 {ratio0:.0%} > 70% —— 大概率没真读进去')
            print('   ❌ 超过 70% 阈值')
        else:
            print('   ✅ 在阈值内')
    if G is not None and I:
        per = G / I
        print(f'   条目数÷图纸数 = {G}/{I} = {per:.2f} 条/份')
        if G < 10 and I >= 50:
            problems.append(f'共 {I} 份图只审出 {G} 条 —— 大概率只看了封面/目录')
        if a.prev:
            if per < a.prev * 0.5:
                problems.append(f'条目数÷图纸数 由上轮 {a.prev:.2f} 降到 {per:.2f}'
                                f'（跌超一半）—— 必须解释')
            else:
                print(f'   与上轮 {a.prev:.2f} 相比: 正常')

    # ===== 4) 叠图声明（v2 核心）=====
    print('\n— 检查 3 · 叠图声明（v2 新增）—')
    ov_state, ov_line = detect_overlay(txt)
    if ov_state == 'done':
        print('   ✅ 声明「叠图：完成」')
        print(f'      依据: {ov_line}')
    elif ov_state == 'not_done':
        downgrade.append('报告自述叠图未完成 —— 只能作表层审图')
        print('   ⚠️ 声明「叠图：未完成」')
        print(f'      依据: {ov_line}')
    else:
        downgrade.append('报告中未找到「叠图：完成/未完成」的明确声明')
        print('   ⚠️ 未声明叠图状态')
        print('      报告必须有一处明确写：「叠图：完成」或「叠图：未完成（原因…）」')
        if ov_line:
            print(f'      检测到相关行: {ov_line}')

    # 未执行清单里有没有把叠图列进去
    une = overlay_in_unexecuted(txt)
    if une:
        downgrade.append(f'未执行清单里列了叠图/尺寸类项 —— {une}')
        print(f'   ⚠️ 未执行清单里含: {une}')

    # ===== 5) 五问过滤记录 =====
    print('\n— 检查 4 · 五问过滤记录（v2 新增）—')
    if has_review_record(txt):
        print('   ✅ 有五问逐条记录')
    else:
        downgrade.append('没有五问过滤的逐条记录（缺「我最终怎么定 / 为什么不一样」）')
        print('   ⚠️ 未找到「我最终怎么定 / 为什么不一样」的逐条记录')

    # ===== 6) 弱证据 =====
    print('\n— 检查 5 · 弱证据（v2 新增）—')
    weak = count_weak(txt)
    if weak:
        warns.append(f'检测到 {weak} 条证据强度标「弱」—— 确认它们没混进正式销项表')
        print(f'   ⚠️ 标「弱」的条目: {weak} 条')
    else:
        print('   ✅ 未发现弱证据条目（或报告未使用证据强度标注）')

    # ===== 7) 档位判定 =====
    print('\n' + '=' * 60)
    print('=== 档位判定 ===')
    if problems:
        tier, label = 'C', 'C 档 · 不通过'
        detail = problems
    elif downgrade:
        tier, label = 'B', 'B 档 · 表层审图'
        detail = downgrade
    else:
        tier, label = 'A', 'A 档 · 深度审图'
        detail = []

    print(f'   {label}')
    if detail:
        print('   原因：')
        for d in detail:
            print(f'     · {d}')

    if tier == 'B':
        print('\n   ⚠️ 本报告可用于「图纸体检 / 表层问题清单」，')
        print('      不建议直接用于图纸会审 —— 缺叠图与尺寸比对。')
        print('      补救：按《审图监理_多轮补审SOP》场景 A 生成补审提示词，重跑一轮。')
    if tier == 'A':
        print('\n   ✅ 数字齐、覆盖率达、叠图完成、五问有记录 —— 可用于会审。')
    if tier == 'C':
        print('\n   ❌ 必须先补齐上面的问题，再谈档位。')

    if warns:
        print('\n⚠️ 提示（不影响档位）：')
        for w in warns:
            print(f'   · {w}')

    # ===== 8) 退出码 =====
    if a.strict and tier != 'A':
        print('\n（--strict 模式：要求 A 档，当前未达）')
        sys.exit(1)
    sys.exit({'A': 0, 'B': 3, 'C': 1}.get(tier, 1))


if __name__ == '__main__':
    main()
