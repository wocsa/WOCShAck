// PIN Entry JavaScript Logic
let currentPin = '';
const pinDots = document.querySelectorAll('.pin-dot');
const submitBtn = document.getElementById('submitBtn');
const pinCard = document.querySelector('.pin-card');

/**
 * Updates the visual display of PIN dots
 */
function updateDisplay() {
    pinDots.forEach((dot, index) => {
        if (index < currentPin.length) {
            dot.classList.add('filled');
        } else {
            dot.classList.remove('filled');
        }
    });

    submitBtn.disabled = currentPin.length !== 6;
}

/**
 * Adds a digit to the current PIN
 * @param {string} digit - The digit to add (0-9)
 */
function addDigit(digit) {
    if (currentPin.length < 6) {
        currentPin += digit;
        updateDisplay();
    }
}

/**
 * Removes the last digit from the PIN
 */
function backspace() {
    if (currentPin.length > 0) {
        currentPin = currentPin.slice(0, -1);
        updateDisplay();
    }
}

/**
 * Clears the entire PIN
 */
function clearPin() {
    currentPin = '';
    updateDisplay();
}

/**
 * Submits the PIN to the Django backend
 */
async function submitPin() {
    if (currentPin.length === 6) {
        // Disable submit button during request
        submitBtn.disabled = true;
        submitBtn.textContent = 'Verifying...';

        try {
            const response = await fetch('/banking/verify-pin/', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRFToken': getCsrfToken(),
                },
                body: JSON.stringify({
                    pin: currentPin
                })
            });

            const data = await response.json();

            if (response.ok && data.success) {
                showSuccess(data.message || 'PIN Verified Successfully!');
                // Redirect if URL provided
                if (data.redirect_url) {
                    setTimeout(() => {
                        window.location.href = data.redirect_url;
                    }, 1500);
                }
            } else if (response.status === 403) {
                // Account locked — show the reset link permanently
                showError(data.message || 'Account locked. Please reset your PIN.');
                showLockedNotice();
            } else {
                showError(data.message || 'Invalid PIN. Please try again.');
            }
        } catch (error) {
            console.error('Error:', error);
            showError('Connection error. Please try again.');
        }

        // Re-enable submit button
        submitBtn.disabled = false;
        submitBtn.textContent = 'Submit';
    }
}

/**
 * Shows success message
 * @param {string} message - Success message to display
 */
function showSuccess(message = '✓ PIN Verified Successfully!') {
    const successMsg = document.createElement('div');
    successMsg.className = 'success-message';
    successMsg.textContent = message;
    document.body.appendChild(successMsg);

    setTimeout(() => {
        successMsg.remove();
    }, 3000);
}

/**
 * Shows error message and shakes the card
 * @param {string} message - Error message to display
 */
function showError(message = 'Invalid PIN. Please try again.') {
    pinCard.classList.add('error-shake');

    // Show error message
    const errorMsg = document.createElement('div');
    errorMsg.className = 'success-message';
    errorMsg.style.background = 'rgba(220, 38, 38, 0.95)';
    errorMsg.style.boxShadow = '0 10px 30px rgba(220, 38, 38, 0.3)';
    errorMsg.textContent = message;
    document.body.appendChild(errorMsg);

    setTimeout(() => {
        pinCard.classList.remove('error-shake');
        errorMsg.remove();
    }, 2000);

    // Clear PIN after error
    setTimeout(() => {
        clearPin();
    }, 1000);
}

/**
 * Shows the locked notice and disables the keypad
 */
function showLockedNotice() {
    const notice = document.getElementById('pinLockedNotice');
    if (notice) {
        notice.style.display = 'block';
    }
    // Disable all keypad buttons so the user can't keep trying
    document.querySelectorAll('.pin-key, #submitBtn').forEach(btn => {
        btn.disabled = true;
    });
}

/**
 * Gets CSRF token from Django cookies
 * @param {string} name - Cookie name
 * @returns {string|null} Cookie value
 */
function getCsrfToken() {
    const tokenInput = document.querySelector('input[name="csrfmiddlewaretoken"]');
    if (tokenInput) return tokenInput.value;
    return getCookie('csrftoken');
}

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

/**
 * Handles keyboard input
 */
function handleKeyboardInput() {
    document.addEventListener('keydown', (e) => {
        // Prevent default behavior for handled keys
        if ((e.key >= '0' && e.key <= '9') ||
            e.key === 'Backspace' ||
            e.key === 'Enter' ||
            e.key === 'Escape') {
            e.preventDefault();
        }

        if (e.key >= '0' && e.key <= '9') {
            addDigit(e.key);
        } else if (e.key === 'Backspace') {
            backspace();
        } else if (e.key === 'Enter' && currentPin.length === 6) {
            submitPin();
        } else if (e.key === 'Escape') {
            clearPin();
        }
    });
}

function preventContextMenu() {
    const buttons = document.querySelectorAll('.pin-key, .pin-btn');
    buttons.forEach(button => {
        button.addEventListener('contextmenu', (e) => {
            e.preventDefault();
        });
    });
}

/**
 * Initialize the PIN entry interface
 */
function initializePinEntry() {
    updateDisplay();
    handleKeyboardInput();
    addClickSound();
    preventContextMenu();

    // Focus trap for accessibility
    document.querySelector('.pin-card').setAttribute('tabindex', '-1');
    document.querySelector('.pin-card').focus();
}

// Initialize when DOM is loaded
document.addEventListener('DOMContentLoaded', initializePinEntry);