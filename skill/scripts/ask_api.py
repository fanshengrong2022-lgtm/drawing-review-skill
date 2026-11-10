#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
审图 Skill · 云端判定引擎客户端（免费版）

⚠️ 本脚本不含任何判定规则与方法细则——它们全部在服务端，需 API Key。

用法：
  python ask_api.py --machine-id              # 打印本机机器码（申请授权码用）
  python ask_api.py --health
  python ask_api.py --rules --ids R14,R1
  python ask_api.py --rules --keyword 同号
  python ask_api.py --checklist --keyword 防水 --limit 20
  python ask_api.py --checklist --profession 装修
  python ask_api.py --review --text "同一编号在不同册指不同材料"
  python ask_api.py --review --file items.json     # [{"问题描述": "..."}, ...]

  # 方法库（怎么审）
  python ask_api.py --method list                   # 有哪些主题
  python ask_api.py --method five-steps --outline   # 该主题分几段
  python ask_api.py --method five-steps 3           # 取第 3 段正文

配置（环境变量）：
  DRAWING_REVIEW_KEY   API Key（向作者申请）
  DRAWING_REVIEW_API   服务地址（已内置，一般不用配）
"""
import os
import sys
import json
import argparse
import urllib.request
import urllib.error

API = os.environ.get(
    'DRAWING_REVIEW_API',
    'https://drawing-review-d1g4mjq96a0f1cdcc-1510749119.ap-shanghai.app.tcloudbase.com'
).rstrip('/')
KEY = os.environ.get('DRAWING_REVIEW_KEY', '')


def machine_id():
    """本机机器码（8 位）—— 授权码与这台机器绑死，换机器要重新申请。

    取机器唯一标识的 SHA256 前 8 位，只上传哈希值，不上传原始信息：
      Windows → 注册表 HKLM\\SOFTWARE\\Microsoft\\Cryptography\\MachineGuid
      Linux   → /etc/machine-id
      macOS   → ioreg IOPlatformUUID
      兜底    → 主机名 + 网卡 MAC

    同一台电脑上装多少个 Agent，算出来都是同一个码 —— 所以多 Agent 可以共用。
    """
    import hashlib
    raw = []

    # Windows
    try:
        import winreg
        k = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE,
                           r'SOFTWARE\Microsoft\Cryptography')
        v, _ = winreg.QueryValueEx(k, 'MachineGuid')
        winreg.CloseKey(k)
        if v:
            raw.append(str(v))
    except Exception:
        pass

    # Linux
    try:
        with open('/etc/machine-id') as f:
            v = f.read().strip()
        if v:
            raw.append(v)
    except Exception:
        pass

    # macOS
    try:
        import subprocess
        out = subprocess.run(['ioreg', '-rd1', '-c', 'IOPlatformExpertDevice'],
                             capture_output=True, text=True, timeout=5).stdout
        for line in out.splitlines():
            if 'IOPlatformUUID' in line:
                raw.append(line.split('=')[-1].strip().strip('"'))
                break
    except Exception:
        pass

    # 兜底
    if not raw:
        import socket
        import uuid
        raw.append(socket.gethostname())
        raw.append(str(uuid.getnode()))

    h = hashlib.sha256(('drawing-review:v1:' + '|'.join(raw)).encode('utf-8')).hexdigest()
    return h[:8].upper()


def call(path, payload=None):
    url = API + path
    data = json.dumps(payload or {}, ensure_ascii=False).encode('utf-8')
    req = urllib.request.Request(url, data=data, method='POST',
                                 headers={'Content-Type': 'application/json',
                                          'X-API-Key': KEY,
                                          'X-Machine-Id': machine_id()})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return r.status, json.loads(r.read().decode('utf-8'))
    except urllib.error.HTTPError as e:
        body = e.read().decode('utf-8', 'ignore')
        try:
            return e.code, json.loads(body)
        except Exception:
            return e.code, {'error': body[:300]}
    except Exception as e:
        return 0, {'error': f'连接失败：{e}（检查网络或 DRAWING_REVIEW_API）'}


def main():
    ap = argparse.ArgumentParser(description='审图 Skill 云端判定引擎客户端')
    ap.add_argument('--health', action='store_true')
    ap.add_argument('--rules', action='store_true', help='查判定规则（只给规则名与动作）')
    ap.add_argument('--ids', help='规则编号，逗号分隔，如 R14,R1')
    ap.add_argument('--keyword', help='关键词')
    ap.add_argument('--profession', help='专业，如 装修 / 给排水 / 电气 / 房建 / 道路 / 排水 / 桥梁')
    ap.add_argument('--limit', type=int, default=200)
    ap.add_argument('--checklist', action='store_true', help='查审图条目')
    ap.add_argument('--chapter', help='配合 --checklist：按章节取条目，如 "P3 管道" / "6.8 给排水"')
    ap.add_argument('--offset', type=int, default=0, help='配合 --checklist：分页偏移，按 next_offset 翻页')
    ap.add_argument('--sweep', help='批量关键词扫描（技术内容审查），逗号分隔，如 闭水,闭气,温控')
    ap.add_argument('--review', action='store_true', help='报告条目五问预检')
    ap.add_argument('--text', help='单条问题描述')
    ap.add_argument('--file', help='条目 JSON 文件（[{"问题描述":"..."}]）')
    ap.add_argument('--method', nargs='*', metavar='TOPIC [PART]',
                    help='方法库：--method list / --method 主题 / --method 主题 段号')
    ap.add_argument('--outline', action='store_true',
                    help='配合 --method 或 --checklist：只看分段 / 只看章节大纲')
    ap.add_argument('--all', action='store_true',
                    help='配合 --method：一次取该主题全部段落（推荐，少跑几次）')
    ap.add_argument('--machine-id', action='store_true',
                    help='只打印本机机器码（申请授权码时把这串发给作者）')
    a = ap.parse_args()

    # 只打印机器码：不需要 key、不联网
    if a.machine_id:
        mid = machine_id()
        print(f'M-{mid[:4]}-{mid[4:]}')
        print('\n这是本机机器码，授权码会和它绑死。')
        print('· 同一台电脑换多少个 AI 工具（WorkBuddy / Claude Code / Cursor…）都用这一个码')
        print('· 换电脑要重新申请')
        print('\n申请授权码时，把这串发给作者即可：')
        print(f'  M-{mid[:4]}-{mid[4:]}')
        return 0

    if a.health:
        code, d = call('/v1/health')

    elif a.rules:
        code, d = call('/v1/rules', {'ids': a.ids, 'keyword': a.keyword})

    elif a.checklist:
        code, d = call('/v1/checklist', {'keyword': a.keyword,
                                         'profession': a.profession,
                                         'chapter': a.chapter,
                                         'offset': a.offset,
                                         'outline': bool(a.outline),
                                         'limit': a.limit})

    elif a.sweep:
        kws = [x.strip() for x in a.sweep.replace('，', ',').replace('、', ',').split(',') if x.strip()]
        if not kws:
            print('⚠️ --sweep 后面跟关键词，逗号分隔，例如：--sweep 闭水,闭气,温控')
            return 1
        code, d = call('/v1/sweep', {'keywords': kws, 'profession': a.profession})

    elif a.review:
        items = []
        if a.file:
            items = json.load(open(a.file, encoding='utf-8'))
        elif a.text:
            items = [{'问题描述': a.text}]
        code, d = call('/v1/review', {'items': items})

    elif a.method is not None:
        m = a.method
        if not m or m[0].lower() == 'list':
            code, d = call('/v1/method', {})
        elif a.all:
            code, d = call('/v1/method', {'topic': m[0], 'all': True})
        elif a.outline or len(m) == 1:
            code, d = call('/v1/method', {'topic': m[0], 'outline': True})
        else:
            try:
                part = int(m[1])
            except ValueError:
                print('⚠️ 段号必须是整数，例如：--method five-steps 3')
                return 1
            code, d = call('/v1/method', {'topic': m[0], 'part': part})

    else:
        print(__doc__)
        return 1

    if code == 402:
        body = d.get('body') if isinstance(d, dict) else None
        reason = body.get('reason') if isinstance(body, dict) else ''
        # v2.1.1 起云端对外只返回统一 invalid-key（细分原因只进服务端日志），
        # 客户端按通用话术提示，覆盖最常见的三种情况
        print('⚠️ 授权未通过：Key 无效、已过期，或不匹配这台电脑。')
        if reason:
            print('   原因代码：%s' % reason)
        print(json.dumps(d, ensure_ascii=False, indent=2))
        print('\n→ 取本机机器码：python scripts/ask_api.py --machine-id')
        print('→ 把机器码发给作者重新申领授权码，再设为 DRAWING_REVIEW_KEY')
        return 2
    if code == 0:
        print('⚠️ 连不上服务：')
        print(json.dumps(d, ensure_ascii=False, indent=2))
        return 3

    body = d.get('body', d) if isinstance(d, dict) else d
    if not isinstance(body, dict):
        body = d

    # 方法库：单段正文 / 批量多段，直接输出正文，方便 Agent 直接读
    if isinstance(body, dict) and body.get('error') == 'too_large':
        print('⚠️ 该主题一次取不完（%s 字，上限 %s 字），请用段号分批取：'
              % (body.get('total_chars'), body.get('limit')))
        for o in body.get('outline', []):
            print('   %2d. %-40s %5d 字' % (o['part'], o['title'][:38], o['chars']))
        return 1

    if isinstance(body, dict) and 'content' in body and a.method is not None:
        print(body['content'])
        return 0

    if isinstance(body, dict) and body.get('sections') and a.method is not None:
        print('# %s（共 %d 段 / %d 字）' % (body.get('title', ''), body.get('count', 0),
                                        body.get('total_chars', 0)))
        for s in body['sections']:
            print('\n---\n')
            print(s['content'])
        return 0

    # 章节大纲
    if isinstance(body, dict) and body.get('mode') == 'outline':
        print('总条数：%d' % body.get('total', 0))
        print()
        print('%-34s %5s' % ('章节', '条数'))
        print('-' * 44)
        for c in body.get('chapters', []):
            print('%-34s %5d' % (c['chapter'][:32], c['count']))
        print()
        print('→ 逐章取条目：--checklist --chapter "<章节名>" --limit 200')
        return 0

    # 条目列表：紧凑输出 + 翻页提示
    if isinstance(body, dict) and body.get('mode') not in ('stat', 'outline') and 'items' in body:
        items = body.get('items') or []
        print('命中 %d 条，本页 %d 条（offset=%s）'
              % (body.get('total', 0), len(items), body.get('offset', 0)))
        print()
        for i in items:
            expect = (' → ' + i['expect']) if i.get('expect') else ''
            print('[%s] %s%s' % (i.get('no', ''), (i.get('content') or ''), expect))
        if body.get('next_offset') is not None:
            print()
            print('→ 还有下一页：--checklist --chapter "<章节>" --offset %s --limit %s'
                  % (body['next_offset'], a.limit))
        return 0

    # 关键词扫描
    if isinstance(body, dict) and 'hit_keywords' in body:
        print('命中 %d / %d 个词' % (body.get('hit_keywords'), body.get('count')))
        print()
        print('%-10s %6s  %s' % ('关键词', '云端', '首条样例'))
        print('-' * 60)
        for r in body.get('results', []):
            s = ''
            if r.get('sample'):
                x = r['sample'][0]
                s = (x.get('content') or '')[:36]
                if x.get('expect'):
                    s += ' → ' + x['expect'][:18]
            print('%-10s %6d  %s' % (r['kw'], r['n'], s))
        print()
        print('→ 云端 0 命中的词 = 本库未覆盖，列「能力外」，不许硬报')
        return 0

    print(json.dumps(d, ensure_ascii=False, indent=2))
    return 0 if code == 200 else 1


if __name__ == '__main__':
    sys.exit(main())
