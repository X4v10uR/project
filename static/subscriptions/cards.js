
// ─────────────────────────────────────────────
// STATE
// ─────────────────────────────────────────────
const CARD_ROUTE_SENTINEL = '987654321';
const API = window.CARDS_API_URLS || {};

const DEFAULT_STATE = {
  cards: [],
  subscriptions: [],
  selectedCardId: null,
  search: '',
  addModalOpen: false,
  editCardId: null,
  deleteCardId: null,
};

function parseBootstrapState() {
  const el = document.getElementById('cards-initial-state');
  if (!el || !el.textContent) return { ...DEFAULT_STATE };

  try {
    const parsed = JSON.parse(el.textContent);
    return {
      ...DEFAULT_STATE,
      ...parsed,
      cards: Array.isArray(parsed.cards) ? parsed.cards : [],
      subscriptions: Array.isArray(parsed.subscriptions) ? parsed.subscriptions : [],
      selectedCardId: parsed.selectedCardId ? String(parsed.selectedCardId) : null,
      editCardId: parsed.editCardId ? String(parsed.editCardId) : null,
      deleteCardId: parsed.deleteCardId ? String(parsed.deleteCardId) : null,
    };
  } catch (err) {
    return { ...DEFAULT_STATE };
  }
}

let state = parseBootstrapState();

// ─────────────────────────────────────────────
// HELPERS
// ─────────────────────────────────────────────
const BRAND_LABELS = { visa:'Visa', mastercard:'Mastercard', amex:'American Express', discover:'Discover', jcb:'JCB' };
const THEMES = [
  { key:'dark',   label:'Midnight', color:'#2A2A2A' },
  { key:'navy',   label:'Ocean',    color:'#162660' },
  { key:'forest', label:'Forest',   color:'#0F3A22' },
  { key:'plum',   label:'Plum',     color:'#3A1050' },
  { key:'rose',   label:'Rose',     color:'#4A1025' },
];
const BRANDS = ['visa','mastercard','amex','discover','jcb'];

function apiUrlForCard(template, cardId) {
  return (template || '').replace(CARD_ROUTE_SENTINEL, String(cardId));
}

function getCookie(name) {
  let cookieValue = null;
  if (!document.cookie) return cookieValue;

  const cookies = document.cookie.split(';');
  for (let i = 0; i < cookies.length; i += 1) {
    const cookie = cookies[i].trim();
    if (cookie.substring(0, name.length + 1) === `${name}=`) {
      cookieValue = decodeURIComponent(cookie.substring(name.length + 1));
      break;
    }
  }
  return cookieValue;
}

async function postJson(url, payload) {
  const response = await fetch(url, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'X-Requested-With': 'XMLHttpRequest',
      'X-CSRFToken': getCookie('csrftoken') || '',
    },
    body: JSON.stringify(payload || {}),
  });

  let data = {};
  try {
    data = await response.json();
  } catch (err) {
    data = {};
  }

  if (!response.ok || data.ok === false) {
    throw data;
  }

  return data;
}

function hydrateState(serverState, { keepSearch = true, keepSelected = true } = {}) {
  const previousSearch = state.search;
  const previousSelection = state.selectedCardId;

  state = {
    ...DEFAULT_STATE,
    ...serverState,
    cards: Array.isArray(serverState.cards) ? serverState.cards : [],
    subscriptions: Array.isArray(serverState.subscriptions) ? serverState.subscriptions : [],
    selectedCardId: serverState.selectedCardId ? String(serverState.selectedCardId) : null,
    editCardId: serverState.editCardId ? String(serverState.editCardId) : null,
    deleteCardId: serverState.deleteCardId ? String(serverState.deleteCardId) : null,
  };

  if (keepSearch) {
    state.search = previousSearch || '';
  }

  if (keepSelected && previousSelection) {
    const stillExists = state.cards.some(card => String(card.id) === String(previousSelection));
    state.selectedCardId = stillExists ? String(previousSelection) : state.selectedCardId;
  }
}

function getCardSubs(cardId) { return state.subscriptions.filter(s => String(s.cardId) === String(cardId)); }
function getMonthlySpend(cardId) { return getCardSubs(cardId).reduce((sum,s) => sum + Number(s.monthlyPrice || 0), 0); }
function totalMonthly() { return state.subscriptions.reduce((sum,s) => sum + Number(s.monthlyPrice || 0), 0); }
function primaryCard() { return state.cards.find(c => c.isPrimary); }

// ─────────────────────────────────────────────
// SVG BRAND ICONS
// ─────────────────────────────────────────────
function brandIconSVG(brand, size='md', onCard=true) {
  const px = size === 'sm' ? 24 : size === 'lg' ? 52 : 36;
  const fill = onCard ? 'white' : '#374151';
  if (brand === 'visa') return `<svg width="${px}" height="${px*0.4}" viewBox="0 0 60 20"><text x="0" y="18" font-family="Arial Black, Arial" font-weight="900" font-style="italic" font-size="22" fill="${fill}" letter-spacing="-1">VISA</text></svg>`;
  if (brand === 'mastercard') {
    const r = px*0.38;
    return `<svg width="${px}" height="${r*2}" viewBox="0 0 ${px} ${r*2}"><circle cx="${r*0.7}" cy="${r}" r="${r}" fill="#EB001B" opacity="0.95"/><circle cx="${r*1.3}" cy="${r}" r="${r}" fill="#F79E1B" opacity="0.85"/></svg>`;
  }
  if (brand === 'amex') return `<svg width="${px*1.1}" height="${px*0.4}" viewBox="0 0 70 22"><text x="0" y="18" font-family="Arial, sans-serif" font-weight="800" font-size="18" fill="${fill}" letter-spacing="2">AMEX</text></svg>`;
  if (brand === 'discover') return `<svg width="${px*1.4}" height="${px*0.4}" viewBox="0 0 90 22"><text x="0" y="16" font-family="Arial, sans-serif" font-weight="700" font-size="13" fill="${fill}" letter-spacing="1">DISCOVER</text><circle cx="82" cy="11" r="9" fill="#F76F20"/></svg>`;
  if (brand === 'jcb') {
    const h = px*0.5, w = px*0.8;
    return `<svg width="${w}" height="${h}" viewBox="0 0 ${w} ${h}"><rect x="0" y="0" width="${w/3}" height="${h}" rx="4" fill="#003087"/><rect x="${w/3}" y="0" width="${w/3}" height="${h}" rx="4" fill="#CC0000"/><rect x="${w/3*2}" y="0" width="${w/3}" height="${h}" rx="4" fill="#007B40"/><text x="${w/2}" y="${h*0.68}" font-family="Arial" font-weight="800" font-size="${h*0.55}" fill="white" text-anchor="middle">JCB</text></svg>`;
  }
  return '';
}

