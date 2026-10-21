# 审图 Skill · 图纸会审预审方法体系

> 一线精装项目经理把「图纸会审预审」的动作固化成一个 AI Skill。
> 定标准 → 叠图 → 核冲突 → 出报告 → 收口自查，产出可直接拿去会审的《预审报告》。
>
> **出品**：范工AI实战（抖音号 80823565662）｜ **许可**：CC BY-NC-SA 4.0

---

## 这是什么

一套给 AI 用的**图纸会审预审作业流程**。不是"帮你随便看看图"，是把会审前该做的动作排好顺序、定好判据、配好产出格式。

包内只有**流程骨架**；**判定能力在云端**（19 条判定规则 + 18 专业 1,571 条审图条目 + 5 主题 44 段方法库），凭授权码按次调用。

```
审图Skill/
├── SKILL.md              入口（九个章节：能力 / 触发 / 加载顺序 / 边界 / 云端 / 八条错 / 顺序 / 适用范围 / 包含什么）
├── INSTALL.md            安装说明
├── references/           方法骨架 × 9
└── scripts/              5 个脚本
    ├── ask_api.py              云端判定引擎客户端
    ├── health_check.py         图纸体检单
    ├── report_check.py         报告自检
    ├── extract_hatch_leader.py 填充 / 引线提取
    └── extract_material_tags.py 跨块拼装材料标注提取
```

## 它解决什么问题

会审最怕的不是"审不出来"，是**"审了但等于没审"**——资料没点齐、图没打开、结论靠猜。

这套东西把六个容易出事的环节卡住：

| 环节 | 具体做法 |
|---|---|
| **资料齐备** | 图纸 / 物料书 / 工程量清单 / 合同（承包范围·界面依据）**四类逐份点名**，缺一类就停下问，不许默默往下审 |
| **图纸体检** | 参照可达性 / 污染 / 可读性 / AUDIT 坏图层 / 视口 / 字体，一条命令出报告——先确认"图能打开、内容在不在" |
| **数据自检** | Model / Paper / 文字 / 块 / 图层 / Xref 六处逐个报数，**"读不到"先怀疑自己读错**，不轻易下"没有"的结论 |
| **叠图基准** | 以**轴线对轴线**认同一处，禁止靠图元坐标对位 |
| **核冲突** | 《跨图比对表》报四个数：应比 / 实比 / 无法核 / 不一致 |
| **出报告** | 三张汇总表 + 12 列销项表 + 6 张兜底清单 + 建议层 + 能力外清单，**附《质量自证表》**防"审得太少" |

## 适用 / 不适用

**✅ 适用**：图纸会审预审 ｜ 施工图自查 ｜ 跨专业界面核对 ｜ 物料书与图纸对账 ｜ 精装 / 公装 / 幕墙深化图预审

**⛔ 不适用**：结构受力计算 / 配筋验算 ｜ 消防性能化设计评审 ｜ 造价审核 / 结算审计 ｜ 需注册师签章的法定审查 ｜ 纯扫描件（会明确标【需人工复核】）

> 本 Skill 产出的是**预审报告**，不替代法定审查。

## 安装

**前提**：一个能执行本地命令的 AI（WorkBuddy / Claude Code / Cursor / Trae / OpenClaw 等）+ Python 3.10+

```bash
# 1) 放进技能目录（WorkBuddy 为例）
~/.workbuddy/skills/

# 2) 装依赖
pip install ezdxf pymupdf openpyxl

# 3) 配授权码（只有一个变量）
export DRAWING_REVIEW_KEY="skfg-你的授权码"      # Mac / Linux
set DRAWING_REVIEW_KEY=skfg-你的授权码            # Windows CMD
$env:DRAWING_REVIEW_KEY="skfg-你的授权码"         # Windows PowerShell

# 4) 自检
python scripts/ask_api.py --health                # 应返回 ok:true
python scripts/ask_api.py --rules --ids R14       # 能返回规则内容 = 授权码有效
```

