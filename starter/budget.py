from __future__ import annotations

import math
import re
import unicodedata
from dataclasses import dataclass
from functools import lru_cache


_NUMBER = r"(?:(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?|\.\d+)"
_AMOUNT = rf"(?:usd\s*|us\$\s*|\$\s*)?{_NUMBER}\s*(?:usd|dollars?)?"
_AMOUNT_RE = re.compile(rf"{_AMOUNT}\Z")
_NUMBER_RE = re.compile(_NUMBER)
_BOUND_PREFIXES = (
    (r"<=|at most|no more than|not more than|up to|maximum(?: of)?|max", False, True),
    (r"<|under|below|less than", False, False),
    (r">=|at least|no less than|not less than|minimum(?: of)?|min", True, True),
    (r">|over|above|more than", True, False),
)


@dataclass(frozen=True)
class BudgetInterval:
    """A supported USD price interval; absent bounds are unbounded."""

    lower: float | None = None
    upper: float | None = None
    lower_inclusive: bool = True
    upper_inclusive: bool = True

    def contains(self, price: float) -> bool:
        if self.lower is not None:
            if price < self.lower or (price == self.lower and not self.lower_inclusive):
                return False
        if self.upper is not None:
            if price > self.upper or (price == self.upper and not self.upper_inclusive):
                return False
        return True


def _amount(raw: str) -> float | None:
    raw = raw.strip()
    if not _AMOUNT_RE.fullmatch(raw):
        return None
    match = _NUMBER_RE.search(raw)
    number = float(match.group().replace(",", "")) if match else math.inf
    return number if math.isfinite(number) else None


def _valid(interval: BudgetInterval) -> bool:
    if interval.lower is None or interval.upper is None:
        return True
    return interval.lower < interval.upper or (
        interval.lower == interval.upper
        and interval.lower_inclusive
        and interval.upper_inclusive
    )


def _bound(raw: str) -> BudgetInterval | None:
    for prefix, is_lower, inclusive in _BOUND_PREFIXES:
        match = re.fullmatch(rf"(?:{prefix})\s*({_AMOUNT})", raw)
        if match:
            number = _amount(match.group(1))
            if number is None:
                return None
            if is_lower:
                return BudgetInterval(lower=number, lower_inclusive=inclusive)
            return BudgetInterval(upper=number, upper_inclusive=inclusive)
    match = re.fullmatch(rf"(?:==|=|exactly)\s*({_AMOUNT})", raw)
    if match:
        number = _amount(match.group(1))
        return BudgetInterval(number, number) if number is not None else None
    match = re.fullmatch(rf"({_AMOUNT})\s+(?:and above|and up|or above|or more)", raw)
    if match:
        number = _amount(match.group(1))
        return BudgetInterval(lower=number) if number is not None else None
    match = re.fullmatch(rf"({_AMOUNT})\s+(?:and below|or below|or less)", raw)
    if match:
        number = _amount(match.group(1))
        return BudgetInterval(upper=number) if number is not None else None
    return None


@lru_cache(maxsize=512)
def parse_budget(value: str) -> BudgetInterval | None:
    """Parse explicit bounds/ranges, or return None for unsupported syntax.

    Canonical forms include ``<= 60``, ``= 60``, ``between 20 and 60``, and
    ``>= 20 and < 60``. Only USD/$ (or unspecified currency) is supported; no
    currency conversion is inferred. Bare amounts and explicit around/about
    amounts retain the legacy +/- max($5, 25%) interpretation.
    """

    if not isinstance(value, str):
        return None
    raw = unicodedata.normalize("NFKC", value).casefold().strip().rstrip(".").strip()
    raw = raw.replace("≤", "<=").replace("≥", ">=").replace("–", "-").replace("—", "-")
    raw = re.sub(r"\s+", " ", raw)
    raw = re.sub(r"^(?:budget|price)(?: range)?(?: is| of)?\s*:?\s*", "", raw)
    # An explicitly declared USD currency can precede an operator or a range.
    raw = re.sub(r"^(?:usd\s+|us\$\s*|\$\s+)", "", raw)
    interval = _bound(raw)
    if interval is not None:
        return interval

    match = re.fullmatch(rf"between\s+({_AMOUNT})\s+and\s+({_AMOUNT})", raw)
    if match is None:
        match = re.fullmatch(rf"(?:from\s+)?({_AMOUNT})\s*(?:to|-)\s*({_AMOUNT})", raw)
    if match:
        lower, upper = _amount(match.group(1)), _amount(match.group(2))
        if lower is None or upper is None:
            return None
        interval = BudgetInterval(lower, upper)
        return interval if _valid(interval) else None

    clauses = raw.split(" and ")
    if len(clauses) > 1:
        bounds = [_bound(clause) for clause in clauses]
        if any(bound is None for bound in bounds):
            return None
        lower = upper = None
        lower_inclusive = upper_inclusive = True
        for bound in bounds:
            assert bound is not None
            if bound.lower is not None:
                if lower is None or bound.lower > lower:
                    lower, lower_inclusive = bound.lower, bound.lower_inclusive
                elif bound.lower == lower:
                    lower_inclusive = lower_inclusive and bound.lower_inclusive
            if bound.upper is not None:
                if upper is None or bound.upper < upper:
                    upper, upper_inclusive = bound.upper, bound.upper_inclusive
                elif bound.upper == upper:
                    upper_inclusive = upper_inclusive and bound.upper_inclusive
        interval = BudgetInterval(lower, upper, lower_inclusive, upper_inclusive)
        return interval if _valid(interval) else None

    approximate = re.sub(r"^(?:around|about|approximately)\s+", "", raw)
    amount = _amount(approximate)
    if amount is not None:
        tolerance = max(5.0, amount * 0.25)
        return BudgetInterval(max(0.0, amount - tolerance), amount + tolerance)
    return None


def budget_relation(price: float | None, value: str) -> int:
    """Return 1 match, -1 contradiction, or 0 for missing/unsupported evidence."""

    if price is None or isinstance(price, bool):
        return 0
    try:
        number = float(price)
    except (TypeError, ValueError):
        return 0
    if not math.isfinite(number) or number < 0:
        return 0
    interval = parse_budget(value)
    return 0 if interval is None else (1 if interval.contains(number) else -1)
