import asyncio
import math
import shutil
import struct
import subprocess
import zipfile
from pathlib import Path

import pytest

from backend import core_bridge, takes
from backend.exports import levels, video
from backend.exports.mix import write_impulse
from backend.exports.video import filter_graph

HAS_FFMPEG = bool(shutil.which("ffmpeg") and shutil.which("ffprobe"))

PATHS = {"ffmpeg": "/usr/bin/ffmpeg", "output": "/tmp/out/mezzanine.mkv", "graph": "/tmp/out/graph.txt"}

IMPULSE = "/tmp/out/reverb.wav"

SHOT = {"name": "1.mp4", "path": "/media/1.mp4"}

STRIP = (
    "[m0]apad=whole_dur=4,atrim=duration=4,lowshelf=f=200:t=s:w=1:g=3,equalizer=f=1200:t=q:w=1:g=-2,"
    "highshelf=f=5000:t=s:w=1:g=1,lowpass=f=8000:p=2:t=q:w=1.122018,"
    "acompressor=threshold=0.125893:ratio=3:attack=10:release=120:makeup=2.290868:knee=1:detection=peak:link=maximum,"
    "pan=stereo|c0=1*c0+0.707107*c1|c1=0.707107*c1,volume=-4dB[t0]"
)


def _options(**extra):
    return {"format": "web", "resolution": "720p", "audio": {}, "stills": [], "impulse": IMPULSE, **extra}


def _doc(make_doc, audio=(), lanes=None, master=None, aux=None, dur=4):
    doc = make_doc(clips=[{"id": "c1", "start": 0, "dur": dur}])
    doc["audio"] = [
        {"id": f"u{index}", "assetId": None, "lane": "A1", "start": 0, "dur": 1, "srcIn": 0, "fadeIn": 0, "fadeOut": 0, "gain": 0, **item}
        for index, item in enumerate(audio)
    ]
    for lane in doc["lanes"]:
        lane.update({"vol": 0, "pan": 0, "sends": {"R1": -60, "D1": -60}, "inserts": []})
        lane.update((lanes or {}).get(lane["id"], {}))
    for bus in doc["aux"]:
        bus.update((aux or {}).get(bus["id"], {}))
    doc["master"].update(master or {})
    return doc


def _graph(doc, files=None, sounds=None, paths=None, **options):
    return filter_graph(doc, files or {"c1": None}, _options(**options), {**PATHS, **(paths or {}), "audio": sounds or {}}).split(";")


def _strip(graph):
    return next(chain for chain in graph if chain.startswith("[m0]apad="))


def _inputs(doc, files=None, sounds=None, **options):
    command = video.build_command(doc, files or {"c1": None}, _options(**options), {**PATHS, "audio": sounds or {}})
    return [command[index + 1] for index, item in enumerate(command) if item == "-i"]


def test_a_dry_console_sums_each_track_and_mixes_its_role_with_the_shots_sound(make_doc):
    doc = _doc(make_doc, audio=[{"id": "voice"}, {"id": "more", "start": 2}])

    graph = _graph(doc, sounds={"voice": "/v.wav", "more": "/w.wav"})

    assert graph[5] == "[m0][m1]amix=inputs=2:duration=longest:dropout_transition=0:normalize=0,apad=whole_dur=4,atrim=duration=4[t0]"
    assert graph[6] == "[t0]anull[dialogue]"
    assert graph[7] == "[bed][dialogue]amix=inputs=2:duration=first:dropout_transition=0:normalize=0[aout]"
    assert IMPULSE not in _inputs(doc, sounds={"voice": "/v.wav", "more": "/w.wav"})


def test_the_strip_runs_its_equalizer_low_pass_compressor_pan_and_fader_in_the_order_the_page_wires_them(make_doc):
    inserts = [
        {"type": "comp", "on": True, "threshold": -18, "ratio": 3, "attack": 10, "release": 120},
        {"type": "filter", "on": True, "cutoff": 8000},
        {"type": "eq", "on": True, "low": 3, "mid": -2, "high": 1},
    ]
    doc = _doc(make_doc, audio=[{"id": "voice"}], lanes={"A1": {"vol": -4, "pan": -0.5, "inserts": inserts}})

    assert _strip(_graph(doc, sounds={"voice": "/v.wav"})) == STRIP


