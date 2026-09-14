import sys
import types
from pathlib import Path

BRIDGE = Path(__file__).resolve().parents[1] / "mt5_module" / "mt5_bridge"
sys.path.insert(0, str(BRIDGE))
multipart = types.ModuleType("multipart")
multipart.__version__ = "0.0.20"
multipart_parser = types.ModuleType("multipart.multipart")
multipart_parser.parse_options_header = lambda value: (value, {})
sys.modules.setdefault("multipart", multipart)
sys.modules.setdefault("multipart.multipart", multipart_parser)

import main


def test_empty_quote_poll_is_a_noop():
    assert main.get_quotes("", None) == []


def test_quote_proxy_preserves_single_and_multiple_symbol_names(monkeypatch):
    calls = []
    monkeypatch.setattr(main.multi_account_client, "account_request", lambda login, path, timeout=10: calls.append((login, path)) or [])

    main.get_quotes("EURUSD", 123)
    main.get_quotes("Volatility 10 Index", 123)
    main.get_quotes("EURUSD,Volatility 10 Index,GBPUSD", 123)

    assert calls[0] == (123, "/quotes?symbols=EURUSD")
    assert calls[1] == (123, "/quotes?symbols=Volatility%2010%20Index")
    assert calls[2] == (123, "/quotes?symbols=EURUSD%2CVolatility%2010%20Index%2CGBPUSD")
