import asyncio
import json
import shutil
import subprocess
from array import array
from pathlib import Path

import pytest

from backend import projects
from backend.exports import levels, video

HAS_FFMPEG = bool(shutil.which("ffmpeg") and shutil.which("ffprobe"))

PATHS = {"ffmpeg": "/usr/bin/ffmpeg", "output": "/tmp/out/mezzanine.mkv", "graph": "/tmp/out/graph.txt"}

REPORT = """[Parsed_loudnorm_0 @ 0x56e94e1daf00]
{
	"input_i" : "-39.03",
	"input_tp" : "-32.44",
	"input_lra" : "12.20",
	"input_thresh" : "-49.03",
	"output_i" : "-11.67",
	"output_tp" : "-5.01",
	"output_lra" : "4.00",
	"output_thresh" : "-22.66",
	"normalization_type" : "dynamic",
	"target_offset" : "-2.33"
}
"""

MEASURED = {"input_i": -30.0, "input_tp": -20.0, "input_lra": 6.0, "input_thresh": -40.0}


def _doc(make_doc, audio=(), master=None, fps=25, srcs=None):
    doc = make_doc(clips=[{"id": "c1", "start": 0, "dur": 6}])
    doc["fps"] = fps
    doc["audio"] = [
        {"id": f"u{index}", "assetId": None, "lane": "A1", "start": 0, "dur": 1, "srcIn": 0, "fadeIn": 0, "fadeOut": 0, "gain": 0, **item}
        for index, item in enumerate(audio)
    ]
    doc["assets"] = [{"id": key, "kind": "audio", "name": key, "src": None, "srcDur": length} for key, length in (srcs or {}).items()]
    doc["master"] = {"vol": 0, **(master or {})}
    return doc


def _sounds(doc):
    return {item["id"]: f"/media/{item['id']}.wav" for item in doc["audio"]}


def _shape(doc):
    return [[(heard.item["id"], round(heard.head, 6), round(heard.tail, 6)) for heard in run] for run in video.runs(doc, _sounds(doc))]


def test_the_loudness_target_is_the_masters_setting_and_none_keeps_the_mix():
    assert levels.target_of({"master": {"vol": 0}}) is None
    assert levels.target_of({"master": {"vol": 0, "loudness": "web"}}) == -14
    assert levels.target_of({"master": {"vol": 0, "loudness": "broadcast"}}) == -23
    assert levels.target_of({"master": {"vol": 0, "loudness": "loud"}}) is None
    assert levels.target_of({}) is None


def test_the_first_pass_only_measures_the_first_audio_stream_and_prints_json():
    command = levels.measure_command("ffmpeg", Path("/job/mezzanine.mp4"), -14)
    assert command[command.index("-af") + 1] == "loudnorm=I=-14:TP=-1:LRA=11:print_format=json"
    assert command[-3:] == ["-f", "null", "-"] and "-vn" in command
    assert command[command.index("-loglevel") + 1] == "info"


def test_the_measurement_is_read_from_the_last_json_report_on_stderr():
    stderr = "size=N/A time=00:00:05.10 bitrate=N/A speed=28.9x\n" + REPORT.replace("-39.03", "-1") + "noise\n" + REPORT
    assert levels.parse(stderr) == {"input_i": -39.03, "input_tp": -32.44, "input_lra": 12.2, "input_thresh": -49.03}


@pytest.mark.parametrize("stderr", ["", "no report here", REPORT.replace('"-39.03"', '"-inf"'), REPORT.replace('"-39.03"', '"-75"'), REPORT.replace('"-39.03"', '"loud"')])
def test_a_silent_mix_or_a_missing_report_has_no_measurement(stderr):
    assert levels.parse(stderr) is None


def test_the_second_pass_is_one_linear_gain_to_the_target_resampled_to_the_mix_rate():
    text = levels.normalize_filter(-14, MEASURED, 48000)
    assert text == (
        "loudnorm=I=-14:TP=-1:LRA=11:measured_I=-30:measured_TP=-20:measured_LRA=6:measured_thresh=-40:linear=true,aresample=48000"
    )


def test_the_target_is_lowered_so_that_the_true_peak_stays_under_the_ceiling():
    text = levels.normalize_filter(-14, {**MEASURED, "input_i": -20.0, "input_tp": -2.0}, 48000)
    assert text.startswith("loudnorm=I=-19.1:TP=-1:")


