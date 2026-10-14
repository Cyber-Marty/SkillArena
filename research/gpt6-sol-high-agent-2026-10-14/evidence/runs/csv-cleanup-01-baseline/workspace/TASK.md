# Clean a contact CSV

Read `contacts.csv` as CSV, respecting quoted fields. Trim leading and trailing whitespace from `name`, `email`, and `city`; preserve internal spaces and letter case in names and cities. Lowercase each trimmed email. Drop a row if its trimmed name or email is empty. Keep remaining rows in input order. Output an object with `contacts` and `dropped_ids`. Each contact has string fields `id`, `name`, `email`, and `city`, except that an empty trimmed city becomes JSON null. `dropped_ids` is an array of the dropped string IDs in input order.

Write a UTF-8 `output.json` in the workspace root. Use the exact JSON field names, value types, and array order specified above. JSON object key order and whitespace do not matter.