def test_an_insert_turned_off_and_a_centred_pan_leave_the_sound_as_it_is(make_doc):
    inserts = [{"type": "eq", "on": False, "low": 6, "mid": 6, "high": 6}, {"type": "comp", "on": True, "threshold": -20, "ratio": 1, "attack": 10, "release": 120}]
    doc = _doc(make_doc, audio=[{"id": "voice"}], lanes={"A1": {"inserts": inserts}})

    assert _strip(_graph(doc, sounds={"voice": "/v.wav"})) == "[m0]apad=whole_dur=4,atrim=duration=4[t0]"


def test_a_pan_to_the_right_folds_the_left_channel_into_the_right_one(make_doc):
    doc = _doc(make_doc, audio=[{"id": "voice"}], lanes={"A1": {"pan": 0.5}})

    assert _strip(_graph(doc, sounds={"voice": "/v.wav"})).endswith(",pan=stereo|c0=0.707107*c0|c1=0.707107*c0+1*c1[t0]")


def test_the_sends_feed_one_reverb_and_one_delay_per_role_after_the_fader_and_the_bus_level(make_doc):
    doc = _doc(
        make_doc,
        audio=[{"id": "voice"}, {"id": "music", "lane": "A2"}],
        lanes={"A1": {"vol": -2, "sends": {"R1": -12, "D1": -60}}, "A2": {"sends": {"R1": -12, "D1": -20}}},
        aux={"R1": {"vol": -6}, "D1": {"vol": -10}},
    )
    sounds = {"voice": "/v.wav", "music": "/m.wav"}

    graph = _graph(doc, sounds=sounds)

    assert _inputs(doc, sounds=sounds) == ["/v.wav", "/m.wav", IMPULSE]
    assert "[m0]apad=whole_dur=4,atrim=duration=4,volume=-2dB,asplit=2[t0][t0R1]" in graph
    assert "[t0R1]volume=-18dB[t0R1s]" in graph and "[t1R1]volume=-18dB[t1R1s]" in graph and "[t1D1]volume=-30dB[t1D1s]" in graph
    assert "[2:a]asplit=2[ir0][ir1]" in graph
    assert "[t0R1s][ir0]afir=gtype=none[dialogueR1]" in graph and "[t1R1s][ir1]afir=gtype=none[musicR1]" in graph
    assert (
        "[t1D1s]aecho=in_gain=0:out_gain=1:delays=320|640|960|1280|1600|1920|2240:"
        "decays=1|0.35|0.1225|0.042875|0.015006|0.005252|0.001838,atrim=duration=4[musicD1]"
    ) in graph
    assert "[t0][dialogueR1]amix=inputs=2:duration=longest:dropout_transition=0:normalize=0[dialogue]" in graph
    assert "[t1][musicR1][musicD1]amix=inputs=3:duration=longest:dropout_transition=0:normalize=0[music]" in graph


@pytest.mark.parametrize("aux, sends", [({"R1": {"mute": True}}, {"R1": -6}), ({}, {"R1": -59}), ({"R1": {"vol": -60}}, {"R1": 0})])
def test_a_muted_bus_or_a_send_down_to_silence_opens_no_reverb(make_doc, aux, sends):
    doc = _doc(make_doc, audio=[{"id": "voice"}], lanes={"A1": {"sends": {"D1": -60, **sends}}}, aux=aux)

    graph = ";".join(_graph(doc, sounds={"voice": "/v.wav"}))

    assert "afir" not in graph and IMPULSE not in _inputs(doc, sounds={"voice": "/v.wav"})


def test_the_reverb_takes_its_impulse_as_it_is_with_the_option_of_the_ffmpeg_in_use(make_doc):
    doc = _doc(make_doc, audio=[{"id": "voice"}], lanes={"A1": {"sends": {"R1": 0, "D1": -60}}})

    recent = ";".join(_graph(doc, sounds={"voice": "/v.wav"}, paths={"graph_option": video.GRAPH_OPTION}))
    legacy = ";".join(_graph(doc, sounds={"voice": "/v.wav"}, paths={"graph_option": video.LEGACY_GRAPH_OPTION}))

    assert "afir=irnorm=-1" in recent and "afir=gtype=none" in legacy
    assert video.impulse_option_of(video.GRAPH_OPTION) == "irnorm=-1" and video.impulse_option_of(video.LEGACY_GRAPH_OPTION) == "gtype=none"


