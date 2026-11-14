from pathlib import Path

import pytest

from potion_audit.config import DEFAULT_CASES, ConfigError, credentials, load_config


def write(path: Path, text: str) -> Path:
    path.write_text(text, encoding="utf-8")
    return path


def test_relative_paths_resolve_against_the_config_folder(tmp_path):
    config = load_config(write(tmp_path / "audit.toml", '[target]\nurl = "http://127.0.0.1:8000/"\n\n[run]\noutput_dir = "runs"\ncases = "cases/x.json"\n'))
    assert config.target.url == "http://127.0.0.1:8000"
    assert config.target.mode == "shared"
    assert config.output_dir == (tmp_path / "runs").resolve()
    assert config.cases_file == (tmp_path / "cases" / "x.json").resolve()
    assert config.probe_source == "none"


def test_the_packaged_case_file_is_the_default():
    assert DEFAULT_CASES.name == "54c51e21d.json"
    assert DEFAULT_CASES.exists()


def test_an_unknown_mode_is_refused(tmp_path):
    with pytest.raises(ConfigError, match="mode"):
        load_config(write(tmp_path / "audit.toml", '[target]\nurl = "http://127.0.0.1:8000"\nmode = "production"\n\n[run]\noutput_dir = "out"\n'))


def test_a_url_without_scheme_is_refused(tmp_path):
    with pytest.raises(ConfigError, match="url"):
        load_config(write(tmp_path / "audit.toml", '[target]\nurl = "127.0.0.1:8000"\n\n[run]\noutput_dir = "out"\n'))


def test_a_probe_file_source_needs_a_file(tmp_path):
    with pytest.raises(ConfigError, match="file"):
        load_config(write(tmp_path / "audit.toml", '[target]\nurl = "http://127.0.0.1:8000"\n\n[run]\noutput_dir = "out"\n\n[probe]\nsource = "file"\n'))


def test_a_missing_config_says_to_copy_the_example(tmp_path):
    with pytest.raises(ConfigError, match="audit.example.toml"):
        load_config(tmp_path / "audit.toml")


def test_credentials_come_from_the_named_variables(tmp_path):
    config = load_config(write(tmp_path / "audit.toml", '[target]\nurl = "http://127.0.0.1:8000"\nuser_env = "A_USER"\npassword_env = "A_PASS"\n\n[run]\noutput_dir = "out"\n'))
    assert credentials(config.target, {"A_USER": "u", "A_PASS": "p"}) == ("u", "p")


def test_missing_credentials_name_the_variables_and_no_value(tmp_path):
    config = load_config(write(tmp_path / "audit.toml", '[target]\nurl = "http://127.0.0.1:8000"\n\n[run]\noutput_dir = "out"\n'))
    with pytest.raises(ConfigError) as caught:
        credentials(config.target, {"POTION_AUDIT_USER": "someone"})
    assert "POTION_AUDIT_PASSWORD" in str(caught.value)
    assert "someone" not in str(caught.value)
