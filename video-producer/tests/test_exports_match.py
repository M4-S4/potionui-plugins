import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest
from PIL import Image

from backend import projects
from backend.exports import levels, match, video

HAS_FFMPEG = bool(shutil.which("ffmpeg") and shutil.which("ffprobe"))

FIXTURE = json.loads((Path(__file__).parent / "fixtures" / "color_match.json").read_text(encoding="utf-8"))

BLOCK, COLUMNS, INNER = 8, 24, 2

PATHS = {"ffmpeg": "/usr/bin/ffmpeg", "output": "/tmp/out/mezzanine.mkv", "graph": "/tmp/out/graph.txt"}


def _match(**fields):
    return {"anchor": "keyframe", "anchorId": "f1", "assetId": "a1", "strength": 100, "source": [50, 0, 0, 20, 8, 8], "target": [50, 0, 0, 20, 8, 8], **fields}


def _trilinear(points, size, rgb):
    scaled = [c / 255 * (size - 1) for c in rgb]
    low = [min(int(v), size - 2) for v in scaled]
    frac = [scaled[k] - low[k] for k in range(3)]
    out = [0.0, 0.0, 0.0]
    for db in (0, 1):
        for dg in (0, 1):
            for dr in (0, 1):
                weight = (frac[0] if dr else 1 - frac[0]) * (frac[1] if dg else 1 - frac[1]) * (frac[2] if db else 1 - frac[2])
                point = points[(low[2] + db) * size * size + (low[1] + dg) * size + low[0] + dr]
                for k in range(3):
                    out[k] += weight * point[k]
    return [min(max(round(v * 255), 0), 255) for v in out]


def _gap(found, expected):
    errors = sorted(max(abs(a[k] - b[k]) for k in range(3)) for a, b in zip(found, expected))
    mean = sum(abs(a[k] - b[k]) for a, b in zip(found, expected) for k in range(3)) / (3 * len(found))
    return mean, errors[int(len(errors) * 0.95)], errors[-1]


def _stats(pixels):
    labs = [match.to_lab([c / 255 for c in rgb]) for rgb in pixels]
    means = [sum(lab[k] for lab in labs) / len(labs) for k in range(3)]
    spreads = [(sum((lab[k] - means[k]) ** 2 for lab in labs) / len(labs)) ** 0.5 for k in range(3)]
    return means + spreads


def _delta(a, b):
    return sum((a[k] - b[k]) ** 2 for k in range(3)) ** 0.5


