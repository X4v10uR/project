document.addEventListener('DOMContentLoaded', function () {
    document.querySelectorAll('.js-clickable-card').forEach(function (card) {
        card.addEventListener('click', function () {
            const url = this.getAttribute('data-url');
            if (url) {
                window.location.href = url;
            }
        });
    });

    document.querySelectorAll('a[href^="#"]').forEach(function (anchor) {
        anchor.addEventListener('click', function (event) {
            event.preventDefault();
            const target = document.querySelector(this.getAttribute('href'));
            if (target) {
                target.scrollIntoView({ behavior: 'smooth' });
            }
        });
    });

    initBalanceTrendChart();
    initBalanceTrendToggle();
    initActiveSubscriptionsScroller();
});

function initBalanceTrendChart() {
    const chart = document.querySelector('.js-balance-trend-graph');
    const dataNode = document.getElementById('balance-trend-points');
    if (!chart || !dataNode) {
        return;
    }

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
        updateBalanceTrendMetrics([]);
        return;
    }

    if (points.length === 1) {
        points = [points[0], points[0]];
    }

    updateBalanceTrendMetrics(points);

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

function updateBalanceTrendMetrics(points) {
    const totalNode = document.querySelector('.js-balance-trend-total');
    const peakNode = document.querySelector('.js-balance-trend-peak');
    const activeNode = document.querySelector('.js-balance-trend-active');
    if (!totalNode || !peakNode || !activeNode) {
        return;
    }

    if (!points.length) {
        totalNode.textContent = '$0.00';
        peakNode.textContent = '$0.00';
        activeNode.textContent = '0/0';
        return;
    }

    const total = points.reduce(function (sum, value) { return sum + value; }, 0);
    const peak = Math.max.apply(null, points);
    const activeDays = points.filter(function (value) { return value > 0; }).length;

    totalNode.textContent = formatTrendAmount(total);
    peakNode.textContent = formatTrendAmount(peak);
    activeNode.textContent = String(activeDays) + '/' + String(points.length);
}

function formatTrendAmount(value) {
    if (typeof value !== 'number' || !isFinite(value)) {
        return '$0.00';
    }

    if (Math.abs(value) >= 1000) {
        return '$' + value.toLocaleString(undefined, { maximumFractionDigits: 0 });
    }
    return '$' + value.toFixed(2);
}

function initBalanceTrendToggle() {
    const toggle = document.querySelector('.js-balance-trend-toggle');
    const panel = document.querySelector('.js-balance-trend-panel');
    if (!toggle || !panel) {
        return;
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

    applyState();

    toggle.addEventListener('click', function () {
        isCollapsed = !isCollapsed;
        applyState();
        try {
            window.localStorage.setItem(storageKey, isCollapsed ? '1' : '0');
        } catch (error) {
            // Ignore storage write errors (private mode / blocked storage).
        }
    });
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
        return;
    }

    const track = viewport.querySelector('.js-active-subscriptions-track');
    if (!track) {
        return;
    }

    const visibleCards = Math.max(1, parseInt(viewport.dataset.visibleCards || '2', 10));
    const scrollIntervalMs = Math.max(3000, parseInt(viewport.dataset.scrollInterval || '7000', 10));
    const animationDurationMs = 450;

    const getCards = function () {
        return Array.from(track.children);
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

    const prefersReducedMotion = window.matchMedia &&
        window.matchMedia('(prefers-reduced-motion: reduce)').matches;
    const cards = getCards();
    if (cards.length <= 1 || prefersReducedMotion) {
        setViewportHeight();
        return;
    }

    let isAnimating = false;
    let intervalId = null;

    const rotateOnce = function () {
        if (isAnimating || document.hidden) {
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
            track.appendChild(firstCard.cloneNode(true));
        }

        isAnimating = true;
        track.classList.add('is-animating');
        track.style.transition = 'transform ' + animationDurationMs + 'ms ease';
        track.style.transform = 'translateY(-' + distance + 'px)';

        window.setTimeout(function () {
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

    setViewportHeight();
    start();

    viewport.addEventListener('mouseenter', stop);
    viewport.addEventListener('mouseleave', start);
    viewport.addEventListener('focusin', stop);
    viewport.addEventListener('focusout', function (event) {
        if (viewport.contains(event.relatedTarget)) {
            return;
        }
        start();
    });

    document.addEventListener('visibilitychange', function () {
        if (document.hidden) {
            stop();
            return;
        }
        start();
    });

    window.addEventListener('resize', setViewportHeight);
}
