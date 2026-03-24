const dashboardRuntimeState = {
    root: null,
    cleanup: null,
};

function teardownDashboardPage() {
    if (typeof dashboardRuntimeState.cleanup === 'function') {
        dashboardRuntimeState.cleanup();
    }
    if (dashboardRuntimeState.root && dashboardRuntimeState.root.dataset) {
        delete dashboardRuntimeState.root.dataset.dashboardInit;
    }
    dashboardRuntimeState.root = null;
    dashboardRuntimeState.cleanup = null;
}

function initDashboardPage() {
    if (typeof document === 'undefined') {
        return;
    }

    const dashboardRoot = document.querySelector('.dashboard-shell');
    if (!dashboardRoot) {
        teardownDashboardPage();
        return;
    }

    if (dashboardRuntimeState.root === dashboardRoot && dashboardRoot.dataset.dashboardInit === '1') {
        return;
    }

    teardownDashboardPage();

    dashboardRoot.dataset.dashboardInit = '1';
    dashboardRuntimeState.root = dashboardRoot;

    const cleanupCallbacks = [];
    const registerCleanup = function (cleanupFn) {
        if (typeof cleanupFn === 'function') {
            cleanupCallbacks.push(cleanupFn);
        }
    };

    const listen = function (target, eventName, handler, options) {
        if (!target || typeof target.addEventListener !== 'function') {
            return;
        }
        target.addEventListener(eventName, handler, options);
        registerCleanup(function () {
            target.removeEventListener(eventName, handler, options);
        });
    };

    dashboardRoot.querySelectorAll('.js-clickable-card').forEach(function (card) {
        const onClick = function () {
            const url = this.getAttribute('data-url');
            if (url) {
                window.location.href = url;
            }
        };
        listen(card, 'click', onClick);
    });

    dashboardRoot.querySelectorAll('a[href^="#"]').forEach(function (anchor) {
        const onClick = function (event) {
            event.preventDefault();
            const target = document.querySelector(this.getAttribute('href'));
            if (target) {
                target.scrollIntoView({ behavior: 'smooth' });
            }
        };
        listen(anchor, 'click', onClick);
    });

    initBalanceTrendChart();
    registerCleanup(initBalanceTrendToggle());
    registerCleanup(initBalanceAdjuster());
    registerCleanup(initActiveSubscriptionsScroller());
    registerCleanup(initDashboardOverflowGuard(dashboardRoot));

    dashboardRuntimeState.cleanup = function () {
        for (let index = cleanupCallbacks.length - 1; index >= 0; index -= 1) {
            try {
                cleanupCallbacks[index]();
            } catch (error) {
                // Ignore cleanup errors so other disposers still run.
            }
        }
    };
}

function bootstrapDashboardPage() {
    initDashboardPage();
}

if (typeof document !== 'undefined') {
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', bootstrapDashboardPage);
    } else {
        bootstrapDashboardPage();
    }

    document.addEventListener('subly:content-loaded', bootstrapDashboardPage);
}

function getCookie(name) {
    if (!document.cookie) {
        return null;
    }

    const cookies = document.cookie.split(';');
    for (let i = 0; i < cookies.length; i += 1) {
        const cookie = cookies[i].trim();
        if (cookie.substring(0, name.length + 1) === name + '=') {
            return decodeURIComponent(cookie.substring(name.length + 1));
        }
    }
    return null;
}

function normalizeCurrencyCode(currencyCode) {
    if (typeof currencyCode !== 'string') {
        return 'USD';
    }
    const normalized = currencyCode.trim().toUpperCase();
    return normalized || 'USD';
}

