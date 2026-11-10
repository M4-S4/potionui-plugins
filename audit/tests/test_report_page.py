import io
import re
from pathlib import Path

import numpy as np
from PIL import Image

from potion_audit.pack import load_pack
from potion_audit.report import changes, compare_sets, load_set, series_time, storage_use, write_report

from packs import write_pack
from test_report import assert_self_contained, play, quiet, read, write


def host_probe(**changes):
    probe = {
        "probe": "windows",
        "generated_at": "2026-01-01T00:00:00Z",
        "os": {"caption": "Microsoft Windows 11 Professionnel", "version": "10.0.26300", "build": "26300"},
        "physical_disks": [
            {"device_id": "0", "model": "System NVMe", "bus_type": "NVMe", "media_type": "SSD", "size_bytes": 2 * 10 ** 12, "health": "Healthy", "firmware": "FW-SYSTEM"},
            {"device_id": "1", "model": "Storage SATA", "bus_type": "SATA", "media_type": "SSD", "size_bytes": 10 ** 12, "health": "Healthy", "firmware": "FW-STORAGE"},
            {"device_id": "2", "model": "Archive HDD", "bus_type": "SATA", "media_type": "HDD", "size_bytes": 4 * 10 ** 12, "health": "Healthy", "firmware": "FW-ARCHIVE"},
            {"device_id": "3", "model": "Models NVMe", "bus_type": "NVMe", "media_type": "SSD", "size_bytes": 2 * 10 ** 12, "health": "Healthy", "firmware": "FW-MODELS"},
        ],
        "partitions": [{"disk": 0, "drive": "C"}, {"disk": 1, "drive": "D"}, {"disk": 2, "drive": "F"}, {"disk": 3, "drive": "G"}],
        "volumes": [
            {"drive": drive, "label": label, "file_system": "NTFS", "size_bytes": 10 ** 12, "free_bytes": 5 * 10 ** 11, "free_percent": 50}
            for drive, label in (("C", "system"), ("D", "storage"), ("F", "archive"), ("G", "models"))
        ],
        "wsl": {"distros": [{"name": "docker-desktop", "vhdx": {"path": "G:\\vm\\main\\ext4.vhdx", "size_bytes": 10 ** 8, "drive": "G"}}]},
        "docker_desktop": {"disks": [{"path": "G:\\vm\\disk\\docker_data.vhdx", "size_bytes": 10 ** 12, "drive": "G"}, {"path": "G:\\vm\\main\\ext4.vhdx", "size_bytes": 10 ** 8, "drive": "G"}]},
    }
    probe.update(changes)
    return probe


def container_probe(paths=None, notes=()):
    if paths is None:
        paths = [{"path": "/work/storage", "fs_type": "v9fs", "total_bytes": 10 ** 12, "free_bytes": 5 * 10 ** 11, "findmnt": {"filesystems": [{"source": "D:\\[/audit/storage]", "fstype": "9p", "options": "rw,aname=drvfs;path=D:\\;uid=0"}]}}]
    return {"probe": "linux", "kernel": "6.1", "generated_at": "2026-01-01T00:00:00Z", "paths": paths, "notes": list(notes)}


def probed_report(fake_api, tmp_path, case_file, out_name, probes):
    pack = load_pack(write_pack(tmp_path, case_file))
    if not (tmp_path / "out" / "r1").is_dir():
        play(fake_api, pack, tmp_path / "out", "r1", machine="box")
    files = []
    for index, probe in enumerate(probes):
        path = tmp_path / f"{out_name}-{index}-probe.json"
        write(path, probe)
        files.append(path)
    run_set = load_set([tmp_path / "out" / "r1"], probes=files)
    return run_set, write_report(run_set, tmp_path / out_name, media=False, log=quiet).read_text(encoding="utf-8")


def test_the_host_os_is_named_the_same_whatever_the_language_of_windows(fake_api, tmp_path, case_file):
    _, page = probed_report(fake_api, tmp_path, case_file, "old", [host_probe()])
    assert "Windows 11 · build 26300" in page
    assert "Professionnel" not in page
    current = {"name": "Windows 11 Pro", "edition_id": "Professional", "display_version": "25H2", "version": "10.0.26300", "build": "26300"}
    _, page = probed_report(fake_api, tmp_path, case_file, "new", [host_probe(os=current)])
    assert "Windows 11 Pro 25H2 · build 26300" in page
    script = (Path(__file__).parents[1] / "probe" / "probe-windows.ps1").read_text(encoding="utf-8")
    assert "EditionID" in script and "caption" not in script.lower()


