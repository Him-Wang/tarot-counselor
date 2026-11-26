# 公开只读演示 / Public read-only demo

> ⚠️ **先读这句**：Olivia 默认是「本机私人工具」，会把记忆、笔记、定时任务、盯事、占卜档案写在 `agent/data/`。**绝对不要把非演示模式直接暴露到公网。** 公网演示只能用下面这套只读配置。

## 中文

### 这是什么

演示模式（demo mode）是 Olivia 的一个只读运行方式，给公开访问用。开启后：

- **不接模型、不发网络请求**：任何 API key 都会被丢弃，`backend` 显示为 `offline`，回复是本地离线整理（牌义 + 客观提问），开头明确写着「离线整理……不是 AI 解读」。
- **不落盘、不留痕**：不写 `config.json` / `memory.db` / `kb.db` / `scheduler.db` / `watchers.db`，不记笔记、任务、盯事、占卜档案，不追加 `extras.jsonl`，不写视觉模型配置；内存里的抽牌与待办状态在每个请求开始时清空，两个访客之间互不串味。
- **关掉会写库的功能**：记忆、神秘学（通灵 / 召唤 / 仪式）、预言模式、二段安全复查全部关闭；工具调用、语气、两阶段抽牌这几个产品硬开关保持开启。
- **有可见标识**：`GET /api/config` 返回 `"demo": true`，页面顶部出现一条「演示模式」提示条，命令行启动时也会打印醒目横幅。

### 怎么安全地跑

本仓库当前版本的 `agent/server.py` 只从环境变量读 `AGENT_HOST` / `AGENT_PORT`（没有 `--host` / `--port` 命令行参数）。等价写法：

```bash
# 在仓库根目录（Python 3.9+，无需 pip 依赖）
OLIVIA_DEMO=1 AGENT_HOST=127.0.0.1 AGENT_PORT=8765 python agent/server.py
```

Windows PowerShell：

```powershell
$env:OLIVIA_DEMO="1"; $env:AGENT_HOST="127.0.0.1"; $env:AGENT_PORT="8765"; python agent/server.py
```

如果父流程后续为 `server.py` 加了 `--host` / `--port` / `--demo` 参数，则等价命令是
`OLIVIA_DEMO=1 python agent/server.py --host 127.0.0.1 --port 8765`；`--demo` 与环境变量二选一即可。

**一定要放在反向代理后面，用 HTTPS 对外**：

```
访客 ──HTTPS──> Caddy / nginx（TLS + 限速 + 超时）──HTTP──> 127.0.0.1:8765（仅回环）
```

Caddy 最小示例（`Caddyfile`）：

```caddyfile
demo.example.com {
    reverse_proxy 127.0.0.1:8765
}
```

nginx 最小示例：

```nginx
server {
    listen 443 ssl;
    server_name demo.example.com;
    ssl_certificate     /etc/letsencrypt/live/demo.example.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/demo.example.com/privkey.pem;
    location / {
        proxy_pass http://127.0.0.1:8765;
        proxy_set_header Host $host;
        proxy_read_timeout 60s;   # 见下方超时建议
    }
}
```

Docker 同样可以：给容器加 `OLIVIA_DEMO=1` 环境变量，并把发布端口限制为 `127.0.0.1:8765:8765`（不要用 `0.0.0.0`）。

### 建议的运维参数

| 项目 | 建议 | 原因 |
|---|---|---|
| 反向代理超时 | 30–60s（`proxy_read_timeout` / Caddy `reverse_proxy` 超时） | 演示只走本地离线整理，不需要等模型 120s |
| 自动重置 | 每个 HTTP 请求开头清空内存状态（demo guard 已实现） | 不跨请求累积会话内容 |
| 会话回收 | 给浏览器侧定时刷新 / 强制新 `session_id`；代理层可限制单 IP 请求频率 | 防止单个访客长期占用 |
| 进程重启 | 每天或每次升级后重启进程 | 内存态彻底归零；演示模式无数据可丢 |
| 日志 | 不要开启记录请求正文的代理日志 | 问题文本本身就是用户数据 |

### 限制与边界

- 没有模型调用，所以回答是固定的本地话术，**不是 AI 解读**，也不会结合历史。
- 不能保存记忆 / 笔记 / 任务 / 档案；刷新页面即忘，这是设计目标而不是 bug。
- 因为每个请求都清空待抽牌状态，「先抽牌、后提问」的两阶段流程在演示中会被打断，聊天里会直接本地抽牌，这是预期行为。
- 演示模式是「纵深防御」，不是沙箱：如果另有 worker 直接绕过 guard 调用某个 DB 模块，仍可能写文件。审计时请检查 `agent/demo_mode.py` 文档里列出的全部写入点都已接上 `guard_write()` / `should_persist()`。

## English

`OLIVIA_DEMO=1` starts Olivia as a **public, read-only demo**. It discards every
API key, forces offline canned replies, disables memory / occult / prophecy /
second-check, blocks all disk writes, and clears in-memory session state on
every request. `GET /api/config` returns `"demo": true` and the UI shows a
persistent banner. Bind to `127.0.0.1` and put it behind an HTTPS reverse proxy
(e.g. Caddy: `reverse_proxy 127.0.0.1:8765`); set a 30–60s proxy timeout and
restart the process periodically. Replies are local, offline guidance — **not
AI readings**. Never expose a normal (non-demo) instance to the internet: it
persists conversations, memory, notes, tasks and archives under `agent/data/`.
