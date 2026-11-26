/**
 * Floating Chat Bubble JavaScript
 *
 * - No inline event handlers
 * - Proper DOM element handling
 * - Keyboard accessibility support
 */

(function() {
    'use strict';

    // DOM Elements
    const toggleBtn = document.getElementById('chat-bubble-toggle');
    const widgetContainer = document.getElementById('chat-widget-container');
    const closeBtn = document.getElementById('chat-widget-close');

    // Exit early if elements don't exist
    if (!toggleBtn || !widgetContainer) {
        console.warn('Chat bubble elements not found');
        return;
    }

    // State
    let isOpen = false;

    /**
     * Toggle chat widget visibility
     * Uses class manipulation, not innerHTML
     */
    function toggleChat() {
        isOpen = !isOpen;

        if (isOpen) {
            widgetContainer.classList.add('open');
            toggleBtn.classList.add('active');
            toggleBtn.setAttribute('aria-expanded', 'true');

            // Focus management for accessibility
            const iframe = widgetContainer.querySelector('iframe');
            if (iframe) {
                iframe.focus();
            }
        } else {
            widgetContainer.classList.remove('open');
            toggleBtn.classList.remove('active');
            toggleBtn.setAttribute('aria-expanded', 'false');
            toggleBtn.focus();
        }
    }

    /**
     * Close chat widget
     */
    function closeChat() {
        if (isOpen) {
            isOpen = false;
            widgetContainer.classList.remove('open');
            toggleBtn.classList.remove('active');
            toggleBtn.setAttribute('aria-expanded', 'false');
            toggleBtn.focus();
        }
    }

    // Event Listeners
    toggleBtn.addEventListener('click', toggleChat);

    if (closeBtn) {
        closeBtn.addEventListener('click', closeChat);
    }

    // Keyboard support (Escape to close)
    document.addEventListener('keydown', function(e) {
        if (e.key === 'Escape' && isOpen) {
            closeChat();
        }
    });

    // Click outside to close
    document.addEventListener('click', function(e) {
        if (isOpen &&
            !widgetContainer.contains(e.target) &&
            !toggleBtn.contains(e.target)) {
            closeChat();
        }
    });

    // Prevent clicks inside widget from closing
    widgetContainer.addEventListener('click', function(e) {
        e.stopPropagation();
    });

    // Store state in sessionStorage to persist across page navigations
    const STORAGE_KEY = 'vrc_chat_open';

    function saveState() {
        try {
            sessionStorage.setItem(STORAGE_KEY, isOpen ? '1' : '0');
        } catch (e) {
            // sessionStorage might be unavailable
        }
    }

    function restoreState() {
        try {
            const saved = sessionStorage.getItem(STORAGE_KEY);
            if (saved === '1') {
                toggleChat();
            }
        } catch (e) {
            // sessionStorage might be unavailable
        }
    }

    // Save state when toggling
    toggleBtn.addEventListener('click', saveState);
    if (closeBtn) {
        closeBtn.addEventListener('click', saveState);
    }

    // Restore state on page load
    restoreState();

})();
