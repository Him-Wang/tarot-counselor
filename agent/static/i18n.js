/* SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
 * Copyright (c) 2026 Him-Wang
 * i18n.js — 轻量界面语言层（不引第三方库）。
 * 只翻译带固定文案的元素；用户内容、牌义、知识库正文不在此处理。
 */
(function () {
  var EN = {
    "Olivia · 奥莉薇娅": "Olivia",
    "奥莉薇娅 · 私人塔罗师": "Your private tarot reader",
    "你的私人塔罗咨询师": "Your private tarot counselor",
    "未配置": "Not configured",
    "未连接": "Disconnected",
    "设置": "Settings",
    "关怀": "Care",
    "主动关怀": "Check-ins",
    "打开「主动关怀」设置": "Open check-in settings",
    "定时问候、每天一张牌、盯事提醒；到点写好的消息进收件箱。关怀页只在触发危机时自动跳转，平时没有入口，也不会打断你。": "Scheduled hellos, a daily card, and watch tasks — messages land in the inbox. The care page only opens automatically when a crisis is detected; it has no entry point and will not interrupt you.",
    "会话簿": "Sessions",
    "分享图": "Export image",
    "知识库": "Notes",
    "记忆": "Memory",
    "牌义": "Card meanings",
    "新对话": "New chat",
    "＋ 新对话": "+ New chat",
    "发送": "Send",
    "停止": "Stop",
    "离线整理": "Offline digest",
    "预言模式 · 仅供娱乐": "Prophecy mode · just for fun",
    "未保存密钥": "No key saved",
    "已保存密钥 · 留空保存不会覆盖": "Key saved · leaving this blank keeps it",
    "清除已保存的密钥": "Clear the saved key",
    "神秘学模式": "Occult mode",
    "（通灵 / 召唤 / 仪式 · 可随时开关）": "(channeling / invocation / ritual)",
    "开启后可以正面聊通灵、召唤、仪式与神秘学体系，也可以用塔罗照见这类经验；不给可能伤到人的实操步骤，也不冒充通灵者。医疗、法律、财务与危机边界仍不放开。语境库在 agent/knowledge/occult/，随时可以往里放资料。": "Talk openly about channeling, invocation, ritual and esoteric systems — and read such experience through the cards. No step-by-step instructions that could hurt you, and no pretending to be a medium. Medical, legal, financial and crisis limits still hold. The context library lives in agent/knowledge/occult/ — drop your own material there any time.",
    "换行": "for a new line",
    "抽牌与牌义都在本地完成": "Drawing & meanings stay local",
    "重选": "Reshuffle",
    "接入设置": "Connection",
    "记忆管理": "Memory",
    "个人知识库 · 归档": "Personal notes",
    "主动关怀 · Always-on": "Always-on care",
    "后端预设": "Backend preset",
    "模型协议": "Protocol",
    "接口地址 base_url": "Base URL",
    "模型 model（可下拉选，也可手填）": "Model",
    "API key": "API key",
    "temperature": "temperature",
    "超时（秒）": "Timeout (s)",
    "每日 token 预算（0 = 不限制）": "Daily token budget (0 = off)",
    "单轮最大输出 token（0 = 后端默认）": "Max output tokens (0 = default)",
    "最多带多少条历史": "Max history messages",
    "历史字符上限": "Max history characters",
    "已加载的专业资料（knowledge/）": "Loaded knowledge docs",
    "成本与上下文（每日预算 / 历史裁剪）": "Cost & context",
    "数据备份与迁移（记忆 / 笔记 / 定时 / 盯事）": "Backup & migration",
    "👁 看图：本机 OCR + 云端视觉（选填）": "Image reading: local OCR + cloud vision (optional)",
  "启用云端视觉识别": "Enable cloud vision",
  "视觉 API 预设": "Vision API preset",
  "工具调用": "Tool calls",
  "语气系统": "Tone system",
  "默认开启 · 不可关闭": "Always on · locked",
  "检索 / 记忆 / 知识库 / 危机检查 · 抽牌始终在本地": "Search / memory / notes / crisis check · drawing stays local",
  "奥莉薇娅的女性塔罗师口吻 + 自然非暴力沟通": "Olivia's reader voice + non-violent phrasing",
  "接口地址": "Base URL",
  "视觉模型": "Vision model",
  "留空则不覆盖": "Leave blank to keep the saved key",
    "启用工具调用（检索/记忆/知识库/危机检查；抽牌是本地动作，不受此开关影响）":
      "Enable tools (search / memory / notes / crisis check; drawing is local)",
    "启用视觉识别": "Enable cloud vision",
    "启用长期记忆": "Enable long-term memory",
    "启用主动关怀（总开关）": "Enable always-on care",
    "模糊表达时再做一次安全分类（会多一次很小的模型调用）":
      "Second safety pass for ambiguous wording (extra tiny model call)",
    "测试连接": "Test",
    "取消": "Cancel",
    "保存": "Save",
    "完成": "Done",
    "关闭": "Close",
    "保存视觉设置": "Save vision settings",
    "导出全部数据": "Export all data",
    "导入备份": "Import backup",
    "＋ 添加线索": "+ Add a fact",
    "整理去重": "Deduplicate",
    "忘掉最近 3 条": "Forget last 3",
    "清空全部": "Clear all",
    "＋ 添加笔记": "+ Add note",
    "从记忆归档": "Archive from memory",
    "导出 Markdown": "Export Markdown",
    "＋ 新的一页": "+ New page",
    "＋ 添加盯事": "+ Add watcher",
    "立即检查": "Check now",
    "清空日志": "Clear log",
    "静默开始": "Quiet hours start",
    "静默结束": "Quiet hours end",
    "名称": "Name",
    "意图（关心什么）": "Intent",
    "频率": "Frequency",
    "标题": "Title",
    "标签": "Tags",
    "内容": "Content",
    "线索": "Facts",
    "抽牌历史": "Draw history",
    "画像": "Profile",
    "定时任务": "Scheduled care",
    "收件箱": "Inbox",
    "盯事": "Watchers",
    "已停止生成，保留上面这些。": "(Generation stopped; keeping what was written.)",
    "本轮 tokens": "Tokens this turn",
    "参考了资料：": "Used sources: ",
    "（没有收到回复，检查设置里的连接。）": "(No reply. Check the connection in Settings.)",
    "保存设置后即可开始对话": "Save settings to start",
    "今日": "Today",
    "附图": "Attach image",
    "功能": "Main"
  };

  /* 元素里可能夹着徽标/图标等子元素，取第一个有字的文本节点当 key，
     这样「关怀」+ 角标数字 不会被拼成查不到的「关怀2」。 */
  function keyOf(el) {
    if (el.dataset.i18n) return el.dataset.i18n;
    for (var i = 0; i < el.childNodes.length; i++) {
      var n = el.childNodes[i];
      if (n.nodeType === 3 && n.nodeValue && n.nodeValue.trim()) return n.nodeValue.trim();
    }
    return el.dataset.zhText || "";
  }

  function setText(el, text) {
    var node = null;
    for (var i = 0; i < el.childNodes.length; i++) {
      var n = el.childNodes[i];
      if (n.nodeType === 3 && n.nodeValue && n.nodeValue.trim()) { node = n; break; }
    }
    if (node) {
      var lead = node.nodeValue.match(/^\s*/)[0];
      node.nodeValue = lead + text;
    } else {
      el.textContent = text;
    }
  }

  /* 悬停提示（title）不在文本节点里，单独换一份 */
  var TITLES = {
    "usageChip": ["\u4eca\u65e5 token \u7528\u91cf / \u9884\u7b97", "Today\u2019s token usage / budget"],
    "offlineChip": ["\u6a21\u578b\u4e0d\u53ef\u7528\uff1a\u62bd\u724c\u4e0e\u79bb\u7ebf\u6574\u7406\u4ecd\u53ef\u6b63\u5e38\u4f7f\u7528",
                    "Model unavailable: drawing and the offline digest still work"],
    "prophecyChip": ["\u9884\u8a00\u6a21\u5f0f\u5df2\u5f00\u542f\uff1a\u89e3\u8bfb\u4ec5\u4f9b\u5a31\u4e50",
                     "Prophecy mode on: readings are just for fun"]
  };

  var SELECTOR = [
    "header button",
    ".sheet h2",
    ".actions button",
    ".mem-tabs button",
    ".field > label",
    ".sheet summary",
    ".switch",
    ".send",
    ".title small",
    "#backendChip",
    "#offlineChip",
    "#prophecyChip",
    ".composer .hint",
    ".pick-hint, .pick-reset",
    "[data-i18n]"
  ].join(", ");

  function apply(lang) {
    var en = String(lang || "zh").toLowerCase().indexOf("en") === 0;
    document.documentElement.lang = en ? "en" : "zh-CN";
    var nav = document.querySelector("nav.tools");
    if (nav) nav.setAttribute("aria-label", en ? "Main" : "功能");
    var nodes = document.querySelectorAll(SELECTOR);
    for (var i = 0; i < nodes.length; i++) {
      var el = nodes[i];
      if (!el.dataset.zhText) el.dataset.zhText = keyOf(el);
      var key = el.dataset.i18n || el.dataset.zhText;
      if (!key) continue;
      if (en && EN[key]) {
        setText(el, EN[key]);
        el.dataset.translated = "1";
      } else if (!en && el.dataset.translated) {
        setText(el, key);
        delete el.dataset.translated;
      }
    }
    for (var id in TITLES) {
      var el2 = document.getElementById(id);
      if (!el2) continue;
      if (!el2.dataset.zhTitle) el2.dataset.zhTitle = TITLES[id][0];
      el2.title = en ? TITLES[id][1] : el2.dataset.zhTitle;
    }
    var imgBtn = document.querySelector(".img-btn");
    if (imgBtn) {
      if (!imgBtn.dataset.zhTitle) imgBtn.dataset.zhTitle = imgBtn.title;
      imgBtn.title = en ? "Attach image (read by local OCR or your vision model)" : imgBtn.dataset.zhTitle;
    }
    var input = document.getElementById("input");
    if (input) {
      if (!input.dataset.zhPlaceholder) input.dataset.zhPlaceholder = input.placeholder;
      input.placeholder = en
        ? "Tell me what is on your mind…"
        : input.dataset.zhPlaceholder;
    }
    var apiKey = document.getElementById("apiKey");
    if (apiKey && en && apiKey.placeholder.indexOf("sk-") === 0) {
      apiKey.placeholder = "sk-… (leave blank to keep the saved key)";
    }
  }

  window.OliviaI18n = { apply: apply, dict: EN };
})();
