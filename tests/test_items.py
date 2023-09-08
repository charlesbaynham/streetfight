import pytest

@pytest.mark.xfail
def test_can_collect_item():
    raise NotImplementedError


@pytest.mark.xfail
def test_item_appears_in_database():
    raise NotImplementedError

@pytest.mark.xfail
def test_cannot_collect_invalid_item():
    raise NotImplementedError

@pytest.mark.xfail
def test_collecting_armour_when_alive():
    raise NotImplementedError

@pytest.mark.xfail
def test_collecting_armour_when_dead():
    raise NotImplementedError

@pytest.mark.xfail
def test_collecting_ammo():
    raise NotImplementedError



@pytest.mark.xfail
def test_collecting_revive():
    raise NotImplementedError

