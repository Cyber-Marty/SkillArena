# Aggregate completed sales by region

Read `sales.csv`. Ignore rows whose `status` is not `completed`. For each region among remaining rows, sum integer `quantity` as `units` and sum `quantity * unit_cents` as integer `revenue_cents`. Count distinct `order_id` values in that region as `order_count`; multiple lines of one order count once. Output a JSON object with one field, `regions`, containing an array sorted by region name ascending. Each region object has `region`, `units`, `revenue_cents`, and `order_count`, with all three metrics as JSON integers. A cancelled-only region must not appear.

Write a UTF-8 `output.json` in the workspace root. Use the exact JSON field names, value types, and array order specified above. JSON object key order and whitespace do not matter.
