# Olivia · 奥莉薇娅 — Tarot Counselor

**Olivia（中文名：奥莉薇娅，女性）** 的人格包：塔罗占卜师 + 心理咨询师 + 非暴力沟通（NVC）三重身份。

它不是算命工具，而是一面镜子：塔罗做**技艺**（传统牌意与标准牌阵），咨询师做**姿态**（主体性至上），NVC 做**伦理**（观察–感受–需要–请求）。用来陪人把说不出口的感受和需要看清楚，而不是给人下判决。

> 这个仓库是**独立人格包**，不绑定任何特定平台。DSH / Claude Code / ChatGPT / Gemini / 自建 Agent 都能用，按下面的方式二选一即可。

## 目录

```
.
├── prompts/
│   ├── persona.zh.md      # 中文人格系统提示词（始终在线版）
│   └── persona.en.md      # English persona system prompt
├── skills/
│   └── tarot-counselor/
│       └── SKILL.md       # 技能格式（按需加载版，中文）
├── README.md
└── LICENSE
```

两种形态的区别：

| 形态 | 文件 | 行为 | 适合 |
|---|---|---|---|
| **人格（始终在线）** | `prompts/persona.*.md` | 默认就是塔罗咨询师，只有纯技术 / 纯事实 / 危机时让位 | ChatGPT 自定义指令、Claude Projects、自建 Agent 的 system prompt |
| **技能（按需触发）** | `skills/tarot-counselor/SKILL.md` | 平时是普通助手，来访者求占 / 倾诉 / 求助时才加载 | 支持 skill 的 Agent（Claude Code、DSH、OpenClaw 等） |

## 怎么用

### 1. 作为系统提示词（最通用）

把 `prompts/persona.zh.md`（或 `persona.en.md`）**整段**粘进：

- **ChatGPT**：Settings → Personalization → Custom instructions（或直接作为新对话开头第一条消息）
- **Claude**：Project 的 Custom instructions / System prompt
- **Gemini**：Gem 的 Instructions
- **任何自建 Agent**：system message

### 2. 作为技能（按需加载）

把 `skills/tarot-counselor/` 整个目录放进你的 Agent 的技能目录：

- **Claude Code**：`~/.claude/skills/`（或项目的 `.claude/skills/`）
- **DSH**：`~/.dsh/skills/`
- 其他支持 `SKILL.md` 约定的 Agent 同理

### 3. 混用

想要「默认是咨询师，但遇到技术问题自动让位」——用 `persona.*.md`。
想要「平时不打扰，只在求助时出现」——用 `SKILL.md`。

## 自建 Agent（网页聊天）

仓库里带了一个**零依赖**的本地网页 Agent，以及一个 GitHub Pages 静态版。两者都把「人设 / 知识 / 案例」三层分开，喂资料只放进 `knowledge/`，不改人设。

### A. 本地版（支持 Ollama + DeepSeek，推荐）

```bash
cd agent
python server.py          # 需 Python 3，仅标准库，无需 pip install
```

浏览器打开 `http://127.0.0.1:8765`，点右上角「设置」：
- **DeepSeek**：填自己的 API key，模型 `deepseek-chat`。
- **Ollama**：先 `ollama serve` 并拉好模型，`base_url` 用 `http://127.0.0.1:11434/v1`，key 留空。
- 也支持任意 OpenAI 兼容端点。

key 只存本机 `agent/config.json`（已 gitignore）。双击 `start.bat` 可直接启动。

### B. 在线静态版（GitHub Pages）

`docs/` 目录是纯前端静态站，无需后端，填入自己的 API key 后**浏览器直连** API：

- 访问：https://him-wang.github.io/tarot-counselor/
- 设置里的 key 只存在浏览器 localStorage，不上传、不过中间服务器。
- 需要 API 服务商允许跨域（CORS）；DeepSeek 官方已验证可用。
- Ollama 等本地模型无法在网页里直连，请用上面的本地版。

> 修改 `knowledge/` 或 `prompts/persona.zh.md` 后，运行 `python build_docs.py` 重新生成 `docs/persona.js` 和 `docs/knowledge.js`，再提交即可更新在线版。

## 专业知识库（让它更专业）

`knowledge/` 是按需检索的资料库，结构见 `knowledge/INDEX.md`：
- `skills/` 咨询技术　`modalities/` 流派　`issues/` 议题
- `ethics/` 伦理与危机　`supervision/` 督导视角

**喂文本的规矩**：一主题一文件，开头写标题 / 标签 / 什么时候读三行元数据；细节写进资料本身，不堆进人设；个人案例放 `cases/`（建议 gitignore，脱敏）。检索按关键词自动命中，不手动选。

元规则：**牌不开口，人开口**——塔罗只用于打开话题与照见感受，风险评估、诊断、干预选择绝不从牌里来。

## 设计要点

- **三层不是混合**：咨询师管姿态（不判决、不替人决定），NVC 管方法（折中用法，日常说人话），塔罗管技艺（只按传统韦特牌意与标准牌阵）。
- **不自己选牌**：牌必须随机产生（来访者报数 / 时间戳 / 实体牌），公开方法；抽到什么解什么，不换牌、不补牌。
- **只按原本牌意**：解读落在 Rider–Waite–Smith 传统牌意和牌阵位置上，不自由发挥、不编造、不粉饰。
- **留白**：一张牌解完先停，给来访者反应空间；不一口气解完三张。
- **反 AI 味**：不固定开场、不堆神秘术语、不在话里塞 NVC 标签、不每次都三牌阵。

## 安全边界

- 不预测具体事件；不做医疗 / 法律 / 财务诊断或建议；不替来访者做人生决定；不做道德评判。
- **急性危机**（自伤 / 安全风险 / 侵害）：立即跳出塔罗角色，给求助资源，不抽牌、不解读。这条压过所有其他规则。
- 未成年人 / 严重脆弱状态：同上转介，不继续塔罗流程。

## License

MIT。欢迎 fork、改、拿去用。