// ─────────────────────────────────────────────
// CARD VISUAL HTML (cards stay dark — real credit cards are dark)
// ─────────────────────────────────────────────
function cardVisualHTML(card, isSelected=false, compact=false) {
  const p = compact ? 'p-3' : 'p-5';
  const selClass = isSelected ? 'selected' : '';
  const chipW = compact ? 'width:28px;height:20px' : 'width:40px;height:28px';
  const numSize = compact ? 'font-size:0.75rem' : 'font-size:1rem';
  const nameSize = compact ? 'font-size:0.75rem' : 'font-size:0.875rem';
  const labelSize = compact ? 'font-size:8px' : 'font-size:10px';
  const starSize = compact ? 8 : 10;

  const primaryBadge = card.isPrimary ? `
    <div style="display:flex;align-items:center;gap:4px;background:rgba(222,255,26,0.25);border:1px solid rgba(222,255,26,0.5);border-radius:9999px;padding:2px 8px;">
      <svg width="${starSize}" height="${starSize}" viewBox="0 0 24 24" fill="#DEFF1A" stroke="#DEFF1A" stroke-width="2"><polygon points="12 2 15.09 8.26 22 9.27 17 14.14 18.18 21.02 12 17.77 5.82 21.02 7 14.14 2 9.27 8.91 8.26 12 2"/></svg>
      <span style="color:#DEFF1A;font-size:${starSize}px;font-weight:600;">Primary</span>
    </div>` : '';

  return `
    <div class="card-visual gradient-${card.theme} ${selClass}" data-card-id="${card.id}" onclick="handleCardClick('${card.id}')">
      <div style="position:absolute;inset:0;background:linear-gradient(135deg,rgba(255,255,255,0.05),transparent);pointer-events:none;"></div>
      <div style="position:absolute;right:-32px;top:-32px;width:160px;height:160px;border-radius:50%;background:rgba(255,255,255,0.04);pointer-events:none;"></div>
      <div style="position:absolute;right:-16px;bottom:-48px;width:208px;height:208px;border-radius:50%;background:rgba(255,255,255,0.03);pointer-events:none;"></div>
      <div class="${p}" style="position:relative;height:100%;display:flex;flex-direction:column;justify-content:space-between;">
        <div style="display:flex;align-items:flex-start;justify-content:space-between;">
          <div class="chip-${card.theme}" style="${chipW};border-radius:6px;box-shadow:inset 0 0 0 1px rgba(255,255,255,0.15);">
            <div style="width:100%;height:100%;border-radius:6px;overflow:hidden;opacity:0.3;">
              <div style="height:1px;background:rgba(0,0,0,0.4);margin-top:35%;"></div>
              <div style="height:1px;background:rgba(0,0,0,0.4);margin-top:25%;"></div>
            </div>
          </div>
          ${primaryBadge}
        </div>
        <div>
          <p class="mono" style="color:rgba(255,255,255,0.85);letter-spacing:0.2em;${numSize};">•••• •••• •••• ${card.last4 || '0000'}</p>
        </div>
        <div style="display:flex;align-items:flex-end;justify-content:space-between;">
          <div>
            <p style="color:rgba(255,255,255,0.5);${labelSize};text-transform:uppercase;letter-spacing:0.1em;margin-bottom:2px;">Card Holder</p>
            <p style="color:white;${nameSize};max-width:120px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;">${card.nickname || 'My Card'}</p>
          </div>
          <div>${brandIconSVG(card.brand, compact ? 'sm' : 'md', true)}</div>
        </div>
      </div>
    </div>`;
}

// ─────────────────────────────────────────────
// RENDER FUNCTIONS
// ─────────────────────────────────────────────
function renderApp() {
  const app = document.getElementById('cards-app');
  if (!app) return;
  app.innerHTML = `
    <div style="flex:1;overflow-y:auto;" id="main-area">
      <div style="padding:24px 20px;max-width:900px;">
        ${renderHeader()}
        ${renderStats()}
        ${renderSearch()}
        ${renderCardsGrid()}
      </div>
    </div>
    ${state.selectedCardId ? renderDetailPanel() : ''}
    ${state.addModalOpen ? renderAddModal() : ''}
    ${state.deleteCardId ? renderDeleteModal() : ''}
  `;
  lucide.createIcons();
  bindModalEvents();
}

function renderHeader() {
  return `
    <div style="display:flex;align-items:flex-start;justify-content:space-between;margin-bottom:24px;">
      <div>
        <h1 style="color:#111827;font-size:1.5rem;font-weight:700;margin:0;">Payment Methods</h1>
        <p style="color:#9CA3AF;font-size:0.875rem;margin:4px 0 0;">Manage your cards and see linked subscriptions</p>
      </div>
      <button onclick="openAddModal()" style="display:flex;align-items:center;gap:8px;background:#DEFF1A;color:#111;padding:10px 16px;border-radius:12px;border:none;cursor:pointer;font-size:0.875rem;font-weight:700;font-family:inherit;white-space:nowrap;transition:background 0.15s;box-shadow:0 2px 8px rgba(0,0,0,0.1);" onmouseover="this.style.background='#CCEE00'" onmouseout="this.style.background='#DEFF1A'">
        <i data-lucide="plus" style="width:15px;height:15px;"></i> Add Card
      </button>
    </div>`;
}

function renderStats() {
  const total = state.cards.length;
  const primaryCount = state.cards.filter(c => c.isPrimary).length;
  const monthly = totalMonthly();
  const pc = primaryCard();
  return `
    <div style="display:grid;grid-template-columns:repeat(3,1fr);gap:12px;margin-bottom:24px;">
      <div class="stat-card">
        <div style="display:flex;align-items:center;gap:8px;margin-bottom:8px;">
          <div style="width:28px;height:28px;border-radius:8px;background:#F0FDF4;display:flex;align-items:center;justify-content:center;">
            <i data-lucide="credit-card" style="width:14px;height:14px;color:#16A34A;"></i>
          </div>
          <span style="color:#6B7280;font-size:0.75rem;font-weight:500;">Total Cards</span>
        </div>
        <p style="color:#111827;font-size:1.5rem;font-weight:700;margin:0;">${total}</p>
        <p style="color:#9CA3AF;font-size:0.75rem;margin:2px 0 0;">${primaryCount} primary</p>
      </div>
      <div class="stat-card">
        <div style="display:flex;align-items:center;gap:8px;margin-bottom:8px;">
          <div style="width:28px;height:28px;border-radius:8px;background:#EFF6FF;display:flex;align-items:center;justify-content:center;">
            <i data-lucide="trending-up" style="width:14px;height:14px;color:#2563EB;"></i>
          </div>
          <span style="color:#6B7280;font-size:0.75rem;font-weight:500;">Monthly Spend</span>
        </div>
        <p style="color:#111827;font-size:1.5rem;font-weight:700;margin:0;">$${monthly.toFixed(0)}</p>
        <p style="color:#9CA3AF;font-size:0.75rem;margin:2px 0 0;">across all cards</p>
      </div>
      <div class="stat-card">
        <div style="display:flex;align-items:center;gap:8px;margin-bottom:8px;">
          <div style="width:28px;height:28px;border-radius:8px;background:#FEFCE8;display:flex;align-items:center;justify-content:center;">
            <i data-lucide="star" style="width:14px;height:14px;color:#CA8A04;fill:#CA8A04;"></i>
          </div>
          <span style="color:#6B7280;font-size:0.75rem;font-weight:500;">Primary Card</span>
        </div>
        <p style="color:#111827;font-size:0.875rem;font-weight:600;margin:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;">${pc ? pc.nickname : '—'}</p>
        <p style="color:#9CA3AF;font-size:0.75rem;margin:2px 0 0;">${pc ? `•••• ${pc.last4}` : 'None set'}</p>
      </div>
    </div>`;
}

