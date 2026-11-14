from src.plugin_api.media_tools import MediaTool

from .audio import encode_audio


class ExtractAudio(MediaTool):
    def run(self, inputs, params, ctx):
        return [encode_audio(media, params, ctx, from_video=True) for media in inputs]
