(function () {
    function getCookie(name) {
        if (!document.cookie) {
            return null;
        }
        var cookies = document.cookie.split(';');
        for (var i = 0; i < cookies.length; i += 1) {
            var cookie = cookies[i].trim();
            if (cookie.substring(0, name.length + 1) === name + '=') {
                return decodeURIComponent(cookie.substring(name.length + 1));
            }
        }
        return null;
    }

    function setVisible(node, visible) {
        if (!node) {
            return;
        }
        if (visible) {
            node.classList.remove('is-hidden');
        } else {
            node.classList.add('is-hidden');
        }
    }

    function initOverviewMode() {
        var root = document.getElementById('teams-overview-root');
        if (!root) {
            return;
        }

        var overviewPane = root.querySelector('[data-teams-overview-pane]');
        var createPane = root.querySelector('[data-teams-create-pane]');
        var openButtons = root.querySelectorAll('[data-teams-open-create]');
        var closeButtons = root.querySelectorAll('[data-teams-close-create]');
        var overviewUrl = root.getAttribute('data-overview-url') || '/accounts/teams/';
        var createUrl = root.getAttribute('data-create-url') || '/accounts/teams/create/';
        var initialMode = root.getAttribute('data-teams-mode') || 'overview';

        function setMode(mode, syncHistory) {
            var safeMode = mode === 'create' ? 'create' : 'overview';
            root.setAttribute('data-teams-mode', safeMode);
            setVisible(overviewPane, safeMode !== 'create');
            setVisible(createPane, safeMode === 'create');

            if (!syncHistory || !window.history || !window.history.pushState) {
                return;
            }

            var target = safeMode === 'create' ? createUrl : overviewUrl;
            if (window.location.pathname !== target) {
                window.history.pushState({ teamsMode: safeMode }, '', target);
            }
        }

        openButtons.forEach(function (button) {
            button.addEventListener('click', function (event) {
                event.preventDefault();
                setMode('create', true);
            });
        });

        closeButtons.forEach(function (button) {
            button.addEventListener('click', function (event) {
                event.preventDefault();
                setMode('overview', true);
            });
        });

        window.addEventListener('popstate', function () {
            if (window.location.pathname === createUrl) {
                setMode('create', false);
            } else {
                setMode('overview', false);
            }
        });

        setMode(initialMode, false);
    }

    function initCreateCounter() {
        var input = document.getElementById('teams-create-name');
        var count = document.getElementById('teams-create-count');
        var error = document.getElementById('teams-create-error');

        if (!input || !count) {
            return;
        }

        function updateCount() {
            count.textContent = String(input.value.length) + '/120';
            if (error && input.value.trim()) {
                error.textContent = '';
            }
        }

        input.addEventListener('input', updateCount);
        updateCount();
    }

    function initTeamFilters() {
        var chips = document.querySelectorAll('[data-team-filter]');
        var rows = document.querySelectorAll('[data-team-row]');
        var emptyRow = document.querySelector('[data-team-empty]');
        if (!chips.length || !rows.length) {
            return;
        }

        function applyFilter(filterValue) {
            var visibleCount = 0;
            rows.forEach(function (row) {
                var rowTeam = row.getAttribute('data-team-row');
                var visible = filterValue === 'all' || rowTeam === filterValue;
                row.classList.toggle('teams-hidden', !visible);
                if (visible) {
                    visibleCount += 1;
                }
            });

            if (emptyRow) {
                emptyRow.classList.toggle('teams-hidden', visibleCount !== 0);
            }

            chips.forEach(function (chip) {
                chip.classList.toggle('is-active', chip.getAttribute('data-team-filter') === filterValue);
            });
        }

        chips.forEach(function (chip) {
            chip.addEventListener('click', function () {
                var value = chip.getAttribute('data-team-filter') || 'all';
                applyFilter(value);
            });
        });

        var activeChip = document.querySelector('[data-team-filter].is-active');
        applyFilter(activeChip ? activeChip.getAttribute('data-team-filter') : 'all');
    }

    function initRevealPasswords() {
        var buttons = document.querySelectorAll('.js-reveal-team-password');
        if (!buttons.length) {
            return;
        }

        buttons.forEach(function (button) {
            button.addEventListener('click', function () {
                var targetId = button.getAttribute('data-target');
                var revealUrl = button.getAttribute('data-url') || '';
                var target = targetId ? document.getElementById(targetId) : null;
                var currentlyRevealed = button.getAttribute('data-revealed') === 'true';

                if (!target) {
                    return;
                }

                if (currentlyRevealed) {
                    target.textContent = '••••••••';
                    button.setAttribute('data-revealed', 'false');
                    button.textContent = 'Reveal';
                    return;
                }

                if (!revealUrl) {
                    return;
                }

                button.disabled = true;
                fetch(revealUrl, {
                    method: 'POST',
                    headers: {
                        'X-CSRFToken': getCookie('csrftoken') || '',
                        'X-Requested-With': 'XMLHttpRequest'
                    }
                })
                    .then(function (response) { return response.json(); })
                    .then(function (payload) {
                        if (!payload.ok || !payload.password) {
                            return;
                        }
                        target.textContent = payload.password;
                        button.setAttribute('data-revealed', 'true');
                        button.textContent = 'Hide';
                    })
                    .catch(function () {})
                    .finally(function () {
                        button.disabled = false;
                    });
            });
        });
    }

    function initToggleBox(triggerId, boxId, cancelId) {
        var trigger = document.getElementById(triggerId);
        var box = document.getElementById(boxId);
        var cancel = document.getElementById(cancelId);

        if (trigger && box) {
            trigger.addEventListener('click', function () {
                box.classList.toggle('is-open');
            });
        }

        if (cancel && box) {
            cancel.addEventListener('click', function () {
                box.classList.remove('is-open');
            });
        }
    }

    function bootTeamsModule() {
        var teamsShell = document.querySelector('.teams-shell');
        if (!teamsShell || teamsShell.dataset.teamsModuleInit === '1') {
            return;
        }
        teamsShell.dataset.teamsModuleInit = '1';

        initOverviewMode();
        initCreateCounter();
        initTeamFilters();
        initRevealPasswords();
        initToggleBox('delete-team-trigger', 'delete-team-confirm', 'delete-team-cancel');
        initToggleBox('leave-team-trigger', 'leave-team-confirm', 'leave-team-cancel');
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', bootTeamsModule);
    } else {
        bootTeamsModule();
    }

    document.addEventListener('subly:content-loaded', bootTeamsModule);
})();