function renderSearch() {
  return `
    <div style="position:relative;margin-bottom:20px;">
      <i data-lucide="search" style="position:absolute;left:12px;top:50%;transform:translateY(-50%);width:15px;height:15px;color:#9CA3AF;"></i>
      <input type="text" id="search-input" placeholder="Search cards..." value="${escHtml(state.search)}"
        oninput="handleSearch(this.value)"
        style="width:100%;background:#FFFFFF;border:1px solid #E2E5EA;border-radius:12px;padding:10px 16px 10px 38px;color:#111827;outline:none;font-size:0.875rem;font-family:inherit;transition:all 0.15s;box-shadow:0 1px 3px rgba(0,0,0,0.05);"
        onfocus="this.style.borderColor='#BBCC00';this.style.boxShadow='0 0 0 3px rgba(222,255,26,0.2)'" onblur="this.style.borderColor='#E2E5EA';this.style.boxShadow='0 1px 3px rgba(0,0,0,0.05)'"
      />
    </div>`;
}

function renderCardsGrid() {
  const query = state.search.toLowerCase();
  const filtered = state.cards.filter(c =>
    c.nickname.toLowerCase().includes(query) ||
    (BRAND_LABELS[c.brand] || 'Visa').toLowerCase().includes(query) ||
    c.last4.includes(query)
  );

  if (filtered.length === 0) {
    return `
      <div style="display:flex;flex-direction:column;align-items:center;justify-content:center;padding:80px 0;text-align:center;">
        <div style="width:64px;height:64px;border-radius:16px;background:#FFFFFF;border:1px solid #E2E5EA;display:flex;align-items:center;justify-content:center;margin-bottom:16px;box-shadow:0 1px 4px rgba(0,0,0,0.06);">
          <i data-lucide="credit-card" style="width:24px;height:24px;color:#D1D5DB;"></i>
        </div>
        <p style="color:#9CA3AF;font-size:0.875rem;">${state.search ? 'No cards match your search' : 'No cards added yet'}</p>
        ${!state.search ? `<button onclick="openAddModal()" style="margin-top:16px;display:flex;align-items:center;gap:8px;background:#DEFF1A;color:#111;padding:8px 16px;border-radius:12px;border:none;cursor:pointer;font-size:0.875rem;font-family:inherit;font-weight:700;"><i data-lucide="plus" style="width:14px;height:14px;"></i> Add your first card</button>` : ''}
      </div>`;
  }

  const cols = 'repeat(auto-fill, minmax(220px, 1fr))';
  const cards = filtered.map(card => {
    const subs = getCardSubs(card.id);
    const spend = getMonthlySpend(card.id);
    const isSelected = String(state.selectedCardId) === String(card.id);

    const subsChips = isSelected && subs.length > 0 ? `
      <div style="margin-top:10px;display:flex;flex-wrap:wrap;gap:6px;">
        ${subs.map(sub => `<span style="font-size:10px;padding:4px 10px;border-radius:9999px;color:#111;font-weight:600;background:${sub.color}CC;">${sub.name}</span>`).join('')}
      </div>` : '';

    const miniIcons = subs.length > 0 ? `
      <div style="display:flex;">
        ${subs.slice(0,3).map(sub => `
          <div title="${sub.name}" style="width:20px;height:20px;border-radius:50%;border:2px solid #F0F2F6;background:${sub.color};display:flex;align-items:center;justify-content:center;font-size:8px;color:#111;margin-left:-4px;font-weight:600;">${sub.iconLabel[0]}</div>
        `).join('')}
        ${subs.length > 3 ? `<div style="width:20px;height:20px;border-radius:50%;border:2px solid #F0F2F6;background:#E5E7EB;display:flex;align-items:center;justify-content:center;font-size:8px;color:#6B7280;margin-left:-4px;">+${subs.length-3}</div>` : ''}
      </div>` : '';

    return `
      <div class="fade-in" style="display:flex;flex-direction:column;">
        ${cardVisualHTML(card, isSelected)}
        <div style="margin-top:10px;display:flex;align-items:center;justify-content:space-between;padding:0 4px;opacity:${isSelected ? 1 : 0.85};transition:opacity 0.2s;" onmouseover="this.style.opacity=1" onmouseout="this.style.opacity=${isSelected ? 1 : 0.85}">
          <div style="display:flex;align-items:center;gap:8px;">
            <div style="display:flex;align-items:center;gap:6px;background:#FFFFFF;border:1px solid #E2E5EA;border-radius:9999px;padding:4px 10px;box-shadow:0 1px 2px rgba(0,0,0,0.04);">
              <div style="width:6px;height:6px;border-radius:50%;background:#16A34A;"></div>
              <span style="color:#4B5563;font-size:0.75rem;font-weight:500;">${subs.length} sub${subs.length !== 1 ? 's' : ''}</span>
            </div>
            ${subs.length > 0 ? `<div style="display:flex;align-items:center;gap:4px;font-size:0.75rem;color:#6B7280;font-weight:500;"><i data-lucide="trending-up" style="width:11px;height:11px;"></i><span>$${spend.toFixed(0)}/mo</span></div>` : ''}
          </div>
          ${miniIcons}
        </div>
        ${subsChips}
      </div>`;
  }).join('');

  const addTile = `
    <button onclick="openAddModal()" style="aspect-ratio:1.586/1;display:flex;flex-direction:column;align-items:center;justify-content:center;gap:12px;border:2px dashed #D1D5DB;border-radius:16px;background:#FFFFFF;cursor:pointer;transition:all 0.2s;width:100%;box-shadow:0 1px 4px rgba(0,0,0,0.04);" onmouseover="this.style.borderColor='#BBCC00';this.style.background='#FAFFF0'" onmouseout="this.style.borderColor='#D1D5DB';this.style.background='#FFFFFF'">
      <div style="width:40px;height:40px;border-radius:12px;background:#F3F4F6;border:1px solid #E5E7EB;display:flex;align-items:center;justify-content:center;">
        <i data-lucide="plus" style="width:18px;height:18px;color:#9CA3AF;"></i>
      </div>
      <span style="color:#9CA3AF;font-size:0.875rem;font-weight:500;">Add New Card</span>
    </button>`;

  return `
    <div style="display:grid;grid-template-columns:${cols};gap:16px;">
      ${cards}
      ${addTile}
    </div>`;
}

