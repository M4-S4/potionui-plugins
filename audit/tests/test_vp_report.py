import json

import pytest

from potion_audit.cli import main
from potion_audit.pack import DEFAULT_PACK, load_pack
from potion_audit.report import ReportError, load_set, write_report
from potion_audit.vp_report import compare_scenarios, load_scenario, split_dirs
from potion_audit.vp_scenario import run_scenario, select_engines

from packs import write_pack
from test_report import play
from test_vp_scenario import logged_in, no_sleep, quiet, vp_api

H3 = "MiniMax-H3-12GB"
WAN = "Wan2.1-T2V-1.3B-8GB"


def read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def write(path, data):
    path.write_text(json.dumps(data, indent=1) + "\n", encoding="utf-8")


def scenario_run(api, out, run_id, names, machine="box"):
    pack = load_pack(DEFAULT_PACK)
    engines = select_engines(pack, None, names)
    run_scenario(logged_in(api), pack, out, run_id, engines, None, upscaler="rtx", interval=0.01, sleep=no_sleep, log=quiet, machine=machine)
    return out / run_id


def matrix_run(api, tmp_path, case_file, run_id, machine="box"):
    pack = load_pack(write_pack(tmp_path, case_file))
    play(api, pack, tmp_path / "out", run_id, machine=machine)
    return tmp_path / "out" / run_id


def test_a_scenario_alone_gives_a_row_per_engine_a_column_per_step_and_a_player_per_export(vp_api, tmp_path):
    vp_api.blocked_shots = {"s2-bottle"}
    run_dir = scenario_run(vp_api, tmp_path / "out", "vp-a", [WAN, H3])
    code = main(["report", str(run_dir), "--out", str(tmp_path / "report"), "--note", "a test note"])
    assert code == 0
    page = (tmp_path / "report" / "index.html").read_text(encoding="utf-8")
    assert '<h2 id="vp">Video Producer scenario</h2>' in page and "<h2>Matrix</h2>" not in page
    assert "<th>Shot 1</th><th>Shot 2 chained</th><th>Shot 3 Ref2VA</th><th>Final pass</th><th>Export</th>" in page
    assert page.count('<a class="cell off" href="#vp-Wan2.1-T2V-1.3B-8GB--Shot_3_Ref2VA"') == 1
    assert ">not offered<" in page and "has no refs mode" in page
    assert ">BLOCKED<" in page and "cannot start a shot from an image" in page
    assert "a test note" in page
    player = tmp_path / "report" / "media" / "vp" / "vp-MiniMax-H3-12GB--Export" / "export.mp4"
    assert player.is_file() and (player.parent / "export.thumb.jpg").is_file()
    assert 'src="media/vp/vp-MiniMax-H3-12GB--Export/export.mp4"' in page
    assert (tmp_path / "report" / "media" / "vp" / "vp-MiniMax-H3-12GB--Shot_1" / "0.thumb.jpg").is_file()
    assert "http://" not in page and "https://" not in page
    report = read(tmp_path / "report" / "report.json")
    assert report["runs"] == [] and report["machine"] == "box"
    steps = {(step["engine"], step["step"]): step for step in report["scenario"]["steps"]}
    assert steps[(WAN, "Shot 3 Ref2VA")]["status"] == "skipped"
    assert steps[(WAN, "Shot 2 chained")]["verdict"] == "BLOCKED"
    assert steps[(H3, "Export")]["verdict"] == "PASS" and steps[(H3, "Export")]["seconds"] is not None


def test_the_chaining_checks_are_shown_as_recorded_and_a_failed_one_is_a_failure(vp_api, tmp_path):
    run_dir = scenario_run(vp_api, tmp_path / "out", "vp-b", [H3])
    scenario = read(run_dir / "scenario.json")
    second = next(step for step in scenario["engines"][3]["steps"] if step.get("shot") == "s2-bottle")
    result_path = run_dir / second["result"]
    result = read(result_path)
    for check in result["checks"]:
        if check["check"] == "chain_frame":
            check.update(actual={"state": None, "source": {}}, ok=False)
    result["verdict"] = "FAIL"
    write(result_path, result)
    second["verdict"] = "FAIL"
    second["result"] = second["result"].replace("/", "\\")
    write(run_dir / "scenario.json", scenario)
    loaded = load_scenario(run_dir)
    step = next(item for item in loaded.steps if item.column == "Shot 2 chained" and item.engine == H3)
    assert step.result is not None
    assert [(check["check"], check["ok"]) for check in step.chain_checks] == [("chain_frame", False), ("chain_start", True)]
    page = write_report(None, tmp_path / "report", media=False, scenario=loaded).read_text(encoding="utf-8")
    assert '<span class="tag bad">chain_frame</span> {&quot;state&quot;: null, &quot;source&quot;: {}}' in page
    assert '<span class="tag ok">chain_start</span> &quot;i2v&quot;' in page
    assert '<a class="cell bad" href="#vp-MiniMax-H3-12GB--Shot_2_chained"' in page


