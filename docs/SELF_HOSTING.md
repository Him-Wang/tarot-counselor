# 自托管指南

Olivia 只有一台服务：`agent/server.py`。它用 Python 标准库提供网页、SSE 接口、抽牌、记忆、定时任务与安全闸门。下面分别说明源码、Docker 与 Windows 安装器三种跑法，以及手机连接、访问令牌、备份与彻底删除。

## 方式一：源码运行

环境只需要 **Python 3.9+**，不装任何 pip 包。

```bash
# 在仓库根目录
python agent/server.py
```

也可以：

```bash
cd agent
python server.py
```

浏览器打开 <http://127.0.0.1:8765>。第一次启动会自动创建 `agent/data/`；右上角「设置」里填自己的模型 API key。没有 key 也能抽牌、看牌与读离线整理。

可选环境变量：

| 变量 | 默认 | 说明 |
|---|---|---|
| `AGENT_HOST` | `127.0.0.1` | 只监听本机；手机连接时改为 `0.0.0.0` |
| `AGENT_PORT` | `8765` | HTTP 端口 |
| `OLIVIA_TOKEN` | 空 | 局域网访问令牌；为空时自动生成配对码 |

## 方式二：Docker

仓库自带 `Dockerfile` 与 `docker-compose.yml`，镜像基于 `python:3.12-slim`，不安装任何 pip 包。

```bash
docker compose up -d --build
docker compose logs -f olivia
```

打开 <http://127.0.0.1:8765>。停止与重建：

```bash
docker compose stop        # 停止
docker compose up -d       # 再启动
docker compose down        # 删除容器（不删 ./agent/data）
```

说明：

- 服务在容器内监听 `0.0.0.0:8765`，compose 把端口发布到宿主机所有网卡；同网段设备可能直接访问。只想本机访问时，把 `ports` 改成 `"127.0.0.1:8765:8765"`。
- 因为容器内不是回环地址，配对鉴权默认开启；**本机浏览器第一次打开也要输入配对码**，从下面的日志里取。
- `./agent/data` 绑定到 `/app/agent/data`，记忆、笔记、定时任务与配对码都在这里持久化。
- **配置注意**：`agent/config.json` 不在数据卷里，只存在容器内部。`docker compose down` 后重新 `up`，需要在设置里重新填一次 key（容器内会重新加密保存）。要避免这一点，可以自行在 compose 里再加一条 `./agent/config.json:/app/agent/config.json` 的绑定，并先在宿主机准备好文件（否则 Docker 会建出同名目录）。
- compose 会把 `OLIVIA_TOKEN` 注入容器；不设置时容器会在 `agent/data/access_token` 生成 8 位配对码，并以 `xxxx-xxxx` 的形式打印在日志里：

```bash
docker compose logs olivia | Select-String -Pattern "token|配对"
```

（Linux / macOS 用 `grep -E "token|配对"`。）

- 需要换端口时，同时改 `ports` 与 `AGENT_PORT`，例如 `"9000:9000"` 与 `AGENT_PORT=9000`。

## 方式三：Windows 安装器

