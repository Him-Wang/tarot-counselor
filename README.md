# Olivia · 奥莉薇娅 — Tarot Reader

**Olivia（中文名：奥莉薇娅，女性）**：**首先是塔罗师，其次才是心理咨询师**。

咨询与NVC（非暴力沟通）是工具，不是主业——它们让牌解读得更贴合人，但不喧宾夺主。塔罗始终是她工作的主体：抽牌、牌阵、解牌。她不做预言、不替人做决定，只按传统韦特（Rider–Waite–smith）牌意和标准牌阵，陪你把说不出口的东西看清楚。

> 这是一个**独立人格包**，不绑定任何平台。ChatGPT / Claude / Gemini / Claude Code / DSH / 自建 Agent 都能用。仓库还带了一个网页 Agent，打开就能聊。

---

## 快速开始

### 本地网页（支持 Ollama + DeepSeek）

```bash
cd agent
python server.py          # 仅 Python 3 标准库，无需 pip install
```

打开 `http://127.0.0.1:8765`，点「设置」填 key。
- **DeepSeek**：填自己的 key（platform.deepseek.com 申请），预设可选：
  - `deepseek-flash`（V4.1-Flash，快、便宜，默认带思考）——默认
  - `deepseek-v4-pro`（V4-Pro，更强，适合复杂问题）
  - `deepseek-chat`（旧版，兼容老配置）
  - 模型框也可下拉选 `deepseek-flash` / `deepseek-v4-pro` / `deepseek-chat` / `deepseek-reasoner`，或手填其他模型名。
- **Ollama**：先 `ollama serve` 并拉好模型，`base_url` 填 `http://127.0.0.1:11434/v1`，key 留空。
- 也支持任意 OpenAI 兼容端点。

双击 `start.bat` 可直接启动。key 只存本机 `agent/config.json`（已 gitignore）。Ollama 只能本地版用。

### 一键安装（双击 installer）

双击 `installer/install.bat` 直接进安装：自动检测 Python，问你三个问题（安装位置 / 开机自启 / 立即启动），然后建快捷方式并装好，全程不写死路径、不带任何 key 和记忆数据。

发给别人则先 `python installer/make_installer.py` 生成 `installer/dist/Olivia-agent-setup.zip`，对方解压后双击里面的 `install.bat`，体验完全一样。`uninstall.bat` 一键卸载。详见 `installer/README.md`。

---

## 目录

```
.
├── prompts/
│   ├── persona.zh.md          # 中文系统提示词（始终在线）
│   └── persona.en.md          # English system prompt
├── skills/tarot-counselor/
│   └── SKILL.md               # 技能格式（按需触发）
├── agent/                     # 本地网页 Agent（双后端 + 记忆 + 工具 + 插件）
│   ├── llm.py / knowledge.py / memory.py / tools.py / server.py
│   ├── scheduler.py / watchers.py  # L3 主动关怀 + 条件触发（纯 stdlib）
│   ├── plugin_kb.py           # 个人知识库插件（记忆的归档扩展）
│   ├── plugin_vision.py       # 视觉识别插件（云端 VLM 桥接，可配置）
│   └── data/                  # memory.db / kb.db / scheduler.db / watchers.db（gitignore，绝不提交）
├── knowledge/                 # 专业知识库（辅助解牌）
└── README.md
```

两种人格形态：

| 形态 | 文件 | 行为 | 适合 |
|---|---|---|---|
| **人格（始终在线）** | `prompts/persona.*.md` | 默认就是 Olivia，纯技术/事实/危机时让位 | ChatGPT 自定义指令、Claude Project、自建 Agent 的 system prompt |
| **技能（按需触发）** | `skills/tarot-counselor/SKILL.md` | 平时是普通助手，求占/倾诉/求助时才加载 | 支持 skill 的 Agent（Claude Code、DSH 等） |

---

## 身份设定

**塔罗师是第一身份，心理咨询师是辅助身份，NVC 是工具。** 三者有主次，不是平均混合：

- **塔罗师（核心）**：抽牌、牌阵、解牌是工作主体。牌意只落在传统韦特（Rider–Waite–Smith）牌意和标准牌阵位置上。
- **心理咨询师（辅助）**：让解牌更贴合人。来访者主体性至上，不给定性判决、不替人做决定。
- **NVC（工具）**：观察 → 感受 → 需要 → 请求。日常说人话，情绪激烈时才显式拆解。

### 抽牌规则

牌必须**随机产生**，与对来访者的印象无关——不能挑牌、换牌、补牌。合规方式（公开告诉来访者用了哪种）：

1. 来访者报数（每张一个 1–78 的数，按韦特牌序映射）；
2. 时间戳对 78 取余；
3. 来访者用实体牌自己抽。

