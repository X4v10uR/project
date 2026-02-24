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
                .filter(function (value) { return Number.isFinite(value); });
        }
    } catch (error) {
        points = [];
    }

    if (!points.length) {
        return;
    }

    if (points.length === 1) {
        points = [points[0], points[0]];
    }

    const min = Math.min.apply(null, points);
    const max = Math.max.apply(null, points);
    const range = max - min || 1;

    const width = 100;
    const height = 32;
    const topPadding = 2;
    const bottomPadding = 3;
    const leftPadding = 2;
    const rightPadding = 2;
    const graphWidth = width - leftPadding - rightPadding;
    const graphHeight = height - topPadding - bottomPadding;
    const stepX = points.length > 1 ? graphWidth / (points.length - 1) : graphWidth;

    const coordinates = points.map(function (point, index) {
        const ratio = (point - min) / range;
        return {
            x: leftPadding + (stepX * index),
            y: topPadding + (graphHeight * (1 - ratio)),
        };
    });

    const linePath = coordinates
        .map(function (point, index) {
            const command = index === 0 ? 'M' : 'L';
            return command + ' ' + point.x.toFixed(2) + ' ' + point.y.toFixed(2);
        })
        .join(' ');

    const firstPoint = coordinates[0];
    const lastPoint = coordinates[coordinates.length - 1];
    const floorY = (height - bottomPadding).toFixed(2);
    const areaPath = linePath
        + ' L ' + lastPoint.x.toFixed(2) + ' ' + floorY
        + ' L ' + firstPoint.x.toFixed(2) + ' ' + floorY
        + ' Z';
    const gradientId = 'balance-trend-fill-' + Math.random().toString(36).slice(2, 9);

    chart.innerHTML = [
        '<defs>',
        '  <linearGradient id="' + gradientId + '" x1="0" y1="0" x2="0" y2="1">',
        '    <stop offset="0%" stop-color="rgba(96, 165, 250, 0.32)" />',
        '    <stop offset="100%" stop-color="rgba(96, 165, 250, 0)" />',
        '  </linearGradient>',
        '</defs>',
        '<path d="' + areaPath + '" fill="url(#' + gradientId + ')" />',
        '<path d="' + linePath + '" fill="none" stroke="#93c5fd" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round" />',
        '<circle cx="' + lastPoint.x.toFixed(2) + '" cy="' + lastPoint.y.toFixed(2) + '" r="1.8" fill="#bfdbfe" />',
    ].join('');
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
