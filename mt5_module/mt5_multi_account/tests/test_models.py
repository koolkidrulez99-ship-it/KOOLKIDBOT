from mt5_multi_account.models import CopyRequest
def test_copy_request_defaults():
    x=CopyRequest(master_account_id="a", slave_account_ids=["b"])
    assert x.poll_ms==300 and x.lot_mode=="same"
