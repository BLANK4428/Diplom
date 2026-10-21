let currentOrderId = null;
let busy = false;
let _abortController = null;

function _abortPending() {
  if (_abortController) { _abortController.abort(); _abortController = null; }
  busy = false;
  const btn = document.getElementById('send-btn');
  if (btn) btn.disabled = false;
  hideTyping();
}

/* ── Auto-resize textarea ── */
function autoResize(el) {
  el.style.height = 'auto';
  el.style.height = Math.min(el.scrollHeight, 160) + 'px';
}

/* ── Enter / Shift+Enter ── */
function handleKey(e) {
  if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); send(); }
}

/* ── Example chips ── */
function useExample(el) {
  document.getElementById('text').value = el.textContent.trim();
  autoResize(document.getElementById('text'));
  document.getElementById('text').focus();
}

/* ── Escape HTML ── */
function esc(s) {
  return String(s)
    .replace(/&/g, '&amp;').replace(/</g, '&lt;')
    .replace(/>/g, '&gt;').replace(/"/g, '&quot;')
    .replace(/\n/g, '<br>');
}

/* ── Add message bubble ── */
function addMsg(text, type) {
  const chat = document.getElementById('chat');
  const welcome = document.getElementById('welcome');
  if (welcome) welcome.remove();

  const wrap = document.createElement('div');
  wrap.className = 'msg-row ' + type;

  if (type === 'bot') {
    wrap.innerHTML = `
      <div class="msg-label">AI</div>
      <div class="bubble">${esc(text)}</div>`;
  } else if (type === 'user') {
    wrap.innerHTML = `
      <div class="msg-label">ВЫ</div>
      <div class="bubble">${esc(text)}</div>`;
  } else if (type === 'err') {
    wrap.innerHTML = `
      <div class="msg-label">!</div>
      <div class="bubble err-bubble">${esc(text)}</div>`;
  }

  chat.appendChild(wrap);
  chat.scrollTop = chat.scrollHeight;
  return wrap;
}

/* ── Typing indicator ── */
function showTyping() {
  const chat = document.getElementById('chat');
  const el = document.createElement('div');
  el.className = 'msg-row bot';
  el.id = 'typing';
  el.innerHTML = `
    <div class="msg-label">AI</div>
    <div class="bubble typing-bubble">
      <span class="dot"></span><span class="dot"></span><span class="dot"></span>
    </div>`;
  chat.appendChild(el);
  chat.scrollTop = chat.scrollHeight;
}

function hideTyping() {
  const el = document.getElementById('typing');
  if (el) el.remove();
}

/* ── Send message to server ── */
async function send() {
  if (busy) return;
  const ta = document.getElementById('text');
  const text = ta.value.trim();
  if (!text) return;

  addMsg(text, 'user');
  ta.value = '';
  ta.style.height = 'auto';

  busy = true;
  document.getElementById('send-btn').disabled = true;
  showTyping();

  _abortController = new AbortController();

  try {
    const res = await fetch('/send', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ text }),
      signal: _abortController.signal,
    });

    hideTyping();

    if (!res.ok) { addMsg('Ошибка сервера. Попробуйте позже.', 'err'); return; }

    const data = await res.json();

    if (data.status === 'question') {
      addMsg(data.message, 'bot');

    } else if (data.status === 'done') {
      addMsg('Все параметры получены. Техническое задание сформировано!', 'bot');
      currentOrderId = data.order_id;
      addDownloadCard(data.order_id, data.json);
      showModal(data.json, data.order_id);
      loadHistory();

    } else {
      addMsg(data.message || 'Произошла ошибка.', 'err');
    }

  } catch (e) {
    hideTyping();
    if (e.name !== 'AbortError') {
      addMsg('Нет связи с сервером. Убедитесь, что Flask запущен.', 'err');
    }
  } finally {
    _abortController = null;
    busy = false;
    document.getElementById('send-btn').disabled = false;
  }
}

