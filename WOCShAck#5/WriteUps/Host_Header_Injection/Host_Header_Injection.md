# Description

Open redirect via Host header injection (CWE-601 / CWE-116), with a second vector on the advertisement click endpoint. Two independent issues abuse the trusted domain:

- **Host Header Injection (unauthenticated):** BunkerWeb (the reverse proxy) performs the HTTP→HTTPS redirect using the incoming `Host` header. Django is configured with `ALLOWED_HOSTS = ['*']` and `USE_X_FORWARDED_HOST = True` (`settings/base.py:29,35`), so the application trusts any forwarded host value. Sending `Host: evil.com` on an HTTP URL can produce a redirect to `https://evil.com/<path>`.
- **Advertisement click redirect:** `/advertisement/click/<uuid>/` redirects to the ad's stored `target_url` with no domain validation, and works **before** the ad is approved ("Pending Review").

The Host-header vector is also a **password-reset poisoning** primitive when `SITE_URL` is empty (the default): reset links are built from the request host via `request.build_absolute_uri()`, so a poisoned `Host` header sends the victim's reset token to the attacker's domain.

# Exploitation

| Vector | Action | Result |
|--------|--------|--------|
| Host header | `GET /account/login` with `Host: evil.com`. | `301 → https://evil.com/account/login`, unauthenticated. |
| Ad click | Create an ad with `target_url=https://evil.com`, hit `/advertisement/click/<uuid>/`. | `302 → https://evil.com`. |

# PoC

**1. Host Header Injection (no auth, every endpoint):**

```http
GET /account/password-reset-request HTTP/1.1
Host: evil.com
→ HTTP/1.1 301 Moved Permanently
  Location: https://evil.com/account/password-reset-request
```

```http
GET / HTTP/1.1
Host: evil.com
→ HTTP/1.1 301  Location: https://evil.com/
```

**2. Advertisement click redirect (works pre-approval):**

```http
POST /advertisement/create/  → target_url=https://evil.com/phishing-page  (status: Pending Review)
POST /advertisement/click/a5d36db2-…/  →  HTTP 302 Location: https://evil.com/phishing-page
```

# Risk

| Dimension | Impact |
|-----------|--------|
| Confidentiality | Password-reset link poisoning → reset token sent to `https://evil.com/...` → account takeover. |
| Integrity | Legitimate-looking V.R.C links redirect victims to attacker phishing pages. |
| Availability | None directly. |

Overall severity: **High** — unauthenticated, universal across endpoints, defeats anti-phishing filters (source URL is the trusted domain).

# Remediation

1. **Pin the canonical host in BunkerWeb**: restrict the `SERVER_NAME` and reject unknown `Host` values.
2. **Set Django `ALLOWED_HOSTS`** to the actual domain (not `['*']`), disable `USE_X_FORWARDED_HOST`, and build e-mail links from a hard-coded `SITE_URL`, not `request.build_absolute_uri()`.
3. **Validate `target_url`** against an allow-list; only redirect for approved ads; add an interstitial warning before external redirects.

# Author
CHILL HUNT
