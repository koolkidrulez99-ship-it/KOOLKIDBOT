import re


HUMAN_MANUAL_ACTIONS = {
    "HIGH_TICK": {
        "label": "High Tick",
        "aliases": ("TICKHIGH", "HIGH_TICK", "HIGHTICK", "HIGHLOWTICKHIGH"),
        "text": ("high tick", "tick high", "highlowticks"),
        "reject": ("low tick", "tick low", "only"),
        "default_duration": 5,
    },
    "LOW_TICK": {
        "label": "Low Tick",
        "aliases": ("TICKLOW", "LOW_TICK", "LOWTICK", "HIGHLOWTICKLOW"),
        "text": ("low tick", "tick low", "highlowticks"),
        "reject": ("high tick", "tick high", "only"),
        "default_duration": 5,
    },
    "ONLY_UPS": {
        "label": "Only Ups",
        "aliases": ("RUNHIGH", "ONLYUP", "ONLYUPS", "RUNSUP"),
        "text": ("only up", "only ups", "run high", "runs high", "only ups/only downs"),
        "reject": ("only down", "only downs", "run low", "runs low"),
        "default_duration": 2,
    },
    "ONLY_DOWNS": {
        "label": "Only Downs",
        "aliases": ("RUNLOW", "ONLYDOWN", "ONLYDOWNS", "RUNSDOWN"),
        "text": ("only down", "only downs", "run low", "runs low", "only ups/only downs"),
        "reject": ("only up", "only ups", "run high", "runs high"),
        "default_duration": 2,
    },
}


def normalize_human_manual_action(action):
    key = str(action or "").upper().strip().replace("-", "_").replace(" ", "_")
    aliases = {
        "HIGH": "HIGH_TICK",
        "LOW": "LOW_TICK",
        "UP": "ONLY_UPS",
        "UPS": "ONLY_UPS",
        "DOWN": "ONLY_DOWNS",
        "DOWNS": "ONLY_DOWNS",
    }
    key = aliases.get(key, key)
    return key if key in HUMAN_MANUAL_ACTIONS else ""


def _as_text(item):
    parts = []
    for key in (
        "contract_type",
        "contract_display",
        "contract_category",
        "contract_category_display",
        "display_name",
        "shortcode",
        "market",
        "submarket_display_name",
        "barrier_category",
        "barrier",
    ):
        val = item.get(key)
        if val not in (None, ""):
            parts.append(str(val))
    return " ".join(parts).lower()


def _duration_to_ticks(value):
    if value in (None, ""):
        return None
    if isinstance(value, (int, float)):
        return int(value)
    text = str(value).strip().lower()
    match = re.search(r"(-?\d+)", text)
    if not match:
        return None
    try:
        return int(match.group(1))
    except Exception:
        return None


def _duration_unit(item, fallback="t"):
    for key in ("duration_unit", "min_contract_duration_unit", "max_contract_duration_unit"):
        val = str(item.get(key) or "").strip().lower()
        if val in ("t", "s", "m", "h", "d"):
            return val
    for key in ("min_contract_duration", "max_contract_duration"):
        text = str(item.get(key) or "").strip().lower()
        if text and text[-1:] in ("t", "s", "m", "h", "d"):
            return text[-1:]
    return fallback


def _duration_bounds(item):
    unit = _duration_unit(item)
    min_duration = (
        _duration_to_ticks(item.get("min_contract_duration"))
        or _duration_to_ticks(item.get("min_duration"))
        or 1
    )
    max_duration = (
        _duration_to_ticks(item.get("max_contract_duration"))
        or _duration_to_ticks(item.get("max_duration"))
        or None
    )
    return max(1, int(min_duration)), (int(max_duration) if max_duration else None), unit


def _score_contract(item, action_key):
    meta = HUMAN_MANUAL_ACTIONS[action_key]
    contract_type = str(item.get("contract_type") or "").upper().strip()
    compact_type = re.sub(r"[^A-Z0-9]", "", contract_type)
    text = _as_text(item)
    if compact_type in meta["aliases"]:
        return 100
    category = str(item.get("contract_category") or "").lower().strip()
    display = str(item.get("contract_display") or item.get("display_name") or "").lower().strip()
    if action_key == "HIGH_TICK" and category == "highlowticks" and "high" in display:
        return 95
    if action_key == "LOW_TICK" and category == "highlowticks" and "low" in display:
        return 95
    if action_key == "ONLY_UPS" and category == "runs" and ("up" in display or "high" in display):
        return 95
    if action_key == "ONLY_DOWNS" and category == "runs" and ("down" in display or "low" in display):
        return 95
    if any(block in text for block in meta["reject"]):
        return 0
    if any(phrase in text for phrase in meta["text"]):
        return 80
    return 0


def build_human_manual_contract_info(available_contracts):
    info = {}
    available_contracts = list(available_contracts or [])
    for action_key, action_meta in HUMAN_MANUAL_ACTIONS.items():
        candidates = []
        for item in available_contracts:
            if not isinstance(item, dict):
                continue
            score = _score_contract(item, action_key)
            if score > 0:
                candidates.append((score, item))

        if not candidates:
            info[action_key] = {
                "available": False,
                "label": action_meta["label"],
                "message": "This contract is not available for the selected market.",
            }
            continue

        candidates.sort(key=lambda pair: pair[0], reverse=True)
        chosen = candidates[0][1]
        min_duration, max_duration, duration_unit = _duration_bounds(chosen)
        default_duration = max(min_duration, int(action_meta.get("default_duration") or min_duration))
        if max_duration is not None:
            default_duration = min(default_duration, max_duration)
        info[action_key] = {
            "available": True,
            "label": action_meta["label"],
            "contract_type": str(chosen.get("contract_type") or "").upper().strip(),
            "contract_display": chosen.get("contract_display") or chosen.get("display_name") or action_meta["label"],
            "min_duration": min_duration,
            "max_duration": max_duration,
            "duration_unit": duration_unit,
            "default_duration": default_duration,
            "message": "Available",
            "matched_contract": {
                "contract_type": chosen.get("contract_type"),
                "contract_display": chosen.get("contract_display") or chosen.get("display_name"),
                "contract_category": chosen.get("contract_category"),
                "min_contract_duration": chosen.get("min_contract_duration"),
                "max_contract_duration": chosen.get("max_contract_duration"),
            },
        }
    return info
