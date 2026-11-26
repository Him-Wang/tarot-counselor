# 安全、边界与 AI 披露

> Olivia 是一款在本地运行的 AI 塔罗陪伴程序。她陪你把牌读完，但不替你决定，也不能替代专业帮助。
> 使用即表示你理解并接受下面这些边界。

---

## 1. AI 身份披露

- **Olivia 是一个人工智能程序**，不是持证心理治疗师、心理咨询师，也不是医生、律师或财务顾问。
- 她的输出只用于**娱乐与自我反思辅助**：把牌面、你的问题和你的处境放在一起，提供一个看待事情的视角。它**不是诊断、不是预测、不是专业意见**。
- 解读文字由你配置的模型生成；没有配置 key 时，由本地离线整理生成并明确标注「离线整理」。两种情况下都可能出错，也可能带有模型自身的偏差。请把它当作参考，而不是结论。
- 涉及健康、法律、财务或人身安全的决定，请以持证专业人士的意见为准，不要以 Olivia 的话为依据。

---

## 2. 代码级危机闸门会做什么

Olivia 有一条**写在服务端代码里的**安全闸门（`agent/safety.py`），它不是提示词里的请求。它位于 `/api/chat` 入口，**早于视觉、抽牌、模型调用和记忆写入**执行。

- 它识别五类情况：`self`（自伤 / 轻生）、`threat`（他人施暴或威胁）、`sexual-assault`（性侵 / 性暴力）、`sexual-harm`（伤害他人的性意图）、`harm-others`（伤害他人）。
- 一旦命中，Olivia **不解读牌、不调用模型、不把原文写进记忆、会话簿或占卜档案**，而是停下来，先给出支持性回应和现实中的求助资源。
- 它也做了基本的误报抑制：明确否定句（如「我不会自杀」）和梦境 / 虚构语境通常不会触发。

**重要限制：**

- 这套检测是**基于正则关键词**的，会漏掉隐喻、谐音、间接表达和中英混写的变体；误报和漏报都真实存在。
- 可选的「二次判断」（`safety_second_check`，让模型对模糊语句做一次 YES/NO 分类）**默认关闭**，且只对少量模糊词触发。
- 因此，**不要把这条闸门当作安全网**。如果你或身边的人正处于危险中，请直接联系现实中的紧急服务或可信赖的人，不要等待程序先识别出来。

红队套件 `tests/test_safety_redteam.py` 收录了 **267 个对抗用例**，并公开记录了 **70 个已知缺口**（隐喻、规避写法、英文变体、误报等）。这是持续进行中的工作，而不是「已经完全安全」的证明。

---

## 3. Olivia 不会做的事

- **不预测具体未来事件**：不预测日期、输赢、生死或具体结果。只有当你显式开启「预言模式」时，才会以娱乐口吻谈论「预测」，且输出明确标注「仅供娱乐」，不构成事实判断。
- **不替你做决定**：不替你选工作、伴侣或人生方向。目标状态和下一步建议都需要你亲自确认；MCP 写入接口也只开放「新增 / 提建议」，没有替你拍板的工具。
- **不给医疗、法律、财务建议**：不替代诊断、治疗、法律意见或投资建议。
- **不提供有害的仪式指令**：即使开启「神秘模式」（occult mode），也只提供象征性、文化性的解读视角，不会给出伤害自己或他人、或替代正规医疗的「仪式」步骤。
- **遇到危机停止占卜**：在风险面前，牌局让位于人和安全。

---

## 4. 遇到危机时，先找现实中的帮助

如果你或身边的人可能受到伤害，请按下面的顺序求助：

1. **拨打当地紧急电话。** 中国大陆：`110`（报警）、`120`（急救）；美国 / 加拿大：`911`。其他地区请拨打当地紧急号码。
2. **去最近的医院急诊。** 已经受伤、服药过量或失去意识时，不要等待「确认严重」。
3. **联系一个信得过的人。** 一句话就够：「我现在需要你陪我。」
4. **查找当地的危机干预 / 心理援助热线。** 热线号码会随地区和时间变化，请以当地官方或权威机构当前公布的信息为准；本文件刻意不列出可能过期的具体号码。
5. 不确定该打哪一个时，**优先拨打当地紧急电话**，接线员会帮你转接。

Olivia 不能替你完成以上任何一步。她的角色是在你安全之后，再陪你坐下来看牌。

---

## 5. 数据与隐私

- **本地优先。** 对话、记忆、笔记、抽牌历史存放在本机 `agent/data/` 与浏览器本地；项目自身没有遥测或分析服务器。
- **危机原文不入库。** 闸门命中时，原文不会写入记忆、会话簿或占卜档案。
- **但仍需注意**：正常解读会把对话上下文发给你配置的第三方模型服务商；开启视觉桥后，图片会发给第三方 VLM，受该服务商的留存政策约束。
- **局域网是明文 HTTP。** 设置 `AGENT_HOST=0.0.0.0` 后，同一网络可能看到配对码与对话内容。请只在可信网络临时使用，不要把端口映射到公网或暴露到不可信网络；长期远程访问请用 VPN 或带 TLS 与身份认证的反向代理。
- 更完整的技术威胁模型与加固建议见 [SECURITY.md](SECURITY.md)。

---

## 6. 如何反馈安全问题

- 一般的安全边界、文档或行为问题：请到 GitHub 仓库 **Him-Wang/tarot-counselor** 开 **Issue**，描述你看到的行为、期望的边界和复现方式。请勿在 issue 中粘贴真实对话、记忆或密钥。
- 可复现的安全漏洞：不要公开 issue。请按 [SECURITY.md](SECURITY.md) 的说明，用 GitHub **Security Advisory** 私密报告。

---

## 7. 应用内查看

运行 Olivia 后，可打开 `/safety` 查看本文件的精简版；危机时的求助入口是 `/care`。

---

## English summary

Olivia is an AI program, not a licensed therapist, doctor, lawyer or financial adviser. Her readings are for entertainment and reflection only, never a diagnosis, prediction or professional advice. A code-level crisis gate at `/api/chat` runs before vision, drawing, model calls and memory writes: it recognizes self-harm, threat, sexual assault, sexual harm and harm-to-others, stops the reading, keeps no transcript, and points to real-world help. It is regex-based, has known gaps (267 red-team cases, 70 documented gaps), and its optional model second check is off by default — **never rely on it as a safety net**. In danger, call your local emergency number (110/120 in China, 911 in the US/Canada), go to the nearest ER, contact someone you trust, or look up your local crisis hotline. Data stays local-first with no telemetry, crisis text is never stored, but normal readings go to your chosen model provider and LAN HTTP is plaintext: do not expose it to untrusted networks. Report safety concerns via GitHub issues; report vulnerabilities privately as described in `SECURITY.md`.

---

*本文内容采用 [CC BY-NC-SA 4.0](LICENSE-CONTENT) 许可；程序代码见 [LICENSE](LICENSE)。*
