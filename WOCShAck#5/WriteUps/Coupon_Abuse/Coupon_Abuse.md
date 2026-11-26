# Description

Coupon abuse via cross-tenant discount application (CWE-285). The Developer Coupon Management portal is protected by the `@developer_required` decorator and enforces a server-side discount range of 0.01% to 100% (`Developer/views_coupons.py:25-58`).

Developer-specific coupon restrictions are implemented in `Coupon.get_applicable_total()` (`Shopping/models.py:395-409`) and enforced by the web shopping interface.

The API shopping implementation does not enforce these restrictions. Both `POST /api/shop/coupon/apply/` (`Api/views_shopping.py:450-456`) and `POST /api/shop/checkout/` (`Api/views_shopping.py:267-285`) call `coupon.calculate_discount(total)` on the **whole cart total** returned by `cart_obj.get_total()`. Neither calls `get_applicable_total()` or checks `coupon.developer_id`, so a developer-scoped coupon is computed against items sold by other sellers. The web shop, by contrast, uses `get_applicable_total()` and filters on `css.creator_id == coupon_obj.developer_id` (`Shopping/views.py:590-591, 651-681`).

The API checkout also never increments `coupon.current_uses` (only the web flow does, `Shopping/views.py:871`). It records a `CouponUsage` row, so the per-user limit is enforced, but the global `max_uses` limit is never reached through the API.

The API checkout implementation (`Api/views_shopping.py:267-359`) also handles discounted order totals inconsistently with actual banking payments, resulting in incorrect preliminary balance validation and inaccurate order and local accounting records.

# Exploitation

| Step | Action | Result |
|------|--------|--------|
| 1 | Log in as a user with the Developer Role. | Developer access. |
| 2 | `POST /developer/coupons/create/` with `discount_value=100`, `minimum_order_amount=0`, high max-uses. | 100%-off coupon created (the server-side discount cap allows discounts of up to 100%). |
| 3 | With another seller's item in the cart, `POST /api/shop/coupon/apply/` with the coupon code (session cookie or `X-API-Key`). | The discount is computed on the whole cart total, including items the developer does not own. No completed free purchase is demonstrated. |

# PoC

Create the coupon (as a Developer):

```
POST /developer/coupons/create/
code=FREEALL100  discount_value=100  max_uses=999  minimum_order_amount=0
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

The coupon validation response demonstrates incorrect discount calculation, not a completed purchase.

The API checkout processes banking payments at the undiscounted item prices (`Api/views_shopping.py:304-320`). However, the order and local transaction records contain the discounted amount (`Api/views_shopping.py:330-338, 353-357`).

The preliminary balance check uses the discounted total rather than the actual payment amount (`Api/views_shopping.py:285-302`). The banking backend still enforces sufficient funds for the actual payment.

Observed checkout results:

- Payments with insufficient funds are rejected by the banking backend.
- Successful payments charge the undiscounted amount.
- Completed order records contain the discounted amount instead of the amount actually paid.

In a separate checkout test involving an item priced at 6.00 Neuros, the buyer was debited 6.00 Neuros and the seller was credited 6.00 Neuros, while the order recorded a `total_amount` of 0.00 and a `discount_amount` of 6.00.

These results demonstrate inconsistencies between payment processing and accounting records rather than a successful free purchase.

# Risk

| Dimension | Impact |
|-----------|--------|
| Confidentiality | None directly. |
| Integrity | Incorrect discount calculations, inconsistent preliminary balance validation, and order and local accounting records that do not reflect actual banking payments. |
| Availability | None directly. |

Overall severity: **Medium** — improper enforcement of developer-specific coupon restrictions and of the global usage limit compromises the integrity of marketplace order and accounting records.

Free purchases and direct revenue loss are not demonstrated.

**CVSS 3.1:** 4.3 (Medium) — `CVSS:3.1/AV:N/AC:L/PR:L/UI:N/S:U/C:N/I:L/A:N`.

# Remediation

1. **Enforce the server-side discount policy** consistently and require administrative approval for exceptional discounts where appropriate.
2. **Consistently enforce the existing developer-specific coupon scope** across both web and API shopping interfaces.
3. **Validate coupon eligibility** against the applicable cart contents before checkout.
4. **Ensure consistency between calculated totals, banking payments, order records and local transaction records.**
5. **Increment `current_uses` in the API checkout** (inside the same transaction as `CouponUsage`) so `max_uses` is enforced on every checkout path.
6. **Add regression tests** covering coupon scope enforcement, usage limits, payment consistency and accounting accuracy.

# Author
CPE LYON