def test_the_range_target_is_never_narrower_than_the_measured_range_so_loudnorm_stays_linear():
    assert ":LRA=15.1:" in levels.normalize_filter(-14, {**MEASURED, "input_lra": 15.04}, 48000)
    assert ":LRA=50:" in levels.normalize_filter(-14, {**MEASURED, "input_lra": 80.0}, 48000)


def test_measured_values_are_held_in_the_ranges_loudnorm_accepts():
    text = levels.normalize_filter(-14, {"input_i": -120.0, "input_tp": 120.0, "input_lra": 120.0, "input_thresh": 3.0}, 48000)
    assert "measured_I=-99:measured_TP=99:measured_LRA=99:measured_thresh=0" in text
    assert text.startswith("loudnorm=I=-70:")


def test_the_delivery_run_takes_the_audio_filter_when_given(tmp_path):
    plain = video.convert_command("ffmpeg", tmp_path / "m.mp4", tmp_path / "f.mp4", (1280, 720), 25)
    loud = video.convert_command("ffmpeg", tmp_path / "m.mp4", tmp_path / "f.mp4", (1280, 720), 25, "loudnorm=I=-14")
    assert "-af" not in plain
    assert loud[loud.index("-af") + 1] == "loudnorm=I=-14" and loud.index("-af") < loud.index("-c:a")
    assert [part for part in loud if part not in ("-af", "loudnorm=I=-14")] == plain


def test_the_loudness_and_the_crossfade_are_optional_fields_of_the_master(make_doc):
    doc = make_doc()
    doc["master"] = {"vol": 0, "loudness": "web", "crossfade": 0.5}
    projects.validate_doc(doc)
    for wrong in ({"loudness": "max"}, {"crossfade": 3}, {"crossfade": -1}, {"limiter": True}):
        doc["master"] = {"vol": 0, **wrong}
        with pytest.raises(projects.DocError):
            projects.validate_doc(doc)


@pytest.mark.parametrize("value, length", [(None, 0), (0, 0), (0.01, 0), (0.5, 0.5), (5, 2.0), (True, 0), ("0.5", 0)])
def test_the_crossfade_length_is_the_masters_setting_held_under_two_seconds(value, length):
    master = {"vol": 0} if value is None else {"vol": 0, "crossfade": value}
    assert video.crossfade_of({"master": master}) == length


def test_without_a_crossfade_every_item_plays_alone_with_the_chain_it_had(make_doc):
    audio = [{"start": 0, "dur": 1, "srcIn": 1}, {"start": 1, "dur": 1, "srcIn": 1}]
    off = _doc(make_doc, audio)
    chains, labels = video._lanes(off, _sounds(off), video._Inputs())
    assert _shape(off) == [[("u0", 0, 0)], [("u1", 0, 0)]]
    assert labels == ["[m0]", "[m1]"] and all("acrossfade" not in chain for chain in chains)
    assert chains[1] == f"[1:a]{','.join(video.sound_chain(off['audio'][1], off['lanes'][0]))}[m1]"


def test_neighbours_of_a_lane_crossfade_half_on_each_side_of_the_cut(make_doc):
    doc = _doc(make_doc, [{"start": 0, "dur": 2, "assetId": "s0"}, {"start": 2, "dur": 2, "srcIn": 1}], {"crossfade": 0.5}, srcs={"s0": 5})
    assert _shape(doc) == [[("u0", 0, 0.25), ("u1", 0.25, 0)]]


def test_a_side_without_source_past_the_cut_leaves_the_whole_crossfade_to_the_other(make_doc):
    doc = _doc(make_doc, [{"start": 0, "dur": 2, "assetId": "s0"}, {"start": 2, "dur": 2, "srcIn": 0}], {"crossfade": 0.5}, srcs={"s0": 5})
    assert _shape(doc) == [[("u0", 0, 0.5), ("u1", 0, 0)]]
    doc = _doc(make_doc, [{"start": 0, "dur": 2, "assetId": "s0"}, {"start": 2, "dur": 2, "srcIn": 3}], {"crossfade": 0.5}, srcs={"s0": 2.1})
    assert _shape(doc) == [[("u0", 0, 0.1), ("u1", 0.4, 0)]]


def test_items_with_no_source_past_the_cut_on_either_side_keep_a_hard_cut(make_doc):
    doc = _doc(make_doc, [{"start": 0, "dur": 2, "assetId": "s0"}, {"start": 2, "dur": 2, "srcIn": 0}], {"crossfade": 0.5}, srcs={"s0": 2})
    assert _shape(doc) == [[("u0", 0, 0)], [("u1", 0, 0)]]