@pytest.mark.parametrize("vol, tail", [(-3, ",volume=-3dB"), (-60, ",volume=0"), (0, "")])
def test_the_master_fader_levels_the_mix_and_silences_it_at_its_floor(make_doc, vol, tail):
    doc = _doc(make_doc, audio=[{"id": "voice"}], master={"vol": vol})

    assert _graph(doc, sounds={"voice": "/v.wav"})[-1] == f"[bed][dialogue]amix=inputs=2:duration=first:dropout_transition=0:normalize=0{tail}[aout]"
    assert _graph(_doc(make_doc, master={"vol": vol}))[-1] == f"[bed]{tail[1:] or 'anull'}[aout]"


def test_a_lane_down_to_silence_is_left_out_as_the_page_plays_it(make_doc):
    doc = _doc(make_doc, audio=[{"id": "voice"}, {"id": "music", "lane": "A2"}], lanes={"A1": {"vol": -60}})

    assert [item["id"] for item, _ in video.audible(doc)] == ["music"]


def test_a_mono_file_plays_on_both_channels_at_its_full_level_on_a_track_and_on_a_shot(make_doc):
    doc = _doc(make_doc, audio=[{"id": "voice"}])

    graph = _graph(doc, {"c1": SHOT}, sounds={"voice": "/v.wav"}, audio={"c1": True}, mono=["/v.wav", "/media/1.mp4"])
    stereo = _graph(doc, {"c1": SHOT}, sounds={"voice": "/v.wav"}, audio={"c1": True})

    item = next(chain for chain in graph if chain.endswith("[m0]"))
    bed = next(chain for chain in graph if chain.endswith("[a0]"))
    assert "aresample=48000,pan=stereo|c0=c0|c1=c0,aformat=sample_fmts=fltp:channel_layouts=stereo," in item
    assert "aresample=48000,pan=stereo|c0=c0|c1=c0,aformat=sample_fmts=fltp:channel_layouts=stereo," in bed
    assert "pan=stereo|c0=c0|c1=c0" not in ";".join(stereo)


def test_the_stems_split_the_mix_into_the_four_roles_and_the_shots_sound_under_the_masters_fader(make_doc):
    doc = _doc(make_doc, audio=[{"id": "voice"}, {"id": "music", "lane": "A2"}], master={"vol": -3})

    graph = _graph(doc, sounds={"voice": "/v.wav", "music": "/m.wav"}, stems=True)

    assert "[dialogue]asplit=2[dialoguem][dialogues]" in graph and "[bed]asplit=2[shotsm][shotss]" in graph
    assert "[dialogues]volume=-3dB,apad=whole_dur=4,atrim=duration=4[stem_dialogue]" in graph
    assert "[shotss]volume=-3dB,apad=whole_dur=4,atrim=duration=4[stem_shots]" in graph
    assert "anullsrc=r=48000:cl=stereo,atrim=duration=4[stem_ambience]" in graph and "anullsrc=r=48000:cl=stereo,atrim=duration=4[stem_sfx]" in graph
    assert graph[-1] == "[shotsm][dialoguem][musicm]amix=inputs=3:duration=first:dropout_transition=0:normalize=0,volume=-3dB[aout]"
    assert video.STEM_NAMES == ("dialogue", "music", "ambience", "sfx", "shots")


def test_the_last_run_writes_each_stem_beside_the_mezzanine_as_float_wav(make_doc, monkeypatch, tmp_path):
    commands = []

    async def ran(command, *args, **kwargs):
        commands.append(command)
        return ""

    monkeypatch.setattr(video, "assemble", ran)
    doc = _doc(make_doc, audio=[{"id": "voice"}])
    paths = {**PATHS, "output": str(tmp_path / "mezzanine.mkv"), "graph": str(tmp_path / "graph.txt"), "audio": {"voice": "/v.wav"}}

    stems = asyncio.run(video.assemble_sequence(doc, {"c1": None}, _options(stems=True), paths, tmp_path, lambda progress, step: True))

    assert stems == {name: tmp_path / f"mix-{name}.wav" for name in video.STEM_NAMES}
    command = " ".join(commands[-1])
    for name in video.STEM_NAMES:
        assert f"-map [stem_{name}] -t 4 -c:a pcm_f32le -ar 48000 -ac 2 -rf64 auto {tmp_path / f'mix-{name}.wav'}" in command
    assert asyncio.run(video.assemble_sequence(doc, {"c1": None}, _options(), paths, tmp_path, lambda progress, step: True)) == {}


