(function () {
    'use strict';

    var ICON_MAP = {
        friend_request: '\u{1F465}',
        friend_accept: '\u{1F91D}',
        new_message: '\u{1F4AC}',
        level_up: '\u2B06',
        achievement: '\u{1F3C5}',
        daily_reward: '\u{1F381}',
        new_follower: '\u2795',
        streak_broken: '\u{1F494}',
        streak_shield: '\u{1F6E1}',
        system: '\u{1F514}',
        new_blog_post: '\u{1F4DD}',
        blog_comment: '\u{1F4AC}',
        forum_reply: '\u21A9',
        forum_mention: '@',
        order_update: '\u{1F4E6}',
        ad_status: '\u{1F4E2}',
        new_review: '\u2B50',
        mission_assigned: '\u{1F3AF}'
    };

    function getCsrfToken() {
        var tokenInput = document.querySelector('input[name="csrfmiddlewaretoken"]');
        if (tokenInput) return tokenInput.value;
        var match = document.cookie.match(/(?:^|;\s*)csrftoken=([^;]*)/);
        return match ? decodeURIComponent(match[1]) : '';
    }

    function timeAgo(dateStr) {
        var diff = (Date.now() - new Date(dateStr).getTime()) / 1000;
        if (diff < 60) return Math.max(1, Math.floor(diff)) + 's ago';
        diff /= 60;
        if (diff < 60) return Math.floor(diff) + 'm ago';
        diff /= 60;
        if (diff < 24) return Math.floor(diff) + 'h ago';
        diff /= 24;
        if (diff < 30) return Math.floor(diff) + 'd ago';
        diff /= 30;
        return Math.floor(diff) + 'mo ago';
    }

    function renderItem(n) {
        var icon = ICON_MAP[n.notif_type] || '\u{1F514}';
        var cls = 'notif-dd-item' + (n.is_read ? '' : ' unread');
        var url = n.action_url || '#';
        var el = document.createElement('a');
        el.className = cls;
        el.href = '#';
        el.setAttribute('data-notif-id', n.id);
        el.innerHTML =
            '<span class="notif-dd-icon">' + icon + '</span>' +
            '<div class="notif-dd-body">' +
                '<div class="notif-dd-item-title">' + escapeHtml(n.title) + '</div>' +
                '<div class="notif-dd-item-msg">' + escapeHtml(truncate(n.message, 80)) + '</div>' +
                '<div class="notif-dd-item-time">' + timeAgo(n.created_at) + '</div>' +
            '</div>';
        el.addEventListener('click', function (e) {
            e.preventDefault();
            markRead(n.id, function () {
                if (url && url !== '#') window.location.href = url;
            });
        });
        return el;
    }

    function escapeHtml(str) {
        var d = document.createElement('div');
        d.textContent = str || '';
        return d.innerHTML;
    }

    function truncate(str, max) {
        if (!str) return '';
        return str.length > max ? str.substring(0, max) + '\u2026' : str;
    }

    function markRead(id, cb) {
        fetch('/community/notifications/read/' + id + '/', {
            method: 'POST',
            headers: { 'X-CSRFToken': getCsrfToken(), 'Content-Type': 'application/json' },
            credentials: 'same-origin'
        }).then(function () { if (cb) cb(); }).catch(function () { if (cb) cb(); });
    }

    function initNotificationBell() {
        var bellBtn = document.getElementById('notif-bell-btn');
        var badge = document.getElementById('notif-bell-badge');
        var dropdown = document.getElementById('notif-bell-dropdown');
        var list = document.getElementById('notif-bell-list');
        var markAllBtn = document.getElementById('notif-dd-mark-all');

        if (!bellBtn || !dropdown) return;

        // Populate server-rendered icons
        var iconSpans = list.querySelectorAll('.notif-dd-icon[data-type]');
        iconSpans.forEach(function (span) {
            var type = span.getAttribute('data-type');
            span.textContent = ICON_MAP[type] || '\u{1F514}';
        });

        // Toggle dropdown
        bellBtn.addEventListener('click', function (e) {
            e.stopPropagation();
            var isOpen = dropdown.classList.toggle('active');
            if (isOpen) fetchRecent();
        });

        // Close on outside click
        document.addEventListener('click', function (e) {
            if (!dropdown.contains(e.target) && e.target !== bellBtn) {
                dropdown.classList.remove('active');
            }
        });

        // Mark all read
        if (markAllBtn) {
            markAllBtn.addEventListener('click', function (e) {
                e.stopPropagation();
                fetch('/community/notifications/read-all/', {
                    method: 'POST',
                    headers: { 'X-CSRFToken': getCsrfToken(), 'Content-Type': 'application/json' },
                    credentials: 'same-origin'
                }).then(function () {
                    updateBadge(0);
                    list.querySelectorAll('.notif-dd-item.unread').forEach(function (el) {
                        el.classList.remove('unread');
                    });
                });
            });
        }

        function fetchRecent() {
            fetch('/community/notifications/recent/', { credentials: 'same-origin' })
                .then(function (r) { return r.json(); })
                .then(function (data) {
                    updateBadge(data.unread || 0);
                    if (data.notifications && data.notifications.length) {
                        list.innerHTML = '';
                        data.notifications.forEach(function (n) {
                            list.appendChild(renderItem(n));
                        });
                    } else if (!list.children.length || list.querySelector('.notif-dd-empty')) {
                        list.innerHTML = '<div class="notif-dd-empty">No notifications yet</div>';
                    }
                })
                .catch(function () {
                    // Keep server-rendered content on fetch failure
                });
        }

        function updateBadge(count) {
            if (!badge) return;
            if (count > 0) {
                badge.textContent = count > 99 ? '99+' : count;
                badge.classList.remove('hidden');
            } else {
                badge.textContent = '';
                badge.classList.add('hidden');
            }
        }

        // Polling
        pollNotificationCount();

        function pollNotificationCount() {
            fetch('/community/notifications/count/', { credentials: 'same-origin' })
                .then(function (r) { return r.json(); })
                .then(function (data) {
                    updateBadge(data.unread || 0);
                })
                .catch(function () {})
                .finally(function () {
                    setTimeout(pollNotificationCount, 30000);
                });
        }
    }

    document.addEventListener('DOMContentLoaded', initNotificationBell);
})();
