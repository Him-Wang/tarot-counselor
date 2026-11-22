<div align="center">

# 🔮 Olivia · 奥莉薇娅

一个住在你电脑里的塔罗师。女性，话不多，不预言，也不替你做决定。

牌在本地抽，记忆留在本机；只有「把牌读给你听」这一步会连模型。

[![CI](https://github.com/Him-Wang/tarot-counselor/actions/workflows/ci.yml/badge.svg)](https://github.com/Him-Wang/tarot-counselor/actions/workflows/ci.yml)
[![version](https://img.shields.io/badge/version-1.2.0-blue.svg)](CHANGELOG.md)
[![python](https://img.shields.io/badge/python-3.9%2B-blue.svg)](https://www.python.org/)
[![license](https://img.shields.io/badge/license-PolyForm%20NC%20%2B%20CC%20BY--NC--SA-green.svg)](LICENSE)

[上手](#三十秒) · [一次占卜](#一次占卜的全程) · [安全边界](#安全边界) · [工具](#她的手) · [MCP](#mcp) · [配置](#配置) · [自查](#自查)

![Olivia 演示：抽牌、提问、解读](docs/media/demo.gif)

<sub>[首页](docs/media/home.png) · [牌阵](docs/media/spreads.png) · [牌面](docs/media/cards.png) · [解读](docs/media/reading.png) · [设置](docs/media/settings.png) · [手机端](docs/media/mobile.png)</sub>

<sub>[English](README.en.md)</sub>

</div>

---

## 她是什么

- **一个人格包**：`prompts/` 里是人格、语气与可选的预言模式。可以当常驻 system prompt、按需加载的 skill，或者本地网页里那个会打字的人。
- **一个会动手的 agent**：9 个工具（抽牌、查牌、检索、记忆、笔记、危机闸门、定时提醒）由模型自己判断何时调用，不是写死的流程。
- **一间纯本地的咨询室**：78 张韦特牌面、39 个牌阵、牌义、记忆、笔记都在你自己的磁盘上。抽牌这一步连 API key 都不需要。

她刻意不做的事：不预测具体事件、不看医疗 / 法律 / 财务、不扮演通灵、不替人做人生决定。遇到急性危机（自伤、轻生、受侵害）直接跳出塔罗师角色，先给求助资源——这道闸门在服务端，早于抽牌、早于模型、早于写记忆。

---

## 三十秒

### Windows：双击装

从 [最新 Release](https://github.com/Him-Wang/tarot-counselor/releases/latest) 拿 **`Olivia-setup.exe`**（约 11 MB）：

1. 选安装目录（默认 `%LOCALAPPDATA%\Olivia`）、要不要开机自启
2. 它建快捷方式、后台起服务、打开 <http://127.0.0.1:8765>
3. 点右上「设置」填自己的 key

需要本机有 **Python 3 且在 PATH 里**（安装时勾 *Add Python to PATH*）。没有会提示并给下载链接；服务端只用标准库，不用 pip 装任何东西。

### 源码：一行

```bash
cd agent && python server.py      # 只用 Python 3 标准库
```

### Docker：一条命令

```bash
docker compose up -d              # 打开 http://127.0.0.1:8765
```

镜像基于 `python:3.12-slim`，仍然只用标准库；数据挂在 `./agent/data`，删容器不等于让她失忆。

### 手机：同一个 Release 里的 `Olivia-release.apk`

不重新实现任何逻辑的 WebView 薄客户端，连电脑上那台 Olivia（详见 [手机端](#手机端)）。

### 接哪个模型

| 后端 | 怎么填 |
|---|---|
| **DeepSeek**（默认） | key 去 platform.deepseek.com 申请；预设 `deepseek-flash`（默认，快而省）、`deepseek-v4-pro`、`deepseek-chat`，也能手填 `deepseek-reasoner` |
| **Anthropic** | 原生 Messages API，`sk-ant-…`，模型如 `claude-sonnet-4-5-20250929` |
| **Gemini** | 原生 GenerateContent API，模型如 `gemini-2.5-flash` |
| **Ollama** | `ollama serve` 拉好模型，`base_url` 填 `http://127.0.0.1:<端口>/v1`，key 留空 |
| 其它 | 协议选 `auto` 或 `openai`，任何 OpenAI 兼容端点都行 |

三种协议跑的是同一套 agentic loop 与工具调用，设置里随时换。key 只写在 `agent/config.json`（已 gitignore），落盘时加密。

---

## 一次占卜的全程

**1. 你说「抽牌」。** 她列出 39 个牌阵让你点：单张、三张、凯尔特十字、生命之树、七脉轮、关系、二选一、是非、四季……每个牌位悬浮可见「这个位置在问什么」。这一步纯本地，零 API 调用。

**2. 她抽牌，但不解读。** 78 张牌不放回随机，按牌阵的传统几何摆开，逆位转 180°。摆完只问一句「你有什么问题吗？」——不知道你要问什么之前，她不开口。

**3. 你说出真正想问的事。** 她这才只对这副牌、围绕这个问题讲。落点是 **原本牌意 → 牌阵位置 → 对应问题 → 你的情境**；两张以上连读时，还会从元素、数字阶段、大小牌对位、宫廷牌、叙事弧线五个角度看牌与牌的关系（`knowledge/meanings/牌间关系.md`，是视角不是公式）。

**4. 读着读着，你可以打断她。** 点「停止」立刻收住，已经说出来的话留着，末尾标一句「已停止生成」。

**5. 想再看一面，就补一张。** 点「补一张」并写下理由（比如「想看清我忽略的那部分」）。补来的牌单列在「补牌 · 后来补上的视角」里，不替换原牌，理由会记进 `agent/data/extras.jsonl`。

**6. 看牌、存牌、听牌。** 双击任意牌出大图（逆位自动转正给你看清）；点「存这次解读」把牌面和她的话渲成一张 1080 宽的 PNG（浏览器下载，手机直接进相册 `Pictures/Olivia`）；点「朗读」让她念出来（浏览器走 Web Speech，安卓走系统 TTS）。

**7. 每次对话收尾都留个账。** 消息下面显示「本轮 tokens：入 x / 出 y」。设置里还能给每天设预算：接近上限会提示，超了就只做离线整理，不会悄悄烧钱；历史消息也会按条数和字符数自动裁剪，长对话不至于越聊越贵。

**8. 明天不聊也行。** 关怀面板里开「每日一牌」，每天到点她本地抽一张写进收件箱——**不调模型，没 key 也照常送达**。

---

## 安全边界

危机处理不是一句提示词，是服务端的一段代码。`/api/chat` 的请求一进来就先过 `agent/safety.py`：

- **先分类，再做事**：自伤、正在受暴力、性侵害、想伤害他人，各自对应不同的回应；识别顺序避免「我想杀了那个伤害我的人」被误判成自伤。
- **早于一切**：判定发生在视觉桥、抽牌、模型调用、记忆写入之前。危机请求不会发牌、不会调工具、不会把原文写进任何数据库。
- **给资源，不占卜**：回应里明确停止占卜，给出 110 / 120 与心理援助热线，并说明她不能替代专业帮助。
- **中英文都覆盖**：英文的 self-harm / abuse 表述同样能触发；否定句（「我不会自杀」）与梦境（「梦到有人追杀我」）不误报。
- **可选二次判定**：模糊表达可以在设置里打开 `safety_second_check`，额外调用一次分类，宁可多拦一次。

> 牌不开口，人开口。她可以陪你把牌读完，但不接管你的人生。

---

## 她的手

真 agentic loop，模型自己决定调谁，前端用 ⚙ 徽章显示每一步。

| 工具 | 干什么 |
|---|---|
| `draw_cards` | 按牌阵本地抽牌（不放回、带种子） |
| `search_knowledge` | 检索解牌方法、牌间关系、共情式倾听、伦理与转介 |
| `lookup_card` | 直查某张牌的韦特传统牌意（正 / 逆位） |
| `save_memory` | 记住你明确说过的偏好、边界、「请记住」 |
| `recall_memory` | 回想画像 / 线索 / 抽牌历史，或删掉一条记错的 |
| `save_note` / `search_notes` | 把你的笔记归档、翻出来 |
| `crisis_check` | 危机兜底（服务端的 `safety.py` 才是权威闸门） |
| `schedule_reminder` | 建定时提醒：一次 / 每天 / 每周 / 间隔 N 分钟 |

所以她听得懂「明晚八点提醒我」「我上次问过什么」「死神这张牌什么意思」——而不只是聊牌。

**定时与盯事**（`scheduler.py` / `watchers.py`，都在「关怀」面板管）：到点写一条关怀进收件箱并弹 Windows 通知；安静时段默认 22:00–08:00 不打扰，总开关默认关闭，一切本地跑。盯事支持网页 / RSS / JSON / 天气四种数据源，规则有 contains / regex / 数值阈值 / 变了 / 有新条目，**首次只建基线**，不会一上来就误报。

**视觉**（可选）：填任意 OpenAI 兼容 VLM 的 key，她把客观中文描述当成文字线索交给主模型。主模型仍是纯文本，不假装自己看见了。

---

## 她的记性

`agent/memory.py` 分四层存：**稳定画像**、**线索**（偏好与边界）、**对话**、**抽牌历史**。每轮按相关度注入，不用你重复自己。她也能**主动想**（`recall_memory`）和**主动忘**（删单条或清最近）。

另外两本：`agent/plugin_kb.py` 是你的**个人笔记库**（`kb.db`，可归档、检索、导出 Markdown），会话簿是**浏览器本地存的历次对话**（可命名、回访，深链 `#/chat/<id>`；危机对话只存占位，不存原文）。

想搬家或换机器，设置里能**整体导出 / 导入**一个 JSON：画像、线索、抽牌、对话、笔记、定时任务、盯事都在里面，**不含 key**。数据库用 WAL 并带 schema 版本号，升级时自动迁移，不会因为换版本把旧记忆读废。

---

## 联网与隐私

默认 `127.0.0.1`，只有本机能访问，没有任何配对步骤。

一旦 `AGENT_HOST` 不是回环地址，启动时会在控制台打印一个 8 位配对码（也存在 `agent/data/access_token`，用 `OLIVIA_TOKEN` 可指定自己的）。别的设备第一次打开要先输这串码，之后靠 HttpOnly Cookie 记住；脚本调用可以带 `X-Olivia-Token` 头。同一个 IP 十分钟内错 8 次会被暂时挡住。

对话、记忆、笔记、key 全在本机，不上传、不过中间服务器。API key 落盘前加密（Windows 走 DPAPI，其它平台退化为受限权限的包装）。想让她忘掉一切：删 `agent/data/`；想彻底清：删安装目录。

---

## 配置

`agent/config.json`（从 `config.example.json` 抄）：

```json
{
  "backend": "deepseek-flash",
  "base_url": "https://api.deepseek.com/v1",
  "api_key": "",
  "model": "deepseek-flash",
  "temperature": 0.8,
  "timeout": 120
}
```

环境变量：`AGENT_PORT`（默认 `8765`）、`AGENT_HOST`（默认 `127.0.0.1`）。

数据全在 `agent/data/`：`memory.db`（画像 / 线索 / 对话 / 抽牌）、`kb.db`（笔记）、`scheduler.db`（定时任务与收件箱）、`watchers.db`（盯事与基线）、`extras.jsonl`（补牌记录）。

---

## MCP

`agent/mcp_server.py` 是一个零依赖的 MCP stdio server，把「抽牌、查牌、检索、列牌阵」四件事交给别的客户端用，不联网、不碰你的记忆与 key。

```json
{
  "mcpServers": {
    "olivia-tarot": {
      "command": "python",
      "args": ["C:/path/to/tarot-counselor/agent/mcp_server.py"]
    }
  }
}
```

| 工具 | 返回 |
|---|---|
| `draw_cards` | 按牌阵本地抽牌，含牌位、正逆位、传统牌意、布局坐标与可复现种子 |
| `lookup_card` | 单张韦特牌意（正位 / 逆位 / 两者） |
| `search_knowledge` | 解牌方法、牌间关系、共情式倾听、伦理与转介 |
| `list_spreads` | 39 个牌阵的名称与位置说明 |

自检：`python agent/mcp_server.py --selftest`。

---

## 自查

只依赖标准库，**不碰真实模型 API**，没 key 也能跑：

```bash
python tests/test_whitebox.py     # 120 项：源码结构、纯函数、协议转换、牌阵完整性、配对/加密/迁移/MCP
python tests/test_blackbox.py     # 57 项：起独立服务发真实 HTTP 请求（含局域网配对）
```

黑盒会验证：危机请求不发牌、不调工具、先给求助资源；抽牌不放回；没有 key 时解读轮标 offline 且明说不是 AI 解读；历史里的危机残留不二次报警；深链路由与分享图按钮在首页；牌图可访问、目录穿越被拒；`AGENT_HOST=0.0.0.0` 时未配对 401、错码限流、对码后 Cookie 放行。它用 `AGENT_PORT` 起独立端口，不会打扰你正在跑的实例。

CI 在 Ubuntu 与 Windows 上跑 Python 3.9 / 3.12 四个组合，命令与上面一致。

---

## 手机端

`android/` 是**不重新实现任何逻辑**的 WebView 薄客户端——牌义、记忆、定时任务只有一份，手机只是个窗口。

- **连哪台机器**：`http://<电脑IP>:8765`；连不上会显示错误页，页里能直接改地址（默认填的是模拟器地址 `10.0.2.2:8765`）
- **手机上能做的**：抽牌 / 解读 / 补牌 / 停止 / 双击放大 / 存解读进相册 / 系统 TTS 朗读 / 关怀面板开每日一牌
- **第一次连真机**：电脑上 `AGENT_HOST=0.0.0.0 python agent/server.py`，手机与电脑同一 Wi-Fi，再输入控制台打印的配对码

自己出包，不需要 Android Studio，也不需要 Gradle：

```powershell
# 需要 JDK 17 + Android SDK（platform 34、build-tools 34.0.0）
powershell -NoProfile -ExecutionPolicy Bypass -File android\build.ps1
# 产物 android\build\Olivia-release.apk
```

签名默认读 `android\keystore\olivia-release.jks`（别名 `olivia`，示例口令 `olivia-tarot`，自己用请换掉），也可以 `-Keystore/-StorePass/-KeyAlias` 指定。细节见 [`android/README.md`](android/README.md)。

---

## 换个地方用她

- **当提示词**：`prompts/persona.zh.md`（可加 `tone.zh.md`）塞进 ChatGPT 自定义指令 / Claude Project / 自建 Agent 的 system prompt
- **当技能**：整个 `skills/tarot-counselor/` 放进技能目录（Claude Code `~/.claude/skills/`，DSH `~/.dsh/skills/`），平时是普通助手，求占或想说话时才加载

---

## 目录

```
.
├── prompts/                     # 人格 / 语气 / 预言模式（中英各一套）
├── skills/tarot-counselor/SKILL.md  # 按需加载的技能格式
├── knowledge/                   # 专业资料，入口 INDEX.md
│   ├── meanings/                # 大阿卡纳 + 四花色 + 解牌方法 + 牌间关系
│   ├── readings/                # 方法层：读牌流程、单张深读、逆位、宫廷牌
│   ├── spreads/牌阵速查.md
│   ├── skills/共情式倾听.md
│   └── ethics/危机与转介.md
├── agent/
│   ├── server.py                # HTTP 服务、API、两阶段抽牌与解读编排
│   ├── index.html               # 单页界面：对话 / 牌面 / 大图 / 分享图 / 关怀
│   ├── provider.py  llm.py      # 三协议流式调用 + usage 归一
│   ├── tools.py                 # 9 个工具的定义与执行
│   ├── spreads.py               # 39 个牌阵的唯一来源
│   ├── safety.py  offline.py    # 危机闸门 / 离线整理降级
│   ├── memory.py  knowledge.py  # 记忆分层 / 知识检索
│   ├── scheduler.py  watchers.py # 定时关怀（含每日一牌）/ 条件盯事
│   ├── auth.py  secret_store.py # 局域网配对 / 密钥加密
│   ├── db.py  backup.py         # schema 迁移 / 全量导出导入
│   ├── mcp_server.py            # MCP stdio server
│   ├── static/                  # 拆分后的 CSS / JS / PWA 资源
│   ├── cards/                   # 78 张 RWS 牌面
│   └── data/                    # 数据库与记录（gitignore）
├── android/                     # 手机端：WebView 薄客户端
├── installer/                   # Windows 单文件安装器
├── docs/                        # 架构、自托管与截图
├── tests/                       # 白盒 + 黑盒自查
├── README.en.md                 # 英文版
└── README.md
```

---

## 许可

默认是「**随便玩，但别拿去赚钱**」，分两条许可：

| 内容 | 许可 | 一句话 |
|---|---|---|
| `agent/` `android/` `installer/` `tests/`（程序代码） | [PolyForm Noncommercial 1.0.0](LICENSE) | 代码：可自用、可改着玩，不能商用 |
| `prompts/` `skills/` `knowledge/`（人格、语气、牌义、牌阵、解牌方法） | [CC BY-NC-SA 4.0](LICENSE-CONTENT) | 文字与人格：署名、非商业，改编须同样授权 |
| `agent/cards/` 78 张牌面 | 公有领域（1909 RWS） | 不需要授权，出处见 `agent/cards/SOURCE.md` |

可以：下载、装在自己电脑或手机上用、读源码、改着玩、给朋友看、非商业地分享（带上 `LICENSE` 与 `Required Notice` 那行署名）。

不可以：拿去商用——卖、作为付费产品或服务的一部分、在公司里当生产工具、换个名字包装成自己的产品再发布。

**想商用？** 可以单独买商业授权，见 [`COMMERCIAL.md`](COMMERCIAL.md)。个人、学习、研究、非营利用途不用联系，直接用。

「Olivia / 奥莉薇娅」的名字与人格设定归作者所有，换品牌对外提供需在合同中单独约定。
