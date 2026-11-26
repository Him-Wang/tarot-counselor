const $ = id => document.getElementById(id);
const chat = $('chat'), input = $('input');

/* 界面语言：静态文案由 i18n.js 负责，这里是脚本自己拼出来的状态文字 */
const langEn = () => (localStorage.getItem('olivia.lang') || 'zh').toLowerCase().indexOf('en') === 0;
const uiText = (zh, en) => (langEn() ? en : zh);

/* ---------- 弹层可访问性（M-6）：焦点管理 / Esc 关闭 / Tab 陷阱 / 背景禁滚 ---------- */
let _lastFocused = null;
const FOCUSABLE = 'button:not([disabled]),[href],input:not([disabled]),select:not([disabled]),textarea:not([disabled]),summary,[tabindex]:not([tabindex="-1"])';
function openSheet(el){
  if(!el || el.classList.contains('show')) return;
  _lastFocused = document.activeElement;
  el.classList.add('show');
  document.body.style.overflow = 'hidden';           // 防止弹层后面页面滚动
  const first = el.querySelector(FOCUSABLE);
  if(first) setTimeout(()=>first.focus(), 0);
}
function closeSheet(el){
  if(!el) return;
  el.classList.remove('show');
  document.body.style.overflow = '';
  if(_lastFocused && typeof _lastFocused.focus === 'function') _lastFocused.focus();
  _lastFocused = null;
}
document.addEventListener('keydown', e => {
  const open = document.querySelector('.overlay.show');
  if(!open) return;
  if(e.key === 'Escape'){ closeSheet(open); return; }
  if(e.key === 'Tab'){
    const items = [...open.querySelectorAll(FOCUSABLE)].filter(n => n.offsetParent !== null);
    if(!items.length){ e.preventDefault(); return; }
    const first = items[0], last = items[items.length-1];
    if(e.shiftKey && document.activeElement === first){ e.preventDefault(); last.focus(); }
    else if(!e.shiftKey && document.activeElement === last){ e.preventDefault(); first.focus(); }
    else if(!open.contains(document.activeElement)){ e.preventDefault(); first.focus(); }
  }
});
// 点遮罩空白处关闭（点到 sheet 内部不关）
document.querySelectorAll('.overlay').forEach(ov => {
  ov.addEventListener('mousedown', e => { if(e.target === ov) closeSheet(ov); });
});

/* ---------- 后端连通性：把非 JSON 响应转成看得懂的提示 ---------- */
/* 直接用浏览器打开 index.html（file://）或页面不是由 python server.py 提供时，
   /api/* 会返回纯文本（如 "method not allowed"），r.json() 只会抛出
   SyntaxError，用户看到的是一堆英文。这里统一换成能照着做的中文提示。 */
const BACKEND_HINT = '请先运行 agent/start.bat（或 python server.py）启动服务，再从 http://127.0.0.1:8765 打开本页。';
function backendHint(status, body){
  if (location.protocol === 'file:') return '这个页面是直接打开的文件，没有连上 Olivia 本地服务。' + BACKEND_HINT;
  if (/method not allowed/i.test(body || '')) return '当前页面不是由 Olivia 服务提供的（静态服务器不接受接口请求）。' + BACKEND_HINT;
  if (status === 0) return '连不上 Olivia 本地服务。' + BACKEND_HINT;
  if (status === 404) return '这个地址上没有 Olivia 的接口。' + BACKEND_HINT;
  return 'Olivia 本地服务返回了异常响应（HTTP ' + status + '）。' + BACKEND_HINT;
}
const _rawFetch = window.fetch.bind(window);
const TOKEN_KEY = 'olivia.token';
function authToken(){ try { return localStorage.getItem(TOKEN_KEY) || ''; } catch(e){ return ''; } }
let pairingPromise = null;
async function pairOnce(){
  if(pairingPromise) return pairingPromise;
  pairingPromise = (async () => {
    const code = window.prompt('这台 Olivia 在局域网模式。请输入电脑端控制台显示的配对码（如 abcd-1234）：');
    if(!code) return false;
    const r = await _rawFetch('/api/pair', {method:'POST', headers:{'Content-Type':'application/json'},
      body: JSON.stringify({code: code})});
    let d = {};
    try { d = await r.json(); } catch(e){}
    if(r.ok && d.ok){
      try { localStorage.setItem(TOKEN_KEY, code.replace(/[^0-9a-zA-Z]/g,'')); } catch(e){}
      return true;
    }
    return false;
  })();
  try { return await pairingPromise; } finally { pairingPromise = null; }
}
window.fetch = async (input, init) => {
  const url = typeof input === 'string' ? input : (input && input.url) || '';
  init = init || {};
  try {
    const headers = new Headers(init.headers || {});
    const tk = authToken();
    if(tk && !headers.has('X-Olivia-Token')) headers.set('X-Olivia-Token', tk);
    init.headers = headers;
  } catch(e){}
  let res;
  try {
    res = await _rawFetch(input, init);
  } catch (err) {
    // file:// 直接打开、或服务没起，网络层就失败了
    if (url.indexOf('/api/') >= 0) throw new Error(backendHint(0, ''));
    throw err;
  }
  if (url.indexOf('/api/') < 0) return res;
  // 局域网未配对：输一次码，然后原样重放（body 是字符串，可重放）
  if (res.status === 401 && url.indexOf('/api/pair') < 0) {
    if (await pairOnce()) {
      try { res = await _rawFetch(input, init); } catch(e){}
    }
  }
  if (res && res.status === 401) {
    throw new Error('需要配对码：请在电脑端控制台查看后刷新页面。');
  }
  const ct = (res.headers.get('content-type') || '').toLowerCase();
  // JSON 接口和 /api/chat 的 SSE 流都是正常响应，原样放行
  if (ct.indexOf('application/json') >= 0 || ct.indexOf('text/event-stream') >= 0) return res;
  let body = '';
  try { body = (await res.clone().text()).trim().slice(0, 80); } catch (_) {}
  throw new Error(backendHint(res.status, body));
};
let history = [];
let streaming = false;
let pendingImages = [];  // data URLs queued for the next message
// 两阶段抽牌：服务端按 session_id 隔离「已抽出待解读」的牌。
// 新会话换一个 id，旧会话的牌不会被误用来解读。
const newSessionId = () => 's-' + Date.now().toString(36) + '-' + Math.random().toString(36).slice(2, 8);
let sessionId = newSessionId();

/* ---------- 会话簿：本机持久化 + hash 路由（Olivia 自己的记事簿） ----------
   和别家的「路由优先」不同，Olivia 是塔罗师手边的一摞册子：
   · 每本册子 = 一次对话，保存在浏览器 localStorage，只存文字/牌面，不存密钥；
   · 地址栏 #/chat/<id> 是这本册子的书脊，刷新、关页、分享地址都能翻回来；
   · 会话不上传服务器（服务端记忆是另一回事），完全本机私有。
--------------------------------------------------------------------------- */
const SHELF_KEY = 'olivia.shelf.v1';
const SHELF_ACTIVE_KEY = 'olivia.shelf.active.v1';
const ZH_GREETING = '你好，我是 Olivia（奥莉薇娅）。坐吧，慢慢说——今天是什么把你带到我这儿来的？';
const EN_GREETING = "Hi — I'm Olivia. Sit down, take your time. What brings you here today?";
const DEFAULT_GREETING = uiText(ZH_GREETING, EN_GREETING);

function loadShelf(){
  try { const a = JSON.parse(localStorage.getItem(SHELF_KEY) || '[]'); return Array.isArray(a) ? a : []; }
  catch(e){ return []; }
}
function saveShelf(shelf){
  try { localStorage.setItem(SHELF_KEY, JSON.stringify(shelf)); } catch(e){}
}
function shelfTitle(hist){
  const first = (hist || []).find(m => m && m.role === 'user');
  if(!first) return '未命名的一页';
  const t = String(first.content || '').replace(/\s+/g, ' ');
  return t.length > 18 ? t.slice(0, 18) + '…' : t;
}
function persistSession(){
  /* 空页不入册。连点「新对话」时每一页都是空的，若照存一遍，
     会话簿很快被「未命名的一页 · 0 条」占满，真正的对话就被挤到下面去了。 */
  const hasContent = history.some(m => m && String(m.content || '').trim());
  if(!hasContent){
    try { localStorage.setItem(SHELF_ACTIVE_KEY, sessionId); } catch(e){}
    return;
  }
  const shelf = loadShelf();
  let s = shelf.find(x => x.id === sessionId);
  if(!s){ s = { id: sessionId, title: '', history: [], updatedAt: Date.now() }; shelf.unshift(s); }
  s.history = history.slice(-40);
  s.title = shelfTitle(history);
  s.updatedAt = Date.now();
  saveShelf(shelf);
  try { localStorage.setItem(SHELF_ACTIVE_KEY, sessionId); } catch(e){}
}
function setRoute(id, push){
  const url = '#/chat/' + id;
  if(window.location.hash === url) return;
  try {
    if(push) window.history.pushState({ sid: id }, '', url);
    else window.history.replaceState({ sid: id }, '', url);
  } catch(e){ window.location.hash = url; }
}
function renderHistory(){
  chat.innerHTML = '';
  clearBoard();
  if(!history.length){
    const w = document.createElement('div'); w.className = 'msg assistant greeting';
    const inn = document.createElement('div');
    const who = document.createElement('div'); who.className = 'who'; who.textContent = 'Olivia';
    const bub = document.createElement('div'); bub.className = 'bub'; bub.textContent = DEFAULT_GREETING;
    inn.appendChild(who); inn.appendChild(bub); w.appendChild(inn); chat.appendChild(w);
    return;
  }
  history.forEach(m => {
    const { bub, inner } = addMsg(m.role || 'assistant', m.content || '');
    if(m.cards){ lastCards = m.cards; renderCards(inner, bub, m.cards); }
    if(m.safety) bub.classList.add('safety-line');
  });
  // 回到旧会话：牌桌的问句取这副牌之后的第一条用户消息
  let ci = -1;
  history.forEach((m, i) => { if(m.cards) ci = i; });
  if(ci >= 0){
    const q = history.slice(ci + 1).find(x => x.role === 'user' && x.content);
    if(q) updateBoardQuestion(q.content);
  }
  chat.scrollTop = chat.scrollHeight;
}
function openSession(id, push){
  const shelf = loadShelf();
  const s = shelf.find(x => x.id === id);
  persistSession();                       // 先把当前这本合上
  sessionId = id;
  history = s ? (s.history || []).slice() : [];
  pendingImages = []; renderImages();
  renderHistory();
  setRoute(id, push);
  try { localStorage.setItem(SHELF_ACTIVE_KEY, id); } catch(e){}
}
/* 固定的一两句话也按字落出来，短句才看得出「她正在打」 */
function typeGreeting(bub, text, startDelay){
  const reduce = window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  bub.textContent = '';
  bub.classList.add('typewriting');
  requestAnimationFrame(() => {
  let i = 0;
  const step = () => {
    if(i >= text.length){ bub.classList.remove('typewriting'); return; }
    const ch = text[i++];
    bub.textContent += ch;
    chat.scrollTop = chat.scrollHeight;
    const base = reduce ? 10 : 46;
    const pause = reduce ? 0
      : /[。！？!?]/.test(ch) ? 300 : /[，、；：,;:…—]/.test(ch) ? 180 : 0;
    setTimeout(step, base + pause + Math.random() * 16);
  };
  setTimeout(step, startDelay || 160);
  });
}

function newSession(){
  // 上一轮如果还停在流式/选牌里，切新页时把它收掉，否则输入框会一直是禁用的
  if(streaming){
    stopped = true;
    try { if(abortCtl) abortCtl.abort(); } catch(e){}
    abortCtl = null; streaming = false;
    $('sendBtn').disabled = false;
    $('stopBtn').hidden = true;
  }
  persistSession();
  openSession(newSessionId(), true);
  // 开场白不再「一次印好」：直接借对话里那条问候气泡，按字落出来。
  const greetBub = chat.querySelector('.msg.greeting .bub');
  if(greetBub) typeGreeting(greetBub, uiText('新的一页。这次，你想从哪里说起？', 'A new page. Where would you like to start?'), 220);
  else {
    const { bub } = addMsg('assistant', '');
    typeGreeting(bub, uiText('新的一页。这次，你想从哪里说起？', 'A new page. Where would you like to start?'), 220);
  }
}
/* 一页里有没有真的聊过东西。历史遗留的「未命名的一页 · 0 条」是早期
   persistSession() 不看内容就写盘留下的，这里按内容判定，顺手清掉。 */
function shelfHasContent(s){
  const h = (s && s.history) || [];
  return h.some(m => m && (String(m.content || '').trim() || m.image));
}

function renderShelf(){
  const all = loadShelf();
  // 当前正在看的那一页即使还是空的也留着，否则一打开会话簿就把自己删了
  const kept = all.filter(s => s.id === sessionId || shelfHasContent(s));
  if(kept.length !== all.length) saveShelf(kept);
  const shelf = kept.slice().sort((a, b) => (b.updatedAt || 0) - (a.updatedAt || 0));
  const list = $('shelfList');
  list.innerHTML = '';
  if(!shelf.length){ list.textContent = '（还没有保存的会话，聊几句就有了。）'; return; }
  shelf.forEach(s => {
    const el = document.createElement('div');
    el.className = 'shelf-item' + (s.id === sessionId ? ' active' : '');
    const g = document.createElement('div'); g.className = 'grow';
    const st = document.createElement('div'); st.className = 'st'; st.textContent = s.title || '未命名的一页';
    const sm = document.createElement('div'); sm.className = 'sm';
    const d = new Date(s.updatedAt || Date.now());
    sm.textContent = (s.history || []).length + ' 条 · ' + d.toLocaleString('zh-CN');
    g.appendChild(st); g.appendChild(sm); el.appendChild(g);
    const del = document.createElement('button');
    del.className = 'del'; del.textContent = '×'; del.title = '删除这一页';
    del.onclick = (ev) => {
      ev.stopPropagation();
      saveShelf(loadShelf().filter(x => x.id !== s.id));
      renderShelf();
      if(s.id === sessionId) newSession();
    };
    el.appendChild(del);
    el.onclick = () => { closeSheet($('shelfOverlay')); openSession(s.id, true); };
    list.appendChild(el);
  });
}

const PRESET_NOTE = {
  'deepseek-flash': 'DeepSeek V4.1-Flash：快、便宜，默认带思考。填自己的 API key（platform.deepseek.com）。',
  'deepseek-v4-pro': 'DeepSeek V4-Pro：更强，适合复杂问题。填自己的 API key。',
  'deepseek-chat': '旧版 deepseek-chat，兼容老配置。填自己的 API key。',
  ollama: '先运行 ollama serve 并拉好模型；API key 留空，模型名填本地已有的（如 qwen2.5:7b）。',
  anthropic: 'Anthropic Claude 原生 Messages API：填 Anthropic key，协议选 Anthropic。',
  gemini: 'Google Gemini 原生 generateContent：填 Google AI key，协议选 Gemini。',
  custom: '任意 OpenAI 兼容端点：/chat/completions 接口。自行填写全部字段。'
};
// [base_url, model, protocol]
const PRESET_MAP = {
  'deepseek-flash': ['https://api.deepseek.com/v1','deepseek-flash','auto'],
  'deepseek-v4-pro': ['https://api.deepseek.com/v1','deepseek-v4-pro','auto'],
  'deepseek-chat': ['https://api.deepseek.com/v1','deepseek-chat','auto'],
  ollama: ['http://127.0.0.1:11434/v1','qwen2.5:7b','auto'],
  anthropic: ['https://api.anthropic.com/v1','claude-sonnet-4-5-20250929','anthropic'],
  gemini: ['https://generativelanguage.googleapis.com/v1beta','gemini-2.5-flash','gemini'],
  custom: ['','','auto']
};

function addMsg(role, text){
  const wrap = document.createElement('div');
  wrap.className = 'msg ' + (role === 'user' ? 'user' : 'assistant');
  const inner = document.createElement('div');
  const who = document.createElement('div'); who.className='who'; who.textContent = role==='user'?'你':'Olivia';
  const bub = document.createElement('div'); bub.className='bub'; bub.textContent = text;
  inner.appendChild(who); inner.appendChild(bub); wrap.appendChild(inner); chat.appendChild(wrap);
  chat.scrollTop = chat.scrollHeight;
  return {bub, inner};
}