// ─────────────────────────────────────────────
// DETAIL PANEL
// ─────────────────────────────────────────────
function renderDetailPanel() {
  const card = state.cards.find(c => String(c.id) === String(state.selectedCardId));
  if (!card) return '';
  const subs = getCardSubs(card.id);
  const monthly = subs.reduce((s,sub) => s + Number(sub.monthlyPrice || 0), 0);
  const yearly = monthly * 12;

  const subItems = subs.length === 0
    ? `<div style="background:#F8F9FB;border-radius:16px;padding:24px;border:1px solid #E8EBF0;text-align:center;"><i data-lucide="credit-card" style="width:24px;height:24px;color:#D1D5DB;margin:0 auto 8px;display:block;"></i><p style="color:#9CA3AF;font-size:0.875rem;margin:0;">No subscriptions linked</p></div>`
    : subs.map(sub => `
      <div style="display:flex;align-items:center;gap:12px;padding:12px;border-radius:12px;border:1px solid #E8EBF0;background:${sub.color}20;transition:border-color 0.15s;box-shadow:0 1px 3px rgba(0,0,0,0.04);" onmouseover="this.style.borderColor='#C4C9D4'" onmouseout="this.style.borderColor='#E8EBF0'">
        <div style="width:40px;height:40px;border-radius:12px;background:${sub.iconBg};display:flex;align-items:center;justify-content:center;font-size:0.875rem;flex-shrink:0;border:1px solid rgba(0,0,0,0.08);">${sub.iconLabel}</div>
        <div style="flex:1;min-width:0;">
          <p style="color:#111827;font-size:0.875rem;font-weight:500;margin:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;">${sub.name}</p>
          <p style="color:#9CA3AF;font-size:0.75rem;margin:0;">${sub.plan}</p>
        </div>
        <div style="text-align:right;flex-shrink:0;">
          <p style="color:#111827;font-size:0.875rem;font-weight:600;margin:0;">$${sub.monthlyPrice}/mo</p>
          <p style="color:#9CA3AF;font-size:0.75rem;margin:0;">${sub.daysLeft}d left</p>
        </div>
      </div>`).join('');

  return `
    <style>
      #detail-panel-desktop { display: none; }
      #detail-panel-mobile  { display: none; }
      @media(min-width:1024px) { #detail-panel-desktop { display: flex; flex-direction: column; } }
      @media(max-width:1023px) { #detail-panel-mobile  { display: block; } }
    </style>
    <div class="detail-panel fade-in" id="detail-panel-desktop">
      ${detailPanelContent(card, subs, monthly, yearly, subItems)}
    </div>
    <div id="detail-panel-mobile" style="position:fixed;inset-x:0;bottom:0;z-index:30;background:#FAFBFC;border-top:1px solid #E2E5EA;border-radius:24px 24px 0 0;max-height:60vh;overflow-y:auto;box-shadow:0 -8px 30px rgba(0,0,0,0.1);">
      <div style="width:40px;height:4px;background:#E5E7EB;border-radius:2px;margin:12px auto 4px;"></div>
      ${detailPanelContent(card, subs, monthly, yearly, subItems, true)}
    </div>`;
}