/* ── Download card appended to chat after order completes ── */
function addDownloadCard(orderId, order) {
  const chat = document.getElementById('chat');
  const card = document.createElement('div');
  card.className = 'msg-row bot';

  const mat  = Array.isArray(order.materials) ? order.materials.join(', ') : '—';
  const fin  = Array.isArray(order.finishing) && order.finishing.length ? order.finishing.join(', ') : '—';
  const dims = order.dimensions || {};
  const size = (dims.width_mm && dims.height_mm)
               ? dims.width_mm + ' × ' + dims.height_mm + ' мм' : '—';
  const pd   = order.print_details || {};
  const dl   = order.deadline || {};

  card.innerHTML = `
    <div class="msg-label">AI</div>
    <div class="dl-card">
      <div class="dl-card-head">
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
          <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"></path>
          <polyline points="14 2 14 8 20 8"></polyline>
        </svg>
        <span>${esc(order.product_type || 'Заказ')}</span>
      </div>
      <table class="h-tbl">
        <tr><td>Тираж</td><td>${esc(order.quantity ? order.quantity + ' шт.' : '—')}</td></tr>
        <tr><td>Формат</td><td>${esc(size)}</td></tr>
        <tr><td>Материал</td><td>${esc(mat)}</td></tr>
        <tr><td>Отделка</td><td>${esc(fin)}</td></tr>
        <tr><td>Цветность</td><td>${esc(pd.colors || '—')}</td></tr>
        <tr><td>Срок</td><td>${esc(dl.date || '—')}</td></tr>
      </table>
      <button class="dl-card-btn" onclick="window.location.href='/download/id/${orderId}'">
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5">
          <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"></path>
          <polyline points="7 10 12 15 17 10"></polyline>
          <line x1="12" y1="15" x2="12" y2="3"></line>
        </svg>
        Скачать КП (DOCX)
      </button>
    </div>`;
  chat.appendChild(card);
  chat.scrollTop = chat.scrollHeight;
}

/* ── Order summary modal ── */
function showModal(order, orderId) {
  const dims = order.dimensions || {};
  const w = dims.width_mm, h = dims.height_mm, d = dims.depth_mm;
  const size = (w && h) ? `${w} × ${h} мм${d ? ' × ' + d + ' мм' : ''}` : '—';

  const mat = Array.isArray(order.materials) ? order.materials.join(', ') : '—';
  const fin = Array.isArray(order.finishing) && order.finishing.length
              ? order.finishing.join(', ') : '—';
  const pd  = order.print_details || {};
  const dl  = order.deadline || {};

  const rows = [
    ['Тип изделия',            order.product_type || '—'],
    ['Тираж',                  order.quantity ? order.quantity + ' шт.' : '—'],
    ['Формат',                 size],
    ['Материал',               mat],
    ['Постпечатная обработка', fin],
    ['Цветность',              pd.colors || '—'],
    ['Срок выполнения',        dl.date || '—'],
    ['Примечания',             order.notes || pd.notes || '—'],
  ];

  document.getElementById('modal-body').innerHTML = `
    <table class="order-tbl">
      ${rows.map(([l, v]) => `
        <tr>
          <td class="ol">${esc(l)}</td>
          <td class="ov">${esc(v)}</td>
        </tr>`).join('')}
    </table>`;

  document.getElementById('dl-btn').onclick = () => {
    if (orderId) window.location.href = '/download/id/' + orderId;
  };
  document.getElementById('modal-overlay').classList.remove('hidden');
}

function closeModal(e) {
  if (!e || e.target === document.getElementById('modal-overlay')) {
    document.getElementById('modal-overlay').classList.add('hidden');
  }
}

/* ── Start a new order session ── */
async function newOrder() {
  _abortPending();
  await fetch('/reset', { method: 'POST' });
  currentOrderId = null;
  document.getElementById('chat').innerHTML = `
    <div class="welcome" id="welcome">
      <div class="welcome-icon">
        <svg width="40" height="40" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
          <polyline points="6 9 6 2 18 2 18 9"></polyline>
          <path d="M6 18H4a2 2 0 0 1-2-2v-5a2 2 0 0 1 2-2h16a2 2 0 0 1 2 2v5a2 2 0 0 1-2 2h-2"></path>
          <rect x="6" y="14" width="12" height="8"></rect>
        </svg>
      </div>
      <h2>Новый заказ</h2>
      <p>Опишите заказ в свободной форме. Система задаст уточняющие вопросы и сформирует структурированное техническое задание.</p>
    </div>`;
}

/* ── History sidebar ── */
let _history = [];

async function loadHistory() {
  try {
    const data = await (await fetch('/history')).json();
    _history = data.slice(0, 12);
    const list = document.getElementById('history-list');
    if (!_history.length) {
      list.innerHTML = '<div class="history-empty">Нет заказов</div>';
      return;
    }
    list.innerHTML = _history.map((o, i) => `
      <div class="h-item" onclick="openHistoryOrder(${i})">
        <div class="h-type">${esc(o.product_type || 'Заказ')}</div>
        <div class="h-meta">
          ${o.quantity ? o.quantity + ' шт.' : ''}
          ${o.deadline?.date ? '· ' + o.deadline.date : ''}
          ${o.created_at ? '<span class="h-date">' + o.created_at.slice(0, 10) + '</span>' : ''}
        </div>
      </div>`).join('');
  } catch (_) {}
}