def test_the_crossfade_is_at_most_half_of_either_item(make_doc):
    doc = _doc(make_doc, [{"start": 0, "dur": 0.4}, {"start": 0.4, "dur": 3, "srcIn": 2}], {"crossfade": 1})
    assert _shape(doc) == [[("u0", 0, 0.1), ("u1", 0.1, 0)]]


@pytest.mark.parametrize(
    "second",
    [{"start": 2.05, "dur": 1, "srcIn": 1}, {"start": 1.9, "dur": 1, "srcIn": 1}, {"start": 2, "dur": 1, "srcIn": 1, "lane": "A2"}],
    ids=["gap", "overlap", "other lane"],
)
def test_items_apart_overlapping_or_on_another_lane_are_no_neighbours(make_doc, second):
    doc = _doc(make_doc, [{"start": 0, "dur": 2}, second], {"crossfade": 0.5})
    if second.get("lane") == "A2":
        doc["lanes"].append({**doc["lanes"][0], "id": "A2"})
    assert [len(run) for run in video.runs(doc, _sounds(doc))] == [1, 1]


def test_a_cut_within_half_a_frame_still_counts_as_neighbours(make_doc):
    doc = _doc(make_doc, [{"start": 0, "dur": 2}, {"start": 2.02, "dur": 1, "srcIn": 1}], {"crossfade": 0.5}, fps=25)
    assert [len(run) for run in video.runs(doc, _sounds(doc))] == [2]


def test_a_run_of_three_takes_source_on_both_sides_of_the_middle_item_and_keeps_the_document_order(make_doc):
    doc = _doc(
        make_doc,
        [{"start": 4, "dur": 2, "srcIn": 1}, {"start": 0, "dur": 2}, {"start": 2, "dur": 2, "srcIn": 1}, {"start": 7, "dur": 1}],
        {"crossfade": 0.4},
    )
    assert _shape(doc) == [[("u1", 0, 0.2), ("u2", 0.2, 0.2), ("u0", 0.2, 0)], [("u3", 0, 0)]]


def test_a_run_is_played_with_its_extra_source_without_its_inner_fades_joined_by_acrossfade_and_delayed_once(make_doc):
    doc = _doc(
        make_doc,
        [{"start": 1, "dur": 2, "fadeIn": 0.3, "fadeOut": 0.4, "gain": -3}, {"start": 3, "dur": 2, "srcIn": 1, "fadeIn": 0.6, "fadeOut": 0.5}],
        {"crossfade": 0.5},
    )

    chains, labels = video._lanes(doc, _sounds(doc), video._Inputs())

    assert labels == ["[m0]"]
    assert chains == [
        "[0:a]atrim=start=0:duration=2.25,asetpts=PTS-STARTPTS,aresample=48000,aformat=sample_fmts=fltp:channel_layouts=stereo,"
        "volume=-3dB,afade=t=in:st=0:d=0.3,apad=whole_dur=2.25[m0x0]",
        "[1:a]atrim=start=0.75:duration=2.25,asetpts=PTS-STARTPTS,aresample=48000,aformat=sample_fmts=fltp:channel_layouts=stereo,"
        "volume=0dB,afade=t=out:st=1.75:d=0.5,apad=whole_dur=2.25[m0x1]",
        "[m0x0][m0x1]acrossfade=d=0.5:c1=qsin:c2=qsin[m0j1]",
        "[m0j1]adelay=delays=1000:all=1[m0]",
    ]


def test_the_premix_keeps_a_run_of_neighbours_in_one_batch(make_doc, monkeypatch, tmp_path):
    graphs = []

    async def ran(command, *args, **kwargs):
        graphs.append(Path(command[command.index("-/filter_complex") + 1]).read_text(encoding="utf-8"))
        return ""

    monkeypatch.setattr(video, "MIX_INPUTS", 3)
    monkeypatch.setattr(video, "assemble", ran)
    doc = _doc(make_doc, [{"start": 0, "dur": 2}, {"start": 3, "dur": 1}, {"start": 4, "dur": 1, "srcIn": 1}, {"start": 5, "dur": 1, "srcIn": 1}], {"crossfade": 0.5})
    sounds = {item["id"]: str(tmp_path / f"{item['id']}.wav") for item in doc["audio"]}

    asyncio.run(video._premix(doc, sounds, {**PATHS, "graph_option": "-/filter_complex"}, tmp_path, 6.0, None))

    assert len(graphs) == 2
    assert graphs[0].count("acrossfade") == 0 and graphs[1].count("acrossfade") == 2


