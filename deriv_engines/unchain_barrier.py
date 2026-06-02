from decimal import Decimal, InvalidOperation


DEFAULT_HIGHER_BARRIER = Decimal("0.10")
DEFAULT_LOWER_BARRIER = Decimal("0.10")


def _to_decimal(value):
    try:
        return Decimal(str(value).strip()).copy_abs()
    except (InvalidOperation, ValueError, TypeError):
        return None


def _format_decimal(value):
    value = value.normalize()
    if value == value.to_integral():
        return str(value.quantize(Decimal("1")))
    text = format(value, "f").rstrip("0")
    if text.endswith("."):
        text += "0"
    if text == "0.1":
        return "0.10"
    return text


def sanitize_unchain_higher_lower_barrier(barrier, contract_type):
    """Return a signed relative price barrier for UNCHAIN CALL/PUT trades."""
    contract = str(contract_type or "").upper().strip()
    if contract in ("HIGHER", "RISE"):
        contract = "CALL"
    elif contract in ("LOWER", "FALL"):
        contract = "PUT"
    if contract not in ("CALL", "PUT"):
        return barrier

    sign = "+" if contract == "CALL" else "-"
    default_value = DEFAULT_HIGHER_BARRIER if contract == "CALL" else DEFAULT_LOWER_BARRIER
    raw = "" if barrier in (None, "") else str(barrier).strip()
    magnitude = None

    if raw:
        signed = raw[0] in "+-"
        candidate = raw[1:] if signed else raw
        parsed = _to_decimal(candidate)
        if parsed is not None and parsed > 0:
            is_integer_digit = parsed == parsed.to_integral() and Decimal("0") <= parsed <= Decimal("9")
            if not is_integer_digit:
                magnitude = parsed

    if magnitude is None:
        magnitude = default_value

    return f"{sign}{_format_decimal(magnitude)}"
