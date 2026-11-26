# 贡献指南

Olivia 是一个本地优先的塔罗 agent：牌在本机抽，记忆在本机存，只有解读那一步会连模型。欢迎修 bug、补测试、改文档、扩牌义，也欢迎提 issue 说清楚哪里不好用。

参与之前请先读 [`SECURITY.md`](SECURITY.md) 与 [`README.md`](README.md)。涉及安全边界、隐私或数据落盘的改动，请在 PR 描述里单独说明。

## 开发环境

- **只需要 Python 3.9 或更高版本**，不装任何第三方包，不用 pip、不用虚拟环境也能跑。
- Windows / macOS / Linux 都可以。Windows 安装器与安卓客户端另有各自工具链，见 `installer/README.md` 与 `android/README.md`。
- 第一次启动会在 `agent/data/` 下自动建库，在 `agent/config.json` 里保存配置。这两处都在 `.gitignore` 里，**不要提交**。

## 启动

```bash
# 在仓库根目录
python agent/server.py
```

也可以进 `agent/` 再运行 `python server.py`。

浏览器打开 <http://127.0.0.1:8765>，右上角「设置」填自己的 API key。没有 key 也能抽牌、看牌、看离线整理，只是不能调模型解读。

环境变量：

| 变量 | 默认 | 说明 |
|---|---|---|
| `AGENT_HOST` | `127.0.0.1` | 只监听本机；要让手机连才改成 `0.0.0.0` |
| `AGENT_PORT` | `8765` | HTTP 端口 |

## 测试

两套自查都只用标准库，不碰真实模型 API，没 key 也能跑：

```bash
python -m compileall -q agent tests   # 先过一遍字节编译
python tests/test_whitebox.py         # 纯函数与模块级，187 项
python tests/test_blackbox.py         # 起真实服务发 HTTP 请求，75 项
python tests/test_safety_redteam.py   # 安全闸门红队对抗，267 项（含已知缺口清单）
python tests/test_mcp_http.py         # Streamable HTTP 传输，27 项
python tests/test_backup_crypto.py    # 加密备份，8 项
python tests/test_tls_server.py       # 局域网自签 HTTPS，7 项
python tests/test_demo_mode.py        # 只读演示模式，48 项
python tests/test_share_link.py       # 分享深链，22 项
```

注意事项：

- 黑盒测试会自己用 `18765` 端口起一个独立服务，**不要和白盒并行跑**，也不要在同一个 job 里并行化这两个步骤。
- 如果 `18765` 被占用，可以换端口：`python tests/test_blackbox.py --port 18766`。
- 改了 `agent/safety.py`、抽牌逻辑、协议转换或牌阵布局，必须跑两套测试，并按需补用例。
- CI 在 Ubuntu 与 Windows 上跑 Python 3.9 / 3.12 四个组合，命令与上面一致。

## 代码结构

| 文件 | 职责 |
|---|---|
| `agent/server.py` | HTTP 路由、两阶段抽牌编排、SSE 输出、安全闸门入口 |
| `agent/index.html` | 界面壳；样式、脚本与 PWA 资源在 `agent/static/` |
| `agent/static/` | `app.css` / `app.js` / `i18n.js` / `manifest.webmanifest` / `sw.js` |
| `agent/auth.py` | 局域网配对码、Cookie、`X-Olivia-Token` 与失败限流 |
| `agent/backup.py` | 用户数据整体导出与合并导入（不含 API key） |
| `agent/db.py` | SQLite 连接与 schema 版本迁移 |
| `agent/provider.py` | OpenAI 兼容 / Anthropic / Gemini 三协议流式适配与工具调用 |
| `agent/llm.py` | 面向定时关怀的简单 OpenAI 兼容补全客户端 |
| `agent/tools.py` | 9 个工具的定义、执行与界面摘要 |
| `agent/spreads.py` | 39 个牌阵的定义、几何布局与目录输出 |
| `agent/safety.py` | 中英文危机类别判定、可选二次检查与安全回应文案 |
| `agent/offline.py` | 无可用模型时按牌位、牌意做离线整理 |
| `agent/memory.py` | 四层本地记忆与每日 token 用量：画像、线索、对话、抽牌历史 |
| `agent/knowledge.py` | 对 `knowledge/` 的中文二元组关键词检索与牌义直查 |
| `agent/scheduler.py` | 定时关怀、每日一牌、收件箱与后台线程 |
| `agent/watchers.py` | 条件盯事：网页 / RSS / JSON / 天气数据源与规则 |
| `agent/plugin_kb.py` | 个人笔记库（归档、检索、导出 Markdown） |
| `agent/plugin_vision.py` | 可配置的视觉桥：图片交给第三方 VLM 转文字描述 |
| `agent/secret_store.py` | 保存前加密 API key：Windows DPAPI，其他平台 base64 + 权限收紧 |
| `agent/mcp_server.py` | 独立 MCP stdio 服务：只读地暴露抽牌、查牌、检索与牌阵 |
| `agent/cards/` | 78 张公有领域 RWS 牌面 |
| `prompts/`、`knowledge/`、`skills/` | 人格、语气、牌义、解牌方法与技能格式 |
| `tests/` | 白盒与黑盒自查 |
| `installer/`、`android/` | Windows 安装器与安卓 WebView 薄客户端 |

