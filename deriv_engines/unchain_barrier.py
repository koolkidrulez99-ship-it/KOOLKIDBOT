from decimal import Decimal, InvalidOperation


DEFAULT_HIGHER_BARRIER = Decimal("0.10")
DEFAULT_LOWER_BARRIER = Decimal("0.10")


def _to_decimal(value):
    try:
        return Decimal(str(value).strip()).copy_abs()
    except (InvalidOperation, ValueError, TypeError):
        return None


def _to_signed_decimal(value):
    try:
        return Decimal(str(value).strip())
    except (InvalidOperation, ValueError, TypeError):
        return None


def _decimal_places(value):
    text = str(value or "").strip()
    if not text:
        return None
    if "e" in text.lower():
        parsed = _to_signed_decimal(text)
        if parsed is None:
            return None
        return max(0, -parsed.as_tuple().exponent)
    if "." in text:
        return len(text.split(".", 1)[1])
    return 0


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
    contract_type = str((item or {}).get("contract_type") or "").upper().strip()
    if contract_type not in ("CALL", "PUT"):
        return False
    has_barrier = bool(contract_item_barrier_values(item))
    try:
        has_barrier = has_barrier or int(float((item or {}).get("barriers") or 0)) > 0
    except Exception:
        has_barrier = has_barrier or bool((item or {}).get("barriers"))
    if not has_barrier:
        return False
    return True


def contract_item_direction(item):
    contract_type = str((item or {}).get("contract_type") or "").upper().strip()
    if contract_type == "CALL":
        return "up"
    if contract_type == "PUT":
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
                continue
        if not duration_matches:
            return None, "Deriv Higher/Lower is not supported for the selected duration on this market"
        matches = duration_matches

    def score(item):
        text = _item_text(item)
        contract_type = str((item or {}).get("contract_type") or "").upper().strip()
        return (
            2 if str((item or {}).get("sentiment") or "").lower().strip() == wanted_direction else 0,
            1 if contract_type in ("CALL", "PUT") else 0,
            1 if contract_item_barrier_values(item) else 0,
            1 if "callput" in text or "higher" in text or "lower" in text else 0,
        )

    return sorted(matches, key=score, reverse=True)[0], None


def _barrier_range_rule(item):
    value = (item or {}).get("barrier_range")
    return value if isinstance(value, dict) else {}


def _barrier_precision(contract_item, requested=None):
    item = contract_item or {}
    for key in ("barrier_precision", "barrier_decimals", "display_decimals"):
        value = item.get(key)
        if value in (None, ""):
            continue
        try:
            return max(0, int(float(value)))
        except Exception:
            pass
    rule = _barrier_range_rule(item)
    for key in ("step", "interval", "pip_size"):
        value = rule.get(key)
        if value not in (None, ""):
            places = _decimal_places(value)
            if places is not None:
                return places
    places = [
        _decimal_places(value)
        for value in contract_item_barrier_values(item)
        if _decimal_places(value) is not None
    ]
    if places:
        return max(places)
    return _decimal_places(requested)


def _format_signed_barrier(magnitude, direction, places=None):
    if magnitude is None or magnitude <= 0:
        return None
    text = format(magnitude, "f")
    if places is not None:
        text = f"{magnitude:.{int(places)}f}"
    elif "." in text:
        text = text.rstrip("0").rstrip(".")
    sign = "+" if normalize_unchain_direction(direction) == "up" else "-"
    return f"{sign}{text}"


def _normalize_allowed_barrier(value, direction):
    parsed = _to_decimal(value)
    if parsed is None or parsed <= 0:
        return None
    places = _decimal_places(value)
    return _format_signed_barrier(parsed, direction, places)


def _requested_barrier_magnitude(value):
    raw = "" if value in (None, "") else str(value).strip()
    if not raw:
        return None, None
    candidate = raw[1:] if raw[0] in "+-" else raw
    parsed = _to_decimal(candidate)
    if parsed is None or parsed <= 0:
        return None, raw
    return parsed, raw


