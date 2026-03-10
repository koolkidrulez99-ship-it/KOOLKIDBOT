import pytest

from server import _is_contract_settled_fast


@pytest.mark.parametrize(
    "contract",
    [
        {"is_sold": True},
        {"is_settled": True},
        {"status": "sold"},
        {"status": "won"},
        {"status": "lost"},
        {"status": "settled"},
        {"status": "closed"},
        {"status": "expired"},
        {"status": "cancelled"},
        {"status": "canceled"},
        {"sell_price": 0},
        {"sell_price": 1.25},
    ],
)
def test_is_contract_settled_fast_true(contract):
    assert _is_contract_settled_fast(contract) is True


@pytest.mark.parametrize(
    "contract",
    [
        {},
        {"status": "open"},
        {"status": "purchase"},
        {"status": "close requested"},
        {"sell_price": ""},
        {"sell_price": None},
    ],
)
def test_is_contract_settled_fast_false(contract):
    assert _is_contract_settled_fast(contract) is False