逆位同样客观决定。抽到什么解什么；说对不上就核对牌意，不换牌。

### 标准牌阵（只用这些）

单牌 · 三牌阵（时间流：过去/现在/未来）· 三牌阵（问题解决：现状/阻碍/出路）· 三牌阵（关系：你/对方/关系）· 凯尔特十字（十张）。

### 解读规则

每张牌按固定顺序：**原本牌意 → 牌阵位置 → 对应问题 → 落到情境**。落脚必须由牌意推出。禁止主观投射、编造牌意、粉饰凶牌、预言具体事件。

### 边界

不预测具体事件；不做医疗/法律/财务建议；不扮演通灵；不替人做人生决定；不做道德评判。
**急性危机**（自伤/安全风险/侵害）：立即跳出塔罗师角色，给求助资源，不抽牌不解读——这条压过所有规则。未成年人/严重脆弱状态转介。

---

## 专业知识库（让它更专业）

`knowledge/` 是**辅助解牌**的资料库，结构见 `knowledge/INDEX.md`：
- `meanings/` 传统 RWS 牌意（大阿卡纳 + 四花色）与解牌方法——`draw_cards` 会随每张牌返回对应牌意，作为解牌的既定依据
- `skills/` 咨询技术　`modalities/` 流派　`issues/` 议题
- `ethics/` 伦理与危机　`supervision/` 督导视角

牌义笔记依据《塔罗智慧》《21世纪的塔罗书》《其实你已经很塔罗了》三书要义，用原创中文按 RWS 传统重写（非原文摘录）；公开仓库不含书籍原文。

喂文本规矩：一主题一文件，开头写「标题 / 标签 / 什么时候读」三行元数据；细节写进资料本身，不堆进人设；个人案例放 `cases/`（已 gitignore，记得脱敏）。检索按关键词自动命中。

**元规则：牌不开口，人开口**——塔罗是主体；只在风险评估与急性危机时，才跳出塔罗师角色走安全流程。

知识库改动即时生效——本地 Agent 每轮直接从 `knowledge/` 检索，无需重新构建。

---

## 长期记忆（仅本地版）

本地 Agent 会记住关于你的信息，让咨询有连续性；数据只存在 `agent/data/memory.db`（已 gitignore，绝不上传）。结构参考 mem0 的"抽取→存储→检索→注入"与 Letta 的分层，落到纯 stdlib：

| 层 | 内容 | 表 |
|---|---|---|
| 稳定画像 | 称呼等，每轮常驻 | `profile` |
| 长期线索 | 偏好/边界/「请记住」的事实，规则抽取（零延迟，不额外调模型）| `facts` |
| 会话原文 | 完整对话，用于回访不重复 | `messages` |
| 抽牌历史 | 结构化记录牌名/正逆位/牌阵/所问问题 | `draws` |

- 每轮把相关记忆注入 system prompt，Olivia 会自然提起（如"上次你问感情抽到圣杯三，后来如何？"），不会生硬复述，也不会把记忆当成新牌面。
- **危机内容不进事实库**（遵守上面的边界规则）。
- 说"忘掉刚才记的"即可撤销最近线索。
- 点顶栏「记忆」打开面板：查看/固定/添加/删除线索、看抽牌历史、手动添加画像、整理去重、清空全部，还可一键开关记忆。

---

## 插件（仅本地版）

### 个人知识库（记忆的归档扩展）

记忆是自动、轻量的"线索"；知识库是你主动整理的"档案"——重要笔记、清单、决定，长期留存、可检索、可导出。存在 `agent/data/kb.db`（gitignore）。

- 聊天里说"**记到知识库**"，Olivia 会调用 `save_note` 自动归档；需要调阅时调用 `search_notes`，相关笔记也会在每轮自然注入。
- 点顶栏「**知识库**」：手动添加/置顶/删除笔记，一键"从记忆归档"（把已有的线索与抽牌历史整理进来，幂等），导出 Markdown 备份。
- 与记忆的分工：`memory` = 自动抽取的线索；`plugin_kb` = 用户策展的档案，是分层里的"归档层"。

### 视觉识别（云端 VLM 桥接，纯文本模型也能看图）

**不依赖本地模型**。任意 OpenAI 兼容的视觉大模型都行（OpenAI / 通义 VL / 智谱 GLM-4V / Moonshot / 自建网关），填自己的 key 即用：

- 在「设置 → 👁 视觉识别插件」里开启并填 base_url / model / api_key（预设已内置常见服务商）。密钥只存本机 `agent/data/plugins.json`（gitignore）。
- 聊天框左侧「＋图」可附带最多 3 张图片。流程是：**云端 VLM 看图 → 生成客观中文描述 → 描述作为文字线索喂给主模型**。主模型始终是你配置的那个纯文本模型，它不会"假装看见"图片，只把描述当作你提供的线索。
- 视觉 API 调用失败不会中断对话，会如实标注"图片识别失败"。