function initBalanceTrendChart() {
    const chart = document.querySelector('.js-balance-trend-graph');
    const dataNode = document.getElementById('balance-trend-points');
    if (!chart || !dataNode) {
        return;
    }

    const currencyCode = normalizeCurrencyCode(chart.dataset.currency);
    let points = [];
    try {
        const parsed = JSON.parse(dataNode.textContent || '[]');
        if (Array.isArray(parsed)) {
            points = parsed
                .map(function (value) { return Number(value); })
                .filter(function (value) {
                    return typeof value === 'number' && isFinite(value);
                });
        }
    } catch (error) {
        points = [];
    }

    if (!points.length) {
        updateBalanceTrendMetrics([], currencyCode);
        return;
    }

    if (points.length === 1) {
        points = [points[0], points[0]];
    }

    updateBalanceTrendMetrics(points, currencyCode);

    // Light smoothing to avoid harsh spikes and keep a trading-chart feel.
    const smoothedPoints = points.map(function (point, index) {
        const prev = points[Math.max(0, index - 1)];
        const next = points[Math.min(points.length - 1, index + 1)];
        return (prev * 0.25) + (point * 0.5) + (next * 0.25);
    });

    const min = Math.min.apply(null, smoothedPoints);
    const max = Math.max.apply(null, smoothedPoints);
    const range = max - min || 1;

    const width = 100;
    const height = 32;
    const topPadding = 3;
    const bottomPadding = 3;
    const leftPadding = 2;
    const rightPadding = 2;
    const graphWidth = width - leftPadding - rightPadding;
    const graphHeight = height - topPadding - bottomPadding;
    const stepX = points.length > 1 ? graphWidth / (points.length - 1) : graphWidth;

    const coordinates = smoothedPoints.map(function (point, index) {
        const ratio = (point - min) / range;
        return {
            x: leftPadding + (stepX * index),
            y: topPadding + (graphHeight * (1 - ratio)),
        };
    });

    const linePath = buildSmoothPath(coordinates);
    const svgNs = 'http://www.w3.org/2000/svg';

    while (chart.firstChild) {
        chart.removeChild(chart.firstChild);
    }

    const glowLine = document.createElementNS(svgNs, 'path');
    glowLine.setAttribute('d', linePath);
    glowLine.setAttribute('fill', 'none');
    glowLine.setAttribute('stroke', '#22c55e');
    glowLine.setAttribute('stroke-width', '2.4');
    glowLine.setAttribute('stroke-opacity', '0.2');
    glowLine.setAttribute('stroke-linecap', 'round');
    glowLine.setAttribute('stroke-linejoin', 'round');
    glowLine.setAttribute('vector-effect', 'non-scaling-stroke');
    chart.appendChild(glowLine);

    const line = document.createElementNS(svgNs, 'path');
    line.setAttribute('d', linePath);
    line.setAttribute('fill', 'none');
    line.setAttribute('stroke', '#2ee67d');
    line.setAttribute('stroke-width', '1.05');
    line.setAttribute('stroke-opacity', '0.98');
    line.setAttribute('stroke-linecap', 'round');
    line.setAttribute('stroke-linejoin', 'round');
    line.setAttribute('vector-effect', 'non-scaling-stroke');
    chart.appendChild(line);
}

function updateBalanceTrendMetrics(points, currencyCode) {
    const totalNode = document.querySelector('.js-balance-trend-total');
    const peakNode = document.querySelector('.js-balance-trend-peak');
    const activeNode = document.querySelector('.js-balance-trend-active');
    if (!totalNode || !peakNode || !activeNode) {
        return;
    }

    const normalizedCurrency = normalizeCurrencyCode(currencyCode);

    if (!points.length) {
        totalNode.textContent = formatTrendAmount(0, normalizedCurrency);
        peakNode.textContent = formatTrendAmount(0, normalizedCurrency);
        activeNode.textContent = '0/0';
        return;
    }

    const total = points.reduce(function (sum, value) { return sum + value; }, 0);
    const peak = Math.max.apply(null, points);
    const activeDays = points.filter(function (value) { return value > 0; }).length;

    totalNode.textContent = formatTrendAmount(total, normalizedCurrency);
    peakNode.textContent = formatTrendAmount(peak, normalizedCurrency);
    activeNode.textContent = String(activeDays) + '/' + String(points.length);
}

