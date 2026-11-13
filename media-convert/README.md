# Media Converter

Media Converter adds four tools to the **Tools** menu of the Library and of the History in PotionUI:

| Tool | Takes | Makes |
|---|---|---|
| **Convert image** | an image | PNG, JPEG or WebP |
| **Convert video** | a video | MP4 (H.264), MOV (H.264) or WebM (VP9) |
| **Convert sound** | a sound | WAV, MP3, FLAC, M4A (AAC) or OGG (Opus) |
| **Extract sound** | a video with sound | WAV, MP3, FLAC, M4A (AAC) or OGG (Opus) |

The result is a new item in the Library, next to the original, which stays as it was. It keeps the name of the original with the extension of the new format: `Cat.png` converted to WebP becomes `Cat.webp`. Select several items and run a tool once to convert them all in one run. The tools never replace the original, because a replaced item would keep its old name and extension.

The plugin has no page of its own: each tool opens the usual tool window of PotionUI with the settings below. It needs ffmpeg and ffprobe on the server, which the PotionUI image ships, and nothing else.

## The tools

### Convert image

| Setting | Values |
|---|---|
| Format | PNG, JPEG (default), WebP |
| Quality | High, Balanced (default), Small. Hidden for PNG, which is lossless. |
| Largest side | Original size (default), 3840, 2560, 1920, 1280, 1024 or 640 px. A larger image is shrunk so that its longest side fits, in the same pass as the conversion; a smaller image keeps its size. |
| Background | The colour that fills transparent areas, white by default. Shown for JPEG only, since JPEG has no transparency. |
| Keep metadata | On by default. |

It reads PNG, JPEG, WebP, GIF and BMP images. The orientation that a camera writes in the EXIF data is applied to the picture, so the result is upright everywhere.

### Convert video

| Setting | Values |
|---|---|
| Format | MP4 (H.264) (default), MOV (H.264), WebM (VP9) |
| Quality | High, Balanced (default), Small |
| Largest side | Original size (default), 3840, 2560, 1920, 1280, 1024 or 640 px, never larger than the original. |
| Keep metadata | On by default. |

The picture and the sound are always encoded again, even when the source already has the format you pick: converting an MP4 to MP4 at Small makes a lighter copy. The frame rate and the length stay those of the source. Width and height are rounded down to even numbers, which H.264 needs. A rotation stored in the file is applied to the picture.

### Convert sound

| Setting | Values |
|---|---|
| Format | WAV, MP3 (default), FLAC, M4A (AAC), OGG (Opus) |
| Quality | High, Balanced (default), Small. Hidden for WAV and FLAC, which are lossless. |
| Keep metadata | On by default. |

### Extract sound

The same settings as **Convert sound**, with M4A as the default format. It takes the first sound track of the video. It is offered only for videos with sound.

## Quality

The three steps stand for these encoder settings. Small files lose more detail; the differences between High and Balanced are hard to hear or see on most sources.

| Format | Encoder | High | Balanced | Small |
|---|---|---|---|---|
| JPEG | Pillow | quality 95, full colour resolution | quality 85 | quality 72 |
| WebP | Pillow (libwebp) | quality 92 | quality 80 | quality 65 |
| PNG | Pillow | lossless | lossless | lossless |
| MP4, MOV picture | libx264, preset `medium` | CRF 18 | CRF 23 | CRF 28 |
| MP4, MOV sound | aac | 192 kbit/s | 160 kbit/s | 128 kbit/s |
| WebM picture | libvpx-vp9, `-cpu-used 4` | CRF 27 | CRF 32 | CRF 37 |
| WebM sound | libopus | 160 kbit/s | 128 kbit/s | 96 kbit/s |
| MP3 | libmp3lame, variable bitrate | `-q:a 0` | `-q:a 2` | `-q:a 5` |
| M4A | aac | 256 kbit/s | 192 kbit/s | 128 kbit/s |
| OGG | libopus | 160 kbit/s | 128 kbit/s | 96 kbit/s |
| WAV | PCM, 16 bits, or 24 bits for a deeper source | lossless | lossless | lossless |
| FLAC | flac, compression level 5 | lossless | lossless | lossless |

## What is kept and what is lost

