<div align="center">

# OpenCode AIRP SillyTavern

**OpenCode 作为 AI 叙事引擎，直驱中文角色扮演。**

[![Python](https://img.shields.io/badge/Python-3.x-3776AB?style=for-the-badge&logo=python&logoColor=white)](https://www.python.org/)
[![OpenCode](https://img.shields.io/badge/OpenCode-编排引擎-d97706?style=for-the-badge&logo=anthropic&logoColor=white)](https://github.com/anthropics/opencode)
[![License](https://img.shields.io/badge/License-MIT-yellow?style=for-the-badge)](LICENSE)
[![Status](https://img.shields.io/badge/Status-Active-brightgreen?style=for-the-badge)]()

</div>

---

## 🙏 致谢与前言

### 致谢
感谢 **[梁文峰（梁圣）](https://www.deepseek.com)** 开源并大幅降价的 **DeepSeek-V4-Pro**。1M 上下文窗口、相对低廉的价格、稳定且强大的注意力机制——没有这个模型，这个项目不可能跑起来。

感谢社区 **Logan** 提出的原始 idea。我只不过在他的想法之上，试着动手做了一下。

感谢 **Damages** —— 本项目最核心的前端桥接层：聊天记录、MVU 变量引擎和内容渲染，全部出自他手。没有 `web-frontend/handler.py`，浏览器里的每一个字都不可能出现在你面前。

本项目同样站在巨人的肩膀上——角色卡格式来自 **SillyTavern**，叙事编排依赖 **OpenCode**。感谢这些开源项目。

### 关于本项目

**OpenCode AIRP SillyTavern 不是 SillyTavern 的替代品。**

SillyTavern 是一个成熟、全面、久经考验的角色扮演前端，本项目无意也无力与之竞争。这是一个**实验性叙事引擎**，核心思路只有一条——

> 把角色卡、世界书、记忆、变量全部放在本地文件夹里，让 OpenCode 自己看着办。

不用精细的 prompt engineering、不用复杂的 pipeline、不用层层过滤——就把 OpenCode 当成 RP 引擎本身，靠模型的原始能力硬推叙事。

### 维护声明

作者现实生活繁忙，**不保证按时更新**。但会定时查看 Issue，有好思路会不定期更新。欢迎提想法、报 bug、交 PR。

---

## 📖 目录

- [致谢与前言](#-致谢与前言)
- [简介](#-简介)
- [核心特性](#-核心特性)
- [快速开始](#-快速开始)
- [目录结构](#-目录结构)
- [技术栈](#-技术栈)
- [数据流](#-数据流)
- [文风与记忆](#-文风与记忆)
- [角色卡使用](#-角色卡使用)
- [Web 功能](#-web-功能)
- [NovelAI 生图](#-novelai-生图)
- [常见问题](#-常见问题)
- [上传 GitHub 前检查](#-上传-github-前检查)
- [术语表](#-术语表)

---

## 💡 简介

**OpenCode AIRP SillyTavern** 是一个以 OpenCode 为编排引擎、Python 标准库为后端的角色扮演系统。

你不需要写 prompt——OpenCode 本身就是 RP 引擎。它读取角色卡、管理对话历史、按选定文风生成叙事，并通过 Web 前端与用户互动。

> 将 OpenCode 的代码分析和工具调用能力，转化为 AI 叙事创作的编排层。

把写好的人设、世界书放进文件夹，浏览器打开，就开始一段故事。

---

## ✨ 核心特性

<table>
<tr>
<td width="50%">

### 🎭 角色卡直读
拖入 SillyTavern PNG 角色卡，自动解析 `tEXt/chara` chunk → 提取角色设定、开场白、世界观。支持 `card.json`、JSON 角色卡和纯文本材料导入。

### 📖 世界书按需触发
世界书条目通过 `.worldbook_index.json` 轻量索引常驻。当叙事触及索引中的话题时，AI 按关键词 Grep 检索相关条目，每轮最多 2-3 条——不堆砌、不遗漏。

### 🖊️ 文风配置系统
Markdown 格式风格文件，支持通过 `skills/styles/` 和 `skills/styles/profiles/` 维护可切换文风。可通过对话分析小说/作者文风自动生成新配置。

### ⚙️ Web 控制面板
前端提供角色卡设置隐藏/展开、聊天区域宽度拖拽调整、移动端自动适配。

</td>
<td width="50%">

### 🔄 重掷与回退
一键重掷最后一轮 AI 回复，或回退到任意历史轮次重新输入。

### 🎬 开场白切换
切换角色卡时自动从角色卡 `first_mes` 提取开场白。前端支持多开场白切换。

### 📊 MVU 变量系统
完整支持卡作者原生的 `<UpdateVariable>` + `<JSONPatch>` 格式。replace / delta / insert / remove / move 五种操作。正文中 `{{getvar::路径}}` 模板宏实时引用变量当前值。

### 📏 跨会话记忆
六种记忆文件 + 世界书索引存在卡片文件夹下的 `memory/` 目录中，**关闭后明日再开也能接着剧情继续玩**。

</td>
</tr>
<tr>
<td width="50%">

### 🎯 双 OpenCode 架构
一个固定端口实例（4096）专门回复前端消息，一个普通实例用于修改角色卡、文风和项目文件。职责分离，互不干扰。

### 👥 世界后台推进
NPC 可以在用户视线外主动行动。每轮都要有可感知的状态变化、信息推进或关系变化——日常场景可以慢，但不能空转。

</td>
<td width="50%">

### 🎨 可选 NovelAI 生图
回复中出现 `[img: english tags]` 时，通过 Web 按钮或脚本调用 NovelAI API 生成插图。

### 📦 本地优先
角色卡、聊天记录、变量、记忆和设置都保存在项目目录内，一个文件夹就是一张卡的完整世界。便于备份和迁移。

</td>
</tr>
</table>

### 🧠 跨会话记忆系统

五种记忆文件 + 两种索引存在卡片文件夹下的 `memory/` 目录中：

| 文件 | 作用 | 更新频率 |
|------|------|---------|
| `memory/project.md` | 剧情进度、未落地伏笔、NPC 状态、下阶段方向 | 每轮自动 |
| `memory/reference.md` | 世界观规则、角色卡核心设定、关键地点 | 几乎不变 |
| `memory/feedback.md` | 用户偏好（文风/节奏/NSFW 边界）、踩过的坑 | 偶尔追加 |
| `memory/user.md` | 用户角色当前状态（外貌/衣着/关系变化） | 低频更新 |
| `memory/story_plan.md` | 长远剧情规划——节拍定位/伏笔清单/下阶段方向 | 按需更新 |
| `memory/.worldbook_index.json` | 世界书条目关键词索引，AI 按需 Grep 检索 | 启动时生成 |

启动时自动读取全部记忆文件重建叙事上下文，每轮生成后自动更新剧情记忆。

---

## 🚀 快速开始

### 你需要准备

| 你需要 | 怎么获取 |
|--------|---------|
| **Python 3.x** | [python.org](https://www.python.org/) 下载安装（安装时勾选"Add Python to PATH"） |
| **OpenCode** | 安装并配置好 OpenCode CLI |
| **角色卡（可选）** | `.png` 或 `.json` 格式的 SillyTavern 角色卡 |

### 5 分钟从零开始

**① 放卡片**

在项目根目录的 `角色卡/` 下新建一个文件夹，把角色卡放进去：

```
角色卡/
└── 我的角色/
    ├── card.json
    └── worldbooks/main.json
```

**② 启动回复引擎**

```powershell
cd "C:\Users\hu\Desktop\RP\Opencode- AIRP-SillyTavern"
opencode --port 4096
```

这个 OpenCode 负责生成所有前端回复。不要在这个窗口里执行 `/rp`。

**③ 启动编辑/控制 OpenCode**

在第二个终端进入同一目录：

```powershell
cd "C:\Users\hu\Desktop\RP\Opencode- AIRP-SillyTavern"
opencode
```

然后输入：

```
/rp
```

`/rp` 会启动本地 Web 服务（默认端口 8765，被占用自动顺延）。实际端口会写入 `web-frontend/server-port.txt`。

**④ 打开浏览器**

访问 `http://127.0.0.1:8765/index.html`，在输入框打字，点提交。AI 会在几秒到几十秒内生成回复。

> 你会看到：页面顶栏显示角色名/状态，中间是叙事内容，下面是输入框。打完字提交后，等待片刻，AI 回复会自动出现在页面上。

**之后怎么继续玩？** 两个终端都不要关。换个角色卡就输入 `/play <卡片名>`，修改世界书/文风就在编辑 OpenCode 里直接改。

---

### 运行模式：双 OpenCode 分工

| 实例 | 启动方式 | 职责 |
|------|---------|------|
| **回复引擎** | `opencode --port 4096` | 接收前端消息 → 读取 AGENTS.md/角色卡/世界书/记忆/变量 → 生成回复 → 写入 `web-response.txt` |
| **编辑控制** | `opencode` | 执行 `/rp`、`/play` 等命令 → 修改角色卡/世界书/文风/项目文件 |

两个实例的职责不能混。回复引擎只负责叙事生成，编辑引擎只负责文件操作和命令执行。

---

### 切换角色卡

```text
/play example-card
```

查看角色卡列表：

```text
/cards
```

---

## 📂 目录结构

```
opencode-AIRP-SillyTavern/
├── AGENTS.md                  # 🧠 回复引擎核心叙事规则
├── README.md                  # 📄 本文件
├── .env.example               # 🔑 NovelAI API Key 示例
├── .gitignore                 # 🚫 Git 忽略规则
├── .opencode/
│   └── commands/              # ⚡ OpenCode 自定义命令
│       ├── rp.md              #   /rp 启动 Web 模式
│       ├── play.md            #   /play 切换角色卡
│       ├── cards.md           #   /cards 列出角色卡
│       ├── img.md             #   /img 生图辅助
│       └── 退出RP.md          #   退出 Web 服务
├── web-frontend/
│   ├── index.html             # 🖥️ 主前端界面
│   ├── server.py              # 🌐 本地 Web/API 服务
│   ├── handler.py             # 🔧 聊天记录、MVU、内容渲染
│   ├── card_store.py          # 📥 角色卡读写
│   ├── airp_context.py        # 🔍 上下文快照与世界书激活
│   └── opencode_client.py     # 🔗 OpenCode TUI API 注入客户端
├── airp-sillytavern/
│   ├── runtime/               # 🏃 AIRP 核心运行时
│   ├── schemas/               # 📐 状态结构定义
│   ├── templates/             # 📋 角色卡、世界书、人格模板
│   └── references/            # 📘 SillyTavern 结构参考
├── skills/
│   ├── image-gen.md           # 🎨 生图提示词规则
│   ├── novelai-gen.md         # 🖼️ NovelAI 生图规则
│   └── styles/                # 🖊️ 文风预设与文风配置
│       └── profiles/          #   文风配置文件
├── scripts/
│   ├── extract-img.py         # 📤 从文本中提取 [img: ...]
│   └── novelai-generate.py    # 🤖 调用 NovelAI API
├── 角色卡/
│   └── example-card/          # 🃏 示例角色卡
│       ├── card.json
│       └── worldbooks/main.json
└── 预设/                      # 📦 可选 SillyTavern 预设参考
```

> 运行时自动生成的文件（`current-card.txt`、`chat_log.json`、`variables.json`、`memory/` 等）已加入 `.gitignore`。

---

## 🛠️ 技术栈

<div align="center">

| 层 | 技术 | 说明 |
|:---:|------|------|
| 🧠 **AI 编排** | OpenCode | 读取 AGENTS.md 规则，调用工具链执行 |
| 🌐 **后端** | Python `http.server` | 标准库，零外部依赖 |
| 🖥️ **前端** | 原生 HTML/CSS/JS | 无框架，动态内容注入 |
| 📦 **数据** | JSON + Markdown + JS | 聊天记录/变量用 JSON，文风用 MD，状态用 JS |
| 🃏 **角色卡** | SillyTavern PNG/JSON | `tEXt/chara` chunk → base64 → JSON |

</div>

---

## 🔄 数据流

```
浏览器 Web 前端
  -> web-frontend/server.py
  -> http://127.0.0.1:4096 OpenCode TUI API
  -> 回复引擎 OpenCode
  -> web-frontend/web-response.txt
  -> web-frontend/handler.py
  -> 角色卡/{card}/chat_log.json
  -> 角色卡/{card}/variables.json
  -> 角色卡/{card}/memory/
  -> 浏览器刷新显示
```

### 说人话版：你打一个字，背后发生了什么？

不用看懂上面那张图。用大白话说，从你点"提交"到看到 AI 回复，整个过程是这样的：

```
你在浏览器输入 "你好" → 点提交
                ↓
server.py 收到你的话，注入到回复引擎 OpenCode (端口 4096)
                ↓
OpenCode 开始干活：
  ✦ 读取 current-card.txt，确认当前是哪个角色卡
  ✦ 翻翻最近几轮聊了什么（chat_log.json）
  ✦ 检查有没有世界书条目跟当前场景相关
  ✦ 想想 NPC 状态、记忆、剧情规划
  ✦ 按你选的文风写叙事回复
  ✦ 更新变量（时间推进、好感变化等）
  ✦ 如果画面有价值，末尾补上 [img: ...]
                ↓
把写好的回复写入 web-frontend/web-response.txt
                ↓
handler.py 把回复组装成网页能显示的格式 → 前端自动刷新
                ↓
你看到 AI 的回复出现在浏览器里 ✨
```

整个过程快则几秒，慢则几十秒（取决于回复长度和复杂度）。

---

## 🖊️ 文风与记忆

文风文件位于 `skills/styles/` 和 `skills/styles/profiles/`。回复引擎会根据当前设置、角色卡、最近剧情、世界书触发项和 memory 文件共同生成回复。

每张角色卡运行后会自动维护五类记忆文件（见[跨会话记忆系统](#-跨会话记忆系统)）。记忆文件属于运行时数据，默认不上传 GitHub。

---

## 🃏 角色卡使用

角色卡统一放在 `角色卡/{card-id}/`：

```
角色卡/my-card/
├── card.json
└── worldbooks/main.json
```

可以把 SillyTavern PNG 角色卡、JSON 角色卡、世界书 JSON 或纯文本材料放入角色卡目录，再通过 `/play <card-id>` 触发导入和规范化。

---

## 🌐 Web 功能

Web 前端提供以下能力：

| 功能 | 说明 |
|------|------|
| 发送消息 | 输入框打字 → 点提交 → 等待 OpenCode 回复 |
| 自动聊天记录 | 对话自动写入 chat_log.json |
| 变量更新 | 自动处理 `<UpdateVariable>` / `<JSONPatch>` |
| 状态显示 | 显示当前变量、消息数量、角色卡信息 |
| 角色卡编辑 | 前端面板直接修改角色卡字段 |
| 世界书编辑 | 前端面板编辑世界书条目 |
| 上下文预览 | 预览世界书触发结果与当前上下文 |
| 开场白切换 | 多开场白之间自由切换 |
| 重掷 | 删除最后一轮 AI 回复，重新生成 |
| 回退 | 回滚到指定历史消息 |
| 生图 | 生成或重试插图任务 |
| 布局调整 | 隐藏/展开角色卡设置面板、拖拽调整聊天区域宽度 |
| 移动端适配 | 自动适配移动端布局 |

---

## 🎨 NovelAI 生图

如需使用 NovelAI 生图，先复制环境变量文件：

```powershell
copy .env.example .env
```

填写：

```text
NOVELAI_API_KEY=你的 NovelAI API Key
```

回复中出现：

```text
[img: 1girl, cinematic lighting, detailed background]
```

即可在 Web 前端点击"生成插图"，或通过命令调用脚本：

```powershell
python scripts/extract-img.py 角色卡/example-card/rp-log.txt -g --latest-only
```

---

## 🆘 常见问题

### 浏览器打不开 http://127.0.0.1:8765/index.html？

1. 确认编辑 OpenCode 中输入了 `/rp` 且服务已启动
2. 检查 `web-frontend/server-port.txt` 确认实际端口
3. 如果端口被占用，服务会自动顺延——去看 `server-port.txt` 里写的到底是多少

### 回复一直没出现？

1. 确认你真的点了"提交"按钮
2. 等待 30-60 秒——AI 生成需要时间，尤其是长回复
3. 如果超过 2 分钟还没反应，检查回复引擎 OpenCode（端口 4096）的终端有没有报错

### 我没有角色卡，能试用吗？

可以。项目自带 `角色卡/example-card/` 示例角色卡。输入 `/play example-card` 即可开始。

### 怎么换一张卡片玩？

在编辑 OpenCode 中输入 `/play <卡片名>`。前端会自动切换。

> 注意：不要同时开着两个编辑 OpenCode 实例——它们会抢同一个 Web 服务端口。

### 怎么备份我的进度？

卡片文件夹里的 `chat_log.json`（完整聊天记录）和 `memory/` 目录（剧情记忆）就是全部进度。复制整个卡片文件夹到别处即可备份。

### 回复质量不好怎么办？

- 换一个文风：修改文风配置
- 调整变量：通过前端或命令修改变量
- 重掷当前回复：前端点击重掷按钮

---

## 📤 上传 GitHub 前检查

建议上传前确认不要包含以下内容：

- `.env`
- `.opencode/node_modules/`
- `__pycache__/`
- `web-frontend/*.tmp`
- `web-frontend/web-response.txt`
- `角色卡/*/chat_log.json`
- `角色卡/*/memory/`
- `角色卡/*/generated/`
- 私人角色卡、私人世界书、私人聊天记录

项目已提供 `.gitignore`，如果使用 Git 上传，运行时文件会被自动忽略。

---

## 📖 术语表

| 术语 | 全称 | 一句话解释 |
|------|------|-----------|
| **RP** | Role-Playing | 角色扮演——你扮演一个角色，AI 扮演其他角色和世界 |
| **MVU** | MagVarUpdate | SillyTavern 的变量更新系统，用 JSONPatch 格式管理角色数值变化 |
| **JSONPatch** | — | 一种描述 JSON 数据修改的标准格式（replace/add/remove 等操作） |
| **世界书** | World Book | 按关键词触发的世界观设定条目集合，由 SillyTavern 定义 |
| **角色卡** | Character Card | 含角色设定、开场白的 PNG/JSON 文件，由 SillyTavern 定义 |
| **NPC** | Non-Player Character | 非玩家角色——AI 控制的配角、路人、反派 |
| **memory/** | — | 卡片文件夹下的记忆目录。存剧情进度、世界观、用户偏好 |
| **重掷** | Re-roll | 删除 AI 最后一轮回复，用同样的用户输入重新生成一次 |
| **开场白** | First Message | 角色卡中的第一条消息，定义故事起始场景 |
| **文风** | Style Profile | Markdown 格式的风格规则文件，控制 AI 的叙事语调和句式 |

---

## 📄 许可

本项目建议使用 MIT License。正式开源前请自行确认角色卡、预设、世界书和第三方素材的授权情况。

---

<div align="center">

**⚡ 把角色卡和世界书放进文件夹，让 OpenCode 替你叙述一个世界 ⚡**

</div>