function escHtml(s){
  return String(s==null?'':s).replace(/[&<>"']/g, c => (
    {'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]
  ));
}
function escAttr(s){ return escHtml(s); }

/* ---------- 牌面放大：78 张都在本地，没有理由看不了大图 ---------- */
function openLightbox(c){
  const lb = $('lightbox');
  if(!lb || !c) return;
  const safeImg = typeof c.image === 'string' && /^cards\/[A-Za-z0-9_\-\.]+\.(jpe?g|png)$/i.test(c.image)
    ? c.image : '';
  if(!safeImg) return;
  $('lbImg').src = safeImg;
  $('lbImg').alt = c.name || '';
  $('lbImg').className = c.orientation === '逆位' ? 'rev' : '';
  $('lbName').textContent = (c.name || '') + (c.orientation ? '　' + c.orientation : '');
  $('lbPos').textContent = [c.position, c.position_meaning,
    c.reason ? '补牌理由：' + c.reason : ''].filter(Boolean).join(' · ');
  lb.hidden = false;
  $('lbClose').focus();
}
function closeLightbox(){
  const lb = $('lightbox');
  if(!lb || lb.hidden) return;
  lb.hidden = true;
  $('lbImg').removeAttribute('src');
}

/* ---------- 朗读：把 Olivia 的话念出来 ---------- */
let speakingBtn = null;
let nativeTimer = null;
function plainForSpeech(text){
  return String(text || '')
    .replace(/```[\s\S]*?```/g, '')
    .replace(/!\[[^\]]*\]\([^)]*\)/g, '')
    .replace(/\[([^\]]*)\]\([^)]*\)/g, '$1')
    .replace(/[*_`#>~|]/g, '')
    .replace(/[\u{1F300}-\u{1FAFF}\u{2600}-\u{27BF}\u{FE0F}\u{2B00}-\u{2BFF}]/gu, '')
    .replace(/\s+/g, ' ')
    .trim();
}
// 安卓 WebView 没有 Web Speech API，App 里自带一个 TTS 桥（window.OliviaNative）
function hasWebSpeech(){ return typeof window.speechSynthesis !== 'undefined'; }
function hasNativeSpeech(){ return !!(window.OliviaNative && window.OliviaNative.speak); }
function canSpeak(){ return hasWebSpeech() || hasNativeSpeech(); }
function stopSpeech(){
  try { if(hasWebSpeech()) window.speechSynthesis.cancel(); } catch(e) {}
  try { if(hasNativeSpeech() && window.OliviaNative.stop) window.OliviaNative.stop(); } catch(e) {}
  if(nativeTimer){ clearTimeout(nativeTimer); nativeTimer = null; }
  if(speakingBtn){ speakingBtn.classList.remove('on'); speakingBtn.textContent = '朗读'; speakingBtn = null; }
}
function speakText(text, btn){
  if(!canSpeak()){ btn.textContent = '这台设备没有语音引擎'; return; }
  if(speakingBtn === btn){ stopSpeech(); return; }
  stopSpeech();
  const body = plainForSpeech(text);
  if(!body) return;
  speakingBtn = btn;
  btn.classList.add('on'); btn.textContent = '停止朗读';
  if(!hasWebSpeech()){
    // 原生 TTS：念完由 App 回调 stopSpeech() 复位按钮；
    // 有些引擎（或离线语音包缺失时）不回调，这里按字数估个时长兜底复位
    try {
      window.OliviaNative.speak(body);
      const ms = Math.min(600000, 1200 + body.length * 240);
      nativeTimer = setTimeout(() => { nativeTimer = null; stopSpeech(); }, ms);
    }
    catch(e){ stopSpeech(); }
    return;
  }
  // 按句切分排队：长回复可以中途停，也不会被浏览器截断
  const chunks = body.match(/[^。！？!?；;\n]{1,90}[。！？!?；;]?/g) || [body];
  let i = 0;
  const next = () => {
    if(speakingBtn !== btn) return;
    if(i >= chunks.length){ stopSpeech(); return; }
    const u = new SpeechSynthesisUtterance(chunks[i++]);
    u.lang = 'zh-CN'; u.rate = 1.02; u.pitch = 1.0;
    u.onend = next;
    u.onerror = () => { if(speakingBtn === btn) stopSpeech(); };
    window.speechSynthesis.speak(u);
  };
  next();
}
// 原生 TTS 念完时由 App 调用
window.__ttsDone = function(){ if(speakingBtn) stopSpeech(); };

/* ---------- 把一次解读存成图片：牌面 + Olivia 的话 ---------- */
function loadCanvasImage(src){
  return new Promise(res => {
    const im = new Image();
    im.onload = () => res(im);
    im.onerror = () => res(null);
    im.src = src;
  });
}
function cleanForCanvas(text){
  return String(text || '')
    .replace(/```[\s\S]*?```/g, '')
    .replace(/!\[[^\]]*\]\([^)]*\)/g, '')
    .replace(/\[([^\]]*)\]\([^)]*\)/g, '$1')
    .replace(/^[ \t]*#{1,6}[ \t]*/gm, '')
    .replace(/[*_`~]/g, '')
    .replace(/[\u{1F300}-\u{1FAFF}\u{2600}-\u{27BF}\u{FE0F}\u{2B00}-\u{2BFF}]/gu, '')
    .replace(/[ \t]+/g, ' ')
    .replace(/\n{3,}/g, '\n\n')
    .trim();
}
function wrapCanvasLines(ctx, text, maxW){
  const lines = [];
  let cur = '';
  String(text || '').split('\n').forEach(para => {
    cur = '';
    for(const ch of para){
      const t = cur + ch;
      if(ctx.measureText(t).width > maxW && cur){ lines.push(cur); cur = ch; }
      else cur = t;
    }
    lines.push(cur);
  });
  return lines;
}
async function exportReading(inner, text){
  const data = inner && inner._cards;
  const cards = (data && data.items) || [];
  const extras = (data && data.extras) || [];
  const W = 1080, PAD = 72, MAXW = W - PAD * 2;
  const c = document.createElement('canvas');
  const ctx = c.getContext('2d');
  const FONT = '"PingFang SC","Microsoft YaHei","Noto Sans SC",system-ui,sans-serif';
  const fTitle = '700 46px ' + FONT;
  const fSub = '400 26px ' + FONT;
  const fBody = '400 31px ' + FONT;
  const fName = '500 23px ' + FONT;

  ctx.font = fBody;
  const lines = wrapCanvasLines(ctx, cleanForCanvas(text), MAXW);
  const gap = 20;
  const want = Math.min(Math.max(cards.length, 1), 3);
  const cw = Math.min(320, Math.floor((MAXW - gap * (want - 1)) / want));
  const chh = Math.round(cw * 1.7);
  const perRow = Math.max(1, Math.floor((MAXW + gap) / (cw + gap)));
  const rows = Math.ceil(cards.length / perRow);
  const extrasRows = extras.length ? 1 : 0;

  let H = PAD + 62 + 44 + (cards.length ? 56 + rows * (chh + 62) : 0) +
    (extras.length ? 46 + extrasRows * (chh + 62) : 0) + 60 + lines.length * 48 + PAD;
  c.width = W; c.height = Math.max(H, 560);

  // 底色与网页一致：浅灰蓝 + 一点紫
  const g = ctx.createLinearGradient(0, 0, W, c.height);
  g.addColorStop(0, '#f3f5fa');
  g.addColorStop(1, '#e6e9f3');
  ctx.fillStyle = g; ctx.fillRect(0, 0, W, c.height);
  ctx.fillStyle = 'rgba(154,134,194,.10)';
  ctx.fillRect(0, 0, W, 8);

  let y = PAD + 46;
  ctx.fillStyle = '#42425a'; ctx.font = fTitle;
  ctx.fillText('Olivia · 塔罗解读', PAD, y);
  y += 40;
  ctx.fillStyle = '#6b598f'; ctx.font = fSub;
  const now = new Date();
  ctx.fillText(now.getFullYear() + ' 年 ' + (now.getMonth() + 1) + ' 月 ' + now.getDate() +
    ' 日 ' + (cards.length ? cards.length + ' 张牌' : ''), PAD, y);

  if(cards.length){
    y += 58;
    ctx.fillStyle = '#42425a'; ctx.font = '700 30px ' + FONT;
    ctx.fillText((data.spread || '抽牌') + (data.spread_desc ? ' · ' + data.spread_desc : ''), PAD, y);
    y += 26;
    for(let i = 0; i < cards.length; i++){
      const row = Math.floor(i / perRow), col = i % perRow;
      const x = PAD + col * (cw + gap);
      const yy = y + row * (chh + 62);
      const card = cards[i];
      const safeImg = typeof card.image === 'string' &&
        /^cards\/[A-Za-z0-9_\-\.]+\.(jpe?g|png)$/i.test(card.image) ? card.image : '';
      const im = safeImg ? await loadCanvasImage(safeImg) : null;
      ctx.save();
      ctx.beginPath();
      const r = 14;
      ctx.moveTo(x + r, yy); ctx.lineTo(x + cw - r, yy);
      ctx.quadraticCurveTo(x + cw, yy, x + cw, yy + r);
      ctx.lineTo(x + cw, yy + chh - r);
      ctx.quadraticCurveTo(x + cw, yy + chh, x + cw - r, yy + chh);
      ctx.lineTo(x + r, yy + chh);
      ctx.quadraticCurveTo(x, yy + chh, x, yy + chh - r);
      ctx.lineTo(x, yy + r); ctx.quadraticCurveTo(x, yy, x + r, yy);
      ctx.closePath(); ctx.clip();
      ctx.fillStyle = '#fff'; ctx.fillRect(x, yy, cw, chh);
      if(im){
        if(card.orientation === '逆位'){
          ctx.translate(x + cw / 2, yy + chh / 2); ctx.rotate(Math.PI); ctx.translate(-(x + cw / 2), -(yy + chh / 2));
        }
        ctx.drawImage(im, x, yy, cw, chh);
      }
      ctx.restore();
      ctx.fillStyle = '#42425a'; ctx.font = fName;
      const label = (i + 1) + '. ' + (card.position || '') + '　' + (card.name || '') +
        (card.orientation ? '（' + card.orientation + '）' : '');
      ctx.fillText(label, x, yy + chh + 34);
    }
    y += rows * (chh + 62);
  }

  if(extras.length){
    y += 10;
    ctx.fillStyle = '#6b598f'; ctx.font = '700 26px ' + FONT;
    ctx.fillText('补牌 · ' + extras.map(e => (e.name || '') + (e.orientation ? '（' + e.orientation + '）' : '')).join('、'), PAD, y);
    y += 12;
    for(let i = 0; i < extras.length && i < perRow; i++){
      const card = extras[i];
      const x = PAD + i * (cw + gap), yy = y + 10;
      const safeImg = typeof card.image === 'string' &&
        /^cards\/[A-Za-z0-9_\-\.]+\.(jpe?g|png)$/i.test(card.image) ? card.image : '';
      const im = safeImg ? await loadCanvasImage(safeImg) : null;
      if(im){ ctx.save(); ctx.beginPath(); ctx.rect(x, yy, cw, chh); ctx.clip();
        if(card.orientation === '逆位'){
          ctx.translate(x + cw / 2, yy + chh / 2); ctx.rotate(Math.PI); ctx.translate(-(x + cw / 2), -(yy + chh / 2));
        }
        ctx.drawImage(im, x, yy, cw, chh); ctx.restore(); }
      if(card.reason){
        ctx.fillStyle = '#67677f'; ctx.font = '400 22px ' + FONT;
        ctx.fillText(card.reason.slice(0, 18), x, yy + chh + 30);
      }
    }
    y += extrasRows * (chh + 62);
  }

  y += 34;
  ctx.fillStyle = '#6b598f'; ctx.font = '700 26px ' + FONT;
  ctx.fillText('Olivia 说', PAD, y);
  y += 20;
  ctx.fillStyle = '#42425a'; ctx.font = fBody;
  lines.forEach(line => { y += 46; ctx.fillText(line, PAD, y); });

  const a = document.createElement('a');
  a.download = 'olivia-reading-' + now.toISOString().slice(0, 19).replace(/[:T]/g, '-') + '.png';
  a.href = c.toDataURL('image/png');
  a.click();
}

/* 选阵轮：悬浮详情窗（鼠标悬停 / 键盘聚焦显示，ⓘ 可点开固定）。 */
let spreadTip = null, spreadTipTimer = null, spreadTipPinned = false;

function buildSpreadTipHtml(item){
  const positions = item.positions || [];
  let html = '<div class="spread-tip-h"><b>' + escHtml(item.name) + '</b>' +
    '<span class="spread-tip-n">' + escHtml(item.count) + ' 张牌</span></div>';
  if(item.desc) html += '<p class="spread-tip-desc">' + escHtml(item.desc) + '</p>';
  if(positions.length){
    html += '<div class="spread-tip-label">牌位说明</div><ol class="spread-tip-pos">' +
      positions.map(p => '<li><b>' + escHtml(p.name) + '</b> — ' + escHtml(p.meaning) + '</li>').join('') +
      '</ol>';
  }
  return html;
}

function showSpreadTip(item, anchor){
  if(!spreadTip){
    spreadTip = document.createElement('div');
    spreadTip.className = 'spread-tip';
    spreadTip.setAttribute('role', 'tooltip');
    spreadTip.addEventListener('mouseenter', () => clearTimeout(spreadTipTimer));
    spreadTip.addEventListener('mouseleave', () => { if(!spreadTipPinned) hideSpreadTip(); });
    document.body.appendChild(spreadTip);
  }
  clearTimeout(spreadTipTimer);
  spreadTip.innerHTML = buildSpreadTipHtml(item);
  spreadTip.style.display = 'block';
  spreadTip.style.visibility = 'hidden';
  const r = anchor.getBoundingClientRect();
  const tw = spreadTip.offsetWidth, th = spreadTip.offsetHeight;
  let left = r.right + 12;
  if(left + tw > window.innerWidth - 12) left = r.left - tw - 12;
  if(left < 12) left = 12;
  let top = r.top;
  if(top + th > window.innerHeight - 12) top = window.innerHeight - th - 12;
  if(top < 12) top = 12;
  spreadTip.style.left = left + 'px';
  spreadTip.style.top = top + 'px';
  spreadTip.style.visibility = 'visible';
}
function hideSpreadTip(){
  if(spreadTip) spreadTip.style.display = 'none';
  spreadTipPinned = false;
}

