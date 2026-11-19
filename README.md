# Olivia · 奥莉薇娅 — Tarot Reader

**Olivia（中文名：奥莉薇娅，女性）**：**首先是塔罗师，其次才是心理咨询师**。

咨询与NVC（非暴力沟通）是工具，不是主业——它们让牌解读得更贴合人，但不喧宾夺主。塔罗始终是她工作的主体：抽牌、牌阵、解牌。她不做预言、不替人做决定，只按传统韦特（Rider–Waite–smith）牌意和标准牌阵，陪你把说不出口的东西看清楚。

> 这是一个**独立人格包**，不绑定任何平台。ChatGPT / Claude / Gemini / Claude Code / DSH / 自建 Agent 都能用。仓库还带了一个网页 Agent，打开就能聊。

---

## 快速开始

### 在线网页（最简单，不用装东西）

**https://him-wang.github.io/tarot-counselor/**

打开 → 右上角「设置」→ 选 DeepSeek → 填你自己的 API key → 开始聊。
纯静态页面，浏览器直连 API；key 只存在浏览器 localStorage，不上传、不过中间服务器。需要 API 服务商允许跨域（DeepSeek 官方已验证可用）。

### 本地网页（支持 Ollama + DeepSeek）

```bash
cd agent
python server.py          # 仅 Python 3 标准库，无需 pip install
```

打开 `http://127.0.0.1:8765`，点「设置」填 key。
- **DeepSeek**：填自己的 key，模型 `deepseek-chat`。
- **Ollama**：先 `ollama serve` 并拉好模型，`base_url` 填 `http://127.0.0.1:11434/v1`，key 留空。
- 也支持任意 OpenAI 兼容端点。

双击 `start.bat` 可直接启动。key 只存本机 `agent/config.json`（已 gitignore）。Ollama 只能在本地版用，网页版没法直连本机模型。

---

## 目录

```
.
├── prompts/
│   ├── persona.zh.md          # 中文系统提示词（始终在线）
│   └── persona.en.md          # English system prompt
├── skills/tarot-counselor/
│   └── SKILL.md               # 技能格式（按需触发）
├── agent/                     # 本地网页 Agent（双后端）
├── docs/                      # GitHub Pages 静态站源码
├── knowledge/                 # 专业知识库（辅助解牌）
├── build_docs.py              # 把人设+知识打包给静态站
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
- `skills/` 咨询技术　`modalities/` 流派　`issues/` 议题
- `ethics/` 伦理与危机　`supervision/` 督导视角

喂文本规矩：一主题一文件，开头写「标题 / 标签 / 什么时候读」三行元数据；细节写进资料本身，不堆进人设；个人案例放 `cases/`（已 gitignore，记得脱敏）。检索按关键词自动命中。

**元规则：牌不开口，人开口**——塔罗是主体；只在风险评估与急性危机时，才跳出塔罗师角色走安全流程。

改了 `knowledge/` 或 `prompts/persona.zh.md` 后，运行 `python build_docs.py` 重新生成 `docs/persona.js` 与 `docs/knowledge.js`，提交推送即可更新在线版（Pages 几分钟后自动重建）。

---

## 作为技能安装

把 `skills/tarot-counselor/` 整个目录放进 Agent 的技能目录：
- **Claude Code**：`~/.claude/skills/` 或项目的 `.claude/skills/`
- **DSH**：`~/.dsh/skills/`
- 其他支持 `SKILL.md` 约定的 Agent 同理

---

## License

MIT。欢迎 fork、改、拿去用。
