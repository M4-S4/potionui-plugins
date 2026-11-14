# Media Converter

Media Converter adds four tools to the **Tools** menu of the Library and of the History in PotionUI, under **Edit**, where the menu names them with "Media Convert" below each tool:

| Tool | Takes | Makes |
|---|---|---|
| **Convert image** | an image | PNG, JPEG or WebP |
| **Convert video** | a video | MP4 (H.264), MOV (H.264) or WebM (VP9) |
| **Convert sound** | a sound | WAV, MP3, FLAC, M4A (AAC) or OGG (Opus) |
| **Extract sound** | a video with sound | WAV, MP3, FLAC, M4A (AAC) or OGG (Opus) |

The result is a new item in the Library, next to the original, which stays as it was. It keeps the name of the original with the extension of the new format: `Cat.png` converted to WebP becomes `Cat.webp`. A file of a generation keeps the name it has in the History. Select several items and run a tool once to convert them all in one run; if one of them is refused, the whole run fails and none of them is saved. Two sources with the same name, such as `Cat.png` and `Cat.webp` converted to JPEG, give two items both named `Cat.jpg`.

The tool window always saves a new item and never offers to replace the original. A request from the chat, the automation or the API can still ask PotionUI to replace an image, a video or a sound by its conversion; the item then keeps its old name and extension over the new content (`Cat.png` holding a WebP picture), which a download or a zip export of the Library carries along. The chat asks before it replaces anything: answer no and ask for a new item instead.

The plugin has no page of its own: each tool opens the usual tool window of PotionUI with the settings below, filled with the values you used last. It needs ffmpeg and ffprobe on the server, which the PotionUI image ships, and nothing else.

## The tools

### Convert image

| Setting | Values |
|---|---|
| Format | PNG, JPEG (default), WebP |
| Quality | High, Balanced (default), Small. Hidden for PNG, which is lossless. |
| Largest side | Original size (default), 3840, 2560, 1920, 1280, 1024 or 640 px. A larger image is shrunk so that its longest side fits, in the same pass as the conversion; a smaller image keeps its size. |
| Background | The colour that fills transparent areas, white by default. Shown for JPEG only, since JPEG has no transparency. |
| Keep metadata | On by default. |

It reads PNG, JPEG, WebP, GIF and BMP images of up to 67 million pixels, such as 8192 × 8192. The orientation that a camera writes in the EXIF data is applied to the picture, so the result is upright everywhere.

### Convert video

| Setting | Values |
|---|---|
| Format | MP4 (H.264) (default), MOV (H.264), WebM (VP9) |
| Quality | High, Balanced (default), Small |
| Largest side | Original size (default), 3840, 2560, 1920, 1280, 1024 or 640 px, never larger than the original. |
| Keep metadata | On by default. |

It takes videos of up to 4096 × 2304 pixels (about 9.4 million, which covers 4K). The picture and the sound are always encoded again, even when the source already has the format you pick: converting an MP4 to MP4 at Small makes a lighter copy. The frame rate and the length stay those of the source. The picture comes out in 8-bit 4:2:0 colour, which every browser plays. Width and height are rounded down to even numbers, which H.264 needs. A rotation stored in the file is applied to the picture.

### Convert sound

| Setting | Values |
|---|---|
| Format | WAV, MP3 (default), FLAC, M4A (AAC), OGG (Opus) |
| Quality | High, Balanced (default), Small. Hidden for WAV and FLAC, which are lossless. |
| Keep metadata | On by default. |

### Extract sound

The same settings as **Convert sound**, with M4A as the default format. It takes the first sound track of the video.

## Quality

The three steps stand for these encoder settings. Small files lose more detail; the differences between High and Balanced are hard to hear or see on most sources.

| Format | Encoder | High | Balanced | Small |
|---|---|---|---|---|
| JPEG | Pillow | quality 95, full colour resolution | quality 85 | quality 72 |
| WebP | Pillow (libwebp) | quality 92 | quality 80 | quality 65 |
| PNG | Pillow, compression level 6 | lossless | lossless | lossless |
| MP4, MOV picture | libx264, preset `medium`, 8-bit 4:2:0 | CRF 18 | CRF 23 | CRF 28 |
| MP4, MOV sound | aac | 192 kbit/s | 160 kbit/s | 128 kbit/s |
| WebM picture | libvpx-vp9, `-cpu-used 4`, 8-bit 4:2:0 | CRF 27 | CRF 32 | CRF 37 |
| WebM sound | libopus | 160 kbit/s | 128 kbit/s | 96 kbit/s |
| MP3 | libmp3lame, variable bitrate | `-q:a 0` | `-q:a 2` | `-q:a 5` |
| M4A | aac | 256 kbit/s | 192 kbit/s | 128 kbit/s |
| OGG | libopus | 160 kbit/s | 128 kbit/s | 96 kbit/s |
| WAV | PCM, 16 bits, or 24 bits for a deeper source | lossless | lossless | lossless |
| FLAC | flac, compression level 5 | lossless | lossless | lossless |