@pytest.mark.parametrize(
    "fmt, codecs",
    [
        ("master", "-c:v prores_ks -profile:v 3 -pix_fmt yuv422p10le -c:a pcm_s24le -f mov"),
        ("archive", "-c:v libx265 -crf 18 -preset medium -pix_fmt yuv420p10le -tag:v hvc1 -x265-params log-level=error -movflags +faststart -c:a aac -b:a 256k -f mp4"),
        ("web", "-c:v libx264 -crf 26 -preset slow -pix_fmt yuv420p -movflags +faststart -c:a aac -b:a 96k -f mp4"),
        ("social", "-c:v libx264 -crf 26 -preset slow -pix_fmt yuv420p -movflags +faststart -c:a aac -b:a 96k -f mp4"),
    ],
)
def test_each_format_is_converted_with_its_own_codecs(tmp_path, fmt, codecs):
    command = video.convert_command("ffmpeg", tmp_path / "m.mkv", tmp_path / "f", (1920, 1080), 24, "loudnorm=I=-14", fmt)

    assert " ".join(command).endswith(f"-af loudnorm=I=-14 {codecs} {tmp_path / 'f'}")


def test_the_name_of_an_export_tells_its_format_and_its_stems():
    assert video.file_name("Aube sur le port", "1080p", "master") == "Aube_sur_le_port_1080p.mov"
    assert video.file_name("Aube sur le port", "4K", "archive") == "Aube_sur_le_port_4K_archive.mp4"
    assert video.file_name("Aube sur le port", "720p", "social") == "Aube_sur_le_port_720p.mp4"
    assert video.file_name("Aube sur le port", "1080p", "archive", stems=True) == "Aube_sur_le_port_1080p_archive_stems.zip"
    assert video.file_name("Aube sur le port", "1080p", "master", stems=True) == "Aube_sur_le_port_1080p_master_stems.zip"
    assert video.file_name("Aube sur le port", "1080p", "web", stems=True) == "Aube_sur_le_port_1080p_web_stems.zip"
    assert video.download_name("Aube sur le port", "1080p", "archive", True) == "Aube sur le port_1080p_archive_stems"
    assert video.download_name("Aube sur le port", "1080p", "archive") == "Aube sur le port_1080p_archive"
    assert video.stem_file("Aube_sur_le_port_1080p.mov", "music") == "Aube_sur_le_port_1080p_music.wav"


def test_the_stems_are_written_in_24_bits_at_the_gain_the_loudness_target_gave_the_mix(tmp_path):
    stems = {"dialogue": tmp_path / "mix-dialogue.wav", "shots": tmp_path / "mix-shots.wav"}
    finals = {"dialogue": tmp_path / "a_dialogue.wav", "shots": tmp_path / "a_shots.wav"}

    loud = " ".join(video.stems_command("ffmpeg", stems, finals, -3.25))
    plain = " ".join(video.stems_command("ffmpeg", stems, finals))

    assert f"-i {stems['dialogue']} -i {stems['shots']} -map 0:a:0 -af volume=-3.25dB -c:a pcm_s24le -ar 48000 -ac 2 -rf64 auto {finals['dialogue']}" in loud
    assert f"-map 1:a:0 -af volume=-3.25dB -c:a pcm_s24le" in loud and "-af" not in plain


def test_the_gain_of_the_second_pass_is_the_loudness_it_aims_at_less_the_loudness_measured():
    quiet = {"input_i": -23.456, "input_tp": -6.0, "input_lra": 5.0, "input_thresh": -33.0}
    peaky = {"input_i": -20.0, "input_tp": -9.0, "input_lra": 5.0, "input_thresh": -30.0}

    assert levels.normalize_gain(-14, quiet) == pytest.approx(-18.56 + 23.46)
    assert "I=-18.56:" in levels.normalize_filter(-14, quiet, 48000) and "measured_I=-23.46:" in levels.normalize_filter(-14, quiet, 48000)
    assert levels.normalize_gain(-14, peaky) == pytest.approx(6.0)


