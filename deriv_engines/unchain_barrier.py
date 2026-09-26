from decimal import Decimal, InvalidOperation


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
    """Normalize only the sign for an explicit UNCHAIN Higher/Lower barrier.

    This helper never invents a default magnitude. The authoritative value for
    OAuth/PAT trades is resolved later from the matched contracts_for item.
    """
    direction = normalize_unchain_direction(contract_type)
    if direction not in ("up", "down"):
        return barrier
    raw = "" if barrier in (None, "") else str(barrier).strip()
    if not raw:
        return None
    candidate = raw[1:] if raw[:1] in "+-" else raw
    magnitude = _to_decimal(candidate)
    if magnitude is None:
        return barrier
    return _format_signed_barrier(
        magnitude,
        direction,
        _decimal_places(raw),
        allow_zero=True,
    )


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


def contract_item_supports_second_barrier(item):
    try:
        count = int(float((item or {}).get("barriers") or 0))
    except Exception:
        count = 0
    return count >= 2 or (item or {}).get("barrier2") not in (None, "")


def contract_item_second_barrier_value(item):
    value = (item or {}).get("barrier2")
    if value in (None, ""):
        return None
    return str(value).strip()


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
    if contract_type not in ("CALL", "PUT", "HIGHER", "LOWER"):
        return False

    has_barrier = bool(contract_item_barrier_values(item))
    try:
        has_barrier = has_barrier or int(float((item or {}).get("barriers") or 0)) > 0
    except Exception:
        has_barrier = has_barrier or bool((item or {}).get("barriers"))
    range_rule = (item or {}).get("barrier_range")
    if isinstance(range_rule, dict) and range_rule:
        has_barrier = True
    if (item or {}).get("barrier2") not in (None, ""):
        has_barrier = True

    # Plain Rise/Fall CALL/PUT has no Higher/Lower barrier requirement and
    # must not be selected for UNCHAIN.
    return bool(has_barrier)


def contract_item_direction(item):
    sentiment = normalize_unchain_direction((item or {}).get("sentiment"))
    if sentiment in ("up", "down"):
        return sentiment
    contract_type = str((item or {}).get("contract_type") or "").upper().strip()
    if contract_type in ("CALL", "HIGHER"):
        return "up"
    if contract_type in ("PUT", "LOWER"):
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
            1 if contract_type in ("CALL", "PUT", "HIGHER", "LOWER") else 0,
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


def _format_signed_barrier(magnitude, direction, places=None, *, allow_zero=False):
    if magnitude is None or magnitude < 0 or (magnitude == 0 and not allow_zero):
        return None
    text = format(magnitude, "f")
    if places is not None:
        text = f"{magnitude:.{int(places)}f}"
    elif "." in text:
        text = text.rstrip("0").rstrip(".")
    if not text:
        text = "0"
    sign = "+" if normalize_unchain_direction(direction) == "up" else "-"
    return f"{sign}{text}"


def _normalize_allowed_barrier(value, direction):
    raw = "" if value in (None, "") else str(value).strip()
    if not raw:
        return None
    parsed = _to_signed_decimal(raw)
    if parsed is None:
        return None

    # Preserve Deriv's exact signed representation, including +0.0/-0.0 and
    # decimal precision. If Deriv omitted a sign, add only the side sign.
    if raw[:1] in "+-":
        return raw
    return _format_signed_barrier(
        parsed.copy_abs(),
        direction,
        _decimal_places(raw),
        allow_zero=True,
    )


def _requested_barrier_magnitude(value):
    raw = "" if value in (None, "") else str(value).strip()
    if not raw:
        return None, None
    candidate = raw[1:] if raw[:1] in "+-" else raw
    parsed = _to_decimal(candidate)
    if parsed is None:
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

    matched_direction = contract_item_direction(contract_item)
    if matched_direction != wanted_direction:
        return None, "Matched Deriv contract does not represent the selected Higher/Lower side"

    # New Deriv Options contracts can advertise +0.0 as the ATM/default
    # barrier sentinel while rejecting a literal barrier="+0.0" proposal.
    # For that server-advertised zero, the valid proposal form is to omit the
    # barrier field. Non-zero advertised barriers remain literal.
    allowed_values = []
    for value in contract_item_barrier_values(contract_item):
        normalized = _normalize_allowed_barrier(value, wanted_direction)
        if normalized is not None:
            allowed_values.append(normalized)
    allowed_values = list(dict.fromkeys(allowed_values))

    requested_magnitude, raw_requested = _requested_barrier_magnitude(barrier)
    if allowed_values:
        allowed_decimals = [
            _to_signed_decimal(value)
            for value in allowed_values
            if _to_signed_decimal(value) is not None
        ]
        zero_only = bool(allowed_decimals) and all(value == 0 for value in allowed_decimals)
        if requested_magnitude is None:
            if zero_only:
                return None, None
            return None, "Invalid UNCHAIN Higher/Lower barrier"
        for allowed in allowed_values:
            allowed_decimal = _to_signed_decimal(allowed)
            if allowed_decimal is not None and allowed_decimal.copy_abs() == requested_magnitude:
                if allowed_decimal == 0:
                    return None, None
                return allowed, None
        chosen = allowed_values[0]
        chosen_decimal = _to_signed_decimal(chosen)
        if chosen_decimal == 0:
            return None, None
        return chosen, None

    if requested_magnitude is None:
        return None, "Invalid UNCHAIN Higher/Lower barrier"

    requested_places = _decimal_places(raw_requested)
    allow_zero = requested_magnitude == 0
    formatted = _format_signed_barrier(
        requested_magnitude,
        wanted_direction,
        requested_places,
        allow_zero=allow_zero,
    )
    if not formatted or formatted[:1] not in "+-":
        return None, "Invalid UNCHAIN Higher/Lower barrier"

    parsed = _to_signed_decimal(formatted)
    if parsed is None:
        return None, "Invalid UNCHAIN Higher/Lower barrier"
    if parsed != 0:
        if wanted_direction == "up" and parsed <= 0:
            return None, "Higher requires a positive relative barrier"
        if wanted_direction == "down" and parsed >= 0:
            return None, "Lower requires a negative relative barrier"

    rule = _barrier_range_rule(contract_item)
    if parsed == 0 and not rule:
        return None, "Zero UNCHAIN Higher/Lower barrier is only valid when Deriv advertises it"
    precision = _barrier_precision(contract_item, formatted)
    formatted = _format_signed_barrier(
        requested_magnitude,
        wanted_direction,
        precision,
        allow_zero=allow_zero,
    )
    if not _barrier_allowed_by_range(formatted, rule):
        return None, f"Barrier {formatted} is outside Deriv's supported range for this market"
    return formatted, None


def resolve_unchain_higher_lower_barrier(barrier, direction, contract_item=None):
    resolved, _ = validate_unchain_higher_lower_barrier(barrier, direction, contract_item)
    return resolved
