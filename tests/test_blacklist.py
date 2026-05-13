from core.blacklist import filter_phones, is_blacklisted


def test_jobkorea_self_number_blocked():
    """잡코리아 사이트 자체 대표번호 1588-9350은 회사 번호로 채택되면 안 된다."""
    assert is_blacklisted("1588-9350") is True
    assert is_blacklisted("15889350") is True
    assert is_blacklisted("1588 9350") is True


def test_saramin_self_number_blocked():
    assert is_blacklisted("1588-9759") is True


def test_normal_company_number_pass():
    """일반 회사 대표번호는 통과해야 한다."""
    assert is_blacklisted("02-6363-2600") is False  # 동원로엑스
    assert is_blacklisted("1588-7110") is False


def test_filter_phones_removes_blacklist_only():
    phones = ["02-1234-5678", "1588-9350", "031-555-1234", "1588-9759"]
    out = filter_phones(phones)
    assert "02-1234-5678" in out
    assert "031-555-1234" in out
    assert "1588-9350" not in out
    assert "1588-9759" not in out
