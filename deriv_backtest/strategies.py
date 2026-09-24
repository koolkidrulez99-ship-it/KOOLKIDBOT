"""Research adapters; all detectors receive only ticks observed so far."""
from dataclasses import dataclass
from collections import deque
from cloud_reinvest_engine import CloudReinvestEngine
from strategies.koolkid import KoolKidStrategy


@dataclass(frozen=True)
class Strategy:
    id: str
    name: str
    required: int
    contracts: tuple
    detector: object
    duration: int = 1


def absence(digits, target, contract):
    if len(digits) >= 11 and digits[-1] == target and target not in digits[-11:-1]:
        return contract, target


def golden(digits):
    # Pure existing confidence/loss-guard implementation. No execution state.
    pick = KoolKidStrategy()._golden_card_pick_trade(digits[-20:], 'BOTH')
    if not pick['blocked'] and pick['confidence_pct'] >= 55:
        return 'DIGIT' + pick['type'], pick['barrier']


def differ(digits):
    # Reuse the selective SAFE detector only; this object has no socket or execution callback.
    analyzer = CloudReinvestEngine('global-research', '', {'cloud_trade_type': 'digit_differs', 'cloud_trade_mode': 'SAFE'})
    candidate = analyzer._differ_candidate({'digits': deque(digits[-100:]), 'tick': len(digits)})
    return ('DIGITDIFF', candidate['digit']) if candidate else None


REGISTRY = (
    Strategy('under9', 'Under 9 / ten-tick absence', 11, ('DIGITUNDER',), lambda d: absence(d, 9, 'DIGITUNDER')),
    Strategy('over0', 'Over 0 / ten-tick absence', 11, ('DIGITOVER',), lambda d: absence(d, 0, 'DIGITOVER')),
    Strategy('golden', 'Golden Card / Over 1 + Under 8', 20, ('DIGITOVER', 'DIGITUNDER'), golden),
    Strategy('differ_safe', 'Selective Differ / SAFE setup', 100, ('DIGITDIFF',), differ),
)


def evaluate(contract, barrier, digit):
    if contract == 'DIGITUNDER':
        return digit < barrier
    if contract == 'DIGITOVER':
        return digit > barrier
    if contract == 'DIGITDIFF':
        return digit != barrier
    if contract == 'DIGITMATCH':
        return digit == barrier
    if contract == 'DIGITEVEN':
        return digit % 2 == 0
    if contract == 'DIGITODD':
        return digit % 2 == 1
    raise ValueError('Unsupported research contract')