function detailPanelContent(card, subs, monthly, yearly, subItems, mobile=false) {
  const setPrimaryBtn = !card.isPrimary ? `
    <button onclick="handleSetPrimary('${card.id}')" style="width:100%;padding:10px;border-radius:12px;border:1px solid #BBCC00;color:#7A8C00;background:#FAFFF0;cursor:pointer;font-size:0.875rem;font-family:inherit;font-weight:600;display:flex;align-items:center;justify-content:center;gap:8px;margin-bottom:8px;transition:all 0.15s;" onmouseover="this.style.background='#F0FF90'" onmouseout="this.style.background='#FAFFF0'">
      <i data-lucide="star" style="width:14px;height:14px;fill:#BBCC00;color:#BBCC00;"></i> Set as Primary
    </button>` : '';

  return `
    <div style="display:flex;align-items:center;justify-content:space-between;padding:16px 20px;border-bottom:1px solid #E8EBF0;flex-shrink:0;">
      <h3 style="color:#111827;font-size:1rem;font-weight:700;margin:0;">Card Details</h3>
      <button onclick="closeDetailPanel()" style="width:32px;height:32px;border-radius:50%;background:#F3F4F6;border:1px solid #E5E7EB;cursor:pointer;display:flex;align-items:center;justify-content:center;color:#6B7280;transition:all 0.15s;" onmouseover="this.style.background='#E5E7EB';this.style.color='#111827'" onmouseout="this.style.background='#F3F4F6';this.style.color='#6B7280'">
        <i data-lucide="x" style="width:14px;height:14px;"></i>
      </button>
    </div>
    <div style="flex:1;overflow-y:auto;padding:20px;display:flex;flex-direction:column;gap:20px;">
      ${cardVisualHTML(card, false, false)}
      <div style="background:#F8F9FB;border-radius:16px;padding:16px;border:1px solid #E8EBF0;display:flex;flex-direction:column;gap:12px;">
        ${infoRow('Nickname', card.nickname)}
        ${infoRow('Number', `<span class="mono">•••• •••• •••• ${card.last4}</span>`)}
        ${infoRow('Brand', BRAND_LABELS[card.brand] || 'Visa')}
        ${infoRow('Status', card.isPrimary
          ? `<span style="display:flex;align-items:center;gap:4px;font-size:10px;color:#7A8C00;font-weight:700;border:1px solid #BBCC00;background:#FAFFF0;border-radius:9999px;padding:2px 8px;"><i data-lucide="star" style="width:8px;height:8px;fill:#BBCC00;color:#BBCC00;"></i>Primary</span>`
          : `<span style="color:#9CA3AF;font-size:0.875rem;">Backup</span>`)}
      </div>
      <div style="display:grid;grid-template-columns:1fr 1fr;gap:12px;">
        <div class="stat-card">
          <div style="display:flex;align-items:center;gap:8px;margin-bottom:8px;">
            <div style="width:24px;height:24px;border-radius:6px;background:#EFF6FF;display:flex;align-items:center;justify-content:center;">
              <i data-lucide="trending-up" style="width:12px;height:12px;color:#2563EB;"></i>
            </div>
            <span style="color:#6B7280;font-size:0.75rem;">Monthly</span>
          </div>
          <p style="color:#111827;font-size:1.125rem;font-weight:700;margin:0;">$${monthly.toFixed(2)}</p>
        </div>
        <div class="stat-card">
          <div style="display:flex;align-items:center;gap:8px;margin-bottom:8px;">
            <div style="width:24px;height:24px;border-radius:6px;background:#F0FDF4;display:flex;align-items:center;justify-content:center;">
              <i data-lucide="credit-card" style="width:12px;height:12px;color:#16A34A;"></i>
            </div>
            <span style="color:#6B7280;font-size:0.75rem;">Yearly</span>
          </div>
          <p style="color:#111827;font-size:1.125rem;font-weight:700;margin:0;">$${yearly.toFixed(0)}</p>
        </div>
      </div>
      <div>
        <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:12px;">
          <h4 style="color:#111827;font-size:0.875rem;font-weight:700;margin:0;">Linked Services</h4>
          <span style="color:#9CA3AF;font-size:0.75rem;">${subs.length} active</span>
        </div>
        <div style="display:flex;flex-direction:column;gap:8px;">${subItems}</div>
      </div>
    </div>
    <div style="padding:20px;border-top:1px solid #E8EBF0;flex-shrink:0;">
      ${setPrimaryBtn}
      <div style="display:flex;gap:8px;">
        <button onclick="openEditModal('${card.id}')" style="flex:1;padding:10px;border-radius:12px;background:#F3F4F6;color:#374151;border:1px solid #E5E7EB;cursor:pointer;font-size:0.875rem;font-weight:600;font-family:inherit;display:flex;align-items:center;justify-content:center;gap:8px;transition:all 0.15s;" onmouseover="this.style.background='#E5E7EB'" onmouseout="this.style.background='#F3F4F6'">
          <i data-lucide="edit-2" style="width:14px;height:14px;"></i> Edit
        </button>
        <button onclick="openDeleteModal('${card.id}')" style="flex:1;padding:10px;border-radius:12px;border:1px solid #FECACA;color:#DC2626;background:#FFF5F5;cursor:pointer;font-size:0.875rem;font-weight:600;font-family:inherit;display:flex;align-items:center;justify-content:center;gap:8px;transition:all 0.15s;" onmouseover="this.style.background='#FEE2E2'" onmouseout="this.style.background='#FFF5F5'">
          <i data-lucide="trash-2" style="width:14px;height:14px;"></i> Delete
        </button>
      </div>
    </div>`;
}

function infoRow(label, valueHtml) {
  return `<div style="display:flex;align-items:center;justify-content:space-between;"><span style="color:#6B7280;font-size:0.875rem;">${label}</span><span style="color:#111827;font-size:0.875rem;font-weight:500;">${valueHtml}</span></div>`;
}

// ─────────────────────────────────────────────
// ADD / EDIT MODAL
// ─────────────────────────────────────────────
let modalForm = { nickname:'', last4:'', brand:'visa', isPrimary:false, theme:'dark' };
let modalErrors = {};

