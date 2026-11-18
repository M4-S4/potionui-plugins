# Media Converter: reference

Every setting of the six tools, the encoder settings behind each quality, what a conversion keeps and loses, every refusal, the admin settings and the load on the server. The [README](https://github.com/M4-S4/potionui-plugins/blob/main/media-convert/README.md), also in Admin › Documentation as "Media Converter", gives the short version.

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
| Format | MP4 (H.264) (default), MOV (H.264), WebM (VP9), MP4 (H.265). MP4 (H.265) is refused while the admin setting that allows it is off. |
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

### Make an animation

| Setting | Values |
|---|---|
| Format | GIF (default), Animated WebP |
| Start | Where the animation starts in the video, in seconds, 0 by default. |
| Length | 10 seconds by default, from 0.5 to 30. The animation stops at the end of the video if it comes first. |
| Largest side | 640, 480 (default) or 320 px. A smaller video keeps its size. |
| Frame rate | Like the video, 25 per second at most (default); Half; A third. |
| Quality | High, Balanced (default), Small |

The first step is the video's frame rate divided by the smallest whole number that brings it to 25 per second or less: 16 stays 16, 24 stays 24, 30 gives 15 and 60 gives 20. Half and A third divide that rate again by 2 and 3, so the result keeps evenly spaced frames of the video. A video whose frame rate cannot be read is taken at 12 frames per second.

The result is a GIF or an animated WebP that loops forever, with no sound. A GIF is made in two steps: ffmpeg first reads the chosen part of the video to work out a palette of colours, saved as a small PNG in the working folder, then reads it again to write the GIF with that palette; the PNG is deleted afterwards. The palette keeps no transparent colour, so the GIF is opaque. An animated WebP is written in one step; the WebP encoder may draw a frame over the one before and leave transparent the areas that do not change, and the file is then marked as transparent although every frame it shows is opaque, so a tool or a viewer that reads that mark may treat it as a transparent picture. In our tests, the WebP of a test pattern was marked so, and the WebP of grainy footage, whose every frame changes everywhere, was not. The length limit of the admin settings does not apply: the tool reads 30 seconds at most, wherever they are in the video.

A GIF grows fast with grain and movement. In our tests, 15 seconds at 480 px weighed about 5 MB from a clean video and 23 MB from a grainy one, and 16 seconds of grainy footage at 640 px and High weighed 47 MB; the same in animated WebP weighed 2 to 16 times less. For a light GIF, pick 320 px, Half or A third, or the animated WebP.

### Lighten for sending

| Setting | Values |
|---|---|
| Largest size | 8 MB, 16 MB (default), 18 MB, 20 MB, 30 MB, 50 MB, counted in millions of bytes. |
| Keep the sound | On by default. Off, the result has no sound. |
| Keep metadata | Off by default. |

The result is an MP4 in H.264 (`libx264`, preset `medium`, 8-bit 4:2:0, High profile) with AAC sound and the index at the start of the file, so that it starts to play before it is fully downloaded. It is worked out this way:

1. The length is that of what is kept: the picture, and the sound when Keep the sound is on, whichever lasts longer. The budget is the chosen size less 4 %, spread over that length.
2. The sound gets 128 kbit/s when the whole file may use 1000 kbit/s or more, 96 kbit/s from 500, 64 kbit/s below, and never more than the sound of the source. More than two channels are mixed down to stereo.
3. The picture gets the rest. Its size is the largest of the original size, 1920, 1280, 960, 640 and 480 px on the longest side, never larger than the original, that still gives each pixel of each frame 0.04 bit of what the chosen size allows; below that, 480 px.
4. If the picture would get less than 150 kbit/s, the size is refused before anything is encoded, with the smallest size that would work for this length: 150 kbit/s for the picture and the sound the source would get at that size (64 kbit/s, or less when the sound of the source is lighter), plus the 4 %, rounded up to the next whole megabyte.
5. A video already lighter than the chosen size gets no more bitrate than its own, less 4 %, when its picture is H.264, and no more than one and a half times its own, less 4 %, in another format: the size of the picture still follows the chosen size, only the bitrate is bounded.
6. The picture is encoded in two passes: the first one reads the whole video and writes its statistics in the working folder, the second one uses them to spread the bitrate where the picture needs it. The statistics files are deleted afterwards, and so is a result left half written by a cancelled run.
7. The file written is measured. When it reaches the chosen size, or weighs exactly that, the second pass runs once more with the bitrate lowered by the excess; when it still reaches it, the tool refuses.

The two passes usually land about 4 % under the chosen size. At the lowest bitrates they come closer to it: 0.8 % under it in our tests, for a 10-minute video at 15 MB with its picture near 150 kbit/s.

Only the result counts against the storage left to the user and against the largest file the plan allows; the statistics files count only against the disk and the run. When the largest file is smaller than the chosen size, the tool refuses before encoding with "Your files may weigh at most N MB; choose M MB or less", M being the largest size of the list that fits, and when the storage left is too small, with "This video would not fit in what is left of your storage; free some space or choose a smaller size".

An MP4 or MOV already lighter than the chosen size, with an H.264 picture in 8-bit 4:2:0 and AAC sound in mono or stereo (or no sound, or Keep the sound off), is copied into a new MP4 without being encoded again, leaving out the subtitles, the sound tracks after the first and, with Keep metadata off, the tags. If the copy weighs the chosen size or more, the video is encoded as above.

## Quality

The three steps stand for these encoder settings. Small files lose more detail; the differences between High and Balanced are hard to hear or see on most sources.

| Format | Encoder | High | Balanced | Small |
|---|---|---|---|---|
| JPEG | Pillow | quality 95, full colour resolution | quality 85 | quality 72 |
| WebP | Pillow (libwebp) | quality 92 | quality 80 | quality 65 |
| PNG | Pillow, compression level 6 | lossless | lossless | lossless |
| MP4, MOV picture | libx264, preset `medium`, 8-bit 4:2:0 | CRF 18 | CRF 23 | CRF 28 |
| MP4 (H.265) picture | libx265, preset `medium`, 8-bit 4:2:0, Main profile, tagged `hvc1` | CRF 22 | CRF 26 | CRF 30 |
| MP4, MOV sound | aac | 192 kbit/s | 160 kbit/s | 128 kbit/s |
| WebM picture | libvpx-vp9, `-cpu-used 4`, 8-bit 4:2:0 | CRF 27 | CRF 32 | CRF 37 |
| WebM sound | libopus | 160 kbit/s | 128 kbit/s | 96 kbit/s |
| MP3 | libmp3lame, variable bitrate | `-q:a 0` | `-q:a 2` | `-q:a 5` |
| M4A | aac | 256 kbit/s | 192 kbit/s | 128 kbit/s |
| OGG | libopus | 160 kbit/s | 128 kbit/s | 96 kbit/s |
| WAV | PCM, 16 bits, or 24 bits for a deeper source | lossless | lossless | lossless |
| FLAC | flac, compression level 5 | lossless | lossless | lossless |
| GIF | ffmpeg palette, `stats_mode=diff`, `diff_mode=rectangle` | 256 colours, Sierra dithering | 256 colours, Bayer dithering (scale 5) | 128 colours, Bayer dithering (scale 5) |
| Animated WebP | libwebp, compression level 4 | quality 85 | quality 75 | quality 60 |

The sound of MP4 (H.265) is encoded like that of MP4 (H.264). Lighten for sending has no quality step: its bitrate comes from the chosen size.

## What is kept and what is lost

**Keep metadata** is on by default in the four conversion tools and off in Lighten for sending. Turn it off before you share a photo or a video taken with a phone: the place where it was taken is kept otherwise.

| Converting | With **Keep metadata** on | With it off | Always lost |
|---|---|---|---|
| An image | EXIF data (camera, date, place), with the orientation set to normal; the text chunks of a PNG, such as generation parameters, when the result is a PNG too | No EXIF data, no text chunks | Animation (animated images are refused); XMP data, except from PNG to PNG; the text chunks of a PNG when the result is JPEG or WebP; EXIF data longer than 64 KB when the result is a JPEG, which cannot hold it; transparency in JPEG (filled with the background colour); 16 bits per channel (the result has 8) |
| An image's colour profile | Kept | Kept | A profile that does not match the result's colours, such as a CMYK profile on a picture converted to RGB; a profile larger than 1 MB, or one whose declared length does not match its bytes |
| A video | Title and other tags, the place where it was filmed (in MP4, MOV and WebM alike), chapters, the first eight sound tracks with their language, text subtitles (as `mov_text` in MP4 and MOV, WebVTT in WebM) | Only the picture and the first sound track, no tags, no place, no chapters, no subtitles | Picture subtitles (DVD, Blu-ray), attached files, data tracks; sound tracks after the eighth; 10-bit colour (the result is 8-bit); more than two sound channels in WebM (mixed down to stereo). An HDR video keeps its HDR colour labels over 8-bit pictures, without tone mapping: it can show colour bands, or look washed out in a player that ignores the labels. The same holds for Lighten for sending. |
| A sound | Title, artist and the other tags | No tags | Cover art; more than two channels in MP3 and OGG (mixed down to stereo); sample rates above 48 kHz in MP3 (it goes up to 48 kHz) and every rate other than 48 kHz in OGG (Opus works at 48 kHz) |
| The sound of a video | The tags of the video, such as its title | No tags | Every sound track after the first |
| A video made into an animation | No switch | No switch | The sound, the tags, the place, the subtitles; the frames between the chosen ones |
| A lightened video | Title and other tags, the place where it was filmed, chapters | No tags, no place, no chapters | Every sound track after the first, the subtitles, more than two sound channels |

ffmpeg writes its own name and version in every video and sound it makes, whatever the switch says.

## When a tool refuses

The tool window shows the reason, and nothing is added to the Library.

| Case | What happens |
|---|---|
| An animated GIF or WebP | Refused: "This image is animated (N frames); Media Converter converts still images only". |
| An SVG drawing | Refused, since Convert image reads pictures made of pixels only: the run ends with "This image cannot be read". |
| An image larger than 67 million pixels | Refused with its size and the limit. Media Converter reads only the size written in the file and does not decode the picture. |
| A PNG converted to PNG with the same size | Refused, since nothing would change. With a largest side smaller than the picture, it is shrunk. |
| A WAV converted to WAV, a FLAC to FLAC | Refused, since nothing would change. A JPEG, WebP, MP3, M4A or OGG file can be converted to its own format to make it lighter. |
| A video of more than 4096 × 2304 pixels (about 9.4 million) | Refused before any encoding, with its size and the limit. |
| A video whose picture grows past about 9.4 million pixels partway through | The larger pictures are not decoded and are left out of the result. |
| A video thinner than 2 pixels, or one that a largest side would make so | Refused. |
| A video without sound given to **Extract sound** | The menu may offer the tool on such a video; the run then ends with "Extract sound needs a video with sound". |
| A sound with no samples | Refused: "This sound is empty: there is nothing to convert". |
| A video or sound longer than the limit the admin set | Refused before any encoding when the file, or any of its tracks, states a longer length. A file that states no length, or a shorter one than it has, is encoded up to the limit plus one second, then refused. Half a second over the limit is let through, since encoders add a few milliseconds. |
| A result that would weigh more than one conversion or one run may write, more than the server can hold, or more than is left of the user's storage | Refused with what to do: choose a lighter format, convert fewer items at a time, free some space, or try again later or ask an admin when the server is short of disk space (see Load on the server). A WAV of known length is refused before encoding, since its size is known in advance; any other sound, and a video, is stopped as soon as it reaches the limit, then refused; an image is written whole, then refused, and nothing is added to the Library. |
| A transparent image converted to JPEG | Converted, with transparent areas filled with the background colour. |
| MP4 (H.265) while the admin setting is off | Refused when the run is asked for, before any step of it runs, also as a later step of a chain: "MP4 (H.265) is turned off on this server: an admin can allow it in Admin › Plugins › Media Converter › Settings. Choose MP4 (H.264) meanwhile". |
| MP4 (H.265) on a video that would take too long | Media Converter first counts the frames of the video by reading the file. When the size of the result and that count, against the thread count and the processor cores Media Converter may use (a processor limit set on its container included), leave any doubt, or when the frames cannot be counted, it encodes and times three parts of about 2 seconds and at most 120 frames each, at a quarter, half and three quarters of the video. If all the frames of the video would take more than about 18 minutes at the pace of the slowest part, it is refused before the real encoding starts: "MP4 (H.265) would take about N minutes to encode this video on this server, more than a conversion may take; choose a smaller Largest side, MP4 (H.264), or a shorter video". This is an estimate: a video much heavier elsewhere than in these parts can take longer, and may then be stopped as too long, as said under Settings below. |
| An animation longer than 30 seconds or shorter than half a second | Refused by the tool window; a request that bypasses it is refused by the tool. |
| An animation that starts at or after the end of the video | Refused before any encoding: "This video lasts N s: the animation must start before its end". |
| A size too small for Lighten for sending | Refused before any encoding, with the length of the video, the smallest size that would work and the next size of the list, and with a hint to turn off Keep the sound when that alone is enough. A video too long for 50 MB is told to be trimmed first. |
| A lightened video still too heavy after its second try | Refused: "Media Converter could not bring this video under N MB; choose a larger size". |
| A lightened video that the room of the run or of the file cannot hold | Refused with the messages of the run budget and of the disk, or with "Media Converter could not write the lightened video in the room it had; choose a smaller size". |
| A video that holds more frames than the first pass of Lighten for sending was given | Refused before the second pass: "This video does not hold what its file states (its length or its frame rate is wrong); convert it with Convert video first, then lighten the result". The first pass is given the number of frames Media Converter counted in the file, plus 2 %, or, when they cannot be counted, the frame rate and the length the file states. |
| A video whose length cannot be read, given to Lighten for sending | Refused: "Media Converter cannot read the length of this video", since the bitrate comes from the length. |
| A cancelled run | The encoder stops at once and nothing is published. |

## For admins

### Settings

In **Admin › Plugins › Media Converter › Settings**:

| Setting | Default | What it does |
|---|---|---|
| ffmpeg threads per conversion | 4 | How many processor threads one video or sound conversion may use, from 1 to 16. |
| Longest video or sound, in minutes | 30 | Longer files are refused with a message, from 1 to 30 minutes. Make an animation does not use it. |
| Allow MP4 (H.265) in Convert video | Off | On, Convert video may write MP4 in H.265. Off, the format stays in the list and is refused with a message. |

An encoding that runs too long is stopped with "Editing timed out", and nothing is saved. Sound converts in seconds, but a long video in 4K at High quality can take longer to encode than it lasts: if such runs time out, pick a largest side, raise the thread count, or lower the length limit.

Any signed-in user can run the tools. To turn them off for everyone, disable the plugin.

### Load on the server

Conversions run on the server's processor and never use the graphics card: no hardware encoder is used, so a generation keeps the whole card. The encoders of a video or sound conversion use at most the number of threads set above, the H.265 encoder included, whose own thread pool is set to the same number; reading the video and ffmpeg itself add about one more processor core in our tests. The slowest encoder is libx265 at its `medium` preset, two to five times slower than libx264 at the same preset in our tests. Lighten for sending reads the video twice, once per pass, and a GIF reads its part of the video twice too. A long video still takes the processor for a while and slows down the preparation of a generation that starts meanwhile: lower the thread count if that matters on your server.

Each run is bounded:

- an image of 67 million pixels takes up to about 1.6 GB of memory while it converts (WebP takes the most), which is why larger ones are refused;
- a 4K video takes about 2 GB of memory in ffmpeg, which is why larger ones are refused;
- ffmpeg stops at the length limit plus one second, even when a file does not state its length;
- one sound conversion writes at most what its sound can fill in the length limit: sample rate × channels × sample size × the limit, plus 2 %, and never less than 64 kB per second for MP3, M4A and OGG. A stereo WAV at 44.1 kHz may weigh up to about 325 MB with the 30-minute limit, whatever the size of its source. A sound whose length cannot be found gets no more than a video conversion would: 32 times the size of its source, never less than 1 GB;
- one video conversion writes at most 32 times the size of its source, never less than 1 GB; no conversion writes more than 4 GB;
- an animation writes at most 2 bytes per pixel of each of its frames, plus 1 MB, and its palette at most 1 MB more;
- Lighten for sending holds room for the chosen size and for its statistics files, counted for the frames of the first pass (the frames counted in the file plus 2 %, or the frame rate and length the file states when they cannot be counted) at 2 bytes per block of 16 × 16 pixels and 512 bytes per frame, plus 1 MB, which is about twice what libx264 writes; the first pass stops at that number of frames, so a file that states a wrong frame rate or length cannot make it write more;
- one run writes at most 8 GB, every item and every step of a chain together, counting what the other tools of the chain wrote before it; a conversion that would go past it is refused with a message that asks to convert fewer items at a time;
- Media Converter keeps 2 GB free on the disk where PotionUI keeps its working files. When a conversion starts, Media Converter takes out of the free space these 2 GB and the room it gave to its other conversions that are still running, less what they have written so far in their working folders, and gives the new conversion at most half of what is left; with too little left, it refuses. A room stops counting when its conversion ends, whether it finished, was refused, was cancelled or failed. So the conversions of Media Converter, however many run at once and in whatever order they start, stay out of these 2 GB together, except for what a video or sound conversion writes past its room before ffmpeg stops: about one encoded frame and the end of the file, which can reach about ten megabytes for a large video (up to 4 MB in MP4 and 11 MB in WebM in our tests, on a 4096 × 2304 video full of fine detail). The reserve does not hold against anything else that writes to the disk meanwhile: Media Converter counts only its own conversions. It does not see the conversions of another PotionUI server that shares the disk, and it counts every conversion it runs, whatever disk it writes to, so a server with working folders on several disks may refuse earlier than it needs to. When Media Converter refuses for lack of disk space, the user is asked to try again later or ask an admin, and the server log gives the space that was free, the 2 GB kept, the room promised to conversions still running, and the room the conversion had and needed;
- when a user's plan limits their storage or the size of one file, Media Converter reads these limits before each conversion, and a result that would not fit is refused: before encoding for a WAV of known length, as soon as it reaches the limit for any other sound and for a video, and once written for an image, which is then not added to the Library. If the plan cannot be read, the conversion goes on bounded by the rest of this list, and the server log says which limit could not be read.

The results count toward each user's storage, as uploads do. A WAV or a PNG can weigh much more than its source.

ffmpeg reads only the file it converts, and the palette it wrote for a GIF: the command allows local files only, a fixed list of container formats, and an absolute path, so a playlist or a concat list disguised as a video is refused. No text typed by a user reaches the command line: every setting is a choice from a list, a switch, or a number (the start and the length of an animation) that Media Converter checks and writes itself.

### Chat, MCP and automation

The six tools can also be run from the chat, MCP and the automation. Start long video conversions from the Library: the chat and the automation may stop waiting for a long conversion before it ends.

## Not in this version

- An animated GIF or WebP made back into a video, and the conversion of animated images.
- A target file size for images.
- Replacing the original from the tool window.
- AV1, AVIF, HEIC, JPEG XL and Opus in `.opus` files, since such a result may not open or play well in the Library.
- Copying the sound or the picture without encoding it again, such as a MOV to MP4 change of container, except for a video already under the size chosen in Lighten for sending.
- Keeping the cover art of a sound file.
- The tool in the media field of a generation form.
- Photos above 67 million pixels, such as the 108 and 200 megapixel photos of some phones and large panoramas, and videos above about 9.4 million pixels (4096 × 2304), such as 5.7K and 8K: they are refused.