function formatTrendAmount(value, currencyCode) {
    if (typeof value !== 'number' || !isFinite(value)) {
        value = 0;
    }

    const normalizedCurrency = normalizeCurrencyCode(currencyCode);
    const useCompactPrecision = Math.abs(value) >= 1000;

    try {
        return new Intl.NumberFormat(undefined, {
            style: 'currency',
            currency: normalizedCurrency,
            minimumFractionDigits: useCompactPrecision ? 0 : 2,
            maximumFractionDigits: useCompactPrecision ? 0 : 2,
        }).format(value);
    } catch (error) {
        const fixed = useCompactPrecision
            ? value.toLocaleString(undefined, { maximumFractionDigits: 0 })
            : value.toFixed(2);
        return normalizedCurrency + ' ' + fixed;
    }
}

function initBalanceTrendToggle() {
    const toggle = document.querySelector('.js-balance-trend-toggle');
    const panel = document.querySelector('.js-balance-trend-panel');
    if (!toggle || !panel) {
        return null;
    }

    const storageKey = 'dashboard.balanceTrendCollapsed';
    let isCollapsed = false;
    try {
        isCollapsed = window.localStorage.getItem(storageKey) === '1';
    } catch (error) {
        isCollapsed = false;
    }

    const applyState = function () {
        panel.classList.toggle('is-collapsed', isCollapsed);
        toggle.classList.toggle('is-collapsed', isCollapsed);
        toggle.setAttribute('aria-expanded', String(!isCollapsed));
        toggle.setAttribute(
            'aria-label',
            isCollapsed ? 'Expand balance trend chart' : 'Collapse balance trend chart',
        );
        toggle.title = isCollapsed ? 'Expand chart' : 'Collapse chart';
    };

    const onClick = function () {
        isCollapsed = !isCollapsed;
        applyState();
        try {
            window.localStorage.setItem(storageKey, isCollapsed ? '1' : '0');
        } catch (error) {
            // Ignore storage write errors (private mode / blocked storage).
        }
    };

    applyState();
    toggle.addEventListener('click', onClick);

    return function cleanupBalanceTrendToggle() {
        toggle.removeEventListener('click', onClick);
    };
}