function renderAddModal() {
  const isEdit = !!state.editCardId;
  const f = modalForm;

  const brandButtons = BRANDS.map(b => `
    <button type="button" onclick="setModalField('brand','${b}')" style="position:relative;display:flex;flex-direction:column;align-items:center;justify-content:center;gap:8px;padding:12px 8px;border-radius:12px;border:1px solid ${f.brand===b ? '#BBCC00' : '#E2E5EA'};background:${f.brand===b ? '#FAFFF0' : '#F8F9FB'};cursor:pointer;transition:all 0.15s;">
      <div style="height:24px;display:flex;align-items:center;">${brandIconSVG(b,'sm',false)}</div>
      <span style="color:#6B7280;font-size:0.75rem;font-weight:500;">${BRAND_LABELS[b]}</span>
      ${f.brand===b ? `<div style="position:absolute;top:6px;right:6px;width:16px;height:16px;border-radius:50%;background:#DEFF1A;display:flex;align-items:center;justify-content:center;"><i data-lucide="check" style="width:10px;height:10px;color:#111;"></i></div>` : ''}
    </button>`).join('');

  const themeButtons = THEMES.map(t => `
    <button type="button" onclick="setModalField('theme','${t.key}')" style="position:relative;flex:1;display:flex;flex-direction:column;align-items:center;gap:6px;padding:8px;border-radius:12px;border:1px solid ${f.theme===t.key ? '#BBCC00' : '#E2E5EA'};background:${f.theme===t.key ? '#FAFFF0' : '#F8F9FB'};cursor:pointer;transition:all 0.15s;">
      <div style="width:32px;height:32px;border-radius:8px;background:${t.color};"></div>
      <span style="font-size:10px;color:#9CA3AF;">${t.label}</span>
      ${f.theme===t.key ? `<div style="position:absolute;top:4px;right:4px;width:12px;height:12px;border-radius:50%;background:#DEFF1A;display:flex;align-items:center;justify-content:center;"><i data-lucide="check" style="width:8px;height:8px;color:#111;"></i></div>` : ''}
    </button>`).join('');

  const previewCard = { nickname: f.nickname || 'My Card', last4: f.last4 || '0000', brand: f.brand, isPrimary: f.isPrimary, theme: f.theme };

  return `
    <div class="backdrop" id="add-modal-backdrop" onclick="handleBackdropClick(event,'add-modal-backdrop')">
      <div class="modal fade-in" style="max-width:680px;">
        <div style="display:flex;align-items:center;justify-content:space-between;padding:20px 24px;border-bottom:1px solid #E8EBF0;">
          <div>
            <h2 style="color:#111827;font-size:1.25rem;font-weight:700;margin:0;">${isEdit ? 'Edit Card' : 'Add New Card'}</h2>
            <p style="color:#9CA3AF;font-size:0.875rem;margin:4px 0 0;">${isEdit ? 'Update your card details' : 'Add a payment card to your account'}</p>
          </div>
          <button onclick="closeAddModal()" style="width:36px;height:36px;border-radius:50%;background:#F3F4F6;border:1px solid #E5E7EB;cursor:pointer;display:flex;align-items:center;justify-content:center;color:#6B7280;transition:all 0.15s;" onmouseover="this.style.background='#E5E7EB';this.style.color='#111827'" onmouseout="this.style.background='#F3F4F6';this.style.color='#6B7280'">
            <i data-lucide="x" style="width:16px;height:16px;"></i>
          </button>
        </div>
        <form onsubmit="handleModalSubmit(event)">
          <div style="padding:24px;">
            <div style="display:grid;grid-template-columns:1fr 1fr;gap:24px;">
              <!-- Left: Form -->
              <div style="display:flex;flex-direction:column;gap:20px;">
                <div>
                  <label style="display:block;color:#374151;font-size:0.875rem;font-weight:600;margin-bottom:8px;">Card Nickname</label>
                  <input type="text" id="modal-nickname" value="${escHtml(f.nickname)}" oninput="setModalField('nickname',this.value)" placeholder='e.g. "Work Amex"'
                    style="width:100%;background:#F8F9FB;border:1px solid ${modalErrors.nickname ? '#FCA5A5' : '#E2E5EA'};border-radius:12px;padding:12px 16px;color:#111827;outline:none;font-size:0.875rem;font-family:inherit;transition:all 0.15s;box-sizing:border-box;"
                    onfocus="this.style.borderColor='#BBCC00';this.style.background='#FFFFF8';this.style.boxShadow='0 0 0 3px rgba(222,255,26,0.2)'"
                    onblur="this.style.borderColor='${modalErrors.nickname ? '#FCA5A5' : '#E2E5EA'}';this.style.background='#F8F9FB';this.style.boxShadow='none'" />
                  ${modalErrors.nickname ? `<p style="display:flex;align-items:center;gap:4px;color:#DC2626;font-size:0.75rem;margin:6px 0 0;"><i data-lucide="alert-circle" style="width:12px;height:12px;"></i>${modalErrors.nickname}</p>` : ''}
                </div>
                <div>
                  <label style="display:block;color:#374151;font-size:0.875rem;font-weight:600;margin-bottom:8px;">Last 4 Digits</label>
                  <input type="text" id="modal-last4" value="${escHtml(f.last4)}" oninput="handleLast4Input(this.value)" placeholder="1234" maxlength="4" inputmode="numeric"
                    class="mono" style="width:100%;background:#F8F9FB;border:1px solid ${modalErrors.last4 ? '#FCA5A5' : '#E2E5EA'};border-radius:12px;padding:12px 16px;color:#111827;outline:none;font-size:1rem;letter-spacing:0.2em;transition:all 0.15s;box-sizing:border-box;"
                    onfocus="this.style.borderColor='#BBCC00';this.style.background='#FFFFF8';this.style.boxShadow='0 0 0 3px rgba(222,255,26,0.2)'"
                    onblur="this.style.borderColor='${modalErrors.last4 ? '#FCA5A5' : '#E2E5EA'}';this.style.background='#F8F9FB';this.style.boxShadow='none'" />
                  ${modalErrors.last4 ? `<p style="display:flex;align-items:center;gap:4px;color:#DC2626;font-size:0.75rem;margin:6px 0 0;"><i data-lucide="alert-circle" style="width:12px;height:12px;"></i>${modalErrors.last4}</p>` : ''}
                  ${!modalErrors.last4 && f.last4.length > 0 && f.last4.length < 4 ? `<p style="color:#9CA3AF;font-size:0.75rem;margin:6px 0 0;">${4-f.last4.length} more digit${f.last4.length!==3?'s':''} needed</p>` : ''}
                </div>
                <div>
                  <label style="display:block;color:#374151;font-size:0.875rem;font-weight:600;margin-bottom:8px;">Card Brand</label>
                  <div style="display:grid;grid-template-columns:repeat(3,1fr);gap:8px;">${brandButtons}</div>
                </div>
                <div>
                  <label style="display:block;color:#374151;font-size:0.875rem;font-weight:600;margin-bottom:8px;">Card Theme</label>
                  <div style="display:flex;gap:8px;">${themeButtons}</div>
                </div>
                <div style="display:flex;align-items:center;justify-content:space-between;padding:16px;background:#F8F9FB;border-radius:12px;border:1px solid #E2E5EA;">
                  <div>
                    <p style="color:#111827;font-size:0.875rem;font-weight:600;margin:0;">Set as Primary Card</p>
                    <p style="color:#9CA3AF;font-size:0.75rem;margin:4px 0 0;">Default card for new subscriptions</p>
                  </div>
                  <div class="toggle-track" style="background:${f.isPrimary ? '#DEFF1A' : '#E5E7EB'};" onclick="togglePrimary()">
                    <div class="toggle-thumb" style="left:${f.isPrimary ? '26px' : '2px'};"></div>
                  </div>
                </div>
              </div>
              <!-- Right: Preview -->
              <div>
                <label style="display:block;color:#374151;font-size:0.875rem;font-weight:600;margin-bottom:12px;">Live Preview</label>
                <div id="card-preview">${cardVisualHTML(previewCard, false)}</div>
                <div style="margin-top:16px;padding:16px;background:#F8F9FB;border-radius:12px;border:1px solid #E2E5EA;display:flex;flex-direction:column;gap:8px;">
                  ${previewRow('Brand', BRAND_LABELS[f.brand] || 'Visa')}
                  ${previewRow('Number', `<span class="mono">•••• ${f.last4 || '0000'}</span>`)}
                  ${previewRow('Nickname', f.nickname || '—')}
                  ${previewRow('Primary', `<span style="color:${f.isPrimary ? '#7A8C00' : '#9CA3AF'};font-weight:600;">${f.isPrimary ? 'Yes' : 'No'}</span>`)}
                </div>
              </div>
            </div>
          </div>
          <div style="padding:0 24px 24px;display:flex;gap:12px;">
            <button type="button" onclick="closeAddModal()" style="flex:1;padding:12px;border-radius:12px;border:1px solid #E2E5EA;color:#6B7280;background:#F3F4F6;cursor:pointer;font-size:0.875rem;font-weight:600;font-family:inherit;transition:all 0.15s;" onmouseover="this.style.background='#E5E7EB';this.style.color='#111827'" onmouseout="this.style.background='#F3F4F6';this.style.color='#6B7280'">Cancel</button>
            <button type="submit" id="modal-submit-btn" style="flex:1;padding:12px;border-radius:12px;background:#DEFF1A;color:#111;border:none;cursor:pointer;font-size:0.875rem;font-weight:700;font-family:inherit;transition:background 0.15s;" onmouseover="this.style.background='#CCEE00'" onmouseout="this.style.background='#DEFF1A'">${isEdit ? 'Save Changes' : 'Add Card'}</button>
          </div>
        </form>
      </div>
    </div>`;
}

function previewRow(label, valHtml) {
  return `<div style="display:flex;align-items:center;justify-content:space-between;font-size:0.875rem;"><span style="color:#6B7280;">${label}</span><span style="color:#111827;font-weight:500;">${valHtml}</span></div>`;
}

