def resolve_symbol(active_symbols, requested_symbol, legacy_aliases=None):
    original = str(requested_symbol or "").strip()
    if not original:
        return None, "Invalid symbol for new Deriv API: "
    by_symbol = {}
    for item in active_symbols or []:
        if not isinstance(item, dict):
            continue
        symbol = str(item.get("symbol") or item.get("underlying_symbol") or "").strip()
        if symbol:
            by_symbol[symbol.upper()] = symbol
    upper = original.upper()
    if upper in by_symbol:
        return by_symbol[upper], None
    for alias in (legacy_aliases or {}).get(upper, ()):
        if str(alias).upper() in by_symbol:
            return by_symbol[str(alias).upper()], None
    return None, f"Invalid symbol for new Deriv API: {original}"

