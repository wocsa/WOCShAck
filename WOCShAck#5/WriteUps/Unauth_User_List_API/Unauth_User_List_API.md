# Description

**CWE-306: Missing Authentication for Critical Function**

The `user_list` view returns every `UserProfile` record's username and bank ID (`bid`) to any caller. The view has no authentication check, and the project has no global authentication middleware that would enforce one (`djangoWocshack_5/settings/base.py` `MIDDLEWARE` contains only the stock Django security, session, CSRF, auth, messages and clickjacking middleware). The endpoint is reachable at `GET /api/users/` without a session or API key.

Vulnerable code:

- `Api/views.py:3850-3853`

```python
def user_list(request):
    from Account.models import UserProfile
    users = UserProfile.objects.all().values('user__username', 'bid')
    return JsonResponse(list(users), safe=False)
```

- Route: `Api/urls.py:220` — `path("users/", views.user_list, name="user_list"),`, included under `api/` by `djangoWocshack_5/urls.py:48`.

The full dump has no pagination, filtering or rate limiting. The project's `robots.txt` template (`djangoWocshack_5/urls.py:29`) contains `Disallow: /api/users/`, but robots.txt is advisory and does not restrict access.

# Exploitation

| Step | Action | Result |
|------|--------|--------|
| 1 | Log out (or use a fresh client with no session cookie and no API key). | Caller is fully unauthenticated. |
| 2 | Send `GET /api/users/` to the application. | Server responds `200 OK` with a JSON array. |
| 3 | Parse the response. Each element contains `user__username` and `bid`. | Complete list of registered usernames and their bank IDs is obtained in one request. |
| 4 | Use the harvested usernames as input to follow-on attacks, such as login brute force or password spraying against `/account/login/`, or as targets for other broken-access-control or account-takeover issues in the platform. | Attack surface for account compromise is expanded without any prior knowledge of valid accounts. |

# PoC

```bash
curl -s http://localhost:8000/api/users/
```

Expected response shape (values depend on seeded data):

```json
[{"user__username": "admin", "bid": "..."},
 {"user__username": "johndoe", "bid": "..."},
 ...]
```

Confirm no authentication is required by checking the status code with no cookies:

```bash
curl -s -o /dev/null -w "%{http_code}\n" http://localhost:8000/api/users/
# 200
```

# Risk

| Dimension | Impact |
|-----------|--------|
| Confidentiality | Every registered username and its `bid` (bank ID) is disclosed to anonymous callers. Usernames and bank identifiers are personal and financial-adjacent data. |
| Integrity | No direct modification of data. The disclosed usernames enable follow-on integrity attacks (credential stuffing, password spraying, account takeover via other flaws). |
| Availability | No direct impact. The unpaginated full-table dump is cheap to request repeatedly and is not rate-limited, but it does not by itself degrade service. |

Overall severity: **Medium** — the endpoint leaks the full user roster and bank IDs to anyone with network access, with no preconditions (CVSS 3.1 `AV:N/AC:L/PR:N/UI:N/S:U/C:L/I:N/A:N`, score 5.3). Severity rises when chained with login brute force or other account-takeover flaws, since the attacker no longer has to guess valid usernames.

# Remediation

1. Require authentication on the view. Apply `@login_required` (or the project's API-key/DRF permission class) to `user_list` in `Api/views.py`, or enforce authentication globally for `/api/` routes.
2. If a public user directory is genuinely required, return only the minimum fields. Remove `bid` from the response, and do not expose usernames in bulk.
3. Remove the endpoint if it has no legitimate consumer. The `Disallow` entry in robots.txt should not be relied on as an access control.
4. Add rate limiting and pagination to any remaining user-enumeration endpoints (including `/api/check-user/`), so enumeration is slowed even when authentication is present.
5. Add a regression test asserting that an anonymous `GET /api/users/` returns `302`/`401`/`403` and not `200`.

# Author
WOCSA
