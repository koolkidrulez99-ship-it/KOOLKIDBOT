import re


CONTRACT_ALIASES = {
    "OVER": "DIGITOVER",
    "UNDER": "DIGITUNDER",
    "MATCHES": "DIGITMATCH",
    "MATCH": "DIGITMATCH",
    "DIFFERS": "DIGITDIFF",
    "DIFFER": "DIGITDIFF",
    "DIFF": "DIGITDIFF",
    "DIGITDIFFERS": "DIGITDIFF",
    "DIGITMATCHES": "DIGITMATCH",
    "EVEN": "DIGITEVEN",
    "ODD": "DIGITODD",
    "HIGHER": "CALL",
    "RISE": "CALL",
    "LOWER": "PUT",
    "FALL": "PUT",
    "TOUCH": "ONETOUCH",
    "NO TOUCH": "NOTOUCH",
    "NO_TOUCH": "NOTOUCH",
    "NO-TOUCH": "NOTOUCH",
}


def normalize_contract_type(value):
    raw = str(value or "").upper().strip()
    if not raw:
        return ""
    match = re.match(r"^(OVER|UNDER|MATCHES|MATCH|DIFFERS|DIFFER|DIFF)\s+([0-9])$", raw)
    if match:
        return CONTRACT_ALIASES.get(match.group(1), raw)
    return CONTRACT_ALIASES.get(raw, raw)


def contracts_for_candidates(contracts_for, contract_type):
    wanted = normalize_contract_type(contract_type)
    return [
        item for item in ((contracts_for or {}).get("available") or [])
        if str((item or {}).get("contract_type") or "").upper().strip() == wanted
    ]

