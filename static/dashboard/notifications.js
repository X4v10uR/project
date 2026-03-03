(function () {
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

    function formatTime(value) {
        if (!value) {
            return '';
        }
        const parsed = new Date(value);
        if (Number.isNaN(parsed.getTime())) {
            return '';
        }
        return parsed.toLocaleString();
    }

    function NotificationBell() {
        this.shell = document.getElementById('global-notification-shell');
        this.toggle = document.getElementById('global-notification-toggle');
        this.panel = document.getElementById('global-notification-panel');
        this.countNode = document.getElementById('global-notification-count');
        this.listNode = document.getElementById('global-notification-list');
        this.readAllBtn = document.getElementById('global-notification-read-all');
        this.notifications = [];
        this.unreadCount = 0;
        this.socket = null;
        this.pollTimer = null;

        if (!this.shell || !this.toggle || !this.panel || !this.listNode || !this.countNode) {
            return;
        }

        this.bindEvents();
        this.fetchList();
        this.startPolling();
        this.connectSocket();
    }

    NotificationBell.prototype.bindEvents = function () {
        const self = this;

        this.toggle.addEventListener('click', function (event) {
            event.preventDefault();
            const open = self.panel.classList.contains('is-open');
            if (open) {
                self.closePanel();
            } else {
                self.openPanel();
            }
        });

        document.addEventListener('click', function (event) {
            if (!self.shell.contains(event.target)) {
                self.closePanel();
            }
        });

        document.addEventListener('visibilitychange', function () {
            if (!document.hidden) {
                self.fetchList();
            }
        });

        if (this.readAllBtn) {
            this.readAllBtn.addEventListener('click', function () {
                self.markAllRead();
            });
        }
    };

    NotificationBell.prototype.startPolling = function () {
        const self = this;
        if (this.pollTimer) {
            return;
        }
        this.pollTimer = window.setInterval(function () {
            self.fetchList();
        }, 15000);
    };

    NotificationBell.prototype.stopPolling = function () {
        if (!this.pollTimer) {
            return;
        }
        window.clearInterval(this.pollTimer);
        this.pollTimer = null;
    };

    NotificationBell.prototype.openPanel = function () {
        this.panel.classList.add('is-open');
        this.toggle.setAttribute('aria-expanded', 'true');
        this.fetchList();
    };

    NotificationBell.prototype.closePanel = function () {
        this.panel.classList.remove('is-open');
        this.toggle.setAttribute('aria-expanded', 'false');
    };

    NotificationBell.prototype.setUnreadCount = function (count) {
        this.unreadCount = count;
        if (count > 0) {
            this.countNode.classList.remove('hidden');
            this.countNode.textContent = count > 99 ? '99+' : String(count);
        } else {
            this.countNode.classList.add('hidden');
            this.countNode.textContent = '0';
        }
    };

    NotificationBell.prototype.render = function () {
        if (!this.notifications.length) {
            this.listNode.innerHTML = '<p class="p-4 text-sm text-slate-500">No notifications yet.</p>';
            return;
        }

        const rows = this.notifications
            .map(function (item) {
                const baseClass = item.is_read ? 'bg-white' : 'bg-slate-50';
                return (
                    '<button type="button" class="block w-full text-left border-b border-slate-100 px-3 py-2 hover:bg-slate-100 ' + baseClass + '" data-notification-id="' + item.id + '" data-link-url="' + (item.link_url || '') + '">' +
                    '<p class="text-sm font-medium text-slate-800">' + item.title + '</p>' +
                    '<p class="text-xs text-slate-600 mt-0.5">' + (item.body || '') + '</p>' +
                    '<p class="text-[11px] text-slate-400 mt-1">' + formatTime(item.created_at) + '</p>' +
                    '</button>'
                );
            })
            .join('');

        this.listNode.innerHTML = rows;
        this.bindRows();
    };

    NotificationBell.prototype.bindRows = function () {
        const self = this;
        this.listNode.querySelectorAll('[data-notification-id]').forEach(function (node) {
            node.addEventListener('click', function () {
                const notificationId = this.getAttribute('data-notification-id');
                const linkUrl = this.getAttribute('data-link-url');
                self.markRead(notificationId).finally(function () {
                    if (linkUrl) {
                        window.location.href = linkUrl;
                    }
                });
            });
        });
    };

    NotificationBell.prototype.fetchList = function () {
        const self = this;
        return fetch('/dashboard/notifications/api/list/', {
            headers: { 'X-Requested-With': 'XMLHttpRequest' },
        })
            .then(function (response) { return response.json(); })
            .then(function (payload) {
                if (!payload.ok) {
                    return;
                }
                self.notifications = payload.notifications || [];
                self.setUnreadCount(payload.unread_count || 0);
                self.render();
            })
            .catch(function () {});
    };

    NotificationBell.prototype.markRead = function (notificationId) {
        const self = this;
        return fetch('/dashboard/notifications/api/' + notificationId + '/read/', {
            method: 'POST',
            headers: {
                'X-CSRFToken': getCookie('csrftoken') || '',
                'X-Requested-With': 'XMLHttpRequest',
            },
        })
            .then(function (response) { return response.json(); })
            .then(function (payload) {
                if (!payload.ok) {
                    return;
                }
                self.notifications = self.notifications.map(function (item) {
                    if (String(item.id) === String(notificationId)) {
                        return Object.assign({}, item, { is_read: true });
                    }
                    return item;
                });
                self.setUnreadCount(payload.unread_count || 0);
                self.render();
            })
            .catch(function () {});
    };

    NotificationBell.prototype.markAllRead = function () {
        const self = this;
        fetch('/dashboard/notifications/api/read-all/', {
            method: 'POST',
            headers: {
                'X-CSRFToken': getCookie('csrftoken') || '',
                'X-Requested-With': 'XMLHttpRequest',
            },
        })
            .then(function (response) { return response.json(); })
            .then(function (payload) {
                if (!payload.ok) {
                    return;
                }
                self.notifications = self.notifications.map(function (item) {
                    return Object.assign({}, item, { is_read: true });
                });
                self.setUnreadCount(payload.unread_count || 0);
                self.render();
            })
            .catch(function () {});
    };

    NotificationBell.prototype.connectSocket = function () {
        if (!window.WebSocket) {
            this.startPolling();
            return;
        }
        const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
        const url = protocol + '//' + window.location.host + '/ws/notifications/';
        const self = this;
        this.socket = new WebSocket(url);

        this.socket.onopen = function () {
            self.stopPolling();
            self.fetchList();
        };

        this.socket.onmessage = function (event) {
            try {
                const payload = JSON.parse(event.data);
                if (payload.type === 'notification.created' && payload.notification) {
                    self.notifications.unshift(payload.notification);
                    self.notifications = self.notifications.slice(0, 20);
                    self.setUnreadCount(payload.unread_count || 0);
                    self.render();
                    return;
                }
                if (payload.type === 'notification.updated') {
                    self.notifications = self.notifications.map(function (item) {
                        if (String(item.id) === String(payload.notification_id)) {
                            return Object.assign({}, item, { is_read: payload.is_read });
                        }
                        return item;
                    });
                    self.setUnreadCount(payload.unread_count || 0);
                    self.render();
                    return;
                }
                if (payload.type === 'notification.bulk_read') {
                    self.notifications = self.notifications.map(function (item) {
                        return Object.assign({}, item, { is_read: true });
                    });
                    self.setUnreadCount(payload.unread_count || 0);
                    self.render();
                }
            } catch (error) {
                return;
            }
        };

        this.socket.onclose = function () {
            self.startPolling();
            window.setTimeout(function () {
                self.connectSocket();
                self.fetchList();
            }, 4000);
        };
    };

    document.addEventListener('DOMContentLoaded', function () {
        new NotificationBell();
    });
})();
