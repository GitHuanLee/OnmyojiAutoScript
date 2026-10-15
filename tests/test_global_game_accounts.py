import json

import pytest

from tasks.GlobalGame.config import GameAccountSettings


def test_game_accounts_are_loaded_from_external_file(tmp_path):
    """账号密码应从独立文件读取，主配置只保留文件地址。"""
    account_file = tmp_path / 'accounts.json'
    account_file.write_text(json.dumps({'accounts': [
        {'account': 'ios-user', 'password': 'ios-secret', 'platform': 'IOS'},
        {'account': 'android-user', 'password': 'android-secret', 'platform': 'Android'},
    ]}), encoding='utf-8')
    accounts = GameAccountSettings(account_file=str(account_file)).load_accounts()
    assert [account.platform.value for account in accounts] == ['IOS', 'Android']
    assert accounts[0].password == 'ios-secret'


def test_game_accounts_reject_invalid_platform(tmp_path):
    """外部文件中的平台值必须限制为 IOS 或 Android。"""
    account_file = tmp_path / 'accounts.json'
    account_file.write_text(json.dumps({'accounts': [{'platform': 'Andraid'}]}), encoding='utf-8')
    with pytest.raises(ValueError, match='Invalid account file'):
        GameAccountSettings(account_file=str(account_file)).load_accounts()
