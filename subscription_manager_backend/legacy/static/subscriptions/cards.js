
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
      cards: Array.isArray(parsed.cards) ? parsed.cards.map(normalizeCard) : [],
      subscriptions: Array.isArray(parsed.subscriptions)
        ? parsed.subscriptions.map(normalizeSubscription)
        : [],
      selectedCardId: parsed.selectedCardId ? String(parsed.selectedCardId) : null,
      editCardId: parsed.editCardId ? String(parsed.editCardId) : null,
      deleteCardId: parsed.deleteCardId ? String(parsed.deleteCardId) : null,
    };
  } catch (err) {
    return { ...DEFAULT_STATE };
  }
}

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
const BRAND_LOGO_URLS = {
  visa: 'https://cdn.jsdelivr.net/gh/selfhst/icons@main/svg/visa.svg',
  mastercard: 'https://cdn.jsdelivr.net/gh/selfhst/icons@main/svg/mastercard.svg',
  amex: 'https://cdn.jsdelivr.net/gh/selfhst/icons@main/svg/american-express.svg',
  discover: 'https://cdn.jsdelivr.net/gh/selfhst/icons@main/svg/discover-card.svg',
};
const ICON_PATHS = {
  plus: '<line x1="12" y1="5" x2="12" y2="19"></line><line x1="5" y1="12" x2="19" y2="12"></line>',
  'credit-card': '<rect x="2" y="5" width="20" height="14" rx="2"></rect><line x1="2" y1="10" x2="22" y2="10"></line>',
  'trending-up': '<polyline points="22 7 13.5 15.5 8.5 10.5 2 17"></polyline><polyline points="16 7 22 7 22 13"></polyline>',
  star: '<polygon points="12 2 15.09 8.26 22 9.27 17 14.14 18.18 21.02 12 17.77 5.82 21.02 7 14.14 2 9.27 8.91 8.26 12 2"></polygon>',
  search: '<circle cx="11" cy="11" r="8"></circle><line x1="21" y1="21" x2="16.65" y2="16.65"></line>',
  x: '<line x1="18" y1="6" x2="6" y2="18"></line><line x1="6" y1="6" x2="18" y2="18"></line>',
  'edit-2': '<path d="M17 3a2.828 2.828 0 1 1 4 4L7 21l-4 1 1-4L17 3z"></path>',
  'trash-2': '<polyline points="3 6 5 6 21 6"></polyline><path d="M19 6l-1 14H6L5 6"></path><path d="M10 11v6"></path><path d="M14 11v6"></path><path d="M9 6V4h6v2"></path>',
  check: '<polyline points="20 6 9 17 4 12"></polyline>',
  'alert-circle': '<circle cx="12" cy="12" r="10"></circle><line x1="12" y1="8" x2="12" y2="12"></line><line x1="12" y1="16" x2="12.01" y2="16"></line>',
  'alert-triangle': '<path d="M10.29 3.86 1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"></path><line x1="12" y1="9" x2="12" y2="13"></line><line x1="12" y1="17" x2="12.01" y2="17"></line>',
  'arrow-right': '<line x1="5" y1="12" x2="19" y2="12"></line><polyline points="12 5 19 12 12 19"></polyline>',
};

const JCB_INLINE_SVG = `<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink" viewBox="0 0 432.37 324.5" style="width:100%;height:100%;display:block;"><defs><style>.a{fill:url(#a);}.b{fill:url(#b);}.c{fill:url(#c);}.d{fill:url(#d);}.e{fill:url(#e);}</style><linearGradient id="a" x1="148.19" y1="270.12" x2="213.35" y2="270.12" gradientTransform="matrix(2.05, 0, 0, -2.05, -4.47, 736.29)" gradientUnits="userSpaceOnUse"><stop offset="0" stop-color="#007940"/><stop offset="0.23" stop-color="#00873f"/><stop offset="0.74" stop-color="#40a737"/><stop offset="1" stop-color="#5cb531"/></linearGradient><linearGradient id="b" x1="148.18" y1="280.2" x2="213.29" y2="280.2" xlink:href="#a"/><linearGradient id="c" x1="148.18" y1="291.29" x2="213.35" y2="291.29" xlink:href="#a"/><linearGradient id="d" x1="2.3" y1="280.27" x2="68.47" y2="280.27" gradientTransform="matrix(2.05, 0, 0, -2.05, -4.47, 736.29)" gradientUnits="userSpaceOnUse"><stop offset="0" stop-color="#1f286f"/><stop offset="0.48" stop-color="#004e94"/><stop offset="0.83" stop-color="#0066b1"/><stop offset="1" stop-color="#006fbc"/></linearGradient><linearGradient id="e" x1="74.89" y1="280.13" x2="139.16" y2="280.13" gradientTransform="matrix(2.05, 0, 0, -2.05, -4.47, 736.29)" gradientUnits="userSpaceOnUse"><stop offset="0" stop-color="#6c2c2f"/><stop offset="0.17" stop-color="#882730"/><stop offset="0.57" stop-color="#be1833"/><stop offset="0.86" stop-color="#dc0436"/><stop offset="1" stop-color="#e60039"/></linearGradient></defs><path class="a" d="M325.69,197h31.2c.89,0,3-.3,3.86-.3a13.92,13.92,0,0,0,11-14,14.41,14.41,0,0,0-11-14,15.52,15.52,0,0,0-3.86-.3h-31.2V197Z"/><path class="b" d="M353.32,0a54.09,54.09,0,0,0-54.08,54.08v56.17h76.37a31.36,31.36,0,0,1,5.35.29c17.24.9,30,9.81,30,25.26,0,12.19-8.61,22.59-24.66,24.67v.59c17.53,1.19,30.9,11,30.9,26.15,0,16.35-14.85,27-34.47,27h-83.8v110h79.35a54.09,54.09,0,0,0,54.08-54.08V0Z"/><path class="c" d="M367.89,139.37a12.65,12.65,0,0,0-11-12.78c-.59,0-2.08-.3-3-.3H325.69v26.15h28.23c.89,0,2.67,0,3-.29A12.66,12.66,0,0,0,367.89,139.37Z"/><path class="d" d="M54.38,0A54.08,54.08,0,0,0,.3,54.08V187.51c15.15,7.43,30.9,12.18,46.65,12.18,18.72,0,28.83-11.29,28.83-26.74V110h46.35v62.7c0,24.37-15.15,44.28-66.56,44.28A228,228,0,0,1,0,210.09V323.91H79.34a54.09,54.09,0,0,0,54.09-54.09V0Z"/><path class="e" d="M203.85,0a54.09,54.09,0,0,0-54.08,54.08v70.73c13.67-11.59,37.44-19,75.78-17.24,20.5.89,42.49,6.54,42.49,6.54V137c-11-5.64-24.07-10.7-41-11.89-29.12-2.08-46.65,12.19-46.65,37.15,0,25.26,17.53,39.52,46.65,37.14,16.94-1.18,30-6.53,41-11.88v22.88s-21.69,5.65-42.49,6.54c-38.34,1.78-62.11-5.65-75.78-17.24V324.5h79.34a54.08,54.08,0,0,0,54.08-54.08V0Z"/></svg>`;
const VALID_THEME_KEYS = new Set(THEMES.map(theme => theme.key));
const VALID_BRANDS = new Set(BRANDS);

