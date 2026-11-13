import pytest
from PIL import Image, ImageCms, PngImagePlugin

from src.plugin_api.media import upload_formats
from src.plugin_api.media_tools import ToolCancelled, ToolContext, ToolFailed

from tools.image import ConvertImage

from .conftest import make_image, noisy_image, params_for

TOOL = "media-convert.image"
PILLOW_FORMATS = {"png": "PNG", "jpeg": "JPEG", "webp": "WEBP"}
SUFFIXES = {"png": ".png", "jpeg": ".jpg", "webp": ".webp"}
MODEL = 0x0110
ORIENTATION = 0x0112
EXIF_IFD = 0x8769
GPS_IFD = 0x8825
TAKEN = 0x9003
LATITUDE_REF = 0x0001


def convert(ctx, path, **given):
    media = ctx.probe(path, "image")
    return ConvertImage().run([media], params_for(TOOL, **given), ctx)[0]


def srgb_icc():
    return ImageCms.ImageCmsProfile(ImageCms.createProfile("sRGB")).tobytes()


def exif_with(model="Test camera", orientation=None):
    exif = Image.Exif()
    exif[MODEL] = model
    exif.get_ifd(EXIF_IFD)[TAKEN] = "2026:11:13 10:00:00"
    exif.get_ifd(GPS_IFD)[LATITUDE_REF] = "N"
    if orientation is not None:
        exif[ORIENTATION] = orientation
    return exif.tobytes()


IMAGE_CASES = [
    (fmt, source)
    for fmt in sorted(PILLOW_FORMATS)
    for source in ("photo.jpg", "drawing.webp", "still.gif", "scan.bmp", "logo.png")
    if not (fmt == "png" and source.endswith(".png"))
]


@pytest.mark.parametrize("fmt,source", IMAGE_CASES)
def test_each_format_comes_out_with_its_extension_kind_and_encoding(ctx, source_dir, fmt, source):
    path = make_image(source_dir / source, size=(40, 30))

    result = convert(ctx, path, format=fmt)

    assert result.kind == "image" and result.path.suffix == SUFFIXES[fmt]
    assert result.path.suffix in upload_formats()["image"]
    with Image.open(result.path) as written:
        assert written.format == PILLOW_FORMATS[fmt]
        assert written.size == (40, 30)
    assert result.path.parent == ctx.scratch_dir


@pytest.mark.parametrize("fmt", ["jpeg", "webp"])
def test_small_is_lighter_than_balanced_and_balanced_than_high(ctx, source_dir, fmt):
    path = noisy_image(source_dir / "noise.png")

    sizes = [convert(ctx, path, format=fmt, quality=level).path.stat().st_size for level in ("high", "balanced", "small")]

    assert sizes[0] > sizes[1] > sizes[2]


def test_jpeg_high_keeps_full_colour_resolution_and_the_others_halve_it(ctx, source_dir):
    path = noisy_image(source_dir / "noise.png")

    high = convert(ctx, path, format="jpeg", quality="high")
    small = convert(ctx, path, format="jpeg", quality="small")

    with Image.open(high.path) as image:
        assert image.layer[0][1:3] == image.layer[1][1:3] == (1, 1)
    with Image.open(small.path) as image:
        assert image.layer[0][1:3] == (2, 2)


@pytest.mark.parametrize("size,limit,expected", [((400, 100), 256, (256, 64)), ((100, 400), 256, (64, 256)), ((120, 90), 640, (120, 90))])
def test_the_largest_side_shrinks_and_never_enlarges(ctx, source_dir, size, limit, expected):
    path = make_image(source_dir / "wide.jpg", size=size)
    params = {"format": "webp", "quality": "balanced", "max_side": limit, "keep_metadata": True}

    result = ConvertImage().run([ctx.probe(path, "image")], params, ctx)[0]

    assert (result.width, result.height) == expected
    with Image.open(result.path) as image:
        assert image.size == expected


def test_a_listed_size_shrinks_a_large_picture(ctx, source_dir):
    path = make_image(source_dir / "big.png", size=(1500, 700))

    result = convert(ctx, path, format="png", max_side=640)

    assert (result.width, result.height) == (640, 299)


def test_transparency_becomes_the_chosen_background_in_jpeg(ctx, source_dir):
    image = Image.new("RGBA", (20, 10), (0, 0, 0, 0))
    image.paste((255, 0, 0, 255), (0, 0, 10, 10))
    path = source_dir / "half.png"
    image.save(path)

    result = convert(ctx, path, format="jpeg", quality="high", background="#00ff00")

    with Image.open(result.path) as written:
        assert written.mode == "RGB"
        green = written.getpixel((15, 5))
        red = written.getpixel((4, 5))
    assert green[1] > 240 and green[0] < 15 and green[2] < 15
    assert red[0] > 240 and red[1] < 15


@pytest.mark.parametrize("fmt", ["png", "webp"])
def test_transparency_stays_in_png_and_webp(ctx, source_dir, fmt):
    path = make_image(source_dir / "clear.gif", mode="RGBA", color=(0, 0, 255, 0))

    result = convert(ctx, path, format=fmt)

    assert result.has_alpha
    with Image.open(result.path) as written:
        assert written.convert("RGBA").getpixel((1, 1))[3] == 0


def test_a_png_is_not_converted_to_png_without_a_new_size(ctx, source_dir):
    path = make_image(source_dir / "logo.png")

    with pytest.raises(ToolFailed, match="already a PNG"):
        convert(ctx, path, format="png")


