const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const NotificationBell = require('../static/dashboard/notifications.js');

function worker() {
    const handlers = {};
    const shown = [];
    const opened = [];
    let options;
    const existing = {
        url: 'https://subly.example/dashboard/',
        navigate: async (url) => ({ focus: async () => url }),
    };
    vm.runInNewContext(fs.readFileSync(path.resolve(__dirname, '../../../subscription_manager_frontend/public/notification-worker.js'), 'utf8'), {
        URL,
        self: {
            location: { origin: 'https://subly.example' },
            addEventListener: (name, handler) => { handlers[name] = handler; },
            registration: { showNotification: async (title, data) => { shown.push({ title, ...data }); } },
        },
        clients: {
            matchAll: async (value) => { options = value; return [existing]; },
            openWindow: async (url) => { opened.push(url); },
        },
    });
    return { handlers, shown, opened, existing, options: () => options };
}

test('push handles malformed payloads and keeps destinations on this origin', async () => {
    for (const payload of [null, { title: null, body: 42, url: 'https://other.example/' }, { url: 'http://[' }]) {
        const state = worker();
        let waiting;
        state.handlers.push({ data: { json: () => payload }, waitUntil: (promise) => { waiting = promise; } });
        await waiting;
        assert.equal(state.shown[0].title, 'DUES reminder');
        assert.equal(state.shown[0].data.url, 'https://subly.example/dashboard/notifications/');
    }
});

test('clicking push reuses a tab that is not yet controlled by the worker', async () => {
    const state = worker();
    let waiting;
    state.handlers.notificationclick({ notification: { close() {}, data: { url: '/subscriptions/' } }, waitUntil: (promise) => { waiting = promise; } });
    assert.equal(await waiting, 'https://subly.example/subscriptions/');
    assert.equal(state.options().includeUncontrolled, true);
    assert.deepEqual(state.opened, []);
});

test('clicking push opens a window if the matched tab closes during navigation', async () => {
    const state = worker();
    state.existing.navigate = async () => null;
    let waiting;
    state.handlers.notificationclick({ notification: { close() {}, data: { url: '/subscriptions/' } }, waitUntil: (promise) => { waiting = promise; } });
    await waiting;
    assert.deepEqual(state.opened, ['https://subly.example/subscriptions/']);
});

test('legacy bell refreshes snoozed items and retains fallback polling with a socket', () => {
    const originalWindow = global.window;
    const originalWebSocket = global.WebSocket;
    try {
        let refreshes = 0;
        global.window = { SUBLY_RUNTIME: { notificationsWsEnabled: true }, WebSocket: true, location: { protocol: 'https:', host: 'subly.example' } };
        global.WebSocket = class {};
        const bell = Object.create(NotificationBell.prototype);
        bell.pollTimer = 123;
        bell.fetchList = () => { refreshes++; };
        bell.connectSocket();
        bell.socket.onopen();
        assert.equal(bell.pollTimer, 123);
        bell.socket.onmessage({ data: JSON.stringify({ type: 'notification.updated', notification_id: 1 }) });
        assert.equal(refreshes, 2);
    } finally {
        global.window = originalWindow;
        global.WebSocket = originalWebSocket;
    }
});

test('legacy bell does not replace newer results with a stale response', async () => {
    const originalFetch = global.fetch;
    const pending = [];
    try {
        global.fetch = () => new Promise((resolve) => pending.push(resolve));
        const bell = Object.create(NotificationBell.prototype);
        bell.requestNumber = 0;
        bell.setUnreadCount = () => {};
        bell.render = () => {};
        const oldRequest = bell.fetchList();
        const newRequest = bell.fetchList();
        pending[1]({ json: async () => ({ ok: true, notifications: [{ id: 2 }] }) });
        await newRequest;
        pending[0]({ json: async () => ({ ok: true, notifications: [{ id: 1 }] }) });
        await oldRequest;
        assert.deepEqual(bell.notifications, [{ id: 2 }]);
    } finally {
        global.fetch = originalFetch;
    }
});
