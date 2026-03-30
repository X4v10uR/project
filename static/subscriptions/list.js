(function () {
    let drawerSubscriptionsById = {};

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

    function statusLabel(statusValue) {
        if (statusValue === 'active') {
            return 'Active';
        }
        if (statusValue === 'paused') {
            return 'Paused';
        }
        if (statusValue === 'cancelled') {
            return 'Cancelled';
        }
        return 'Active';
    }

    function setSubscriptionStatusInPayload(subscriptionId, statusValue) {
        const key = String(subscriptionId || '');
        if (!key || !drawerSubscriptionsById[key]) {
            return;
        }
        drawerSubscriptionsById[key].status = statusValue;
        drawerSubscriptionsById[key].status_display = statusLabel(statusValue);
    }

    function updateStatusIndicators(wrapper, newStatus) {
        wrapper.dataset.status = newStatus;
        const btn = wrapper.querySelector('.status-btn');
        if (btn) {
            btn.dataset.currentStatus = newStatus;
        }
        const text = wrapper.querySelector('.status-text');
        if (text) {
            text.textContent = statusLabel(newStatus);
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

    function syncSubscriptionCardStatus(subscriptionId, statusValue) {
        document.querySelectorAll('.subscription-card[data-subscription-id="' + subscriptionId + '"]')
            .forEach(function (card) {
                card.dataset.status = statusValue;
            });
    }

    function syncAllStatusWrappers(subscriptionId, newStatus) {
        document.querySelectorAll('.status-dropdown-wrapper[data-subscription-id="' + subscriptionId + '"]')
            .forEach(function (wrapper) {
                updateStatusIndicators(wrapper, newStatus);
            });
        syncSubscriptionCardStatus(subscriptionId, newStatus);
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
            const btn = wrapper.querySelector('.status-btn');
            const menu = wrapper.querySelector('.status-menu');
            const options = wrapper.querySelectorAll('.status-option');

            if (!btn || !menu || !options.length) {
                return;
            }
            wrapper.dataset.dropdownInit = '1';

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
                    const subId = wrapper.dataset.subscriptionId;
                    const statusUrl = wrapper.dataset.statusUrl;

                    if (newStatus === currentStatus) {
                        menu.classList.add('hidden');
                        return;
                    }
                    if (wrapper.dataset.statusPending === '1') {
                        return;
                    }
                    if (!subId || !statusUrl) {
                        showToast('Unable to update status');
                        menu.classList.add('hidden');
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
                                setSubscriptionStatusInPayload(subId, newStatus);
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

    function formatAmount(currency, rawValue) {
        const amount = Number(rawValue || 0);
        if (!Number.isFinite(amount)) {
            return currency === 'USD' ? '$0.00' : (currency || 'USD') + ' 0.00';
        }
        if (currency === 'USD') {
            return '$' + amount.toFixed(2);
        }
        return (currency || 'USD') + ' ' + amount.toFixed(2);
    }

    function formatPeople(count) {
        const safeCount = Number(count || 0);
        if (!Number.isFinite(safeCount) || safeCount <= 1) {
            return 'Only me';
        }
        return safeCount + ' people';
    }

    function billingCyclePeriod(billingCycleValue) {
        if (billingCycleValue === 'weekly') {
            return '/week';
        }
        if (billingCycleValue === 'yearly') {
            return '/year';
        }
        return '/month';
    }

    function readDrawerPayload() {
        const payloadNode = document.getElementById('subscription-drawer-data');
        if (!payloadNode) {
            drawerSubscriptionsById = {};
            return;
        }
        try {
            const parsed = JSON.parse(payloadNode.textContent || '{}');
            if (parsed && typeof parsed === 'object') {
                drawerSubscriptionsById = parsed;
            } else {
                drawerSubscriptionsById = {};
            }
        } catch (error) {
            drawerSubscriptionsById = {};
        }
    }

    function renewalTextFromSubscription(subscription) {
        const dateDisplay = subscription.renewal_date_display || 'No renewal date';
        const days = subscription.days_until_renewal;
        if (days === null || typeof days === 'undefined') {
            return 'Next renewal: ' + dateDisplay;
        }
        if (days < 0) {
            return 'Next renewal: ' + dateDisplay + ' (Overdue)';
        }
        if (days === 0) {
            return 'Next renewal: ' + dateDisplay + ' (Today)';
        }
        return 'Next renewal: ' + dateDisplay + ' (' + days + ' day' + (days === 1 ? '' : 's') + ' left)';
    }

    function renderDrawerHistory(container, historyItems) {
        if (!container) {
            return;
        }
        container.innerHTML = '';

        if (!historyItems || !historyItems.length) {
            const emptyNode = document.createElement('div');
            emptyNode.className = 'subscription-drawer-history-empty';
            emptyNode.textContent = 'No payment history yet.';
            container.appendChild(emptyNode);
            return;
        }

        historyItems.forEach(function (item) {
            const historyItem = document.createElement('div');
            historyItem.className = 'subscription-drawer-history-item';
            historyItem.innerHTML =
                '<div class="subscription-drawer-history-main">' +
                    '<span class="subscription-drawer-history-check" aria-hidden="true">' +
                        '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round">' +
                            '<polyline points="20 6 9 17 4 12"></polyline>' +
                        '</svg>' +
                    '</span>' +
                    '<div>' +
                        '<p class="subscription-drawer-history-date"></p>' +
                        '<p class="subscription-drawer-history-copy">Successful transaction</p>' +
                    '</div>' +
                '</div>' +
                '<span class="subscription-drawer-history-amount"></span>';

            const dateNode = historyItem.querySelector('.subscription-drawer-history-date');
            const amountNode = historyItem.querySelector('.subscription-drawer-history-amount');
            if (dateNode) {
                dateNode.textContent = item.charged_for_date_display || 'Unknown date';
            }
            if (amountNode) {
                amountNode.textContent = item.amount_display || formatAmount(item.currency, item.amount);
            }
            container.appendChild(historyItem);
        });
    }

    function initSubscriptionDrawer() {
        const page = document.getElementById('subscriptions-page');
        const drawer = document.getElementById('subscription-drawer');
        const overlay = document.getElementById('subscription-drawer-overlay');
        const closeButton = document.getElementById('subscription-drawer-close');
        if (!page || !drawer || !overlay || !closeButton) {
            window.__sublyCloseSubscriptionsDrawer = null;
            return;
        }

        readDrawerPayload();

        const statusWrapper = document.getElementById('subscription-drawer-status-wrapper');
        const serviceImage = document.getElementById('subscription-drawer-service-image');
        const serviceFallback = document.getElementById('subscription-drawer-service-fallback');
        const serviceBadge = document.getElementById('subscription-drawer-service-badge');
        const titleNode = document.getElementById('subscription-drawer-title');
        const planChip = document.getElementById('subscription-drawer-plan-chip');
        const sharedChip = document.getElementById('subscription-drawer-shared-chip');
        const renewalNode = document.getElementById('subscription-drawer-renewal-text');
        const shareAmountNode = document.getElementById('subscription-drawer-share-amount');
        const sharePeriodNode = document.getElementById('subscription-drawer-share-period');
        const shareBarFill = document.getElementById('subscription-drawer-share-bar-fill');
        const shareCopyNode = document.getElementById('subscription-drawer-share-copy');
        const categoryNode = document.getElementById('subscription-drawer-category');
        const participantsNode = document.getElementById('subscription-drawer-participants');
        const emailNode = document.getElementById('subscription-drawer-email');
        const cardLast4Node = document.getElementById('subscription-drawer-card-last4');
        const cardBrandNode = document.getElementById('subscription-drawer-card-brand');
        const billingCycleNode = document.getElementById('subscription-drawer-billing-cycle');
        const historyNode = document.getElementById('subscription-drawer-history');
        const editLink = document.getElementById('subscription-drawer-edit-link');
        const deleteLink = document.getElementById('subscription-drawer-delete-link');

        let activeSubscriptionId = '';

        function lockBodyScroll() {
            if (document.body.dataset.sublyDrawerScrollLock === '1') {
                return;
            }
            document.body.dataset.sublyDrawerPreviousOverflow = document.body.style.overflow || '';
            document.body.style.overflow = 'hidden';
            document.body.dataset.sublyDrawerScrollLock = '1';
        }

        function unlockBodyScroll() {
            if (document.body.dataset.sublyDrawerScrollLock !== '1') {
                return;
            }
            document.body.style.overflow = document.body.dataset.sublyDrawerPreviousOverflow || '';
            delete document.body.dataset.sublyDrawerPreviousOverflow;
            delete document.body.dataset.sublyDrawerScrollLock;
        }

        function closeDrawer() {
            drawer.classList.remove('translate-x-0');
            drawer.classList.add('translate-x-full');
            overlay.classList.remove('opacity-100');
            overlay.classList.add('opacity-0');
            drawer.setAttribute('aria-hidden', 'true');
            overlay.setAttribute('aria-hidden', 'true');
            drawer.querySelectorAll('.status-menu').forEach(function (menu) {
                menu.classList.add('hidden');
            });
            activeSubscriptionId = '';
            if (statusWrapper) {
                statusWrapper.dataset.subscriptionId = '';
                statusWrapper.dataset.statusUrl = '';
            }
            unlockBodyScroll();
        }

        function populateDrawer(subscription) {
            if (!subscription) {
                return;
            }

            if (titleNode) {
                titleNode.textContent = subscription.service_name || 'Subscription';
            }
            if (serviceImage) {
                serviceImage.src = subscription.icon_url || '';
                serviceImage.alt = (subscription.service_name || 'Subscription') + ' logo';
                serviceImage.style.display = subscription.icon_url ? 'block' : 'none';
                serviceImage.onerror = function () {
                    serviceImage.style.display = 'none';
                    if (serviceFallback) {
                        serviceFallback.style.display = 'flex';
                    }
                };
            }
            if (serviceFallback) {
                serviceFallback.textContent = subscription.fallback_icon || 'S';
                serviceFallback.style.display = subscription.icon_url ? 'none' : 'flex';
            }
            if (serviceBadge) {
                const badgeText = (subscription.category || 'Sub').trim();
                serviceBadge.textContent = (badgeText.slice(0, 3) || 'SUB').toUpperCase();
            }

            if (planChip) {
                if (subscription.plan_name) {
                    planChip.textContent = subscription.plan_name;
                    planChip.style.display = 'inline-flex';
                } else {
                    planChip.style.display = 'none';
                }
            }
            if (sharedChip) {
                sharedChip.style.display = subscription.is_shared ? 'inline-flex' : 'none';
            }
            if (renewalNode) {
                renewalNode.textContent = renewalTextFromSubscription(subscription);
            }

            if (shareAmountNode) {
                shareAmountNode.textContent = subscription.user_cost_display || formatAmount(subscription.currency, subscription.user_cost);
            }
            if (sharePeriodNode) {
                sharePeriodNode.textContent = billingCyclePeriod(subscription.billing_cycle);
            }
            if (shareBarFill) {
                shareBarFill.style.width = String(subscription.share_percent || 0) + '%';
            }
            if (shareCopyNode) {
                if (subscription.is_shared) {
                    shareCopyNode.textContent =
                        'This accounts for ' + (subscription.share_percent || 0) + '% of the total plan cost (' +
                        (subscription.cost_display || formatAmount(subscription.currency, subscription.cost)) + ').';
                } else {
                    shareCopyNode.textContent =
                        'You cover the full plan cost (' +
                        (subscription.cost_display || formatAmount(subscription.currency, subscription.cost)) + ').';
                }
            }

            if (categoryNode) {
                categoryNode.textContent = subscription.category || 'Uncategorized';
            }
            if (participantsNode) {
                participantsNode.textContent = formatPeople(subscription.total_people);
            }
            if (emailNode) {
                emailNode.textContent = subscription.account_email || 'Not set';
            }
            if (cardLast4Node) {
                cardLast4Node.textContent = subscription.has_card ? ('•••• ' + (subscription.card_last4 || '')) : 'Not linked';
            }
            if (cardBrandNode) {
                if (subscription.card_brand) {
                    cardBrandNode.textContent = subscription.card_brand;
                    cardBrandNode.style.display = 'inline-flex';
                } else {
                    cardBrandNode.style.display = 'none';
                }
            }
            if (billingCycleNode) {
                billingCycleNode.textContent = subscription.billing_cycle_detail || subscription.billing_cycle_display || '--';
            }

            if (editLink) {
                editLink.href = subscription.edit_url || '#';
            }
            if (deleteLink) {
                deleteLink.href = subscription.delete_url || '#';
            }

            if (statusWrapper) {
                statusWrapper.dataset.subscriptionId = String(subscription.id || '');
                statusWrapper.dataset.status = subscription.status || 'active';
                statusWrapper.dataset.statusUrl = subscription.status_url || '';
                const statusButton = statusWrapper.querySelector('.status-btn');
                if (statusButton) {
                    statusButton.dataset.currentStatus = subscription.status || 'active';
                }
                updateStatusIndicators(statusWrapper, subscription.status || 'active');
            }

            renderDrawerHistory(historyNode, subscription.history || []);
        }

        function openDrawer(subscriptionId) {
            const key = String(subscriptionId || '');
            const subscription = drawerSubscriptionsById[key];
            if (!subscription) {
                return;
            }
            activeSubscriptionId = key;
            populateDrawer(subscription);
            drawer.classList.remove('translate-x-full');
            drawer.classList.add('translate-x-0');
            overlay.classList.remove('opacity-0');
            overlay.classList.add('opacity-100');
            drawer.setAttribute('aria-hidden', 'false');
            overlay.setAttribute('aria-hidden', 'false');
            lockBodyScroll();
            initStatusDropdowns(drawer);
        }

        function shouldIgnoreCardOpen(target) {
            if (!target || !target.closest) {
                return false;
            }
            if (target.closest('.status-dropdown-wrapper')) {
                return true;
            }
            return Boolean(target.closest('a, button, input, textarea, select, label, form'));
        }

        if (page.dataset.drawerInit !== '1') {
            page.dataset.drawerInit = '1';

            page.addEventListener('click', function (event) {
                const card = event.target.closest('.subscription-card[data-subscription-id]');
                if (!card || !page.contains(card)) {
                    return;
                }
                if (shouldIgnoreCardOpen(event.target)) {
                    return;
                }
                openDrawer(card.dataset.subscriptionId);
            });

            page.addEventListener('keydown', function (event) {
                if (event.key !== 'Enter' && event.key !== ' ') {
                    return;
                }
                const card = event.target.closest('.subscription-card[data-subscription-id]');
                if (!card || !page.contains(card)) {
                    return;
                }
                event.preventDefault();
                openDrawer(card.dataset.subscriptionId);
            });
        }

        if (overlay.dataset.drawerCloseInit !== '1') {
            overlay.dataset.drawerCloseInit = '1';
            overlay.addEventListener('click', closeDrawer);
        }
        if (closeButton.dataset.drawerCloseInit !== '1') {
            closeButton.dataset.drawerCloseInit = '1';
            closeButton.addEventListener('click', closeDrawer);
        }

        window.__sublyCloseSubscriptionsDrawer = closeDrawer;
        window.__sublyOpenSubscriptionsDrawer = openDrawer;
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
            if (document.body.dataset.sublyDrawerScrollLock === '1') {
                document.body.style.overflow = document.body.dataset.sublyDrawerPreviousOverflow || '';
                delete document.body.dataset.sublyDrawerPreviousOverflow;
                delete document.body.dataset.sublyDrawerScrollLock;
            }
            window.__sublyCloseSubscriptionsDrawer = null;
            window.__sublyOpenSubscriptionsDrawer = null;
            return;
        }
        initStatusDropdowns(document);
        initFilterToggle();
        initSubscriptionDrawer();
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

    if (!window.__sublySubscriptionsDrawerEscapeBound) {
        document.addEventListener('keydown', function (event) {
            if (event.key !== 'Escape') {
                return;
            }
            if (typeof window.__sublyCloseSubscriptionsDrawer === 'function') {
                window.__sublyCloseSubscriptionsDrawer();
            }
        });
        window.__sublySubscriptionsDrawerEscapeBound = true;
    }

    if (!window.__sublySubscriptionsPageInit) {
        document.addEventListener('subly:content-loaded', initPage);
        window.__sublySubscriptionsPageInit = true;
    }

    if (!window.__sublySubscriptionsPageHtmxSwapInit && window.htmx) {
        document.body.addEventListener('htmx:afterSwap', function (event) {
            if (event && event.detail && event.detail.target && event.detail.target.id === 'app-content') {
                initPage();
            }
        });
        window.__sublySubscriptionsPageHtmxSwapInit = true;
    }

    initPage();
})();