def _tone(folder, name, frequency, seconds):
    path = folder / name
    command = ["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", f"sine=frequency={frequency}:sample_rate=48000:duration={seconds}", "-ac", "2", "-c:a", "pcm_f32le", str(path)]
    subprocess.run(command, check=True, timeout=60)
    return path


def _samples(path):
    command = ["ffmpeg", "-v", "error", "-i", str(path), "-f", "f32le", "-ac", "1", "-ar", "48000", "-"]
    found = array("f")
    found.frombytes(subprocess.run(command, capture_output=True, check=True, timeout=60).stdout)
    return found


def _window(samples, start, end):
    return samples[round(start * 48000):round(end * 48000)]


@pytest.mark.requires_ffmpeg
@pytest.mark.skipif(not HAS_FFMPEG, reason="ffmpeg and ffprobe are not on the PATH")
@pytest.mark.parametrize("start", [1.0, 1.02, 0.98], ids=["touching", "a gap of half a frame", "an overlap of half a frame"])
async def test_a_crossfaded_item_keeps_its_place_on_the_timeline_to_the_sample(make_doc, tmp_path, start):
    first, second = _tone(tmp_path, "a.wav", 440, 2), _tone(tmp_path, "b.wav", 660, 3)
    doc = _doc(make_doc, [{"start": 0, "dur": 1, "assetId": "sa"}, {"start": start, "dur": 1, "srcIn": 0.5, "assetId": "sb"}], {"crossfade": 0.4}, srcs={"sa": 2, "sb": 3})
    sounds = {"u0": str(first), "u1": str(second)}
    inputs = video._Inputs(cwd=str(tmp_path))
    chains, labels = video._lanes(doc, sounds, inputs)
    graph = tmp_path / "graph.txt"
    graph.write_text(";".join([*chains, f"{''.join(labels)}anull[aout]"]), encoding="utf-8")
    output = tmp_path / "mix.wav"
    ffmpeg = shutil.which("ffmpeg")
    run = {"ffmpeg": ffmpeg, "graph_option": video.graph_option(ffmpeg), "graph": str(graph), "output": str(output)}

    await video.assemble(video._command(run, inputs.args, video.LANES_ENCODER, 2.0, maps=("[aout]",)), 2.0, None, None, str(tmp_path))

    mix, a, b = _samples(output), _samples(first), _samples(second)
    assert [len(group) for group in video.runs(doc, sounds)] == [2]
    assert len(mix) == pytest.approx(min(start + 1, 2.0) * 48000, abs=2)
    assert max(abs(x - y) for x, y in zip(_window(mix, 0.1, 0.75), _window(a, 0.1, 0.75))) < 1e-4
    assert max(abs(x - y) for x, y in zip(_window(mix, 1.3, 1.9), _window(b, 1.3 - start + 0.5, 1.9 - start + 0.5))) < 1e-4
    middle = _window(mix, 0.95, 1.05)

    def share(signal):
        return sum(x * y for x, y in zip(middle, signal)) / sum(y * y for y in signal)

    assert 0.5 < share(_window(a, 0.95, 1.05)) < 0.9 and 0.5 < share(_window(b, 0.95 - start + 0.5, 1.05 - start + 0.5)) < 0.9


def _loudness(path):
    command = ["ffmpeg", "-hide_banner", "-nostdin", "-i", str(path), "-map", "0:a:0", "-af", "loudnorm=print_format=json", "-f", "null", "-"]
    return levels.parse(subprocess.run(command, capture_output=True, check=True, timeout=120).stderr.decode("utf-8", "replace"))


def _mezzanine(folder, volume):
    path = folder / "mezzanine.mp4"
    command = [
        "ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "color=c=gray:s=320x180:r=25:d=6",
        "-f", "lavfi", "-i", f"sine=frequency=440:sample_rate=48000:duration=6,volume={volume}",
        "-shortest", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "192k", "-ac", "2", str(path),
    ]
    subprocess.run(command, check=True, timeout=60)
    return path


@pytest.mark.requires_ffmpeg
@pytest.mark.skipif(not HAS_FFMPEG, reason="ffmpeg and ffprobe are not on the PATH")
@pytest.mark.parametrize("setting", ["web", "broadcast"])
async def test_the_delivery_file_lands_on_the_loudness_target(setting, tmp_path):
    mezzanine = _mezzanine(tmp_path, "-32dB")
    final = tmp_path / "final.mp4"
    target = levels.TARGETS[setting]

    await video.convert(shutil.which("ffmpeg"), mezzanine, final, (320, 180), 25, 6.0, lambda progress, step: True, None, target)

    assert _loudness(final)["input_i"] == pytest.approx(target, abs=1.0)
    assert _loudness(final)["input_tp"] <= levels.TRUE_PEAK + 0.5