/* 选阵轮：把服务端发来的牌阵数据渲染成可点击按钮。 */
const RECOMMENDED_SPREADS = ['三张', '单张', '凯尔特十字', '关系', '二选一'];
function _spreadChoiceNode(item){
  const wrap = document.createElement('div'); wrap.className = 'spread-choice';
  const btn = document.createElement('button');
  btn.type = 'button'; btn.className = 'spread-choice-btn';
  btn.innerHTML = '<span class="spread-choice-name">' + escHtml(item.name) +
    '</span><span class="spread-choice-count">' + escHtml(item.count) + ' 张</span>';
  btn.onclick = () => {
    if(streaming) return;
    hideSpreadTip();
    // 点按钮等价于用户说出牌阵名；走正常发消息流程。
    input.value = '用' + item.name + '牌阵抽牌';
    send();
  };
  const info = document.createElement('button');
  info.type = 'button'; info.className = 'spread-info-btn';
  info.textContent = 'ⓘ'; info.setAttribute('aria-label', '查看' + item.name + '详情');
  info.onclick = (e) => {
    e.stopPropagation();
    spreadTipPinned = !spreadTipPinned;
    if(spreadTipPinned) showSpreadTip(item, wrap);
    else hideSpreadTip();
  };
  wrap.appendChild(btn); wrap.appendChild(info);
  wrap.addEventListener('mouseenter', () => showSpreadTip(item, wrap));
  wrap.addEventListener('mouseleave', () => { if(!spreadTipPinned) spreadTipTimer = setTimeout(hideSpreadTip, 120); });
  wrap.addEventListener('focusin', () => showSpreadTip(item, wrap));
  wrap.addEventListener('focusout', () => { if(!spreadTipPinned) hideSpreadTip(); });
  return wrap;
}
function renderSpreadChoices(bub, data){
  if(!data || !data.groups || !data.groups.length) return;
  const all = [];
  (data.groups || []).forEach(g => (g.items || []).forEach(it => all.push(it)));
  const byName = {};
  all.forEach(it => { byName[it.name] = it; });

  // 39 个牌阵一次全铺会造成选择过载：先给 5 个推荐，其余折叠。
  const recRow = document.createElement('div'); recRow.className = 'spread-choice-row';
  RECOMMENDED_SPREADS.forEach(name => {
    if(byName[name]) recRow.appendChild(_spreadChoiceNode(byName[name]));
  });
  if(recRow.children.length){
    const recTitle = document.createElement('div');
    recTitle.className = 'spread-group-title';
    recTitle.textContent = '【推荐】';
    bub.appendChild(recTitle);
    bub.appendChild(recRow);
  }

  const more = document.createElement('details');
  more.className = 'spread-more';
  const summary = document.createElement('summary');
  const restCount = Math.max(0, all.length - recRow.children.length);
  summary.textContent = '更多牌阵（' + restCount + '）';
  more.appendChild(summary);
  (data.groups || []).forEach(group => {
    const items = (group.items || []).filter(it => RECOMMENDED_SPREADS.indexOf(it.name) < 0);
    if(!items.length) return;
    const title = document.createElement('div');
    title.className = 'spread-group-title';
    title.textContent = '【' + group.category + '】';
    more.appendChild(title);
    const row = document.createElement('div'); row.className = 'spread-choice-row';
    items.forEach(item => row.appendChild(_spreadChoiceNode(item)));
    more.appendChild(row);
  });
  bub.appendChild(more);

  if(data.auto){
    const auto = document.createElement('button');
    auto.type = 'button'; auto.className = 'spread-choice-btn spread-choice-auto';
    auto.textContent = '✨ 你帮我选（默认' + data.auto + '）';
    auto.onclick = () => {
      if(streaming) return;
      hideSpreadTip();
      input.value = '你帮我选牌阵';
      send();
    };
    bub.appendChild(auto);
  }
}
document.addEventListener('keydown', e => { if(e.key === 'Escape') hideSpreadTip(); });
window.addEventListener('resize', hideSpreadTip);
$('chat').addEventListener('scroll', hideSpreadTip, {passive:true});

/* 一张牌的 DOM：牌面、序号、悬停浮窗（牌位名）、看大图。
   主牌阵与补牌共用，保证补牌也是同一个样式和同一套交互。 */
function mkCardSlot(c, num, rot){
  const slot = document.createElement('div');
  slot.className = 'draw-slot' + (rot ? ' cross' : '');
  slot.tabIndex = 0;                        // 键盘 Tab 聚焦也能看到牌位名
  // M-5: expose the hidden tooltip's content to assistive technology
  slot.setAttribute('role', 'img');
  slot.setAttribute('aria-label', '第' + num + '张 ' + (c.position || '') + '：' +
    (c.name || '') + ' ' + (c.orientation || ''));
  // m-9: only allow the backend's fixed cards/*.jpeg image paths
  const safeImg = typeof c.image === 'string' && /^cards\/[A-Za-z0-9_\-\.]+\.(jpe?g|png)$/i.test(c.image)
    ? c.image : '';
  const img = safeImg
    ? '<img src="' + escAttr(safeImg) + '" alt="' + escAttr(c.name || '') + '" loading="lazy">'
    : '';
  const rev = c.orientation === '逆位' ? ' rev' : '';
  // 牌面上只留序号；牌位名要鼠标移上去才显示，移开就消失
  slot.innerHTML =
    '<div class="facebox">' +
      '<div class="face' + rev + (rot ? ' rot' : '') + '">' + img + '</div>' +
      '<span class="num">' + num + '</span>' +
      '<div class="poslay"><b>' + escHtml(c.position || '') + '</b>' +
        (c.position_meaning ? '<span>' + escHtml(c.position_meaning) + '</span>' : '') +
        (rot ? '<span class="cd">' + escHtml(c.name || '') +
               (c.orientation ? '　' + escHtml(c.orientation) : '') + '</span>' : '') +
        (safeImg ? '<button class="zoom-btn" type="button">看大图</button>' : '') +
      '</div>' +
    '</div>' +
    '<div class="tip">' +
      (rot
        ? '<span class="nm">' + escHtml(c.name || '') + '</span><span class="or' + (rev ? ' rev' : '') + '">　' + escHtml(c.orientation || '') + '</span>'
        : '<span class="nm">' + escHtml(c.name || '') + '</span>' +
          (c.orientation ? '<span class="or' + (rev ? ' rev' : '') + '">' + escHtml(c.orientation) + '</span>' : '')) +
    '</div>';
  // 触屏没有悬停：点一下显示牌位名，再点收起
  slot.addEventListener('click', function(ev){
    if(ev.target && ev.target.classList && ev.target.classList.contains('zoom-btn')) return;
    slot.classList.toggle('open');
  });
  const zoom = slot.querySelector('.zoom-btn');
  if(zoom) zoom.addEventListener('click', function(ev){
    ev.stopPropagation(); openLightbox(c);
  });
  if(safeImg) slot.addEventListener('dblclick', function(){ openLightbox(c); });
  return slot;
}

function renderCards(inner, bub, data, opts){
  const items = (data && data.items) || [];
  if(!items.length) return;
  inner._cards = data;                      // 存下来给「存这次解读」用
  const extras = (data && data.extras) || [];
  const lay = (data && data.layout) || {cols: items.length, rows: 1,
    cells: items.map((_, i) => [i + 1, 1])};
  const cols = Math.max(1, lay.cols|0), rows = Math.max(1, lay.rows|0);
  const cells = Array.isArray(lay.cells) ? lay.cells : [];

  const wrap = document.createElement('div');
  wrap.className = 'draw-wrap';

  const head = document.createElement('div');
  head.className = 'draw-head';
  head.innerHTML = '<b>' + escHtml(data.spread || '抽牌') + '</b>　' + items.length + ' 张' +
    (data.manual ? ' · 手选' : '') +
    (data.spread_desc ? '　<span>' + escHtml(data.spread_desc) + '</span>' : '');
  wrap.appendChild(head);

  const scroll = document.createElement('div');
  scroll.className = 'draw-scroll';
  const board = document.createElement('div');
  board.className = 'draw-board' + (cols >= 6 ? ' wide' : '');
  board.style.gridTemplateColumns = 'repeat(' + cols + ', var(--cw))';
  if (lay.gap && lay.gap.length === 2) {
    board.style.setProperty('--gy', (Number(lay.gap[0]) || 0) + 'px');
    board.style.setProperty('--gx', (Number(lay.gap[1]) || 0) + 'px');
  }
  scroll.appendChild(board);
  wrap.appendChild(scroll);

  items.forEach((c, i) => {
    const cell = cells[i] || [i + 1, 1];
    const rot = Number(cell[2]) === 90;
    const slot = mkCardSlot(c, i + 1, rot);
    const col = Math.max(1, Math.min(cols, Number(cell[0]) || 1));
    const row = Math.max(1, Math.min(rows, Number(cell[1]) || 1));
    slot.style.gridColumn = String(col);
    slot.style.gridRow = String(row);
    // 右半边的牌，浮窗朝左开，免得顶出容器
    if (col > cols / 2) slot.classList.add('tip-l');
    if (rot) {
      // 横躺的牌（凯尔特十字的「阻碍」）：宽高对调、压在中心那张上
      slot.style.zIndex = '6';
    }
    board.appendChild(slot);
  });

  // 牌位表：默认收起，想一次看全所有位置在问什么时再展开
  const legend = document.createElement('details');
  legend.className = 'draw-legend';
  const sum = document.createElement('summary');
  sum.textContent = '牌位表（点开看 ' + items.length + ' 个位置各自在问什么）';
  legend.appendChild(sum);
  items.forEach((c, i) => {
    const row = document.createElement('div');
    row.className = 'lg';
    row.innerHTML = '<i>' + (i + 1) + '</i><span><b>' + escHtml(c.position || '') + '</b>' +
      (c.position_meaning ? '　' + escHtml(c.position_meaning) : '') +
      '　→ ' + escHtml(c.name || '') +
      (c.orientation ? '（' + escHtml(c.orientation) + '）' : '') +
      '</span>';
    legend.appendChild(row);
  });
  wrap.appendChild(legend);

  // 补牌：来访者主动补的那几张，单独一行，附上当时写的理由
  if(extras.length){
    const eh = document.createElement('div');
    eh.className = 'extra-head';
    eh.textContent = '补牌 · 后来补上的视角';
    wrap.appendChild(eh);
    const box = document.createElement('div');
    box.className = 'draw-extras';
    extras.forEach((c, i) => box.appendChild(mkCardSlot(c, items.length + i + 1, false)));
    wrap.appendChild(box);
    const reasons = extras.map(e => e.reason).filter(Boolean);
    if(reasons.length){
      const rr = document.createElement('div');
      rr.className = 'extra-reason';
      rr.textContent = '补牌理由：' + reasons.join('；');
      wrap.appendChild(rr);
    }
  }

  // 只有解读过的牌才给「补一张」：抽牌轮还没问问题，补牌没有落点
  if(opts && opts.canExtra){
    const addRow = document.createElement('div');
    addRow.className = 'extra-add';
    const ri = document.createElement('input');
    ri.type = 'text';
    ri.placeholder = '为什么想补一张？（可不填）';
    ri.setAttribute('aria-label', '补牌理由');
    const eb = document.createElement('button');
    eb.type = 'button';
    eb.textContent = '补一张';
    eb.onclick = () => {
      const r = ri.value.trim();
      ri.value = '';
      send('补一张牌' + (r ? '：' + r : ''));
    };
    addRow.appendChild(eb); addRow.appendChild(ri);
    wrap.appendChild(addRow);
  }

  inner.insertBefore(wrap, bub);
  renderBoard(data);
}

/* ---------- 手动选牌舞台 ----------
   牌阵定下之后：扇形牌堆围在牌位上方，拖动翻看，轻点一张抽进下一个牌位。
   挑满张数后提交 /api/pick，牌面按挑选顺序落位，再回到「提问 → 解读」。 */
function renderPickStage(inner, bub, data){
  return new Promise(resolve => {
    const positions = (data && data.positions) || [];
    const need = positions.length || 1;
    const spread = (data && data.spread) || '三张';
    const picked = [];
    let pos = 0, vis = 21, suppressUntil = 0, submitting = false, drag = null;

    // 新的一轮开始：先把上一副牌从工作台撤下，避免两副牌同时出现。
    clearBoard();

    const wrap = document.createElement('div');
    wrap.className = 'pick-wrap';
    wrap.innerHTML =
      '<div class="draw-head"><b>' + escHtml(spread) + '</b>　' + need + ' 张' +
        (data.spread_desc ? '　<span>' + escHtml(data.spread_desc) + '</span>' : '') + '</div>' +
      '<div class="pick-slots" role="list" aria-label="' + escHtml(spread) + '牌位"></div>' +
      '<div class="pick-stage">' +
        '<button type="button" class="pick-nav prev" aria-label="往前翻牌堆">‹</button>' +
        '<div class="pick-fan" tabindex="0" role="group" aria-label="牌堆：拖动翻看，轻点一张抽牌"></div>' +
        '<button type="button" class="pick-nav next" aria-label="往后翻牌堆">›</button>' +
      '</div>' +
      '<div class="pick-foot"><span class="pick-hint"></span>' +
        '<button type="button" class="pick-reset">重选</button></div>';

    const slots = wrap.querySelector('.pick-slots');
    const fan = wrap.querySelector('.pick-fan');
    const hint = wrap.querySelector('.pick-hint');
    const resetBtn = wrap.querySelector('.pick-reset');

    // 牌位：先亮出位置名，抽到的牌一张张压上来（牌背朝上）
    const slotEls = positions.map((p, i) => {
      const s = document.createElement('div');
      s.className = 'pick-slot';
      s.setAttribute('role', 'listitem');
      s.innerHTML = '<span class="ps-num">' + (i + 1) + '</span>' +
        '<span class="ps-name">' + escHtml(p.name || '') + '</span>' +
        '<span class="ps-meaning">' + escHtml(p.meaning || '') + '</span>' +
        '<span class="pick-mini" hidden><span class="pm-glyph">✦</span></span>';
      slots.appendChild(s);
      return s;
    });

    // 78 张牌一律牌背朝上：选哪一张由来访者自己决定
    for(let i = 0; i < 78; i++){
      const b = document.createElement('button');
      b.type = 'button';
      b.className = 'pick-card';
      b.dataset.i = String(i);
      b.setAttribute('aria-label', '牌堆第 ' + (i + 1) + ' 张（牌背）');
      b.innerHTML = '<span class="pc-glyph">✦</span>';
      fan.appendChild(b);
    }
    const cards = Array.prototype.slice.call(fan.querySelectorAll('.pick-card'));

    function updateHint(){
      if(submitting) return;
      const left = need - picked.length;
      hint.textContent = left > 0
        ? '还需 ' + left + ' 张 · 拖动牌堆翻看，轻点一张抽出'
        : '张数够了，正在落位…';
    }

    // 扇形排布：只显示视口容得下的张数，拖动时整圈平移
    function layout(){
      const w = fan.clientWidth || 480;
      const cardW = w < 620 ? 46 : 56;
      vis = Math.max(9, Math.min(cards.length, Math.round(w / (cardW * 0.5))));
      const max = Math.max(0, cards.length - vis);
      pos = Math.max(0, Math.min(max, pos));
      const span = Math.min(w - cardW - 16, Math.max(0, (vis - 1) * cardW * 0.62));
      cards.forEach((card, i) => {
        const u = (i - pos) / Math.max(1, vis - 1);
        if(u < -0.06 || u > 1.06 || card.classList.contains('picked')){
          card.style.visibility = 'hidden';
          card.style.pointerEvents = 'none';
          return;
        }
        const edge = (u - 0.5) * 2;                 // -1 .. 1
        const rot = edge * 20;
        const x = edge * span / 2;
        const lift = Math.pow(Math.abs(edge), 2) * 16;
        card.style.visibility = 'visible';
        card.style.pointerEvents = 'auto';
        card.style.transform = 'translate(-50%,0) translate(' + x.toFixed(1) + 'px,' +
          lift.toFixed(1) + 'px) rotate(' + rot.toFixed(1) + 'deg)';
        card.style.zIndex = String(100 + Math.round((1 - Math.abs(edge)) * 100));
      });
    }

    function pick(card){
      if(submitting || card.disabled) return;
      const idx = Number(card.dataset.i);
      if(picked.indexOf(idx) >= 0) return;
      picked.push(idx);
      card.classList.add('picked');
      card.disabled = true;
      card.style.visibility = 'hidden';
      const s = slotEls[picked.length - 1];
      if(s){
        s.classList.add('filled');
        const mini = s.querySelector('.pick-mini');
        if(mini) mini.hidden = false;
      }
      layout();
      updateHint();
      if(picked.length >= need) submit();
    }

    async function submit(){
      if(submitting) return;
      submitting = true;
      wrap.classList.add('is-submitting');
      hint.textContent = '正在把牌放到牌位上…';
      try{
        const r = await fetch('/api/pick', {
          method: 'POST', headers: {'Content-Type': 'application/json'},
          body: JSON.stringify({session_id: sessionId, spread: spread, picks: picked})
        });
        const d = await r.json();
        if(!d || !d.ok) throw new Error((d && d.error) || '落牌失败');
        window.removeEventListener('resize', onResize);
        wrap.remove();
        resolve({cards: d.cards, ask: d.ask || ''});
      }catch(err){
        submitting = false;
        wrap.classList.remove('is-submitting');
        hint.textContent = '落牌失败：' + ((err && err.message) || err) + ' · 点「重选」再来一次';
      }
    }

    function reset(){
      if(submitting) return;
      picked.length = 0;
      cards.forEach(c => {
        c.classList.remove('picked');
        c.disabled = false;
        c.style.visibility = 'visible';
        c.style.pointerEvents = 'auto';
      });
      slotEls.forEach(s => {
        s.classList.remove('filled');
        const mini = s.querySelector('.pick-mini');
        if(mini) mini.hidden = true;
      });
      updateHint();
      layout();
    }

    // 拖动翻牌堆；移动超过 8px 就当作拖动，不误抽一张
    fan.addEventListener('pointerdown', e => {
      if(e.button !== undefined && e.button !== 0) return;
      drag = {x: e.clientX, pos: pos, moved: 0};
      fan.classList.add('is-dragging');
    });
    fan.addEventListener('pointermove', e => {
      if(!drag) return;
      const dx = e.clientX - drag.x;
      drag.moved = Math.max(drag.moved, Math.abs(dx));
      pos = drag.pos - dx / 34;
      layout();
    });
    function endDrag(){
      if(!drag) return;
      const moved = drag.moved;
      drag = null;
      fan.classList.remove('is-dragging');
      if(moved > 8) suppressUntil = Date.now() + 260;
      layout();
    }
    fan.addEventListener('pointerup', endDrag);
    fan.addEventListener('pointercancel', endDrag);
    fan.addEventListener('click', e => {
      if(Date.now() < suppressUntil) return;
      const card = e.target.closest && e.target.closest('.pick-card');
      if(card) pick(card);
    });

    function page(dir){
      const max = Math.max(0, cards.length - vis);
      pos = Math.max(0, Math.min(max, pos + dir * Math.max(1, Math.round(vis / 5))));
      layout();
    }
    wrap.querySelector('.pick-nav.prev').onclick = () => page(-1);
    wrap.querySelector('.pick-nav.next').onclick = () => page(1);
    resetBtn.onclick = reset;
    fan.addEventListener('keydown', e => {
      if(e.key === 'ArrowLeft'){ page(-1); e.preventDefault(); }
      else if(e.key === 'ArrowRight'){ page(1); e.preventDefault(); }
    });

    function onResize(){
      if(!wrap.isConnected){ window.removeEventListener('resize', onResize); return; }
      layout();
    }
    window.addEventListener('resize', onResize);

    inner.insertBefore(wrap, bub);
    chat.scrollTop = chat.scrollHeight;
    updateHint();
    requestAnimationFrame(layout);
  });
}

