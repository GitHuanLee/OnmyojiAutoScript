import pytest
from pydantic import ValidationError

from tasks.GlobalGame.config import GameAccountSettings, GlobalGame


def test_game_accounts_support_multiple_platforms_and_passwords():
    """账号列表应保留每个账号的密码和独立平台选项。"""
    settings = GameAccountSettings()
    settings.accounts = [
        {"account": "ios-user", "password": "ios-secret", "platform": "IOS"},
        {"account": "android-user", "password": "android-secret", "platform": "Android"},
    ]

    assert settings.model_dump(mode="json")["accounts"] == [
        {"account": "ios-user", "password": "ios-secret", "platform": "IOS"},
        {"account": "android-user", "password": "android-secret", "platform": "Android"},
    ]


def test_game_account_platform_rejects_unsupported_values():
    """平台字段只接受 IOS 或 Android，避免保存无法识别的平台名称。"""
    with pytest.raises(ValidationError):
        GameAccountSettings(accounts=[{"platform": "Andraid"}])


def test_global_game_schema_exposes_account_list_for_gui():
    """全局游戏设置 schema 应将账号列表声明为数组供配置界面渲染。"""
    schema = GlobalGame.model_json_schema()
    account_settings_ref = schema["properties"]["account_settings"]["$ref"].rsplit("/", 1)[-1]
    account_settings = schema["$defs"][account_settings_ref]

    assert account_settings["properties"]["accounts"]["type"] == "array"
    assert account_settings["properties"]["accounts"]["items"]["$ref"].endswith("/GameAccount")
