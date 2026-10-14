"""External evaluator: this file is outside the agent's editable workspace."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path.cwd()))

from calculate import inclusive_total  # noqa: E402


assert inclusive_total([2, 3, 5], 0) == 2
assert inclusive_total([2, 3, 5], 1) == 5
assert inclusive_total([2, 3, 5], 2) == 10
assert inclusive_total([], 0) == 0
print("4/4 assertions passed")
