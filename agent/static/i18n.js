/* SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
 * Copyright (c) 2026 Him-Wang
 * i18n.js — 轻量界面语言层（不引第三方库）。
 * 只翻译带固定文案的元素；用户内容、牌义、知识库正文不在此处理。
 */
(function () {
  var EN = {
    "Olivia · 奥莉薇娅": "Olivia",
    "你的私人塔罗咨询师": "Your private tarot counselor",
    "未配置": "Not configured",
    "未连接": "Disconnected",
    "设置": "Settings",
    "关怀": "Care",
    "会话簿": "Sessions",
    "分享图": "Export image",
    "知识库": "Notes",
    "记忆": "Memory",
    "牌义": "Card meanings",
    "新对话": "New chat",
    "发送": "Send",
    "停止": "Stop",
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
    "视觉识别插件（云端 VLM，选填）": "Vision bridge (optional)",
    "启用工具调用（检索/记忆/知识库/危机检查；抽牌是本地动作，不受此开关影响）":
      "Enable tools (search / memory / notes / crisis check; drawing is local)",
    "启用视觉识别": "Enable vision",
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
    "今日": "Today"
  };

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

  function apply(lang) {
    var en = String(lang || "zh").toLowerCase().indexOf("en") === 0;
    document.documentElement.lang = en ? "en" : "zh-CN";
    var nodes = document.querySelectorAll(
      "header button, .sheet h2, .actions button, .mem-tabs button, " +
      ".field > label, .sheet summary, .switch, .send, .title small, #backendChip"
    );
    for (var i = 0; i < nodes.length; i++) {
      var el = nodes[i];
      if (!el.dataset.zhText) el.dataset.zhText = (el.textContent || "").trim();
      var key = el.dataset.i18n || el.dataset.zhText;
      if (!key) continue;
      if (en && EN[key]) {
        setText(el, EN[key]);
        el.dataset.translated = "1";
      } else if (el.dataset.translated) {
        setText(el, key);
        delete el.dataset.translated;
      }
    }
    var input = document.getElementById("input");
    if (input) {
      if (!input.dataset.zhPlaceholder) input.dataset.zhPlaceholder = input.placeholder;
      input.placeholder = en
        ? "Tell me what is on your mind… (Enter to send, Shift+Enter for a new line)"
        : input.dataset.zhPlaceholder;
    }
    var apiKey = document.getElementById("apiKey");
    if (apiKey && en && apiKey.placeholder.indexOf("sk-") === 0) {
      apiKey.placeholder = "sk-… (leave blank to keep the saved key)";
    }
  }

  window.OliviaI18n = { apply: apply, dict: EN };
})();
