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
    direction = normalize_unchain_direction(contract_type)
    if direction not in ("up", "down"):
        return barrier

    sign = "+" if direction == "up" else "-"
    default_value = DEFAULT_HIGHER_BARRIER if direction == "up" else DEFAULT_LOWER_BARRIER
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


def normalize_unchain_direction(value):
    raw = str(value or "").upper().strip()
    if raw in ("HIGHER", "UP", "RISE", "CALL"):
        return "up"
    if raw in ("LOWER", "DOWN", "FALL", "PUT"):
        return "down"
    text = raw.replace("_", " ")
    if "HIGHER" in text or "RISE" in text:
        return "up"
    if "LOWER" in text or "FALL" in text:
        return "down"
    return ""


def contract_item_barrier_values(item):
    values = []
    for key in ("barrier", "barrier1"):
        value = (item or {}).get(key)
        if value not in (None, ""):
            values.append(str(value).strip())
    for key in ("barrier_choices", "barrier_range"):
        value = (item or {}).get(key)
        if isinstance(value, (list, tuple)):
            values.extend(str(v).strip() for v in value if v not in (None, ""))
    return [v for v in values if v]


def _item_text(item):
    keys = (
        "contract_type",
        "contract_category",
        "contract_category_display",
        "category",
        "display_name",
        "longcode",
        "sentiment",
    )
    return " ".join(str((item or {}).get(key) or "") for key in keys).lower()


def _item_is_higher_lower_contract(item):
    text = _item_text(item)
    contract_type = str((item or {}).get("contract_type") or "").upper().strip()
    if contract_type in ("CALL", "PUT", "HIGHER", "LOWER", "RISE", "FALL"):
        return True
    return any(
        token in text
        for token in (
            "callput",
            "call put",
            "call/put",
            "higher",
            "lower",
            "rise",
            "fall",
            "up/down",
            "updown",
        )
    )


def contract_item_direction(item):
    sentiment = str((item or {}).get("sentiment") or "").lower().strip()
    if sentiment in ("up", "down"):
        return sentiment
    contract_type = str((item or {}).get("contract_type") or "").upper().strip()
    direct = normalize_unchain_direction(contract_type)
    if direct:
        return direct
    text = _item_text(item)
    if "higher" in text or "rise" in text:
        return "up"
    if "lower" in text or "fall" in text:
        return "down"
    return ""


def relevant_unchain_contracts(contracts_for):
    return [
        item for item in ((contracts_for or {}).get("available") or [])
        if isinstance(item, dict) and _item_is_higher_lower_contract(item)
    ]


def choose_unchain_contract(contracts_for, direction, *, duration=None, duration_unit=None, duration_matcher=None):
    wanted_direction = normalize_unchain_direction(direction)
    if wanted_direction not in ("up", "down"):
        return None, "Invalid UNCHAIN direction"
    available = relevant_unchain_contracts(contracts_for)
    matches = [item for item in available if contract_item_direction(item) == wanted_direction]
    if not matches:
        return None, f"No Deriv Higher/Lower contract is available for direction {wanted_direction}"

    if duration_matcher:
        duration_matches = []
        for item in matches:
            try:
                if duration_matcher(item, int(float(duration or 0)), str(duration_unit or "t").lower()):
                    duration_matches.append(item)
            except Exception:
                duration_matches.append(item)
        if duration_matches:
            matches = duration_matches

    def score(item):
        text = _item_text(item)
        contract_type = str((item or {}).get("contract_type") or "").upper().strip()
        return (
            2 if str((item or {}).get("sentiment") or "").lower().strip() == wanted_direction else 0,
            1 if contract_type in ("CALL", "PUT", "HIGHER", "LOWER", "RISE", "FALL") else 0,
            1 if contract_item_barrier_values(item) else 0,
            1 if "callput" in text or "higher" in text or "lower" in text else 0,
        )

    return sorted(matches, key=score, reverse=True)[0], None


def resolve_unchain_higher_lower_barrier(barrier, direction, contract_item=None):
    item_values = contract_item_barrier_values(contract_item)
    requested = sanitize_unchain_higher_lower_barrier(barrier, direction)
    if item_values:
        if requested in item_values:
            return requested
        wanted_sign = "+" if normalize_unchain_direction(direction) == "up" else "-"
        signed_values = [value for value in item_values if str(value).strip().startswith(wanted_sign)]
        if signed_values:
            return signed_values[0]
        return item_values[0]
    return requested
