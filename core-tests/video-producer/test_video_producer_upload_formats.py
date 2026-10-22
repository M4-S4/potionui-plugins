import re
from pathlib import Path

import pytest

from src.platform.filesystem.audio_formats import AUDIO_EXTENSIONS
from src.platform.filesystem.visual_formats import IMAGE_EXTENSIONS, VIDEO_EXTENSIONS

UPLOAD_JS = Path(__file__).resolve().parents[3] / "content" / "plugins" / "marketplace" / "video-producer" / "frontend" / "src" / "lib" / "upload.js"
LEFT_OUT = {"image": {".svg"}, "video": set(), "audio": set()}
HOST = {"image": IMAGE_EXTENSIONS, "video": VIDEO_EXTENSIONS, "audio": AUDIO_EXTENSIONS}


def _plugin_extensions():
    source = UPLOAD_JS.read_text(encoding="utf-8")
    block = re.search(r"export const UPLOAD_EXTENSIONS = \{(.*?)\n\};", source, re.S).group(1)
    return {kind: set(re.findall(r"'(\.[a-z0-9]+)'", values)) for kind, values in re.findall(r"(\w+): \[([^\]]*)\]", block)}


@pytest.mark.parametrize("kind", sorted(HOST))
def test_the_page_offers_the_extensions_potionui_accepts_for_each_kind(kind):
    assert _plugin_extensions()[kind] == set(HOST[kind]) - LEFT_OUT[kind]


def test_the_page_lists_no_other_kind():
    assert set(_plugin_extensions()) == set(HOST)
