# Join orders to customers

Read `orders.csv` and `customers.csv`. Match each order's `customer_id` to the customer row with that ID. Keep all orders in original order. Output an object with `orders`, `unmatched_order_ids`, and `known_total_cents`. Each order object has `order_id`, `customer_id`, `customer_name`, `region`, and `amount_cents`; the last field is an integer. For unmatched customers, use JSON null for both `customer_name` and `region`. `unmatched_order_ids` lists those orders' IDs in input order. `known_total_cents` sums amounts only for orders with a matching customer, including zero amounts.

Write a UTF-8 `output.json` in the workspace root. Use the exact JSON field names, value types, and array order specified above. JSON object key order and whitespace do not matter.
