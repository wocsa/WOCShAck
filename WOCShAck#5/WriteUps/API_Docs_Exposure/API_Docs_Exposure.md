# Description

Sensitive information exposure (CWE-200) via the public API schema `GET /api/openapi.json` (`Api/views.py:1071-1072`). The `openapi_spec` view has **no authentication decorator**, so the full OpenAPI 3.0.3 specification is served to anonymous users. The spec documents sensitive endpoints — including `/loader/` (with a `file` query parameter for arbitrary path loading), `/totp-secret/` (returns TOTP secrets without security), and `/users/` (exposes usernames and bank IDs) — providing a precise attack-surface map.

# Exploitation

A single unauthenticated request returns the annotated schema:

```
GET /api/openapi.json
```

# PoC

```bash
curl -s "http://<TARGET>/api/openapi.json" | python3 -m json.tool | head -30
# {"openapi": "3.0.3", "info": {"title": "V.R.C API", ...},
#  "paths": {
#    "/loader/":       {"get": {"summary": "File loader", "parameters": [{"name": "file", "description": "Raw file path"}]}},
#    "/totp-secret/":  {"get": {"summary": "...", ...}},
#    "/users/":        {"get": {"summary": "Exposes usernames and bank IDs", ...}},
#    ...
#  }}
```

Key entries that map directly to known vulnerabilities:
- `/loader/` with a `file` query parameter → path traversal / LFI
- `/totp-secret/` → unauthenticated TOTP secret leak
- `/users/` → unauthenticated user enumeration with bank IDs

# Risk

| Dimension | Impact |
|-----------|--------|
| Confidentiality | Full attack-surface map disclosed to anyone; sensitive endpoint parameters and descriptions visible. |
| Integrity | Accelerates exploitation of every linked endpoint. |
| Availability | None directly. |

Overall severity: **Medium** — low impact alone, but a strong force-multiplier that removes recon for the higher-severity findings.

# Remediation

1. **Require authentication** for `/api/openapi.json` (add `@login_required` or `@api_auth_required` to `openapi_spec`).
2. **Remove sensitive endpoint descriptions** (parameter hints like "Raw file path") from the production schema.
3. If public docs are required, publish a sanitised version that omits internal/admin-only routes.

# Author
Brain Scratch
