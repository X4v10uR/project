const test = require('node:test');
const assert = require('node:assert/strict');

const dashboardModule = require('../static/dashboard/dashboard.js');

class EventTargetMock {
    constructor() {
        this.listeners = new Map();
    }

    addEventListener(eventName, handler) {
        if (!this.listeners.has(eventName)) {
            this.listeners.set(eventName, new Set());
        }
        this.listeners.get(eventName).add(handler);
    }

    removeEventListener(eventName, handler) {
        const handlers = this.listeners.get(eventName);
        if (!handlers) {
            return;
        }
        handlers.delete(handler);
        if (handlers.size === 0) {
            this.listeners.delete(eventName);
        }
    }

    listenerCount(eventName) {
        const handlers = this.listeners.get(eventName);
        return handlers ? handlers.size : 0;
    }
}

function withGlobalMocks(mocks, callback) {
    const originalWindow = global.window;
    const originalDocument = global.document;

    if (Object.prototype.hasOwnProperty.call(mocks, 'window')) {
        global.window = mocks.window;
    } else {
        delete global.window;
    }

    if (Object.prototype.hasOwnProperty.call(mocks, 'document')) {
        global.document = mocks.document;
    } else {
        delete global.document;
    }

    try {
        callback();
    } finally {
        if (typeof originalWindow === 'undefined') {
            delete global.window;
        } else {
            global.window = originalWindow;
        }

        if (typeof originalDocument === 'undefined') {
            delete global.document;
        } else {
            global.document = originalDocument;
        }
    }
}

test('overflow guard is dashboard-scoped and cleans listeners', function () {
    const windowTarget = new EventTargetMock();
    let rafId = 0;
    const scheduledAnimationFrames = new Map();
    const scheduledTimeouts = new Map();
    let timeoutId = 0;

    const rootStyle = {
        removeProperty(name) {
            if (name === 'overflow-x') {
                delete this.overflowX;
            }
        },
    };
    const root = {
        scrollWidth: 1004,
        clientWidth: 1000,
        style: rootStyle,
    };

    const documentElementStyle = { overflowX: 'visible', overflowY: 'visible' };
    const bodyStyle = { overflowX: 'visible', overflowY: 'visible' };

    const mockWindow = {
        addEventListener: windowTarget.addEventListener.bind(windowTarget),
        removeEventListener: windowTarget.removeEventListener.bind(windowTarget),
        requestAnimationFrame(callback) {
            rafId += 1;
            scheduledAnimationFrames.set(rafId, callback);
            callback();
            return rafId;
        },
        cancelAnimationFrame(id) {
            scheduledAnimationFrames.delete(id);
        },
        setTimeout(callback) {
            timeoutId += 1;
            scheduledTimeouts.set(timeoutId, callback);
            callback();
            return timeoutId;
        },
        clearTimeout(id) {
            scheduledTimeouts.delete(id);
        },
    };

    const mockDocument = {
        documentElement: { style: documentElementStyle },
        body: { style: bodyStyle },
    };

    withGlobalMocks({ window: mockWindow, document: mockDocument }, function () {
        const cleanup = dashboardModule.initDashboardOverflowGuard(root);

        assert.equal(typeof cleanup, 'function');
        assert.equal(root.style.overflowX, 'hidden');
        assert.equal(mockDocument.documentElement.style.overflowX, 'visible');
        assert.equal(mockDocument.body.style.overflowX, 'visible');
        assert.equal(windowTarget.listenerCount('load'), 1);
        assert.equal(windowTarget.listenerCount('resize'), 1);

        cleanup();

        assert.equal(windowTarget.listenerCount('load'), 0);
        assert.equal(windowTarget.listenerCount('resize'), 0);
        assert.equal(root.style.overflowX, undefined);
    });
});

