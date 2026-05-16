class LegacyDerivTradeEngine:
    """Marker wrapper for the existing manual-token trade path.

    The implementation remains in server.py intentionally so its payload and
    websocket behavior stay byte-for-byte familiar to the legacy flow.
    """

