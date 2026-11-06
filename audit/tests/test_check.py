import json

from potion_audit.cli import main

from conftest import MISSING_SHA, PASSWORD, TOKEN


def run_check(config_file, tmp_path):
    out = tmp_path / "preflight"
    code = main(["check", "--config", str(config_file), "--out", str(out)])
    return code, json.loads((out / "preflight.json").read_text(encoding="utf-8")), (out / "preflight.html").read_text(encoding="utf-8")


def test_check_writes_a_json_and_an_english_html_page(fake_api, config_file, credentials_env, tmp_path):
    code, preflight, html = run_check(config_file, tmp_path)
    assert code == 0
    assert preflight["blocking"] == []
    assert preflight["instance"]["app_version"] == "9.9.9"
    assert preflight["hardware"]["gpu_profile"]["name"] == "Fake GPU"
    assert preflight["queue"] == {"pending": 0, "running": 0}
    assert "<title>Potion audit preflight</title>" in html
    assert "Missing models" in html


def test_check_sends_only_gets_after_the_login(fake_api, config_file, credentials_env, tmp_path):
    run_check(config_file, tmp_path)
    methods = [method for method, _ in fake_api.methods()]
    assert methods[0] == "POST"
    assert fake_api.methods()[0][1] == "/api/auth/login"
    assert set(methods[1:]) == {"GET"}


def test_a_busy_global_queue_blocks_with_exit_code_2(fake_api, config_file, credentials_env, tmp_path):
    fake_api.queue = {"pending": [{"id": "x"}], "running": []}
    code, preflight, _ = run_check(config_file, tmp_path)
    assert code == 2
    assert preflight["blocking"] == ["queue_busy: 0 running, 1 pending"]


def test_a_failed_login_blocks_and_writes_the_reason(fake_api, config_file, monkeypatch, tmp_path):
    monkeypatch.setenv("POTION_AUDIT_USER", "auditor")
    monkeypatch.setenv("POTION_AUDIT_PASSWORD", "wrong")
    code, preflight, _ = run_check(config_file, tmp_path)
    assert code == 2
    assert preflight["blocking"] == ["login_failed: HTTP 401"]


def test_a_missing_model_is_listed_with_the_recipe_size(fake_api, config_file, credentials_env, tmp_path):
    _, preflight, _ = run_check(config_file, tmp_path)
    missing = [model for model in preflight["models"] if model["present"] is False]
    assert [model["sha256"] for model in missing] == [MISSING_SHA]
    assert missing[0]["expected_size_bytes"] == 7000
    wan = next(case for case in preflight["cases"] if case["name"] == "wan-t2v")
    assert wan["verdict"] == "model_missing"
    assert wan["missing_bytes"] == 7000
    assert preflight["summary"]["missing_bytes"] == 7000


def test_presets_report_version_assignment_and_vram_tier(fake_api, config_file, credentials_env, tmp_path):
    _, preflight, _ = run_check(config_file, tmp_path)
    by_key = {preset["key"]: preset for preset in preflight["presets"]}
    assert by_key["SDXL"]["version_match"] is True
    assert by_key["SDXL"]["assigned_to_me"] is True
    assert by_key["SDXL"]["tier"] == "within"
    assert by_key["Wan"]["assigned_to_me"] is False
    assert by_key["Wan"]["tier"] == "beyond"
    assert by_key["ModelTools"]["installed"] is False
    sdxl = [case for case in preflight["cases"] if case["preset_key"] == "SDXL"]
    assert {case["verdict"] for case in sdxl} == {"ready"}


def test_only_the_listed_settings_are_copied(fake_api, config_file, credentials_env, tmp_path):
    _, preflight, html = run_check(config_file, tmp_path)
    assert "s3_secret_key" not in preflight["instance"]["settings"]
    assert "should-not-be-copied" not in json.dumps(preflight)
    assert "should-not-be-copied" not in html


def test_low_disk_space_is_a_warning_not_a_block(fake_api, config_file, credentials_env, tmp_path):
    fake_api.disk_free = 50
    code, preflight, _ = run_check(config_file, tmp_path)
    assert code == 0
    assert preflight["warnings"] == ["low_disk: native:models has 5.0 % free"]


def test_no_credential_or_token_reaches_the_preflight_files(fake_api, config_file, credentials_env, tmp_path):
    _, preflight, html = run_check(config_file, tmp_path)
    text = json.dumps(preflight) + html
    assert PASSWORD not in text
    assert TOKEN not in text


def test_missing_credentials_stop_before_any_request(fake_api, config_file, monkeypatch, tmp_path, capsys):
    monkeypatch.delenv("POTION_AUDIT_USER", raising=False)
    monkeypatch.delenv("POTION_AUDIT_PASSWORD", raising=False)
    code = main(["check", "--config", str(config_file), "--out", str(tmp_path / "p")])
    assert code == 2
    assert fake_api.requests == []
    assert "POTION_AUDIT_USER" in capsys.readouterr().err
