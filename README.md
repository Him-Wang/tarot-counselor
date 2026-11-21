<div align="center">

# 🔮 Olivia · 奥莉薇娅

**先是一名塔罗师，其次才借咨询与 NVC 让解牌更贴近人。**

Olivia（奥莉薇娅，女性）是一位**可独立使用的人格包 + 本地网页 Agent**。她不预言、不替人做决定，只依据传统韦特（Rider–Waite–Smith）牌意与标准牌阵，陪你把说不出口的东西看清楚。

[快速开始](#-快速开始) · [她怎么解牌](#-她怎么解牌) · [功能](#-功能) · [目录](#-目录) · [换个地方用她](#-换个地方用她) · [隐私](#-隐私)

</div>

---

## 为什么是她

- **牌是主角，人是中心**：解牌是主体，咨询与 NVC（非暴力沟通）只是让牌意落到真实处境的工具，不喧宾夺主。
- **客观，可复核**：78 张牌代码不放回随机抽取，抽牌纯本地、不需要 API key；每次都给出随机种子，可一键复现同一副牌，自证没有临时挑牌。
- **先出牌，后问问题**：抽牌那一刻不解读，等你说出真正想问的事，她才只针对这副牌回答。
- **形体自由**：同一个灵魂，既能作为常驻 system prompt，也能作为按需加载的 skill，还能在本地网页里开着用。

---

## 🚀 快速开始

### Windows 一键安装（推荐）

1. 从 [Releases](../../releases) 下载 **`Olivia-setup.exe`**，双击。
2. 选安装目录（默认 `%LOCALAPPDATA%\Olivia`）与是否开机自启。
3. 安装器自动建快捷方式、后台静默启动服务、打开 <http://127.0.0.1:8765>。
4. 点右上角「设置」填入自己的 API key（DeepSeek 等）即可开始解读。

> 安装器需要本机有 Python 3 并勾选了 **Add Python to PATH**；没有会给出提示。装完可到 [python.org](https://www.python.org/downloads/) 下载。

### 直接跑源码

```bash
cd agent
python server.py          # 仅依赖 Python 3 标准库
```

打开 <http://127.0.0.1:8765>，在「设置」里选后端：

| 后端 | 配置 |
|---|---|
| **DeepSeek**（默认） | 填自己的 key（platform.deepseek.com 申请）；预设 `deepseek-flash`（快而省，默认）、`deepseek-v4-pro`、`deepseek-chat`，模型框也可手填 `deepseek-reasoner` |
| **Ollama** | `ollama serve` 并拉好模型，`base_url` 填 `http://127.0.0.1:<端口>/v1`，key 留空 |
| 其他 | 任意 OpenAI 兼容端点均可 |

key 只存本机 `agent/config.json`（已 gitignore）。**抽牌本身不需要 key**，只有解读才调用大模型。

---

## 🔮 她怎么解牌

### 两阶段流程

1. 你说「抽牌」→ 列出 **39 种牌阵**供你点选（悬浮可看每个牌位的含义），全程本地、零 API 调用。
2. 点选后客观抽牌、按传统几何摆牌并展示牌面，此时**不解读**，只问一句「你有什么问题吗？」。
3. 你给出问题后，她才只对这一副牌、围绕这个问题解读。想再抽，重新开始即可。

### 解牌方法

- 每张牌按 **原本牌意 → 牌阵位置 → 对应问题 → 落到情境** 解读，落脚必须由牌意推出。
- 两张以上连读时，参考 `knowledge/meanings/牌间关系.md`：从**元素相处、数字阶段、大小牌对位、宫廷牌看人、叙事弧线**五个角度看牌与牌的关系——视角而非公式，不可覆盖牌面本身。
- 建议一定**具体到时间与动作**（"今晚睡前把那句话先写下来"），不说"顺其自然""保持平衡""一切都会好"这类正确的废话。
- 禁主观投射、编造牌意、粉饰凶牌、预言具体事件。逆位有受阻 / 内化 / 过度或不足 / 需调整四种读法，按情境取用。

### 牌阵与牌面

共 **39 个牌阵**，覆盖快速（单张 / 三张）、专业（凯尔特十字）、咨询（关系 / 二选一）、季节与神秘布局等，定义集中在 `agent/spreads.py`，每个牌位自带「这个位置在问什么」。原则是**先用最简单的能回答问题的牌阵**，复杂才升级。

78 张韦特牌面（`agent/cards/`，公有领域扫描）随牌气泡显示，逆位旋转 180°，按各牌阵的传统几何摆放；悬浮才浮出该位置含义，底部牌位表可一次看全。

### 安全边界

急性危机（自伤 / 轻生 / 受侵害 / 伤害他人）由独立闸门 `agent/safety.py` 在服务端统一拦截，**早于抽牌、早于模型、早于记忆写入**：直接跳出塔罗师角色，给求助资源，不抽牌不解读。中文句式覆盖"他打我了"这类直白说法，并处理"我不会自杀的"这类否定。此外不预测具体事件、不做医疗 / 法律 / 财务建议、不扮演通灵、不替人做人生决定。

> 元规则：**牌不开口，人开口。**

---

## ✨ 功能

| | |
|---|---|
| 🃏 **客观抽牌** | 78 张 RWS + 39 牌阵，不放回随机、带复现种子；纯本地、零 API key |
| 💬 **流式对话** | 打字机式输出，温柔克制、带 NVC 底色的女性口吻，轻拟态界面 |
| 🧠 **长期记忆** | 画像 / 线索 / 对话 / 抽牌历史分层存储，相关记忆每轮自然注入 |
| 📚 **专业知识库** | 78 张牌义 + 解牌方法 + **牌间关系** + 咨询技术，关键词自动检索 |
| 🗂 **个人知识库** | 主动策展的笔记，可归档、检索、导出 Markdown |
| 👁 **视觉识别** | 任意 OpenAI 兼容 VLM 看图，主模型仍是纯文本，不假装看见 |
| ⏰ **主动关怀与盯事** | 定时任务 + 条件触发（网页 / RSS / JSON / 天气），Windows 桌面通知 |
| 🔒 **零第三方依赖** | Agent 仅用 Python 3 标准库；数据全部留在本机 |

### 分层人格

| 层 | 文件 | 作用 |
|---|---|---|
| 人格（始终在线） | `prompts/persona.*.md` | 她是谁、塔罗 / 咨询 / NVC 的主次与边界 |
| 语气（始终在线） | `prompts/tone.*.md` | 怎么说：真实女性口吻 + 自然 NVC + 反巴纳姆具体化 |
| 预言模式（可选） | `prompts/prophecy.zh.md` | 默认关闭；开启后用"趋势 / 展望"口吻，每段附"仅供娱乐" |

### 工具与插件

真 **agentic loop**：模型自己判断何时调用，前端用 ⚙ 徽章显示每步。

- `search_knowledge` 检索专业资料 · `save_memory` 存偏好 / 边界 · `save_note` / `search_notes` 归档与检索笔记 · `crisis_check` 危机兜底（另有服务端 `safety.py` 权威闸门）。
- 视觉识别：填任意 OpenAI 兼容 VLM 的 key，把客观中文描述作为文字线索喂给主模型；密钥只存本机 `agent/data/plugins.json`。
- 抽牌由系统本地完成，不占工具调用；设置里的 `tools_enabled` 只管上面这些工具。

### 主动关怀与盯事（L3）

对应 [Anthropic《Building always-on agents》](https://claude.com/resources/articles/building-always-on-agents) 四原语：timers、inbox、outbox、permissions。后台线程每 30 秒检查到期任务，写一条温暖克制的中文关怀消息；默认**关闭**，全部本地运行。盯事读外部数据 → 规则判断 → 满足条件才提醒，支持网页 / RSS / JSON / 天气，首次只建基线不误报。在「关怀」面板管理；用安装器勾选"开机自启"即可常驻后台。

---

## 📁 目录

```
.
├── prompts/                    # 人格 / 语气 / 预言模式提示词
├── skills/tarot-counselor/
│   └── SKILL.md                # 按需触发的技能格式
├── agent/                      # 本地网页 Agent
│   ├── server.py               # HTTP 服务与全部 API 路由
│   ├── llm.py / tools.py       # 后端调用 / 工具定义与执行
│   ├── safety.py               # 服务端危机闸门（早于抽牌与模型）
│   ├── spreads.py              # 39 个牌阵的唯一来源
│   ├── cards/                  # 78 张 RWS 牌面图
│   ├── knowledge.py / memory.py
│   ├── scheduler.py / watchers.py   # L3 定时关怀 / 条件触发
│   ├── plugin_kb.py / plugin_vision.py
│   └── data/                   # *.db、plugins.json（gitignore）
├── knowledge/                  # 专业知识库（见 INDEX.md）
│   ├── meanings/               # 78 张牌义 + 解牌方法 + 牌间关系
│   ├── spreads/ skills/ ethics/ …
├── installer/                  # 单文件 exe 安装器源码与构建脚本
│   └── build.py                # python installer/build.py 重新构建
└── README.md
```

牌义依据《塔罗智慧》《21世纪的塔罗书》《其实你已经很塔罗了》三书要义，用**原创中文按 RWS 传统重写**；`牌间关系.md` 据《塔罗智慧》整理，均非照搬。

---

## 🌐 换个地方用她

- **作为提示词**：把 `prompts/persona.zh.md`（可加 `tone.zh.md`）放进 ChatGPT 自定义指令 / Claude Project / 自建 Agent 的 system prompt，人格始终在线。
- **作为技能**：把 `skills/tarot-counselor/` 整个目录放进 Agent 的技能目录（Claude Code：`~/.claude/skills/`；DSH：`~/.dsh/skills/`），平时是普通助手，求占 / 倾诉 / 求助时才加载。

---

## 🔒 隐私

- **本地优先**：对话、记忆、知识库、key 只在本机，不上传、不过中间服务器。
- **打包零泄漏**：安装包排除 `config.json`（key）、`agent/data/*.db`（记忆 / 知识库）与缓存。
- **可控可删**：记忆面板可查看 / 删除单条线索；删除安装目录即清除 key 与数据。
- `agent/data/`、`*.db`、`agent/config.json`、`agent/olivia.pid` 均已 gitignore。

---

## 📄 License

MIT。欢迎 fork、改、拿去用。