---

## 工具调用（本地 Agent，自主执行）

本地版是真正的 **agentic loop**：模型自己判断何时调用工具，执行后把结果回填给模型继续，直到它给出最终回答。前端会用 `⚙` 徽章显示每一步工具执行。

六个工具（`agent/tools.py`）：

| 工具 | 作用 | 安全约束 |
|---|---|---|
| `draw_cards` | 按牌阵从标准 78 张韦特牌库**客观随机**抽牌（不放回，同一牌阵不重复），返回牌名/正逆位/位置，**并随每张牌附上传统牌意（核心/正位/逆位）** | 模型只能选牌阵和填问题，不能挑牌/换牌/编牌；必须依据返回的牌意按「牌意→位置→问题→情境」解 |
| `search_knowledge` | 检索 `knowledge/` 专业资料 | 只做专业判断依据，不从牌里来 |
| `save_memory` | 存偏好/边界/「请记住」 | 危机内容拒绝入库 |
| `crisis_check` | 检测自伤/轻生等急性危机信号 | 命中即跳出塔罗师角色，走安全流程 |
| `save_note` | 归档到个人知识库 | 用户主动策展，危机内容不入库 |
| `search_notes` | 检索个人知识库笔记 | 调阅此前归档的内容 |

- 实测：本地 `dsv4-9b-heretic-max:latest` 支持工具调用，能正确产出 `draw_cards(spread, question)`；端到端验证通过（模型调用工具→拿到牌→逐张按"牌意→位置→问题→情境"解读）。
- 设置里可一键关闭工具调用（`tools_enabled`）。
- 抽牌由代码随机完成，彻底解决"模型可能编牌/重牌"的问题。

---

## 主动关怀（L3 · Always-on）

对应 [Anthropic《Building always-on agents》](https://claude.com/resources/articles/building-always-on-agents) 的四个原语，做成本地版：

| 原语 | 落地 |
|---|---|
| timers | `tasks` 表：每天 / 每周 / 每隔 N 分钟 / 仅一次 |
| inbox | `events` 表：手动或未来外部触发的事件入口 |
| outbox | `messages` 表：Olivia 主动生成的消息 + 桌面通知 |
| permissions | 总开关 + 静默时段（如 22:00–08:00 不打扰）+ 每任务开关 |

- 后台线程每 30 秒检查到期任务，结合长期记忆写一条**温暖克制的中文关怀消息**，存进收件箱并弹 Windows 桌面通知（`agent/toast.ps1`）。
- 点顶栏「关怀」配置任务、看收件箱、标记已读。默认**关闭**，需手动开启总开关。
- 全部本地运行，不向任何外部发送消息。
- **开机自启**：双击 `agent/autostart.bat`（或把它放进"启动"文件夹）即可让服务随登录启动，L3 才会持续生效；删掉启动项即撤销。

### 盯事 · 条件触发（对标灵光 2.0 的"长事务托管"）

定时关怀只会"到点问候"，条件触发才是真正"盯住一件事"——**读外部数据 → 规则判断 → 满足条件才提醒**（`agent/watchers.py`，纯 stdlib，**不调用模型**）：

| 数据源 | 说明 |
|---|---|
| 网页 / 文本 | 抓取网页全文，配「包含 / 不含 / 正则」规则（如盯某页面出现"降价"） |
| RSS / Atom | 订阅源，配「新条目」规则有新文章才提醒 |
| JSON 接口 | 用字段路径取值（如 `current.temperature_2m`），配数值比较规则 |
| 天气 | 内置常用城市坐标，Open-Meteo 免 key，配 `> / ≥ / < / ≤` 规则（如"低于 5°C 提醒加衣"） |

- 规则：`contains` / `not_contains` / `regex` / `gt` / `gte` / `lt` / `lte` / `changed`（内容变化）/ `new_item`（新条目）/ `always`。
- **冷却与去重**：每条盯事有"检查间隔"和"触发冷却"，避免反复打扰；首次检查只建立基线不误报。
- 判定结果写入 `agent/data/watchers.db`（`watchers` + `watcher_events` 两张表，gitignore），命中才进收件箱 / 弹通知；抓取失败静默记录、不打扰。
- 在「关怀」面板的「盯事 · 条件触发」区添加、启停、立即检查、清空日志。

---

## 作为技能安装

把 `skills/tarot-counselor/` 整个目录放进 Agent 的技能目录：
- **Claude Code**：`~/.claude/skills/` 或项目的 `.claude/skills/`
- **DSH**：`~/.dsh/skills/`
- 其他支持 `SKILL.md` 约定的 Agent 同理

---

## License

MIT。欢迎 fork、改、拿去用。