然后直接说「帮我审这套图」，AI 会按 `SKILL.md` 的流程走。

## ⚠️ 能力边界（先看这条，省得白折腾）

**纯聊天型 AI 用不了这套东西。** 豆包、千问网页版这类没有本地执行能力的助手，即使读了 `SKILL.md` 全文，也只能：

- ✅ 讲清流程、列检查清单、做合同↔清单↔物料书的**文字层**对账
- ❌ 跑不了脚本、调不了云端接口、读不了 DXF → **做不出合规的预审报告**

要跑通全链路，必须用**能执行本地命令**的 AI 工具。

## 报告分三档（v1.3.0 起）

AI 审图最大的坑不是"审错"，是**"审到一半就收工"**——实测两个不同 AI 在同一套图上，一个做了叠图、一个直接跳过，但两者在报告里都写成了"已全量审图"。

所以 v1.3.0 起，**报告必须声明自己审到了哪一档**：

| 档位 | 条件 | 能用来干什么 |
|:-:|---|---|
| **A · 深度审图** | 六处齐 + 零条目≤70% + 叠图完成（有轴距偏差数据）+ 五问有记录 | 可用于图纸会审 |
| **B · 表层审图** | 数据读了，但叠图未做/未声明 | 只能当图纸体检用 |
| **C · 不通过** | 无自证 / 六处有 0 / 零条目>70% | 需要重跑 |

跑完直接查：

```bash
python scripts/report_check.py <你的报告.md>
```

脚本会打印档位并返回退出码（`0`=A / `3`=B / `1`=C）。加 `--strict` 则要求必须 A 档。

> **一句话**：先看报告里有没有「叠图：完成」。没写，或写了"未完成"，就只能当体检结果用，别拿去会审。

## 授权码

判定规则库、审图条目库、方法细则全部在云端，需授权码按次调用。

- 在 [SkillHub](https://skillhub.cn/skills/user_ae723d96/drawing-review-free) 评论区留言，或在本仓库提 Issue，说明用途即可
- 一人一码，测试期免费
- **没有授权码时**：环境自检、图纸体检、报告模板这些本地能力照常可用，只是调不了云端判定

## 相关链接

- **SkillHub（国内）**：https://skillhub.cn/skills/user_ae723d96/drawing-review-free
- **作者抖音**：范工AI实战 ｜ 抖音号 80823565662
- **方法论来源**：15 年精装 / 净化工程一线项目经理，不是纸上谈兵

## 许可

[CC BY-NC-SA 4.0](https://creativecommons.org/licenses/by-nc-sa/4.0/deed.zh)

✅ 可自由使用、修改、分享（需署名）｜ ❌ 禁止商用 ｜ 🔁 修改后须以相同方式共享

---

## English

**Drawing Review Skill** — a pre-review workflow for construction drawing joint review (图纸会审), packaged as an AI skill.

It enforces six checkpoints: material completeness (drawings / material book / BOQ / contract scope), drawing health check (xref reachability, pollution, readability, viewport, fonts), data self-audit (Model/Paper/text/blocks/layers/xref counts), overlay by **grid-axis alignment** (never by geometry coordinates), conflict cross-check with four reported numbers, and a review report with a mandatory *quality self-certification* table.

**Scope**: drawing pre-review, cross-discipline interface checks, material-book reconciliation. **Not for**: structural calculation, fire performance-based design review, cost auditing, or statutory code review.

**Architecture**: the skill ships with *process only*. The judgment engine (19 gating rules, 1,571 checklist items across 18 disciplines, 44 method sections) lives in the cloud and is called per-request with a license key.

**⚠️ Requires an agent with local command execution** (WorkBuddy / Claude Code / Cursor / Trae / OpenClaw). Pure chat assistants cannot run the scripts and therefore cannot produce a valid report.

License: CC BY-NC-SA 4.0 · Author: 范工AI实战 (Douyin ID 80823565662)
