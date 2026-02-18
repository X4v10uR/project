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

    initActiveSubscriptionsScroller();
});

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