function openHistoryOrder(idx) {
  const o = _history[idx];
  if (!o) return;

  _abortPending();
  const chat = document.getElementById('chat');
  chat.innerHTML = '';

  // Replay saved dialogue
  const dialogue = Array.isArray(o.dialogue) ? o.dialogue : [];
  dialogue.forEach(m => {
    if (m.role === 'user') addMsg(m.text, 'user');
    else if (m.role === 'bot') addMsg(m.text, 'bot');
  });

  // Summary card with download button
  const mat  = Array.isArray(o.materials) ? o.materials.join(', ') : '—';
  const fin  = Array.isArray(o.finishing) && o.finishing.length ? o.finishing.join(', ') : '—';
  const dims = o.dimensions || {};
  const size = (dims.width_mm && dims.height_mm)
               ? dims.width_mm + ' × ' + dims.height_mm + ' мм' : '—';
  const orderId = o.id;
  const dlBtn = orderId
    ? `<button class="dl-card-btn" onclick="window.location.href='/download/id/${orderId}'">
         <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5">
           <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"></path>
           <polyline points="7 10 12 15 17 10"></polyline>
           <line x1="12" y1="15" x2="12" y2="3"></line>
         </svg>
         Скачать ТЗ (DOCX)
       </button>`
    : '<span class="h-no-file">Файл не найден</span>';

  const card = document.createElement('div');
  card.className = 'msg-row bot';
  card.innerHTML = `
    <div class="msg-label">AI</div>
    <div class="dl-card">
      <div class="dl-card-head">
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
          <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"></path>
          <polyline points="14 2 14 8 20 8"></polyline>
        </svg>
        <span>${esc(o.product_type || 'Заказ')}</span>
        <span class="dl-card-date">${(o.created_at || '').slice(0, 10)}</span>
      </div>
      <table class="h-tbl">
        <tr><td>Тираж</td><td>${esc(o.quantity ? o.quantity + ' шт.' : '—')}</td></tr>
        <tr><td>Формат</td><td>${esc(size)}</td></tr>
        <tr><td>Материал</td><td>${esc(mat)}</td></tr>
        <tr><td>Отделка</td><td>${esc(fin)}</td></tr>
        <tr><td>Цветность</td><td>${esc(o.print_details?.colors || '—')}</td></tr>
        <tr><td>Срок</td><td>${esc(o.deadline?.date || '—')}</td></tr>
      </table>
      ${dlBtn}
    </div>`;

  chat.appendChild(card);
  chat.scrollTop = chat.scrollHeight;
}

/* ── Theme toggle ── */
const ICONS = {
  dark: `<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
    <circle cx="12" cy="12" r="5"/>
    <line x1="12" y1="1" x2="12" y2="3"/><line x1="12" y1="21" x2="12" y2="23"/>
    <line x1="4.22" y1="4.22" x2="5.64" y2="5.64"/><line x1="18.36" y1="18.36" x2="19.78" y2="19.78"/>
    <line x1="1" y1="12" x2="3" y2="12"/><line x1="21" y1="12" x2="23" y2="12"/>
    <line x1="4.22" y1="19.78" x2="5.64" y2="18.36"/><line x1="18.36" y1="5.64" x2="19.78" y2="4.22"/>
  </svg>`,
  light: `<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
    <path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z"/>
  </svg>`,
};

function applyTheme(t) {
  document.documentElement.setAttribute('data-theme', t);
  document.getElementById('theme-icon').innerHTML = ICONS[t];
}

function toggleTheme() {
  const cur = document.documentElement.getAttribute('data-theme') || 'dark';
  const next = cur === 'dark' ? 'light' : 'dark';
  localStorage.setItem('theme', next);
  applyTheme(next);
}

applyTheme(localStorage.getItem('theme') || 'dark');
loadHistory();

/* ── Hide loader after page is ready ── */
window.addEventListener('load', () => {
  const loader = document.getElementById('loader');
  setTimeout(() => {
    loader.classList.add('fade-out');
    setTimeout(() => loader.remove(), 500);
  }, 700);
});
