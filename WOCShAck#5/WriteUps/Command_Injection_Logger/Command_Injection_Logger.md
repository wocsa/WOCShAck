# Description

**Weakness:** CWE-78 (OS Command Injection)
**Status:** Latent pattern. The injection is **not exploitable** in the deployed code because the input is neutralized by `shlex.quote()` before reaching the shell.

The banking backend audit logger builds a shell command by string interpolation and runs it through `os.system()`, which always invokes a shell:

`VRC_Banking_System_Backend/Activity/Logger.py:6-8`
```python
def write_audit(message):
    safe = shlex.quote(str(message))
    os.system(f'echo {safe} >> /app/Activity/audit.log')
```

`VRC_Banking_System_Backend/Utils/parser.py:109-111` (inside `transaction(data)`) calls the logger with a string that embeds the user-controlled `to` field:
```python
def transaction(data):
    try:
        write_audit(f"Transfer from {data.get('from')} to {data.get('to')} amount {data.get('amount')}")
```

**Full data flow (as deployed):**

1. Client sends `POST /banking/api/quick-transfer/` with a JSON body containing `to`.
2. `djangoWocshack_5/Bank/views.py:423-440` (`quick_transfer`) parses the body and does `payload.update(data)`, so every field, including `to`, is forwarded unchanged to the banking backend over the socket client (`cli.send(payload)`). The `command` is taken from `action`, defaulting to `tr`.
3. `VRC_Banking_System_Backend/Utils/parser.py` `parse()` dispatches `command == "tr"` to `transaction(parsed_data)` (line 496-497).
4. `transaction()` (line 111) builds the audit string containing `to` and calls `write_audit()`.
5. `Logger.py:7` wraps the whole string with `shlex.quote()`, producing a single POSIX shell word.
6. `Logger.py:8` passes that word to `os.system()`, which runs `sh -c`.

**Why the attack fails:** `shlex.quote()` wraps the entire message in single quotes and escapes any embedded single quote as `'"'"'`. The shell therefore sees the whole message as one literal argument to `echo`, so `;`, `>`, `$()`, backticks, and `&&` are inert. The catalog payload `"; id > /tmp/pwned.txt; echo "` is delivered as literal text, and nothing is written to `/tmp/pwned.txt`.

**Verification (local, Python 3):**
```
QUOTED: 'Transfer from 1 to "; id > /tmp/pwned.txt; echo " amount 5'
SHELL WORDS: ['echo', 'Transfer from 1 to "; id > /tmp/pwned.txt; echo " amount 5', '>>', '/dev/null']
QUOTED2 (single-quote breakout attempt): 'Transfer from 1 to x'"'"'; id > /tmp/pwned.txt; echo '"'"'y amount 5'
```

**Why it still matters:** The `os.system` plus f-string pattern is the OWASP A03 anti-pattern. The only thing preventing RCE is one `shlex.quote()` call. Removing it during a refactor would make the `to` field immediately exploitable through `quick_transfer`.

# Exploitation

| Step | Action | Result |
|------|--------|--------|
| 1 | Log in to the Django banking app and obtain a session cookie. | Authenticated session; `quick_transfer` requires `@login_required`. |
| 2 | Send `POST /banking/api/quick-transfer/` with `{"action":"tr","from":<own id>,"to":"\"; id > /tmp/pwned.txt; echo \"","amount":1}`. | `quick_transfer` forwards the body to the backend; `transaction()` runs. |
| 3 | `write_audit()` quotes the message via `shlex.quote()`. | Message becomes one single-quoted shell word. |
| 4 | `os.system("echo '...' >> /app/Activity/audit.log")` executes. | The payload is appended to `audit.log` as literal text. |
| 5 | Check `/tmp/pwned.txt` in the backend container, and `audit.log` for the literal string. | `/tmp/pwned.txt` does **not** exist. The literal payload is in the log, which confirms the mitigation holds. |

# PoC

The catalog payload was tested against the deployed logic. It is **not** exploitable:

```bash
curl -s -b john.cookies -X POST http://localhost:8000/banking/api/quick-transfer/ \
  -H "Content-Type: application/json" \
  -d '{"action":"tr","from":1,"to":"\"; id > /tmp/pwned.txt; echo \"","amount":1}'

# Expected (observed by code analysis): transfer processes normally; the audit log gets the
# literal text; /tmp/pwned.txt is never created.
docker compose exec banking_backend cat /app/Activity/audit.log | tail -1
docker compose exec banking_backend ls /tmp/pwned.txt   # -> No such file
```

Negative control, showing why the quoting matters. This is the same logic with `shlex.quote()` removed, and it is **not** present in the deployed code:
```python
import os
msg = 'Transfer from 1 to "; id > /tmp/pwned.txt; echo " amount 5'
os.system(f'echo {msg} >> /tmp/audit.log')   # would execute `id` and write /tmp/pwned.txt
```

# Risk

| Dimension | Impact |
|-----------|--------|
| Confidentiality | None as deployed. No command output is returned or stored beyond the literal audit line. |
| Integrity | None as deployed. Input cannot break out of the quoted argument. |
| Availability | None as deployed. |

Overall severity: **Informational (latent)**. The current code is not exploitable. Severity would rise to Critical (RCE in the banking-backend container, with access to the SQLite DB and the 172.28.0.0/16 network) if the `shlex.quote()` call were removed or the logger were changed to pass input through a shell without quoting.

# Remediation

1. Remove the shell entirely. Append the line from Python:
   ```python
   def write_audit(message):
       with open('/app/Activity/audit.log', 'a') as f:
           f.write(str(message) + '\n')
   ```
2. If a subprocess is required, use list form with `shell=False`:
   `subprocess.run(['tee', '-a', '/app/Activity/audit.log'], input=(str(message) + '\n').encode(), check=True)`
3. Add a regression test that passes `"; id > /tmp/pwned.txt; echo "` through `write_audit()` and asserts `/tmp/pwned.txt` is not created. This catches future removal of `shlex.quote()`.
4. Add a code comment or lint rule (for example Bandit B605/B607) that flags `os.system` in the banking backend.

# Author
WOCSA