def _board(colors, path):
    rows = len(colors) // COLUMNS
    board = Image.new("RGB", (COLUMNS * BLOCK, rows * BLOCK))
    for index, color in enumerate(colors):
        x, y = (index % COLUMNS) * BLOCK, (index // COLUMNS) * BLOCK
        board.paste(tuple(color), (x, y, x + BLOCK, y + BLOCK))
    board.save(path)
    return board.size


def _blocks(raw, width, count):
    found = []
    for index in range(count):
        x0, y0 = (index % COLUMNS) * BLOCK, (index // COLUMNS) * BLOCK
        sums, n = [0, 0, 0], 0
        for y in range(y0 + INNER, y0 + BLOCK - INNER):
            for x in range(x0 + INNER, x0 + BLOCK - INNER):
                at = (y * width + x) * 3
                for k in range(3):
                    sums[k] += raw[at + k]
                n += 1
        found.append([s / n for s in sums])
    return found


def _rgb(path, size, *filters):
    chain = ",".join([*filters, f"scale={size[0]}:{size[1]}:flags=neighbor"])
    command = ["ffmpeg", "-v", "error", "-i", str(path), "-frames:v", "1", "-vf", chain, "-f", "rawvideo", "-pix_fmt", "rgb24", "-"]
    return subprocess.run(command, capture_output=True, check=True, timeout=60).stdout


def test_lab_is_cielab_d65_of_srgb_and_comes_back_to_the_same_color():
    assert match.to_lab([1, 1, 1]) == pytest.approx((100, 0, 0), abs=0.01)
    assert match.to_lab([1, 0, 0]) == pytest.approx((53.24, 80.09, 67.2), abs=0.02)
    for rgb in ([0.2, 0.5, 0.8], [1, 0.4, 0], [0.01, 0.02, 0.03]):
        assert match.from_lab(match.to_lab(rgb)) == pytest.approx(rgb, abs=1e-6)
    assert all(0 <= c <= 1 for c in match.from_lab([120, 300, -300]))


def test_the_transfer_moves_means_and_spreads_by_the_strength_and_holds_the_spread_ratio_between_2_3_and_3_2():
    gains, offsets = match.transfer(_match(target=[60, 4, -6, 25, 4, 16]))
    assert gains == pytest.approx((1.25, 2 / 3, 1.5))
    assert offsets == pytest.approx((60 - 1.25 * 50, 4, -6))
    gains, offsets = match.transfer(_match(strength=50, target=[60, 4, -6, 25, 4, 16]))
    assert gains == pytest.approx((1.125, 5 / 6, 1.25))
    assert offsets == pytest.approx((0.5 * (60 - 1.25 * 50), 2, -3))
    assert match.is_identity(match.transfer(_match()))
    assert match.is_identity(match.transfer(_match(strength=0, target=[80, 9, 9, 30, 9, 9])))


@pytest.mark.parametrize(
    "fields",
    [{"source": [1, 2, 3]}, {"strength": "80"}, {"strength": True}, {"target": [1, 2, 3, 4, 5, float("nan")]}, {"source": None}],
)
def test_a_match_that_cannot_be_read_has_no_transfer(fields):
    assert match.transfer(_match(**fields)) is None


def test_only_a_match_measured_on_the_asset_the_shot_shows_and_that_moves_colors_applies():
    moving = _match(target=[60, 2, 2, 20, 8, 8])
    assert match.active({"assetId": "a1", "match": moving}) is not None
    assert match.active({"assetId": "a2", "match": moving}) is None
    assert match.active({"assetId": None, "match": moving}) is None
    assert match.active({"assetId": "a1", "match": _match()}) is None
    assert match.active({"assetId": "a1"}) is None


@pytest.mark.parametrize("case", FIXTURE["cases"], ids=lambda case: case["name"])
def test_the_lut_is_the_one_the_page_bakes_and_reads_the_same_pixels_as_its_preview(case):
    assert (FIXTURE["lutSize"], FIXTURE["maxScale"]) == (match.LUT_SIZE, match.MAX_SCALE)
    points = match.lut(match.transfer(case["match"]))
    for index, *expected in case["lut"]:
        assert points[index] == pytest.approx(expected, abs=2e-6)
    preview = [_trilinear(points, match.LUT_SIZE, rgb) for rgb in FIXTURE["colors"]]
    mean, _, worst = _gap(preview, case["preview"])
    assert worst <= 1 and mean < 0.01


def test_the_cube_file_has_its_size_and_a_line_per_point_red_fastest():
    moves = match.transfer(_match(target=[60, 2, 2, 20, 8, 8]))
    lines = match.cube(moves, 3).splitlines()
    assert lines[:2] == ['TITLE "Video Producer match"', "LUT_3D_SIZE 3"]
    assert len(lines) == 2 + 27
    red = match.apply(moves, (1, 0, 0))
    assert [float(v) for v in lines[2 + 2].split()] == pytest.approx(red, abs=1e-6)


def test_cubes_are_written_for_the_shots_whose_match_applies_only(tmp_path, make_doc):
    moving = _match(target=[60, 2, 2, 20, 8, 8])
    doc = make_doc(clips=[
        {"id": "c0", "assetId": "a1", "match": moving},
        {"id": "c1", "assetId": "a2", "match": moving},
        {"id": "c2", "assetId": "a1", "match": _match()},
        {"id": "c3", "assetId": "a1"},
        {"id": "c4", "assetId": "a1", "match": moving},
    ])

    paths = match.write_cubes(doc, tmp_path)

    assert paths == {"c0": str(tmp_path / "match-0.cube"), "c4": str(tmp_path / "match-4.cube")}
    assert (tmp_path / "match-0.cube").read_text(encoding="ascii").count("\n") == 2 + match.LUT_SIZE**3


def test_a_shot_with_a_match_reads_its_lut_before_the_frame_is_fitted_and_its_look_after(make_doc):
    doc = make_doc(clips=[{"id": "c1", "assetId": "a1", "dur": 2, "contrast": 120, "deflicker": True}])
    files = {"c1": {"name": "a.mp4", "path": "/media/a.mp4"}}
    options = {"format": "web", "resolution": "720p", "audio": {}, "stills": [], "cubes": {"c1": "/work/job/match-0.cube"}}

    chain = video.filter_graph(doc, files, options, {**PATHS, "audio": {}}).split(";")[0].split(",")

    names = [step.split("=")[0].split("]")[-1] for step in chain]
    assert names.index("deflicker") == names.index("fps") + 1
    assert names.index("lut3d") == names.index("deflicker") + 1 < names.index("scale") < names.index("pad") < names.index("eq")
    assert "lut3d=file=/work/job/match-0.cube:interp=trilinear" in chain


def test_a_shot_without_a_lut_or_a_still_has_no_lut_and_no_deflicker(make_doc):
    doc = make_doc(clips=[{"id": "c1", "assetId": "a1", "deflicker": True}, {"id": "c2", "assetId": "a2", "start": 4}])
    files = {"c1": {"name": "a.png", "path": "/media/a.png"}, "c2": {"name": "b.mp4", "path": "/media/b.mp4"}}
    options = {"format": "web", "resolution": "720p", "audio": {}, "stills": ["c1"]}

    graph = video.filter_graph(doc, files, options, {**PATHS, "audio": {}})

    assert "lut3d" not in graph and "deflicker" not in graph


def test_a_lut_from_the_working_folder_is_named_relative_to_it_and_escaped_for_the_graph(make_doc, tmp_path):
    folder = tmp_path / "a b,c;d[e]'f"
    doc = make_doc(clips=[{"id": "c1", "assetId": "a1"}])
    files = {"c1": {"name": "a.mp4", "path": str(tmp_path / "a.mp4")}}
    options = {"format": "web", "resolution": "720p", "audio": {}, "stills": [], "cubes": {"c1": str(folder / "match-0.cube")}}

    inputs, chains = video._assembly(doc, files, options, {}, str(tmp_path))

    assert "lut3d=file=./a b\\,c\\;d\\[e\\]\\\\\\'f/match-0.cube:interp=trilinear" in chains[0]


@pytest.mark.parametrize(
    "text, escaped",
    [("./x/match-0.cube", "./x/match-0.cube"), ("C:/x/m.cube", "C\\\\:/x/m.cube"), ("a'b", "a\\\\\\'b"), ("a,b;c[d]", "a\\,b\\;c\\[d\\]")],
)
def test_a_filter_value_is_escaped_for_the_option_then_for_the_graph(text, escaped):
    assert video.filter_value(text) == escaped


@pytest.mark.skipif(os.name != "nt", reason="drive letters and backslashes exist on Windows only")
def test_a_windows_path_is_named_with_forward_slashes_and_its_drive_escaped():
    assert video.filter_path("C:\\Jobs\\a b\\m'1.cube") == "C\\\\:/Jobs/a b/m\\\\\\'1.cube"


@pytest.mark.requires_ffmpeg
@pytest.mark.skipif(not HAS_FFMPEG, reason="ffmpeg and ffprobe are not on the PATH")
@pytest.mark.parametrize("relative", [False, True], ids=["absolute", "relative"])
async def test_the_export_reads_a_lut_whose_path_has_a_drive_spaces_quotes_and_graph_characters(relative, make_doc, tmp_path):
    folder = tmp_path / "job a b,c;d[e]'f"
    folder.mkdir()
    size = _board(FIXTURE["colors"], tmp_path / "colors.png")
    case = FIXTURE["cases"][0]
    doc = make_doc(clips=[{"id": "c1", "assetId": "a1", "dur": 0.2, "match": case["match"]}], aspect="1:1")
    doc["resolution"] = "720p"
    files = {"c1": {"name": "colors.png", "path": str(tmp_path / "colors.png"), "still": True}}
    cubes = match.write_cubes(doc, folder)
    options = {"format": "web", "resolution": "720p", "stills": ["c1"], "audio": {}, "blind": [], "lengths": {}, "cubes": cubes}
    output = folder / "mezzanine.mp4"
    ffmpeg = shutil.which("ffmpeg")
    paths = {"ffmpeg": ffmpeg, "graph_option": video.graph_option(ffmpeg), "output": str(output), "graph": str(folder / "graph.txt"), "audio": {}}

    if relative:
        await video.assemble_sequence(doc, files, options, {**paths, "cwd": str(tmp_path)}, folder, lambda progress, step: True)
    else:
        (folder / "graph.txt").write_text(video.filter_graph(doc, files, options, paths), encoding="utf-8")
        await video.assemble(video.build_command(doc, files, options, paths), 0.2)

    named = video.filter_path(cubes["c1"], str(tmp_path) if relative else None)
    assert named.startswith("./job a b\\,c" if relative else video.filter_value(str(folder.anchor).replace(os.sep, "/")))
    assert f"lut3d=file={named}:" in (folder / "graph.txt").read_text(encoding="utf-8")
    mean, _, worst = _gap(_blocks(_rgb(output, size), size[0], len(FIXTURE["colors"])), case["preview"])
    assert mean < 3 and worst <= 8


def test_the_schema_and_the_export_agree_on_the_color_and_sound_settings():
    assert projects.MATCH_STATS == match.STATS
    assert set(projects.LOUDNESS_TARGETS) == set(levels.TARGETS)
    assert projects.MAX_CROSSFADE == video.CROSSFADE_LIMIT


def test_the_match_and_the_deflicker_are_optional_fields_of_a_shot(make_doc):
    doc = make_doc(clips=[{"id": "c1", "assetId": "a1", "match": _match(), "deflicker": True}])
    projects.validate_doc(doc)
    for wrong in ({"anchor": "seam"}, {"strength": 101}, {"source": [1, 2, 3, 4, 5]}, {"extra": 1}):
        bad = make_doc(clips=[{"id": "c1", "assetId": "a1", "match": {**_match(), **wrong}}])
        with pytest.raises(projects.DocError):
            projects.validate_doc(bad)


@pytest.mark.requires_ffmpeg
@pytest.mark.skipif(not HAS_FFMPEG, reason="ffmpeg and ffprobe are not on the PATH")
@pytest.mark.parametrize("case", FIXTURE["cases"], ids=lambda case: case["name"])
def test_ffmpeg_reads_the_cube_as_the_page_previews_it(case, tmp_path):
    size = _board(FIXTURE["colors"], tmp_path / "colors.png")
    cube = tmp_path / "m.cube"
    cube.write_text(match.cube(match.transfer(case["match"])), encoding="ascii")

    raw = _rgb(tmp_path / "colors.png", size, "format=rgb24", f"lut3d=file={video.filter_path(cube)}:interp=trilinear")

    mean, _, worst = _gap(_blocks(raw, size[0], len(FIXTURE["colors"])), case["preview"])
    assert worst <= 1.0 and mean <= 0.6


async def _export(make_doc, tmp_path, source, still, clip_match):
    clip = {"id": "c1", "assetId": "a1", "dur": 0.2, **({"match": clip_match} if clip_match else {})}
    doc = make_doc(clips=[clip], aspect="1:1")
    doc["resolution"] = "720p"
    files = {"c1": {"name": source.name, "path": str(source), "still": still}}
    options = {"format": "web", "resolution": "720p", "stills": ["c1"] if still else [], "audio": {}, "blind": [], "lengths": {}, "cubes": match.write_cubes(doc, tmp_path)}
    output = tmp_path / ("matched.mp4" if clip_match else "plain.mp4")
    ffmpeg = shutil.which("ffmpeg")
    paths = {"ffmpeg": ffmpeg, "graph_option": video.graph_option(ffmpeg), "output": str(output), "graph": str(tmp_path / "graph.txt"), "audio": {}, "cwd": str(tmp_path)}
    await video.assemble_sequence(doc, files, options, paths, tmp_path, lambda progress, step: True)
    return output


@pytest.mark.requires_ffmpeg
@pytest.mark.skipif(not HAS_FFMPEG, reason="ffmpeg and ffprobe are not on the PATH")
@pytest.mark.parametrize("case", FIXTURE["cases"], ids=lambda case: case["name"])
@pytest.mark.parametrize("kind", ["still", "video"])
async def test_the_exported_shot_differs_from_its_preview_no_more_than_the_export_of_an_unmatched_shot(case, kind, make_doc, tmp_path):
    size = _board(FIXTURE["colors"], tmp_path / "colors.png")
    count = len(FIXTURE["colors"])
    source = tmp_path / "colors.png"
    expected, plain_expected = case["preview"], FIXTURE["colors"]
    if kind == "video":
        source = tmp_path / "colors.mp4"
        command = ["ffmpeg", "-v", "error", "-loop", "1", "-i", str(tmp_path / "colors.png"), "-t", "0.4", "-r", "25", "-c:v", "libx264", "-crf", "4", "-pix_fmt", "yuv420p", str(source)]
        subprocess.run(command, check=True, timeout=60)
        plain_expected = _blocks(_rgb(source, size), size[0], count)
        points = match.lut(match.transfer(case["match"]))
        expected = [_trilinear(points, match.LUT_SIZE, rgb) for rgb in plain_expected]

    matched = await _export(make_doc, tmp_path, source, kind == "still", case["match"])
    plain = await _export(make_doc, tmp_path, source, kind == "still", None)

    gap = _gap(_blocks(_rgb(matched, size), size[0], count), expected)
    baseline = _gap(_blocks(_rgb(plain, size), size[0], count), plain_expected)
    assert gap[0] <= baseline[0] + 1.5 and gap[1] <= baseline[1] + 2 and gap[2] <= baseline[2] + 3, (gap, baseline)


@pytest.mark.requires_ffmpeg
@pytest.mark.skipif(not HAS_FFMPEG, reason="ffmpeg and ffprobe are not on the PATH")
def test_a_take_with_a_cast_matched_through_ffmpeg_lands_on_its_anchor(tmp_path):
    take = [[90 + i * 2, 70 + i * 2, 40 + i] for i in range(64)]
    anchor = [[70 + i * 2, 72 + i * 2, 74 + i * 2] for i in range(64)]
    stats = {"source": _stats(take), "target": _stats(anchor)}
    size = _board(take * 9, tmp_path / "take.png")
    cube = tmp_path / "m.cube"
    cube.write_text(match.cube(match.transfer(_match(**stats))), encoding="ascii")

    raw = _rgb(tmp_path / "take.png", size, "format=rgb24", f"lut3d=file={video.filter_path(cube)}:interp=trilinear")

    after = _stats(_blocks(raw, size[0], 64))
    assert _delta(stats["source"], stats["target"]) > 15
    assert _delta(after, stats["target"]) < 0.2 * _delta(stats["source"], stats["target"])
