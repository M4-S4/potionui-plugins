from PIL import Image, ImageOps, PngImagePlugin, UnidentifiedImageError

from src.plugin_api.media_tools import MediaTool, ToolFailed

from .common import (
    IMAGE_FORMATS,
    JPEG_QUALITY,
    PNG_COMPRESSION,
    WEBP_QUALITY,
    fit,
    guard,
    max_side,
    quality,
)

READABLE = ("PNG", "JPEG", "WEBP", "GIF", "BMP")
ORIENTATION = 0x0112
ICC_SPACES = {b"RGB ": ("RGB", "RGBA"), b"GRAY": ("L", "LA"), b"CMYK": ("CMYK",)}


def parse_color(value) -> tuple[int, int, int]:
    text = str(value or "#ffffff").lstrip("#")
    if len(text) == 3:
        text = "".join(ch * 2 for ch in text)
    try:
        return int(text[0:2], 16), int(text[2:4], 16), int(text[4:6], 16)
    except ValueError:
        return 255, 255, 255


def icc_fits(icc, mode: str) -> bool:
    if not icc or len(icc) < 20:
        return False
    return mode in ICC_SPACES.get(bytes(icc[16:20]), ())


def has_alpha(image: Image.Image) -> bool:
    keyed = image.mode in ("P", "L", "RGB") and "transparency" in image.info
    return image.mode in ("RGBA", "LA", "PA", "RGBa", "La") or keyed


def to_eight_bits(image: Image.Image) -> Image.Image:
    if image.mode in ("I;16", "I;16B", "I;16L", "I;16N", "I"):
        return image.convert("I").point(lambda value: value * (1 / 256)).convert("L")
    if image.mode == "F":
        return image.convert("L")
    return image


def normalize(image: Image.Image) -> Image.Image:
    image = to_eight_bits(image)
    if image.mode == "P":
        return image.convert("RGBA" if has_alpha(image) else "RGB")
    if image.mode == "1":
        return image.convert("L")
    if image.mode in ("L", "RGB") and has_alpha(image):
        return image.convert("LA" if image.mode == "L" else "RGBA")
    if image.mode in ("RGB", "RGBA", "L", "LA", "CMYK"):
        return image
    return image.convert("RGBA" if has_alpha(image) else "RGB")


def prepare(image: Image.Image, fmt: str, background) -> Image.Image:
    alpha = has_alpha(image)
    if fmt == "jpeg":
        if alpha:
            rgba = image.convert("RGBA")
            canvas = Image.new("RGB", rgba.size, parse_color(background))
            canvas.paste(rgba, mask=rgba.getchannel("A"))
            return canvas
        return image if image.mode in ("RGB", "L", "CMYK") else image.convert("RGB")
    if fmt == "webp":
        if alpha:
            return image if image.mode == "RGBA" else image.convert("RGBA")
        return image if image.mode == "RGB" else image.convert("RGB")
    return image.convert("RGB") if image.mode == "CMYK" else image


def exif_bytes(source: Image.Image) -> bytes | None:
    exif = source.getexif()
    if not exif:
        return None
    if ORIENTATION in exif:
        exif[ORIENTATION] = 1
    return exif.tobytes()


def png_text(source: Image.Image) -> PngImagePlugin.PngInfo | None:
    texts = {key: value for key, value in (getattr(source, "text", None) or {}).items() if isinstance(value, str)}
    if not texts:
        return None
    info = PngImagePlugin.PngInfo()
    for key, value in texts.items():
        info.add_itxt(key, value)
    return info


def save_options(source: Image.Image, image: Image.Image, fmt: str, level: str, keep: bool) -> dict:
    options: dict = {}
    icc = source.info.get("icc_profile")
    if icc_fits(icc, image.mode):
        options["icc_profile"] = icc
    if keep:
        exif = exif_bytes(source)
        if exif:
            options["exif"] = exif
        if fmt == "png" and source.format == "PNG":
            text = png_text(source)
            if text is not None:
                options["pnginfo"] = text
    if fmt == "jpeg":
        options.update(quality=JPEG_QUALITY[level], optimize=True, subsampling=0 if level == "high" else 2)
    elif fmt == "webp":
        options.update(quality=WEBP_QUALITY[level], method=4)
    else:
        options.update(compress_level=PNG_COMPRESSION)
    return options


class ConvertImage(MediaTool):
    def run(self, inputs, params, ctx):
        return [self.convert(media, params, ctx) for media in inputs]

    def convert(self, media, params, ctx):
        fmt = params.get("format") or "jpeg"
        if fmt not in IMAGE_FORMATS:
            raise ToolFailed(f"Media Converter cannot write {fmt} images")
        level = quality(params)
        limit = max_side(params)
        keep = bool(params.get("keep_metadata", True))
        guard(ctx)
        try:
            source = Image.open(media.path, formats=READABLE)
        except (UnidentifiedImageError, OSError) as exc:
            raise ToolFailed("Media Converter reads PNG, JPEG, WebP, GIF and BMP images only") from exc
        except Image.DecompressionBombError as exc:
            raise ToolFailed("This image is too large to convert") from exc
        with source:
            frames = getattr(source, "n_frames", 1)
            if frames > 1:
                raise ToolFailed(
                    f"This image is animated ({frames} frames); Media Converter converts still images only"
                )
            if fmt == "png" and source.format == "PNG" and not limit:
                raise ToolFailed("This image is already a PNG; choose another format or a maximum size")
            try:
                source.load()
            except (OSError, Image.DecompressionBombError) as exc:
                raise ToolFailed("This image cannot be read") from exc
            image = normalize(ImageOps.exif_transpose(source))
            if limit:
                width, height = fit(image.width, image.height, limit, even=False)
                if (width, height) != image.size:
                    image = image.resize((width, height), Image.Resampling.LANCZOS)
            image = prepare(image, fmt, params.get("background"))
            image.info = {}
            options = save_options(source, image, fmt, level, keep)
            guard(ctx)
            out = ctx.new_path(IMAGE_FORMATS[fmt])
            image.save(out, format=fmt.upper(), **options)
        guard(ctx)
        return ctx.probe(out, "image")