def test_a_matrix_and_a_scenario_of_one_machine_and_version_share_a_page(vp_api, tmp_path, case_file, capsys):
    matrix_dir = matrix_run(vp_api, tmp_path, case_file, "night-1")
    night = tmp_path / "out" / "night"
    night.mkdir()
    write(night / "night.json", {"run_id": "night", "segments": [{"run_id": "night-1"}]})
    run_dir = scenario_run(vp_api, tmp_path / "out", "vp-c", [H3])
    assert split_dirs([night, run_dir]) == ([matrix_dir], [run_dir])
    code = main(["report", str(night), str(run_dir), "--out", str(tmp_path / "both"), "--no-media", "--pack", str(tmp_path / "pack" / "pack.toml")])
    assert code == 0
    page = (tmp_path / "both" / "index.html").read_text(encoding="utf-8")
    assert page.index("<h2>Matrix</h2>") < page.index('<h2 id="vp">') < page.index("<h2>Cells</h2>") < page.index('<h2 id="vp-steps">')
    report = read(tmp_path / "both" / "report.json")
    assert report["runs"] == ["night-1"] and report["scenario"]["run_id"] == "vp-c"
    other = scenario_run(vp_api, tmp_path / "out", "vp-d", [H3], machine="elsewhere")
    capsys.readouterr()
    code = main(["report", str(matrix_dir), str(other), "--out", str(tmp_path / "refused"), "--no-media"])
    assert code == 2
    assert "use merge" in capsys.readouterr().err
    scenario = read(run_dir / "scenario.json")
    scenario["app_version"] = "0.0.1"
    write(run_dir / "scenario.json", scenario)
    with pytest.raises(ReportError, match="same version"):
        write_report(load_set([matrix_dir]), tmp_path / "refused", media=False, scenario=load_scenario(run_dir))


def test_compare_flags_a_changed_step_of_two_scenarios_and_refuses_another_pack(vp_api, tmp_path, capsys):
    old = scenario_run(vp_api, tmp_path / "out", "vp-old", [H3])
    new = scenario_run(vp_api, tmp_path / "out", "vp-new", [H3])
    scenario = read(new / "scenario.json")
    steps = scenario["engines"][3]["steps"]
    steps[2]["verdict"] = "FAIL"
    result = read(new / steps[0]["result"])
    result["timing"]["run_seconds"] = 60
    write(new / steps[0]["result"], result)
    scenario["settings"]["upscaler"] = "seedvr2"
    write(new / "scenario.json", scenario)
    comparison = compare_scenarios(load_scenario(new), load_scenario(old))
    rows = {row["step"]: row for row in comparison["rows"]}
    assert rows[f"{H3} · Shot 3 Ref2VA"]["verdict_changed"] is True
    assert rows[f"{H3} · Shot 1"]["duration_flag"] is True and rows[f"{H3} · Shot 1"]["duration_change"] == 4.0
    assert rows[f"{H3} · Export"]["verdict_changed"] is False
    assert "upscaler: rtx then, seedvr2 now" in comparison["changes"]
    code = main(["report", str(new), "--compare", str(old), "--out", str(tmp_path / "report"), "--no-media"])
    assert code == 0
    page = (tmp_path / "report" / "index.html").read_text(encoding="utf-8")
    assert "Compared with the previous scenario" in page and "PASS → FAIL" in page
    assert "compare scenario: 1 verdicts changed, 1 durations beyond 20 %" in capsys.readouterr().out
    other = read(old / "scenario.json")
    other["pack"]["sha256"] = "0" * 64
    write(old / "scenario.json", other)
    with pytest.raises(ReportError, match="same pack"):
        compare_scenarios(load_scenario(new), load_scenario(old))


def test_merge_puts_each_scenario_in_the_column_of_its_machine(vp_api, tmp_path, case_file):
    alpha = matrix_run(vp_api, tmp_path, case_file, "a-1", machine="alpha")
    alpha_vp = scenario_run(vp_api, tmp_path / "out", "a-vp", [H3], machine="alpha")
    beta_vp = scenario_run(vp_api, tmp_path / "out", "b-vp", [WAN], machine="beta")
    code = main(["merge", str(alpha), str(alpha_vp), str(beta_vp), "--out", str(tmp_path / "merged")])
    assert code == 0
    page = (tmp_path / "merged" / "index.html").read_text(encoding="utf-8")
    assert "<th>Cell</th><th>alpha</th><th>beta</th>" in page
    assert "<th>Step</th><th>alpha</th><th>beta</th>" in page
    assert "a-1, scenario a-vp" in page and "scenario b-vp" in page
    row = page[page.index(f"<td>{WAN} · Shot 3 Ref2VA</td>"):]
    row = row[: row.index("</tr>")]
    assert ">left out<" in row and '<div class="cell off"' in row
    second = scenario_run(vp_api, tmp_path / "out", "a-vp-2", [H3], machine="alpha")
    assert main(["merge", str(alpha_vp), str(second), "--out", str(tmp_path / "refused")]) == 2


def test_a_dry_run_folder_is_refused_as_a_scenario(tmp_path):
    folder = tmp_path / "dry"
    folder.mkdir()
    write(folder / "plan.json", {"kind": "vp-scenario", "dry_run": True})
    with pytest.raises(ReportError, match="dry run"):
        split_dirs([folder])
