from __future__ import annotations

from typing import Any, Callable

from .catalog import NATIVE_PRESETS
from .fib import evaluate_emerald, evaluate_red
from .gold import evaluate_gold
from .models import NativeSignal
from .primordial import evaluate_black, evaluate_blue
from .silver import evaluate_silver
from .white import evaluate_white

Evaluator = Callable[[dict[str, Any]], NativeSignal]

EVALUATORS: dict[str, Evaluator] = {
    "primordial_black": evaluate_black,
    "primordial_blue": evaluate_blue,
    "primordial_emerald": evaluate_emerald,
    "primordial_gold": evaluate_gold,
    "primordial_purple": lambda data: evaluate_black(data, purple=True),
    "primordial_red": evaluate_red,
    "primordial_silver": evaluate_silver,
    "primordial_white": evaluate_white,
}
def preset_for_bot(bot_id: int) -> dict[str, Any] | None:
    row = NATIVE_PRESETS.get(int(bot_id))
    return dict(row) if row else None


def evaluate(strategy_key: str, data: dict[str, Any]) -> NativeSignal:
    fn = EVALUATORS.get(str(strategy_key))
    if fn is None:
        meta = next((row for row in NATIVE_PRESETS.values() if row["key"] == strategy_key), None)
        name = meta["name"] if meta else strategy_key
        title = meta["title"] if meta else "Native strategy unavailable"
        return NativeSignal(
            strategy_key=strategy_key, strategy_name=name, title=title,
            stage="SOURCE_REQUIRED", reason="MQ5 source is required before this preset can run natively.",
        )
    return fn(data)


def ready_keys() -> list[str]:
    return list(EVALUATORS)