更细的调用链、SSE 事件与数据落盘位置见 [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md)。

## 提交信息风格

参考仓库现有的 `git log --oneline`：**一行中文短句，说清这次改动带来的结果**，不加句号，不写空话。常见写法：

```text
服务端安全闸门 + 三协议 + 会话簿路由 + 黑白盒自查
离线整理降级 + 本地分享图导出 + 扩充自查
安卓客户端：把 Olivia 装进手机
窄屏顶栏避开状态栏/灵动岛：viewport-fit=cover + 安全区留白
```

- 一个提交只做一件逻辑上的事；格式化、重命名、功能改动尽量分开。
- `feat:` / `fix:` 前缀可以用，但不是必须；中文短句本身要能读懂。
- 描述“为什么”和“结果”，不要只写“改代码”“update”。
- 不要把无关文件、个人数据或构建产物混进提交。

## 安全与隐私红线

这些不是建议，是硬约束：

1. **不得把用户记忆、对话、密钥写进仓库。** `agent/config.json`、`agent/data/`、`*.db`、`*.jsonl`、`agent/olivia.pid` 永远不提交；截图与日志先脱敏。
2. **不得增加静默上报。** 没有遥测、没有远程日志、没有“顺便上传一份”。新增任何外发请求（模型、VLM、盯事数据源）都必须在 PR 里写明发什么、发给谁。
3. **改 `agent/safety.py` 必须补测试。** 至少覆盖：命中、不命中、否定句、梦境/虚构语境、类别优先级。现有用例在 `tests/test_whitebox.py`。
4. **不得把安全闸门后移。** `/api/chat` 入口必须先过 `safety.detect()`，早于视觉桥、抽牌、模型调用与记忆写入；命中时不得发牌、不得调工具、不得落库。
5. **不得削弱危机处理。** 历史里的危机残留要继续被过滤；危机内容不得被提升为长期记忆或用于后续占卜。
6. **密钥只留在本机。** 不要把 key 写进源码、示例配置、测试、日志或 issue；`config.example.json` 的 `api_key` 必须为空。
7. **第三方素材要可授权。** 不要粘贴来源不明的牌义、牌面或提示词；新增内容要能说明出处与许可。

## 许可

提交即表示你同意按仓库现有许可授权你的贡献：

| 内容 | 许可 |
|---|---|
| `agent/`、`android/`、`installer/`、`tests/` 等程序代码 | [PolyForm Noncommercial 1.0.0](LICENSE) |
| `prompts/`、`skills/`、`knowledge/` 等文字与人格内容 | [CC BY-NC-SA 4.0](LICENSE-CONTENT) |
| `agent/cards/` 的 78 张 RWS 牌面 | 公有领域，出处见 `agent/cards/SOURCE.md` |

代码可自用、可修改，但不能商用；文字内容需署名、非商业、改编后同样授权。想商用请先看 [`COMMERCIAL.md`](COMMERCIAL.md)。提交 PR 不代表获得商业授权，也不得把本项目代码或内容重新授权为更宽松的许可。

## English summary

Olivia is a local-first tarot agent built with the Python standard library only. To contribute, use Python 3.9+ with no third-party packages, start the app with `python agent/server.py`, and run `python tests/test_whitebox.py` followed by `python tests/test_blackbox.py` sequentially (the black box test starts its own server on port 18765). Keep commits as short, outcome-focused Chinese sentences, matching the existing git log. Never commit API keys, user memory, conversations, databases or build artifacts; do not add silent telemetry; any change to `agent/safety.py` must include tests, and the server-side crisis gate must stay before vision, drawing, model calls and memory writes. By submitting a contribution you agree to license code under PolyForm Noncommercial 1.0.0 and written content under CC BY-NC-SA 4.0.