function initBalanceAdjuster() {
    const editor = document.querySelector('.js-balance-adjust-editor');
    if (!editor) {
        return null;
    }

    const openButton = document.querySelector('.js-balance-edit-open');
    const cancelButtons = Array.from(editor.querySelectorAll('.js-balance-adjust-cancel'));
    const overlay = editor.querySelector('.js-balance-adjust-overlay');
    const saveButton = editor.querySelector('.js-balance-adjust-save');
    const input = editor.querySelector('.js-balance-adjust-input');
    const status = editor.querySelector('.js-balance-adjust-status');
    const updateUrl = editor.dataset.url;
    if (!openButton || !cancelButtons.length || !saveButton || !input || !updateUrl) {
        return null;
    }

    let hideTimeoutId = null;
    let previousBodyOverflow = '';

    const clearHideTimeout = function () {
        if (hideTimeoutId !== null) {
            window.clearTimeout(hideTimeoutId);
            hideTimeoutId = null;
        }
    };

    const showEditor = function () {
        editor.classList.remove('hidden');
        editor.setAttribute('aria-hidden', 'false');
        if (typeof document !== 'undefined' && document.body) {
            previousBodyOverflow = document.body.style.overflow || '';
            document.body.style.overflow = 'hidden';
        }
        input.focus();
        input.select();
    };

    const hideEditor = function () {
        clearHideTimeout();
        editor.classList.add('hidden');
        editor.setAttribute('aria-hidden', 'true');
        if (typeof document !== 'undefined' && document.body) {
            document.body.style.overflow = previousBodyOverflow;
        }
        if (status) {
            status.textContent = '';
        }
    };

    const resolveScope = function () {
        const editorScope = normalizeDashboardScope(editor.dataset.scope);
        if (editorScope) {
            return editorScope;
        }

        const scopeSelect = document.getElementById('dashboard-scope');
        if (!scopeSelect) {
            return 'personal';
        }
        return normalizeDashboardScope(scopeSelect.value) || 'personal';
    };

    const applyBalanceSnapshot = function (payload) {
        const balanceNode = document.querySelector('.js-balance-display');
        const basePillNode = document.querySelector('.js-balance-base-pill');
        const adjustmentPillNode = document.querySelector('.js-balance-adjustment-pill');
        if (balanceNode && payload.balance_display) {
            balanceNode.textContent = payload.balance_display;
        }
        if (basePillNode && payload.balance_base_display) {
            basePillNode.textContent = 'Base ' + payload.balance_base_display;
        }
        if (adjustmentPillNode && payload.balance_adjustment_display) {
            adjustmentPillNode.textContent = 'Adj ' + payload.balance_adjustment_display;
        }
        if (typeof payload.balance_adjusted_amount === 'number') {
            input.value = payload.balance_adjusted_amount.toFixed(2);
        }
        if (payload.dashboard_scope) {
            editor.dataset.scope = payload.dashboard_scope;
        }
    };

    const submitUpdate = function () {
        const value = Number(input.value);
        if (!isFinite(value)) {
            if (status) {
                status.textContent = 'Please enter a valid amount.';
            }
            return;
        }

        saveButton.disabled = true;
        saveButton.textContent = 'Saving...';
        if (status) {
            status.textContent = '';
        }

        fetch(updateUrl, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-Requested-With': 'XMLHttpRequest',
                'X-CSRFToken': getCookie('csrftoken') || '',
            },
            body: JSON.stringify({
                target_balance: value,
                scope: resolveScope(),
            }),
        })
            .then(function (response) {
                return response.json().catch(function () { return {}; }).then(function (data) {
                    return { ok: response.ok, data: data };
                });
            })
            .then(function (result) {
                if (!result.ok || result.data.ok === false) {
                    const message = result.data.message || 'Failed to update balance.';
                    throw new Error(message);
                }

                applyBalanceSnapshot(result.data);
                if (status) {
                    status.textContent = 'Balance updated.';
                }
                clearHideTimeout();
                hideTimeoutId = window.setTimeout(function () {
                    hideEditor();
                }, 350);
            })
            .catch(function (error) {
                if (status) {
                    status.textContent = error.message || 'Failed to update balance.';
                }
            })
            .finally(function () {
                saveButton.disabled = false;
                saveButton.textContent = 'Save';
            });
    };

    const onOpenClick = function () {
        if (editor.classList.contains('hidden')) {
            showEditor();
            return;
        }
        hideEditor();
    };

    const onCancelClick = function () {
        hideEditor();
    };

    const onOverlayClick = function () {
        hideEditor();
    };

    const onSaveClick = function () {
        submitUpdate();
    };

    const onInputKeydown = function (event) {
        if (event.key === 'Enter') {
            event.preventDefault();
            submitUpdate();
        } else if (event.key === 'Escape') {
            event.preventDefault();
            hideEditor();
        }
    };

    openButton.addEventListener('click', onOpenClick);
    cancelButtons.forEach(function (button) {
        button.addEventListener('click', onCancelClick);
    });
    if (overlay) {
        overlay.addEventListener('click', onOverlayClick);
    }
    saveButton.addEventListener('click', onSaveClick);
    input.addEventListener('keydown', onInputKeydown);

    return function cleanupBalanceAdjuster() {
        clearHideTimeout();
        hideEditor();
        openButton.removeEventListener('click', onOpenClick);
        cancelButtons.forEach(function (button) {
            button.removeEventListener('click', onCancelClick);
        });
        if (overlay) {
            overlay.removeEventListener('click', onOverlayClick);
        }
        saveButton.removeEventListener('click', onSaveClick);
        input.removeEventListener('keydown', onInputKeydown);
    };
}

function normalizeDashboardScope(scopeValue) {
    const value = String(scopeValue || '').toLowerCase();
    if (value === 'teams' || value === 'personal') {
        return value;
    }
    return '';
}

