"""Number formatting identical to Rust's `{}` for f64 (shortest round-trip, never exponent)."""
from decimal import Decimal


def f(value):
    value = float(value)
    if value == int(value) and abs(value) < 1e16:
        return "-0" if (value == 0 and str(value).startswith("-")) else str(int(value))
    text = repr(value)
    if "e" in text or "E" in text:
        text = format(Decimal(text), "f")
    return text