def test_the_zip_stores_each_file_once_under_its_own_name(tmp_path):
    files = [tmp_path / "a.mov", tmp_path / "a_music.wav"]
    for index, path in enumerate(files):
        path.write_bytes(bytes([index]) * 64)

    packed = video.pack(tmp_path / "a_stems.zip", files)

    with zipfile.ZipFile(packed) as archive:
        assert [(info.filename, info.compress_type, info.file_size) for info in archive.infolist()] == [("a.mov", zipfile.ZIP_STORED, 64), ("a_music.wav", zipfile.ZIP_STORED, 64)]


def _tone(folder, name, channels, seconds=1.0, frequency=1000, volume=0.25):
    path = folder / name
    layout = "mono" if channels == 1 else "stereo"
    subprocess.run(
        [
            "ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-f", "lavfi",
            "-i", f"aevalsrc={volume}*sin(2*PI*{frequency}*t):s=48000:d={seconds}:c={layout}", "-c:a", "pcm_s16le", str(path),
        ],
        check=True,
        timeout=60,
    )
    return path


def _samples(path, start=0.0, seconds=None):
    command = ["ffmpeg", "-hide_banner", "-loglevel", "error", "-ss", str(start), "-i", str(path), "-map", "0:a:0", "-f", "f32le", "-ac", "2", "-ar", "48000"]
    command += ["-t", str(seconds)] if seconds else []
    raw = subprocess.run([*command, "-"], check=True, capture_output=True, timeout=60).stdout
    values = struct.unpack(f"<{len(raw) // 4}f", raw)
    return list(values[0::2]), list(values[1::2])


def _rms(values):
    return math.sqrt(sum(value * value for value in values) / max(len(values), 1))


async def _mix(make_doc, tmp_path, label, sound, **changes):
    doc = _doc(make_doc, audio=[{"id": "voice", "start": 0, "dur": 0.5}], dur=2, **changes)
    paths = {
        "ffmpeg": shutil.which("ffmpeg"),
        "graph_option": video.graph_option(shutil.which("ffmpeg")),
        "output": str(tmp_path / f"{label}.mkv"),
        "graph": str(tmp_path / f"{label}.txt"),
        "audio": {"voice": str(sound)},
    }
    options = _options(impulse=str(write_impulse(tmp_path / "reverb.wav", 48000)), mono=video.mono_files([sound]))
    await video.assemble_sequence(doc, {"c1": None}, options, paths, tmp_path, lambda progress, step: True)
    return tmp_path / f"{label}.mkv"


@pytest.mark.requires_ffmpeg
@pytest.mark.skipif(not HAS_FFMPEG, reason="ffmpeg and ffprobe are not on the PATH")
async def test_the_console_is_heard_in_the_exported_sound(make_doc, tmp_path):
    mono, stereo = _tone(tmp_path, "mono.wav", 1), _tone(tmp_path, "stereo.wav", 2)
    assert video.mono_files([mono, stereo, mono]) == [str(mono)]

    centre = _samples(await _mix(make_doc, tmp_path, "centre", mono), 0.1, 0.3)
    left = _samples(await _mix(make_doc, tmp_path, "left", mono, lanes={"A1": {"pan": -1}}), 0.1, 0.3)
    quiet = _samples(await _mix(make_doc, tmp_path, "quiet", mono, master={"vol": -6}), 0.1, 0.3)
    dry = _samples(await _mix(make_doc, tmp_path, "dry", stereo), 0.8, 0.5)
    wet = _samples(await _mix(make_doc, tmp_path, "wet", stereo, lanes={"A1": {"sends": {"R1": 0, "D1": -60}}}, aux={"R1": {"vol": 0}}), 0.8, 0.5)

    assert _rms(centre[0]) == pytest.approx(0.25 / math.sqrt(2), rel=0.02) and _rms(centre[1]) == pytest.approx(_rms(centre[0]), rel=0.01)
    assert _rms(left[0]) == pytest.approx(0.5 / math.sqrt(2), rel=0.02) and _rms(left[1]) < 1e-4
    assert 20 * math.log10(_rms(quiet[0]) / _rms(centre[0])) == pytest.approx(-6, abs=0.1)
    assert _rms(dry[0]) < 1e-5 and _rms(wet[0]) > 1e-3