/* ---------- 左侧工作台牌桌 ----------
   同一次抽牌同时渲染到左栏。聊天里的 draw-wrap 保留（导出解读时要用），
   但在有牌桌时由 CSS 隐藏，避免同一副牌在屏幕上出现两次。 */
const BOARD_CIRC = ['①','②','③','④','⑤','⑥','⑦','⑧','⑨','⑩','⑪','⑫'];
function boardSafeImg(image){
  return (typeof image === 'string' && /^cards\/[A-Za-z0-9_\-\.]+\.(jpe?g|png)$/i.test(image))
    ? image : '';
}
function clearBoard(){
  const el = $('board');
  if(!el) return;
  el.hidden = true;
  el.innerHTML = '';
  document.body.classList.remove('has-board');
}
/* 抽牌发生在提问之前；用户一提问，就把牌桌上的问句补上（离线解读不发新 cards） */
function updateBoardQuestion(q){
  const el = $('board');
  if(!el || !q) return;
  const head = el.querySelector('.b-head');
  if(!head) return;                       // 牌桌还是空的：没有牌阵可挂问题
  let node = el.querySelector('.b-question');
  if(!node){
    node = document.createElement('p');
    node.className = 'b-question';
    const seed = el.querySelector('.b-seed');
    if(seed) seed.after(node);
    else head.after(node);
  }
  node.innerHTML = '<span>你问</span>' + escHtml(q);
  if(typeof lastCards !== 'undefined' && lastCards) lastCards.question = q;
}
function renderBoard(data){
  const el = $('board');
  if(!el) return;
  const items = (data && data.items) || [];
  if(!items.length){ clearBoard(); return; }
  const extras = (data && data.extras) || [];
  const all = items.concat(extras);
  const seed = data.seed == null ? '' : String(data.seed);
  const question = (data.question || '').trim();
  const circ = n => BOARD_CIRC[n-1] || (n + '.');

  let cardsHtml = '';
  all.forEach((c, i) => {
    const safe = boardSafeImg(c.image);
    const rev = c.orientation === '逆位';
    const isExtra = i >= items.length;
    cardsHtml +=
      '<button class="bcard' + (isExtra ? ' extra' : '') + '" type="button" data-i="' + i + '"' +
        ' aria-label="' + escAttr((c.position || '') + '：' + (c.name || '') + ' ' + (c.orientation || '') + '，看大图') + '">' +
        '<span class="b-face">' +
          (safe ? '<img src="' + escAttr(safe) + '" alt="" loading="lazy" class="' + (rev ? 'rev' : '') + '">' : '') +
        '</span>' +
        '<span class="b-pos">' + (isExtra ? '补牌' : circ(i+1) + ' ' + escHtml(c.position || '')) + '</span>' +
        '<span class="b-name">' + escHtml(c.name || '') +
          (c.orientation ? '<em class="' + (rev ? 'rev' : '') + '">' + escHtml(c.orientation) + '</em>' : '') +
        '</span>' +
      '</button>';
  });

  let legendHtml = '';
  items.forEach((c, i) => {
    legendHtml +=
      '<div class="b-lg"><span class="n">' + circ(i+1) + '</span>' +
        '<b>' + escHtml(c.position || '') + '</b>' +
        '<span>' + escHtml(c.position_meaning || '') + '</span></div>';
  });

  el.innerHTML =
    '<div class="b-inner">' +
      '<div class="b-kicker">本次牌阵 · SPREAD</div>' +
      '<div class="b-head"><h2>' + escHtml(data.spread || '抽牌') + '</h2>' +
        '<div class="b-sub">' + escHtml(data.spread_desc || '') +
          (data.spread_desc ? ' · ' : '') + items.length + ' 张' +
          (extras.length ? ' + 补 ' + extras.length : '') +
        '</div></div>' +
      (data.manual
        ? '<p class="b-seed">手选 · 这 ' + items.length + ' 张由你亲手从牌堆里挑出</p>'
        : (seed ? '<p class="b-seed">种子 <b>' + escHtml(seed) + '</b> · 同种子、同牌阵可抽回同一副牌</p>' : '')) +
      (question ? '<p class="b-question"><span>你问</span>' + escHtml(question) + '</p>' : '') +
      '<div class="b-cards">' + cardsHtml + '</div>' +
      '<div class="b-acts">' +
        '<button type="button" data-act="spread">牌阵</button>' +
        '<button type="button" data-act="redraw">重抽</button>' +
        '<button type="button" data-act="extra">补一张</button>' +
        '<span class="b-hint">' + (all.length) + ' 张 · 点牌看大图</span>' +
      '</div>' +
      (legendHtml ? '<details class="b-legend"><summary>牌位在问什么</summary>' + legendHtml + '</details>' : '') +
    '</div>';

  el.hidden = false;
  document.body.classList.add('has-board');
  if(matchMedia('(max-width:640px)').matches){
    chat.querySelectorAll('.msg.greeting').forEach(n => n.remove());
  }

  el.querySelectorAll('.bcard').forEach(btn => {
    btn.addEventListener('click', () => {
      const c = all[Number(btn.dataset.i)];
      if(c) openLightbox(c);
    });
  });
  el.querySelectorAll('[data-act]').forEach(btn => {
    btn.addEventListener('click', () => {
      const act = btn.dataset.act;
      if(act === 'spread') send('换一个牌阵');
      else if(act === 'redraw') send('重抽这副牌');
      else if(act === 'extra') send('补一张牌');
    });
  });
}

async function loadConfig(){
  let d;
  try {
    const r = await fetch('/api/config'); d = await r.json();
  } catch(e) {
    const msg = (e && e.message) || String(e);
    const doc = $('docList'); if (doc) doc.textContent = msg;
    const st = $('testStatus'); if (st) { st.className = 'status err'; st.textContent = msg; }
    const chip = $('backendChip'); if (chip) chip.textContent = uiText('未连接', 'Disconnected');
    return;
  }
  const c = d.config;
  // 旧配置里的 'deepseek' 别名映射到新的 deepseek-chat 预设
  if (c.backend === 'deepseek') c.backend = 'deepseek-chat';
  $('preset').value = PRESET_MAP[c.backend] ? c.backend : 'deepseek-flash';
  $('protocol').value = ['openai','anthropic','gemini'].includes(c.protocol) ? c.protocol : 'auto';
  $('baseUrl').value = c.base_url || '';
  $('model').value = c.model || '';
  $('apiKey').value = ''; // never prefill the secret
  $('apiKey').placeholder = c.api_key_set ? '已保存密钥（留空则不覆盖）' : 'sk-…';
  if($('keyState')){
    $('keyState').textContent = c.api_key_set
      ? uiText('已保存密钥 · 留空保存不会覆盖', 'Key saved · leaving this blank keeps it')
      : uiText('未保存密钥', 'No key saved');
    $('keyState').classList.toggle('is-set', c.api_key_set === true);
  }
  if($('clearKeyBtn')) $('clearKeyBtn').hidden = c.api_key_set !== true;
  $('temp').value = c.temperature ?? 0.8;
  $('timeout').value = c.timeout ?? 120;
  $('toolsEnabled').checked = true; // 工具调用与语气一样恒定开启，配置里的 false 不再生效
  $('toneEnabled').checked = true; // 语气系统恒定开启，忽略配置里可能残留的 false
  $('prophecyEnabled').checked = c.prophecy_enabled === true;
  $('prophecyChip').classList.toggle('on', c.prophecy_enabled === true);
  if($('occultEnabled')) $('occultEnabled').checked = c.occult_enabled === true;
  if($('budget')) $('budget').value = c.daily_token_budget ?? 0;
  if($('maxOut')) $('maxOut').value = c.max_output_tokens ?? 0;
  if($('maxHist')) $('maxHist').value = c.max_history_messages ?? 20;
  if($('maxChars')) $('maxChars').value = c.max_history_chars ?? 24000;
  if($('secondCheck')) $('secondCheck').checked = c.safety_second_check === true;
  updateUsageChip(d.usage, c.daily_token_budget);
  const lang = (c.language || 'zh').indexOf('en') === 0 ? 'en' : 'zh';
  $('langBtn').textContent = lang === 'zh' ? 'EN' : '中文';
  try { localStorage.setItem('olivia.lang', lang); } catch(e){}
  if(window.OliviaI18n) window.OliviaI18n.apply(lang);
  $('presetNote').textContent = PRESET_NOTE[c.backend] || '';
  $('backendChip').textContent = (c.backend||'?') + (c.api_key_set||c.backend==='ollama'
    ? uiText(' · 就绪', ' · ready') : uiText(' · 待填 key', ' · key needed'));
  $('docList').textContent = d.docs && d.docs.length ? d.docs.join('\n') : '（knowledge/ 目录还是空的）';
}

$('preset').addEventListener('change', e => {
  const v = e.target.value; const p = PRESET_MAP[v] || ['','','auto'];
  $('baseUrl').value = p[0]; $('model').value = p[1]; $('protocol').value = p[2] || 'auto';
  $('presetNote').textContent = PRESET_NOTE[v] || '';
});

$('cardsBtn').onclick = () => { location.href = '/cards'; };
$('settingsBtn').onclick = () => { openSheet($('overlay')); };
$('closeBtn').onclick = () => { closeSheet($('overlay')); };
$('shelfBtn').onclick = () => { renderShelf(); openSheet($('shelfOverlay')); };
$('shelfCloseBtn').onclick = () => { closeSheet($('shelfOverlay')); };
$('shelfNewBtn').onclick = () => { closeSheet($('shelfOverlay')); newSession(); };
$('newBtn').onclick = () => { newSession(); };

$('prophecyEnabled').addEventListener('change', e => {
  const on = e.target.checked;
  $('prophecyChip').classList.toggle('on', on);
  toast(on ? uiText('预言模式已开启 · 仅供娱乐，保存后生效', 'Prophecy mode on (for entertainment) · save to apply')
           : uiText('预言模式已关闭 · 回到不预测具体事件', 'Prophecy mode off'));
});
if($('occultEnabled')){
  $('occultEnabled').addEventListener('change', e => {
    toast(e.target.checked
      ? uiText('神秘学模式已开启 · 保存后生效', 'Occult mode on · save to apply')
      : uiText('神秘学模式已关闭', 'Occult mode off'));
  });
}
if($('clearKeyBtn')){
  $('clearKeyBtn').onclick = async () => {
    if(!window.confirm(uiText('清除已保存的 API key？清掉之后要重新填才能连模型。', 'Clear the saved API key? You will have to paste it again to reconnect.'))) return;
    try{
      await fetch('/api/config', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ api_key_clear: true })
      });
      await loadConfig();
      toast(uiText('已清除保存的密钥', 'Saved key cleared'));
    }catch(e){
      toast(uiText('清除失败：', 'Failed: ') + e.message);
    }
  };
}

function collectConfig(){
  return {
    backend: $('preset').value,
    protocol: $('protocol').value,
    base_url: $('baseUrl').value.trim(),
    model: $('model').value.trim(),
    api_key: $('apiKey').value.trim(),
    temperature: parseFloat($('temp').value)||0.8,
    timeout: parseInt($('timeout').value)||120,
    tools_enabled: $('toolsEnabled').checked,
    tone_enabled: $('toneEnabled').checked,
    prophecy_enabled: $('prophecyEnabled').checked,
    occult_enabled: $('occultEnabled') ? $('occultEnabled').checked : false,
    language: (localStorage.getItem('olivia.lang') || 'zh').indexOf('en') === 0 ? 'en' : 'zh',
    daily_token_budget: parseInt($('budget').value)||0,
    max_output_tokens: parseInt($('maxOut').value)||0,
    max_history_messages: parseInt($('maxHist').value)||20,
    max_history_chars: parseInt($('maxChars').value)||24000,
    safety_second_check: $('secondCheck').checked
  };
}

function updateUsageChip(usage, budget){
  const chip = $('usageChip'); if(!chip) return;
  if(!usage) { chip.hidden = true; return; }
  const used = usage.total || 0;
  chip.hidden = false;
  const en = langEn();
  chip.textContent = budget
    ? (en ? ('Today ' + used + ' / ' + budget) : ('今日 ' + used + ' / ' + budget))
    : (en ? ('Today ' + used + ' tokens') : ('今日 ' + used + ' tokens'));
  chip.title = en
    ? ('Today: in ' + (usage.in||0) + ' / out ' + (usage.out||0) + ', ' + (usage.calls||0) + ' calls' + (budget ? ('; budget ' + budget) : ''))
    : ('今日用量：入 ' + (usage.in||0) + ' / 出 ' + (usage.out||0) +
       '，调用 ' + (usage.calls||0) + ' 次' + (budget ? ('；预算 ' + budget) : ''));
  if(budget && used >= budget) chip.style.color = 'var(--err)';
  const st = $('usageStatus');
  if(st) st.textContent = en
    ? ('Today: in ' + (usage.in||0) + ' / out ' + (usage.out||0) +
       ' (total ' + used + '), ' + (usage.calls||0) + ' calls' +
       (budget ? ('; budget ' + budget + ', offline digest after that') : '; no budget set'))
    : ('今日：入 ' + (usage.in||0) + ' / 出 ' + (usage.out||0) +
       '（合计 ' + used + '），调用 ' + (usage.calls||0) + ' 次' +
       (budget ? ('；预算 ' + budget + '，超出后自动改用离线整理') : '；未设置预算'));
}

$('saveBtn').onclick = async () => {
  try {
    const r = await fetch('/api/config',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(collectConfig())});
    const d = await r.json();
    if (!r.ok || d.error) {
      $('testStatus').className='status err'; $('testStatus').textContent='保存失败：'+(d.error||('HTTP '+r.status));
      return;
    }
    $('testStatus').className='status ok'; $('testStatus').textContent='已保存。';
    await loadConfig();
    closeSheet($('overlay'));
  } catch (e) {
    $('testStatus').className='status err'; $('testStatus').textContent='保存失败：'+e.message;
  }
};

