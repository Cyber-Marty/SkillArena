# Deduplicate contacts by email

Read `contacts.csv`. Trim and lowercase each email to form its deduplication key. Discard rows with a blank normalized email. For each key, keep the row with the latest `updated_at` ISO date; if dates tie, keep the lexicographically smallest `id`. Output an object with `contacts`: one object per retained row, sorted by normalized email ascending. Each object has string fields `id`, `name`, `email`, and `updated_at`. Use the retained row's name exactly as supplied and the normalized email, not the raw email.

Write a UTF-8 `output.json` in the workspace root. Use the exact JSON field names, value types, and array order specified above. JSON object key order and whitespace do not matter.