def _range_value(rule, *keys):
    for key in keys:
        value = rule.get(key)
        if value not in (None, ""):
            return _to_signed_decimal(value)
    return None


def _barrier_allowed_by_range(signed_value, rule):
    if not rule:
        return True
    parsed = _to_signed_decimal(signed_value)
    if parsed is None:
        return False
    minimum = _range_value(rule, "min", "minimum", "from")
    maximum = _range_value(rule, "max", "maximum", "to")
    compare_value = parsed
    compare_minimum = minimum
    compare_maximum = maximum
    if parsed < 0 and (
        minimum is None or minimum >= 0
    ) and (
        maximum is None or maximum >= 0
    ):
        compare_value = parsed.copy_abs()
        compare_minimum = minimum.copy_abs() if minimum is not None else None
        compare_maximum = maximum.copy_abs() if maximum is not None else None
    if compare_minimum is not None and compare_value < compare_minimum:
        return False
    if compare_maximum is not None and compare_value > compare_maximum:
        return False
    step = _range_value(rule, "step", "interval", "pip_size")
    if step is not None and step != 0:
        base = compare_minimum if compare_minimum is not None else Decimal("0")
        try:
            if (compare_value - base) % step.copy_abs() != 0:
                return False
        except Exception:
            return False
    return True


def validate_unchain_higher_lower_barrier(barrier, direction, contract_item=None):
    wanted_direction = normalize_unchain_direction(direction)
    if wanted_direction not in ("up", "down"):
        return None, "Invalid UNCHAIN direction"
    contract_type = str((contract_item or {}).get("contract_type") or "").upper().strip()
    expected_contract = "CALL" if wanted_direction == "up" else "PUT"
    if contract_type != expected_contract:
        return None, f"Deriv Higher/Lower requires {expected_contract} for the selected side"

    requested_magnitude, raw_requested = _requested_barrier_magnitude(barrier)
    if requested_magnitude is None:
        return None, "Invalid UNCHAIN Higher/Lower barrier"
    requested_places = _decimal_places(raw_requested)
    requested = _format_signed_barrier(requested_magnitude, wanted_direction, requested_places)
    requested_decimal = _to_signed_decimal(requested)
    if requested_decimal is None or requested_decimal == 0:
        return None, "Invalid UNCHAIN Higher/Lower barrier"
    if wanted_direction == "up" and requested_decimal <= 0:
        return None, "Higher requires a positive relative barrier"
    if wanted_direction == "down" and requested_decimal >= 0:
        return None, "Lower requires a negative relative barrier"

    allowed_values = []
    for value in contract_item_barrier_values(contract_item):
        normalized = _normalize_allowed_barrier(value, wanted_direction)
        if normalized:
            allowed_values.append(normalized)
    allowed_values = list(dict.fromkeys(allowed_values))
    requested_magnitude = requested_decimal.copy_abs()
    if allowed_values:
        for allowed in allowed_values:
            allowed_decimal = _to_signed_decimal(allowed)
            if allowed_decimal is not None and allowed_decimal.copy_abs() == requested_magnitude:
                return allowed, None
        return None, (
            f"Barrier {requested} is not supported for this UNCHAIN Higher/Lower contract; "
            f"supported barriers: {', '.join(allowed_values[:8])}"
        )

    precision = _barrier_precision(contract_item, requested)
    formatted = _format_signed_barrier(requested_magnitude, wanted_direction, precision)
    if not formatted or formatted[0] not in "+-":
        return None, "Invalid UNCHAIN Higher/Lower barrier"
    rule = _barrier_range_rule(contract_item)
    if not _barrier_allowed_by_range(formatted, rule):
        return None, f"Barrier {formatted} is outside Deriv's supported range for this market"
    return formatted, None


def resolve_unchain_higher_lower_barrier(barrier, direction, contract_item=None):
    resolved, _ = validate_unchain_higher_lower_barrier(barrier, direction, contract_item)
    return resolved
