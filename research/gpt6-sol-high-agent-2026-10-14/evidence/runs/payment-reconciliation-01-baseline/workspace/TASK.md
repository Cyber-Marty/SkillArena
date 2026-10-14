# Reconcile invoices and payments

Read `invoices.csv` and `payments.csv`; all amounts are integer cents. Sum payments by `invoice_id` for each listed invoice, ignoring unmatched payments in those sums. For each invoice in input order, output `invoice_id`, integer `due_cents`, integer `paid_cents`, integer `balance_cents = due_cents - paid_cents`, and `status`. Use `settled` if balance is zero, `underpaid` if positive, and `overpaid` if negative. Also output `orphan_payment_ids`: payment IDs whose invoice ID is absent from `invoices.csv`, in payment input order. The top-level fields are `invoices` and `orphan_payment_ids`.

Write a UTF-8 `output.json` in the workspace root. Use the exact JSON field names, value types, and array order specified above. JSON object key order and whitespace do not matter.