def test_a_jpeg_can_be_compressed_again_as_jpeg(ctx, source_dir):
    path = noisy_image(source_dir / "photo.jpg", quality=98)

    result = convert(ctx, path, format="jpeg", quality="small")

    assert result.path.stat().st_size < path.stat().st_size


def test_an_animated_image_is_refused_with_its_frame_count(ctx, source_dir):
    frames = [Image.new("RGB", (16, 16), color) for color in ("red", "green", "blue")]
    path = source_dir / "loop.gif"
    frames[0].save(path, save_all=True, append_images=frames[1:], duration=100, loop=0)

    with pytest.raises(ToolFailed, match=r"animated \(3 frames\)"):
        convert(ctx, path, format="png")


def test_an_svg_drawing_is_refused_with_a_clear_message(ctx, source_dir):
    path = source_dir / "icon.svg"
    path.write_text('<svg xmlns="http://www.w3.org/2000/svg" width="8" height="8"/>', encoding="utf-8")
    media = ctx.probe(make_image(source_dir / "stand-in.png"), "image").with_changes(path=path)

    with pytest.raises(ToolFailed, match="PNG, JPEG, WebP, GIF and BMP images only"):
        ConvertImage().run([media], params_for(TOOL, format="png"), ctx)


def test_kept_metadata_carries_exif_and_applies_the_orientation(ctx, source_dir):
    path = make_image(source_dir / "turned.jpg", size=(40, 20), exif=exif_with(orientation=6))

    for fmt in ("png", "jpeg", "webp"):
        result = convert(ctx, path, format=fmt, keep_metadata=True)
        with Image.open(result.path) as written:
            exif = written.getexif()
            assert written.size == (20, 40)
            assert exif.get(MODEL) == "Test camera"
            assert exif.get(ORIENTATION) in (None, 1)
            assert exif.get_ifd(EXIF_IFD).get(TAKEN) == "2026:11:13 10:00:00"
            assert exif.get_ifd(GPS_IFD).get(LATITUDE_REF) == "N"


def test_metadata_off_drops_exif_and_still_applies_the_orientation(ctx, source_dir):
    path = make_image(source_dir / "turned.jpg", size=(40, 20), exif=exif_with(orientation=6))

    for fmt in ("png", "jpeg", "webp"):
        result = convert(ctx, path, format=fmt, keep_metadata=False)
        with Image.open(result.path) as written:
            assert written.size == (20, 40)
            assert MODEL not in written.getexif()


@pytest.mark.parametrize("keep", [True, False])
def test_the_colour_profile_is_always_kept(ctx, source_dir, keep):
    icc = srgb_icc()
    path = make_image(source_dir / "profiled.png", icc_profile=icc)

    for fmt in ("jpeg", "webp"):
        result = convert(ctx, path, format=fmt, keep_metadata=keep)
        with Image.open(result.path) as written:
            assert written.info.get("icc_profile") == icc


def test_a_cmyk_profile_is_not_put_on_the_rgb_result(ctx, source_dir):
    cmyk_header = bytes(16) + b"CMYK" + bytes(108)
    path = source_dir / "print.jpg"
    Image.new("CMYK", (16, 16), (0, 100, 200, 0)).save(path, icc_profile=cmyk_header)

    result = convert(ctx, path, format="png")

    with Image.open(result.path) as written:
        assert written.mode == "RGB"
        assert "icc_profile" not in written.info


@pytest.mark.parametrize("keep,expected", [(True, "steps: 30"), (False, None)])
def test_png_text_such_as_generation_parameters_goes_from_png_to_png(ctx, source_dir, keep, expected):
    info = PngImagePlugin.PngInfo()
    info.add_text("parameters", "steps: 30")
    path = make_image(source_dir / "render.png", size=(800, 600), pnginfo=info)

    result = convert(ctx, path, format="png", max_side=640, keep_metadata=keep)

    with Image.open(result.path) as written:
        assert written.text.get("parameters") == expected


def test_a_sixteen_bit_png_keeps_its_brightness_in_jpeg(ctx, source_dir):
    path = source_dir / "deep.png"
    Image.new("I;16", (16, 16), 32768).save(path)

    result = convert(ctx, path, format="jpeg", quality="high")

    with Image.open(result.path) as written:
        assert 120 <= written.convert("L").getpixel((8, 8)) <= 136


def test_a_palette_image_is_resized_smoothly(ctx, source_dir):
    image = Image.linear_gradient("L").resize((2000, 2000)).convert("P")
    path = source_dir / "palette.gif"
    image.save(path)

    result = convert(ctx, path, format="png", max_side=640)

    with Image.open(result.path) as written:
        assert written.mode in ("RGB", "L")
        assert written.size == (640, 640)


def test_a_cancelled_run_writes_nothing(tmp_path, source_dir):
    path = make_image(source_dir / "photo.jpg")
    context = ToolContext(tmp_path / "scratch", is_cancelled=lambda: True)

    with pytest.raises(ToolCancelled):
        ConvertImage().run([context.probe(path, "image")], params_for(TOOL, format="png"), context)

    scratch = tmp_path / "scratch"
    assert not scratch.exists() or not any(scratch.iterdir())


def test_the_result_is_the_only_file_written(ctx, source_dir):
    path = make_image(source_dir / "photo.jpg")

    convert(ctx, path, format="webp")

    assert [entry.suffix for entry in ctx.scratch_dir.iterdir()] == [".webp"]
