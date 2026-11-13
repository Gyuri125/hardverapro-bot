from dealradar.models import Specs


def tier(*gpus: str) -> int:
    return Specs(gpus=list(gpus)).gpu_tier


def test_gpu_tier_generations():
    assert tier("rtx 5090") == 5
    assert tier("rtx 5080") == 5
    assert tier("rtx 5070") == 4
    assert tier("rtx 5060") == 3
    assert tier("rtx 5050") == 3
    assert tier("rtx 4090") == 5
    assert tier("rtx 4070") == 4
    assert tier("rtx 4060") == 3
    assert tier("rtx 4050") == 2
    assert tier("rtx 3080") == 4
    assert tier("rtx 3070") == 3
    assert tier("rtx 3060") == 2
    assert tier("rtx 3050") == 1
    assert tier("gtx 1660") == 1
    assert tier("gtx 1050") == 0


def test_gpu_tier_amd_and_arc():
    assert tier("rx 7900") == 5
    assert tier("rx 7800") == 4
    assert tier("rx 7600") == 3
    assert tier("rx 6600") == 2
    assert tier("arc a770") == 2


def test_gpu_tier_takes_best():
    assert tier("rtx 3050", "rtx 4070") == 4
    assert tier() == 0


def test_gpu_tier_is_not_numeric_order():
    """Az 5050 nem lehet jobb, mint egy 4070 – generáció + kategória számít."""
    assert tier("rtx 5050") < tier("rtx 4070")
