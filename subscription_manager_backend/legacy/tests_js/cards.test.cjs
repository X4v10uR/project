const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

test('card summaries preserve currencies and distinguish an absent renewal from one due today', () => {
  const fixture = {
    cards: [{ id: '1', nickname: 'Travel', last4: '1234' }],
    selectedCardId: '1',
    subscriptions: [
      { id: '1', name: 'Music', cardId: '1', monthlyPrice: 12, currency: 'EUR', daysLeft: 0 },
      { id: '2', name: 'Video', cardId: '1', monthlyPrice: 8, currency: 'USD', daysLeft: null },
    ],
  };
  const document = {
    readyState: 'loading',
    addEventListener() {},
    getElementById(id) {
      return id === 'cards-initial-state' ? { textContent: JSON.stringify(fixture) } : null;
    },
  };
  const context = vm.createContext({ document, window: {} });
  const script = fs.readFileSync(path.join(__dirname, '../static/subscriptions/cards.js'), 'utf8');
  vm.runInContext(script, context);
  const monthly = '\u20ac12.00 + $8.00';
  assert.ok(context.renderStats().includes(monthly));
  assert.ok(context.renderCardsGrid().includes(monthly));
  const detail = context.renderDetailPanel();
  assert.ok(detail.includes(monthly));
  assert.ok(detail.includes('\u20ac144.00 + $96.00'));
  assert.ok(detail.includes('0d left'));
  assert.ok(detail.includes('No renewal scheduled'));
});
