/**
 * V.R.C Chatbot Frontend JavaScript
 *
 * Handles chat interactions, API calls, and UI updates.
 *
 *
 * - CSRF tokens are included in all POST requests
 * - User input is escaped before rendering in the UI
 * - Error messages do not expose internal details
 */

document.addEventListener('DOMContentLoaded', function() {
    // DOM Elements
    const chatForm = document.getElementById('chat-form');
    const userInput = document.getElementById('user-input');
    const chatMessages = document.getElementById('chat-messages');
    const sendBtn = document.getElementById('send-btn');
    const clearChatBtn = document.getElementById('clear-chat-btn');
    const suggestionsContainer = document.getElementById('suggestions');
    const suggestionsList = document.getElementById('suggestions-list');
    const exportBtn = document.getElementById('export-chat-btn');
    const exportMenu = document.getElementById('export-menu');

    // API Endpoints
    const API_CHAT = '/chatbot/api/chat/';
    const API_SUGGESTIONS = '/chatbot/api/suggestions/';
    const API_CLEAR = '/chatbot/api/clear/';
    const API_FLAG = '/chatbot/api/flag/';

    // Get CSRF token from cookie for secure POST requests
    function getCsrfToken() {
        const name = 'csrftoken';
        const cookies = document.cookie.split(';');
        for (let cookie of cookies) {
            cookie = cookie.trim();
            if (cookie.startsWith(name + '=')) {
                return cookie.substring(name.length + 1);
            }
        }
        return null;
    }

    // Initialize
    loadSuggestions();
    scrollToBottom();

    // Event Listeners
    chatForm.addEventListener('submit', handleSubmit);
    clearChatBtn.addEventListener('click', clearChat);

    // Export dropdown toggle
    if (exportBtn && exportMenu) {
        exportBtn.addEventListener('click', function(e) {
            e.stopPropagation();
            exportMenu.classList.toggle('show');
        });

        // Close dropdown when clicking outside
        document.addEventListener('click', function(e) {
            if (!exportBtn.contains(e.target) && !exportMenu.contains(e.target)) {
                exportMenu.classList.remove('show');
            }
        });
    }

    /**
     * Handle form submission
     */
    async function handleSubmit(e) {
        e.preventDefault();

        const message = userInput.value.trim();
        if (!message) return;

        // Clear input and disable button
        userInput.value = '';
        sendBtn.disabled = true;

        // Hide suggestions after first message
        if (suggestionsContainer) {
            suggestionsContainer.style.display = 'none';
        }

        // Add user message to chat
        addMessage(message, 'user');

        // Show typing indicator
        showTypingIndicator();

        try {
            // Include CSRF token in POST request header
            const response = await fetch(API_CHAT, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRFToken': getCsrfToken(),
                },
                body: JSON.stringify({ message: message })
            });

            const data = await response.json();

            // Remove typing indicator
            removeTypingIndicator();

            if (data.status === 'success') {
                // Add bot response with message ID for flagging
                addMessage(data.response, 'bot', false, data.message_id);
            } else {
                addMessage('Sorry, there was an error processing your request.', 'bot', true);
            }
        } catch (error) {
            removeTypingIndicator();
            addMessage('Connection error. Please try again.', 'bot', true);
        }

        sendBtn.disabled = false;
        userInput.focus();
    }

    /**
     * Add a message to the chat
     * Bot messages include a flag button for user feedback
     */
    function addMessage(text, type, isError = false, messageId = null) {
        const messageDiv = document.createElement('div');
        messageDiv.className = `message ${type}-message`;
        if (isError) messageDiv.classList.add('error-message');

        if (type === 'bot') {
            let flagHtml = '';
            if (messageId && !isError) {
                flagHtml = `
                    <div class="message-actions">
                        <button class="flag-btn" data-message-id="${messageId}" title="Flag this response" onclick="flagResponse(this)">
                            <svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                                <path d="M4 15s1-1 4-1 5 2 8 2 4-1 4-1V3s-1 1-4 1-5-2-8-2-4 1-4 1z"/>
                                <line x1="4" y1="22" x2="4" y2="15"/>
                            </svg>
                        </button>
                    </div>
                `;
            }
            messageDiv.innerHTML = `
                <div class="message-avatar">&#129302;</div>
                <div class="message-content">
                    <p>${escapeHtml(text)}</p>
                    ${flagHtml}
                </div>
            `;
        } else {
            messageDiv.innerHTML = `
                <div class="message-content">
                    <p>${escapeHtml(text)}</p>
                </div>
            `;
        }

        chatMessages.appendChild(messageDiv);
        scrollToBottom();
    }

    /**
     * Show typing indicator
     */
    function showTypingIndicator() {
        const typingDiv = document.createElement('div');
        typingDiv.className = 'message bot-message';
        typingDiv.id = 'typing-indicator';
        typingDiv.innerHTML = `
            <div class="message-avatar">&#129302;</div>
            <div class="message-content">
                <div class="typing-indicator">
                    <span></span>
                    <span></span>
                    <span></span>
                </div>
            </div>
        `;
        chatMessages.appendChild(typingDiv);
        scrollToBottom();
    }

    /**
     * Remove typing indicator
     */
    function removeTypingIndicator() {
        const typing = document.getElementById('typing-indicator');
        if (typing) {
            typing.remove();
        }
    }

    /**
     * Load suggestions from API
     */
    async function loadSuggestions() {
        try {
            const response = await fetch(API_SUGGESTIONS);
            const data = await response.json();

            if (data.status === 'success' && data.suggestions) {
                suggestionsList.innerHTML = '';
                data.suggestions.forEach(suggestion => {
                    const btn = document.createElement('button');
                    btn.className = 'suggestion-btn';
                    btn.textContent = suggestion.question;
                    btn.addEventListener('click', () => {
                        userInput.value = suggestion.question;
                        chatForm.dispatchEvent(new Event('submit', {bubbles: true, cancelable: true}));
                    });
                    suggestionsList.appendChild(btn);
                });
            }
        } catch (error) {
        }
    }

    /**
     * Clear chat history
     */
    async function clearChat() {
        if (!confirm('Are you sure you want to clear your chat history?')) {
            return;
        }

        try {
            // Include CSRF token in POST request header
            await fetch(API_CLEAR, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRFToken': getCsrfToken(),
                }
            });

            // Clear messages from UI (keep welcome message)
            const messages = chatMessages.querySelectorAll('.message');
            messages.forEach((msg, index) => {
                if (index > 0) msg.remove();
            });

            // Show suggestions again
            if (suggestionsContainer) {
                suggestionsContainer.style.display = 'block';
            }

        } catch (error) {
            alert('Failed to clear chat history. Please try again.');
        }
    }

    /**
     * Scroll chat to bottom
     */
    function scrollToBottom() {
        chatMessages.scrollTop = chatMessages.scrollHeight;
    }

    /**
     * Escape HTML to prevent XSS
     * Client-side XSS protection
     */
    function escapeHtml(text) {
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    }

    // Allow pressing Enter to send (Shift+Enter for new line)
    userInput.addEventListener('keydown', function(e) {
        if (e.key === 'Enter' && !e.shiftKey) {
            e.preventDefault();
            chatForm.dispatchEvent(new Event('submit', {bubbles: true, cancelable: true}));
        }
    });

    /**
     * Flag a chatbot response for moderation review
     *
     * - CSRF token included in POST request
     * - Rate limiting handled server-side
     * - Duplicate flag prevention handled server-side
     */
    window.flagResponse = async function(button) {
        const messageId = button.getAttribute('data-message-id');
        if (!messageId) return;

        // Show flag reason selector
        const reason = prompt(
            'Why are you flagging this response?\n\n' +
            '1. Inaccurate Information\n' +
            '2. Inappropriate Content\n' +
            '3. Unhelpful Response\n' +
            '4. Offensive Language\n' +
            '5. Misleading Information\n' +
            '6. Security Concern\n' +
            '7. Other\n\n' +
            'Enter the number (1-7):'
        );

        if (!reason) return;

        const reasonMap = {
            '1': 'inaccurate',
            '2': 'inappropriate',
            '3': 'unhelpful',
            '4': 'offensive',
            '5': 'misleading',
            '6': 'security_concern',
            '7': 'other'
        };

        const reasonCode = reasonMap[reason.trim()] || 'other';

        try {
            const response = await fetch(API_FLAG, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRFToken': getCsrfToken(),
                },
                body: JSON.stringify({
                    message_id: messageId,
                    reason: reasonCode,
                    description: ''
                })
            });

            const data = await response.json();

            if (data.status === 'success') {
                button.disabled = true;
                button.style.opacity = '0.5';
                button.title = 'Response flagged';
            } else {
                alert(data.error || 'Failed to flag response.');
            }
        } catch (error) {
            alert('Failed to submit flag. Please try again.');
        }
    };
});
