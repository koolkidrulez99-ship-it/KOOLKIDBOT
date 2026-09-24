"""Score is a research index, never a probability of winning."""
import math

WINDOWS = ('50', '100', '200', '500', 'ALL')


def empty():
    return dict(trades=0, wins=0, losses=0, priced=0, profit=0., payout_sum=0.,
                equity=0., peak=0., drawdown=0., losing=0, longest=0,
                historical=0, forward=0)


def accumulate(stats, trade):
    stats['trades'] += 1
    stats['wins' if trade['won'] else 'losses'] += 1
    stats['historical' if trade['origin'] == 'historical' else 'forward'] += 1
    stats['losing'] = 0 if trade['won'] else stats['losing'] + 1
    stats['longest'] = max(stats['longest'], stats['losing'])
    if trade.get('payout_ratio') is not None:
        stats['priced'] += 1
        stats['payout_sum'] += trade['payout_ratio']
        stats['profit'] += trade['profit']
        stats['equity'] += trade['profit']
        stats['peak'] = max(stats['peak'], stats['equity'])
        stats['drawdown'] = max(stats['drawdown'], stats['peak'] - stats['equity'])


def report(stats, samples):
    n, priced = stats['trades'], stats['priced']
    rate = stats['wins'] / n if n else None
    ev = stats['profit'] / priced if priced else None
    payout = stats['payout_sum'] / priced if priced else None
    quality = priced / n if n else 0
    confidence = min(1., n / 100)
    # EV includes broker payout; reliability and loss-path penalties prevent win-rate ranking.
    score = None
    if priced and n:
        edge = 50 + 50 * math.tanh(ev * 3)
        path = 100 / (1 + stats['drawdown'] / max(1, math.sqrt(priced)))
        streak = 100 / (1 + stats['longest'] / 5)
        score = round((.6 * edge + .25 * path + .15 * streak) * confidence * quality, 2)
    status = 'INSUFFICIENT_DATA' if n < 30 else 'RESEARCHING'
    if n >= 30 and quality >= .9:
        status = 'PAPER_TESTING'
    if n >= 100 and stats['forward'] >= 50 and quality >= .95:
        status = 'VALIDATED' if ev is not None and ev > 0 else 'DEGRADED'
    return dict(score=score, win_rate=round(rate * 100, 2) if rate is not None else None,
                paper_trades=n, wins=stats['wins'], losses=stats['losses'], ev=ev,
                average_payout=payout, break_even=(100 / payout if payout else None),
                max_drawdown=stats['drawdown'] if priced else None, longest_losing_streak=stats['longest'],
                historical_samples=stats['historical'], forward_samples=stats['forward'],
                sample_count=samples, priced_samples=priced, data_quality=quality,
                status=status, score_components={'sample_weight': confidence, 'payout_coverage': quality})
