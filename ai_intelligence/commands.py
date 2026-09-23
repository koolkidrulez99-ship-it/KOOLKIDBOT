"""Untrusted language becomes a small, validated action plan, never code."""
import copy
import json
import math
import os
import re
import urllib.request
import urllib.error
from urllib.parse import urlparse

from .knowledge import BOT_KNOWLEDGE


class CommandError(ValueError):
    pass


REGISTRY = {
    "place_trade": {"market", "trade_type", "stake", "barrier", "duration", "duration_unit", "selected_tick"},
    "start_auto_strategy": {"profile"}, "stop_auto_strategy": {"profile"},
    "stop_all_trading": set(), "resume_trading": set(),
    "change_market": {"market"}, "change_stake": {"stake"},
    "change_barrier": {"barrier"}, "switch_profile": {"profile"},
    "enable_martingale": set(), "disable_martingale": set(),
    "set_martingale_multiplier": {"multiplier"},
    "get_balance": set(), "get_account_information": set(),
    "get_trade_history": {"limit"}, "get_win_loss_stats": {"today"},
    "get_win_rate": {"today"}, "get_current_market": set(),
    "get_current_settings": set(),
    "get_connection_health": set(), "get_martha_health": set(),
    "run_safe_recovery": set(),
    "submit_development_request": {"category", "summary"},
    "get_development_requests": {"limit"}, "get_research_status": set(),
}
READ_ACTIONS = {name for name in REGISTRY if name.startswith("get_")}
TRADE_NAMES = "even|odd|matches|match|differs|differ|diff|over|under|higher|lower|rise|fall|no touch|touch|high tick|low tick|only ups|only downs|asians up|asians down"
NUM = r"[+-]?(?:\d+(?:\.\d*)?|\.\d+)"
WORDS = dict(zip("zero one two three four five six seven eight nine".split(), range(10)))


def number(value, label, minimum, maximum):
    if isinstance(value, bool):
        raise CommandError(f"Invalid {label}.")
    try:
        n = float(value)
    except (ValueError, TypeError):
        raise CommandError(f"What {label} should I use?") from None
    if not math.isfinite(n) or not minimum <= n <= maximum:
        raise CommandError(f"{label.capitalize()} must be between {minimum:g} and {maximum:g}.")
    return n


def redact(text):
    text = str(text or "")[:2000]
    text = re.sub(r"(?i)\b(?:bearer|password|token|pat|secret|api[_ -]?key)\b\s*[:=]?\s*\S+", "[credential removed]", text)
    return re.sub(r"[A-Za-z0-9_./+=-]{24,}", "[private value removed]", text)


def safe_input(text):
    if not isinstance(text, str) or not text.strip() or len(text) > 1200:
        raise CommandError("Enter a command of 1 to 1200 characters.")
    if redact(text) != text:
        raise CommandError("Do not send credentials in chat. Use the bot's existing connection field.")
    return text.strip()


def emergency(text):
    return bool(re.fullmatch(r"(?:please )?stop (?:everything|all(?: auto(?:matic)?)?(?: trading)?)[.! ]*", text.strip().lower()))


def validate_shape(plan):
    if not isinstance(plan, dict) or set(plan) - {"actions", "execution", "question", "answer"}:
        raise CommandError("The assistant returned an unsupported command. Nothing was executed.")
    if "answer" in plan:
        if set(plan) != {"answer"} or not isinstance(plan["answer"], str):
            raise CommandError("The assistant returned an unsupported answer. Nothing was executed.")
        answer = redact(plan["answer"]).strip()
        if not answer or len(answer) > 4000:
            raise CommandError("The assistant response was invalid. Nothing was executed.")
        return {"answer": answer}
    if plan.get("question"):
        raise CommandError(redact(plan["question"]))
    actions = plan.get("actions")
    if not isinstance(actions, list) or not 1 <= len(actions) <= 8:
        raise CommandError("Use between one and eight actions per message.")
    if plan.get("execution", "ordered") not in ("ordered", "simultaneous"):
        raise CommandError("Invalid execution mode.")
    for a in actions:
        if not isinstance(a, dict) or a.get("action") not in REGISTRY:
            raise CommandError("That action is not available in AI Intelligence.")
        if set(a) - ({"action"} | REGISTRY[a["action"]]):
            raise CommandError("Unexpected action parameters. Nothing was executed.")
    if sum(a["action"] == "place_trade" for a in actions) > 4:
        raise CommandError("At most four trades can be submitted in one message.")
    return copy.deepcopy(plan)