def test_storage_lists_only_the_volumes_and_disks_the_instance_uses_without_firmware(fake_api, tmp_path, case_file):
    run_set, page = probed_report(fake_api, tmp_path, case_file, "used", [host_probe(), container_probe()])
    use = storage_use(run_set)
    assert [volume["drive"] for volume in use["volumes"]] == ["D", "G"]
    assert [disk["model"] for disk in use["disks"]] == ["Storage SATA", "Models NVMe"]
    assert use["uses"]["D"] == ["container mount /work/storage"]
    assert "System NVMe" not in page and "Archive HDD" not in page
    assert "<td>C:</td>" not in page and "<td>F:</td>" not in page
    assert "FW-" not in page and "Firmware" not in page
    assert "Not listed: 2 of 4 physical disks and 2 of 4 volumes of the host, which hold nothing the instance uses" in page
    linked = host_probe(partitions=[])
    for volume in linked["volumes"]:
        volume["disk_numbers"] = [{"C": 0, "D": 1, "F": 2, "G": 3}[volume["drive"]]]
    run_set, _ = probed_report(fake_api, tmp_path, case_file, "linked", [linked, container_probe()])
    assert [disk["model"] for disk in storage_use(run_set)["disks"]] == ["Storage SATA", "Models NVMe"]
    old = host_probe()
    del old["partitions"]
    run_set, page = probed_report(fake_api, tmp_path, case_file, "unlinked", [old, container_probe()])
    assert storage_use(run_set)["disks"] == []
    assert "The host probe does not link D:, G: to a physical disk" in page


def test_a_container_probe_without_mounts_says_so_instead_of_an_empty_table(fake_api, tmp_path, case_file):
    notes = ["path not found: C:/Program Files/Git/work/models"]
    run_set, page = probed_report(fake_api, tmp_path, case_file, "empty", [host_probe(), container_probe(paths=[], notes=notes)])
    assert "The container probe recorded no mount" in page
    assert "path not found: C:/Program Files/Git/work/models" in page and "MSYS_NO_PATHCONV=1" in page
    assert "<th>Path</th>" not in page
    assert [volume["drive"] for volume in storage_use(run_set)["volumes"]] == ["G"]
    assert "a volume that only holds a folder mounted into the container is not recognised" in page


def test_a_virtual_disk_of_docker_desktop_and_wsl_is_listed_once(fake_api, tmp_path, case_file):
    _, page = probed_report(fake_api, tmp_path, case_file, "vhdx", [host_probe()])
    assert page.count("main\\ext4.vhdx") == 1
    assert "Docker Desktop · WSL distribution docker-desktop" in page
    assert page.count("disk\\docker_data.vhdx") == 1


def noise_png() -> bytes:
    buffer = io.BytesIO()
    Image.fromarray(np.random.default_rng(1).integers(0, 255, (64, 64, 3), dtype=np.uint8)).save(buffer, format="PNG")
    return buffer.getvalue()


def test_the_page_opens_on_a_summary_with_a_navigation_and_groups_the_cells_by_preset(fake_api, tmp_path, case_file):
    pack = load_pack(write_pack(tmp_path, case_file))
    play(fake_api, pack, tmp_path / "out", "old", machine="box")
    run = read(tmp_path / "out" / "old" / "run.json")
    run["cells"][0]["verdict"] = "FAIL"
    write(tmp_path / "out" / "old" / "run.json", run)
    fake_api.outputs = {"0.png": noise_png()}
    play(fake_api, pack, tmp_path / "out", "new-1", machine="box")
    (tmp_path / "out" / "night").mkdir()
    write(tmp_path / "out" / "night" / "night.json", {"run_id": "night", "segments": [{"run_id": "new-1"}], "restarts": [{"at": "2026-01-01T03:00:00+00:00", "cell": "core/SDXL:txt2img"}]})
    current = load_set([tmp_path / "out" / "new-1"])
    previous = load_set([tmp_path / "out" / "old"])
    comparison = compare_sets(current, previous)
    page = write_report(current, tmp_path / "report", comparison, log=quiet, previous=previous).read_text(encoding="utf-8")
    nav = page[page.index('<nav class="toc"'):page.index("</nav>")]
    anchors = re.findall(r'href="#([^"]+)"', nav)
    assert anchors == ["summary", "machine", "storage", "compare", "matrix", "cells"]
    for anchor in anchors:
        assert f'<h2 id="{anchor}">' in page
    assert page.index('<h2 id="summary">') < page.index('<h2 id="machine">')
    assert '<p class="headline">' in page and "cells passed" in page
    assert 'Restarts</div><div class="big">1</div>' in page
    assert "1<small> fixed</small> · 0<small> regressed</small>" in page
    assert '<a class="totop" href="#top">' in page
    assert '<section class="group"><h3>core/SDXL ' in page
    assert '<span class="nums">' in page
    assert '<div class="pair">' in page and 'src="media/previous/c-core_SDXL_txt2img/0.webp"' in page
    assert_self_contained(page, tmp_path / "report")


