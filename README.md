<div align="center">

# 🔮 Olivia · 奥莉薇娅

**首先是塔罗师，其次才是心理咨询师。** 咨询与 NVC（非暴力沟通）是工具，不是主业——它们让解牌更贴合人，但不喧宾夺主。

Olivia（奥莉薇娅，女性）是一个**独立人格包 + 本地网页 Agent**。她不做预言、不替人做决定，只按传统韦特（Rider–Waite–Smith）牌意与标准牌阵，陪你把说不出口的东西看清楚。

[快速开始](#-快速开始) · [功能一览](#-功能一览) · [人格设定](#-人格设定) · [在其他平台使用](#-在其他平台使用) · [隐私与数据](#-隐私与数据)

</div>

---

## ✨ 特性一览

| | |
|---|---|
| 🃏 **纯本地抽牌** | 78 张 RWS 牌 + 39 种牌阵，代码不放回随机抽取，先出牌再问问题，模型无法挑牌/换牌/编牌 |
| 💬 **流式对话** | 打字机般的流式输出，温柔克制、带 NVC 底色的女性塔罗师口吻 |
| 🧠 **长期记忆** | 画像 / 线索 / 对话 / 抽牌历史分层存储，相关记忆每轮自然注入 |
| 📚 **专业知识库** | 78 张牌义 + 解牌方法 + 咨询技术，关键词自动检索 |
| 🗂 **个人知识库** | 主动策展的笔记，可归档、检索、导出 Markdown |
| 👁 **视觉识别** | 任意 OpenAI 兼容 VLM 看图，主模型仍是纯文本，不假装看见 |
| ⏰ **主动关怀与盯事** | 定时任务 + 条件触发（网页/RSS/JSON/天气），Windows 桌面通知 |
| 🔒 **零第三方依赖** | Agent 仅用 Python 3 标准库；数据全部留在本机 |

---

## 🚀 快速开始

### 安装（Windows，推荐）

1. 从 [Releases](../../releases) 下载 **`Olivia-setup.exe`**，双击。
2. 选安装目录（默认 `%LOCALAPPDATA%\Olivia`）、是否开机自启。
3. 安装器会自动建快捷方式、后台启动服务并打开 <http://127.0.0.1:8765>。
4. 点右上角「设置」填入自己的 API key（DeepSeek 等）即可。

> 无 Python 环境？安装器会给出提示：先装 [Python 3](https://www.python.org/downloads/) 并勾选 **Add Python to PATH**，再重新双击安装器。

### 直接跑源码

```bash
cd agent
python server.py          # 只依赖 Python 3 标准库
```

打开 <http://127.0.0.1:8765>，在「设置」中配置后端：

- **DeepSeek**（默认）：填自己的 key（platform.deepseek.com 申请），预设 `deepseek-flash`（快、便宜，默认）、`deepseek-v4-pro`（更强）、`deepseek-chat`（旧版兼容）；模型框也可手填 `deepseek-reasoner` 等。
- **Ollama**：先 `ollama serve` 并拉好模型，`base_url` 填 `http://127.0.0.1:<端口>/v1`，key 留空。
- 也支持任意 OpenAI 兼容端点。

key 只存本机 `agent/config.json`（已 gitignore）。

---

## 📁 仓库结构

```
.
├── prompts/                    # 人格提示词（始终在线）
│   ├── persona.zh.md / persona.en.md
│   ├── tone.zh.md / tone.en.md  # 语气系统：女性塔罗师口吻 + NVC
│   └── prophecy.zh.md          # 预言模式覆盖层（娱乐，开启时加载）
├── skills/tarot-counselor/
│   └── SKILL.md                # 技能格式（按需触发）
├── agent/                      # 本地网页 Agent
│   ├── server.py               # HTTP 服务 + 全部 API 路由
│   ├── llm.py                  # 后端调用（流式 / 工具调用 / 补完）
│   ├── tools.py                # 工具定义与执行
│   ├── spreads.py              # 牌阵库（39 个牌阵，牌位与几何唯一来源）
│   ├── cards/                  # 78 张 RWS 牌面图（公有领域扫描，420px）
│   ├── knowledge.py            # 专业知识库检索 + 牌意解析
│   ├── memory.py               # 长期记忆
│   ├── scheduler.py            # L3 定时关怀 + 主动触发
│   ├── watchers.py             # L3 条件触发（盯事）
│   ├── plugin_kb.py            # 个人知识库插件
│   ├── plugin_vision.py        # 视觉识别插件（云端 VLM 桥接）
│   └── data/                   # *.db、plugins.json（gitignore，绝不提交）
├── knowledge/                  # 专业知识库（见 INDEX.md）
│   ├── meanings/ 78 张 RWS 牌义 + 解牌方法
│   ├── spreads/  牌阵速查表与选阵原则
│   └── skills/ modalities/ issues/ ethics/ supervision/
├── installer/                  # 单文件 exe 安装器源码与构建脚本
└── README.md
```

两种人格形态：

| 形态 | 文件 | 行为 | 适合 |
|---|---|---|---|
| **提示词（始终在线）** | `prompts/persona.*.md` | 默认就是 Olivia，纯技术/事实/危机时让位 | ChatGPT 自定义指令、Claude Project、自建 Agent 的 system prompt |
| **技能（按需触发）** | `skills/tarot-counselor/SKILL.md` | 平时是普通助手，求占/倾诉/求助时才加载 | 支持 skill 的 Agent（Claude Code、DSH 等） |

---

## 🔮 人格设定

三者有主次，不是平均混合：

1. **塔罗师（核心）**——抽牌、牌阵、解牌是工作主体。
2. **心理咨询师（辅助）**——让解牌更贴合人；来访者主体性至上，不给定性判决、不替人做决定。
3. **NVC（工具）**——观察 → 感受 → 需要 → 请求，自然说人话，不喊术语；情绪激烈时才显式拆解。

### 抽牌规则

牌必须客观随机，与对来访者的印象无关——不挑牌、不换牌、不补牌。系统本地随机抽取（时间戳 / 报数 / 实体牌均可，需告知用了哪种），逆位同样客观决定；抽到什么解什么，说对不上就核对牌意，不换牌。

**两阶段抽牌**：说「抽牌」先列出 39 种牌阵让你点选（全程本地、不需要 API key）→ 点选后客观抽牌并展示牌面，此时**不解读**，只温和地问「你有什么问题吗？」→ 回答后，Olivia 才只对这一副牌、围绕你的问题解读。之后如需再抽，重新开始即可。

**牌阵**：共 39 个，覆盖快速牌阵（单张 / 三张）、专业布局（凯尔特十字）、咨询牌阵（关系 / 二选一）、季节 / 世俗 / 次要 / 神秘等布局，定义集中在 `agent/spreads.py`，每个牌位都带「这个位置在问什么」。原则是**先用最简单的能回答问题的牌阵**，问题复杂才升级。

**牌面图**：78 张韦特牌面（`agent/cards/`，公有领域扫描）抽牌后随气泡显示，逆位旋转 180°，按各牌阵的**传统几何位置**摆放；鼠标悬停才浮出该位置在问什么，底部牌位表可一次看全。

**解读规则**：每张牌按 **原本牌意 → 牌阵位置 → 对应问题 → 落到情境** 解读，落脚必须由牌意推出。禁止主观投射、编造牌意、粉饰凶牌、预言具体事件。

**边界**：不预测具体事件；不做医疗/法律/财务建议；不扮演通灵；不替人做人生决定；不做道德评判。**急性危机**（自伤/安全风险/侵害）立即跳出塔罗师角色、给求助资源、不抽牌不解读——这条压过所有规则。

> 元规则：**牌不开口，人开口**。

### 🔮 预言模式（仅供娱乐）

默认关闭。开启后用"展望 / 趋势"口吻解牌，每段都附 **"仅供娱乐"** 提示，措辞保持"倾向 / 可能"，顶栏常驻标记提醒。安全边界不随模式放开。覆盖层在 `prompts/prophecy.zh.md`，仅开启时加载。

---

## 🛠 功能一览

### 客观抽牌与牌义

标准 78 张韦特牌库（22 大阿卡纳 + 56 小阿卡纳），由代码**不放回随机**抽取，同一牌阵不重复。抽牌是**纯本地动作**，不需要 API key；只有解读才调用大模型。牌义笔记见 `knowledge/meanings/`，依据《塔罗智慧》《21世纪的塔罗书》《其实你已经很塔罗了》三书要义，用**原创中文按 RWS 传统重写**。

### 专业知识库

`knowledge/` 是辅助解牌的资料库（结构见 [`knowledge/INDEX.md`](knowledge/INDEX.md)）：`meanings/` 78 张牌义与解牌方法、`skills/` 咨询技术、`modalities/` 流派、`issues/` 议题、`ethics/` 伦理与危机、`supervision/` 督导视角。一主题一文件，检索按关键词自动命中，改动即时生效。

### 长期记忆

数据只存在 `agent/data/memory.db`（gitignore）。四层结构：稳定画像（`profile`）、长期线索（`facts`，规则抽取零延迟）、会话原文（`messages`）、抽牌历史（`draws`）。相关记忆每轮注入 system prompt，Olivia 会自然提起，不生硬复述；危机内容不进事实库。点顶栏「记忆」可查看/固定/添加/删除线索、看抽牌历史、整理去重、一键开关。

### 个人知识库插件

主动策展的"档案"——重要笔记、清单、决定，长期留存、可检索、可导出（存 `agent/data/kb.db`）。聊天里说"**记到知识库**"自动归档；点顶栏「知识库」可手动增/置顶/删、从记忆归档（幂等）、导出 Markdown。

### 视觉识别插件

不依赖本地模型。任意 OpenAI 兼容视觉大模型（OpenAI / 通义 VL / 智谱 GLM-4V / Moonshot / 自建网关）填 key 即用：主模型保持纯文本，VLM 生成的客观中文描述作为文字线索喂给主模型，不"假装看见"。密钥只存本机 `agent/data/plugins.json`。

### 工具调用

真 **agentic loop**：模型自己判断何时调用工具，执行后回填继续，前端用 ⚙ 徽章显示每步。

| 工具 | 作用 | 安全约束 |
|---|---|---|
| `search_knowledge` | 检索 `knowledge/` 专业资料 | 只作专业判断依据，不从牌里来 |
| `save_memory` | 存偏好/边界/「请记住」 | 危机内容拒绝入库 |
| `crisis_check` | 检测自伤/轻生等急性危机信号 | 命中即跳出角色，走安全流程 |
| `save_note` / `search_notes` | 归档/检索个人知识库 | 用户主动策展，危机内容不入库 |

> 抽牌由系统在本地完成，不占用工具调用；设置里的 `tools_enabled` 开关只管上面这些工具。

### 主动关怀与盯事（L3）

对应 [Anthropic《Building always-on agents》](https://claude.com/resources/articles/building-always-on-agents) 四原语：timers（`tasks` 表：每天/每周/每隔 N 分钟/仅一次）、inbox（`events` 表）、outbox（`messages` 表 + Windows 桌面通知）、permissions（总开关 + 静默时段 + 每任务开关）。后台线程每 30 秒检查到期任务，写一条温暖克制的中文关怀消息；默认**关闭**，全部本地运行。

**盯事 · 条件触发**（`agent/watchers.py`，纯 stdlib 不调模型）：读外部数据 → 规则判断 → 满足条件才提醒。数据源：网页/文本（包含/不含/正则）、RSS/Atom（新条目）、JSON 接口（字段路径取值比较）、天气（Open-Meteo 免 key，>、≥、<、≤）。每条盯事有检查间隔 + 触发冷却，首次检查只建基线不误报。数据在 `agent/data/watchers.db`，在「关怀」面板管理。

> 要让 L3 长期生效，用安装器勾选"开机自启"即可让服务常驻后台。

---

## 🌐 在其他平台使用

### 作为提示词

把 `prompts/persona.zh.md` 的内容放进：ChatGPT 自定义指令 / Claude Project 指令 / 自建 Agent 的 system prompt。人格始终在线；`tone.zh.md` 可一并作为语气层注入。

### 作为技能

把 `skills/tarot-counselor/` 整个目录放进 Agent 的技能目录：

- **Claude Code**：`~/.claude/skills/` 或项目的 `.claude/skills/`
- **DSH**：`~/.dsh/skills/`

平时是普通助手，求占/倾诉/求助时才加载 Olivia。

---

## 🔒 隐私与数据

- **本地优先**：所有对话、记忆、知识库、key 只在本机；不上传、不经过中间服务器。
- **打包零泄漏**：安装包排除 `config.json`（API key）、`agent/data/*.db`（记忆/知识库）、缓存。
- **可控可删**：记忆面板可查看/删除单条线索；删除安装目录即清除 key 与数据。
- `agent/data/`、`*.db`、`agent/config.json`、`agent/olivia.pid` 均已 gitignore。

---

## 📄 License

MIT。欢迎 fork、改、拿去用。
