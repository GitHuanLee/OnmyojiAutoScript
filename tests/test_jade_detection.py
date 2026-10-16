from tasks.GlobalGame.config import GameAccount, GameAccountType
from tasks.JadeDetection.script_task import ScriptTask


def test_email_account_matching_accepts_ocr_prefix():
    account = GameAccount(account="mail@example.com", account_type=GameAccountType.EMAIL)
    assert ScriptTask._account_matches(account, "mail")


def test_phone_account_matching_accepts_masked_number():
    account = GameAccount(account="15355554444", account_type=GameAccountType.PHONE)
    assert ScriptTask._account_matches(account, "153****4444")


def test_phone_account_matching_rejects_wrong_suffix():
    account = GameAccount(account="15355554444", account_type=GameAccountType.PHONE)
    assert not ScriptTask._account_matches(account, "153****9999")