$('testBtn').onclick = async () => {
  $('testStatus').className='status'; $('testStatus').textContent='测试中…';
  try{
    const r = await fetch('/api/test',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(collectConfig())});
    const d = await r.json();
    if(d.ok){ $('testStatus').className='status ok'; $('testStatus').textContent='连接成功：'+d.reply; }
    else { $('testStatus').className='status err'; $('testStatus').textContent='失败：'+d.error; }
  }catch(e){ $('testStatus').className='status err'; $('testStatus').textContent='失败：'+e; }
};

let abortCtl = null, stopped = false;

// 占卜档案：解读完成后 Olivia 问一句「现在的心情」，由来访者亲口点选/输入，
// 答复后经 /api/archive answer_emotion 落一条 JSON。Olivia 只问、只记，不猜不代选。
const ARCHIVE_EMOTIONS = ['平静','焦虑','难过','开心','愤怒','迷茫','纠结','疲惫','放松','期待','失落','害怕','安心','委屈','愧疚','希望'];
function renderEmotionAsk(inner){
  const box=document.createElement('div'); box.className='emotion-ask';
  const lead=document.createElement('div'); lead.className='emotion-ask-lead';
  lead.textContent='这次解读，你此刻的心情是？（只记你说的，不替你猜）';
  box.appendChild(lead);
  const chips=document.createElement('div'); chips.className='emotion-chips';
  const chosen=[];
  ARCHIVE_EMOTIONS.forEach(word=>{
    const c=document.createElement('button'); c.type='button'; c.className='emotion-chip';
    c.textContent=word;
    c.onclick=()=>{ const i=chosen.indexOf(word); if(i>=0){chosen.splice(i,1);c.classList.remove('on');} else {chosen.push(word);c.classList.add('on');} };
    chips.appendChild(c);
  });
  box.appendChild(chips);
  const row=document.createElement('div'); row.className='emotion-ask-row';
  const free=document.createElement('input'); free.type='text'; free.placeholder='也可以自己说一个词';
  free.className='emotion-free';
  const ok=document.createElement('button'); ok.type='button'; ok.className='primary'; ok.textContent='记下来';
  const skip=document.createElement('button'); skip.type='button'; skip.textContent='跳过';
  const done=info=>{ box.textContent=''; box.classList.add('is-done');
    box.appendChild(Object.assign(document.createElement('div'),{className:'emotion-ask-done',
      textContent: info && info.emotion_tags && info.emotion_tags.length
        ? '已记进占卜档案：'+info.emotion_tags.join('、') : '好，这次先不记。'})); };
  const submit=async()=>{
    const typed=free.value.trim();
    ok.disabled=true;
    try{
      const r=await fetch('/api/archive',{method:'POST',headers:{'Content-Type':'application/json'},
        body:JSON.stringify({op:'answer_emotion',session_id:sessionId,
          emotion_tags:chosen.slice(), text:typed})});
      const j=await r.json();
      done(j.ok?j:null);
    }catch(e){ ok.disabled=false; row.appendChild(Object.assign(document.createElement('span'),
      {className:'emotion-ask-err',textContent:'没记上，稍后再试'})); }
  };
  ok.onclick=submit;
  free.addEventListener('keydown',e=>{ if(e.key==='Enter'){ e.preventDefault(); submit(); } });
  skip.onclick=()=>{ box.textContent=''; box.classList.add('is-done');
    box.appendChild(Object.assign(document.createElement('div'),{className:'emotion-ask-done',
      textContent:'好，这次先不记。'})); };
  row.append(free,ok,skip); box.appendChild(row);
  inner.appendChild(box);
  chat.scrollTop=chat.scrollHeight;
}

async function send(textOverride){
  if(streaming) return;
  stopSpeech();
  // textOverride：界面上的「补一张」等按钮直接发一条固定文本，不占用输入框
  const isOverride = typeof textOverride === 'string';
  const text = (isOverride ? textOverride : input.value).trim();
  if(!text && !pendingImages.length) return;
  if(!isOverride) input.value='';
  const imgs = pendingImages.slice(); pendingImages=[]; renderImages();
  const shown = text || '（发来一张图片）';
  const um = addMsg('user', shown);
  if(text && !/^(补一张|重抽|换一个牌阵)/.test(text)) updateBoardQuestion(text);
  if(imgs.length){
    const strip=document.createElement('div'); strip.style.cssText='display:flex;gap:6px;margin-top:6px';
    imgs.forEach(src=>{const im=document.createElement('img');im.src=src;im.style.cssText='width:90px;height:90px;object-fit:cover;border-radius:8px';strip.appendChild(im)});
    um.bub.appendChild(strip);
  }
  history.push({role:'user',content:shown});
  const {bub, inner} = addMsg('assistant','');
  const meta = document.createElement('div'); meta.className='meta-line';
  inner.insertBefore(meta, bub);
  streaming = true; $('sendBtn').disabled=true;
  stopped = false;
  abortCtl = new AbortController();
  $('stopBtn').hidden = false;
  let full='', lastCards=null, safetyKind=null, usageInfo=null, emotionAsk=false;

  // 打字机队列：SSE 事件按到达顺序入队，再依次演出。抽牌轮会先收到
  // meditate（默念引导语）→ cards（翻牌）→ token（提问），于是形成
  // 「默念 → 停顿翻牌 → 提问」的仪式节奏。普通对话只有 token，即时呈现。
  const reduceMotion = window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  const events = [];          // 只放抽牌轮需要演出的事件（meditate/cards/token）
  let drawMode = false;       // 见到 meditate 即判定为抽牌轮
  const sleep = ms => new Promise(res => setTimeout(res, ms));

  // ── 打字机队列 ────────────────────────────────────────────
  // 模型可能一口气吐完整段，也可能逐字流式到达；两种都先进队列，再由
  // 同一个循环按「字」演出来，于是看上去永远是在打，而不是刷地出现。
  // 积压多 → 加快（跟得上流）；积压少 → 放慢（看得出在打）；标点处停顿。
  // 系统开了「减少动态效果」时，慢动效（星空、漂浮、入场）该关就关；
  // 但打字机是内容本身的呈现方式，不是装饰，所以保留，只是调快。
  let typed='', pending='', typing=false;
  function enqueue(text){
    if(!text) return;
    full += text;
    pending += text;
    bub.classList.add('typewriting');
    if(!typing){ typing = true; runTyper(); }
  }
  async function runTyper(){
    // 先让光标单独闪一下再落第一个字：短句也能看出是在「打」。
    await sleep(reduceMotion ? 60 : 180);
    // 逐字写进一个文本节点，而不是每字重设 textContent：
    // 后者每次都重建节点、强制重排，长回复会明显掉帧。
    const node = document.createTextNode('');
    bub.textContent = '';
    bub.appendChild(node);
    // 滚动也按帧合并；用户自己往上翻时就不抢了，否则长回复会一直跟人较劲。
    let queued = false;
    const stick = () => {
      if(queued) return;
      if(chat.scrollHeight - chat.scrollTop - chat.clientHeight > 240) return;
      queued = true;
      requestAnimationFrame(() => {
        queued = false;
        chat.scrollTop = chat.scrollHeight;
      });
    };
    while(pending.length){
      if(stopped){ typed += pending; pending=''; node.nodeValue = typed; break; }
      const back = pending.length;
      const ch = pending.slice(0,1); pending = pending.slice(1);
      typed += ch;
      node.nodeValue = typed;
      stick();
      let d;
      if(reduceMotion){ d = 9; }
      else {
        d = back > 90 ? 6 : back > 28 ? 20 : 44;
        if(/[。！？!?]/.test(ch)) d += back > 90 ? 90 : 330;
        else if(/[，、；：,;:…—]/.test(ch)) d += back > 90 ? 40 : 190;
        else if(ch === '\n') d += 120;
      }
      await sleep(d + Math.random() * 14);
    }
    typing = false;
    if(!pending.length) bub.classList.remove('typewriting');
    stick();
  }
  async function drain(){
    while(typing || pending.length){ await sleep(40); }
  }
  async function typeText(text){ enqueue(text); await drain(); }
  async function showCards(data){
    renderCards(inner, bub, data);
    const wrap = inner.querySelector('.draw-wrap');
    if(wrap && !reduceMotion){
      wrap.classList.add('reveal');
      await sleep(Math.min(700, 90 * (data.items ? data.items.length : 3) + 250));
    }
    chat.scrollTop=chat.scrollHeight;
  }
  async function playEvents(){
    for(const obj of events){
      if(stopped) break;
      if(obj.meta && obj.meta.length){ meta.textContent='参考了资料：'+obj.meta.join('、'); }
      if(obj.budget){ updateUsageChip({total: obj.budget.used}, obj.budget.limit); }
      if(obj.usage){ usageInfo=obj.usage; }
      if(obj.tool){
        const badge=document.createElement('div'); badge.className='tool-badge';
        badge.textContent='⚙ '+obj.tool; inner.insertBefore(badge, bub);
        chat.scrollTop=chat.scrollHeight;
      }
      if(obj.safety){ safetyKind=obj.safety; const sl=document.createElement('div');
        sl.className='safety-line'; sl.textContent='🛡 安全闸门已启动 · Olivia 暂停了占卜';
        inner.insertBefore(sl, bub); }
      if(obj.offline){ $('offlineChip').hidden=false; }
      if(obj.fallback){ const fl=document.createElement('div'); fl.className='safety-line';
        fl.textContent='⚠ '+obj.fallback; inner.insertBefore(fl, bub); }
      if(obj.meditate){ await typeText(obj.meditate); await sleep(reduceMotion?0:650); }
      if(obj.cards){ lastCards=obj.cards; await showCards(obj.cards); }
      if(obj.pick){
        // 选牌轮：牌阵已定，等来访者亲手挑满张数后落位
        const res = await renderPickStage(inner, bub, obj.pick);
        if(res && res.cards){
          lastCards = res.cards;
          renderCards(inner, bub, res.cards, {canExtra:false});
          if(res.ask) await typeText(res.ask);
        }
      }
      if(obj.spread_choices){ renderSpreadChoices(bub, obj.spread_choices); chat.scrollTop=chat.scrollHeight; }
      if(obj.token){ await typeText(obj.token); }
      if(obj.error){ full+='\n[错误] '+obj.error; bub.textContent=full; }
    }
  }

  try{
    const r = await fetch('/api/chat',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({message:text,history:history.slice(0,-1),images:imgs,session_id:sessionId,pick:true}),signal:abortCtl.signal});
    const reader = r.body.getReader(), dec = new TextDecoder();
    let buf='';
    while(true){
      const {value,done} = await reader.read(); if(done) break;
      buf += dec.decode(value,{stream:true});
      let idx;
      while((idx=buf.indexOf('\n\n'))>=0){
        const block=buf.slice(0,idx); buf=buf.slice(idx+2);
        const line=block.split('\n').find(l=>l.startsWith('data:'));
        if(!line) continue;
        let obj; try{obj=JSON.parse(line.slice(5).trim())}catch(e){continue}
        if(obj.meditate) drawMode = true;
        if(obj.pick) drawMode = true;
        if(drawMode){
          // 抽牌轮：收齐 meditate→cards→token，流式结束后按序演出动画。
          events.push(obj);
        } else {
          // 普通/解读轮：meta、tool、token 边到边即时呈现，保证跟手。
          if(obj.safety){ safetyKind=obj.safety; const sl=document.createElement('div');
            sl.className='safety-line'; sl.textContent='🛡 安全闸门已启动 · Olivia 暂停了占卜';
            inner.insertBefore(sl, bub); }
          if(obj.offline){ $('offlineChip').hidden=false; }
          if(obj.fallback){ const fl=document.createElement('div'); fl.className='safety-line';
            fl.textContent='⚠ '+obj.fallback; inner.insertBefore(fl, bub); }
          if(obj.tool){
            const badge=document.createElement('div'); badge.className='tool-badge';
            badge.textContent='⚙ '+obj.tool; inner.insertBefore(badge, bub);
          }
          if(obj.cards){ lastCards=obj.cards; renderCards(inner, bub, obj.cards, {canExtra:true}); }  // 解读轮：直接渲染，无需延迟
          if(obj.spread_choices){ renderSpreadChoices(bub, obj.spread_choices); }
          if(obj.budget){ updateUsageChip({total: obj.budget.used}, obj.budget.limit); }
          if(obj.usage){ usageInfo=obj.usage; }
          if(obj.emotion_ask){ emotionAsk=true; }
          if(obj.token){ enqueue(obj.token); }
          if(obj.error){ full+='\n[错误] '+obj.error; bub.textContent=full; }
          chat.scrollTop=chat.scrollHeight;
        }
      }
    }
  }catch(e){
    if(e && e.name === 'AbortError'){ stopped = true; }
    else { full+='\n[错误] '+e; bub.textContent=full; }
  }
  // 流已经结束，剩下的只是本地演出（翻牌/选牌）；不再提供「停止」，避免选牌时卡住。
  $('stopBtn').hidden = true;
  abortCtl = null;
  if(events.length) await playEvents();
  await drain();               // 等最后一个字打完，再挂按钮/存历史
  if(!full && !stopped) bub.textContent='（没有收到回复，检查设置里的连接。）';
  bub.classList.remove('typewriting');
  abortCtl = null;
  $('stopBtn').hidden = true;

  if(stopped && full){
    const an=document.createElement('div'); an.className='abort-note';
    an.textContent='（已停止生成，保留上面这些。）';
    inner.appendChild(an);
  }
  if(usageInfo && usageInfo.total){
    const ul=document.createElement('div'); ul.className='usage-line';
    ul.textContent='本轮 tokens：入 '+(usageInfo.in||0)+' / 出 '+(usageInfo.out||0)+
      '（合计 '+(usageInfo.total||0)+'）';
    inner.appendChild(ul);
  }
  // 解读完成后请来访者亲口说心情，答复后才落档案（Olivia 不猜、不代选）
  if(emotionAsk && !safetyKind && !stopped){ renderEmotionAsk(inner); }
  // 每条回复都能朗读、都能存成图；完全空回复（比如刚发出就停）不给按钮
  if(full){
    const acts=document.createElement('div'); acts.className='msg-acts';
    const spBtn=document.createElement('button');
    spBtn.type='button'; spBtn.textContent='朗读';
    spBtn.onclick=()=>speakText(full, spBtn);
    const saveBtn=document.createElement('button');
    saveBtn.type='button'; saveBtn.textContent= inner._cards ? '存这次解读' : '存成图';
    saveBtn.onclick=async()=>{
      if(saveBtn.disabled) return;
      saveBtn.disabled=true; const old=saveBtn.textContent; saveBtn.textContent='生成中…';
      try{ await exportReading(inner, full); saveBtn.textContent='已保存'; }
      catch(err){ saveBtn.textContent='保存失败'; }
      setTimeout(()=>{ saveBtn.disabled=false; saveBtn.textContent=old; }, 2200);
    };
    acts.appendChild(spBtn); acts.appendChild(saveBtn);
    inner.appendChild(acts);
  }
  // 危机：读完这句就把人送到关怀页（4 秒后自动走，也可以留下或立刻去）
  if(safetyKind){
    const go=document.createElement('div'); go.className='care-route';
    const txt=document.createElement('span');
    txt.textContent='正在打开关怀页——那里有可以立刻拨的号码。';
    const stay=document.createElement('button');
    stay.type='button'; stay.textContent='先留在这里';
    const now=document.createElement('button');
    now.type='button'; now.className='primary'; now.textContent='现在就去';
    now.onclick=()=>{ location.href='/care?from=chat'; };
    const careTimer=setTimeout(()=>{ location.href='/care?from=chat'; }, 4200);
    stay.onclick=()=>{
      clearTimeout(careTimer);
      txt.textContent='好，留在这里。关怀页随时在左侧「关怀」里。';
      stay.remove(); now.remove();
      go.classList.add('is-cancelled');
    };
    go.append(txt, stay, now);
    inner.appendChild(go);
    chat.scrollTop = chat.scrollHeight;
  }
  // 安全闸门的那条回复不进 history（不让危机文本流进模型上下文）
  if(!safetyKind){
    history.push({role:'assistant',content:full,cards:lastCards||undefined});
  } else {
    // 视觉上显示给用户，但 history 里只留一条不带原文的占位。
    history.push({role:'assistant',content:'（安全闸门回复，详见上方提示）',safety:safetyKind});
  }
  // m-16: keep only the recent window in-session (server uses the last 20)
  if(history.length > 40) history = history.slice(-40);
  persistSession();   // 写进会话簿：刷新/关页都能翻回这一页
  streaming=false; $('sendBtn').disabled=false;
}

