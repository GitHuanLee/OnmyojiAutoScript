import json
from pathlib import Path
from types import SimpleNamespace
from concurrent.futures import ThreadPoolExecutor

from tasks.GlobalGame.config import GameAccount, GameAccountType
from tasks.JadeDetection.script_task import AccountEvoZoneTask, ScriptTask
from tasks.WantedQuests.config import CooperationType


def test_email_account_matching_accepts_ocr_prefix():
    account = GameAccount(account="mail@example.com", account_type=GameAccountType.EMAIL)
    assert ScriptTask._account_matches(account, "mail")


def test_phone_account_matching_accepts_masked_number():
    account = GameAccount(account="15355554444", account_type=GameAccountType.PHONE)
    assert ScriptTask._account_matches(account, "153****4444")


def test_phone_account_matching_rejects_wrong_suffix():
    account = GameAccount(account="15355554444", account_type=GameAccountType.PHONE)
    assert not ScriptTask._account_matches(account, "153****9999")


def test_shared_record_keeps_accounts_and_isolates_oas_instances(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    oas1 = ScriptTask.__new__(ScriptTask)
    oas1.config = SimpleNamespace(config_name="oas1")
    oas2 = ScriptTask.__new__(ScriptTask)
    oas2.config = SimpleNamespace(config_name="oas2")
    first = GameAccount(account="mail@example.com")
    second = GameAccount(account="other@example.com")

    oas1._write_cooperation_record(first, CooperationType.Jade, "普通勾协")
    oas2._write_cooperation_record(second, CooperationType.Jade, "现世勾协")

    record_path = Path("account/jade_detection.json")
    records = json.loads(record_path.read_text(encoding="utf-8"))
    assert records["oas1"][first.account]["jade_kind"] == "普通勾协"
    assert records["oas2"][second.account]["jade_kind"] == "现世勾协"


def test_new_run_clears_only_its_instance_records(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    oas1 = ScriptTask.__new__(ScriptTask)
    oas1.config = SimpleNamespace(config_name="oas1")
    oas2 = ScriptTask.__new__(ScriptTask)
    oas2.config = SimpleNamespace(config_name="oas2")
    oas1._write_cooperation_record(GameAccount(account="one"), CooperationType.Jade, "普通勾协")
    oas2._write_cooperation_record(GameAccount(account="two"), CooperationType.Jade, "现世勾协")

    oas1._clear_previous_cooperation_record()
    records = json.loads(Path("account/jade_detection.json").read_text(encoding="utf-8"))

    assert records["oas1"] == {}
    assert records["oas2"]["two"]["jade_kind"] == "现世勾协"


def test_concurrent_instance_updates_do_not_lose_records(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    def write_record(index):
        task = ScriptTask.__new__(ScriptTask)
        task.config = SimpleNamespace(config_name="oas1" if index % 2 else "oas2")
        task._write_cooperation_record(GameAccount(account=f"account-{index}"), CooperationType.Jade,
                                       "普通勾协")

    with ThreadPoolExecutor(max_workers=8) as executor:
        list(executor.map(write_record, range(24)))

    records = json.loads(Path("account/jade_detection.json").read_text(encoding="utf-8"))
    assert sum(len(instance_records) for instance_records in records.values()) == 24


def test_guild_30_friend_name_supports_wildcard_matching():
    matcher = AccountEvoZoneTask._matches_guild_30_friend_name

    assert matcher("上条当麻*号机", "上条当麻一号机")
    assert matcher("上条当麻*号机", "上条当麻二号机")
    assert not matcher("上条当麻*号机", "上条当麻")
    assert not matcher("上条当麻*号机", "最帅的人")


def test_guild_30_friend_name_without_wildcard_uses_contains_match():
    matcher = AccountEvoZoneTask._matches_guild_30_friend_name

    assert matcher("上条当麻", "上条当麻一号机")
    assert not matcher("上条当麻", "最帅的人")
