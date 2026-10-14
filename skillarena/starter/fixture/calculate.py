"""A deliberately broken example for the synthetic demo."""


def inclusive_total(numbers: list[int], end_index: int) -> int:
    """Sum numbers from index 0 through end_index, inclusive."""
    return sum(numbers[:end_index])
