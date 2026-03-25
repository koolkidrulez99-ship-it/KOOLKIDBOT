from server import _parse_koolkid_half_auto_stakes


def test_parse_koolkid_half_auto_stakes_accepts_all_four_values():
    stakes, error = _parse_koolkid_half_auto_stakes(
        {
            "under1_stake": "1.10",
            "over2_stake": "1.20",
            "over8_stake": "1.30",
            "under7_stake": "1.40",
        },
        1.0,
    )

    assert error is None
    assert stakes == {
        "under1": 1.10,
        "over2": 1.20,
        "over8": 1.30,
        "under7": 1.40,
    }


def test_parse_koolkid_half_auto_stakes_rejects_below_minimum():
    stakes, error = _parse_koolkid_half_auto_stakes(
        {
            "under1_stake": "0.20",
            "over2_stake": "1.20",
            "over8_stake": "1.30",
            "under7_stake": "1.40",
        },
        1.0,
    )

    assert stakes is None
    assert error == "UNDER 1 stake must be at least $0.35"