def tokens(block: str) -> dict[str, str]:
    return dict(re.findall(r"(--[\w-]+):\s*([^;]+);", block))


def test_the_page_loads_nothing_from_outside_and_defines_the_dark_and_the_light_theme(fake_api, tmp_path, case_file):
    _, page = probed_report(fake_api, tmp_path, case_file, "theme", [host_probe()])
    assert "<link" not in page.lower() and "@import" not in page and "@font-face" not in page
    assert not re.search(r"<script[^>]*\bsrc=", page)
    assert not re.search(r"url\(\s*['\"]?(?!data:)", page)
    for link in re.findall(r'(?:href|src|poster|action)="([^"]*)"', page):
        assert not re.match(r"[a-z][a-z0-9+.-]*:|//", link, re.I), link
    style = page[page.index("<style>") + len("<style>"):page.index("</style>")]
    dark = re.search(r':root\[data-theme="dark"\] \{([^}]*)\}', style).group(1)
    light = re.search(r':root\[data-theme="light"\] \{([^}]*)\}', style).group(1)
    assert set(tokens(dark)) == set(tokens(light))
    assert {"--bg", "--card", "--soft", "--fg", "--muted", "--line", "--signal", "--ok", "--bad", "--warn", "--idle"} <= set(tokens(dark))
    assert tokens(dark)["--bg"] != tokens(light)["--bg"] and tokens(dark)["--fg"] != tokens(light)["--fg"]
    assert "color-scheme: dark" in dark and "color-scheme: light" in light
    assert '@media (prefers-color-scheme: light) { :root:not([data-theme="dark"])' in style
    assert style.index('--mono: "IBM Plex Mono"') < style.index("monospace")
    assert '<button type="button" class="theme" id="theme">' in page


def test_the_duration_puts_the_measured_time_first_when_the_segments_are_hours_apart(fake_api, tmp_path, case_file):
    found = series_time([("2026-01-01T22:00:00+00:00", "2026-01-02T00:00:00+00:00"), ("2026-01-02T07:30:00+00:00", "2026-01-02T09:30:00+00:00")])
    assert (found["span"], found["pause"], found["active"]) == (41400.0, 27000.0, 14400.0)
    pack = load_pack(write_pack(tmp_path, case_file))
    for run_id, start, end in (("seg-1", "2026-01-01T22:00:00+00:00", "2026-01-02T00:00:00+00:00"), ("seg-2", "2026-01-02T07:30:00+00:00", "2026-01-02T09:30:00+00:00")):
        play(fake_api, pack, tmp_path / "out", run_id, machine="box")
        run = read(tmp_path / "out" / run_id / "run.json")
        run.update(started_at=start, ended_at=end)
        write(tmp_path / "out" / run_id / "run.json", run)
    page = write_report(load_set([tmp_path / "out" / "seg-1", tmp_path / "out" / "seg-2"]), tmp_path / "report", media=False, log=quiet).read_text(encoding="utf-8")
    tile = page[page.index('<div class="label">Duration</div>'):]
    tile = tile[:tile.index("</div></div>")]
    assert "<small> measured</small>" in tile
    assert "active 4 h 00 min, but spread over 11 h 30 min end to end, with 7 h 30 min of pause between segments" in tile


def test_a_fix_a_regression_and_a_step_run_for_the_first_time_are_told_apart():
    rows = [
        {"verdict_changed": True, "previous_verdict": "OOM", "verdict": "PASS"},
        {"verdict_changed": True, "previous_verdict": "PASS", "verdict": "FAIL"},
        {"verdict_changed": True, "previous_verdict": "not recorded", "verdict": "PASS"},
        {"verdict_changed": True, "previous_verdict": "PASS", "verdict": "not run"},
        {"verdict_changed": False, "previous_verdict": "PASS", "verdict": "PASS"},
    ]
    found = changes(rows)
    assert [len(found[name]) for name in ("fixed", "regressed", "newly run", "no longer run")] == [1, 1, 1, 1]