function safeCssColor(rawValue, fallback = '#AFC0DE') {
  const value = String(rawValue || '').trim();
  if (/^#(?:[0-9a-fA-F]{3}|[0-9a-fA-F]{4}|[0-9a-fA-F]{6}|[0-9a-fA-F]{8})$/.test(value)) {
    return value;
  }
  return fallback;
}

function safeToken(rawValue) {
  return String(rawValue ?? '').replace(/[^A-Za-z0-9_-]/g, '');
}

function normalizeCard(rawCard = {}) {
  const brand = String(rawCard.brand || '').toLowerCase();
  const theme = String(rawCard.theme || '').toLowerCase();
  const last4 = String(rawCard.last4 || '').replace(/\D/g, '').slice(-4);

  return {
    id: safeToken(rawCard.id),
    nickname: String(rawCard.nickname || ''),
    last4: last4 || '0000',
    brand: VALID_BRANDS.has(brand) ? brand : 'visa',
    isPrimary: Boolean(rawCard.isPrimary),
    theme: VALID_THEME_KEYS.has(theme) ? theme : 'dark',
  };
}

function normalizeSubscription(rawSub = {}) {
  const baseColor = safeCssColor(rawSub.color, '#AFC0DE');
  const monthlyPrice = Number(rawSub.monthlyPrice);
  const daysLeft = rawSub.daysLeft == null ? NaN : Number(rawSub.daysLeft);

  return {
    id: safeToken(rawSub.id),
    name: String(rawSub.name || ''),
    monthlyPrice: Number.isFinite(monthlyPrice) ? monthlyPrice : 0,
    currency: /^[A-Z]{3}$/.test(rawSub.currency) ? rawSub.currency : "USD",
    billingCycle: String(rawSub.billingCycle || ''),
    cardId: safeToken(rawSub.cardId),
    color: baseColor,
    iconBg: safeCssColor(rawSub.iconBg, baseColor),
    iconLabel: String(rawSub.iconLabel || 'S').slice(0, 2),
    nextBillingDate: String(rawSub.nextBillingDate || ''),
    daysLeft: Number.isFinite(daysLeft) ? Math.max(0, Math.trunc(daysLeft)) : null,
    plan: String(rawSub.plan || ''),
  };
}

let state = parseBootstrapState();

function renderIcons(root = document) {
  const host = root && root.querySelectorAll ? root : document;
  const iconNodes = host.querySelectorAll('[data-lucide]');

  iconNodes.forEach((node) => {
    const iconName = node.getAttribute('data-lucide');
    const iconMarkup = ICON_PATHS[iconName];
    if (!iconMarkup) {
      return;
    }

    const svg = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
    svg.setAttribute('xmlns', 'http://www.w3.org/2000/svg');
    svg.setAttribute('viewBox', '0 0 24 24');
    svg.setAttribute('fill', 'none');
    svg.setAttribute('stroke', 'currentColor');
    svg.setAttribute('stroke-width', '2');
    svg.setAttribute('stroke-linecap', 'round');
    svg.setAttribute('stroke-linejoin', 'round');

    const style = node.getAttribute('style');
    if (style) {
      svg.setAttribute('style', style);
    }

    const className = node.getAttribute('class');
    if (className) {
      svg.setAttribute('class', className);
    }

    svg.innerHTML = iconMarkup;
    node.replaceWith(svg);
  });
}

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
    cards: Array.isArray(serverState.cards) ? serverState.cards.map(normalizeCard) : [],
    subscriptions: Array.isArray(serverState.subscriptions)
      ? serverState.subscriptions.map(normalizeSubscription)
      : [],
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
function formatMoney(amount, currency) {
  return new Intl.NumberFormat('en-US', { style: 'currency', currency }).format(amount);
}

