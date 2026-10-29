# 安装说明（给 AI 执行）

> **出品**：范工AI实战 ｜ **抖音号：80823565662** ｜ **许可**：CC BY-NC-SA 4.0

你收到的是一份**技能包**（免费版）。核心判定能力在**云端**，本包只含方法流程与调用方式。

```
drawing-review/
├── SKILL.md              ← 入口，先读这个（第五节是云端调用）
├── references/           ← 方法流程（10 个）
│   ├── 00-索引.md              方法库索引（先看这个）
│   ├── 01-setup.md             环境自举
│   ├── 02-preparation.md       开工准备
│   ├── 03-tech-path.md         技术路径（四层读取）
│   ├── 04-five-steps.md        ★ 执行五步（核心）
│   ├── 05-self-check.md        收工自查
│   ├── 06-quality-rules.md     质量纪律 12 条
│   ├── 07-demo.md              完整示范
│   ├── 08-表述规范.md          问题表述规范
│   └── 09-图纸分工表.md        每种图该标什么
├── scripts/
│   ├── prep.py                 ★ 一键预处理（DWG→DXF→文字→体检→分母）
│   ├── ask_api.py              ★ 云端判定引擎客户端（规则/条目/五问）
│   ├── health_check.py         图纸体检
│   ├── report_check.py         报告自检
│   ├── grid_align.py           轴网对齐
│   ├── extract_hatch_leader.py 填充+引线提取
│   └── extract_material_tags.py 跨块拼装材料标注提取
└── INSTALL.md            ← 本文件
```

## 最快装法：把下面整段发给 AI

```
帮我装一个技能包，下载地址：
https://api.skillhub.cn/api/v1/download?slug=@user_ae723d96/drawing-review-free

要求：
1. 下载下来是 zip，解压后放进你的技能目录，目录名用 drawing-review
2. 目录结构必须是 drawing-review/SKILL.md 和 drawing-review/references/ 同级
3. 把授权码 <你的授权码> 单独写一行存成 drawing-review/key.txt（和 SKILL.md 同级，只放这一行码）
4. 装完读一遍 SKILL.md，告诉我 version 是几、references 有几个文件
5. 不要改写 SKILL.md 和 references 里的任何内容
```

装完 AI 应该报：**version 2.6.1 / references 10 个 / scripts 7 个**。
报不出来，说明解压多套了一层目录，或者放错了位置。

## 手动装（AI 装不了时）

1. 下载上面的 zip，解压得到 `drawing-review` 文件夹
2. 整个文件夹放进技能目录：
   - Trae：`C:\Users\<你>\.trae-cn\skills\`
   - WorkBuddy：`~/.workbuddy/skills/`
   - Claude Code：`~/.claude/skills/`
3. **保持目录结构**：`SKILL.md` 在 `drawing-review` 根下，`references/` 与 `scripts/` 与它同级

> ⚠️ 用系统自带的解压（右键 → 全部解压缩）。别用命令行 `unzip`，会把中文文件名解成乱码，`00-索引.md` 就点不开了。

## 装完必做：取机器码 + 填授权码

1. **取本机机器码**

   ```bash
   python scripts/ask_api.py --machine-id
   ```

   会输出一串 `M-XXXX-XXXX`，例如 `M-5514-D1FD`。
   **把这串发给作者申请授权码** —— 授权码和这台电脑绑死，换电脑要重新申请。

   > 同一台电脑上装多少个 AI 工具（WorkBuddy / Claude Code / Cursor / Trae…）
   > 算出来都是同一个机器码，**一个码可以多工具共用**。

2. **填授权码（推荐用 key.txt，不碰环境变量）**

   **A · 最简单：存成一个文件**（v2.6.2 起支持）

   在 `drawing-review/` 目录下（和 `SKILL.md` 同级）新建 `key.txt`，里面**只放一行**：

   ```
   skfg-你的授权码
   ```

   脚本会自动读它 —— 不用设环境变量、不用重开终端、重装也还在。

   **B · 环境变量**（老办法，仍支持，优先级高于 key.txt）

   **Windows · 命令行（CMD）**
   ```bat
   setx DRAWING_REVIEW_KEY "skfg-你的授权码"
   ```

   **Windows · PowerShell**
   ```powershell
   [Environment]::SetEnvironmentVariable("DRAWING_REVIEW_KEY","skfg-你的授权码","User")
   ```

   **Mac / Linux**
   ```bash
   export DRAWING_REVIEW_KEY="skfg-你的授权码"
   ```

   > ⚠️ 用 `set` / `export` 只在**当前窗口**有效，关掉或换个终端就没了 ——
   > 这就是"明明设了却说没有授权码"最常见的原因。要么用 `setx`，要么用上面的 key.txt。
   > 服务地址已内置，不用配。
   > 想让 AI 每次都自动带上，可以把这行写进系统环境变量，或者直接告诉 AI：
   > 「把 DRAWING_REVIEW_KEY 设为 skfg-你的授权码，然后用审图技能帮我审图」。

3. **自检连通**

   ```bash
   python scripts/ask_api.py --health            # 应返回 ok:true
   python scripts/ask_api.py --rules --ids R14   # 能返回规则说明 = 授权码有效
   ```

   - 返回 `ok:true` 但 `--rules` 报 402 → 脚本会打出**本机机器码**和**当前用的码**：机器码变了 = 换了电脑（一机一码，找作者换码）；机器码没变 = 码抄错或过期
   - 连不上 → 检查网络，或让 AI 直接读 `references/00-索引.md`

## 开始用

直接说「帮我审这套图」，AI 会按云端方法库逐步执行。
更好的说法是把三件事一次说清：

```
我装好审图 skill 了，你帮我审一套图。

图纸在 <你的图纸目录>，只审 <哪几个专业/哪几册>，一共 <多少> 张。

这是 <项目性质>，报告里不能出现项目名称、参建各单位名称、项目地址。

开始吧。
```

## 授权码说明

- **一个码绑一台电脑**：无论哪种码，一个授权码最终只认一台机器；同一台电脑上多个 AI 工具可共用一个码
- 码请勿转给他人：别人机器对不上，转过去也用不了
- **两种授权码**（发码方决定给你哪种）：
  - **首绑码**（推荐，粉丝用）：`skfg-20261230-XXXXXX-XXXXXXXX` —— 去掉机器码段，**第一次使用时自动绑定你这台电脑**，之后换电脑就失效。申请时不用报机器码
  - **绑机码**：`skfg-20261230-XXXXXX-XXXXXXXX-XXXXXXXX` —— 最后 8 位是机器码，需先跑 `--machine-id` 报给发码方
- 有效期**精确到日**，写在码里（例：`skfg-20261230-...` = 2026 年 12 月 30 日到期；**到期当天仍可用，次日起失效**）
- 到期后向作者申请新码即可
- 没有授权码时：**环境自检、图纸体检、报告模板这些本地能力照常可用**，只是调不了云端判定

## 付费说明（免费版）

- **判定规则库（19 条）+ 条目库（1,851 条：房建 1,571 / 道路 70 / 排水 77 / 桥梁 91 / 市政通用 42）+ 方法库（10 主题 83 段，约 7.7 万字）在云端**，按需调用
- 授权码无效 → 返回 **402 Payment-Needed**
- 价格见 SkillHub 页面；测试期联系作者领 Key

## 使用纪律

- 不要改写 SKILL.md
- 不要一次读完所有 references
- 用户说「审图」类需求 → 先读 SKILL.md，再按索引走
- **出报告前必须调 `ask_api.py --review` 过一遍五问**

---

*范工AI实战 · 抖音号 80823565662*
