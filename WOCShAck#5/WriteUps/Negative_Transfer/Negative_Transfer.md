# Description

Improper input validation on the quick-transfer endpoint (CWE-20). The standard transfer path (`_handle_transfer` at `Bank/views.py:225-243`) correctly validates `amount > 0`. However, the `quick_transfer` endpoint at `Bank/views.py:421-440` is `@csrf_exempt` and `@login_required`, parses a raw JSON body, and forwards the entire payload (including `amount`) directly to the banking backend via `cli.send(payload)` with **no server-side validation**. If the banking backend does not independently reject negative values, the money flow reverses — debiting the *recipient* and crediting the attacker.

# Exploitation

| Step | Action | Result |
|------|--------|--------|
| 1 | Authenticate and obtain a valid session. | `@login_required` satisfied. |
| 2 | POST to `/banking/quick-transfer/` with a negative `amount` in JSON. | Endpoint forwards to backend with no validation (`@csrf_exempt`). |
| 3 | Observe the backend response. | If the backend does not reject negatives, funds flow in reverse. |

# PoC

```bash
curl -sk -b cookies.txt -X POST "http://<TARGET>/banking/quick-transfer/" \
  -H "Content-Type: application/json" \
  -d '{"action":"tr","recipient":"<victim_bid>","amount":-150,"note":"test"}'
```

The `quick_transfer` endpoint (`Bank/views.py:421-440`) parses the JSON body and calls `cli.send(payload)` without checking the `amount` field. Whether the reversed transfer succeeds depends on the banking backend's own validation. Note: the standard form-based transfer at `/banking/dashboard/` correctly rejects `amount <= 0`.

No backend response or balance change is documented in this PoC. The actual financial impact therefore remains unverified.

# Risk

| Dimension | Impact |
|-----------|--------|
| Confidentiality | None directly. |
| Integrity | Potential unauthorised modification of account balances, depending on the banking backend's validation. |
| Availability | None directly. |

Overall severity: **High (integrity)** — improper input validation in the quick-transfer endpoint; actual financial impact depends on the banking backend's validation and has not been independently demonstrated.

# Remediation

1. **Validate `amount` server-side**: enforce a strictly positive, finite numeric amount and an appropriate upper bound at both the Django application and banking backend levels.
2. **Re-check the sender's balance** server-side within the transfer transaction and ensure atomic balance updates.
3. **Never rely on client-side constraints** (`min`, `max`, `type=number`) for security.
4. **Add regression tests** to verify that invalid amounts are rejected and that rejected transactions leave account balances unchanged.

# Author
Scoubi'Hack