@pytest.mark.requires_ffmpeg
@pytest.mark.skipif(not HAS_FFMPEG, reason="ffmpeg and ffprobe are not on the PATH")
@pytest.mark.parametrize("fmt, loudness", [("master", None), ("archive", "web")])
async def test_a_master_or_an_archive_with_its_stems_is_a_zip_of_the_video_and_five_aligned_wav_that_add_up_to_its_sound(
    make_doc, monkeypatch, export_storage, make_user, tmp_path, fmt, loudness
):
    shot = tmp_path / "shot.mp4"
    subprocess.run(
        [
            "ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-f", "lavfi", "-i", "testsrc2=size=320x240:rate=25:duration=2",
            "-f", "lavfi", "-i", "sine=frequency=440:duration=2", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest", str(shot),
        ],
        check=True,
        timeout=60,
    )
    voice, music = _tone(tmp_path, "voice.wav", 1, 0.8, 660), _tone(tmp_path, "music.wav", 2, 2.0, 220, 0.1)
    doc = _doc(
        make_doc,
        audio=[{"id": "voice", "start": 0.3, "dur": 0.8}, {"id": "music", "lane": "A2", "dur": 2}],
        lanes={"A1": {"sends": {"R1": -12, "D1": -60}, "inserts": [{"type": "comp", "on": True, "threshold": -18, "ratio": 3, "attack": 10, "release": 120}]}, "A2": {"pan": 0.4, "vol": -3}},
        master={"vol": -2, **({"loudness": loudness} if loudness else {})},
        dur=2,
    )
    doc["resolution"] = "720p"
    monkeypatch.setattr(video.media, "local_inputs", lambda doc, found, resolver, folder: ({"c1": {"name": shot.name, "path": str(shot), "still": False}}, {"voice": str(voice), "music": str(music)}))
    monkeypatch.setattr(takes, "list_takes", lambda project_id: [])

    async def refused(user, path):
        raise AssertionError("a master or an archive is not copied to the library")

    monkeypatch.setattr(core_bridge, "save_user_media", refused)
    job = {"id": "job-1", "user_id": "user-1", "format": fmt, "resolution": "720p", "stems": True}
    user = make_user()

    result = await video.render(job, {"id": "p-1", "name": "Aube", "doc": doc}, user, user, lambda progress, step: True)

    folder = export_storage / "video_producer" / "exports" / "user-1" / "job-1"
    video_name = video.file_name("Aube", "720p", fmt)
    assert result["file_name"] == video.file_name("Aube", "720p", fmt, stems=True) and result["media_item_id"] is None and result["media_url"] is None
    assert sorted(path.name for path in folder.iterdir()) == [result["file_name"]]
    with zipfile.ZipFile(folder / result["file_name"]) as archive:
        names = archive.namelist()
        archive.extractall(tmp_path / "out")
    assert names == [video_name, *(video.stem_file(video_name, name) for name in video.STEM_NAMES)]
    out = tmp_path / "out"
    probe = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "stream=codec_name,pix_fmt,channels", "-of", "csv=p=0", str(out / video_name)],
        check=True, capture_output=True, text=True, timeout=60,
    ).stdout.split()
    expected = ["prores,yuv422p10le", "pcm_s24le,2"] if fmt == "master" else ["hevc,yuv420p10le", "aac,2"]
    assert [line.strip(",") for line in probe] == expected
    lengths = set()
    for name in video.STEM_NAMES:
        stem = out / video.stem_file(video_name, name)
        info = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "stream=codec_name,channels,sample_rate,duration", "-of", "csv=p=0", str(stem)],
            check=True, capture_output=True, text=True, timeout=60,
        ).stdout.strip()
        codec, rate, channels, seconds = info.split(",")
        assert (codec, rate, channels) == ("pcm_s24le", "48000", "2")
        lengths.add(round(float(seconds), 3))
    assert lengths == {2.0}
    if fmt == "master":
        heard = _samples(out / video_name, 0.0, 2.0)
        parts = [_samples(out / video.stem_file(video_name, name), 0.0, 2.0) for name in video.STEM_NAMES]
        for channel in (0, 1):
            summed = [sum(part[channel][index] for part in parts) for index in range(len(heard[channel]))]
            residue = _rms([a - b for a, b in zip(summed, heard[channel])])
            assert residue < 1e-4 * max(_rms(heard[channel]), 1e-3)
        assert _rms(parts[2][0]) == 0 and _rms(parts[3][0]) == 0 and _rms(parts[4][0]) > 1e-3