## What is kept and what is lost

**Keep metadata** is on by default. Turn it off before you share a photo or a video taken with a phone: the place where it was taken is kept otherwise.

| Converting | With **Keep metadata** on | With it off | Always lost |
|---|---|---|---|
| An image | EXIF data (camera, date, place), with the orientation set to normal; the text chunks of a PNG, such as generation parameters, when the result is a PNG too | No EXIF data, no text chunks | Animation (animated images are refused); XMP data, except from PNG to PNG; the text chunks of a PNG when the result is JPEG or WebP; EXIF data longer than 64 KB when the result is a JPEG, which cannot hold it; transparency in JPEG (filled with the background colour); 16 bits per channel (the result has 8) |
| An image's colour profile | Kept | Kept | A profile that does not match the result's colours, such as a CMYK profile on a picture converted to RGB; a profile larger than 1 MB, or one whose declared length does not match its bytes |
| A video | Title and other tags, the place where it was filmed (in MP4, MOV and WebM alike), chapters, the first eight sound tracks with their language, text subtitles (as `mov_text` in MP4 and MOV, WebVTT in WebM) | Only the picture and the first sound track, no tags, no place, no chapters, no subtitles | Picture subtitles (DVD, Blu-ray), attached files, data tracks; sound tracks after the eighth; HDR and 10-bit colour (the result is 8-bit SDR, without tone mapping, so an HDR source can look flat); more than two sound channels in WebM (mixed down to stereo) |
| A sound | Title, artist and the other tags | No tags | Cover art; more than two channels in MP3 and OGG (mixed down to stereo); sample rates above 48 kHz in MP3 (it goes up to 48 kHz) and every rate other than 48 kHz in OGG (Opus works at 48 kHz) |
| The sound of a video | The tags of the video, such as its title | No tags | Every sound track after the first |

ffmpeg writes its own name and version in every video and sound it makes, whatever the switch says.

## When a tool refuses

The tool window shows the reason, and nothing is added to the Library.

| Case | What happens |
|---|---|
| An animated GIF or WebP | Refused: "This image is animated (N frames); Media Converter converts still images only". |
| An SVG drawing | The Library accepts SVG files but PotionUI cannot read them as pictures: the run ends with "This image cannot be read". |
| An image larger than 67 million pixels | Refused with its size and the limit. Media Converter reads only the size written in the file and does not decode the picture. |
| A PNG converted to PNG with the same size | Refused, since nothing would change. With a largest side smaller than the picture, it is shrunk. |
| A WAV converted to WAV, a FLAC to FLAC | Refused, since nothing would change. A JPEG, WebP, MP3, M4A or OGG file can be converted to its own format to make it lighter. |
| A video larger than 4096 × 2304 pixels | Refused before any encoding, with its size and the limit. |
| A video whose picture grows past 4096 × 2304 pixels partway through | The larger pictures are not decoded and are left out of the result. |
| A video thinner than 2 pixels, or one that a largest side would make so | Refused. |
| A video without sound given to **Extract sound** | The menu offers the tool, since the Library does not record whether an uploaded video has sound; the run ends with "Extract sound needs a video with sound". |
| A sound with no samples | Refused: "This sound is empty: there is nothing to convert". |
| A video or sound longer than the limit the admin set | Refused before any encoding when the file, or any of its tracks, states a longer length. A file that states no length, or a shorter one than it has, is encoded up to the limit plus one second, then refused. Half a second over the limit is let through, since encoders add a few milliseconds. |
| A result that would weigh more than one conversion or one run may write, more than the server can hold, or more than is left of the user's storage | Refused with what to do: choose a lighter format, convert fewer items at a time, free some space, or try again later or ask an admin when the server is short of disk space (see Load on the server). A WAV of known length is refused before encoding, since its size is known in advance; any other sound, and a video, is stopped as soon as it reaches the limit, then refused; an image is written whole, then refused, and nothing is added to the Library. |
| A transparent image converted to JPEG | Converted, with transparent areas filled with the background colour. |
| A cancelled run | The encoder stops at once and nothing is published. |

## For admins

### Settings

In **Admin › Plugins › Media Converter**:

| Setting | Default | What it does |
|---|---|---|
| ffmpeg threads per conversion | 4 | How many processor threads one video or sound conversion may use, from 1 to 16. |
| Longest video or sound, in minutes | 30 | Longer files are refused with a message, from 1 to 30 minutes. |

PotionUI stops any single encoding after 30 minutes of work, with "Editing timed out", so the length limit cannot go beyond 30 minutes. Sound converts in seconds, but a long video in 4K at High quality can take longer to encode than it lasts: if such runs time out, pick a largest side, raise the thread count, or lower the length limit.