test('active subscription scroller cleanup removes listeners and interval', function () {
    const viewportTarget = new EventTargetMock();
    const windowTarget = new EventTargetMock();
    const documentTarget = new EventTargetMock();

    let intervalId = 0;
    const activeIntervals = new Set();
    const pendingTimeouts = new Set();

    function makeCard(offsetTop, offsetHeight) {
        return {
            offsetTop,
            offsetHeight,
            cloneNode() {
                return makeCard(offsetTop, offsetHeight);
            },
        };
    }

    const track = {
        children: [makeCard(0, 90), makeCard(96, 90), makeCard(192, 90)],
        style: {},
        classList: {
            add() {},
            remove() {},
        },
        appendChild(node) {
            this.children.push(node);
        },
        removeChild(node) {
            const index = this.children.indexOf(node);
            if (index >= 0) {
                this.children.splice(index, 1);
            }
        },
        getBoundingClientRect() {
            return { top: 0 };
        },
    };

    const viewport = {
        dataset: { visibleCards: '2', scrollInterval: '1' },
        style: {},
        querySelector(selector) {
            if (selector === '.js-active-subscriptions-track') {
                return track;
            }
            return null;
        },
        addEventListener: viewportTarget.addEventListener.bind(viewportTarget),
        removeEventListener: viewportTarget.removeEventListener.bind(viewportTarget),
        contains() {
            return false;
        },
    };

    const mockDocument = {
        hidden: false,
        querySelector(selector) {
            if (selector === '.js-active-subscriptions-viewport') {
                return viewport;
            }
            return null;
        },
        addEventListener: documentTarget.addEventListener.bind(documentTarget),
        removeEventListener: documentTarget.removeEventListener.bind(documentTarget),
    };

    const mockWindow = {
        addEventListener: windowTarget.addEventListener.bind(windowTarget),
        removeEventListener: windowTarget.removeEventListener.bind(windowTarget),
        matchMedia() {
            return { matches: false };
        },
        setInterval(callback) {
            intervalId += 1;
            activeIntervals.add(intervalId);
            return intervalId;
        },
        clearInterval(id) {
            activeIntervals.delete(id);
        },
        setTimeout(callback) {
            const id = pendingTimeouts.size + 1;
            pendingTimeouts.add(id);
            return id;
        },
        clearTimeout(id) {
            pendingTimeouts.delete(id);
        },
    };

    withGlobalMocks({ window: mockWindow, document: mockDocument }, function () {
        const cleanup = dashboardModule.initActiveSubscriptionsScroller();

        assert.equal(typeof cleanup, 'function');
        assert.equal(viewportTarget.listenerCount('mouseenter'), 1);
        assert.equal(viewportTarget.listenerCount('mouseleave'), 1);
        assert.equal(viewportTarget.listenerCount('focusin'), 1);
        assert.equal(viewportTarget.listenerCount('focusout'), 1);
        assert.equal(documentTarget.listenerCount('visibilitychange'), 1);
        assert.equal(windowTarget.listenerCount('resize'), 1);
        assert.equal(activeIntervals.size, 1);

        cleanup();

        assert.equal(viewportTarget.listenerCount('mouseenter'), 0);
        assert.equal(viewportTarget.listenerCount('mouseleave'), 0);
        assert.equal(viewportTarget.listenerCount('focusin'), 0);
        assert.equal(viewportTarget.listenerCount('focusout'), 0);
        assert.equal(documentTarget.listenerCount('visibilitychange'), 0);
        assert.equal(windowTarget.listenerCount('resize'), 0);
        assert.equal(activeIntervals.size, 0);
    });
});

test('active subscription scroller animates when card count matches visible cards', function () {
    const viewportTarget = new EventTargetMock();
    const windowTarget = new EventTargetMock();
    const documentTarget = new EventTargetMock();

    let capturedIntervalCallback = null;
    let intervalId = 0;
    const activeIntervals = new Set();
    let timeoutId = 0;
    const pendingTimeouts = new Map();

    function makeCard(name, offsetTop, offsetHeight) {
        return {
            name,
            offsetTop,
            offsetHeight,
            dataset: {},
            cloneNode() {
                return makeCard(name + '-clone', offsetTop, offsetHeight);
            },
        };
    }

    const firstCard = makeCard('spotify', 0, 90);
    const secondCard = makeCard('paramount', 96, 90);

    const track = {
        children: [firstCard, secondCard],
        style: {},
        classList: {
            add() {},
            remove() {},
        },
        appendChild(node) {
            this.children.push(node);
        },
        removeChild(node) {
            const index = this.children.indexOf(node);
            if (index >= 0) {
                this.children.splice(index, 1);
            }
        },
        getBoundingClientRect() {
            return { top: 0 };
        },
    };

    const viewport = {
        dataset: { visibleCards: '2', scrollInterval: '5000' },
        style: {},
        querySelector(selector) {
            if (selector === '.js-active-subscriptions-track') {
                return track;
            }
            return null;
        },
        addEventListener: viewportTarget.addEventListener.bind(viewportTarget),
        removeEventListener: viewportTarget.removeEventListener.bind(viewportTarget),
        contains() {
            return false;
        },
    };

    const mockDocument = {
        hidden: false,
        querySelector(selector) {
            if (selector === '.js-active-subscriptions-viewport') {
                return viewport;
            }
            return null;
        },
        addEventListener: documentTarget.addEventListener.bind(documentTarget),
        removeEventListener: documentTarget.removeEventListener.bind(documentTarget),
    };

    const mockWindow = {
        addEventListener: windowTarget.addEventListener.bind(windowTarget),
        removeEventListener: windowTarget.removeEventListener.bind(windowTarget),
        matchMedia() {
            return { matches: false };
        },
        setInterval(callback) {
            capturedIntervalCallback = callback;
            intervalId += 1;
            activeIntervals.add(intervalId);
            return intervalId;
        },
        clearInterval(id) {
            activeIntervals.delete(id);
        },
        setTimeout(callback) {
            timeoutId += 1;
            pendingTimeouts.set(timeoutId, callback);
            return timeoutId;
        },
        clearTimeout(id) {
            pendingTimeouts.delete(id);
        },
    };

    withGlobalMocks({ window: mockWindow, document: mockDocument }, function () {
        const cleanup = dashboardModule.initActiveSubscriptionsScroller();

        assert.equal(typeof cleanup, 'function');
        assert.equal(activeIntervals.size, 1);
        assert.equal(viewport.style.height, '186px');

        capturedIntervalCallback();

        assert.equal(track.style.transform, 'translateY(-96px)');
        assert.equal(track.children.length, 3);
        assert.equal(track.children[2].dataset.dashboardClone, '1');

        const timeoutCallback = pendingTimeouts.get(timeoutId);
        assert.equal(typeof timeoutCallback, 'function');
        timeoutCallback();

        assert.equal(track.children.length, 2);
        assert.equal(track.children[0].name, 'paramount');
        assert.equal(track.children[1].name, 'spotify-clone');

        cleanup();
    });
});
