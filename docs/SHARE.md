# 分享深链 / Share deep links

## 是什么 / What it is

抽完一副牌之后，点侧边栏「分享图」旁边的 **「分享链接」**，Olivia 会复制一条
`<页面地址>?reading=<token>` 的网址。别人打开这条网址，看到的是那副牌的
**只读预览**：牌阵、问题、牌面（牌位 / 牌名 / 正逆位）和一段静态
提示。它不写访问者的记忆、笔记、目标或档案，也不调用模型，不改 URL 里的
会话（`#/chat/<id>`）。

After drawing a spread, click **分享链接 / Share link** next to the existing
PNG share button. Olivia copies `<page>?reading=<token>`. Opening it shows a
**read-only preview**: spread, question, cards (position / name /
orientation) and static hints. It never writes to the viewer's memory, notes,
goals or archive, never calls the model, and never touches their chat session.

## 格式 / Token format

两边一致的一个格式，两种可接受的编码（`agent/share_link.py` 的 `decode()` 都收）：

One agreed format, two accepted encodings (both handled by `agent/share_link.py:decode`):

| 形式 | 产生方 | token |
|---|---|---|
| 明文 plain | 浏览器 `agent/static/app.js` | `o1.<base64url(UTF-8 紧凑 JSON, 无 padding)>` |
| 压缩 compact | Python `agent/share_link.py:encode()` | `o1z.<base64url(zlib.compress(JSON, 9))>` |

payload（UTF-8, `separators=(',', ':')`，键顺序无关）：

```json
{"v":1,"spread":"三张","question":"...",
 "cards":[{"name":"愚者","orientation":"正位","position":"过去"}]}
```

- `v` 必须是 `1`；token ≤ 16 KB；解码后 JSON ≤ 16 KB；`cards` ≤ 78 张。
- 浏览器端用 `TextEncoder` + `btoa` 做了 UTF-8 → base64url（去掉 `=`）；
  Python 端用 `urlsafe_b64encode(...).rstrip(b'=')`，完全等价。
- 解码只走 `json.loads` / `zlib.decompress`，**绝不 eval / pickle**；
  损坏、未知前缀、超大、版本不符的 token 一律返回 `None`，页面不做任何事。

## 安全边界 / Security notes

- 分享链接里只有牌面文字，**没有 API key、没有记忆、没有图片**；图片不内嵌，
  只读预览不展示牌图（避免外部图片加载）。
- 静态分享**没有密钥**，所以 token 只靠 zlib CRC / JSON 语法做损坏检测，
  **不是 HMAC、不可认证**：别人可以改 token 内容。前端所有字段一律按不可信
  文本转义（`escHtml`），预览不执行任何来自 token 的脚本。
- 只读保证在浏览器端：打开 `?reading=` 时跳过会话簿装载和 `newSession()`，
  锁住输入框与发送键，`mountShareViewer` 只创建 DOM；无 `/api/chat` 调用、
  无 `localStorage` 写入。查看者点「回到我的 Olivia」即回到普通模式。

## 兼容 / Compatibility

`agent/share_link.py:decode()` 同时接受 `o1.`（浏览器明文）与 `o1z.`（Python
压缩）两种 token；`encode()` 产出紧凑的 `o1z.`。若服务端以后要生成链接，直接
调用 `share_link.encode(payload)` 即可，前端查看器只读 `o1.`，故服务端生成链接
应输出 `o1.` 明文形式（把 `json.dumps(payload, ensure_ascii=False,
separators=(',', ':'))` 按同样 base64url 编码）；`o1z.` 仅供 Python 侧解码兼容。