function formatSpend(subscriptions, months = 1) {
  const totals = new Map();
  for (const sub of subscriptions) {
    totals.set(sub.currency, (totals.get(sub.currency) || 0) + sub.monthlyPrice * months);
  }
  return Array.from(totals, ([currency, amount]) => formatMoney(amount, currency)).join(' + ') || formatMoney(0, 'USD');
}
function primaryCard() { return state.cards.find(c => c.isPrimary); }

// ─────────────────────────────────────────────
// SVG BRAND ICONS
// ─────────────────────────────────────────────
function brandIconSVG(brand, size='md', onCard=true) {
  const px = size === 'sm' ? 24 : size === 'lg' ? 52 : size === 'xl' ? 88 : 36;
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

function brandSelectorLogoHTML(brand) {
  if (brand === 'jcb') {
    return `
      <span style="display:flex;align-items:center;justify-content:center;width:100%;height:100%;">
        <span style="display:block;width:78%;height:40px;">
          ${JCB_INLINE_SVG}
        </span>
      </span>
    `;
  }

  const logoUrl = BRAND_LOGO_URLS[brand];
  const alt = BRAND_LABELS[brand] || brand;
  if (!logoUrl) {
    return brandIconSVG(brand, 'md', false);
  }

  return `
    <img src="${logoUrl}" alt="${alt}" style="height:40px;width:auto;max-width:78%;max-height:40px;object-fit:contain;"
      onerror="this.style.display='none';this.nextElementSibling.style.display='flex';" />
    <span style="display:none;align-items:center;justify-content:center;width:100%;height:100%;">${brandIconSVG(brand, 'md', false)}</span>
  `;
}

function brandCardLogoHTML(brand, compact=false) {
  const logoHeight = compact ? 20 : 24;
  const fallback = brandIconSVG(brand, compact ? 'sm' : 'md', true);

  if (brand === 'jcb') {
    return `
      <span style="display:flex;align-items:center;justify-content:flex-end;height:${logoHeight}px;">
        <span style="display:block;width:${compact ? 38 : 48}px;height:${logoHeight}px;">
          ${JCB_INLINE_SVG}
        </span>
      </span>
    `;
  }

  const logoUrl = BRAND_LOGO_URLS[brand];
  const alt = BRAND_LABELS[brand] || brand;
  if (!logoUrl) {
    return fallback;
  }

  return `
    <span style="display:flex;align-items:center;justify-content:flex-end;height:${logoHeight}px;min-width:${compact ? 44 : 56}px;">
      <img src="${logoUrl}" alt="${alt}" style="height:${logoHeight}px;width:auto;max-width:${compact ? 56 : 72}px;object-fit:contain;display:block;"
        onerror="this.style.display='none';this.nextElementSibling.style.display='flex';" />
      <span style="display:none;align-items:center;justify-content:flex-end;height:100%;">${fallback}</span>
    </span>
  `;
}

// ─────────────────────────────────────────────
// CARD VISUAL HTML (cards stay dark — real credit cards are dark)
// ─────────────────────────────────────────────
function cardVisualHTML(card, isSelected=false, compact=false) {
  const safeTheme = VALID_THEME_KEYS.has(card.theme) ? card.theme : 'dark';
  const safeCardId = escHtml(card.id || '');
  const safeLast4 = escHtml(String(card.last4 || '0000').replace(/\D/g, '').slice(-4) || '0000');
  const safeNickname = escHtml(card.nickname || 'My Card');
  const safeBrand = VALID_BRANDS.has(card.brand) ? card.brand : 'visa';
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
    <div class="card-visual gradient-${safeTheme} ${selClass}" data-card-id="${safeCardId}" onclick="handleCardClick('${safeCardId}')">
      <div style="position:absolute;inset:0;background:linear-gradient(135deg,rgba(255,255,255,0.05),transparent);pointer-events:none;"></div>
      <div style="position:absolute;right:-32px;top:-32px;width:160px;height:160px;border-radius:50%;background:rgba(255,255,255,0.04);pointer-events:none;"></div>
      <div style="position:absolute;right:-16px;bottom:-48px;width:208px;height:208px;border-radius:50%;background:rgba(255,255,255,0.03);pointer-events:none;"></div>
      <div class="${p}" style="position:relative;height:100%;display:flex;flex-direction:column;justify-content:space-between;">
        <div style="display:flex;align-items:flex-start;justify-content:space-between;">
          <div class="chip-${safeTheme}" style="${chipW};border-radius:6px;box-shadow:inset 0 0 0 1px rgba(255,255,255,0.15);">
            <div style="width:100%;height:100%;border-radius:6px;overflow:hidden;opacity:0.3;">
              <div style="height:1px;background:rgba(0,0,0,0.4);margin-top:35%;"></div>
              <div style="height:1px;background:rgba(0,0,0,0.4);margin-top:25%;"></div>
            </div>
          </div>
          ${primaryBadge}
        </div>
        <div>
          <p class="mono" data-preview-last4="1" style="color:rgba(255,255,255,0.85);letter-spacing:0.2em;${numSize};">•••• •••• •••• ${safeLast4}</p>
        </div>
        <div style="display:flex;align-items:flex-end;justify-content:space-between;">
          <div>
            <p style="color:rgba(255,255,255,0.5);${labelSize};text-transform:uppercase;letter-spacing:0.1em;margin-bottom:2px;">Card Holder</p>
            <p data-preview-nickname="1" style="color:white;${nameSize};max-width:120px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;">${safeNickname}</p>
          </div>
          <div style="display:flex;align-items:flex-end;justify-content:flex-end;">${brandCardLogoHTML(safeBrand, compact)}</div>
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
  renderIcons(app);
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
  const monthly = formatSpend(state.subscriptions);
  const pc = primaryCard();
  const primaryNickname = pc ? escHtml(pc.nickname) : '—';
  const primaryLast4 = pc ? escHtml(pc.last4) : '';
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
        <p style="color:#111827;font-size:1.5rem;font-weight:700;margin:0;">${monthly}</p>
        <p style="color:#9CA3AF;font-size:0.75rem;margin:2px 0 0;">across all cards</p>
      </div>
      <div class="stat-card">
        <div style="display:flex;align-items:center;gap:8px;margin-bottom:8px;">
          <div style="width:28px;height:28px;border-radius:8px;background:#FEFCE8;display:flex;align-items:center;justify-content:center;">
            <i data-lucide="star" style="width:14px;height:14px;color:#CA8A04;fill:#CA8A04;"></i>
          </div>
          <span style="color:#6B7280;font-size:0.75rem;font-weight:500;">Primary Card</span>
        </div>
        <p style="color:#111827;font-size:0.875rem;font-weight:600;margin:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;">${primaryNickname}</p>
        <p style="color:#9CA3AF;font-size:0.75rem;margin:2px 0 0;">${pc ? `•••• ${primaryLast4}` : 'None set'}</p>
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
  const query = String(state.search || '').toLowerCase();
  const filtered = state.cards.filter(c =>
    String(c.nickname || '').toLowerCase().includes(query) ||
    (BRAND_LABELS[c.brand] || 'Visa').toLowerCase().includes(query) ||
    String(c.last4 || '').includes(query)
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
    const spend = formatSpend(subs);
    const isSelected = String(state.selectedCardId) === String(card.id);

    const subsChips = isSelected && subs.length > 0 ? `
      <div style="margin-top:10px;display:flex;flex-wrap:wrap;gap:6px;">
        ${subs.map(sub => {
          const chipColor = safeCssColor(sub.color, '#AFC0DE');
          const chipBg = chipColor.length === 7 ? `${chipColor}CC` : chipColor;
          const subName = escHtml(sub.name);
          return `<span style="font-size:10px;padding:4px 10px;border-radius:9999px;color:#111;font-weight:600;background:${chipBg};">${subName}</span>`;
        }).join('')}
      </div>` : '';

    const miniIcons = subs.length > 0 ? `
      <div style="display:flex;">
        ${subs.slice(0,3).map(sub => `
          <div title="${escHtml(sub.name)}" style="width:20px;height:20px;border-radius:50%;border:2px solid #F0F2F6;background:${safeCssColor(sub.color, '#AFC0DE')};display:flex;align-items:center;justify-content:center;font-size:8px;color:#111;margin-left:-4px;font-weight:600;">${escHtml((sub.iconLabel || 'S').charAt(0) || 'S')}</div>
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
            ${subs.length > 0 ? `<div style="display:flex;align-items:center;gap:4px;font-size:0.75rem;color:#6B7280;font-weight:500;"><i data-lucide="trending-up" style="width:11px;height:11px;"></i><span>${spend}/mo</span></div>` : ''}
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
  const monthly = formatSpend(subs);
  const yearly = formatSpend(subs, 12);

  const subItems = subs.length === 0
    ? `<div style="background:#F8F9FB;border-radius:16px;padding:24px;border:1px solid #E8EBF0;text-align:center;"><i data-lucide="credit-card" style="width:24px;height:24px;color:#D1D5DB;margin:0 auto 8px;display:block;"></i><p style="color:#9CA3AF;font-size:0.875rem;margin:0;">No subscriptions linked</p></div>`
    : subs.map(sub => {
      const rowColor = safeCssColor(sub.color, '#AFC0DE');
      const rowBg = rowColor.length === 7 ? `${rowColor}20` : rowColor;
      const iconBg = safeCssColor(sub.iconBg, rowColor);
      const label = escHtml(sub.iconLabel || 'S');
      const name = escHtml(sub.name);
      const plan = escHtml(sub.plan);
      const monthlyPrice = formatMoney(sub.monthlyPrice, sub.currency);
      const renewalLabel = sub.daysLeft === null ? 'No renewal scheduled' : `${sub.daysLeft}d left`;

      return `
      <div style="display:flex;align-items:center;gap:12px;padding:12px;border-radius:12px;border:1px solid #E8EBF0;background:${rowBg};transition:border-color 0.15s;box-shadow:0 1px 3px rgba(0,0,0,0.04);" onmouseover="this.style.borderColor='#C4C9D4'" onmouseout="this.style.borderColor='#E8EBF0'">
        <div style="width:40px;height:40px;border-radius:12px;background:${iconBg};display:flex;align-items:center;justify-content:center;font-size:0.875rem;flex-shrink:0;border:1px solid rgba(0,0,0,0.08);">${label}</div>
        <div style="flex:1;min-width:0;">
          <p style="color:#111827;font-size:0.875rem;font-weight:500;margin:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;">${name}</p>
          <p style="color:#9CA3AF;font-size:0.75rem;margin:0;">${plan}</p>
        </div>
        <div style="text-align:right;flex-shrink:0;">
          <p style="color:#111827;font-size:0.875rem;font-weight:600;margin:0;">${monthlyPrice}/mo</p>
          <p style="color:#9CA3AF;font-size:0.75rem;margin:0;">${renewalLabel}</p>
        </div>
      </div>`;
    }).join('');

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
  const safeCardId = escHtml(card.id || '');
  const safeNickname = escHtml(card.nickname || '');
  const safeLast4 = escHtml(card.last4 || '0000');
  const safeBrand = escHtml(BRAND_LABELS[card.brand] || 'Visa');
  const setPrimaryBtn = !card.isPrimary ? `
    <button onclick="handleSetPrimary('${safeCardId}')" style="width:100%;padding:10px;border-radius:12px;border:1px solid #BBCC00;color:#7A8C00;background:#FAFFF0;cursor:pointer;font-size:0.875rem;font-family:inherit;font-weight:600;display:flex;align-items:center;justify-content:center;gap:8px;margin-bottom:8px;transition:all 0.15s;" onmouseover="this.style.background='#F0FF90'" onmouseout="this.style.background='#FAFFF0'">
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
        ${infoRow('Nickname', safeNickname)}
        ${infoRow('Number', `<span class="mono">•••• •••• •••• ${safeLast4}</span>`)}
        ${infoRow('Brand', safeBrand)}
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
          <p style="color:#111827;font-size:1.125rem;font-weight:700;margin:0;">${monthly}</p>
        </div>
        <div class="stat-card">
          <div style="display:flex;align-items:center;gap:8px;margin-bottom:8px;">
            <div style="width:24px;height:24px;border-radius:6px;background:#F0FDF4;display:flex;align-items:center;justify-content:center;">
              <i data-lucide="credit-card" style="width:12px;height:12px;color:#16A34A;"></i>
            </div>
            <span style="color:#6B7280;font-size:0.75rem;">Yearly</span>
          </div>
          <p style="color:#111827;font-size:1.125rem;font-weight:700;margin:0;">${yearly}</p>
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
        <button onclick="openEditModal('${safeCardId}')" style="flex:1;padding:10px;border-radius:12px;background:#F3F4F6;color:#374151;border:1px solid #E5E7EB;cursor:pointer;font-size:0.875rem;font-weight:600;font-family:inherit;display:flex;align-items:center;justify-content:center;gap:8px;transition:all 0.15s;" onmouseover="this.style.background='#E5E7EB'" onmouseout="this.style.background='#F3F4F6'">
          <i data-lucide="edit-2" style="width:14px;height:14px;"></i> Edit
        </button>
        <button onclick="openDeleteModal('${safeCardId}')" style="flex:1;padding:10px;border-radius:12px;border:1px solid #FECACA;color:#DC2626;background:#FFF5F5;cursor:pointer;font-size:0.875rem;font-weight:600;font-family:inherit;display:flex;align-items:center;justify-content:center;gap:8px;transition:all 0.15s;" onmouseover="this.style.background='#FEE2E2'" onmouseout="this.style.background='#FFF5F5'">
          <i data-lucide="trash-2" style="width:14px;height:14px;"></i> Delete
        </button>
      </div>
    </div>`;
}

function infoRow(label, valueHtml) {
  return `<div style="display:flex;align-items:center;justify-content:space-between;"><span style="color:#6B7280;font-size:0.875rem;">${escHtml(label)}</span><span style="color:#111827;font-size:0.875rem;font-weight:500;">${valueHtml}</span></div>`;
}

// ─────────────────────────────────────────────
// ADD / EDIT MODAL
// ─────────────────────────────────────────────
let modalForm = { nickname:'', last4:'', brand:'visa', isPrimary:false, theme:'dark' };
let modalErrors = {};

function renderAddModal() {
  const isEdit = !!state.editCardId;
  const f = modalForm;
  const digitsNeeded = 4 - f.last4.length;

  const brandButtons = BRANDS.map(b => `
    <button type="button" onclick="setModalField('brand','${b}')" style="position:relative;display:flex;align-items:center;justify-content:center;padding:10px;border-radius:12px;border:1px solid ${f.brand===b ? '#BBCC00' : '#E2E5EA'};background:${f.brand===b ? '#FAFFF0' : '#F8F9FB'};cursor:pointer;transition:all 0.15s;min-height:88px;">
      <div style="width:100%;height:100%;display:flex;align-items:center;justify-content:center;padding:6px;">${brandSelectorLogoHTML(b)}</div>
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
      <div class="modal fade-in" style="max-width:680px;max-height:calc(100vh - 1rem);overflow:hidden;">
        <div style="display:flex;align-items:center;justify-content:space-between;padding:14px 22px;border-bottom:1px solid #E8EBF0;">
          <div>
            <h2 style="color:#111827;font-size:1.25rem;font-weight:700;margin:0;">${isEdit ? 'Edit Card' : 'Add New Card'}</h2>
            <p style="color:#9CA3AF;font-size:0.875rem;margin:2px 0 0;">${isEdit ? 'Update your card details' : 'Add a payment card to your account'}</p>
          </div>
          <button onclick="closeAddModal()" style="width:36px;height:36px;border-radius:50%;background:#F3F4F6;border:1px solid #E5E7EB;cursor:pointer;display:flex;align-items:center;justify-content:center;color:#6B7280;transition:all 0.15s;" onmouseover="this.style.background='#E5E7EB';this.style.color='#111827'" onmouseout="this.style.background='#F3F4F6';this.style.color='#6B7280'">
            <i data-lucide="x" style="width:16px;height:16px;"></i>
          </button>
        </div>
        <form onsubmit="handleModalSubmit(event)">
          <div style="padding:20px 22px 18px;">
            <div style="display:grid;grid-template-columns:1fr 1fr;gap:20px;">
              <!-- Left: Form -->
              <div style="display:flex;flex-direction:column;gap:18px;">
                <div>
                  <label style="display:block;color:#374151;font-size:0.875rem;font-weight:600;margin-bottom:8px;">Card Nickname</label>
                  <input type="text" id="modal-nickname" value="${escHtml(f.nickname)}" oninput="setModalField('nickname',this.value)" placeholder='e.g. "Work Amex"'
                    style="width:100%;background:#F8F9FB;border:1px solid ${modalErrors.nickname ? '#FCA5A5' : '#E2E5EA'};border-radius:12px;padding:12px 16px;color:#111827;outline:none;font-size:0.875rem;font-family:inherit;transition:all 0.15s;box-sizing:border-box;"
                    onfocus="this.style.borderColor='#BBCC00';this.style.background='#FFFFF8';this.style.boxShadow='0 0 0 3px rgba(222,255,26,0.2)'"
                    onblur="this.style.borderColor='${modalErrors.nickname ? '#FCA5A5' : '#E2E5EA'}';this.style.background='#F8F9FB';this.style.boxShadow='none'" />
                  ${modalErrors.nickname ? `<p style="display:flex;align-items:center;gap:4px;color:#DC2626;font-size:0.75rem;margin:6px 0 0;"><i data-lucide="alert-circle" style="width:12px;height:12px;"></i>${escHtml(modalErrors.nickname)}</p>` : ''}
                </div>
                <div>
                  <label style="display:block;color:#374151;font-size:0.875rem;font-weight:600;margin-bottom:8px;">Last 4 Digits</label>
                  <input type="text" id="modal-last4" value="${escHtml(f.last4)}" oninput="handleLast4Input(this.value)" placeholder="1234" maxlength="4" inputmode="numeric"
                    class="mono" style="width:100%;background:#F8F9FB;border:1px solid ${modalErrors.last4 ? '#FCA5A5' : '#E2E5EA'};border-radius:12px;padding:12px 16px;color:#111827;outline:none;font-size:1rem;letter-spacing:0.2em;transition:all 0.15s;box-sizing:border-box;"
                    onfocus="this.style.borderColor='#BBCC00';this.style.background='#FFFFF8';this.style.boxShadow='0 0 0 3px rgba(222,255,26,0.2)'"
                    onblur="this.style.borderColor='${modalErrors.last4 ? '#FCA5A5' : '#E2E5EA'}';this.style.background='#F8F9FB';this.style.boxShadow='none'" />
                  ${modalErrors.last4 ? `<p style="display:flex;align-items:center;gap:4px;color:#DC2626;font-size:0.75rem;margin:6px 0 0;"><i data-lucide="alert-circle" style="width:12px;height:12px;"></i>${escHtml(modalErrors.last4)}</p>` : ''}
                  <p id="modal-last4-hint" style="color:#9CA3AF;font-size:0.75rem;margin:6px 0 0;display:${!modalErrors.last4 && f.last4.length > 0 && f.last4.length < 4 ? 'block' : 'none'};">${digitsNeeded > 1 ? `${digitsNeeded} more digits needed` : '1 more digit needed'}</p>
                </div>
                <div>
                  <label style="display:block;color:#374151;font-size:0.875rem;font-weight:600;margin-bottom:8px;">Card Brand</label>
                  <div style="display:grid;grid-template-columns:repeat(3,1fr);gap:8px;">${brandButtons}</div>
                </div>
                <div>
                  <label style="display:block;color:#374151;font-size:0.875rem;font-weight:600;margin:0 0 8px;">Card Theme</label>
                  <div style="display:flex;gap:8px;">${themeButtons}</div>
                </div>
              </div>
              <!-- Right: Preview -->
              <div style="display:flex;flex-direction:column;height:100%;">
                <div style="display:flex;align-items:center;justify-content:space-between;gap:12px;margin-bottom:12px;">
                  <label style="display:block;color:#374151;font-size:0.875rem;font-weight:600;margin:0;">Live Preview</label>
                  <div style="display:flex;align-items:center;gap:8px;flex-shrink:0;">
                    <span style="color:#6B7280;font-size:0.75rem;font-weight:600;">Set as Primary</span>
                    <div class="toggle-track" style="background:${f.isPrimary ? '#DEFF1A' : '#E5E7EB'};" onclick="togglePrimary()">
                      <div class="toggle-thumb" style="left:${f.isPrimary ? '26px' : '2px'};"></div>
                    </div>
                  </div>
                </div>
                <div id="card-preview">${cardVisualHTML(previewCard, false)}</div>
                <div style="margin-top:14px;padding:16px;background:#F8F9FB;border-radius:12px;border:1px solid #E2E5EA;display:flex;flex-direction:column;gap:8px;">
                  <div style="display:flex;align-items:center;justify-content:space-between;font-size:0.875rem;">
                    <span style="color:#6B7280;">Brand</span>
                    <span id="preview-brand-val" style="color:#111827;font-weight:500;">${escHtml(BRAND_LABELS[f.brand] || 'Visa')}</span>
                  </div>
                  <div style="display:flex;align-items:center;justify-content:space-between;font-size:0.875rem;">
                    <span style="color:#6B7280;">Number</span>
                    <span id="preview-number-val" class="mono" style="color:#111827;font-weight:500;">•••• ${escHtml(f.last4 || '0000')}</span>
                  </div>
                  <div style="display:flex;align-items:center;justify-content:space-between;font-size:0.875rem;">
                    <span style="color:#6B7280;">Nickname</span>
                    <span id="preview-nickname-val" style="color:#111827;font-weight:500;">${escHtml(f.nickname || '—')}</span>
                  </div>
                  <div style="display:flex;align-items:center;justify-content:space-between;font-size:0.875rem;">
                    <span style="color:#6B7280;">Primary</span>
                    <span id="preview-primary-val" style="color:${f.isPrimary ? '#7A8C00' : '#9CA3AF'};font-weight:600;">${f.isPrimary ? 'Yes' : 'No'}</span>
                  </div>
                </div>
                <div style="margin-top:auto;padding-top:14px;display:flex;flex-direction:column;gap:8px;width:100%;">
                  <button type="submit" id="modal-submit-btn" style="width:100%;padding:12px;border-radius:12px;background:#DEFF1A;color:#111;border:none;cursor:pointer;font-size:0.875rem;font-weight:700;font-family:inherit;transition:background 0.15s;" onmouseover="this.style.background='#CCEE00'" onmouseout="this.style.background='#DEFF1A'">${isEdit ? 'Save Changes' : 'Add Card'}</button>
                  <button type="button" onclick="closeAddModal()" style="width:100%;padding:12px;border-radius:12px;border:1px solid #E2E5EA;color:#6B7280;background:#F3F4F6;cursor:pointer;font-size:0.875rem;font-weight:600;font-family:inherit;transition:all 0.15s;" onmouseover="this.style.background='#E5E7EB';this.style.color='#111827'" onmouseout="this.style.background='#F3F4F6';this.style.color='#6B7280'">Cancel</button>
                </div>
              </div>
            </div>
          </div>
        </form>
      </div>
    </div>`;
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
    <p style="color:#6B7280;font-size:0.875rem;margin:0 0 16px;">You are about to delete <span style="color:#111827;font-weight:600;">"${escHtml(card.nickname)}"</span> (•••• ${escHtml(card.last4)}).</p>
    ${hasSubs ? `
      <div style="background:#FFFBEB;border:1px solid #FDE68A;border-radius:12px;padding:16px;margin-bottom:16px;">
        <div style="display:flex;align-items:flex-start;gap:12px;">
          <i data-lucide="alert-triangle" style="width:16px;height:16px;color:#D97706;flex-shrink:0;margin-top:2px;"></i>
          <div>
            <p style="color:#92400E;font-size:0.875rem;margin:0 0 8px;font-weight:600;">This card has ${subs.length} active subscription${subs.length!==1?'s':''} linked:</p>
            ${subs.map(s => {
              const color = safeCssColor(s.color, '#AFC0DE');
              const name = escHtml(s.name);
              const monthlyPrice = formatMoney(s.monthlyPrice, s.currency);
              return `<div style="display:flex;align-items:center;gap:8px;color:#78350F;font-size:0.75rem;margin-bottom:4px;"><div style="width:8px;height:8px;border-radius:50%;background:${color};flex-shrink:0;"></div>${name} — ${monthlyPrice}/mo</div>`;
            }).join('')}
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
          <button type="button" onclick="setMoveTarget('${escHtml(c.id)}')" style="display:flex;align-items:center;gap:12px;padding:12px;border-radius:12px;border:1px solid ${moveToCardId===c.id ? '#BBCC00' : '#E2E5EA'};background:${moveToCardId===c.id ? '#FAFFF0' : '#F8F9FB'};cursor:pointer;text-align:left;transition:all 0.15s;width:100%;">
            <div style="width:32px;height:32px;border-radius:8px;background:#E5E7EB;display:flex;align-items:center;justify-content:center;font-size:0.75rem;color:#4B5563;font-family:'JetBrains Mono',monospace;">${escHtml(c.last4)}</div>
            <div style="flex:1;">
              <p style="color:#111827;font-size:0.875rem;font-weight:600;margin:0;">${escHtml(c.nickname)}</p>
              <p style="color:#9CA3AF;font-size:0.75rem;margin:0;">•••• ${escHtml(c.last4)}</p>
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
  return String(str)
    .replace(/&/g,'&amp;')
    .replace(/</g,'&lt;')
    .replace(/>/g,'&gt;')
    .replace(/"/g,'&quot;')
    .replace(/'/g,'&#39;');
}

function showApiError(err) {
  const fallback = 'Something went wrong. Please try again.';
  const message = (err && err.message) ? err.message : fallback;
  window.alert(message);
}

function captureFocusSnapshot() {
  const active = document.activeElement;
  if (!active || !active.id) return null;

  const snapshot = { id: active.id };
  if (typeof active.selectionStart === 'number' && typeof active.selectionEnd === 'number') {
    snapshot.selectionStart = active.selectionStart;
    snapshot.selectionEnd = active.selectionEnd;
  }
  return snapshot;
}

function renderAppKeepingFocus(snapshot) {
  renderApp();
  if (!snapshot || !snapshot.id) return;

  const next = document.getElementById(snapshot.id);
  if (!next) return;

  next.focus({ preventScroll: true });
  if (typeof snapshot.selectionStart === 'number' && typeof next.setSelectionRange === 'function') {
    const valueLength = typeof next.value === 'string' ? next.value.length : 0;
    const start = Math.min(snapshot.selectionStart, valueLength);
    const end = Math.min(
      typeof snapshot.selectionEnd === 'number' ? snapshot.selectionEnd : start,
      valueLength,
    );
    next.setSelectionRange(start, end);
  }
}

function updateModalLiveUI() {
  if (!state.addModalOpen) return;

  const previewCard = {
    nickname: modalForm.nickname || 'My Card',
    last4: modalForm.last4 || '0000',
    brand: modalForm.brand,
    isPrimary: modalForm.isPrimary,
    theme: modalForm.theme,
  };

  const cardPreview = document.getElementById('card-preview');
  if (cardPreview) {
    const last4Node = cardPreview.querySelector('[data-preview-last4]');
    const nicknameNode = cardPreview.querySelector('[data-preview-nickname]');
    if (last4Node && nicknameNode) {
      last4Node.textContent = `•••• •••• •••• ${modalForm.last4 || '0000'}`;
      nicknameNode.textContent = modalForm.nickname || 'My Card';
    } else {
      cardPreview.innerHTML = cardVisualHTML(previewCard, false);
    }
  }

  const brandValue = document.getElementById('preview-brand-val');
  if (brandValue) {
    brandValue.textContent = BRAND_LABELS[modalForm.brand] || 'Visa';
  }

  const numberValue = document.getElementById('preview-number-val');
  if (numberValue) {
    numberValue.textContent = `•••• ${modalForm.last4 || '0000'}`;
  }

  const nicknameValue = document.getElementById('preview-nickname-val');
  if (nicknameValue) {
    nicknameValue.textContent = modalForm.nickname || '—';
  }

  const primaryValue = document.getElementById('preview-primary-val');
  if (primaryValue) {
    primaryValue.textContent = modalForm.isPrimary ? 'Yes' : 'No';
    primaryValue.style.color = modalForm.isPrimary ? '#7A8C00' : '#9CA3AF';
  }

  const hint = document.getElementById('modal-last4-hint');
  if (hint) {
    const digitsNeeded = 4 - modalForm.last4.length;
    const showHint = !modalErrors.last4 && modalForm.last4.length > 0 && modalForm.last4.length < 4;
    hint.style.display = showHint ? 'block' : 'none';
    if (showHint) {
      hint.textContent = digitsNeeded > 1 ? `${digitsNeeded} more digits needed` : '1 more digit needed';
    }
  }
}

function handleCardClick(cardId) { state.selectedCardId = state.selectedCardId === String(cardId) ? null : String(cardId); renderApp(); }
function closeDetailPanel() { state.selectedCardId = null; renderApp(); }
function handleSearch(val) {
  const focusSnapshot = captureFocusSnapshot();
  state.search = val;
  renderAppKeepingFocus(focusSnapshot);
}

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
function setModalField(field, value) {
  const hadError = !!modalErrors[field];
  const focusSnapshot = captureFocusSnapshot();
  modalForm[field] = value;
  if (hadError) {
    modalErrors[field] = '';
    renderAppKeepingFocus(focusSnapshot);
    return;
  }
  if (field === 'nickname') {
    updateModalLiveUI();
    return;
  }
  renderAppKeepingFocus(focusSnapshot);
}
function handleLast4Input(val) {
  const hadError = !!modalErrors.last4;
  const focusSnapshot = captureFocusSnapshot();
  const d = val.replace(/\D/g,'').slice(0,4);
  modalForm.last4 = d;
  const input = document.getElementById('modal-last4');
  if (input && input.value !== d) {
    input.value = d;
  }
  if (hadError) {
    modalErrors.last4 = '';
    renderAppKeepingFocus(focusSnapshot);
    return;
  }
  updateModalLiveUI();
}
function togglePrimary() { modalForm.isPrimary = !modalForm.isPrimary; renderApp(); }

async function handleModalSubmit(e) {
  e.preventDefault();
  const errs = {};
  if (!modalForm.nickname.trim()) errs.nickname = 'Card nickname is required';
  else if (modalForm.nickname.length > 50) errs.nickname = 'Nickname must be 50 characters or fewer';
  if (!modalForm.last4) errs.last4 = 'Last 4 digits are required';
  else if (!/^\d{4}$/.test(modalForm.last4)) errs.last4 = 'Must be exactly 4 digits';
  if (Object.keys(errs).length > 0) { modalErrors = errs; renderApp(); return; }

  const btn = document.getElementById('modal-submit-btn');
  if (btn) {
    btn.disabled = true;
    btn.innerHTML = '<i data-lucide="check" style="width:16px;height:16px;"></i> ' + (state.editCardId ? 'Updated!' : 'Added!');
    btn.style.background = '#16A34A';
    btn.style.color = 'white';
    renderIcons(btn.parentElement || document);
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

function bootCardsPage() {
  if (!document.getElementById('cards-app')) {
    return;
  }

  state = parseBootstrapState();
  deleteStep = 'warn';
  moveToCardId = '';
  modalErrors = {};
  applyInitialModalState();
  renderApp();
}

if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', bootCardsPage);
} else {
  bootCardsPage();
}

document.addEventListener('subly:content-loaded', bootCardsPage);