// ─────────────────────────────────────────────
// DELETE MODAL
// ─────────────────────────────────────────────
let deleteStep = 'warn';
let moveToCardId = '';

function renderDeleteModal() {
  const card = state.cards.find(c => String(c.id) === String(state.deleteCardId));
  if (!card) return '';
  const subs = getCardSubs(card.id);
  const otherCards = state.cards.filter(c => c.id !== card.id);
  const hasSubs = subs.length > 0;

  const warnContent = `
    <p style="color:#6B7280;font-size:0.875rem;margin:0 0 16px;">You are about to delete <span style="color:#111827;font-weight:600;">"${escHtml(card.nickname)}"</span> (•••• ${card.last4}).</p>
    ${hasSubs ? `
      <div style="background:#FFFBEB;border:1px solid #FDE68A;border-radius:12px;padding:16px;margin-bottom:16px;">
        <div style="display:flex;align-items:flex-start;gap:12px;">
          <i data-lucide="alert-triangle" style="width:16px;height:16px;color:#D97706;flex-shrink:0;margin-top:2px;"></i>
          <div>
            <p style="color:#92400E;font-size:0.875rem;margin:0 0 8px;font-weight:600;">This card has ${subs.length} active subscription${subs.length!==1?'s':''} linked:</p>
            ${subs.map(s => `<div style="display:flex;align-items:center;gap:8px;color:#78350F;font-size:0.75rem;margin-bottom:4px;"><div style="width:8px;height:8px;border-radius:50%;background:${s.color};flex-shrink:0;"></div>${s.name} — $${s.monthlyPrice}/mo</div>`).join('')}
          </div>
        </div>
      </div>` : ''}
    <div style="display:flex;gap:12px;">
      <button onclick="closeDeleteModal()" style="flex:1;padding:12px;border-radius:12px;border:1px solid #E2E5EA;color:#6B7280;background:#F3F4F6;cursor:pointer;font-size:0.875rem;font-weight:600;font-family:inherit;transition:all 0.15s;" onmouseover="this.style.background='#E5E7EB'" onmouseout="this.style.background='#F3F4F6'">Cancel</button>
      ${hasSubs
        ? `<button onclick="setDeleteStep('move')" style="flex:1;padding:12px;border-radius:12px;background:#DEFF1A;color:#111;border:none;cursor:pointer;font-size:0.875rem;font-weight:700;font-family:inherit;display:flex;align-items:center;justify-content:center;gap:8px;transition:background 0.15s;" onmouseover="this.style.background='#CCEE00'" onmouseout="this.style.background='#DEFF1A'">Move & Delete <i data-lucide="arrow-right" style="width:14px;height:14px;"></i></button>`
        : `<button onclick="confirmDelete()" style="flex:1;padding:12px;border-radius:12px;background:#DC2626;color:white;border:none;cursor:pointer;font-size:0.875rem;font-weight:600;font-family:inherit;transition:background 0.15s;" onmouseover="this.style.background='#B91C1C'" onmouseout="this.style.background='#DC2626'">Delete Card</button>`}
    </div>`;

  const moveContent = `
    <p style="color:#6B7280;font-size:0.875rem;margin:0 0 16px;">Move all ${subs.length} subscription${subs.length!==1?'s':''} to another card before deleting.</p>
    ${otherCards.length === 0
      ? `<div style="background:#F8F9FB;border-radius:12px;padding:16px;margin-bottom:16px;text-align:center;border:1px solid #E2E5EA;"><p style="color:#6B7280;font-size:0.875rem;margin:0;">No other cards available.</p><p style="color:#9CA3AF;font-size:0.75rem;margin:4px 0 0;">Add another card first or delete without moving.</p></div>`
      : `<div style="display:flex;flex-direction:column;gap:8px;margin-bottom:16px;">${otherCards.map(c => `
          <button type="button" onclick="setMoveTarget('${c.id}')" style="display:flex;align-items:center;gap:12px;padding:12px;border-radius:12px;border:1px solid ${moveToCardId===c.id ? '#BBCC00' : '#E2E5EA'};background:${moveToCardId===c.id ? '#FAFFF0' : '#F8F9FB'};cursor:pointer;text-align:left;transition:all 0.15s;width:100%;">
            <div style="width:32px;height:32px;border-radius:8px;background:#E5E7EB;display:flex;align-items:center;justify-content:center;font-size:0.75rem;color:#4B5563;font-family:'JetBrains Mono',monospace;">${c.last4}</div>
            <div style="flex:1;">
              <p style="color:#111827;font-size:0.875rem;font-weight:600;margin:0;">${c.nickname}</p>
              <p style="color:#9CA3AF;font-size:0.75rem;margin:0;">•••• ${c.last4}</p>
            </div>
            ${c.isPrimary ? `<span style="font-size:10px;color:#7A8C00;font-weight:700;border:1px solid #BBCC00;background:#FAFFF0;border-radius:9999px;padding:2px 8px;">Primary</span>` : ''}
          </button>`).join('')}</div>`}
    <div style="display:flex;gap:12px;">
      <button onclick="confirmDelete()" style="flex:1;padding:12px;border-radius:12px;border:1px solid #FECACA;color:#DC2626;background:#FFF5F5;cursor:pointer;font-size:0.875rem;font-weight:600;font-family:inherit;transition:all 0.15s;" onmouseover="this.style.background='#FEE2E2'" onmouseout="this.style.background='#FFF5F5'">Delete Anyway</button>
      <button onclick="confirmMoveAndDelete()" ${!moveToCardId ? 'disabled' : ''} style="flex:1;padding:12px;border-radius:12px;background:${moveToCardId ? '#DEFF1A' : '#F3F4F6'};color:${moveToCardId ? '#111' : '#9CA3AF'};border:none;cursor:${moveToCardId ? 'pointer' : 'not-allowed'};font-size:0.875rem;font-weight:700;font-family:inherit;transition:all 0.15s;">Move & Delete</button>
    </div>`;

  return `
    <div class="backdrop" id="delete-modal-backdrop" onclick="handleBackdropClick(event,'delete-modal-backdrop')">
      <div class="modal fade-in" style="max-width:420px;">
        <div style="display:flex;align-items:center;justify-content:space-between;padding:20px 24px;border-bottom:1px solid #E8EBF0;">
          <div style="display:flex;align-items:center;gap:12px;">
            <div style="width:36px;height:36px;border-radius:50%;background:#FEF2F2;border:1px solid #FECACA;display:flex;align-items:center;justify-content:center;">
              <i data-lucide="alert-triangle" style="width:16px;height:16px;color:#DC2626;"></i>
            </div>
            <h2 style="color:#111827;font-size:1.125rem;font-weight:700;margin:0;">${deleteStep==='warn' ? 'Delete Card' : 'Move Subscriptions'}</h2>
          </div>
          <button onclick="closeDeleteModal()" style="width:36px;height:36px;border-radius:50%;background:#F3F4F6;border:1px solid #E5E7EB;cursor:pointer;display:flex;align-items:center;justify-content:center;color:#6B7280;transition:all 0.15s;" onmouseover="this.style.background='#E5E7EB'" onmouseout="this.style.background='#F3F4F6'">
            <i data-lucide="x" style="width:16px;height:16px;"></i>
          </button>
        </div>
        <div style="padding:24px;">
          ${deleteStep === 'warn' ? warnContent : moveContent}
        </div>
      </div>
    </div>`;
}

