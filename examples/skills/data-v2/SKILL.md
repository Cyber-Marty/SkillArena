---
name: data-workflow
description: Check edge cases and reconcile small CSV and JSON transformations.
version: 2.0.0
---

# Data workflow

1. Read TASK.md and all inputs. Make a checklist of output fields, types, sort order,
   inclusion rules, tie breakers, and missing-value rules before calculating.
2. Preserve identifiers as strings, including leading zeroes. Distinguish a missing
   value, null, an empty string, zero, and false according to the stated contract.
3. For money, reason in decimal units or integer minor units. Apply rounding at the
   exact stage requested. Compute line totals before aggregates when specified.
4. Check join cardinality: unmatched and repeated keys need explicit treatment.
   Follow the task's winner rule for duplicate records and tie rules for rankings.
5. Normalize time to the requested zone before grouping; retain explicit offsets
   when comparing instants. Check boundaries rather than guessing inclusivity.
6. Reconcile counts and totals against the input. Recheck at least one boundary
   case, one missing value, and one duplicate if present.
7. Write only the requested output.json structure. Use check_output for syntax,
   then inspect your values against the task checklist; valid JSON is not proof
   of a correct answer. Do not invent additional cleaning rules.
