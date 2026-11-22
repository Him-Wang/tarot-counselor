<div align="center">

# 🔮 Olivia · 奥莉薇娅

**先是一名塔罗师，其次才借咨询与 NVC 让解牌更贴近人。**

Olivia（奥莉薇娅，女性）是一位**可独立使用的人格包 + 本地网页 Agent**。她不预言、不替人做决定，只依据传统韦特（Rider–Waite–Smith）牌意与标准牌阵，陪你把说不出口的东西看清楚。

[快速开始](#-快速开始) · [她怎么解牌](#-她怎么解牌) · [能做什么](#-能做什么) · [目录](#-目录) · [换个地方用她](#-换个地方用她) · [隐私](#-隐私)

</div>

---

## 为什么是她

- **牌是主角，人是中心**：解牌是主体，咨询与 NVC（非暴力沟通）只是让牌意落到真实处境，不喧宾夺主。
- **客观，可复核**：78 张牌不放回随机抽取，抽牌纯本地、不需要 API key；每次都给出复现种子，可抽回同一副牌，自证没有临时挑牌。
- **先出牌，后问问题**：抽牌那一刻不解读，等你说出真正想问的事，她才只针对这副牌回答。
- **形体自由**：同一个灵魂，能作为常驻 system prompt，也能作为按需加载的 skill，还能在本地网页或手机 App 里开着用。

---

## 🚀 快速开始

### Windows 一键安装（推荐）

从 [Releases](../../releases/tag/v1.0.0) 下载 **`Olivia-setup.exe`**（约 11 MB），双击：

1. 选安装目录（默认 `%LOCALAPPDATA%\Olivia`）与是否开机自启。
2. 安装器解压内置文件、建桌面/开始菜单快捷方式、后台静默启动服务、打开 <http://127.0.0.1:8765>。
3. 点右上角「设置」填入自己的 API key（DeepSeek 等）即可开始解读。

> 安装器需要本机有 **Python 3 且在 PATH 里**（安装时勾 *Add Python to PATH*）；没有会给出提示并可一键跳到 [python.org](https://www.python.org/downloads/)。服务端只用 Python 3 标准库，不需要 pip 装任何东西。

Want it on your phone? 同一个 Release 下的 **`Olivia-1.0.0.apk`** 是安卓客户端（见 [安卓 App](#-安卓-app)）。

### 直接跑源码

```bash
cd agent
python server.py          # 仅依赖 Python 3 标准库
```

打开 <http://127.0.0.1:8765>，在「设置」里选后端：

| 后端 | 配置 |
|---|---|
| **DeepSeek**（默认） | 填自己的 key（platform.deepseek.com 申请）；预设 `deepseek-flash`（快而省，默认）、`deepseek-v4-pro`、`deepseek-chat`，模型框也可手填 `deepseek-reasoner` |
| **Anthropic** | 原生 Messages API：预设 `anthropic`，填 `sk-ant-…`，模型如 `claude-sonnet-4-5-20250929` |
| **Gemini** | 原生 GenerateContent API：预设 `gemini`，填 key，模型如 `gemini-2.5-flash` |
| **Ollama** | `ollama serve` 并拉好模型，`base_url` 填 `http://127.0.0.1:<端口>/v1`，key 留空 |
| 其他 | 「协议」选 `auto`（按 base_url 自动判断）或 `openai`，任意 OpenAI 兼容端点均可 |

三种协议（OpenAI 兼容 / Anthropic Messages / Gemini GenerateContent）共用同一套 agentic loop 与工具调用，设置里随时切；**抽牌本身不需要 key**，只有解读才调用大模型。key 只存本机 `agent/config.json`（已 gitignore）。

---

## 🔮 她怎么解牌

### 两阶段流程

1. 你说「抽牌」→ 列出 **39 种牌阵**供你点选（悬浮可看每个牌位在问什么），全程本地、零 API 调用。
2. 点选后客观抽牌、按传统几何摆牌并展示牌面，此时**不解读**，只问一句「你有什么问题吗？」。
3. 你给出问题后，她才只对这一副牌、围绕这个问题解读。想再抽，重新开始即可。

### 解牌方法

- 每张牌按 **原本牌意 → 牌阵位置 → 对应问题 → 落到情境** 解读，落脚必须由牌意推出。
- 两张以上连读时参考 `knowledge/meanings/牌间关系.md`：从**元素相处、数字阶段、大小牌对位、宫廷牌看人、叙事弧线**五个角度看牌与牌的关系——是视角，不是公式，不可覆盖牌面本身。
- 建议一定**具体到时间与动作**（"今晚睡前把那句话先写下来"），不说"顺其自然""保持平衡""一切都会好"这类正确的废话。系统每轮都会把**当前日期时间**注入上下文，所以「今晚」「明早七点」这类建议有时间可依，不会拿训练数据里的年份瞎猜。
- 禁主观投射、编造牌意、粉饰凶牌、预言具体事件。逆位有受阻 / 内化 / 过度或不足 / 需调整四种读法，按情境取用。

### 牌阵与牌面

共 **39 个牌阵**（`agent/spreads.py` 是唯一来源，每个牌位自带「这个位置在问什么」）：快速（单张 / 三张）、专业（凯尔特十字、生命之树、六芒星、七脉轮…）、咨询（关系 / 二选一 / 是非）、季节与神秘布局等。原则是**先用最简单的能回答问题的牌阵**，复杂才升级。

78 张韦特牌面在 `agent/cards/`（公有领域扫描，来源见 `SOURCE.md`），随牌气泡显示，逆位旋转 180°，按各牌阵的传统几何摆放；悬浮浮出该位置含义，底部牌位表可一次看全。

### 安全边界

急性危机（自伤 / 轻生 / 受侵害 / 伤害他人）由独立闸门 `agent/safety.py` 在服务端统一拦截，**早于抽牌、早于模型、早于记忆写入**：直接跳出塔罗师角色，给求助资源，不抽牌不解读。中文句式覆盖"他打我了"这类直白说法，并处理"我不会自杀的"这类否定。此外不预测具体事件、不做医疗 / 法律 / 财务建议、不扮演通灵、不替人做人生决定。

### 离线也能用

没填 key、或模型临时连不上时，不会卡在"没有收到回复"的死胡同：`agent/offline.py` 会把**已经在本地客观抽好的那副牌**，按「牌位在问什么 + 随牌传统牌意 + 复现种子」整理成可读文字，并明确标注 **【离线整理】不是 AI 解读**——不编造牌意、不粉饰、不预言、不替你做决定。抽牌、看牌面、读牌位含义本来就不需要联网。顶部会亮出"离线整理"标识，模型恢复后说一句"就着这副牌说说我的问题"即可切回完整解读。

> 元规则：**牌不开口，人开口。** 离线时这张嘴由传统牌意来当，而不是伪装成 AI。

---

## ✨ 能做什么

| | |
|---|---|
| 🃏 **客观抽牌** | 78 张 RWS + 39 牌阵，不放回随机、带复现种子；纯本地、零 API key |
| 💬 **流式对话** | 打字机式输出，温柔克制、带 NVC 底色的女性口吻，轻拟态界面 |
| ⏹ **随时叫停** | 一段话讲太长，点「停止」立刻打断；已经说出来的部分留着，并标注「已停止生成」 |
| 🔍 **放大看牌** | 双击任意牌（含补牌）出大图，逆位自动转 180°，看清牌面细节与牌位含义 |
| 🧠 **长期记忆** | 画像 / 线索 / 对话 / 抽牌历史分层存储，相关记忆每轮自然注入；她也能主动回想过去、忘掉不该留的 |
| 📚 **专业知识库** | 78 张牌义 + 解牌方法 + 牌间关系 + 咨询技术，关键词自动检索；问某张牌可直接查牌意 |
| 🗂 **个人知识库** | 主动策展的笔记，可归档、检索、导出 Markdown |
| 👁 **视觉识别** | 任意 OpenAI 兼容 VLM 看图，主模型仍是纯文本，不假装看见 |
| ⏰ **主动关怀与盯事** | 定时任务（一次 / 每天 / 每周 / 间隔）+ 条件触发（网页 / RSS / JSON / 天气），Windows 桌面通知 |
| 🌅 **每日一牌** | 每天固定时间本地抽一张写进收件箱，**不调用模型、没 key 也照常送达** |
| ➕ **补牌** | 读完想再看一面，点「补一张」并写下理由；补牌只作补充视角，不替换原来的牌，理由会记下来 |
| 🔊 **朗读** | 每条回复可一键念出来；安卓端走系统 TTS，浏览器里走 Web Speech，再点停止 |
| 🖼 **存这次解读** | 把牌面 + 她的话导出成一张 PNG（1080 宽，手机直接进相册），纯 Canvas 本地生成、不上传 |
| 📊 **tokens 用量** | 每条回复下显示「本轮 tokens：入 x / 出 y」，知道这一问花了多少 |
| 🔀 **三种模型协议** | OpenAI 兼容 / Anthropic Messages / Gemini GenerateContent，同一套工具调用，设置里随时切 |
| 📖 **会话簿** | 本机浏览器保存历次对话，可命名、回访、深链 `#/chat/<id>`；刷新不丢，crisis 只存占位不存原文 |
| 🌙 **离线整理** | 没 key / 模型失败也能用：按传统牌意 + 牌位 + 复现种子客观整理已抽的牌，明说"不是 AI 解读" |
| 📱 **安卓 App** | `android/` 是一个 WebView 薄客户端：把电脑上跑着的 Olivia 装进手机，支持返回键、存图到相册、原生中文朗读、双击放大 |
| ✅ **改完能自查** | `tests/` 白盒 + 黑盒两套脚本，纯标准库、不碰真实 API |
| 🔒 **零第三方依赖** | Agent 仅用 Python 3 标准库；数据全部留在本机 |

### 工具：她真的会动手

真 **agentic loop**：模型自己判断何时调用，前端用 ⚙ 徽章显示每一步。`agent/tools.py` 里共 9 个工具：

| 工具 | 做什么 |
|---|---|
| `draw_cards` | 按牌阵本地抽牌（不放回、带种子） |
| `search_knowledge` | 检索 78 张牌义、解牌方法、牌间关系、咨询技术 |
| `lookup_card` | 直查某一两张牌的牌意（正位 / 逆位），不必靠检索碰运气 |
| `save_memory` | 记住偏好、边界、重要线索 |
| `recall_memory` | 回想画像 / 线索 / 抽牌历史，或按要求忘掉某条 |
| `save_note` / `search_notes` | 归档与检索你自己的笔记 |
| `crisis_check` | 危机兜底（另有服务端 `safety.py` 作权威闸门） |
| `schedule_reminder` | 建定时提醒（一次 / 每天 / 每周 / 间隔），到点写进收件箱 |

所以她能听懂「明晚八点提醒我」「我上次问过什么」「死神是什么牌」这类话，而不只是聊牌。视觉识别单独在设置里配：填任意 OpenAI 兼容 VLM 的 key，把客观中文描述作为文字线索喂给主模型，密钥只存本机 `agent/data/plugins.json`。

### 分层人格

| 层 | 文件 | 作用 |
|---|---|---|
| 人格（始终在线） | `prompts/persona.zh.md` / `persona.en.md` | 她是谁、塔罗 / 咨询 / NVC 的主次与边界 |
| 语气（始终在线） | `prompts/tone.zh.md` / `tone.en.md` | 怎么说：真实女性口吻 + 自然 NVC + 反巴纳姆具体化 |
| 预言模式（可选） | `prompts/prophecy.zh.md` | 默认关闭；开启后用"趋势 / 展望"口吻，每段附"仅供娱乐" |

### 主动关怀与盯事

对应 [Anthropic《Building always-on agents》](https://claude.com/resources/articles/building-always-on-agents) 四原语：timers、inbox、outbox、permissions。后台线程每 30 秒检查到期任务，写一条温暖克制的中文关怀消息；默认**关闭**，全部本地运行。盯事（`agent/watchers.py`）读外部数据 → 规则判断 → 满足条件才提醒，支持网页 / RSS / JSON / 天气，首次只建基线不误报。都在「关怀」面板里管。

---

## 📁 目录

```
.
├── prompts/                        # 人格 / 语气 / 预言模式提示词（中英各一套）
├── skills/tarot-counselor/
│   └── SKILL.md                    # 按需触发的技能格式
├── knowledge/                      # 专业知识库（入口 INDEX.md）
│   ├── meanings/                   # 大阿卡纳 + 四花色 + 解牌方法 + 牌间关系
│   ├── spreads/牌阵速查.md
│   ├── skills/共情式倾听.md
│   └── ethics/危机与转介.md
├── agent/                          # 本地网页 Agent
│   ├── server.py                   # HTTP 服务、API 路由、两阶段抽牌与解读编排
│   ├── index.html                  # 单页前端（对话 / 牌面 / 大图 / 分享图 / 关怀面板）
│   ├── provider.py / llm.py        # 三协议流式调用、工具调用、usage 归一
│   ├── tools.py                    # 9 个工具的定义与执行
│   ├── spreads.py                  # 39 个牌阵的唯一来源
│   ├── cards/                      # 78 张 RWS 牌面图（来源见 SOURCE.md）
│   ├── safety.py                   # 服务端危机闸门（早于抽牌与模型）
│   ├── offline.py                  # 离线整理降级（无 key / 模型失败时接住）
│   ├── knowledge.py / memory.py    # 知识检索 / 分层记忆
│   ├── scheduler.py / watchers.py  # 定时关怀（含每日一牌）/ 条件触发盯事
│   ├── plugin_kb.py / plugin_vision.py
│   ├── toast.ps1                   # Windows 桌面通知
│   └── data/                       # *.db、plugins.json（gitignore）
├── android/                        # 安卓 App（WebView 薄客户端，见 android/README.md）
│   ├── build.ps1                   # 一条命令出签名 APK（aapt2 + d8 + apksigner）
│   ├── src/com/olivia/tarot/       # MainActivity：WebView / TTS 桥 / 相册下载 / 换地址
│   ├── res/                        # 图标与字符串
│   └── tools/merge_dex.py          # 把 classes.dex 合进 aapt2 打出的底座 APK
├── installer/                      # Windows 单文件安装器
│   ├── build.py                    # python installer/build.py 重新构建
│   ├── Setup.cs / Launcher.cs      # 安装器与启动器（csc.exe 直接编译）
│   └── dist/                       # 产物（gitignore）
├── tests/                          # 白盒 + 黑盒自查
└── README.md
```

牌义依据《塔罗智慧》《21世纪的塔罗书》《其实你已经很塔罗了》三书要义，用**原创中文按 RWS 传统重写**；`牌间关系.md` 据《塔罗智慧》整理，均非照搬。

---

## ✅ 改完能自查

只依赖 Python 3 标准库，**不碰真实模型 API**（无 key 也能跑）：

```bash
python tests/test_whitebox.py     # 白盒：69 项，查源码结构与纯函数
python tests/test_blackbox.py     # 黑盒：41 项，起独立服务发真实 HTTP 请求
```

- **白盒**：安全闸门 18 条用例（含否定句、主谓宾句式、梦境排除）、三协议识别与消息/工具转换、39 牌阵布局完整性、抽牌不放回、危机文本不入库、离线整理内容与切分还原、服务端集成点断言。
- **黑盒**：危机请求**不发牌、不调工具、先给求助资源**；本地抽牌出牌正确且不放回；无 key 时解读轮标注 offline、明确"不是 AI 解读"、带传统牌意与复现种子；history 危机残留不二次报警；深链路由、协议选择器、分享图按钮在首页；牌图可访问、目录穿越被拒。

> 黑盒用 `AGENT_PORT` 起独立端口，不会占用你正在跑的 8765 实例；可用 `--port` 改端口。

---

## 📱 安卓 App

`android/` 是一个**不重新实现任何逻辑**的 WebView 薄客户端：Olivia 仍然跑在你的电脑（或任何一台机器）上，手机只是个窗口。牌义、记忆、定时任务、离线整理因此只有一份，改一处两边都更新。

- **连哪台机器**：先连电脑上的 `http://<电脑IP>:8765`；连不上会显示错误页，里面可以直接改地址。默认地址是模拟器用的 `http://10.0.2.2:8765`。
- **手机能做的**：抽牌 / 解读 / 补牌 / 停止生成 / 双击放大牌面 / 存这次解读进相册（`Pictures/Olivia`）/ 朗读（走系统 TTS，不依赖 Web Speech）/ 关怀面板里开每日一牌。
- **第一次连真机**：电脑上 `AGENT_HOST=0.0.0.0 python agent/server.py`（默认只监听 `127.0.0.1`），手机与电脑同一 Wi-Fi；安卓 9+ 的明文 HTTP 已在 App 里放行。开放到局域网后同网段的人也能打开她，用完记得改回默认。

自己出包（无需 Android Studio、无需 Gradle，一台装了 JDK 17 + Android SDK 的机器即可）：

```powershell
# 依赖：JDK 17、Android SDK（platform 34 + build-tools 34.0.0）放在 ..\android\sdk
powershell -NoProfile -ExecutionPolicy Bypass -File android\build.ps1
# 产物：android\build\Olivia-release.apk
```

签名密钥默认读 `android\keystore\olivia-release.jks`（别名 `olivia`，示例口令 `olivia-tarot`，**自己用请换掉**）；不想用现成密钥就加 `-Keystore <路径> -StorePass <口令> -KeyAlias <别名>` 重新生成一把。更细的说明与调试（`chrome://inspect`、`adb reverse`）见 [`android/README.md`](android/README.md)。

---

## 🌐 换个地方用她

- **作为提示词**：把 `prompts/persona.zh.md`（可加 `tone.zh.md`）放进 ChatGPT 自定义指令 / Claude Project / 自建 Agent 的 system prompt，人格始终在线。
- **作为技能**：把 `skills/tarot-counselor/` 整个目录放进 Agent 的技能目录（Claude Code：`~/.claude/skills/`；DSH：`~/.dsh/skills/`），平时是普通助手，求占 / 倾诉 / 求助时才加载。

---

## 🔒 隐私

- **本地优先**：对话、记忆、知识库、key 只在本机，不上传、不过中间服务器。
- **打包零泄漏**：安装包排除 `config.json`（key）、`agent/data/*.db`（记忆 / 知识库）与缓存。
- **可控可删**：记忆面板可查看 / 删除单条线索；删除安装目录即清除 key 与数据。
- `agent/data/`、`*.db`、`agent/config.json`、`agent/olivia.pid`、`installer/dist/`、`android/build/`、`android/keystore/` 均已 gitignore。

---

## 📄 License

MIT。欢迎 fork、改、拿去用。
