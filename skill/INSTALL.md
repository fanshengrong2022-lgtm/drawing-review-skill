# 安装说明（给 AI 执行）

> **出品**：范工AI实战 ｜ **抖音号：80823565662** ｜ **许可**：自定义《授权与防转卖条款》（可自用／可改条目库自用／不可转售或公开再分发，非 CC 协议）

你收到的是一份**技能包**，目录结构如下：

```
审图Skill/
├── SKILL.md              ← 入口，先读这个
├── references/           ← 配套文件，按需读，不要一次全读
│   ├── 01-setup.md                     环境自举（第一次用先做这个）
│   ├── 02-preparation.md               开工准备三件
│   ├── 03-tech-path.md                 技术路径（含四层读取法）
│   ├── 04-five-steps.md                ★ 执行五步（核心）
│   ├── 05-self-check.md                收工覆盖自查（14 项）
│   ├── 06-quality-rules.md             质量纪律 14 条
│   ├── 07-demo.md                      一条完整示范
│   ├── 08-表述规范.md                  ★ 问题表述规范（怎么写才让人看懂）
│   ├── 09-判定经验库.md                ★ 提问前五问 + 十类问题判定
│   ├── 10-checklist-index.md           条目库总说明
│   ├── 11-checklist-arch-struct.md     条目库·总图/建筑/结构
│   ├── 12-checklist-interior.md        条目库·装修
│   ├── 13-checklist-mep.md             条目库·机电及其他专业
│   ├── 14-checklist-appendix.md        条目库·使用须知与附表
│   ├── 15-checklist-site-foundation.md 2026-11 新增·基坑支护 + 木结构（45 条）
│   ├── 16-checklist-signature.md       2026-11 新增·签章与资质（15 条）
│   ├── 17-cross-discipline-collision.md 2026-11 新增·跨专业对撞 30 项
│   └── 18-defect-patterns.md           2026-11 新增·缺陷模式 10 类
├── scripts/              ← 可直接运行的脚本
│   ├── health_check.py                 图纸体检（参照/污染/可读性/坏图层/视口/字体）
│   ├── report_check.py                 报告自检（质量自证行、读取量、条目数合理性）
│   ├── score_report.py                 报告评分（按六维规则给分并提示扣分项）
│   ├── extract_hatch_leader.py         填充（HATCH）+ 引线（LEADER）提取
│   ├── extract_material_tags.py        跨块拼装材料标注提取（含隐藏标志过滤）
│   ├── dedup_md5.py                    重复文件检测（按 MD5 找字节完全相同的文件）
│   └── search_keywords.py              关键词批量检索（详见/参见/二次深化/待定/取消等）
└── INSTALL.md            ← 本文件
```

> ⚠️ **文件名用英文是为了跨解压工具不乱码**；每个文件内部标题与正文全是中文，不影响阅读。
>
> **2026-11 增补**：`15`–`18` 号为新增专项（基坑/木结构、签章、跨专业对撞、缺陷模式）；`score_report.py` 为报告评分脚本。**安装步骤不变**，老用户只需把新增文件覆盖进原目录。
>
> **2026-11-07 新增两个取证脚本**：`dedup_md5.py`（查重复文件）、`search_keywords.py`（批量检索"详见/待定"类表述）。两者**只用 Python 标准库**，不需要额外安装依赖；已用合成数据自测通过，**尚未用真实图纸回测，不承诺精度**，结果只作线索。

## 请按以下步骤安装

1. **放到技能目录**：把整个 `审图Skill` 目录放进你的技能目录
   - WorkBuddy：`~/.workbuddy/skills/`
   - 其他 Agent 平台：各自的 skills / 技能目录（不确定就先问用户）
2. **保持目录结构不变** —— 尤其 `SKILL.md` 必须在技能目录根下，`references/` 与 `scripts/` 与它同级
3. **装完自检环境**：按 `references/01-setup.md` 检查 Python 与四个库、以及可选的 DWG→DXF 工具
   - **缺什么装什么**；装不上就走该文件里的**降级路线**
4. **向用户报告三件事**：① 装在哪 ② 环境就绪情况（哪个好了、哪个没装成）③ **能走 A / B / C 哪条线**

## 使用纪律

- **不要改写 SKILL.md 的内容**
- **不要一次性读完所有 references** —— 按 `SKILL.md` 第三节的索引表按需加载
- 用户说「审图」类需求时，先读 `SKILL.md`，再按索引表往下走

---

*范工AI实战 · 抖音号 80823565662*
