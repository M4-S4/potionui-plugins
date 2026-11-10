import json
import re
import shutil
import urllib.parse

import numpy as np
import pytest
from PIL import Image

from potion_audit.cli import main
from potion_audit.client import ApiClient
from potion_audit.matrix import run_profile
from potion_audit.media import media_ssim, ssim, write_thumbnail
from potion_audit.pack import load_pack
from potion_audit.reevaluate import ReevaluateError, reevaluate_run
from potion_audit.report import ReportError, add_pack_cells, bias_factors, compare_sets, load_set, reduce_home, render_merge, write_report

from conftest import PASSWORD, USER
from packs import write_pack
from test_media import make_video


class FakeClock:
    def __init__(self):
        self.now = 0.0

    def __call__(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.now += seconds


def quiet(line: str) -> None:
    return None


def logged_in(fake_api) -> ApiClient:
    client = ApiClient(fake_api.url)
    client.login(USER, PASSWORD)
    return client


def play(fake_api, pack, out, run_id, **kwargs):
    clock = FakeClock()
    return run_profile(logged_in(fake_api), pack, kwargs.pop("profile", "smoke"), out, run_id, clock=clock, sleep=clock.sleep, log=quiet, **kwargs)


def read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def write(path, data):
    path.write_text(json.dumps(data, indent=1) + "\n", encoding="utf-8")


def test_a_run_records_its_mode_the_instance_and_the_host_probe(fake_api, tmp_path, case_file):
    probe = tmp_path / "probe.json"
    write(probe, {"probe": "windows", "gpu": {"driver": "999.1"}})
    pack = load_pack(write_pack(tmp_path, case_file))
    play(fake_api, pack, tmp_path / "out", "r1", machine="box", mode="dedicated", host_probe=probe)
    run_dir = tmp_path / "out" / "r1"
    assert read(run_dir / "run.json")["mode"] == "dedicated"
    assert read(run_dir / "instance.json")["gpu_profile"]["name"] == "Fake GPU"
    assert read(run_dir / "host-probe.json")["gpu"]["driver"] == "999.1"


def test_reevaluate_writes_a_new_verdict_beside_result_json_and_never_rewrites_it(fake_api, tmp_path, case_file):
    pack = load_pack(write_pack(tmp_path, case_file))
    play(fake_api, pack, tmp_path / "out", "r1", machine="box")
    folder = tmp_path / "out" / "r1" / "cells" / "core-SDXL--txt2img"
    result = read(folder / "result.json")
    result["verdict"] = "FAIL"
    result["checks_version"] = 1
    result["checks"].append({"check": "generation_step", "expected": "none of TXT2IMG", "actual": ["TXT2IMG"], "ok": False})
    write(folder / "result.json", result)
    before = (folder / "result.json").read_bytes()
    lines = []
    records = reevaluate_run(tmp_path / "out" / "r1", pack, lines.append)
    assert (folder / "result.json").read_bytes() == before
    record = read(folder / "result.reevaluated.json")
    assert (record["previous"]["verdict"], record["verdict"], record["changed"]) == ("FAIL", "PASS", True)
    assert record["previous"]["checks_version"] == 1
    assert record["checks_version"] == 2
    assert record["pack"]["same_as_run"] is True
    assert [check["check"] for check in record["checks"]] == ["min_outputs", "resolution", "not_black"]
    assert [item["changed"] for item in records] == [True]
    assert "core/SDXL:txt2img: FAIL -> PASS" in lines


def test_reevaluate_reads_the_outputs_again_from_the_run_folder(fake_api, tmp_path, case_file):
    pack = load_pack(write_pack(tmp_path, case_file))
    play(fake_api, pack, tmp_path / "out", "r1", machine="box")
    folder = tmp_path / "out" / "r1" / "cells" / "core-SDXL--txt2img"
    Image.new("RGB", (64, 64), (0, 0, 0)).save(folder / "0.png")
    reevaluate_run(tmp_path / "out" / "r1", pack, quiet)
    record = read(folder / "result.reevaluated.json")
    assert (record["previous"]["verdict"], record["verdict"]) == ("PASS", "FAIL")
    assert next(check for check in record["checks"] if check["check"] == "not_black")["ok"] is False


def test_reevaluate_keeps_the_verdict_of_a_generation_that_did_not_complete(fake_api, tmp_path, case_file):
    pack = load_pack(write_pack(tmp_path, case_file))
    fake_api.outcomes = [("failed", {"error_code": "cuda_oom", "message": "out of memory"})]
    play(fake_api, pack, tmp_path / "out", "r1", machine="box")
    reevaluate_run(tmp_path / "out" / "r1", pack, quiet)
    record = read(tmp_path / "out" / "r1" / "cells" / "core-SDXL--txt2img" / "result.reevaluated.json")
    assert (record["verdict"], record["changed"]) == ("OOM", False)
    assert "did not complete" in record["kept"]


def test_reevaluate_refuses_a_run_of_another_pack(fake_api, tmp_path, case_file):
    pack = load_pack(write_pack(tmp_path, case_file))
    play(fake_api, pack, tmp_path / "out", "r1", machine="box")
    run = read(tmp_path / "out" / "r1" / "run.json")
    run["pack"]["id"] = "another-pack"
    write(tmp_path / "out" / "r1" / "run.json", run)
    with pytest.raises(ReevaluateError):
        reevaluate_run(tmp_path / "out" / "r1", pack, quiet)


def test_the_segments_of_one_run_become_one_matrix_with_the_reasons_of_the_cells_not_run(fake_api, tmp_path, case_file):
    pack = load_pack(write_pack(tmp_path, case_file))
    fake_api.outcomes = [("failed", {"error_code": "cuda_oom", "message": "out of memory"})]
    play(fake_api, pack, tmp_path / "out", "seg-1", profile="full", beyond_tier=True, machine="box", mode="shared")
    play(fake_api, pack, tmp_path / "out", "seg-2", profile="full", only="core/Wan", machine="box", mode="shared")
    run_set = load_set([tmp_path / "out" / "seg-1", tmp_path / "out" / "seg-2"])
    assert add_pack_cells(run_set, pack) == 1
    rows = {entry.key: (entry.status, entry.shown_verdict) for entry in run_set.entries}
    assert rows["core/SDXL:txt2img"] == ("ready", "OOM")
    assert rows["core/SDXL:txt2img/edit"][0] == "not_run"
    assert rows["core/Wan:video"] == ("beyond_tier", None)
    assert rows["core/ModelTools:*"] == ("excluded", None)
    index = write_report(run_set, tmp_path / "report", log=quiet)
    page = index.read_text(encoding="utf-8")
    assert "writes into the model store" in page
    assert "the min_vram_gb" in page or "beyond_tier" in page
    assert any("segment seg-1" in item for item in bias_factors(run_set))
    assert any(item.startswith("shared instance") for item in bias_factors(run_set))
    assert 'name="viewport"' in page and "prefers-color-scheme: dark" in page
    assert "http://" not in page and "https://" not in page
    report = read(tmp_path / "report" / "report.json")
    assert report["runs"] == ["seg-1", "seg-2"]


def test_reevaluate_derives_the_peak_again_from_the_recorded_preset_statistics(fake_api, tmp_path, case_file):
    pack = load_pack(write_pack(tmp_path, case_file))
    play(fake_api, pack, tmp_path / "out", "r1", machine="box")
    folder = tmp_path / "out" / "r1" / "cells" / "core-SDXL--txt2img"
    result = read(folder / "result.json")
    assert result["generation_stats"]["preset_stats"]["after"]["peak_vram_mb"] == 7400.0
    result["generation_stats"]["peak_vram_mb"] = 9999.0
    write(folder / "result.json", result)
    lines = []
    reevaluate_run(tmp_path / "out" / "r1", pack, lines.append)
    stats = read(folder / "result.reevaluated.json")["generation_stats"]
    assert (stats["previous_peak_vram_mb"], stats["peak_vram_mb"]) == (9999.0, 7400.0)
    assert any("peak VRAM 9999.0 -> 7400.0 MiB" in line for line in lines)
    run_set = load_set([tmp_path / "out" / "r1"])
    assert run_set.entries[0].peak_vram_mb == 7400.0


def test_reevaluate_says_why_a_run_without_recorded_statistics_keeps_its_peak(fake_api, tmp_path, case_file):
    pack = load_pack(write_pack(tmp_path, case_file))
    play(fake_api, pack, tmp_path / "out", "r1", machine="box")
    folder = tmp_path / "out" / "r1" / "cells" / "core-SDXL--txt2img"
    result = read(folder / "result.json")
    del result["generation_stats"]["preset_stats"]
    result["generation_stats"]["peak_vram_mb"] = 9999.0
    write(folder / "result.json", result)
    reevaluate_run(tmp_path / "out" / "r1", pack, quiet)
    stats = read(folder / "result.reevaluated.json")["generation_stats"]
    assert stats["peak_vram_mb"] == 9999.0
    assert "did not record the preset statistics" in stats["kept"]
    assert load_set([tmp_path / "out" / "r1"]).entries[0].peak_vram_mb == 9999.0


def test_the_report_says_why_a_peak_is_not_derivable(fake_api, tmp_path, case_file):
    pack = load_pack(write_pack(tmp_path, case_file))
    fake_api.stats_after["resources"].update(avg_vram_mb=9000.0)
    play(fake_api, pack, tmp_path / "out", "r1", machine="box")
    run_set = load_set([tmp_path / "out" / "r1"])
    assert run_set.entries[0].peak_vram_mb is None
    page = write_report(run_set, tmp_path / "report", log=quiet).read_text(encoding="utf-8")
    assert "Peak VRAM (core record of the generation)" in page
    assert "not derivable: the preset&#x27;s maximum rose to 7400.0 MiB" in page


def test_the_report_shows_the_reevaluated_verdict_and_the_old_one_beside_it(fake_api, tmp_path, case_file):
    pack = load_pack(write_pack(tmp_path, case_file))
    play(fake_api, pack, tmp_path / "out", "r1", machine="box")
    folder = tmp_path / "out" / "r1" / "cells" / "core-SDXL--txt2img"
    result = read(folder / "result.json")
    result["verdict"] = "FAIL"
    write(folder / "result.json", result)
    reevaluate_run(tmp_path / "out" / "r1", pack, quiet)
    run_set = load_set([tmp_path / "out" / "r1"])
    entry = run_set.entries[0]
    assert (entry.shown_verdict, entry.previous_verdict) == ("PASS", "FAIL")
    page = write_report(run_set, tmp_path / "report", log=quiet).read_text(encoding="utf-8")
    assert '<span class="was">FAIL</span>' in page
    assert "checks version 2" in page


def links(page: str) -> list[str]:
    return re.findall(r'(?:href|src|poster)="([^"]*)"', page)


def assert_self_contained(page: str, out) -> None:
    for link in links(page):
        if link.startswith("#"):
            continue
        assert ":" not in link and not link.startswith(("/", "..")) and "/../" not in link, link
        assert (out / urllib.parse.unquote(link)).is_file(), link


def test_the_report_makes_a_thumbnail_and_a_reduced_copy_and_names_the_original_without_linking_out_of_its_folder(fake_api, tmp_path, case_file):
    clip = make_video(tmp_path / "clip.mp4", size=(192, 128))
    fake_api.outputs = {"1.mp4": clip.read_bytes()}
    pack = load_pack(write_pack(tmp_path, case_file))
    play(fake_api, pack, tmp_path / "out", "r1", machine="box")
    folder = tmp_path / "out" / "r1" / "cells" / "core-SDXL--txt2img"
    assert sorted(path.name for path in folder.iterdir()) == ["1.mp4", "request.json", "result.json", "run_report.json"]
    run_set = load_set([tmp_path / "out" / "r1"])
    page = write_report(run_set, tmp_path / "report", log=quiet).read_text(encoding="utf-8")
    media = tmp_path / "report" / "media" / "c-core_SDXL_txt2img"
    assert (media / "1.mp4").is_file() and (media / "1.thumb.jpg").is_file()
    assert 'src="media/c-core_SDXL_txt2img/1.mp4"' in page
    assert "original 1.mp4, kept in the run folder r1/cells/core-SDXL--txt2img" in page
    assert "../out/r1" not in page
    assert_self_contained(page, tmp_path / "report")


def test_a_shared_report_folder_holds_every_file_its_page_points_to(fake_api, tmp_path, case_file):
    fake_api.outputs = {"1.wav": b"RIFF" + bytes(64), "2.glb": b"glTF" + bytes(64)}
    pack = load_pack(write_pack(tmp_path, case_file))
    play(fake_api, pack, tmp_path / "out", "r1", machine="box")
    run = read(tmp_path / "out" / "r1" / "run.json")
    run["runner"] = {"potion_audit": "0.0.1", "python": "3.13", "executable": "\\".join(["C:", "Users", "someone", "audit", ".venv", "python.exe"])}
    write(tmp_path / "out" / "r1" / "run.json", run)
    page = write_report(load_set([tmp_path / "out" / "r1"]), tmp_path / "shared", log=quiet).read_text(encoding="utf-8")
    assert '<audio controls preload="none" src="media/c-core_SDXL_txt2img/1.wav">' in page
    assert 'href="media/c-core_SDXL_txt2img/2.glb"' in page
    assert "python.exe" not in page and "&lt;home&gt;" not in page
    assert_self_contained(page, tmp_path / "shared")
    moved = tmp_path / "elsewhere" / "shared"
    shutil.copytree(tmp_path / "shared", moved)
    shutil.rmtree(tmp_path / "out")
    assert_self_contained((moved / "index.html").read_text(encoding="utf-8"), moved)


def test_storage_says_not_probed_without_a_probe_and_lists_the_mounts_with_one(fake_api, tmp_path, case_file):
    pack = load_pack(write_pack(tmp_path, case_file))
    play(fake_api, pack, tmp_path / "out", "r1", machine="box")
    page = write_report(load_set([tmp_path / "out" / "r1"]), tmp_path / "a", media=False).read_text(encoding="utf-8")
    assert "Not probed" in page
    probe = tmp_path / "container-probe.json"
    write(probe, {"probe": "linux", "kernel": "6.1", "generated_at": "now", "paths": [{"path": "/work/models", "fs_type": "ext2/ext3", "total_bytes": 1000, "free_bytes": 400, "findmnt": {"filesystems": [{"source": "/dev/sdd[/volumes/models]", "fstype": "ext4"}]}}], "read_test": {"mib_per_second": 2500.0, "read_bytes": 2 ** 30, "direct_io": True}})
    page = write_report(load_set([tmp_path / "out" / "r1"], probes=[probe]), tmp_path / "b", media=False).read_text(encoding="utf-8")
    assert "Not probed" not in page
    assert "/dev/sdd[/volumes/models]" in page and "2500.0 MiB/s" in page


def test_compare_flags_a_changed_verdict_a_slower_cell_and_scores_same_seed_outputs(fake_api, tmp_path, case_file):
    pack = load_pack(write_pack(tmp_path, case_file))
    play(fake_api, pack, tmp_path / "out", "old", machine="box")
    play(fake_api, pack, tmp_path / "out", "new", machine="box")
    folder = tmp_path / "out" / "new" / "cells" / "core-SDXL--txt2img"
    result = read(folder / "result.json")
    result["timing"]["run_seconds"] = 18
    write(folder / "result.json", result)
    run = read(tmp_path / "out" / "new" / "run.json")
    run["cells"][0]["verdict"] = "FAIL"
    write(tmp_path / "out" / "new" / "run.json", run)
    comparison = compare_sets(load_set([tmp_path / "out" / "new"]), load_set([tmp_path / "out" / "old"]))
    row = comparison["rows"][0]
    assert (row["previous_verdict"], row["verdict"], row["verdict_changed"]) == ("PASS", "FAIL", True)
    assert row["duration_change"] == 0.5 and row["duration_flag"] is True
    assert row["ssim"] == {"value": 1.0, "reason": None}
    assert comparison["storage_probed"] is False
    assert comparison["only_in_this_run"] == [] and comparison["only_in_previous"] == []


def test_compare_lists_cells_missing_on_one_side_apart_from_the_changed_verdicts(fake_api, tmp_path, case_file):
    pack = load_pack(write_pack(tmp_path, case_file))
    play(fake_api, pack, tmp_path / "out", "old", machine="box", only="core/SDXL:txt2img")
    play(fake_api, pack, tmp_path / "out", "new", machine="box", beyond_tier=True)
    comparison = compare_sets(load_set([tmp_path / "out" / "new"]), load_set([tmp_path / "out" / "old"]))
    assert [row["cell"] for row in comparison["rows"]] == ["core/SDXL:txt2img"]
    assert comparison["rows"][0]["verdict_changed"] is False
    assert comparison["only_in_this_run"] == ["core/Wan:video"]


def test_compare_refuses_two_runs_of_different_packs(fake_api, tmp_path, case_file, capsys):
    pack = load_pack(write_pack(tmp_path, case_file))
    play(fake_api, pack, tmp_path / "out", "old", machine="box")
    play(fake_api, pack, tmp_path / "out", "new", machine="box")
    run = read(tmp_path / "out" / "old" / "run.json")
    run["pack"]["sha256"] = "0" * 64
    write(tmp_path / "out" / "old" / "run.json", run)
    with pytest.raises(ReportError):
        compare_sets(load_set([tmp_path / "out" / "new"]), load_set([tmp_path / "out" / "old"]))
    code = main(["report", str(tmp_path / "out" / "new"), "--compare", str(tmp_path / "out" / "old"), "--no-media", "--pack", str(tmp_path / "pack" / "pack.toml")])
    assert code == 2
    assert "same pack" in capsys.readouterr().err


def test_segments_from_two_machines_are_refused_by_report_and_merged_by_merge(fake_api, tmp_path, case_file):
    pack = load_pack(write_pack(tmp_path, case_file))
    play(fake_api, pack, tmp_path / "out", "a-1", machine="alpha")
    play(fake_api, pack, tmp_path / "out", "a-2", machine="alpha")
    play(fake_api, pack, tmp_path / "out", "b-1", machine="beta")
    with pytest.raises(ReportError):
        load_set([tmp_path / "out" / "a-1", tmp_path / "out" / "b-1"])
    code = main(["merge", str(tmp_path / "out" / "a-1"), str(tmp_path / "out" / "a-2"), str(tmp_path / "out" / "b-1"), "--out", str(tmp_path / "merged")])
    assert code == 0
    page = (tmp_path / "merged" / "index.html").read_text(encoding="utf-8")
    assert "<th>alpha</th><th>beta</th>" in page
    assert "a-1, a-2" in page


def test_merge_refuses_runs_of_different_packs(fake_api, tmp_path, case_file):
    pack = load_pack(write_pack(tmp_path, case_file))
    play(fake_api, pack, tmp_path / "out", "a-1", machine="alpha")
    play(fake_api, pack, tmp_path / "out", "b-1", machine="beta")
    run = read(tmp_path / "out" / "b-1" / "run.json")
    run["pack"]["sha256"] = "1" * 64
    write(tmp_path / "out" / "b-1" / "run.json", run)
    with pytest.raises(ReportError):
        render_merge([load_set([tmp_path / "out" / "a-1"]), load_set([tmp_path / "out" / "b-1"])])


def test_home_folders_are_hidden_in_the_report():
    windows = "\\".join(["C:", "Users", "someone", "audit", "python.exe"])
    linux = "/".join(["", "home", "someone", "audit", "python"])
    assert reduce_home(windows) == "<home>\\audit\\python.exe"
    assert reduce_home(linux) == "<home>/audit/python"


def test_ssim_is_one_for_the_same_picture_and_lower_for_noise():
    rng = np.random.default_rng(0)
    picture = rng.integers(0, 255, (48, 64)).astype(np.float64)
    noisy = np.clip(picture + rng.normal(0, 40, picture.shape), 0, 255)
    assert ssim(picture, picture) == pytest.approx(1.0)
    assert ssim(picture, noisy) < 0.95
    with pytest.raises(ValueError):
        ssim(picture, picture[:10])


def test_ssim_of_two_videos_samples_frames_and_a_thumbnail_comes_from_the_middle(tmp_path):
    first = make_video(tmp_path / "a.mp4")
    second = make_video(tmp_path / "b.mp4", value=40)
    assert media_ssim(first, first, "video") == pytest.approx(1.0)
    assert media_ssim(first, second, "video") < 0.99
    thumb = write_thumbnail(first, tmp_path / "t" / "a.jpg", "video", side=48)
    assert (thumb["width"], thumb["height"]) == (48, 32)