Any signed-in user can run the tools. To turn them off for everyone, disable the plugin.

### Load on the server

Conversions run on the server's processor and never use the graphics card: no hardware encoder is used, so a generation keeps the whole card. Each video or sound conversion uses at most the number of threads set above; the slowest encoder setting used is libx264's `medium` preset. A long video still takes the processor for a while and slows down the preparation of a generation that starts meanwhile: lower the thread count if that matters on your server.

Each run is bounded:

- an image of 67 million pixels takes up to about 1.6 GB of memory while it converts (WebP takes the most), which is why larger ones are refused;
- a 4K video takes about 2 GB of memory in ffmpeg, which is why larger ones are refused;
- ffmpeg stops at the length limit plus one second, even when a file does not state its length;
- one sound conversion writes at most what its sound can fill in the length limit: sample rate × channels × sample size × the limit, plus 2 %, and never less than 64 kB per second for MP3, M4A and OGG. A stereo WAV at 44.1 kHz may weigh up to about 325 MB with the 30-minute limit, whatever the size of its source. A sound that neither PotionUI nor ffprobe can find a length for gets no more than a video conversion would: 32 times the size of its source, never less than 1 GB;
- one video conversion writes at most 32 times the size of its source, never less than 1 GB; no conversion writes more than 4 GB;
- one run writes at most 8 GB, every item and every step of a chain together, counting what PotionUI's own tools wrote earlier in the chain; a conversion that would go past it is refused with a message that asks to convert fewer items at a time;
- Media Converter keeps 2 GB free on the disk where PotionUI keeps its working files. When a conversion starts, Media Converter takes out of the free space these 2 GB and the room it gave to its other conversions that are still running, less what they have written so far in their working folders, and gives the new conversion at most half of what is left; with too little left, it refuses. A room stops counting when its conversion ends, whether it finished, was refused, was cancelled or failed. So the conversions of Media Converter, however many run at once and in whatever order they start, stay out of these 2 GB together, except for what a video or sound conversion writes past its room before ffmpeg stops: about one encoded frame and the end of the file, which can reach about ten megabytes for a large video (up to 4 MB in MP4 and 11 MB in WebM in our tests, on a 4096 × 2304 video full of fine detail). The reserve does not hold against anything else that writes to the disk meanwhile: Media Converter counts only its own conversions. It counts them in the memory of the PotionUI process that runs them, so two PotionUI processes that share a disk do not see each other's conversions, and it counts every conversion it runs, whatever disk it writes to, so a server with working folders on several disks may refuse earlier than it needs to. When Media Converter refuses for lack of disk space, the user is asked to try again later or ask an admin, and the server log gives the space that was free, the 2 GB kept, the room promised to conversions still running, and the room the conversion had and needed;
- when a user's plan limits their storage or the size of one file, Media Converter reads these limits before each conversion, and a result that would not fit is refused: before encoding for a WAV of known length, as soon as it reaches the limit for any other sound and for a video, and once written for an image, which is then not added to the Library. If the plan cannot be read, the conversion goes on bounded by the rest of this list, and the server log says which limit could not be read.

The results count toward each user's storage, as uploads do. A WAV or a PNG can weigh much more than its source.

ffmpeg reads only the file it converts: the command allows local files only, a fixed list of container formats, and an absolute path, so a playlist or a concat list disguised as a video is refused. No text typed by a user reaches the command line: every setting is a choice from a list or a switch.

### Installing and updating

Install it from the catalogue of this repository, then enable it in **Admin › Plugins**; its tools appear in the Tools menus at once. Unless the notes of a version say otherwise, restart PotionUI after an update from the catalogue.

Updating from 0.1.0 to 0.1.1 needs its own order: disable Media Converter in **Admin › Plugins**, restart PotionUI, update it from the catalogue, then enable it. Tried in another order, the tools of 0.1.1 did not load: the update or the enabling ended with an error, and Media Converter stayed on 0.1.0 or without its tools. If that happens, start again from the first step, and skip the update step if the catalogue already shows 0.1.1 installed.

From chat, MCP and automation, PotionUI offers these tools like its own. A run from chat is cancelled after ten minutes and an automation node waits five minutes by default, so convert long videos from the Library.

## Not in this version

- GIF and animated WebP made from a video, and the conversion of animated images.
- A target file size ("make it fit in 25 MB").
- H.265, AV1, AVIF, HEIC, JPEG XL and Opus in `.opus` files: PotionUI's Library does not accept these files yet, or plays them badly.
- Copying the sound or the picture without encoding it again, such as a MOV to MP4 change of container.
- Keeping the cover art of a sound file.
- The tool in the media field of a generation form.
- Photos above 67 million pixels, such as the 108 and 200 megapixel photos of some phones and large panoramas, and videos above 4096 × 2304 pixels, such as 5.7K and 8K: they are refused.

## License

GPL-3.0, like the other plugins of this repository.