function buildSmoothPath(points) {
    if (!points.length) {
        return '';
    }

    if (points.length === 1) {
        return 'M ' + points[0].x.toFixed(2) + ' ' + points[0].y.toFixed(2);
    }

    let path = 'M ' + points[0].x.toFixed(2) + ' ' + points[0].y.toFixed(2);
    for (let index = 1; index < points.length; index += 1) {
        const previous = points[index - 1];
        const current = points[index];
        const dx = current.x - previous.x;
        const cp1x = previous.x + (dx * 0.45);
        const cp1y = previous.y;
        const cp2x = current.x - (dx * 0.45);
        const cp2y = current.y;
        path += ' C '
            + cp1x.toFixed(2) + ' ' + cp1y.toFixed(2) + ', '
            + cp2x.toFixed(2) + ' ' + cp2y.toFixed(2) + ', '
            + current.x.toFixed(2) + ' ' + current.y.toFixed(2);
    }

    return path;
}

function initActiveSubscriptionsScroller() {
    const viewport = document.querySelector('.js-active-subscriptions-viewport');
    if (!viewport) {
        return null;
    }

    const track = viewport.querySelector('.js-active-subscriptions-track');
    if (!track) {
        return null;
    }

    const visibleCards = Math.max(1, parseInt(viewport.dataset.visibleCards || '2', 10));
    const scrollIntervalMs = Math.max(3000, parseInt(viewport.dataset.scrollInterval || '7000', 10));
    const animationDurationMs = 450;
    const disableScroll = viewport.dataset.disableScroll === '1';

    const listeners = [];
    const listen = function (target, eventName, handler, options) {
        if (!target || typeof target.addEventListener !== 'function') {
            return;
        }
        target.addEventListener(eventName, handler, options);
        listeners.push(function () {
            target.removeEventListener(eventName, handler, options);
        });
    };

    const getCards = function () {
        return Array.from(track.children);
    };

    const resetTrackState = function () {
        track.classList.remove('is-animating');
        track.style.transition = 'none';
        track.style.transform = 'translateY(0)';
    };

    const removeClonedCards = function () {
        getCards().forEach(function (card) {
            if (!card || !card.dataset || card.dataset.dashboardClone !== '1') {
                return;
            }
            if (typeof track.removeChild === 'function') {
                track.removeChild(card);
            }
        });
    };

    const setViewportHeight = function () {
        const cards = getCards();
        if (!cards.length) {
            viewport.style.height = '0px';
            return;
        }

        if (cards.length === 1) {
            viewport.style.height = 'auto';
            return;
        }

        const lastVisibleCard = cards[Math.min(visibleCards, cards.length) - 1];
        const height = lastVisibleCard.offsetTop + lastVisibleCard.offsetHeight - cards[0].offsetTop;
        viewport.style.height = height + 'px';
    };

    resetTrackState();
    removeClonedCards();

    const prefersReducedMotion = window.matchMedia &&
        window.matchMedia('(prefers-reduced-motion: reduce)').matches;
    const cards = getCards();
    if (disableScroll || cards.length <= 1 || prefersReducedMotion) {
        setViewportHeight();
        return null;
    }

    let isAnimating = false;
    let intervalId = null;
    let rotationTimeoutId = null;

    const clearRotationTimeout = function () {
        if (rotationTimeoutId !== null) {
            window.clearTimeout(rotationTimeoutId);
            rotationTimeoutId = null;
        }
    };

    const rotateOnce = function () {
        if (isAnimating || (typeof document !== 'undefined' && document.hidden)) {
            return;
        }

        const currentCards = getCards();
        if (currentCards.length <= 1) {
            return;
        }

        const firstCard = currentCards[0];
        const secondCard = currentCards[1];
        const distance = secondCard
            ? secondCard.offsetTop - firstCard.offsetTop
            : firstCard.offsetHeight;

        if (distance <= 0) {
            return;
        }

        const needsCloneForLoop = currentCards.length <= visibleCards;
        if (needsCloneForLoop) {
            const clone = firstCard.cloneNode(true);
            if (!clone.dataset) {
                clone.dataset = {};
            }
            clone.dataset.dashboardClone = '1';
            track.appendChild(clone);
        }

        isAnimating = true;
        track.classList.add('is-animating');
        track.style.transition = 'transform ' + animationDurationMs + 'ms ease';
        track.style.transform = 'translateY(-' + distance + 'px)';

        clearRotationTimeout();
        rotationTimeoutId = window.setTimeout(function () {
            if (needsCloneForLoop) {
                track.removeChild(firstCard);
            } else {
                track.appendChild(firstCard);
            }
            track.style.transition = 'none';
            track.style.transform = 'translateY(0)';
            track.getBoundingClientRect();
            track.classList.remove('is-animating');
            isAnimating = false;
            setViewportHeight();
        }, animationDurationMs + 40);
    };

    const start = function () {
        if (intervalId !== null) {
            return;
        }
        intervalId = window.setInterval(rotateOnce, scrollIntervalMs);
    };

    const stop = function () {
        if (intervalId === null) {
            return;
        }
        window.clearInterval(intervalId);
        intervalId = null;
    };

    const onFocusOut = function (event) {
        if (viewport.contains(event.relatedTarget)) {
            return;
        }
        start();
    };

    const onVisibilityChange = function () {
        if (document.hidden) {
            stop();
            return;
        }
        start();
    };

    setViewportHeight();
    start();

    listen(viewport, 'mouseenter', stop);
    listen(viewport, 'mouseleave', start);
    listen(viewport, 'focusin', stop);
    listen(viewport, 'focusout', onFocusOut);
    listen(document, 'visibilitychange', onVisibilityChange);
    listen(window, 'resize', setViewportHeight);

    return function cleanupActiveSubscriptionsScroller() {
        stop();
        clearRotationTimeout();
        resetTrackState();
        removeClonedCards();
        setViewportHeight();
        listeners.forEach(function (removeListener) {
            removeListener();
        });
    };
}

