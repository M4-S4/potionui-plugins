import dataclasses
import json

import pytest

from potion_audit.cli import main
from potion_audit.client import ApiClient
from potion_audit.matrix import run_profile
from potion_audit.pack import DEFAULT_PACK, PackError, beyond_tier_default, load_pack, resolve_beyond_tier

from conftest import PASSWORD, USER
from packs import write_pack

LAST = {"[bible]": '[profiles.full]\nbeyond_tier = "last"\n\n[bible]'}


class FakeClock:
    def __init__(self):
        self.now = 0.0

    def __call__(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.now += seconds


def logged_in(fake_api) -> ApiClient:
    client = ApiClient(fake_api.url)
    client.login(USER, PASSWORD)
    return client


def quiet(line: str) -> None:
    return None


def wan_first(pack):
    cells = []
    for cell in pack.cells:
        position = -1 if cell.preset_ref == "core/Wan" else cell.position
        cells.append(dataclasses.replace(cell, position=position))
    return dataclasses.replace(pack, cells=tuple(cells))


def test_the_shipped_pack_plays_the_cells_beyond_the_tier_last_in_full_only():
    pack = load_pack(DEFAULT_PACK)
    assert pack.profile_settings == {"full": {"beyond_tier": "last"}}
    assert beyond_tier_default(pack, "full")
    assert not beyond_tier_default(pack, "smoke")
    assert resolve_beyond_tier(pack, "full", False) is False
    assert resolve_beyond_tier(pack, "smoke", True) is True


@pytest.mark.parametrize(
    "section, message",
    [
        ('[profiles.night]\nbeyond_tier = "last"\n', "unknown profile"),
        ('[profiles.full]\nbeyond_tier = "first"\n', "expected one of skip, last"),
        ('[profiles.full]\nlast = true\n', "unknown keys: last"),
    ],
)
def test_a_profile_setting_the_tool_does_not_know_is_refused(tmp_path, case_file, section, message):
    path = write_pack(tmp_path, case_file, replace={"[bible]": section + "\n[bible]"})
    with pytest.raises(PackError, match=message):
        load_pack(path)


def test_a_full_run_plays_the_cells_beyond_the_tier_after_all_the_others_by_default(fake_api, tmp_path, case_file):
    path = write_pack(tmp_path, case_file, replace=LAST)
    assert main(["pack", "make-inputs", "--pack", str(path), "--transforms-only", "--config", str(tmp_path / "none.toml")]) == 0
    pack = wan_first(load_pack(path))
    clock = FakeClock()
    run = run_profile(logged_in(fake_api), pack, "full", tmp_path / "out", "beyond-1", clock=clock, sleep=clock.sleep, log=quiet)
    rows = [(entry["order"], entry["cell"], entry["warm_repeat"], entry["status"], entry.get("beyond_tier", False), entry["verdict"]) for entry in run["cells"]]
    assert rows == [
        (1, "core/SDXL:txt2img", False, "ready", False, "PASS"),
        (2, "core/SDXL:txt2img/edit", False, "ready", False, "PASS"),
        (3, "core/Wan:video", False, "ready_beyond_tier", True, "PASS"),
        (4, "core/Wan:video", True, "ready_beyond_tier", True, "PASS"),
    ]
    assert run["beyond_tier"] == "last"
    assert run["summary"]["beyond_tier_verdicts"] == {"PASS": 2}


def test_a_full_run_skips_the_cells_beyond_the_tier_when_told_to(fake_api, tmp_path, case_file):
    pack = wan_first(load_pack(write_pack(tmp_path, case_file, replace=LAST)))
    clock = FakeClock()
    run = run_profile(logged_in(fake_api), pack, "full", tmp_path / "out", "beyond-2", beyond_tier=False, clock=clock, sleep=clock.sleep, log=quiet)
    rows = [(entry["cell"], entry["warm_repeat"], entry["status"]) for entry in run["cells"]]
    assert rows[:2] == [("core/Wan:video", False, "beyond_tier"), ("core/Wan:video", True, "beyond_tier")]
    assert run["beyond_tier"] == "skip"
    assert run["summary"]["beyond_tier_verdicts"] == {}


def test_an_oom_beyond_the_tier_leaves_only_the_cells_after_it_not_run(fake_api, tmp_path, case_file):
    path = write_pack(tmp_path, case_file, replace=LAST)
    assert main(["pack", "make-inputs", "--pack", str(path), "--transforms-only", "--config", str(tmp_path / "none.toml")]) == 0
    pack = wan_first(load_pack(path))
    fake_api.outcomes = [("completed", None), ("completed", None), ("failed", {"error_code": "cuda_oom", "message": "out of memory"})]
    clock = FakeClock()
    run = run_profile(logged_in(fake_api), pack, "full", tmp_path / "out", "beyond-3", clock=clock, sleep=clock.sleep, log=quiet)
    rows = [(entry["cell"], entry["warm_repeat"], entry["status"], entry["verdict"]) for entry in run["cells"]]
    assert rows[2:] == [("core/Wan:video", False, "ready_beyond_tier", "OOM"), ("core/Wan:video", True, "not_run", None)]
    assert [row[3] for row in rows[:2]] == ["PASS", "PASS"]
    assert "OOM" in run["stopped"]
    assert run["summary"]["beyond_tier_verdicts"] == {"OOM": 1}


def test_a_smoke_run_keeps_skipping_the_cells_beyond_the_tier(fake_api, tmp_path, case_file):
    pack = load_pack(write_pack(tmp_path, case_file, replace=LAST))
    clock = FakeClock()
    run = run_profile(logged_in(fake_api), pack, "smoke", tmp_path / "out", "beyond-4", clock=clock, sleep=clock.sleep, log=quiet)
    assert [(entry["cell"], entry["status"]) for entry in run["cells"]] == [("core/SDXL:txt2img", "ready"), ("core/Wan:video", "beyond_tier")]


def test_a_dry_run_of_full_lists_the_cells_beyond_the_tier_last_and_counts_them(fake_api, config_file, credentials_env, tmp_path, case_file):
    path = write_pack(tmp_path, case_file, replace=LAST)
    assert main(["run", "--config", str(config_file), "--pack", str(path), "--profile", "full", "--dry-run", "--run-id", "plan-beyond"]) == 0
    plan = json.loads((tmp_path / "out" / "plan-beyond" / "plan.json").read_text(encoding="utf-8"))
    assert plan["beyond_tier"] == "last"
    assert [entry["status"] for entry in plan["cells"]][-2:] == ["ready_beyond_tier", "ready_beyond_tier"]
    assert plan["summary"]["beyond_tier_planned"] == 2
    assert main(["run", "--config", str(config_file), "--pack", str(path), "--profile", "full", "--dry-run", "--run-id", "plan-within", "--no-beyond-tier"]) == 0
    plan = json.loads((tmp_path / "out" / "plan-within" / "plan.json").read_text(encoding="utf-8"))
    assert plan["beyond_tier"] == "skip"
    assert plan["summary"]["beyond_tier_planned"] == 0
