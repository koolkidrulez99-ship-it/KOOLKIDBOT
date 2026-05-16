from .contract_resolver import contracts_for_candidates, normalize_contract_type


SINGLE_BARRIER_CONTRACTS = {
    "CALL",
    "PUT",
    "DIGITOVER",
    "DIGITUNDER",
    "DIGITMATCH",
    "DIGITDIFF",
    "DIGITEVEN",
    "DIGITODD",
    "ONETOUCH",
    "NOTOUCH",
}


def barrier_values(item):
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


def allows_no_barrier(item):
    try:
        barriers_count = int(float((item or {}).get("barriers") or 0))
    except Exception:
        barriers_count = 0
    category = str((item or {}).get("barrier_category") or "").strip().lower()
    return barriers_count <= 0 and not barrier_values(item) and category in ("", "none", "no_barrier")


def duration_matches(item, duration, duration_unit, duration_matcher=None):
    if not duration_matcher:
        return True
    try:
        return bool(duration_matcher(item, int(float(duration or 0)), str(duration_unit or "t").lower()))
    except Exception:
        return True


def sanitize_parameters(parameters, *, contracts_for, contract_type, requested_barrier, duration, duration_unit, duration_matcher=None):
    original = dict(parameters or {})
    sanitized = dict(parameters or {})
    removed = {}
    resolved_barrier = None
    matched_item = None
    deriv_contract = normalize_contract_type(contract_type)
    candidates = [
        item for item in contracts_for_candidates(contracts_for, deriv_contract)
        if duration_matches(item, duration, duration_unit, duration_matcher=duration_matcher)
    ] or contracts_for_candidates(contracts_for, deriv_contract)
    if candidates:
        matched_item = candidates[0]

    def remove(name):
        if name in sanitized:
            removed[name] = sanitized.pop(name, None)

    if deriv_contract in SINGLE_BARRIER_CONTRACTS:
        remove("barrier2")

    if deriv_contract in ("DIGITOVER", "DIGITUNDER", "DIGITMATCH", "DIGITDIFF"):
        try:
            digit = int(float(requested_barrier))
        except Exception:
            return sanitized, f"Invalid barrier for {deriv_contract}: {requested_barrier}", {
                "original": original,
                "removed": removed,
                "matched_item": matched_item,
                "resolved_barrier": resolved_barrier,
            }
        if digit < 0 or digit > 9:
            return sanitized, f"Invalid barrier for {deriv_contract}: {requested_barrier}", {
                "original": original,
                "removed": removed,
                "matched_item": matched_item,
                "resolved_barrier": resolved_barrier,
            }
        sanitized["barrier"] = digit
        resolved_barrier = digit
    elif deriv_contract in ("DIGITEVEN", "DIGITODD"):
        remove("barrier")
        remove("barrier2")
    elif deriv_contract in ("CALL", "PUT"):
        if any(allows_no_barrier(item) for item in candidates):
            remove("barrier")
            remove("barrier2")
        else:
            values = []
            for item in candidates:
                values.extend(barrier_values(item))
            values = [str(v).strip() for v in values if str(v).strip()]
            requested = "" if requested_barrier in (None, "") else str(requested_barrier).strip()
            if requested and requested in values:
                sanitized["barrier"] = requested
                resolved_barrier = requested
            elif values:
                sanitized["barrier"] = values[0]
                resolved_barrier = values[0]
            elif not candidates:
                return sanitized, "Invalid barrier for CALL/PUT on this market/duration", {
                    "original": original,
                    "removed": removed,
                    "matched_item": matched_item,
                    "resolved_barrier": resolved_barrier,
                }
            else:
                remove("barrier")
                remove("barrier2")
    elif deriv_contract in ("ONETOUCH", "NOTOUCH"):
        remove("barrier2")
        values = []
        for item in candidates:
            values.extend(barrier_values(item))
        values = [str(v).strip() for v in values if str(v).strip()]
        requested = "" if requested_barrier in (None, "") else str(requested_barrier).strip()
        if requested and requested in values:
            sanitized["barrier"] = requested
            resolved_barrier = requested
        elif values:
            sanitized["barrier"] = values[0]
            resolved_barrier = values[0]
        else:
            return sanitized, f"Invalid barrier for {deriv_contract} on this market/duration", {
                "original": original,
                "removed": removed,
                "matched_item": matched_item,
                "resolved_barrier": resolved_barrier,
            }

    return sanitized, None, {
        "original": original,
        "removed": removed,
        "matched_item": matched_item,
        "resolved_barrier": resolved_barrier,
    }

