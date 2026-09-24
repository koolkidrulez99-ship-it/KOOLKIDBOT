"""Keep the independent research runtime out of legacy execution tests.

Existing execution tests exercise transports and strategy mechanics with the
admin confirmation switch off. Confirmation tests explicitly enable it. Neither
group reads or writes the operator's local research database or credentials.
"""
import pytest

from deriv_backtest import confirmation
from deriv_backtest.store import Store


@pytest.fixture(autouse=True)
def isolated_confirmation_store(tmp_path, monkeypatch):
    db = Store(tmp_path / 'confirmation.sqlite3')
    db.set('confirmation_policy', {'enabled': False})
    monkeypatch.setattr(confirmation, '_store', db)
    return db
