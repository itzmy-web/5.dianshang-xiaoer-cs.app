/* ============================================================
 * 商擎助理 · AI 客服「小暹」（暹罗猫）1:1 复刻自 TalkData 项目
 * 自包含模块：一行 <script src="/cat.js"></script> 即可接入
 *   - 16 帧循环动画（assets/cat/f01-f16.png）
 *   - 可拖动 / 点按弹出 摸摸·跳跳·喵喵 菜单
 *   - 摸摸→爱心+呼噜气泡；跳跳→跳跃；喵喵→说话
 *   - 聊天面板：快捷提问 + 输入框（本地规则问答，不依赖 LLM）
 * ============================================================ */
(function () {
  if (window.__wenshuCat) return;
  window.__wenshuCat = 1;

  /* ---------- CSS（复刻原版，颜色写死避免依赖宿主变量） ---------- */
  var css = ''
    + '.cat-dock{position:fixed;z-index:95;right:26px;bottom:26px;width:96px;height:110px;cursor:grab;'
    + 'user-select:none;-webkit-user-select:none;touch-action:none;'
    + 'filter:drop-shadow(0 10px 18px rgba(0,0,0,.28))}'
    + '.cat-dock:active{cursor:grabbing}'
    + '.cat-dock.drag{filter:drop-shadow(0 18px 26px rgba(0,0,0,.36))}'
    + '.cat-dock img{position:absolute;left:0;top:0;width:100%;height:100%;object-fit:contain;'
    + 'pointer-events:none;display:none}'
    + '.cat-dock img.on{display:block}'
    + '.cat-dock.jumping{animation:catRealJump .8s cubic-bezier(.3,0,.25,1)}'
    + '@keyframes catRealJump{0%,100%{transform:translateY(0)}30%{transform:translateY(-46px) rotate(-4deg)}'
    + '55%{transform:translateY(-6px)}75%{transform:translateY(-22px)}}'
    + '.cat-dock.wiggling{animation:catWiggle .65s ease-in-out}'
    + '@keyframes catWiggle{0%,100%{transform:rotate(0)}25%{transform:rotate(-9deg)}55%{transform:rotate(8deg)}80%{transform:rotate(-4deg)}}'
    + '.cat-dock.talking{animation:catTalk .55s ease}'
    + '@keyframes catTalk{0%,100%{transform:translateX(0)}25%{transform:translateX(-5px)}55%{transform:translateX(5px)}80%{transform:translateX(-3px)}}'
    + '.cat-heart{position:fixed;z-index:98;font-size:15px;pointer-events:none;opacity:0;'
    + 'animation:catHeartUp 1.3s ease-out forwards}'
    + '@keyframes catHeartUp{0%{opacity:1;transform:translateY(0) scale(.6)}100%{opacity:0;transform:translateY(-60px) scale(1.3)}}'
    + '.cat-say{position:fixed;z-index:98;white-space:nowrap;background:#fffaf4;border:2px solid #c99a5f;'
    + 'border-radius:12px;padding:5px 12px;font-size:12.5px;font-weight:700;color:#7a4a21;'
    + 'box-shadow:0 6px 16px rgba(0,0,0,.22);animation:catPopIn .22s ease}'
    + '@keyframes catPopIn{0%{opacity:0;transform:scale(.6)}100%{opacity:1;transform:scale(1)}}'
    + '.cat-bubble{position:fixed;z-index:96;display:flex;flex-direction:column;gap:5px;padding:7px 10px;'
    + 'background:#fffaf4;border:2px solid #c99a5f;border-radius:14px;box-shadow:0 8px 22px rgba(0,0,0,.22)}'
    + '.cat-bubble button{background:#f6e8dc;border:1px solid #d9b896;border-radius:8px;padding:3px 12px;'
    + 'font-size:12px;color:#7a4a21;cursor:pointer}'
    + '.cat-bubble button:hover{background:#efd9c4}'
    + '.cat-chat{position:fixed;z-index:97;width:min(372px,94vw);height:min(500px,74vh);display:flex;flex-direction:column;'
    + 'background:#fff;border:1px solid #e8e0cd;border-radius:18px;overflow:hidden;'
    + 'box-shadow:0 24px 60px rgba(0,0,0,.3)}'
    + '.cat-chat .hd{display:flex;align-items:center;gap:8px;padding:12px 14px;'
    + 'background:linear-gradient(135deg,#8a5a2b,#c99a5f);color:#fff;font-weight:600;font-size:14px}'
    + '.cat-chat .hd small{font-weight:400;font-size:11.5px;opacity:.92}'
    + '.cat-chat .hd .cls{margin-left:auto;cursor:pointer;opacity:.9;font-size:15px;padding:2px 6px}'
    + '.cat-chat .hd .cls:hover{opacity:1}'
    + '.cat-chat .msgs{flex:1;overflow:auto;padding:12px;display:flex;flex-direction:column;gap:8px;background:#f7f4ef}'
    + '.cat-msg{max-width:84%;padding:9px 12px;border-radius:14px;font-size:13.5px;line-height:1.6;'
    + 'white-space:pre-wrap;word-break:break-word}'
    + '.cat-msg.bot{align-self:flex-start;background:#fff;border:1px solid #e8ded0;color:#3d2b1f}'
    + '.cat-msg.me{align-self:flex-end;background:linear-gradient(135deg,#b07a3f,#d9a869);color:#fff}'
    + '.cat-chat .chips{display:flex;gap:6px;flex-wrap:wrap;padding:8px 12px 0}'
    + '.cat-chat .chips button{background:#f6e8dc;border:1px solid #d9b896;border-radius:999px;'
    + 'padding:4px 11px;font-size:12px;color:#7a4a21;cursor:pointer}'
    + '.cat-chat .chips button:hover{background:#efd9c4}'
    + '.cat-chat .inprow{display:flex;gap:8px;padding:10px 12px 12px}'
    + '.cat-chat .inprow input{flex:1;border:1px solid #d9b896;border-radius:10px;padding:9px 12px;'
    + 'font-size:13px;outline:none;color:#3d2b1f;background:#fffdf9}'
    + '.cat-chat .inprow input:focus{border-color:#b07a3f}'
    + '.cat-chat .inprow button{background:linear-gradient(135deg,#b07a3f,#d9a869);color:#fff;border:none;'
    + 'border-radius:10px;padding:9px 16px;cursor:pointer;font-weight:600}'
    + '.cat-chat .inprow button:disabled{opacity:.6;cursor:default}'
    + '.cat-hide{display:none!important}';
  var style = document.createElement('style');
  style.textContent = css;
  document.head.appendChild(style);

  /* ---------- HTML ---------- */
  var framesHtml = '';
  for (var i = 1; i <= 16; i++) {
    var nn = (i < 10 ? '0' : '') + i;
    framesHtml += '<img src="/assets/cat/f' + nn + '.png"' + (i === 1 ? ' class="on"' : '') + ' alt="AI 客服暹罗猫">';
  }
  var wrap = document.createElement('div');
  wrap.innerHTML = ''
    + '<div class="cat-dock" id="catDock" title="拖动换位置 · 点一下和小暹聊天">' + framesHtml + '</div>'
    + '<div class="cat-bubble cat-hide" id="catBubble">'
    +   '<button data-act="pet">🖐 摸摸</button>'
    +   '<button data-act="happy">🎂 跳跳</button>'
    +   '<button data-act="meow">🗣 喵喵</button>'
    + '</div>'
    + '<div class="cat-chat cat-hide" id="catChat">'
    +   '<div class="hd">🐱 小暹 · AI 客服 <small>小猫客服，在线服务</small><span class="cls" id="catClose">✕</span></div>'
    +   '<div class="msgs" id="catMsgs"></div>'
    +   '<div class="chips" id="catChips">'
    +     '<button data-q="这个项目是干什么的？能帮我做什么？">小二能做什么？</button>'
    +     '<button data-q="怎么申请退款？">怎么申请退款？</button>'
    +     '<button data-q="多久能发货？">多久能发货？</button>'
    +     '<button data-q="怎么转人工？">怎么转人工？</button>'
    +   '</div>'
    +   '<div class="inprow"><input id="catInput" placeholder="问小暹点什么喵…" /><button id="catSend">发送</button></div>'
    + '</div>';
  document.body.appendChild(wrap);

  /* ---------- 逻辑（1:1 复刻原版交互） ---------- */
  function $(id) { return document.getElementById(id); }
  var catDock = $('catDock'), catChat = $('catChat'), catBubble = $('catBubble'), catMsgs = $('catMsgs');
  var catHistory = [];
  var catFrames = Array.prototype.slice.call(catDock.querySelectorAll('img'));
  var catFi = 0, catFast = false;
  (function catLoop() {
    setTimeout(function () {
      if (catFrames.length) { catFrames[catFi].classList.remove('on'); catFi = (catFi + 1) % catFrames.length; catFrames[catFi].classList.add('on'); }
      catLoop();
    }, catFast ? 50 : 110);
  })();
  function catPos() { return catDock.getBoundingClientRect(); }
  function showBubble() {
    var r = catPos(); if (r.width === 0) return;
    var x = r.right + 4, y = r.top - 4;
    if (x + 120 > window.innerWidth - 8) x = r.left - 118;
    y = Math.max(8, Math.min(y, window.innerHeight - 150));
    catBubble.style.left = x + 'px'; catBubble.style.top = y + 'px';
    catBubble.classList.remove('cat-hide');
  }
  function hideBubble() { catBubble.classList.add('cat-hide'); }
  function positionChat() {
    var r = catPos(); if (r.width === 0) return;
    var w = catChat.offsetWidth || 372, h = catChat.offsetHeight || 500;
    var x = r.right - w, y = r.bottom + 10;
    if (y + h > window.innerHeight - 8) y = r.top - h - 10;
    if (y < 8) y = 8;
    x = Math.max(8, Math.min(x, window.innerWidth - w - 8));
    catChat.style.left = x + 'px'; catChat.style.top = y + 'px';
  }
  /* 拖动（pointer 事件）；区分「拖动」与「点击」 */
  var catDrag = null;
  catDock.addEventListener('pointerdown', function (e) {
    var r = catPos();
    catDrag = { dx: e.clientX - r.left, dy: e.clientY - r.top, moved: false };
    catDock.classList.add('drag');
    try { catDock.setPointerCapture(e.pointerId); } catch (_) {}
  });
  catDock.addEventListener('pointermove', function (e) {
    if (!catDrag) return;
    if (!catDrag.moved) {
      var dx = e.clientX - catDrag.dx - catPos().left, dy = e.clientY - catDrag.dy - catPos().top;
      if (Math.abs(dx) < 4 && Math.abs(dy) < 4) return;
      catDrag.moved = true;
    }
    var x = Math.min(window.innerWidth - catPos().width - 6, Math.max(6, e.clientX - catDrag.dx));
    var y = Math.min(window.innerHeight - catPos().height - 6, Math.max(6, e.clientY - catDrag.dy));
    catDock.style.left = x + 'px'; catDock.style.top = y + 'px';
    catDock.style.right = 'auto'; catDock.style.bottom = 'auto';
    if (!catBubble.classList.contains('cat-hide')) showBubble();
    if (!catChat.classList.contains('cat-hide')) positionChat();
  });
  catDock.addEventListener('pointerup', function () {
    catDock.classList.remove('drag');
    var wasDrag = catDrag && catDrag.moved; catDrag = null;
    if (wasDrag) return;
    if (catChat.classList.contains('cat-hide')) openChat(); else closeChat();
  });
  /* 悬停保持：离开 300ms 后才收起 */
  var bubT = null;
  function holdBubble() { if (bubT) { clearTimeout(bubT); bubT = null; } if (catChat.classList.contains('cat-hide')) showBubble(); }
  function lateHide() { if (bubT) clearTimeout(bubT); bubT = setTimeout(function () { catBubble.classList.add('cat-hide'); }, 300); }
  catDock.addEventListener('mouseenter', holdBubble);
  catDock.addEventListener('mouseleave', lateHide);
  catBubble.addEventListener('mouseenter', holdBubble);
  catBubble.addEventListener('mouseleave', lateHide);

  function catAnim(cls, ms) { catDock.classList.remove(cls); void catDock.offsetWidth; catDock.classList.add(cls); setTimeout(function () { catDock.classList.remove(cls); }, ms); }
  function spawnHearts() {
    var r = catPos();
    for (var i = 0; i < 6; i++) {
      var s = document.createElement('span'); s.className = 'cat-heart';
      s.textContent = ['❤️', '💕', '✨', '💙'][i % 4];
      s.style.left = (r.left + 12 + Math.random() * (r.width - 24)) + 'px';
      s.style.top = (r.top - 4 - Math.random() * 10) + 'px';
      s.style.animationDelay = (i * 0.09) + 's';
      document.body.appendChild(s); setTimeout(function (el) { return function () { el.remove(); }; }(s), 1500);
    }
  }
  function catSay(t) {
    var r = catPos();
    var old = document.querySelector('.cat-say'); if (old) old.remove();
    var s = document.createElement('div'); s.className = 'cat-say'; s.textContent = t;
    s.style.left = Math.max(8, r.left - 60) + 'px'; s.style.top = Math.max(8, r.top - 46) + 'px';
    document.body.appendChild(s); setTimeout(function () { s.remove(); }, 2300);
  }
  Array.prototype.forEach.call(catBubble.querySelectorAll('button'), function (b) {
    b.onclick = function () {
      var act = b.dataset.act;
      catFast = true; setTimeout(function () { catFast = false; }, 1400);
      if (act === 'pet') { catAnim('wiggling', 650); spawnHearts(); catSay('呼噜呼噜～最开心被摸头了喵！'); }
      else if (act === 'happy') { catAnim('jumping', 800); catSay('喵呜！看我 leap～'); }
      else { catAnim('talking', 550); catSay('喵喵喵～有问题尽管问！'); }
    };
  });

  /* ---------- 聊天面板（本地规则问答，商擎助理场景） ---------- */
  function botSay(t) {
    var m = document.createElement('div');
    m.className = 'cat-msg bot' + (t === '小暹思考中…' ? ' loading' : '');
    m.textContent = t + (t === '小暹思考中…' ? ' ⏳' : '');
    catMsgs.appendChild(m); catMsgs.scrollTop = catMsgs.scrollHeight; return m;
  }
  function meSay(t) {
    var m = document.createElement('div'); m.className = 'cat-msg me'; m.textContent = t;
    catMsgs.appendChild(m); catMsgs.scrollTop = catMsgs.scrollHeight;
  }
  /* 本地问答大脑：命中关键词给答案，未命中卖萌兜底（永不报错） */
  var CAT_KB = [
    { k: ['项目', '干什么', '做什么', '能帮', '介绍', '是什么'], a: '喵~ 这里是「商擎助理 · 智能客服」🐱\n退款、物流、查订单一句话全办完，商品知识与售后政策随问随答，还能陪你闲聊～\n上方工具条还有语音提问、图片识别，随便试！' },
    { k: ['退款', '退货', '售后'], a: '退款这样做喵：\n直接说「我要退款」，我会收集订单号帮你发起申请，\n流程进度实时显示在对话里，随时可查～' },
    { k: ['物流', '发货', '快递', '到货'], a: '发货时效喵：\n现货 48 小时内发出，偏远地区 72 小时；\n直接说「查物流 + 订单号」我帮你查最新轨迹！' },
    { k: ['人工', '真人', '接管'], a: '想找真人客服喵？\n对话里点「🙋 转人工」或直接说「转人工」，\n人工接手后回复会出现在聊天里，还有提示音提醒～' },
    { k: ['订单', '查订单'], a: '查订单喵：\n说「查订单」或点输入框上方的📦 订单卡片，\n订单状态、物流轨迹一次看全～' },
    { k: ['语音', '朗读', '说话'], a: '语音功能喵：\n🎤 语音按钮开启麦克风直接说话，\n🔊 朗读开关让我的回复自动读出来，设置页还能调语速音量！' },
    { k: ['你好', 'hi', 'hello', '在吗', '嗨'], a: '喵呜～我在的！查订单、办退款、聊商品，有什么尽管吩咐！' },
    { k: ['谢谢', '感谢', '辛苦'], a: '不客气喵～摸摸头就更开心了（蹭）🐾' },
    { k: ['天气', '吃饭', '笑话', '故事'], a: '虽然我是客服小猫，但闲聊也接得住喵～\n不过要说店铺里的事，我可是全场最强的！' }
  ];
  function catReply(text) {
    var q = text.toLowerCase();
    for (var i = 0; i < CAT_KB.length; i++) {
      var item = CAT_KB[i];
      for (var j = 0; j < item.k.length; j++) {
        if (q.indexOf(item.k[j].toLowerCase()) >= 0) return item.a;
      }
    }
    return '喵呜…这个问题有点超出猫脑啦 🐾\n退款、物流、查订单、转人工这些我最拿手～\n也可以直接在上方输入框问我试试！';
  }
  function sendCat(text) {
    text = (text || '').trim(); if (!text) return;
    meSay(text); $('catInput').value = '';
    var thinking = botSay('小暹思考中…');
    setTimeout(function () {
      var reply = catReply(text);
      catHistory.push({ role: 'user', content: text }, { role: 'assistant', content: reply });
      if (catHistory.length > 16) catHistory = catHistory.slice(-16);
      thinking.textContent = reply;
      catMsgs.scrollTop = catMsgs.scrollHeight;
      catAnim('talking', 550);
    }, 500 + Math.random() * 400);
  }
  function openChat() {
    catChat.classList.remove('cat-hide'); hideBubble(); positionChat();
    if (!catMsgs.children.length) {
      botSay('喵~ 我是 AI 客服小暹 🐱\n「商擎助理」的问题随便问：怎么退款、多久发货、怎么转人工…\n就算聊天气、聊闲话我也能接住，快来试试！');
    }
    $('catInput').focus();
  }
  function closeChat() { catChat.classList.add('cat-hide'); }
  $('catSend').onclick = function () { sendCat($('catInput').value); };
  $('catInput').addEventListener('keydown', function (e) { if (e.key === 'Enter') sendCat($('catInput').value); });
  $('catClose').onclick = closeChat;
  Array.prototype.forEach.call(document.querySelectorAll('#catChips button'), function (b) {
    b.onclick = function () { sendCat(b.dataset.q); };
  });
})();
