# Invoice totals with decimal rounding

Read `invoices.csv`. Each row has a decimal `base`, decimal `rebate`, and decimal `tax_rate`. For each invoice, calculate `taxable = base - rebate`, then `tax = taxable * tax_rate` rounded to exactly two decimal places using decimal ROUND_HALF_UP (a half-cent rounds away from zero). Calculate `total = taxable + tax`. Do not round or sum tax before the per-invoice rounding. All amounts are nonnegative. Output an object with `invoices` in input order and `summary`. Each invoice object has `invoice_id`, `taxable`, `tax`, and `total`; monetary values are strings with exactly two digits after the decimal point. `summary` has `taxable`, `tax`, and `total`, each the sum of the corresponding rounded invoice values, in the same string format.

Write a UTF-8 `output.json` in the workspace root. Use the exact JSON field names, value types, and array order specified above. JSON object key order and whitespace do not matter.
