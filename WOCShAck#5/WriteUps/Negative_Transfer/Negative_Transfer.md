# Description

Improper input validation on the quick-transfer endpoint (CWE-20). The standard transfer path (`_handle_transfer` at `Bank/views.py:225-243`) correctly validates `amount > 0`. However, the `quick_transfer` endpoint at `Bank/views.py:421-440` is `@csrf_exempt` and `@login_required`, parses a raw JSON body, and forwards the entire payload (including `amount`) directly to the banking backend via `cli.send(payload)` with **no server-side validation**. The banking backend does not reject negative values either: its `tr` handler (`VRC_Banking_System_Backend/Utils/parser.py:109-131`) calls `sub_balance(from, amount)` and then `add_balance(to, amount)`, and `sub_balance` only checks `balance < amount` (`DbManager.py:591`). With a negative amount the check always passes and the money flow reverses — debiting the *recipient* and crediting the attacker.

# Exploitation

| Step | Action | Result |
|------|--------|--------|
| 1 | Authenticate and obtain a valid session. | `@login_required` satisfied. |
| 2 | POST to `/banking/api/quick-transfer/` with `{"action":"tr","from":<ATTACKER_ID>,"to":<VICTIM_ID>,"amount":-150}`. | Endpoint forwards the payload to the backend with no validation (`@csrf_exempt`, no CSRF token needed). |
| 3 | Observe the backend response and both balances. | `{"status": "success"}`; the victim is debited 150 and the attacker is credited 150. |

# PoC

```bash
curl -s -b cookies.txt -X POST "http://<TARGET>/banking/api/quick-transfer/" \
  -H "Content-Type: application/json" \
  -d '{"action":"tr","from":<ATTACKER_ID>,"to":<VICTIM_ID>,"amount":-150}'
# {"status": "success"}
```

`<ATTACKER_ID>` and `<VICTIM_ID>` are banking backend user ids (in this application they match the Django user ids). The backend `tr` command reads `from` / `to`; a `recipient` field is ignored and the request fails with `{"error": "no response"}`.

Reproduced on throwaway accounts: attacker balance 0 → 150, victim balance 200 → 50, with transaction history entries `You -> --150 -> <VICTIM_ID>`. The same result was obtained through the BunkerWeb reverse proxy over HTTP and HTTPS (no CRS rule fired; nothing was blocked).

The `quick_transfer` endpoint (`Bank/views.py:421-440`) parses the JSON body and calls `cli.send(payload)` without checking the `amount` field. Note: the standard form-based transfer at `/banking/dashboard/` correctly rejects `amount <= 0`. Because `from` is also taken from the client, the same request can move money between any two accounts (see Banking_Protocol_Injection).

# Risk

| Dimension | Impact |
|-----------|--------|
| Confidentiality | None directly. |
| Integrity | Unauthorised modification of account balances: a negative transfer debits the recipient and credits the attacker (demonstrated). |
| Availability | None directly. |

Overall severity: **High (integrity)** — no amount validation in either the quick-transfer endpoint or the banking backend lets any authenticated user pull funds from another account.

# Remediation

1. **Validate `amount` server-side**: enforce a strictly positive, finite numeric amount and an appropriate upper bound at both the Django application and banking backend levels.
2. **Re-check the sender's balance** server-side within the transfer transaction and ensure atomic balance updates.
3. **Never rely on client-side constraints** (`min`, `max`, `type=number`) for security.
4. **Add regression tests** to verify that invalid amounts are rejected and that rejected transactions leave account balances unchanged.

# Author
Scoubi'Hack
