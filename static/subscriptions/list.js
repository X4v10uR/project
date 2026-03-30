(function () {
    function getCookie(name) {
        let cookieValue = null;
        if (document.cookie && document.cookie !== '') {
            const cookies = document.cookie.split(';');
            for (let i = 0; i < cookies.length; i++) {
                const cookie = cookies[i].trim();
                if (cookie.substring(0, name.length + 1) === (name + '=')) {
                    cookieValue = decodeURIComponent(cookie.substring(name.length + 1));
                    break;
                }
            }
        }
        return cookieValue;
    }

    function showToast(message) {
        const toast = document.createElement('div');
        toast.style.position = 'fixed';
        toast.style.bottom = '14px';
        toast.style.right = '14px';
        toast.style.padding = '8px 12px';
        toast.style.border = '1px solid rgba(15, 23, 42, 0.15)';
        toast.style.background = 'white';
        toast.style.borderRadius = '10px';
        toast.style.boxShadow = '0 10px 30px rgba(15, 23, 42, 0.2)';
        toast.style.fontSize = '12px';
        toast.textContent = message;
        document.body.appendChild(toast);
        setTimeout(function () {
            toast.remove();
        }, 2000);
    }

    function updateStatusIndicators(wrapper, newStatus) {
        wrapper.dataset.status = newStatus;
        const btn = wrapper.querySelector('.status-btn');
        if (btn) {
            btn.dataset.currentStatus = newStatus;
        }
        const text = wrapper.querySelector('.status-text');
        if (text) {
            text.textContent = newStatus.charAt(0).toUpperCase() + newStatus.slice(1);
        }

        const dot = wrapper.querySelector('.status-dot');
        if (dot) {
            dot.classList.remove('bg-emerald-500', 'bg-amber-400', 'bg-red-400');
            if (newStatus === 'active') {
                dot.classList.add('bg-emerald-500');
            } else if (newStatus === 'paused') {
                dot.classList.add('bg-amber-400');
            } else {
                dot.classList.add('bg-red-400');
            }
        }
    }

    function syncAllStatusWrappers(subscriptionId, newStatus) {
        document.querySelectorAll('.status-dropdown-wrapper[data-subscription-id="' + subscriptionId + '"]')
            .forEach(function (wrapper) {
                updateStatusIndicators(wrapper, newStatus);
            });
        const card = document.querySelector('[data-subscription-card][data-subscription-id="' + subscriptionId + '"]');
        if (card) {
            card.dataset.status = newStatus;
        }
    }

    function setStatusPending(subscriptionId, isPending) {
        document.querySelectorAll('.status-dropdown-wrapper[data-subscription-id="' + subscriptionId + '"]')
            .forEach(function (wrapper) {
                wrapper.dataset.statusPending = isPending ? '1' : '0';
                const btn = wrapper.querySelector('.status-btn');
                if (btn) {
                    btn.disabled = isPending;
                }
                wrapper.querySelectorAll('.status-option').forEach(function (option) {
                    option.disabled = isPending;
                });
            });
    }

    function initStatusDropdowns(scope) {
        const root = scope || document;
        const wrappers = root.querySelectorAll('.status-dropdown-wrapper');
        wrappers.forEach(function (wrapper) {
            if (wrapper.dataset.dropdownInit === '1') {
                return;
            }
            wrapper.dataset.dropdownInit = '1';

            const btn = wrapper.querySelector('.status-btn');
            const menu = wrapper.querySelector('.status-menu');
            const options = wrapper.querySelectorAll('.status-option');
            const subId = wrapper.dataset.subscriptionId;
            const statusUrl = wrapper.dataset.statusUrl;

            if (!btn || !menu || !subId || !statusUrl) {
                return;
            }

            updateStatusIndicators(wrapper, btn.dataset.currentStatus || wrapper.dataset.status || 'active');

            btn.addEventListener('click', function (event) {
                event.stopPropagation();
                if (wrapper.dataset.statusPending === '1') {
                    return;
                }
                document.querySelectorAll('.status-menu').forEach(function (node) {
                    if (node !== menu) {
                        node.classList.add('hidden');
                    }
                });
                menu.classList.toggle('hidden');
            });

            options.forEach(function (option) {
                option.addEventListener('click', function (event) {
                    event.stopPropagation();
                    const newStatus = this.dataset.value;
                    const currentStatus = btn.dataset.currentStatus;

                    if (newStatus === currentStatus) {
                        menu.classList.add('hidden');
                        return;
                    }

                    if (wrapper.dataset.statusPending === '1') {
                        return;
                    }

                    setStatusPending(subId, true);
                    syncAllStatusWrappers(subId, newStatus);
                    menu.classList.add('hidden');

                    fetch(statusUrl, {
                        method: 'POST',
                        headers: {
                            'Content-Type': 'application/x-www-form-urlencoded',
                            'X-Requested-With': 'XMLHttpRequest',
                            'X-CSRFToken': getCookie('csrftoken')
                        },
                        body: 'status=' + newStatus
                    })
                        .then(function (response) { return response.json(); })
                        .then(function (data) {
                            if (data.status === 'success') {
                                syncAllStatusWrappers(subId, newStatus);
                                showToast('Status updated');
                            } else {
                                syncAllStatusWrappers(subId, currentStatus);
                                showToast('Failed to update');
                            }
                        })
                        .catch(function () {
                            syncAllStatusWrappers(subId, currentStatus);
                            showToast('Failed to update');
                        })
                        .finally(function () {
                            setStatusPending(subId, false);
                        });
                });
            });
        });
    }

    function initDrawer() {
        function getDrawerElements() {
            return {
                overlay: document.getElementById('subscription-drawer-overlay'),
                drawer: document.getElementById('subscription-drawer'),
                content: document.getElementById('subscription-drawer-content')
            };
        }

        function syncDrawerVisualState() {
            const elements = getDrawerElements();
            if (!elements.overlay || !elements.drawer || !elements.content) {
                return false;
            }
            elements.drawer.style.transform = elements.drawer.classList.contains('translate-x-0') ? 'translateX(0)' : 'translateX(100%)';
            elements.overlay.style.opacity = elements.overlay.classList.contains('opacity-100') ? '1' : '0';
            elements.overlay.style.pointerEvents = elements.overlay.classList.contains('opacity-100') ? 'auto' : 'none';
            return true;
        }

        if (!syncDrawerVisualState()) {
            return;
        }

        function openDrawer(id) {
            const elements = getDrawerElements();
            if (!elements.overlay || !elements.drawer || !elements.content) {
                return;
            }
            const overlay = elements.overlay;
            const drawer = elements.drawer;
            const content = elements.content;
            const template = document.getElementById('drawer-template-' + id);
            if (!template) {
                return;
            }
            content.innerHTML = template.innerHTML;
            drawer.classList.remove('translate-x-full');
            drawer.classList.add('translate-x-0');
            drawer.style.transform = 'translateX(0)';
            drawer.setAttribute('aria-hidden', 'false');
            overlay.classList.remove('opacity-0', 'pointer-events-none');
            overlay.classList.add('opacity-100');
            overlay.style.opacity = '1';
            overlay.style.pointerEvents = 'auto';
            overlay.setAttribute('aria-hidden', 'false');
            document.body.style.overflow = 'hidden';
            initStatusDropdowns(content);
        }

        function closeDrawer() {
            const elements = getDrawerElements();
            if (!elements.overlay || !elements.drawer) {
                return;
            }
            const overlay = elements.overlay;
            const drawer = elements.drawer;
            drawer.classList.add('translate-x-full');
            drawer.classList.remove('translate-x-0');
            drawer.style.transform = 'translateX(100%)';
            drawer.setAttribute('aria-hidden', 'true');
            overlay.classList.add('opacity-0', 'pointer-events-none');
            overlay.classList.remove('opacity-100');
            overlay.style.opacity = '0';
            overlay.style.pointerEvents = 'none';
            overlay.setAttribute('aria-hidden', 'true');
            document.body.style.overflow = '';
        }

        if (!document.body.dataset.subscriptionDrawerDelegationBound) {
            document.body.dataset.subscriptionDrawerDelegationBound = '1';

            document.addEventListener('click', function (event) {
                if (event.target && event.target.id === 'subscription-drawer-overlay') {
                    closeDrawer();
                    return;
                }
                if (event.target.closest('[data-drawer-close]')) {
                    closeDrawer();
                    return;
                }
                const card = event.target.closest('[data-subscription-card]');
                if (!card) {
                    return;
                }
                if (event.target.closest('[data-drawer-ignore]')) {
                    return;
                }
                openDrawer(card.dataset.subscriptionId);
            });

            document.addEventListener('keydown', function (event) {
                if (event.key !== 'Enter' && event.key !== ' ') {
                    return;
                }
                const card = event.target.closest('[data-subscription-card]');
                if (!card) {
                    return;
                }
                if (event.target.closest('[data-drawer-ignore]')) {
                    return;
                }
                if (
                    event.target !== card
                    && event.target.closest('a,button,input,select,textarea,[role="button"],[role="link"]')
                ) {
                    return;
                }
                event.preventDefault();
                openDrawer(card.dataset.subscriptionId);
            });
            document.addEventListener('keydown', function (event) {
                if (event.key === 'Escape') {
                    closeDrawer();
                }
            });
        }
    }

    function initFilterToggle() {
        const toggle = document.getElementById('subscriptions-filter-toggle');
        const panel = document.getElementById('subscriptions-filter-panel');
        if (!toggle || !panel) {
            return;
        }
        if (toggle.dataset.toggleInit === '1') {
            return;
        }
        toggle.dataset.toggleInit = '1';
        const syncToggleState = function () {
            const isOpen = !panel.classList.contains('hidden');
            toggle.setAttribute('aria-expanded', isOpen ? 'true' : 'false');
            toggle.classList.toggle('is-active', isOpen);
        };
        syncToggleState();
        toggle.addEventListener('click', function () {
            panel.classList.toggle('hidden');
            syncToggleState();
        });
    }

    function initPage() {
        if (!document.getElementById('subscriptions-page')) {
            return;
        }
        initStatusDropdowns(document);
        initDrawer();
        initFilterToggle();
    }

    if (!window.__sublyStatusDropdownDocClickBound) {
        document.addEventListener('click', function (event) {
            if (!event.target.closest('.status-dropdown-wrapper')) {
                document.querySelectorAll('.status-menu').forEach(function (menu) {
                    menu.classList.add('hidden');
                });
            }
        });
        window.__sublyStatusDropdownDocClickBound = true;
    }

    if (!window.__sublySubscriptionsPageInit) {
        document.addEventListener('subly:content-loaded', initPage);
        window.__sublySubscriptionsPageInit = true;
    }

    initPage();
})();