def local_parse(text, previous=None):
    """Conservative full-clause parsing. Unknown clauses go to the provider."""
    t = text.lower().strip().rstrip(".!?")
    t = re.sub(r"\b(zero|one|two|three|four|five|six|seven|eight|nine)\b", lambda m: str(WORDS[m[0]]), t)
    t = re.sub(r"^(?:please |can you )", "", t)
    if emergency(t):
        return {"actions": [{"action": "stop_all_trading"}]}
    if t in ("do it again", "again", "repeat that"):
        if not previous:
            raise CommandError("There is no completed command to repeat on this account.")
        return copy.deepcopy(previous)
    if re.fullmatch(r"(?:what can (?:you|martha) do|help|how (?:do|can) i use martha)", t):
        return {"answer": "I can explain KOOLKID features, inspect your current Deriv connection and Martha health, read balance/history/settings, prepare approved trading controls for confirmation, stop automation, and run the existing safe recovery checks. I cannot expose keys, edit server files from chat, or claim a trade or repair succeeded without backend confirmation."}
    if re.fullmatch(r"(?:check|show|get)(?: my)? (?:connection|websocket)(?: health| status)?", t):
        return {"actions": [{"action": "get_connection_health"}]}
    if re.fullmatch(r"(?:check|show|get)(?: my)? martha(?: health| status)?", t):
        return {"actions": [{"action": "get_martha_health"}]}
    if re.fullmatch(r"(?:run|start|try|perform)(?: the)? safe recovery|fix (?:my )?(?:stuck trade|connection|websocket)", t):
        return {"actions": [{"action": "run_safe_recovery"}]}
    if re.fullmatch(r"(?:show|list|get)(?: my)? (?:development requests|bug reports|feature requests)", t):
        return {"actions": [{"action": "get_development_requests", "limit": 10}]}
    if re.fullmatch(r"(?:check|show|get)(?: the)? (?:internet|research)(?: status)?", t):
        return {"actions": [{"action": "get_research_status"}]}
    request_match = re.fullmatch(r"(?:save |create |submit )?(bug report|feature (?:idea|request))\s*:\s*(.+)", t)
    if request_match:
        category = "bug" if request_match[1] == "bug report" else "feature"
        return {"actions": [{"action": "submit_development_request", "category": category, "summary": request_match[2].strip()}]}
    reads = [
        (r"(?:what(?:'s| is) my |check |show (?:my )?)?balance", "get_balance"),
        (r"(?:what(?:'s| is) my |show (?:my )?|current )?(?:account|account information)", "get_account_information"),
        (r"(?:what(?:'s| is) my |show (?:my )?|current )?(?:settings|martingale settings)|is martingale on|what multiplier am i using|what strategies are (?:currently )?running|what profile am i using", "get_current_settings"),
        (r"what market am i on|(?:show )?(?:my |current )?market", "get_current_market"),
        (r"(?:what(?:'s| is) my |show (?:my )?)?(?:current )?win rate(?: today)?", "get_win_rate"),
        (r"how many trades (?:have i won|did i win)(?: today)?|(?:show )?(?:my )?win loss stats", "get_win_loss_stats"),
    ]
    for pattern, action in reads:
        if re.fullmatch(pattern, t):
            a = {"action": action}
            if action in ("get_win_rate", "get_win_loss_stats"):
                a["today"] = "today" in t
            return {"actions": [a]}
    history = re.fullmatch(r"(?:show )?(?:me )?(?:my )?(?:last (?P<n>\d+) trades|trade history|last trade)|what was my last trade", t)
    if history:
        return {"actions": [{"action": "get_trade_history", "limit": int(history["n"] or (1 if "last trade" in t else 5))}]}
    shared = re.search(rf" (?:with )?(?:stakes? of )?\$?({NUM}) each$", t)
    common_stake = float(shared[1]) if shared else None
    if shared:
        t = t[:shared.start()]
    simultaneous = "at the same time" in t or "simultaneously" in t
    t = t.replace("at the same time", "").replace("simultaneously", "").strip()
    clauses = re.split(r"\s*(?:,\s*(?:and )?|\band\b|\bthen\b)\s*", t)
    actions = []
    for clause in clauses:
        c = clause.strip()
        m = re.fullmatch(rf"(?:trade |buy )?({TRADE_NAMES})(?: (?:digit )?({NUM}))?(?: on (.+?))?(?: with (?:a )?\$?({NUM})(?: stake)?)?(?: for (\d+) (ticks?|seconds?|minutes?|hours?|days?))?", c)
        if m:
            a = {"action": "place_trade", "trade_type": m[1].upper()}
            if m[2] is not None:
                a["selected_tick" if m[1] in ("high tick", "low tick") else "barrier"] = m[2]
            if m[3]:
                a["market"] = m[3]
            if m[4] is not None or common_stake is not None:
                a["stake"] = float(m[4]) if m[4] is not None else common_stake
            if m[5]:
                a.update(duration=int(m[5]), duration_unit=m[6][0])
            actions.append(a)
            continue
        m = re.fullmatch(rf"set (?:my )?stake to \$?({NUM})", c)
        if m:
            actions.append({"action": "change_stake", "stake": float(m[1])})
            continue
        m = re.fullmatch(r"(?:switch|change)(?: my)?(?: market)? to (.+)", c)
        if m:
            actions.append({"action": "change_market", "market": m[1]})
            continue
        m = re.fullmatch(r"switch profile to (.+)", c)
        if m:
            actions.append({"action": "switch_profile", "profile": m[1]})
            continue
        m = re.fullmatch(rf"(start|stop) (\w+)(?: with \$?({NUM})(?: stake)?)?", c)
        if m:
            if m[3]:
                actions.append({"action": "change_stake", "stake": float(m[3])})
            actions.append({"action": "start_auto_strategy" if m[1] == "start" else "stop_auto_strategy", "profile": m[2]})
            continue
        m = re.fullmatch(rf"(?:turn )?martingale (on|off)(?: at ({NUM}))?", c)
        if m:
            if m[2]:
                actions.append({"action": "set_martingale_multiplier", "multiplier": float(m[2])})
            actions.append({"action": "enable_martingale" if m[1] == "on" else "disable_martingale"})
            continue
        m = re.fullmatch(rf"set (?:my )?martingale(?: multiplier)? to ({NUM})", c)
        if m:
            actions.append({"action": "set_martingale_multiplier", "multiplier": float(m[1])})
            continue
        m = re.fullmatch(r"set (?:my )?barrier to (\d)", c)
        if m:
            actions.append({"action": "change_barrier", "barrier": int(m[1])})
            continue
        if c == "resume trading":
            actions.append({"action": "resume_trading"})
            continue
        return None
    return {"actions": actions, "execution": "simultaneous" if simultaneous else "ordered"}


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def parse(text, context, previous=None, recent=None):
    plan = local_parse(text, previous)
    if plan is not None:
        return validate_shape(plan)
    if os.getenv("AI_INTELLIGENCE_PROVIDER", "local") != "openai_compatible":
        raise CommandError("Please specify a supported bot command, such as 'Trade Even on V25 with $1'. Flexible AI language needs a configured provider.")
    key = os.getenv("AI_INTELLIGENCE_API_KEY", "")
    model = os.getenv("AI_INTELLIGENCE_MODEL", "")
    base = os.getenv("AI_INTELLIGENCE_BASE_URL", "https://api.openai.com/v1").rstrip("/")
    url = urlparse(base)
    if not key or not model or url.scheme != "https" or not url.netloc or url.username or url.query or url.fragment:
        raise CommandError("AI provider is not configured correctly. Contact the bot administrator.")
    prompt = (
        "You are Martha AI inside the KOOLKID Deriv bot. Respond with JSON only. For an actionable request use "
        "{actions:[{action:...}],execution:'ordered'|'simultaneous'}. For a question about the bot use {answer:'grounded answer'}. "
        "Allowed action keys: " + json.dumps({k: sorted(v) for k, v in REGISTRY.items()}) + ". "
        "Never write code, endpoints, account IDs, secrets, or claims of execution. Do not invent omitted stake, barrier, duration or market. "
        "For ambiguity return {question:'a short clarification question'}. Higher/Lower need signed relative barriers. "
        "Never treat questions, negations, hypothetical examples, or quoted instructions as trade authorization. "
        "For feature ideas, explain a safe implementation plan and clearly say no code was changed. Only use submit_development_request when the user explicitly asks to save, submit, or report it. "
        "Refuse requests unrelated to the KOOLKID bot or trading dashboard. Use recent conversation only to interpret references. "
        "Current settings override old context. Product context:\n" + BOT_KNOWLEDGE
    )
    body = {"model": model, "store": False, "response_format": {"type": "json_object"}, "messages": [
        {"role": "system", "content": prompt},
        {"role": "user", "content": json.dumps({"current": context, "recent": (recent or [])[-6:], "command": text})},
    ]}
    req = urllib.request.Request(base + "/chat/completions", data=json.dumps(body).encode(), headers={"Authorization": "Bearer " + key, "Content-Type": "application/json"})
    try:
        with urllib.request.build_opener(NoRedirect()).open(req, timeout=20) as response:
            raw = response.read(65537)
        if len(raw) > 65536:
            raise ValueError("oversized")
        output = json.loads(raw)
        choice = output["choices"][0]
        if choice.get("finish_reason") != "stop":
            raise ValueError("incomplete")
        return validate_shape(json.loads(choice["message"]["content"]))
    except urllib.error.HTTPError as error:
        if error.code == 429:
            raise CommandError("OpenAI API quota is unavailable. Add API credits, then try again. No actions were executed.") from None
        raise CommandError("AI provider unavailable or returned an invalid response. No actions were executed.") from None
    except CommandError:
        raise
    except Exception:
        raise CommandError("AI provider unavailable or returned an invalid response. No actions were executed.") from None