| Converting | With **Keep metadata** on | With it off | Always lost |
|---|---|---|---|
| An image | EXIF data (camera, date, place), with the orientation set to normal; the text chunks of a PNG, such as generation parameters, when the result is a PNG too | No EXIF data, no text chunks | Animation (animated images are refused); XMP data, except from PNG to PNG; the text chunks of a PNG when the result is JPEG or WebP; transparency in JPEG (filled with the background colour); 16 bits per channel (the result has 8) |
| An image's colour profile | Kept | Kept | A profile that does not match the result's colours, such as a CMYK profile on a picture converted to RGB |
| A video | Title and other tags, chapters, every sound track with its language, text subtitles (as `mov_text` in MP4 and MOV, WebVTT in WebM) | Only the picture and the first sound track, no tags, no chapters, no subtitles | Picture subtitles (DVD, Blu-ray), attached files, data tracks; HDR and 10-bit colour (the result is 8-bit SDR, without tone mapping, so an HDR source can look flat); more than two sound channels in WebM (mixed down to stereo) |
| A sound | Title, artist and the other tags | No tags | Cover art; more than two channels in MP3 and OGG (mixed down to stereo); sample rates other than 48 kHz in OGG (Opus works at 48 kHz) |
| The sound of a video | The tags of the video, such as its title | No tags | Every sound track after the first |

## When a tool refuses

The tool window shows the reason, and nothing is added to the Library.

| Case | What happens |
|---|---|
| An animated GIF or WebP | Refused: "This image is animated (N frames); Media Converter converts still images only". |
| An SVG drawing, or a file that is not a PNG, JPEG, WebP, GIF or BMP image | Refused with the list of the image formats it reads. |
| A PNG converted to PNG at its original size | Refused, since nothing would change. With a largest side, it is shrunk. |
| A WAV converted to WAV, a FLAC to FLAC | Refused, since nothing would change. A JPEG, WebP, MP3, M4A or OGG file can be converted to its own format to make it lighter. |
| A video without sound given to **Extract sound** | The tool is not offered for it; a run asked through the API or the chat ends with "Extract sound needs a video with sound". |
| A video or sound longer than the limit the admin set | Refused before any encoding, with its length and the limit. |
| A transparent image converted to JPEG | Converted, with transparent areas filled with the background colour. |
| A cancelled run | The encoder stops at once and nothing is published. |

## For admins

### Settings

In **Admin › Plugins › Media Converter**:

| Setting | Default | What it does |
|---|---|---|
| ffmpeg threads per conversion | 4 | How many processor threads one video or sound conversion may use, from 1 to 16. |
| Longest video or sound, in minutes | 60 | Longer files are refused with a message, from 1 to 600 minutes. |

Any signed-in user can run the tools. To turn them off for everyone, disable the plugin.

### Load on the server

Conversions run on the server's processor and never use the graphics card: no hardware encoder is used, so a generation keeps the whole card. PotionUI runs at most two tool runs at once on the server, and each video or sound conversion uses at most the number of threads set above; the slowest encoder setting used is libx264's `medium` preset. A long video still takes the processor for a while and slows down the preparation of a generation that starts meanwhile: lower the thread count if that matters on your server.

The results count toward each user's storage, as uploads do. A WAV or a PNG can weigh much more than its source; when a user's storage is full, the run fails at the end, and nothing is kept.

ffmpeg reads only the file it converts: the command allows local files only, a fixed list of container formats, and an absolute path. No text typed by a user reaches the command line: every setting is a choice from a list or a switch.

### Installing and updating

Install it from the catalogue of this repository, then enable it in **Admin › Plugins**; its tools appear in the Tools menus at once. After an update from the catalogue, restart PotionUI: the server keeps running the code of the version it had loaded until it restarts.

From chat, MCP and automation, PotionUI offers these tools like its own. A run from chat is cancelled after ten minutes, so convert long videos from the Library.

## Not in this version

- GIF and animated WebP made from a video, and the conversion of animated images.
- A target file size ("make it fit in 25 MB").
- H.265, AV1, AVIF, HEIC, JPEG XL and Opus in `.opus` files: PotionUI's Library does not accept these files yet, or plays them badly.
- Copying the sound or the picture without encoding it again, such as a MOV to MP4 change of container.
- Keeping the cover art of a sound file.
- The tool in the media field of a generation form.

## License

GPL-3.0, like the other plugins of this repository.