// ─────────────────────────────────────────────
// EVENT HANDLERS
// ─────────────────────────────────────────────
function escHtml(str) {
  return String(str).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
}

function showApiError(err) {
  const fallback = 'Something went wrong. Please try again.';
  const message = (err && err.message) ? err.message : fallback;
  window.alert(message);
}

function handleCardClick(cardId) { state.selectedCardId = state.selectedCardId === String(cardId) ? null : String(cardId); renderApp(); }
function closeDetailPanel() { state.selectedCardId = null; renderApp(); }
function handleSearch(val) { state.search = val; renderApp(); }

function openAddModal() {
  modalForm = { nickname:'', last4:'', brand:'visa', isPrimary:false, theme:'dark' };
  modalErrors = {};
  state.addModalOpen = true;
  state.editCardId = null;
  renderApp();
}
function openEditModal(cardId) {
  const card = state.cards.find(c => String(c.id) === String(cardId));
  if (!card) return;
  modalForm = { nickname: card.nickname, last4: card.last4, brand: card.brand, isPrimary: card.isPrimary, theme: card.theme };
  modalErrors = {};
  state.addModalOpen = true;
  state.editCardId = String(cardId);
  renderApp();
}
function closeAddModal() { state.addModalOpen = false; state.editCardId = null; renderApp(); }
function setModalField(field, value) { modalForm[field] = value; if (modalErrors[field]) modalErrors[field] = ''; renderApp(); }
function handleLast4Input(val) { const d = val.replace(/\D/g,'').slice(0,4); modalForm.last4 = d; if (modalErrors.last4) modalErrors.last4 = ''; renderApp(); }
function togglePrimary() { modalForm.isPrimary = !modalForm.isPrimary; renderApp(); }

async function handleModalSubmit(e) {
  e.preventDefault();
  const errs = {};
  if (!modalForm.nickname.trim()) errs.nickname = 'Card nickname is required';
  else if (modalForm.nickname.length > 30) errs.nickname = 'Nickname must be 30 characters or fewer';
  if (!modalForm.last4) errs.last4 = 'Last 4 digits are required';
  else if (!/^\d{4}$/.test(modalForm.last4)) errs.last4 = 'Must be exactly 4 digits';
  if (Object.keys(errs).length > 0) { modalErrors = errs; renderApp(); return; }

  const btn = document.getElementById('modal-submit-btn');
  if (btn) {
    btn.disabled = true;
    btn.innerHTML = '<i data-lucide="check" style="width:16px;height:16px;"></i> ' + (state.editCardId ? 'Updated!' : 'Added!');
    btn.style.background = '#16A34A';
    btn.style.color = 'white';
    lucide.createIcons();
  }

  try {
    const payload = {
      nickname: modalForm.nickname.trim(),
      last4: modalForm.last4,
      brand: modalForm.brand,
      isPrimary: modalForm.isPrimary,
      theme: modalForm.theme,
    };
    const url = state.editCardId
      ? apiUrlForCard(API.update, state.editCardId)
      : API.create;
    const response = await postJson(url, payload);
    hydrateState(response.state, { keepSearch: true, keepSelected: true });
    state.addModalOpen = false;
    state.editCardId = null;
    modalErrors = {};
    renderApp();
  } catch (err) {
    if (err && err.errors) {
      modalErrors = { ...modalErrors, ...err.errors };
      renderApp();
    } else {
      showApiError(err);
    }
  } finally {
    if (btn) btn.disabled = false;
  }
}

function handleBackdropClick(e, id) { if (e.target.id === id) { closeAddModal(); closeDeleteModal(); } }
function openDeleteModal(cardId) { state.deleteCardId = String(cardId); deleteStep = 'warn'; moveToCardId = ''; renderApp(); }
function closeDeleteModal() { state.deleteCardId = null; deleteStep = 'warn'; moveToCardId = ''; renderApp(); }
function setDeleteStep(step) { deleteStep = step; renderApp(); }
function setMoveTarget(cardId) { moveToCardId = String(cardId); renderApp(); }

async function confirmDelete() {
  if (!state.deleteCardId) {
    return;
  }

  try {
    const response = await postJson(apiUrlForCard(API.remove, state.deleteCardId), {});
    hydrateState(response.state, { keepSearch: true, keepSelected: true });
    closeDeleteModal();
  } catch (err) {
    showApiError(err);
  }
}
async function confirmMoveAndDelete() {
  if (!moveToCardId || !state.deleteCardId) return;

  try {
    const response = await postJson(apiUrlForCard(API.remove, state.deleteCardId), {
      move_to_card_id: moveToCardId,
    });
    hydrateState(response.state, { keepSearch: true, keepSelected: true });
    closeDeleteModal();
  } catch (err) {
    showApiError(err);
  }
}

async function handleSetPrimary(cardId) {
  try {
    const response = await postJson(apiUrlForCard(API.setPrimary, cardId), {});
    hydrateState(response.state, { keepSearch: true, keepSelected: true });
    state.selectedCardId = String(cardId);
    renderApp();
  } catch (err) {
    showApiError(err);
  }
}

function bindModalEvents() {
  document.onkeydown = (e) => {
    if (e.key === 'Escape') {
      if (state.addModalOpen) closeAddModal();
      else if (state.deleteCardId) closeDeleteModal();
    }
  };
}

function applyInitialModalState() {
  if (state.addModalOpen) {
    if (state.editCardId) {
      const card = state.cards.find(c => String(c.id) === String(state.editCardId));
      if (card) {
        modalForm = {
          nickname: card.nickname,
          last4: card.last4,
          brand: card.brand,
          isPrimary: card.isPrimary,
          theme: card.theme,
        };
      } else {
        state.addModalOpen = false;
        state.editCardId = null;
      }
    } else {
      modalForm = { nickname:'', last4:'', brand:'visa', isPrimary:false, theme:'dark' };
    }
  }
}

applyInitialModalState();
renderApp();

