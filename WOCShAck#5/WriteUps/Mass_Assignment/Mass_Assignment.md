# Description

Mass assignment (CWE-915) in the profile-update flow `POST /account/settings/` (`Account/views.py:452-457`). The `new_username` branch of `settings()` iterates over **every** key in `request.POST` and calls `setattr(profile, key, value)` for any key matching a `UserProfile` field (only `csrfmiddlewaretoken` is excluded). An authenticated user can write any `UserProfile` column by adding it as a POST field — including the **bank ID (`bid`)** used to receive transfers.

Note: `is_staff`, `is_superuser`, and `balance` are **not** `UserProfile` fields (they belong to the `User` model or the banking backend), so admin/privilege escalation via this vector is not possible. The impact is limited to `UserProfile` attributes such as `bid`, `biography`, `profile_picture`, and other profile-level fields.

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

By overwriting `bid` to another user's bank ID, the attacker redirects incoming transfers to their own profile. Fields like `role`, `balance`, `is_staff` are NOT on `UserProfile` and will be silently ignored.

# Risk

| Dimension | Impact |
|-----------|--------|
| Confidentiality | None directly. |
| Integrity | Identity tampering: overwrite `bid` to hijack incoming transfers. Privilege escalation (`is_staff`, `is_superuser`) is not reachable via this vector since those fields are on the `User` model, not `UserProfile`. |
| Availability | None directly. |

Overall severity: **High** — profile-object control from a regular account; bank-ID hijacking enables financial redirection.

# Remediation

1. **Allow-list editable fields explicitly**; never iterate `request.POST` into `setattr`.
2. Protect identity-bearing fields (`bid`, `id`) by excluding them from any bulk-update path.
3. **Separate sensitive fields** (`bid`, role) behind their own audited, authorised flows.

# Author
CPE LYON