$('sendBtn').onclick = send;
$('stopBtn').onclick = () => {
  stopped = true;
  try { if(abortCtl) abortCtl.abort(); } catch(e) {}
  $('stopBtn').hidden = true;
};
$('lbClose').onclick = closeLightbox;
$('lightbox').addEventListener('click', e => { if(e.target === $('lightbox')) closeLightbox(); });
document.addEventListener('keydown', e => { if(e.key === 'Escape') closeLightbox(); });
input.addEventListener('keydown', e => {
  if(e.key==='Enter' && !e.shiftKey){ e.preventDefault(); send(); }
});
input.addEventListener('input', () => { input.style.height='auto'; input.style.height=Math.min(input.scrollHeight,160)+'px'; });

/* ---------------- memory panel ---------------- */
let memTab = 'facts';
let memData = null;

async function loadMemory(){
  try{
    const r = await fetch('/api/memory'); const d = await r.json();
    memData = d;
    $('memEnabled').checked = d.enabled !== false;
    renderMem();
  }catch(e){ $('memList').textContent = '加载失败：'+e; }
}

function renderMem(){
  if(!memData) return;
  const list = $('memList'); list.innerHTML='';
  const mk = (tag, text, when, buttons) => {
    const el = document.createElement('div'); el.className='mem-item';
    const g = document.createElement('div'); g.className='grow';
    if(tag){ const t=document.createElement('span'); t.className='tag'; t.textContent=tag; g.appendChild(t); }
    g.appendChild(document.createTextNode(text));
    if(when){ const w=document.createElement('span'); w.className='when'; w.textContent=when; g.appendChild(w); }
    el.appendChild(g);
    buttons.forEach(b => { const btn=document.createElement('button'); btn.textContent=b.label; btn.onclick=b.fn; el.appendChild(btn); });
    return el;
  };
  const call = async (op, extra) => {
    const body = Object.assign({op}, extra||{});
    const r = await fetch('/api/memory',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
    memData = await r.json(); renderMem();
  };

  if(memTab === 'facts'){
    const facts = memData.facts||[];
    if(!facts.length){ list.innerHTML='<div class="mem-empty">还没有记住任何线索。正常聊天时会自动提取，也可以手动添加。</div>'; return; }
    facts.forEach(f => {
      const when = (f.created_at||'').slice(0,16) + (f.pinned?' · 已固定':'');
      list.appendChild(mk(f.kind, f.text, when, [
        {label: f.pinned?'取消固定':'固定', fn:()=>call(f.pinned?'unpin':'pin',{id:f.id})},
        {label:'删除', fn:()=>call('delete_fact',{id:f.id})}
      ]));
    });
  } else if(memTab === 'draws'){
    const draws = memData.draws||[];
    if(!draws.length){ list.innerHTML='<div class="mem-empty">还没有抽牌记录。和 Olivia 抽牌后会自动记在这里。</div>'; return; }
    draws.forEach(d => {
      const cards = (d.cards||[]).map(c=>c.name+(c.reversed?'逆位':'正位')).join('、');
      const text = '['+d.spread+'] '+cards+'　问：'+(d.question||'—');
      list.appendChild(mk('抽牌', text, d.created_at, [
        {label:'删除', fn:()=>call('delete_draw',{id:d.id})}
      ]));
    });
  } else {
    const prof = memData.profile||[];
    if(!prof.length){ list.innerHTML='<div class="mem-empty">还没有稳定画像。告诉 Olivia「我叫X」就会记在这里。</div>'; return; }
    prof.forEach(p => {
      list.appendChild(mk('画像', p.key+'：'+p.value, p.updated_at, [
        {label:'删除', fn:()=>call('profile_delete',{key:p.key})}
      ]));
    });
  }
}

$('memoryBtn').onclick = () => { openSheet($('memOverlay')); loadMemory(); };
$('memCloseBtn').onclick = () => { closeSheet($('memOverlay')); };
document.querySelectorAll('.mem-tabs button').forEach(b => {
  b.onclick = () => {
    document.querySelectorAll('.mem-tabs button').forEach(x=>x.classList.remove('active'));
    b.classList.add('active'); memTab = b.dataset.tab; renderMem();
  };
});
$('memEnabled').onchange = async e => {
  const r = await fetch('/api/memory',{method:'POST',headers:{'Content-Type':'application/json'},
    body:JSON.stringify({op:'toggle',enabled:e.target.checked})});
  memData = await r.json();
  $('memStatus').className='status ok'; $('memStatus').textContent = e.target.checked?'记忆已开启':'记忆已关闭（不会读取或写入）';
};
$('memAddBtn').onclick = async () => {
  const text = prompt('要记住什么？（例如：我对咖啡因敏感）');
  if(!text) return;
  const r = await fetch('/api/memory',{method:'POST',headers:{'Content-Type':'application/json'},
    body:JSON.stringify({op:'add_fact',kind:'fact',text})});
  memData = await r.json(); renderMem();
};
$('memTidyBtn').onclick = async () => {
  // lightweight "dreaming": collapse exact-duplicate facts, keep one
  const facts = (memData&&memData.facts)||[];
  const seen = {}; const dups = [];
  facts.forEach(f => { const k=(f.kind+'|'+f.text).trim(); if(seen[k]) dups.push(f.id); else seen[k]=f.id; });
  for(const id of dups){ await fetch('/api/memory',{method:'POST',headers:{'Content-Type':'application/json'},
    body:JSON.stringify({op:'delete_fact',id})}); }
  const r = await fetch('/api/memory'); memData = await r.json(); renderMem();
  $('memStatus').className='status ok'; $('memStatus').textContent = '整理完成，合并了 '+dups.length+' 条重复。';
};
$('memForgetBtn').onclick = async () => {
  const r = await fetch('/api/memory',{method:'POST',headers:{'Content-Type':'application/json'},
    body:JSON.stringify({op:'forget_recent',n:3})});
  memData = await r.json(); renderMem();
  $('memStatus').className='status ok'; $('memStatus').textContent = '已忘掉最近 3 条线索。';
};
$('memClearBtn').onclick = async () => {
  if(!confirm('确定清空全部记忆？此操作不可撤销。')) return;
  const r = await fetch('/api/memory',{method:'POST',headers:{'Content-Type':'application/json'},
    body:JSON.stringify({op:'clear'})});
  memData = await r.json(); renderMem();
  $('memStatus').className='status ok'; $('memStatus').textContent = '已清空全部记忆。';
};

// ---------- 主动关怀 (L3 always-on) ----------
let careData = null;
async function loadCare(silent){
  try {
    const r = await fetch('/api/schedule'); careData = await r.json();
  } catch(e) {
    const msg = (e && e.message) || String(e);
    const l = $('taskList'); if (l) l.textContent = msg;
    const o = $('outboxList'); if (o) o.textContent = msg;
    const wl = $('watcherList'); if (wl) wl.textContent = msg;
    const wg = $('watchLog'); if (wg) wg.textContent = msg;
    return;
  }
  const s = careData.status||{};
  $('careMaster').checked = !!s.master;
  $('quietStart').value = s.quiet_start||'22:00';
  $('quietEnd').value = s.quiet_end||'08:00';
  const unread = s.unread||0;
  const badge = $('careBadge');
  if(badge){ badge.hidden = unread===0; badge.textContent = unread; }
  $('careUnread').hidden = unread===0; $('careUnread').textContent = unread;
  renderGoals(); renderTasks(); renderOutbox(); renderWatchers(); renderWatchLog();
  if(!silent) $('careStatus').className='status';
}
// ---------- 目标 · 下一步（用户自己定方向；Olivia 不替你推进） ----------
const GOAL_STATUS_LABEL = {active:'进行中',paused:'暂停',done:'已完成',dropped:'已放下'};
function renderGoals(){
  const list=$('goalList'); if(!list) return; list.innerHTML='';
  const goals=(careData&&careData.goals)||[];
  if(!goals.length){ list.innerHTML='<div class="mem-empty">还没有目标。新建一个你正在推进的事，Olivia 回访时会带着它。</div>'; return; }
  goals.forEach(g=>{
    const row=document.createElement('div'); row.className='care-row'; row.dataset.gid=g.id;
    const tdiv=document.createElement('div'); tdiv.className='t';
    tdiv.textContent=(GOAL_STATUS_LABEL[g.status]||g.status)+'　'+g.title;
    const sdiv=document.createElement('div'); sdiv.className='s';
    if(g.next_step){
      const tag = g.next_source==='suggested' ? '〔Olivia 建议 · 待你确认〕' : '〔你定的〕';
      sdiv.textContent='下一步：'+g.next_step+'　'+tag;
    } else {
      sdiv.textContent='下一步：还没定';
    }
    const acts=document.createElement('div'); acts.className='acts'; acts.style.cssText='margin-top:6px;flex-wrap:wrap';
    const mk=(label,op,extra)=>{ const b=document.createElement('button'); b.textContent=label;
      b.onclick=async()=>{ await fetch('/api/goals',{method:'POST',headers:{'Content-Type':'application/json'},
        body:JSON.stringify(Object.assign({op,id:g.id},extra||{}))}); await loadCare(true); }; return b; };
    // 下一步的编辑与完成确认只由本人在这里操作；MCP / 模型无权调用 confirm_step。
    const stepIn=document.createElement('input'); stepIn.className='goal-step-input';
    stepIn.placeholder='写下一步（你自己定）'; stepIn.style.flex='1 1 12em';
    const setBtn=document.createElement('button'); setBtn.textContent='设为下一步';
    setBtn.onclick=async()=>{ const v=stepIn.value.trim(); if(!v){alert('先写下一步');return;}
      await fetch('/api/goals',{method:'POST',headers:{'Content-Type':'application/json'},
        body:JSON.stringify({op:'set_next',id:g.id,text:v,source:'user'})}); await loadCare(true); };
    const sugBtn=document.createElement('button'); sugBtn.textContent='记为建议';
    sugBtn.title='由 Olivia 提出、等你点头的下一步';
    sugBtn.onclick=async()=>{ const v=stepIn.value.trim(); if(!v){alert('先写建议内容');return;}
      await fetch('/api/goals',{method:'POST',headers:{'Content-Type':'application/json'},
        body:JSON.stringify({op:'set_next',id:g.id,text:v,source:'suggested'})}); await loadCare(true); };
    acts.appendChild(stepIn); acts.appendChild(setBtn); acts.appendChild(sugBtn);
    if(g.next_step){
      const conf=document.createElement('button'); conf.textContent='✓ 这一步做到了';
      conf.title='只有你能确认；确认后记入完成历史';
      conf.onclick=async()=>{ await fetch('/api/goals',{method:'POST',headers:{'Content-Type':'application/json'},
        body:JSON.stringify({op:'confirm_step',id:g.id})}); await loadCare(true); };
      acts.appendChild(conf);
    }
    const statusSel=document.createElement('select'); statusSel.className='goal-status-select';
    Object.keys(GOAL_STATUS_LABEL).forEach(k=>{ const o=document.createElement('option'); o.value=k;
      o.textContent=GOAL_STATUS_LABEL[k]; if(k===g.status)o.selected=true; statusSel.appendChild(o); });
    statusSel.onchange=async()=>{ await fetch('/api/goals',{method:'POST',headers:{'Content-Type':'application/json'},
      body:JSON.stringify({op:'update',id:g.id,data:{status:statusSel.value}})}); await loadCare(true); };
    acts.appendChild(statusSel);
    acts.appendChild(mk('删除','delete'));
    row.appendChild(tdiv);
    if(g.note){ const ndiv=document.createElement('div'); ndiv.className='c'; ndiv.textContent=g.note; row.appendChild(ndiv); }
    row.appendChild(sdiv); row.appendChild(acts);
    // 已完成步骤历史（最近 3 条）
    if(g.steps&&g.steps.length){
      const hd=document.createElement('div'); hd.className='c';
      hd.textContent='已完成：'+g.steps.slice(0,3).map(s=>s.text).join('、');
      row.appendChild(hd);
    }
    list.appendChild(row);
  });
}
// ---------- 占卜档案（按用户 / 主题检索） ----------
async function searchArchive(){
  const box=$('arcList'); if(!box) return;
  const u=($('arcUser').value||'').trim(), t=($('arcTopic').value||'').trim();
  const q=new URLSearchParams(); if(u)q.set('user',u); if(t)q.set('query',t);
  try{
    const r=await fetch('/api/archive?'+q.toString()); const d=await r.json();
    const recs=d.records||[]; box.innerHTML='';
    if(!recs.length){ box.innerHTML='<div class="mem-empty">没有匹配的档案。</div>'; return; }
    recs.forEach(rec=>{
      const row=document.createElement('div'); row.className='care-row';
      const tdiv=document.createElement('div'); tdiv.className='t';
      tdiv.textContent=(rec.created_at||'')+'　'+(rec.user||'默认');
      const sdiv=document.createElement('div'); sdiv.className='s';
      sdiv.textContent='【'+(rec.spread||'未注明')+'】'+(rec.question||'');
      const cdiv=document.createElement('div'); cdiv.className='c';
      cdiv.textContent=(rec.points||'')+((rec.emotion_tags&&rec.emotion_tags.length)?'　情绪：'+rec.emotion_tags.join('、'):'');
      row.appendChild(tdiv); row.appendChild(sdiv); row.appendChild(cdiv); box.appendChild(row);
    });
  }catch(e){ box.textContent=(e&&e.message)||String(e); }
}
function renderTasks(){
  const list = $('taskList'); list.innerHTML='';
  const tasks = (careData&&careData.tasks)||[];
  if(!tasks.length){ list.innerHTML='<div class="mem-empty">还没有定时任务。添加一个，比如「每天早上 9 点问候」。</div>'; return; }
  const kindLabel = {daily:'每天',weekly:'每周',interval:'每隔',once:'仅一次',card:'每日一牌'};
  tasks.forEach(t => {
    const row=document.createElement('div'); row.className='care-row';
    const when = t.kind==='interval' ? (t.interval_min+' 分钟') : (t.kind==='once' ? t.run_at : t.cron_time);
    const tdiv=document.createElement('div'); tdiv.className='t';
    tdiv.appendChild(document.createTextNode((t.enabled?'':'[停用] ')+t.name+'　'));
    const whenSpan=document.createElement('span'); whenSpan.className='when-inline';
    whenSpan.textContent=kindLabel[t.kind]+' '+when; tdiv.appendChild(whenSpan);
    const sdiv=document.createElement('div'); sdiv.className='s'; sdiv.textContent='意图：'+t.intent+(t.last_run?'　上次：'+t.last_run:'　尚未运行');
    const cdiv=document.createElement('div'); cdiv.className='c';
    const acts=document.createElement('div'); acts.style.marginTop='6px'; acts.style.display='flex'; acts.style.gap='6px';
    const mkBtn=(label,op,extra)=>{ const b=document.createElement('button'); b.textContent=label;
      b.onclick=async()=>{ await fetch('/api/schedule',{method:'POST',headers:{'Content-Type':'application/json'},
        body:JSON.stringify(Object.assign({op,id:t.id},extra||{}))}); await loadCare(true); }; return b; };
    acts.appendChild(mkBtn(t.enabled?'停用':'启用','update_task',{task:{enabled:!t.enabled}}));
    acts.appendChild(mkBtn('删除','delete_task'));
    row.appendChild(tdiv); row.appendChild(sdiv); row.appendChild(cdiv); row.appendChild(acts);
    list.appendChild(row);
  });
}
function renderOutbox(){
  const list=$('outboxList'); list.innerHTML='';
  const msgs=(careData&&careData.outbox)||[];
  if(!msgs.length){ list.innerHTML='<div class="mem-empty">收件箱还是空的。启用任务并到点后，Olivia 的主动消息会出现在这里。</div>'; return; }
  msgs.forEach(m => {
    const row=document.createElement('div'); row.className='care-row';
    const tdiv=document.createElement('div'); tdiv.className='t';
    tdiv.textContent=(m.read?'':'● ')+'Olivia　'+m.created_at;
    const cdiv=document.createElement('div'); cdiv.className='c'; cdiv.textContent=m.content;
    if(m.goals&&m.goals.length){
      const gd=document.createElement('div'); gd.className='c';
      gd.textContent='关联目标：'+m.goals.join('、')+'（决定仍在你）';
      cdiv.appendChild(gd);
    }
    const acts=document.createElement('div'); acts.className='acts';
    if(!m.read){ const rb=document.createElement('button'); rb.textContent='标为已读';
      rb.onclick=async()=>{ await fetch('/api/schedule',{method:'POST',headers:{'Content-Type':'application/json'},
        body:JSON.stringify({op:'mark_read',id:m.id})}); await loadCare(true); }; acts.appendChild(rb); }
    const db=document.createElement('button'); db.textContent='删除';
    db.onclick=async()=>{ await fetch('/api/schedule',{method:'POST',headers:{'Content-Type':'application/json'},
      body:JSON.stringify({op:'delete_message',id:m.id})}); await loadCare(true); }; acts.appendChild(db);
    row.appendChild(tdiv); row.appendChild(cdiv); row.appendChild(acts); list.appendChild(row);
  });
}
// ---------- 盯事 · 条件触发 ----------
const WATCH_SOURCE_LABEL = {http:'网页/文本', rss:'RSS', json:'JSON', weather:'天气'};
const WATCH_RULE_LABEL = {contains:'包含',not_contains:'不含',regex:'正则',gt:'>',gte:'≥',lt:'<',lte:'≤',changed:'有变化',new_item:'新条目',always:'每次'};
function watchSourceHint(){
  const s=$('watchSource').value;
  const hints={http:'抓取整个网页文本，配合「包含/不含/正则」规则最常用。',
    rss:'订阅源地址；用「新条目」规则可在有新文章时提醒。',
    json:'接口返回的 JSON，用字段路径取值，如 current.temperature_2m。',
    weather:'填城市名即可，无需 API key；用数值规则判断温度，如 < 5。'};
  $('watchHint').textContent=hints[s]||'';
  $('watchUrlLabel').textContent = (s==='weather') ? '城市（也可填自定义接口）' : '网址';
}
function renderWatchers(){
  const list=$('watcherList'); if(!list) return; list.innerHTML='';
  const ws=(careData&&careData.watchers)||[];
  if(!ws.length){ list.innerHTML='<div class="mem-empty">还没有盯事任务。比如盯北京气温，低于 5°C 时提醒加衣。</div>'; return; }
  ws.forEach(w=>{
    const row=document.createElement('div'); row.className='care-row';
    const tdiv=document.createElement('div'); tdiv.className='t';
    tdiv.appendChild(document.createTextNode((w.enabled?'':'[停用] ')+w.name+'　'));
    const meta=document.createElement('span'); meta.className='when-inline';
    // m-13: show the threshold for every numeric rule (gt/gte/lt/lte)
    meta.textContent=WATCH_SOURCE_LABEL[w.source_type]+' · '+WATCH_RULE_LABEL[w.rule]+
      (w.keyword?'「'+w.keyword+'」':'')+
      (['gt','gte','lt','lte'].indexOf(w.rule)>=0?' '+w.threshold:'');
    tdiv.appendChild(meta);
    const sdiv=document.createElement('div'); sdiv.className='s';
    sdiv.textContent='提醒：'+w.intent+'　间隔 '+w.interval_min+' 分 / 冷却 '+w.cooldown_min+' 分'+(w.last_fire?'　上次触发：'+w.last_fire:(w.last_check?'　上次检查：'+w.last_check:'　尚未检查'));
    const acts=document.createElement('div'); acts.style.cssText='margin-top:6px;display:flex;gap:6px;flex-wrap:wrap';
    const mkBtn=(label,op,extra)=>{ const b=document.createElement('button'); b.textContent=label;
      b.onclick=async()=>{ await fetch('/api/schedule',{method:'POST',headers:{'Content-Type':'application/json'},
        body:JSON.stringify(Object.assign({op,id:w.id},extra||{}))}); await loadCare(true); }; return b; };
    acts.appendChild(mkBtn(w.enabled?'停用':'启用','update_watcher',{watcher:{enabled:!w.enabled}}));
    acts.appendChild(mkBtn('删除','delete_watcher'));
    row.appendChild(tdiv); row.appendChild(sdiv); row.appendChild(acts); list.appendChild(row);
  });
}
function renderWatchLog(){
  const box=$('watchLog'); if(!box) return; box.innerHTML='';
  const ev=(careData&&careData.watcher_events)||[];
  if(!ev.length){ box.innerHTML='<div class="mem-empty">尚无判定记录。点「立即检查」试一次。</div>'; return; }
  ev.forEach(e=>{
    const row=document.createElement('div'); row.className='care-row';
    const tdiv=document.createElement('div'); tdiv.className='t';
    tdiv.textContent=(e.fired?'● 命中':'○ 未命中')+'　'+e.name+'　'+e.created_at;
    const sdiv=document.createElement('div'); sdiv.className='s'; sdiv.textContent=e.summary||'（无摘要）';
    row.appendChild(tdiv); row.appendChild(sdiv); box.appendChild(row);
  });
}
updateTaskKindUI();
$('dailyCardBtn') && ($('dailyCardBtn').onclick = async () => {
  const t = ($('dailyCardTime').value || '08:00').trim();
  if(!/^\d{1,2}:\d{2}$/.test(t)){ alert('时间写成 08:00 这样'); return; }
  const existing = ((careData && careData.tasks) || []).some(x => x.kind === 'card');
  if(existing && !confirm('已经有一个每日一牌任务了，再建一个会每天发两张。继续？')) return;
  const r = await fetch('/api/schedule',{method:'POST',headers:{'Content-Type':'application/json'},
    body:JSON.stringify({op:'add_task', task:{name:'每日一牌', intent:'每天抽一张牌，陪我看看今天',
      kind:'card', cron_time:t, enabled:true}})});
  const d = await r.json();
  if(d.ok){ $('careStatus').textContent='已开启：每天 '+t+' 抽一张牌'; $('careStatus').className='status ok'; await loadCare(true); }
  else { alert('没能创建：'+(d.error||'')); }
});
$('watchSource') && ($('watchSource').onchange=watchSourceHint);
$('watchAddBtn').onclick = async () => {
  const watcher={
    name:$('watchName').value.trim()||'我的关注',
    intent:$('watchIntent').value.trim()||'有变化时提醒我',
    source_type:$('watchSource').value, rule:$('watchRule').value,
    url:$('watchUrl').value.trim(), keyword:$('watchKeyword').value.trim(),
    threshold:parseFloat($('watchThreshold').value)||0,
    city:$('watchCity').value.trim(), field_path:$('watchField').value.trim(),
    interval_min:parseInt($('watchInterval').value)||60,
    cooldown_min:$('watchCooldown').value||0
  };
  if(watcher.source_type!=='weather' && !watcher.url){ alert('请填写数据源网址'); return; }
  const r=await fetch('/api/schedule',{method:'POST',headers:{'Content-Type':'application/json'},
    body:JSON.stringify({op:'add_watcher',watcher})});
  const d=await r.json();
  if(d.ok){ ['watchName','watchIntent','watchUrl','watchKeyword','watchThreshold','watchCity','watchField'].forEach(id=>$(id).value=''); }
  await loadCare(true);
  $('careStatus').className=d.ok?'status ok':'status err'; $('careStatus').textContent=d.ok?'盯事任务已添加':'添加失败：'+(d.error||'');
};
$('watchCheckBtn').onclick = async () => {
  $('careStatus').className='status'; $('careStatus').textContent='检查中（可能抓取网络，稍候）…';
  const r=await fetch('/api/schedule',{method:'POST',headers:{'Content-Type':'application/json'},
    body:JSON.stringify({op:'run_now'})});
  const d=await r.json(); careData=d; renderTasks(); renderOutbox(); renderWatchers(); renderWatchLog();
  const wf=(d.fired||[]).filter(f=>f.watcher_id);
  $('careStatus').className='status ok';
  $('careStatus').textContent='盯事命中 '+wf.length+' 条'+(wf.length?'，已写入收件箱':'（本次均未满足条件）');
};
$('watchClearLogBtn').onclick = async () => {
  await fetch('/api/schedule',{method:'POST',headers:{'Content-Type':'application/json'},
    body:JSON.stringify({op:'clear_watcher_events'})});
  await loadCare(true);
  $('careStatus').className='status ok'; $('careStatus').textContent='判定日志已清空';
};
// 关怀页没有导航入口：只有安全闸门命中时才会自动跳过去。
// 主动关怀的设置留在设置里，从设置→「主动关怀」打开这个浮层。
const careEntry = $('careSettingsBtn');
if(careEntry) careEntry.onclick = () => {
  closeSheet($('overlay'));
  openSheet($('careOverlay'));
  loadCare();
};
$('careCloseBtn').onclick = () => { closeSheet($('careOverlay')); };
$('careMaster').onchange = async e => {
  await fetch('/api/schedule',{method:'POST',headers:{'Content-Type':'application/json'},
    body:JSON.stringify({op:'settings',values:{master:e.target.checked}})});
  await loadCare(true);
  $('careStatus').className='status ok'; $('careStatus').textContent=e.target.checked?'主动关怀已开启':'主动关怀已暂停';
};
async function saveQuiet(){
  await fetch('/api/schedule',{method:'POST',headers:{'Content-Type':'application/json'},
    body:JSON.stringify({op:'settings',values:{quiet_start:$('quietStart').value.trim()||'22:00',quiet_end:$('quietEnd').value.trim()||'08:00'}})});
  $('careStatus').className='status ok'; $('careStatus').textContent='静默时段已保存';
}
$('quietStart').onchange=saveQuiet; $('quietEnd').onchange=saveQuiet;
function updateTaskKindUI(){
  const kind=$('taskKind').value;
  $('taskWeekdayField').style.display = kind==='weekly' ? '' : 'none';
  $('taskTimeLabel').textContent = kind==='once' ? '日期 + 时间' : (kind==='interval' ? '间隔（分钟）' : '时间');
  $('taskTime').placeholder = kind==='once' ? '2026-12-25 09:00' : (kind==='interval' ? '120' : '09:00');
}
$('taskKind').addEventListener('change', updateTaskKindUI);
$('taskAddBtn').onclick = async () => {
  const name=$('taskName').value.trim(), intent=$('taskIntent').value.trim();
  if(!intent){ alert('请填写「意图」'); return; }
  const kind=$('taskKind').value, time=$('taskTime').value.trim();
  const task={name:name||'主动关怀',intent,kind};
  if(kind==='interval') task.interval_min=parseInt(time)||120;
  else if(kind==='once'){
    // M-2: backend expects "%Y-%m-%d %H:%M", not a bare "09:00"
    const m=time.match(/^(\d{4})[-/](\d{1,2})[-/](\d{1,2})(?:[ T](\d{1,2}):(\d{2}))?$/);
    if(!m){ alert('「仅一次」请填完整日期时间，例如 2026-12-25 09:00'); return; }
    task.run_at=m[1]+'-'+m[2].padStart(2,'0')+'-'+m[3].padStart(2,'0')+' '+(m[4]||'09').padStart(2,'0')+':'+m[5];
  } else {
    task.cron_time=/^\d{1,2}:\d{2}$/.test(time)?time:'09:00';
    if(kind==='weekly') task.weekday=parseInt($('taskWeekday').value,10);
  }
  const r=await fetch('/api/schedule',{method:'POST',headers:{'Content-Type':'application/json'},
    body:JSON.stringify({op:'add_task',task})});
  const d=await r.json(); if(d.ok){ $('taskName').value=''; $('taskIntent').value=''; }
  await loadCare(true);
  $('careStatus').className=d.ok?'status ok':'status err'; $('careStatus').textContent=d.ok?'任务已添加':'添加失败：'+(d.error||'');
};
$('careRunBtn').onclick = async () => {
  $('careStatus').className='status'; $('careStatus').textContent='检查中…';
  const r=await fetch('/api/schedule',{method:'POST',headers:{'Content-Type':'application/json'},
    body:JSON.stringify({op:'run_now'})});
  const d=await r.json(); careData=d; renderTasks(); renderOutbox(); renderWatchers(); renderWatchLog();
  $('careStatus').className='status ok';
  $('careStatus').textContent=(d.fired&&d.fired.length)?('触发了 '+d.fired.length+' 条主动消息'):'当前没有到点的任务';
};
$('outboxReadBtn').onclick = async () => {
  await fetch('/api/schedule',{method:'POST',headers:{'Content-Type':'application/json'},
    body:JSON.stringify({op:'mark_read',all:true})});
  await loadCare(true);
};
$('goalAddBtn') && ($('goalAddBtn').onclick = async () => {
  const title=($('goalTitle').value||'').trim();
  if(!title){ alert('先写一个目标名称'); return; }
  const r=await fetch('/api/goals',{method:'POST',headers:{'Content-Type':'application/json'},
    body:JSON.stringify({op:'add',title,note:($('goalNote').value||'').trim()})});
  const d=await r.json();
  if(d.ok){ $('goalTitle').value=''; $('goalNote').value=''; }
  await loadCare(true);
  $('careStatus').className=d.ok?'status ok':'status err';
  $('careStatus').textContent=d.ok?'目标已建，下一步请你自己定':'新建失败：'+(d.error||'');
});
$('arcSearchBtn') && ($('arcSearchBtn').onclick=searchArchive);
['arcUser','arcTopic'].forEach(id=>{ const el=$(id); if(el) el.addEventListener('keydown',e=>{ if(e.key==='Enter') searchArchive(); }); });

/* ---------- 图片附件 ---------- */
function dataURL(file){
  return new Promise((res,rej)=>{ const fr=new FileReader(); fr.onload=()=>res(fr.result); fr.onerror=rej; fr.readAsDataURL(file); });
}
function renderImages(){
  const box=$('imgPreview'); box.innerHTML='';
  if(!pendingImages.length){ box.style.display='none'; return; }
  box.style.display='flex';
  pendingImages.forEach((src,i)=>{
    const th=document.createElement('div'); th.className='img-thumb';
    const im=document.createElement('img'); im.src=src;
    const x=document.createElement('span'); x.textContent='×'; x.onclick=()=>{pendingImages.splice(i,1);renderImages();};
    th.appendChild(im); th.appendChild(x); box.appendChild(th);
  });
}
$('imgInput').onchange = async e => {
  for(const f of e.target.files){ if(pendingImages.length>=3) break; pendingImages.push(await dataURL(f)); }
  e.target.value=''; renderImages();
};

/* ---------- 个人知识库 ---------- */
let kbData=null;
async function loadKB(){
  let d;
  try {
    d = await (await fetch('/api/plugins')).json();
  } catch(e) {
    const msg = (e && e.message) || String(e);
    const l = $('kbList'); if (l) l.textContent = msg;
    const vs = $('visionStatus'); if (vs) { vs.className = 'status err'; vs.textContent = msg; }
    return;
  }
  kbData=d; renderKB();
  $('visionEnabled').checked=!!(d.vision&&d.vision.config.enabled);
  const vc=d.vision&&d.vision.config||{};
  $('visionBase').value=vc.base_url||''; $('visionModel').value=vc.model||'';
  $('visionKey').placeholder=vc.api_key&&vc.api_key.indexOf('***')>=0?'已保存密钥（留空不覆盖）':'留空则不覆盖';
  renderOcrStatus(d&&d.vision&&d.vision.ocr);
}
function renderOcrStatus(ocr){
  const el=$('ocrStatus'); if(!el) return;
  if(ocr&&ocr.ok){
    const which = ocr.backend==='tesseract' ? 'Tesseract'
      : uiText('Windows 自带识别器','Windows built-in OCR');
    const langs = ocr.langs&&ocr.langs.length ? ' · '+ocr.langs.join(' / ') : '';
    el.className='status ok';
    el.textContent = uiText('本机 OCR 可用（','Local OCR ready (') + which + langs
      + uiText('）：没配云端视觉模型时，图上的字也能读出来。','): text screenshots are readable without a vision model.');
  } else {
    el.className='status err';
    el.textContent = uiText('本机没有找到可用的 OCR：未配云端视觉模型时读不了图。',
      'No local OCR found: images need a vision model to be read.');
  }
}
function renderKB(){
  const list=$('kbList'); list.innerHTML='';
  const notes=(kbData&&kbData.kb&&kbData.kb.notes)||[];
  if(!notes.length){ list.innerHTML='<div class="mem-empty">还没有归档笔记。可以说"记到知识库"，或在下面手动添加。</div>'; return; }
  notes.forEach(n=>{
    const row=document.createElement('div'); row.className='mem-item';
    const t=document.createElement('div'); t.className='t'; t.textContent=(n.pinned?'📌 ':'')+n.title+(n.tags?'　['+n.tags+']':'');
    const c=document.createElement('div'); c.className='s'; c.textContent=n.content;
    const acts=document.createElement('div'); acts.style.cssText='margin-top:6px;display:flex;gap:6px';
    const mk=(label,op,extra)=>{const b=document.createElement('button');b.textContent=label;
      b.onclick=async()=>{await fetch('/api/plugins',{method:'POST',headers:{'Content-Type':'application/json'},
        body:JSON.stringify(Object.assign({op,id:n.id},extra||{}))});await loadKB();};return b;};
    acts.appendChild(mk(n.pinned?'取消置顶':'置顶','kb_pin',{pinned:!n.pinned}));
    acts.appendChild(mk('删除','kb_delete'));
    row.appendChild(t);row.appendChild(c);row.appendChild(acts);list.appendChild(row);
  });
}
$('kbBtn').onclick=()=>{openSheet($('kbOverlay'));loadKB();};
$('kbCloseBtn').onclick=()=>{closeSheet($('kbOverlay'));};
$('kbAddBtn').onclick=async()=>{
  const title=$('kbTitle').value.trim(), content=$('kbContent').value.trim(), tags=$('kbTags').value.trim();
  if(!content){ $('kbStatus').className='status err'; $('kbStatus').textContent='内容不能为空'; return; }
  const r=await fetch('/api/plugins',{method:'POST',headers:{'Content-Type':'application/json'},
    body:JSON.stringify({op:'kb_add',title,content,tags})});
  if((await r.json()).ok){ $('kbTitle').value='';$('kbContent').value='';$('kbTags').value=''; }
  await loadKB(); $('kbStatus').className='status ok'; $('kbStatus').textContent='已归档';
};
$('kbArchiveBtn').onclick=async()=>{
  const r=await (await fetch('/api/plugins',{method:'POST',headers:{'Content-Type':'application/json'},
    body:JSON.stringify({op:'kb_archive_memory'})})).json();
  await loadKB(); $('kbStatus').className='status ok';
  $('kbStatus').textContent='从记忆归档：'+r.facts+' 条线索、'+r.draws+' 次抽牌';
};
$('kbExportBtn').onclick=async()=>{
  const d=await (await fetch('/api/plugins',{method:'POST',headers:{'Content-Type':'application/json'},
    body:JSON.stringify({op:'kb_export'})})).json();
  const blob=new Blob([d.markdown],{type:'text/markdown;charset=utf-8'});
  const url=URL.createObjectURL(blob);
  const a=document.createElement('a');a.href=url;a.download='olivia-kb.md';a.click();
  setTimeout(()=>URL.revokeObjectURL(url), 0);
};

/* ---------- 视觉设置 ---------- */
const VISION_MAP={
  openai:['https://api.openai.com/v1','gpt-4o-mini'],
  qwen:['https://dashscope.aliyuncs.com/compatible-mode/v1','qwen-vl-max'],
  glm:['https://open.bigmodel.cn/api/paas/v4','glm-4v-plus'],
  moonshot:['https://api.moonshot.cn/v1','moonshot-v1-8k-vision-preview'],
  custom:['','']
};
$('visionPreset').onchange=e=>{const p=VISION_MAP[e.target.value]||['',''];$('visionBase').value=p[0];$('visionModel').value=p[1];};
$('visionSaveBtn').onclick=async()=>{
  const payload={op:'vision_config',enabled:$('visionEnabled').checked,
    base_url:$('visionBase').value.trim(),model:$('visionModel').value.trim(),
    api_key:$('visionKey').value.trim()};
  if(!payload.api_key) delete payload.api_key;
  const d=await (await fetch('/api/plugins',{method:'POST',headers:{'Content-Type':'application/json'},
    body:JSON.stringify(payload)})).json();
  $('visionStatus').className='status '+(d.ok?'ok':'err');
  $('visionStatus').textContent=d.ok?'视觉设置已保存':('失败：'+(d.error||''));
  $('visionKey').value='';
  await loadKB();
};

/* ---------------------------------------------------------------------------
   分享图：把最后一副牌导出成 PNG（纯 Canvas，本地生成，不上传）。
   Olivia 的风格——深紫底 + 月光银字，牌是主角：牌图按牌阵网格摆放，
   每张牌下标牌位 / 牌名 / 正逆位，页脚写牌阵、问题与复现种子。
   --------------------------------------------------------------------------- */
function lastShareData(){
  for(let i = history.length - 1; i >= 0; i--){
    const m = history[i];
    if(m && m.cards && m.cards.items && m.cards.items.length) return m.cards;
  }
  return null;
}
function toast(msg){
  const t = document.createElement('div');
  t.className = 'safety-line';
  t.style.cssText = 'position:fixed;left:50%;bottom:24px;transform:translateX(-50%);z-index:999';
  t.textContent = msg;
  document.body.appendChild(t);
  setTimeout(()=>t.remove(), 2600);
}
function loadImage(src){
  return new Promise(res => {
    const im = new Image();
    im.onload = () => res(im);
    im.onerror = () => res(null);
    im.src = src;
  });
}
async function exportShare(){
  const data = lastShareData();
  if(!data){ toast('还没有可分享的牌，先抽一副吧。'); return; }
  const items = data.items || [];
  const W = 1080, H = 1350;
  const cv = document.createElement('canvas'); cv.width = W; cv.height = H;
  const g = cv.getContext('2d');

  // 背景：深紫月光渐变
  const bg = g.createLinearGradient(0, 0, 0, H);
  bg.addColorStop(0, '#241c38'); bg.addColorStop(0.55, '#191430'); bg.addColorStop(1, '#100d20');
  g.fillStyle = bg; g.fillRect(0, 0, W, H);
  // 淡淡的光晕
  const halo = g.createRadialGradient(W/2, 300, 40, W/2, 300, 560);
  halo.addColorStop(0, 'rgba(160,132,214,.20)'); halo.addColorStop(1, 'rgba(160,132,214,0)');
  g.fillStyle = halo; g.fillRect(0, 0, W, 720);

  g.textAlign = 'center'; g.textBaseline = 'middle';
  g.fillStyle = '#efe9f7'; g.font = '600 46px "Noto Serif SC", "Songti SC", serif';
  g.fillText('Olivia · 奥莉薇娅', W/2, 92);
  g.fillStyle = '#b9a9d6'; g.font = '24px "Noto Sans SC", sans-serif';
  g.fillText('你的私人塔罗咨询师', W/2, 146);

  g.fillStyle = '#efe9f7'; g.font = '600 40px "Noto Serif SC", serif';
  g.fillText(String(data.spread || '抽牌') + ' · ' + items.length + ' 张', W/2, 226);
  const q = String(data.question || '').trim();
  if(q && q !== '（来访者未明确说明）'){
    g.fillStyle = '#c9bce0'; g.font = '24px "Noto Sans SC", sans-serif';
    const qline = q.length > 32 ? q.slice(0, 31) + '…' : q;
    g.fillText('问：' + qline, W/2, 282);
  }

  // 牌阵网格（沿用后端的 layout 坐标）
  const lay = data.layout || {cols: items.length, rows: 1, cells: items.map((_,i)=>[i+1,1])};
  const cols = Math.max(1, lay.cols|0), rows = Math.max(1, lay.rows|0);
  const gridTop = 370, gridBottom = 1120;
  const cellW = Math.floor(920 / cols), cellH = Math.floor((gridBottom - gridTop) / rows);
  const imgW = Math.min(150, Math.floor(cellW * 0.72));
  const imgH = Math.round(imgW * 1.62);

  const imgs = await Promise.all(items.map(c => {
    const src = typeof c.image === 'string' && /^cards\/[A-Za-z0-9_\-\.]+\.(jpe?g|png)$/i.test(c.image)
      ? c.image : '';
    return src ? loadImage(src) : null;
  }));

  items.forEach((c, i) => {
    const cell = (lay.cells && lay.cells[i]) || [i+1, 1];
    const col = Math.max(1, Math.min(cols, Number(cell[0])||1));
    const row = Math.max(1, Math.min(rows, Number(cell[1])||1));
    const cx = W/2 + (col - (cols+1)/2) * cellW;
    const cy = gridTop + (row - 0.5) * cellH;
    const im = imgs[i];
    if(im){
      g.save();
      if(c.orientation === '逆位'){ g.translate(cx, cy - 6); g.rotate(Math.PI); g.drawImage(im, -imgW/2, -imgH/2, imgW, imgH); }
      else g.drawImage(im, cx - imgW/2, cy - 6 - imgH/2, imgW, imgH);
      g.restore();
    } else {
      g.strokeStyle = '#5b497e'; g.lineWidth = 2;
      g.strokeRect(cx - imgW/2, cy - 6 - imgH/2, imgW, imgH);
    }
    g.fillStyle = '#efe9f7'; g.font = '600 20px "Noto Sans SC", sans-serif';
    g.fillText(String(c.position || (i+1)), cx, cy + imgH/2 + 16);
    g.fillStyle = '#c9bce0'; g.font = '18px "Noto Sans SC", sans-serif';
    g.fillText(String(c.name || ''), cx, cy + imgH/2 + 44);
    g.fillStyle = '#9a86c0'; g.font = '16px "Noto Sans SC", sans-serif';
    g.fillText(String(c.orientation || ''), cx, cy + imgH/2 + 68);
  });

  // 页脚
  g.strokeStyle = 'rgba(160,132,214,.35)'; g.lineWidth = 1;
  g.beginPath(); g.moveTo(120, 1170); g.lineTo(W-120, 1170); g.stroke();
  g.fillStyle = '#9a86c0'; g.font = '18px "Noto Sans SC", sans-serif';
  g.fillText('牌意来自传统韦特体系 · 照见当下，不预言结果', W/2, 1216);
  if(data.seed != null) g.fillText('复现种子 ' + data.seed, W/2, 1252);
  g.fillStyle = '#6f6191'; g.font = '16px "Noto Sans SC", sans-serif';
  g.fillText('Olivia · 本地生成', W/2, 1300);

  try{
    const a = document.createElement('a');
    a.href = cv.toDataURL('image/png');
    a.download = 'olivia-' + (data.spread || 'spread') + '-' + Date.now() + '.png';
    document.body.appendChild(a); a.click(); a.remove();
    toast('分享图已保存为 PNG。');
  }catch(e){ toast('导出失败：' + e); }
}
$('shareBtn').onclick = exportShare;

/* 启动时按书脊翻到对应的一页：#/chat/<id> */
(function bootRoute(){
  let sid = '';
  const m = String(window.location.hash || '').match(/^#\/chat\/([A-Za-z0-9_-]+)/);
  if(m) sid = m[1];
  const shelf = loadShelf();
  if(sid){
    openSession(sid, false);
  } else {
    const last = shelf.find(x => x.id === localStorage.getItem(SHELF_ACTIVE_KEY)) || shelf[0];
    if(last) openSession(last.id, false);
    else setRoute(sessionId, false);
  }
})();
window.addEventListener('popstate', e => {
  const m = String(window.location.hash || '').match(/^#\/chat\/([A-Za-z0-9_-]+)/);
  if(m && m[1] !== sessionId) openSession(m[1], false);
});

/* ---- 语言切换：界面 + 人格一起换 ---- */
$('langBtn').onclick = async () => {
  const cur = (localStorage.getItem('olivia.lang') || 'zh').indexOf('en') === 0 ? 'en' : 'zh';
  const next = cur === 'zh' ? 'en' : 'zh';
  try { localStorage.setItem('olivia.lang', next); } catch(e){}
  try {
    await fetch('/api/config', {method:'POST', headers:{'Content-Type':'application/json'},
      body: JSON.stringify({language: next})});
  } catch(e){}
  location.reload();
};

/* ---- 全量数据导出 / 导入 ---- */
$('exportAllBtn').onclick = async () => {
  const st = $('backupStatus'); st.className = 'status'; st.textContent = '正在打包…';
  try {
    const r = await fetch('/api/backup');
    if(!r.ok) throw new Error('HTTP ' + r.status);
    const blob = await r.blob();
    const a = document.createElement('a');
    a.href = URL.createObjectURL(blob);
    a.download = 'olivia-backup-' + new Date().toISOString().slice(0,10) + '.json';
    document.body.appendChild(a); a.click(); a.remove();
    setTimeout(() => URL.revokeObjectURL(a.href), 3000);
    st.className = 'status ok'; st.textContent = '已导出（不含 API key）。';
  } catch(e) {
    st.className = 'status err'; st.textContent = '导出失败：' + e.message;
  }
};
$('importAllInput').onchange = async e => {
  const file = (e.target.files || [])[0]; if(!file) return;
  const st = $('backupStatus'); st.className = 'status'; st.textContent = '正在导入…';
  try {
    const payload = JSON.parse(await file.text());
    const r = await fetch('/api/backup', {method:'POST', headers:{'Content-Type':'application/json'},
      body: JSON.stringify(payload)});
    const d = await r.json();
    if(!r.ok || !d.ok) throw new Error(d.error || ('HTTP ' + r.status));
    const c = d.counts || {};
    st.className = 'status ok';
    st.textContent = '导入完成：画像 ' + (c.profile||0) + '、线索 ' + (c.facts||0) +
      '、抽牌 ' + (c.draws||0) + '、笔记 ' + (c.notes||0) + '、定时 ' + (c.tasks||0) +
      '、盯事 ' + (c.watchers||0);
  } catch(err) {
    st.className = 'status err'; st.textContent = '导入失败：' + err.message;
  } finally {
    e.target.value = '';
  }
};

/* ---- PWA：可安装、壳离线 ---- */
if('serviceWorker' in navigator){
  window.addEventListener('load', () => {
    navigator.serviceWorker.register('/sw.js').catch(() => {});
  });
}
if(window.OliviaI18n) window.OliviaI18n.apply(localStorage.getItem('olivia.lang') || 'zh');

/* 开场那句是界面文案而不是对话内容：切到英文时也要跟着换 */
if (langEn()) {
  const gb = chat.querySelector('.msg.greeting .bub');
  if (gb) gb.textContent = EN_GREETING;
}

loadConfig();
loadKB();
loadCare(true);  // refresh unread badge on page load
if (new URLSearchParams(location.search).get('care') === '1') {
  openSheet($('careOverlay'));
  loadCare();
  if (typeof watchSourceHint === 'function') watchSourceHint();
  setTimeout(() => window.history.replaceState(null, '', location.pathname + location.hash), 0);
}

/* 从牌义页带一张牌回来：开一页新对话，把这句话放进输入框 */
(function cardToChat(){
  const params = new URLSearchParams(location.search);
  const name = params.get('card');
  if(!name) return;
  const ori = params.get('orient') === 'rev' ? '逆位' : '正位';
  try { window.history.replaceState(null, '', location.pathname); } catch(e) {}
  newSession();
  const box = $('input');
  if(box){
    box.value = '我想从「' + name + '」（' + ori + '）这张牌说起。';
    box.dispatchEvent(new Event('input', {bubbles:true}));
    box.focus();
  }
})();