从 [最新 Release](https://github.com/Him-Wang/tarot-counselor/releases/latest) 下载 `Olivia-setup.exe`（约 11 MB）：

1. 双击安装器。若提示没有 Python 3，按提示安装 Python 并勾选 **Add Python to PATH**，然后重新运行安装器。
2. 选择安装目录（默认 `%LOCALAPPDATA%\Olivia`）与是否开机自启。
3. 安装器建桌面 / 开始菜单快捷方式，后台启动服务，并打开 <http://127.0.0.1:8765>。
4. 在右上角「设置」填 API key。

以后双击桌面「Olivia 奥莉薇娅」即可启动，不会弹出命令行窗口。数据与配置都在安装目录里：

- 配置：`%LOCALAPPDATA%\Olivia\agent\config.json`
- 数据：`%LOCALAPPDATA%\Olivia\agent\data\`

卸载：Windows「设置 → 应用」里卸载，或删除安装目录后手动清理快捷方式与开机自启项。

## 局域网与手机连接

手机客户端只是窗口，连的是电脑上的同一台 Olivia。

1. 在电脑上显式开放到局域网。

   PowerShell：

   ```powershell
   $env:AGENT_HOST="0.0.0.0"
   python agent/server.py
   ```

   bash：

   ```bash
   AGENT_HOST=0.0.0.0 python agent/server.py
   ```

   用 Docker 时默认已经监听 `0.0.0.0`，无需额外设置。

2. 查电脑的局域网 IP：Windows 运行 `ipconfig`，找当前 Wi-Fi / 以太网的 IPv4 地址，例如 `192.168.1.23`；Linux / macOS 用 `ip addr` 或 `ifconfig`。

3. 允许防火墙：Windows 首次启动可能弹出防火墙提示，只勾选**专用网络**，不要对公用网络放行。没有弹窗时，确认入站规则允许 Python 使用专用网络。

4. 手机与电脑连同一个 Wi-Fi：

   - 手机浏览器打开 `http://192.168.1.23:8765`。
   - 安卓 App 首次打开默认是模拟器地址 `10.0.2.2:8765`，在错误页或设置里改成上面的地址。

5. 用完把 `AGENT_HOST` 改回 `127.0.0.1` 并重启服务，不要长期对局域网开放。

局域网模式没有 TLS，同一 Wi-Fi 下的其他人可能看到流量；请在可信网络使用，并设置访问令牌。

## `OLIVIA_TOKEN` 与配对码

局域网访问需要访问凭证，规则只有两条：

1. **设置了 `OLIVIA_TOKEN`，就用它。** 例如：

   ```bash
   # bash
   OLIVIA_TOKEN="$(python -c 'import secrets; print(secrets.token_urlsafe(24))')" \
     AGENT_HOST=0.0.0.0 python agent/server.py
   ```

   ```powershell
   # PowerShell
   $env:OLIVIA_TOKEN = (python -c "import secrets; print(secrets.token_urlsafe(24))")
   $env:AGENT_HOST = "0.0.0.0"
   python agent/server.py
   ```

   Docker 可以写在 `docker-compose.yml` 同目录的 `.env` 里：

   ```dotenv
   OLIVIA_TOKEN=把这里换成一串足够长的随机字符
   ```

2. **没有设置 `OLIVIA_TOKEN`，服务会自动生成。** 配对码是 8 位十六进制码，写在 `agent/data/access_token`，并以 `abcd-1234` 的形式打印到控制台。Docker 里看 `docker compose logs olivia`。

首次连接时，浏览器/安卓会要求输入配对码；校验通过后写入 `HttpOnly` Cookie，同一设备之后直接可用。也可以直接打开 `http://<电脑IP>:8765/?token=<配对码>` 让它种下 Cookie，或在命令行带 `X-Olivia-Token` 请求头。配对接口对每个 IP 有失败限流（默认 10 分钟内 8 次）。注意：

- 配对码等同密码，不要截图、不要贴群、不要提交到仓库。
- 自定义 `OLIVIA_TOKEN` 时至少 8 位，建议用 `secrets.token_urlsafe(24)` 这类随机串；配对时请输入你设置的**完整值**。控制台里的 `xxxx-xxxx` 是自动生成 8 位短码的展示，长令牌会被截短显示，不能直接当完整令牌用。
- 轮换：停服务，删除 `agent/data/access_token`（或改掉 `OLIVIA_TOKEN`），重启；旧配对码立即失效。
- 忘记配对码：直接读 `agent/data/access_token`；文件不在就重启让它重新生成。
- 它是明文 HTTP 上的凭证，只适合可信局域网；不要把 `8765` 端口转发到公网。需要公网访问时，请走 VPN、SSH 隧道或带 TLS 与身份认证的反向代理。

## 备份与恢复

最轻量的备份在界面里：设置中的「导出全部数据」会下载一个 JSON，包含画像、线索、抽牌历史、笔记、定时任务、盯事规则与补牌记录，**不包含原始对话消息与 API key**；「导入备份」是合并模式，不会清空现有数据。适合日常留档与换设备迁移用户数据。

要做完整快照（包含密钥、配对码与视觉桥配置）时，按下面的文件级方式：

| 路径 | 内容 |
|---|---|
| `agent/data/memory.db` | 画像、线索、对话、抽牌历史、每日 token 用量 |
| `agent/data/kb.db` | 个人笔记库 |
| `agent/data/scheduler.db` | 定时任务、收件箱、关怀设置 |
| `agent/data/watchers.db` | 条件盯事与基线 |
| `agent/data/extras.jsonl` | 补牌记录与理由 |
| `agent/data/plugins.json` | 视觉桥配置与 key（明文） |
| `agent/data/access_token` | 局域网配对码 |
| `agent/config.json` | 主模型配置与加密后的 key（`api_key_enc`） |

备份步骤（源码 / Windows 安装器）：

1. **先停服务**（`Ctrl+C`，或退出安装器启动的后台进程）。SQLite 使用 WAL，运行中直接复制可能漏掉未合并的数据。
2. 复制整个 `agent/data/` 目录；需要连同模型配置一起迁移时，再复制 `agent/config.json`。
3. 存到加密盘或加密压缩包。备份里既有记忆，也可能有加密后的密钥、视觉桥 key 与配对码，应当按机密材料保管。
4. Windows 上用 DPAPI 加密的 `api_key_enc` 只能被同一 Windows 用户解开；换机器或换系统账户后，通常需要在设置里重新填一次 key。其他平台是 base64 包装，可跨机读取，但不提供强机密性。

```powershell
# PowerShell 示例：仓库根目录
Copy-Item -Recurse agent\data D:\backup\olivia-data
Copy-Item agent\config.json D:\backup\olivia-config.json
```

Docker：

```bash
docker compose stop
tar -czf "olivia-data-$(date +%F).tar.gz" agent/data
docker compose start
```

恢复：

1. 停服务。
2. 只恢复用户数据时，用界面的「导入备份」选择 JSON；做完整快照恢复时，把备份的 `data/` 放回 `agent/data/`，需要时放回 `config.json`。
3. 确认当前系统账户对目录有读写权限；Docker 场景下注意容器以 root 运行，必要时修正属主。
4. 启动服务，打开页面确认记忆、笔记与定时任务都在；key 解不开就到设置里重填。

升级前建议先备份。跨大版本恢复时，先在同一大版本上验证数据可读，再升级。

## 彻底删除数据

按使用方式选择：

**源码运行**

1. 停服务（`Ctrl+C`）。
2. 删除 `agent/data/`、`agent/config.json` 与 `agent/olivia.pid`。
3. 如果曾经把数据复制到别处，那些备份不会自动消失，需要单独删除。

**Windows 安装器**

1. 在 Windows「设置 → 应用」里卸载 Olivia；或手动停止后台进程。
2. 删除安装目录（默认 `%LOCALAPPDATA%\Olivia`），其中包含 `agent\data\` 与 `config.json`。
3. 删除桌面 / 开始菜单快捷方式；如果开过机自启，清理启动项。

**Docker**

1. `docker compose down` 删除容器。
2. 删除宿主机上的 `./agent/data/` 目录。`docker compose down -v` 会清理命名卷，但本项目用的是绑定目录，仍需手动删。
3. 需要连镜像一起清理时：`docker image rm <镜像名>`。

**浏览器与手机**

- 浏览器：对 `http://127.0.0.1:8765` 清除站点数据（`localStorage` 里的会话簿与深链）。
- 安卓：系统设置里清除 Olivia 的应用数据；再删除相册 `Pictures/Olivia` 里导出的分享图。

服务端数据删掉后，已导出的分享图、聊天截图、备份包与其它设备上的缓存仍然存在，需要分别处理。想确认清干净，可以在删除后重新启动，页面应回到没有记忆、没有笔记、需要重新填 key 的初始状态。