function initDashboardOverflowGuard(rootElement) {
    if (typeof window === 'undefined') {
        return null;
    }

    const targetRoot = rootElement || (typeof document !== 'undefined'
        ? document.querySelector('.dashboard-shell')
        : null);

    if (!targetRoot) {
        return null;
    }

    const maxHorizontalOverflowPx = 8;
    let rafId = null;
    let timeoutId = null;

    const applyGuard = function () {
        const horizontalOverflow = Math.max(
            0,
            Math.ceil(targetRoot.scrollWidth - targetRoot.clientWidth),
        );

        if (horizontalOverflow > 0 && horizontalOverflow <= maxHorizontalOverflowPx) {
            targetRoot.style.overflowX = 'hidden';
            return;
        }

        targetRoot.style.removeProperty('overflow-x');
    };

    const scheduleGuard = function () {
        if (rafId !== null) {
            return;
        }
        rafId = window.requestAnimationFrame(function () {
            rafId = null;
            applyGuard();
        });
    };

    const onResize = function () {
        scheduleGuard();
    };

    const onLoad = function () {
        scheduleGuard();
    };

    scheduleGuard();
    window.addEventListener('load', onLoad);
    window.addEventListener('resize', onResize);
    timeoutId = window.setTimeout(scheduleGuard, 0);

    return function cleanupDashboardOverflowGuard() {
        if (rafId !== null) {
            window.cancelAnimationFrame(rafId);
            rafId = null;
        }
        if (timeoutId !== null) {
            window.clearTimeout(timeoutId);
            timeoutId = null;
        }

        window.removeEventListener('load', onLoad);
        window.removeEventListener('resize', onResize);
        targetRoot.style.removeProperty('overflow-x');
    };
}

if (typeof module !== 'undefined' && module.exports) {
    module.exports = {
        initDashboardPage,
        teardownDashboardPage,
        initActiveSubscriptionsScroller,
        initDashboardOverflowGuard,
        formatTrendAmount,
        updateBalanceTrendMetrics,
    };
}
