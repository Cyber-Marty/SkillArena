# Inventory: missing counts and zero counts

Read `inventory.csv`. A blank `on_hand` means the count is unknown; it is different from numeric zero. For each row in input order, output an object with `sku`, `status`, and `order_qty`. If `on_hand` is blank, use status `unknown` and JSON null for `order_qty`, regardless of the reorder point. Otherwise parse both numeric fields as integers. If `on_hand` is less than `reorder_point`, use status `reorder` and `order_qty = 2 * reorder_point - on_hand`. Otherwise use status `sufficient` and integer `order_qty = 0`. The top-level JSON object has one field, `items`, containing that ordered array.

Write a UTF-8 `output.json` in the workspace root. Use the exact JSON field names, value types, and array order specified above. JSON object key order and whitespace do not matter.