@pytest.mark.requires_ffmpeg
@pytest.mark.skipif(not HAS_FFMPEG, reason="ffmpeg and ffprobe are not on the PATH")
async def test_a_silent_mix_is_delivered_without_a_second_pass(tmp_path):
    mezzanine = _mezzanine(tmp_path, "0")

    assert await video.loudness_filter(shutil.which("ffmpeg"), mezzanine, -14, 6.0) is None


@pytest.mark.requires_ffmpeg
@pytest.mark.skipif(not HAS_FFMPEG, reason="ffmpeg and ffprobe are not on the PATH")
async def test_without_a_loudness_target_the_level_of_the_mix_is_kept(tmp_path):
    mezzanine = _mezzanine(tmp_path, "-32dB")
    final = tmp_path / "final.mp4"

    await video.convert(shutil.which("ffmpeg"), mezzanine, final, (320, 180), 25, 6.0, lambda progress, step: True)

    assert _loudness(final)["input_i"] == pytest.approx(_loudness(mezzanine)["input_i"], abs=0.5)


@pytest.mark.requires_ffmpeg
@pytest.mark.skipif(not HAS_FFMPEG, reason="ffmpeg and ffprobe are not on the PATH")
async def test_render_bakes_the_lut_of_a_matched_shot_brings_the_sound_to_its_target_and_leaves_no_lut_behind(make_doc, monkeypatch, export_storage, make_user, tmp_path):
    from PIL import Image

    from backend import core_bridge, takes

    still = tmp_path / "still.png"
    Image.new("RGB", (64, 36), (120, 90, 60)).save(still)
    tone = _tone(tmp_path, "tone.wav", 440, 3)
    doc = _doc(make_doc, [{"id": "voice", "start": 0, "dur": 2, "gain": -20}], {"loudness": "web", "crossfade": 0.5})
    doc["clips"] = [{**doc["clips"][0], "assetId": "a1", "dur": 2, "match": {"anchor": "keyframe", "anchorId": "f1", "assetId": "a1", "strength": 100, "source": [42, 9, 22, 1, 1, 1], "target": [42, 0, 0, 1, 1, 1]}}]
    doc["resolution"] = "720p"
    shots = {"c1": {"name": still.name, "path": str(still), "still": True}}
    monkeypatch.setattr(video.media, "local_inputs", lambda doc, found, resolver, folder: (shots, {"voice": str(tone)}))
    monkeypatch.setattr(takes, "list_takes", lambda project_id: [])

    async def save_user_media(user, path):
        return {"value": "uploads/0f0e.mp4", "media_type": "video", "original_filename": Path(path).name, "origin": None}

    monkeypatch.setattr(core_bridge, "save_user_media", save_user_media)
    monkeypatch.setattr(core_bridge, "upload_item", lambda user_id, value: {"item_id": "item-1"})
    graphs = []
    real = video.assemble

    async def watched(command, *args, **kwargs):
        if video.GRAPH_OPTION in command or video.LEGACY_GRAPH_OPTION in command:
            option = video.GRAPH_OPTION if video.GRAPH_OPTION in command else video.LEGACY_GRAPH_OPTION
            graphs.append(Path(command[command.index(option) + 1]).read_text(encoding="utf-8"))
        return await real(command, *args, **kwargs)

    monkeypatch.setattr(video, "assemble", watched)
    user = make_user()
    job = {"id": "job-1", "user_id": "user-1", "format": "web", "resolution": "720p"}

    await video.render(job, {"id": "p-1", "name": "Raccord", "doc": doc}, user, user, lambda progress, step: True)

    folder = export_storage / "video_producer" / "exports" / "user-1" / "job-1"
    assert "lut3d=file=" in graphs[0] and "match-0.cube" in graphs[0]
    assert not list(folder.glob("match-*.cube"))
    final = folder / "Raccord_720p.mp4"
    assert _loudness(final)["input_i"] == pytest.approx(-14, abs=1.0)
    raw = subprocess.run(
        ["ffmpeg", "-v", "error", "-i", str(final), "-frames:v", "1", "-vf", "scale=1:1", "-f", "rawvideo", "-pix_fmt", "rgb24", "-"],
        capture_output=True, check=True, timeout=60,
    ).stdout
    assert abs(raw[0] - raw[2]) < abs(120 - 60) / 2
