# Rank scores while preserving ties

Read `scores.csv`. Sort rows by integer `score` descending; when scores tie, preserve their order in the input file. Give each sorted row a competition rank equal to one plus the number of input rows with a strictly higher score. Output an object with `ranking`, an array of objects with `id`, integer `score`, and integer `rank` in that sorted order. Do not sort tied rows by ID or team.

Write a UTF-8 `output.json` in the workspace root. Use the exact JSON field names, value types, and array order specified above. JSON object key order and whitespace do not matter.
