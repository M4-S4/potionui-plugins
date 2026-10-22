# Video Producer

Video Producer brings a film workflow to AI video inside PotionUI: write a synopsis, split it into shots, generate draft takes for each shot, choose the best take, turn it into a final, then cut, match color, mix sound and deliver. It all happens in one page with five workspaces (Media, Director IA, Storyboard, 3D scene, Mix). Admins and users can both use it. An admin decides which engines and video presets exist (this machine, a studio server or a cloud model), sets a few plugin settings and, through plans, how many GPU minutes each user gets per month. The interface is in English by default and in French; each user picks the language and it is saved per user.

This page is the administration guide. Every user can read the user guide, in English (`docs/user-guide.md`) and in French (`docs/user-guide.fr.md`). Everything described here is delivered: takes are real PotionUI generations, with a real estimate, quota, finals and follow-up (see Generation); the assistant is a PotionUI chat mode with four tools (see The assistant mode); the four files for other software (FCPXML, OpenTimelineIO, EDL, SRT), the web and social videos that ffmpeg assembles on the server and the seam frame are real too (see Exports). The 3D scene builds real Gaussian Splats and renders real reference videos (see The 3D scene). Six functions are simulated, and the page marks them (see What stays simulated). The figures measured on a real machine, and what they mean for the hardware you plan, are under Hardware.

## Requirements

- PotionUI with plugins enabled, and an admin account to enable this one.
- At least one video engine: the native engine on this machine, a Remote Native worker, or a cloud provider with a video model. See Engines below.
- At least one Video Director preset, installed and assigned to the users who will generate: Wan, LTX, MiniMax-H3 or a cloud video preset. See Models and presets below.
- The model files that these presets need, downloaded. Video Producer picks them itself from the recommendations of each preset (see Generation › Required models); a preset with a missing file is blocked for generation.
- The SeedVR2 preset and its model files, assigned to the users, to turn a chosen draft take into a final. A take of the base MiniMax-H3 preset is enlarged by the upscale mode of its own preset instead.
- ffmpeg and ffprobe on the PotionUI server, to deliver a video file and to extract a frame of a take at a given time. See ffmpeg below.
- For a local engine, a GPU that meets PotionUI's own Hardware Requirements page: a Turing or newer NVIDIA card, driver 580 or newer, 8 GB of VRAM and 16 GB of system RAM as the supported minimum, 16 to 24 GB of VRAM and 32 GB of RAM recommended. Video families need more than the floor; that page has a verdict per family. What Video Producer measured on a 12 GB card, and the system RAM it needs, is under Hardware.
- For a cloud engine, an account and an API key with the provider (OpenRouter or Google AI Studio).
- For the assistant, a language model configured in PotionUI (Admin → LLM / Assistant) and assigned to the users, able to call tools. A local llama.cpp `llama-server` (added as an OpenAI configuration) is recommended when the model shares the video card; Ollama works once its context size, keep-alive and thinking mode are set; an online provider such as OpenAI is possible too. The Native client is not recommended on a 12 GB card. See The assistant mode › Which language model.
- The `jsonschema` Python package, which checks the project documents. The plugin relies on it; the PotionUI image already contains it, and its version is pinned in `constraints.txt`. There is nothing to install.

## Hardware

Generation runs on the machines you give it, so the figures below decide what your users can do. They were measured on one machine and are not guarantees for another: an NVIDIA RTX 4070 Ti with 12 GB of VRAM (12,282 MiB), a host with 128 GB of RAM of which 67 GB were given to Docker, and the native engine of PotionUI. Not measured: cloud models (no API key was available), a Studio server and cards with more than 12 GB. A dash means that no figure was recorded or that the step does not use the card. The first table comes from the first real takes; the measures of the hardware-tier presets, made with a RAM limit on the container and, for 8 GB, a capped card, are under Models and presets › Hardware tiers.

| What was run | VRAM peak | System RAM peak | Measured time | Notes |
|---|---|---|---|---|
| MiniMax-H3-Fast (12 GB): 5.17 s draft at 832×480, 24 fps, 124 frames, 8 steps | 11,879 MiB | 25.9 GB | 5 min 57 s, then 5 min 53 s on a second run | The text encoder streams from RAM: encoding the prompt took 83 s. H.264 with AAC stereo sound. |
| MiniMax-H3 (12 GB): the same shot, 20 steps | 11,818 MiB | 25.1 GB | 7 min 26 s (about 18 s per step) | H.264 with AAC stereo sound. |
| MiniMax-H3-Fast without the 12 GB profile, tried before the text encoder could stream from RAM | out of memory | — | Failed after 2 min 08 s | CUDA out of memory in the 32B text encoder. The CUDA context then stayed unusable until the container was restarted. The base and VDN presets load the same text encoder and were not run, and the core presets were not run again after the streaming change. |
| Wan 2.1 / 2.2 (14B, fp8, about 35.6 GB of files): 5 s draft at 832×480, 16 fps, 81 frames | 11,274 to 11,673 MiB | 41.75 GiB | 25 min 49 s, 27 min 19 s and 25 min 58 s on three runs | Most of the model streams from RAM. H.264. |
| SeedVR2: upscale of that Wan draft to 1080p (file of 1872×1072, 6.5 MB) | — | — | 2 h 27 min 45 s | The re-render of the same shot at 1280×720 with the same seed was stopped at 23 % after 83 min (more than 4 hours extrapolated). |
| Web video: the 29 s starter sequence at 1080p | — | — | 11 s (about 6 to assemble and mix, 5 to convert) | 3.2 MB. Needs ffmpeg and ffprobe, not the GPU. |

What to plan for:

- **8 GB of VRAM.** Install and assign the two 8 GB presets, **Wan 2.1 T2V 1.3B (8 GB)** and **Wan 2.2 TI2V 5B (8 GB)** (see Hardware tiers): text to video in 480p, with 32 GB of system RAM.
- **12 GB of VRAM.** For MiniMax-H3, install and assign the two 12 GB presets (see Hardware tiers): the Fast preset without that profile ran out of memory on this card before the text encoder could stream from RAM, and the base and VDN presets load the same text encoder. For Wan 2.2 14B, install and assign **Wan 2.2 14B Lightning (12 GB)** for text to video in 6 steps, and the core Wan 2.1 / 2.2 preset with its image-to-video pair (recipe `vp-wan22-14b-i2v`) for shots that start from a frame; the 30-step text to video of the core preset runs too, slowly (see Hardware tiers). The estimate warns before the user starts: it announced 37.1 GB for Wan and between 41.75 and 42.85 GB for the 12 GB presets against a budget of 10 GB, with the warning "Will stream through host RAM, slower" and no block.
- **System RAM.** Plan on 32 GB for the 8 GB presets and on 64 GB for the 12 GB presets and for Wan 2.2 14B: the MiniMax-H3 presets stream their text encoder from system RAM (the `text_encoder_placement` option), the part of the DiT that does not fit on the card stays there too, and Wan 2.2 14B holds about 35 GB of process memory. Each preset declares its figure in `requires.min_ram_gb`, shown as a badge in the preset picker.
- **Time.** On this card a 5-second draft takes about 6 to 7.5 minutes with the MiniMax-H3 12 GB presets, about 3.5 minutes with Wan 2.2 14B Lightning, about 5.5 minutes in image to video with 6 steps and about 26 minutes with the 30 steps of the core Wan preset, and a final by SeedVR2 upscale to 1080p takes more than two hours. Tell your users, and set **Max generations in flight per user** and the monthly GPU minutes with this in mind.
- **After an out-of-memory error.** The native engine can keep an unusable CUDA context after a CUDA out of memory error. If every take then fails within seconds, restart PotionUI.
- **The assistant.** When its model shares the video GPU, unload it before a generation: see The assistant mode › Which language model.
- **Disk.** The Wan starter recipe downloads about 35.6 GB; the SeedVR2 files are listed under SeedVR2 for finals.

## Install and activate

In Admin → Plugins, enable **Video Producer**. A **Video Producer** entry appears in the sidebar; it opens the page `/plugins/video-producer`. The plugin keeps its own database tables (`video_producer_*`, created when the application starts); they hold the projects, the takes, the time measures and the video exports (see Projects and media, Generation › Tables and Exports › Tables). A background task that follows running generations is started once the application is ready and stopped when the plugin is disabled (see Generation › Following the takes); another one works through the queue of video exports (see Exports › The assembled video).

Admin → Plugins shows a **Setup needed** badge on the plugin until its setup steps are done, and the Overview tab opens with a **Setup** section that links to this page (it is the first entry of the plugin's documentation). The same page is under Admin → Documentation as **Video Producer: administration**. The user guides are in the **User Guide** section of the Documentation page that every signed-in user sees, as **Video Producer: user guide** and **Video Producer : guide utilisateur**; each one starts with a link to the other, because PotionUI has no notion of language for documents.

## The editor

The page is a complete editor with five workspaces: Media (the images, videos and audio files of the project, imported from the PotionUI library and gallery), Director IA (direction, references and results), Storyboard (the synopsis and one card per shot), 3D scene and Mix. Around them are ten menus, the project bar, the Production bar, the Inspector, the timeline (the mixing console takes its place in Mix), the status bar and the windows: prompt library and composer, Advanced workshop, Sound design workshop, export, preferences, keyboard shortcuts and command search.

The interface exists in English and in French. Each user picks the language in Video Producer › Preferences… or with the `EN` or `FR` reminder of the status bar; it is saved per user, and until a user chooses, the page follows the language of the browser (French for a French browser, English otherwise). Keyboard shortcuts show the notation of the user's system (⌘, ⌥ and ⇧ on a Mac, Ctrl, Alt and Shift elsewhere). The single-letter shortcuts (A, R, B, I, O, M and N) can be turned off in the Preferences.

What the page offers:

- The page opens the project that the user opened last, otherwise their most recent project. On a first visit, or when the user has no project left, it creates the starter project "Dawn at the harbour" ("Aube sur le port" in French) and opens it: a synopsis, the global direction in five fields, five shots of 5 seconds to generate, each with its shot prompt, a title, a marker and four empty audio tracks. It has no media, no take, no reference and no 3D scene. Its name, synopsis, shot names, title and marker follow the language of the interface; its global direction and shot prompts follow the prompt language of the project, English by default. Projects are saved on the server as the user works, with a history of versions: File › New project… saves the current project, then starts an empty one, and File › Open… and File › Version history… are real. See Projects and media.
- The user imports images and videos from the PotionUI library (File › Import files…) and from the gallery (File › From the PotionUI gallery), and audio files from the library, with the multi-select pickers of PotionUI. The page resolves each pick with `POST /media/resolve`, shows real thumbnails and durations (and the frame rate when the library knows it), and plays the real video, images and audio. A media that is already in the project, with the same origin, is not imported twice.
- The **Generation engine** pop-up of the Production bar is filled from `GET /me` with the engines and presets that the user may run (see Engines). **Generate selection** starts real takes: they are PotionUI generations, and their videos play in the viewer, the Inspector and the Results tab. The estimate shows the time (measured on previous takes of the same preset, engine and resolution), the memory, the quota and, for admins only, the cloud cost. The status bar shows a GPU quota only when a plan sets a limit for the user. A shot with the FL2VA profile and no frame is not blocked: the page warns that it will be generated from text only, and the take card says "text only". When the shot has a previous shot with a finished take, an icon next to the warning, "Use the previous shot’s last frame", gives it that take's last image as its first frame (see Exports › Seam frames).
- The Assistant button, the Window menu (PotionUI assistant) and Ctrl+J open the PotionUI chat in the Video Producer assistant mode, which has four tools: write the prompt of a shot, fix the conflicts with the direction, split the synopsis into shots and check the continuity. Every change waits for the user's approval; the Direction tab lists what the continuity check found under To check. See The assistant mode.
- The FCPXML, OpenTimelineIO, EDL and SRT files are real downloads, built by the server from the saved project. The web and social videos are real too: ffmpeg assembles the sequence in the background, the MP4 is kept in the export folder of the user and copied to the user's library, and a notification tells when it is ready. The master file, the archive and the audio stems stay simulated. A shot can take the last image of the previous shot's take as its first frame, and any frame of a take can become the first or last frame of a shot. See Exports.
- The mixing console plays the audio files that the user imported, for real. It synthesizes (WebAudio) the sounds that the Sound design workshop prepares.
- The 3D scene builds a Gaussian Splat from a picture or from a frame of a shot, imports splats and Blender files, captures new angles as the first or last frame or a reference of a shot, and renders the camera paths of the 3D shots as reference videos for the generation. See The 3D scene.

## Setup checks

Admin → Plugins → Video Producer → Overview lists five setup steps, each backed by a check. Each one reads the state of the instance as it is now, so the list updates as you work through it.

| Step | Done when | What to do | Where |
|---|---|---|---|
| **Enable a native backend or a cloud video model** (`VideoEngineReady`) | An engine that can run Video Director presets is enabled: This machine with a GPU, a Studio server, or a cloud backend with a video model turned on. ComfyUI backends do not count, and neither does a native backend that PotionUI reports as having no GPU (its device is `cpu`). | This machine: check that it is enabled and that its device is a GPU. Studio server: add a Remote Native backend. Cloud: install the provider plugin, add its backend with the API key, turn on a video model in its catalog. | Admin → Backends, Admin → Plugins |
| **Install and assign at least one Video Director preset (Wan, MiniMax-H3, LTX or a cloud video preset)** (`VideoPresetsReady`) | At least one installed preset that declares Video Director is assigned to a user or a group. | Install the preset, then assign it to the people who will generate. Download its model files. | Admin → Presets, Admin → Downloads, Admin → Models |
| **Install SeedVR2 for final takes** (`UpscalerReady`) | The SeedVR2 preset is installed. The check does not look at its model files; its text tells whether the preset is also assigned. | Install the SeedVR2 preset, assign it to the people who make finals and download its model files (a DiT, a VAE and a prompt embedding). | Admin → Presets, Admin → Downloads, Admin → Models |
| **Install ffmpeg for video delivery** (`FfmpegReady`) | The PotionUI server process finds `ffmpeg` on its `PATH`. The check also looks for `ffprobe`, next to `ffmpeg` or on the `PATH`, which the export needs too (see ffmpeg). | Install ffmpeg and ffprobe so that they are on the `PATH` of the PotionUI process, then restart PotionUI. In Docker, check the image. While the step is not done it offers a **Read the guide** button that opens this page. | The server |
| **If a MiniMax-H3 preset is installed, install its five model files (DiT, text encoder, video VAE, audio VAE, and the latent upscaler of its Upscale mode)** (`MiniMaxH3Ready`) | No MiniMax-H3 preset is installed, or every installed one has its four files, and, for a preset that has an Upscale mode (the base MiniMax-H3 preset, not Fast or VDN), the file of its latent upscaler (`upscale_model`). Each file is recognised by its SHA-256, or else by its file name, among the files that the preset's model pickers recommend. | Download the files, and read the MiniMax-H3 reminder below before you do. | Admin → Downloads, Admin → Models |

How the steps behave, as PotionUI defines them:

- The text under a step comes from the check itself, so it tells you what is missing. An action button appears only when the check offers one, and it disappears once the step is done.
- Each check has three outcomes: done, still to do, and could not be checked. The table below gives the text of each.
- A check that cannot read the state of the instance shows as a step still to do. It says, for example, "Could not check the backends; see the server log.", and offers the button of the Admin page to look at. If a check itself fails, PotionUI shows its own text, "This step could not be checked. See the server log."
- The checks run on every visit to Admin → Plugins. They only read local state and never call out to the network.

| Check | Done (text) | Still to do (text, then button) | Could not be checked (button) |
|---|---|---|---|
| `VideoEngineReady` | "Takes can run on …." It names each native backend that has a GPU or whose device is not known yet (a backend that is not running), and each cloud backend with its number of video models. | A cloud backend without a video model: "No video model is turned on in …. Turn one on in the backend's catalog, or enable a native backend." (**Open catalog**). Nothing enabled: "Enable the native backend of this machine or a native remote worker, or add a cloud backend and turn on a video model in its catalog." (**Open backends**). A native backend without a GPU is named first by "Takes cannot run on …: no GPU is configured." followed by the text above, except that with nothing else enabled the advice reads "Give a native backend a GPU, enable a native remote worker, or add a cloud backend and turn on a video model in its catalog." (**Open backends**). | "Could not check the backends; see the server log." (**Open backends**) |
| `VideoPresetsReady` | "Installed and assigned: …. A user sees only the presets assigned to them or to one of their groups, which this check cannot verify user by user." | Installed but assigned to no one: "Installed but assigned to no one: …. Assign one to the users or groups who will use Video Producer." (**Assign presets**). Not installed: "Install a Video Director preset (…), then assign it. Cloud video presets come with their provider plugins." (**Open presets**). None available: "No Video Director preset is available. Enable a plugin that ships one, such as a cloud provider." (**Open presets**). | "Could not check the presets; see the server log." (**Open presets**) |
| `UpscalerReady` | "… is installed and assigned.", or "… is installed. Assign it to the users or groups who make final takes." | Not available on the instance: "The SeedVR2 preset is not available on this instance; final takes need it." (**Open presets**). Not installed: "Final takes are upscaled with …. Install it, then assign it to the users or groups who make final takes." (**Open …**). | "Could not check the SeedVR2 preset; see the server log." (**Open presets**) |
| `FfmpegReady` | "ffmpeg is available." (ffmpeg and ffprobe are both found) | "Video Producer joins takes and exports the cut with ffmpeg, and reads media with ffprobe; ffprobe is missing. Install ffmpeg with ffprobe on the server so both are on the PATH, then restart PotionUI." (or "ffmpeg is missing") (**Read the guide**) | "Could not check ffmpeg; see the server log." (**Read the guide**) |
| `MiniMaxH3Ready` | "No MiniMax-H3 preset is installed; nothing to check.", or "The DiT, text encoder, video VAE and audio VAE files, and the latent upscaler of the Upscale mode, are on disk for …." | "… is missing its DiT and text encoder. Download one of the files its model pickers recommend; the check recognises those files by their SHA-256 or their file name, not other quantizations." (**Open …**) | "Could not check the MiniMax-H3 model files; see the server log." (**Open presets**) |

In these texts and buttons, "…" stands for the names of the backends or presets concerned.

`tests/test_setup_checks.py` tests every check in its three outcomes with a fake PotionUI context (text, button label and link), the ffmpeg check also with ffprobe missing, and that the manifest declares the five checks with the labels of the first table. The manifest test of the PotionUI core reads the report of the setup with its five steps still to do and their links.

## Settings

In Admin → Plugins → Video Producer → Settings:

- **Draft resolution** (`draft_resolution`, default 832×480): the size of draft takes: 832×480, 960×544 or 1280×720. For a native preset, a draft is made at this size, turned to the orientation of the project (a portrait project gets the reversed size), when the preset offers it among the resolutions that fit the aspect ratio of the project; otherwise the preset's option that is closest in area is used. A cloud model uses its own default resolution (its smallest one when it declares no default). The final quality and a re-render use the largest option of the preset or of the model, whatever this setting says. It does not set the frame rate. A take keeps the frame rate of its preset (16 fps for Wan, 24 fps for MiniMax H3), while the timeline and the exports use the frame rate of the project.
- **Max generations in flight per user** (`max_parallel_jobs`, default 2): how many takes of one user PotionUI holds at once, whether running or waiting in its own queue, across all the projects of that user. Takes past that number stay **Queued** in Video Producer, with no PotionUI generation yet, and the follow-up task hands them over as soon as a place frees up (it looks every 2 seconds while takes are active). A waiting take already reserves its GPU minutes when its user's minutes are limited. See Quotas and Generation › Following the takes.
- **Export cache per user (MB)** (`export_dir_quota_mb`, default 2048): the size budget of each user's export folder (`video_producer/exports/<user id>/` in the file storage directory), where the web and social videos are kept. It is per user, not for the whole instance, and it is checked when an export is requested. See Exports › Storage and quota.
- **Versions kept per project** (`versions_kept`, default 50): how many saved versions each project keeps, from 5 to 500. When a project goes over it, the oldest versions are deleted. See Projects and media.

The first one is a choice between three values; the other three are numbers. Values are saved as text, and the form itself does not enforce a minimum or a maximum, so the plugin applies its own bounds: 1 to 16 parallel generations, 1 to 1,048,576 MB of export budget and 5 to 500 versions. A number outside its range is brought back to the nearest bound; an empty value, or one that is not a whole number, falls back to the default.

The language is not a setting here: each user chooses English or Français in the Preferences of the page, and it is stored for that user. Until a user chooses, the page follows the language of the browser. The language of the prompts is not a setting here either: each project has its own (see Projects and media).

## Quotas

Admin → Users → Plans can limit one thing for this plugin: **Video Producer GPU minutes per month** (`video-producer.gpu_minutes`). It is a count in minutes, in a monthly window. To use it:

1. Open Admin → Users → Plans and open a plan you created. The built-in plans cannot take new limits: their **Add limit** button is disabled.
2. Click **Add limit** and pick **Video Producer GPU minutes per month**.
3. Enter the number of minutes, then assign the plan to groups or users in the same editor.

A plan without this limit means unlimited minutes. The **Admins are exempt** switch in the plans list applies as usual. For a user without a limit and for an exempt admin, Video Producer reserves, adjusts and refunds no minute: nothing is recorded in the ledger for their takes, so a limit that you add later counts only what is recorded from then on.

How it is applied:

- Video Producer applies the limit itself, when a take is created. PotionUI does not count these minutes on its own: the plugin records them in the usage ledger of the limit, and the limit's total is the sum of what it recorded in the month.
- **Reservation.** Each native take of a user whose minutes are limited (a plan limit, and not an exempt admin) reserves minutes as soon as it is created, even while it waits for a free place (`max_parallel_jobs`). The reservation is the measured time of the preset, backend and resolution when there is one (see Generation › Time calibration), otherwise 10 seconds of GPU work for every second of video: a 5-second shot reserves about 0.83 minute.
- **Check.** The estimate that the Production bar shows before generating includes the quota (`quota.needed_minutes` against `quota.remaining`). When it is not enough, Generate selection is refused with the block `quota_exceeded`, and the server applies the same check to a generation, a final and a retry, whatever the page says. Of the three things the estimate measures (time, memory, quota), only the quota blocks: not enough memory only warns. A plan without a limit, and an exempt admin, are never blocked; their takes keep `units_reserved` at 0, and their end neither adjusts nor refunds anything.
- **Adjustment.** When a take that reserved minutes ends, its reservation is brought to the real duration of the generation: if it ran longer, the difference is recorded on top (reference suffixed `:adjust`); if it ran shorter, the reservation is refunded and the real duration is recorded (reference suffixed `:actual`).
- **Refund.** A take that fails, is cancelled or is refused by PotionUI gets its whole reservation back, if it had one. Deleting a take cancels it first when it is in flight, and deleting a project cancels its takes in flight and refunds their reservations before it deletes the rows.
- A generation that is already running is never stopped by a quota; only the next ones are refused.
- Cloud engines do not use GPU minutes (`quota.applies` is false, the reservation is 0). Their spending belongs to the PotionUI limit **Cloud spend per month** (`cloud_spend_usd_month`), which you add to a plan in the same way.

## Engines

Video Producer offers the engines that you enabled for it:

- **This machine** (`native.local`): the native engine of the PotionUI server, always present. Nothing to add; check that it is enabled in Admin → Backends.
- **Studio server** (`native.remote`): a Remote Native backend, that is another machine or rented compute that runs a PotionUI Remote Native worker. In Admin → Backends add a Remote Native backend and paste the URL of the worker, or provision one from the backend's Infrastructure tab. The model files must also be on the worker; the backend's Models tab shows the exact per-file paths. The Remote Native documentation describes the worker.
- **Cloud**: the presets **OpenRouter Video** and **Gemini Video**. Install the `openrouter-provider` or the `google-gemini-provider` plugin, add its backend with your API key ("Add an OpenRouter backend with your API key" or "Add a Google Gemini backend with your AI Studio API key" in that plugin's setup), then turn on a video model in the backend's Catalog tab. Each shot is one paid request to the provider.

ComfyUI is not offered as an engine. Video Producer builds one Video Director document per shot, and a ComfyUI preset does not run Video Director documents: it keeps its own per-batch prompt relay.

What the **Generation engine** pop-up of the Production bar lists, for a given user:

- Under the highest-priority enabled native backend (This machine or a Studio server), each Video Director preset that is assigned to the user. A MiniMax-H3 preset is shown as **MiniMax H3**, **MiniMax H3 Fast** or **MiniMax H3 VDN (experimental)**.
- Under each enabled cloud backend, each video model turned on in its catalog, by the name of the model. A cloud model runs through the cloud preset whose driver (`cloud.openrouter` or `cloud.google`) matches the backend.

The routing of a native take belongs to PotionUI: Video Producer submits the request of the preset and PotionUI chooses the backend that runs it, by its own priority and eligibility rules. The take records the backend it ran on (`backend_id`), and the take card shows it. The pop-up does not pin a take to a backend.

The choice is saved with the project (`engine.backend`, `engine.preset` and, for a cloud model, `engine.model`). When a project saved by an earlier version opens, the page migrates its old engine value: `local` becomes the first local engine, `studio` the first remote one, `cloud` the first cloud one, and anything else the first engine that exists. An engine that is no longer available shows "Engine no longer available" and blocks the generation until the user picks another one. The pop-up is hidden in a window narrower than 1400 pixels; the user then chooses the engine in the Advanced workshop (Production › Generation engine…). When the user has no engine, the pop-up shows "No engine", the bar says "No generation engine: an administrator must enable a video preset or a cloud model." and an admin gets the link "Open plugin settings".

Cloud cost: PotionUI records the cost of every cloud job and shows it to admins only (Admin → Generations, and the spend statistics). Video Producer follows the same rule: only an admin sees a cost estimate, and a price that the provider does not publish is never invented (see Generation › Cloud cost).

## Models and presets

Video Producer can generate with every installed preset that declares Video Director, once it is assigned to the user: Wan, LTX-2, LTX-2.5, MiniMax-H3 (and its Fast and VDN variants), the five hardware-tier presets the plugin ships (see Hardware tiers), OpenRouter Video and Gemini Video. The frame rate of a take is set by the preset, and a user sees only the presets assigned to them.

| Preset | Profiles | What Video Producer asks of it |
|---|---|---|
| Wan 2.1 / 2.2, LTX-2 / 2.3, LTX-2.5 | FL2VA | Mode `video` of the preset, with a text-only, first-frame or first-and-last-frame composition. Wan runs at 16 fps by default. |
| Wan 2.1 T2V 1.3B (8 GB), Wan 2.2 TI2V 5B (8 GB), Wan 2.2 14B Lightning (12 GB) | FL2VA | Mode `video`, text only: their Video Director declares the `t2v` composition alone, so the frames linked to a shot are not used and the estimate warns `text_only_preset`. 16 fps for the 1.3B and the Lightning preset, 24 fps for the 5B, shots cut to 5 seconds. |
| MiniMax-H3 | FL2VA, Ref2VA, Hybrid AV | Mode `video` for FL2VA and Hybrid AV, mode `refs` for Ref2VA, mode `upscale` for a final. Fixed 24 fps, clips up to 15 seconds. |
| MiniMax-H3 (12 GB) | FL2VA, Ref2VA, Hybrid AV | Mode `video` for FL2VA and Hybrid AV, mode `refs` for Ref2VA, with the same memory profile. No `upscale` mode, so its finals go through SeedVR2 like those of Wan. Fixed 24 fps. |
| MiniMax-H3 Fast, MiniMax-H3 VDN and MiniMax-H3-Fast (12 GB) | FL2VA, Hybrid AV | Mode `video` only. They have no `refs` mode, so no Ref2VA, and no `upscale` mode, so their finals go through SeedVR2 like those of Wan. Fixed 24 fps. |
| OpenRouter Video, Gemini Video | FL2VA | Mode `txt2video`, or `img2video` when the shot has a first frame and the model accepts one. |

The profiles that a preset cannot generate are greyed in the page and marked "MiniMax H3 only" (Ref2VA and Hybrid AV need a MiniMax H3 preset, and Ref2VA the base one), and the server answers the block `profile_unsupported` if a client asks for one anyway.

### Wan

- The preset defaults to 832×480 at 16 fps, which is also the default draft resolution of the plugin.
- PotionUI's hardware page lists Wan 2.2 14B (two experts) at 16 GB of VRAM or more, and the 5B variant as the realistic option for a small card (12 GB or more). Measured here, the 14B text-to-video and image-to-video pairs both run on a 12 GB card with about 35 GB of process memory (see Hardware tiers), and the 1.3B and 5B run on an 8 GB card in the plugin's two 8 GB presets.

### LTX

- PotionUI's hardware page lists the LTX family as not yet recommended at any tier, because GPU validation is still open. LTX-2 and 2.3 are one all-in-one checkpoint of about 27 GB; LTX-2.5 uses separate files.
- On the 12 GB card of the Hardware measures, LTX-2.3 22B distilled fp8 ran out of GPU memory in the DiT at 832×480, for a 5-second and for a 2-second clip, with 62 GB of RAM. The plugin ships no LTX preset.
- LTX-2.5 22B distilled int8 ConvRot, with its Gemma4 int8 encoder, ran on that card for a text-to-video clip of 1 second at 480×832 with sound: 5 min 57 s from a cold start, about 1 minute of it for the 8 steps and the decode. The Layout-To-Render shots of the 3D render + AI mode (832×480, 3 seconds, a reference video and a first frame, about twice the tokens of the clip) run there since the core counts the IC-LoRA when it places the DiT: 475 s from a cold start, about 21 s per step, an engine peak of 10.7 GB; before that fix they ran out of GPU memory in the first step. At a reference strength of 0.65 or 0.4 the take copied the reference, whatever its look (splat render, grey, clay or depth); at strength 1 a clay reference kept the look of the first frame and followed its camera move (measured on 20 October 2026). So did the splat render of the 3D scene itself, rendered in 73 frames and sent by the plugin at strength 1: the take followed the parallax of the orbit zone by zone and kept none of its white holes, in 270 s from a cold start (about 7 s per step, engine peak 10.7 GB, 22 October 2026); the look comes from the first frame, rendering defects of a splat capture included.

### MiniMax-H3: read before enabling

Video Producer offers MiniMax-H3 as soon as its presets are installed and assigned, on the same footing as Wan. The interface shows no warning badge, so this reminder is for admins. The page writes the name of the model as **MiniMax H3** in the engine pop-up, on the take cards and in its messages (for example "MiniMax H3 only" next to the profiles that need it).

- **Validation status.** PotionUI's own documentation says that no end-to-end run on real weights has been performed for the MiniMax-H3 family, that GPU validation is pending, and that the family is not recommended on any card size until that is done. Video Producer does not change that status.
- **License.** The weights are published under the MiniMax H3 Community License, not an open-source license. Its Applicable Territory excludes the European Union, the United Kingdom, the United States and the Republic of Korea, and the exclusion extends to what the model generates. Use there needs an individual authorization from MiniMax (https://platform.minimax.io/h3-license). A separate written authorization is required above US$20M of annual revenue, and a commercial product's interface must display "MiniMax H3" prominently. PotionUI ships no weights: the license is between you and MiniMax. The Fast and VDN variants carry the same terms. Showing the name in the pop-up and on the cards is a display choice of the page; whether it meets the license for your use is for you to judge.
- **Files.** Four separate files are needed: the DiT, the text encoder, the video VAE and the audio VAE. The base MiniMax-H3 preset needs a fifth one for its Upscale mode, the latent upscaler; the fifth setup step lists all of them. The Video mode needs the `fl2va` DiT file and the References mode the `ref2va` one. PotionUI cannot tell them apart, so check the file name: a wrong pick runs without an error and ignores the references. The Fast and VDN variants have neither a References mode nor an Upscale mode (their finals go through SeedVR2).
- **Clips.** MiniMax-H3 runs at a fixed 24 fps, for clips up to 15 seconds; its release notes recommend 5 seconds or more. Picture and soundtrack come out of one pass. A shot longer than 15 seconds is cut and the estimate warns `duration_clamped`.
- **Hardware.** It is the heaviest family that PotionUI documents. If the card cannot hold it, the engine streams the overflow from host RAM, which is slower; that needs the size of the overflow plus about 2 GB of free host RAM and refuses to start without it. The Production bar warns "will stream through host RAM, slower" and does not block.

In Video Producer, the reference-guided profile (Ref2VA) uses the References mode of MiniMax-H3. If a user says that references are ignored, check the DiT file first. In Admin → Presets → Configuration, the MiniMax-H3 preset has tag filters for its DiT, text encoder and VAE pickers if you want to narrow the choices.

### Hardware tiers

Video Producer ships five presets of its own, each set up for one size of graphics card, and one recipe per preset that downloads its files, installs and assigns the preset and runs a short first generation. They live in the plugin's `presets` and `recipes` folders (declared by `presets:` and `recipes:` in `manifest.yml`), so Admin → Presets and Admin → Recipes list them as soon as the plugin is enabled.

| Preset | Card | System RAM | What it makes | Recipe |
|---|---|---|---|---|
| **Wan 2.1 T2V 1.3B (8 GB)** | 8 GB | 32 GB | Text to video, 832×480, 480×832, 640×480 or 480×640, 16 fps, up to 5 s, 30 steps, CFG 6 | `vp-wan21-t2v-1-3b-8gb` (2.84 GB to download if nothing is there yet, 9.8 GB in all) |
| **Wan 2.2 TI2V 5B (8 GB)** | 8 GB | 32 GB | Text to video, 832×480 or 480×832, 24 fps, up to 5 s, 30 steps, CFG 5 | `vp-wan22-ti2v-5b-8gb` (18.1 GB in all) |
| **Wan 2.2 14B Lightning (12 GB)** | 12 GB | 64 GB | Text to video, 832×480 or 480×832 in draft, 16 fps, up to 5 s, 6 steps, CFG 1, with the lightx2v LoRA pair | `vp-wan22-14b-lightning-12gb` (about 38 GB) |
| **MiniMax-H3 (12 GB)** | 12 GB | 64 GB | Video and sound, 832×480 by default, 24 fps, up to 15 s, 20 steps | `vp-minimax-h3-12gb` (about 40 GB) |
| **MiniMax-H3-Fast (12 GB)** | 12 GB | 64 GB | Video and sound, the same canvas, 8 steps | `vp-minimax-h3-fast-12gb` (about 41 GB) |

- **Name, `requires` and profile.** The name says the card; `requires` carries `min_vram_gb`, `recommended_vram_gb` (12 for the 8 GB presets, 16 for the Lightning preset) and `min_ram_gb`, which the preset picker shows as badges. `GET /me` gives every preset a `profile`, read from `vars.video_producer.profile`: `"8 GB · 32 GB RAM"` or `"12 GB · 64 GB RAM"` for these five, `null` for the others. The engine pop-up adds to the name the parts of the profile it does not already contain, so it shows **Wan 2.1 T2V 1.3B (8 GB) · 32 GB RAM**. The tags start with the card (`8gb` or `12gb`), `low-vram` and the RAM (`ram-32gb` or `ram-64gb`).
- **The engine settings.** No preset and no recipe can set the engine: `text_encoder_placement`, `gpu_max_vram` and the fp8 quantization at load are settings of the native backend (Admin → Backends). These presets were measured with the defaults (`auto`), and they expect them.
- **The recipes.** Each one enables the HuggingFace provider, indexes the models already on disk, asks to download only what is missing (the consent window of Admin → Recipes), installs and assigns the preset. The two 8 GB recipes then run a 1-second text-to-video clip with 10 steps, within the 5 minutes the recipe runner gives a first generation by default (measured: 3 min 30 s and 2 min 32 s for the whole recipe with the files present). Two recipes cover Wan 2.2 14B: `vp-wan22-14b-lightning-12gb` for the Lightning preset, and `vp-wan22-14b-i2v`, which installs the core Wan 2.1 / 2.2 preset with both 14B expert pairs (about 64 GB, of which 28.6 GB for the image-to-video pair) so that shots can start from a frame. Both run a 1-second text-to-video clip with 6 steps and give it more time with `smoke.timeout_seconds`: 600 s each (measured with the files present: 4 min 02 s for the Lightning check clip with nothing in memory yet; 2 min 51 s for the image-to-video recipe with the text-to-video experts already in memory). The two MiniMax-H3 recipes run no first generation: on a 12 GB card, loading MiniMax-H3 alone took more than those 5 minutes, so their test generation always timed out. They have no "Validate the pipeline" step: that step of the core builds a test form without a Video Director document, which every Video Director preset rejects (the core `wan22-starter` recipe stops there too). The MiniMax-H3 recipe accepts the DiT of Comfy-Org or of Wan2GP, whichever is already installed.
- **Docker Desktop on Windows.** WSL 2 gives Docker half of the host's RAM by default. To give PotionUI the RAM a preset needs, raise it in `%UserProfile%\.wslconfig` (`[wsl2]`, `memory=…`), then run `wsl --shutdown`.

**How they were measured.** On the RTX 4070 Ti of the Hardware section, with the code of this branch, in a container limited with `--memory` equal to `--memory-swap` (no swap), at the full RAM tier and 3 GB below it (16, 13, 32, 29, 62 GB; the Docker VM had 62 GiB in all). For the 8 GB presets the card was capped with `POTIONUI_VRAM_CAP_GB=7.99` (what an 8 GB card reports) and `gpu_max_vram` 6 (what the engine derives for it). A second process that holds VRAM does not stand in for a smaller card on Windows: a container under WSL 2 does not see the VRAM that another one holds. VRAM is the engine's own peak (`peak_vram_mb`, the torch high-water mark); `nvidia-smi` also counts the cache of the allocator. RAM is the cgroup's anonymous memory; its `memory.current` also counts the file cache of the model files. Each figure comes from one 5-second clip, cold start included.

| Preset | RAM limit | Result | Time | VRAM peak (engine) | Process RAM peak |
|---|---|---|---|---|---|
| Wan 2.1 T2V 1.3B (8 GB) | 32 GB, 29 GB | done | 5 min 55 s, 5 min 40 s | 5.2 GB | 10.7 GB |
| Wan 2.1 T2V 1.3B (8 GB) | 16 GB | refused by the engine before sampling: it counts the file cache as used RAM and did not see the 2.6 GB + 2 GB it wants for streaming | — | — | 7.2 GB |
| Wan 2.2 TI2V 5B (8 GB), 832×480 | 32 GB, 29 GB | done | 4 min 51 s, 4 min 38 s | 5.5 GB | 18.6 GB |
| Wan 2.2 TI2V 5B, 1280×704 | 32 GB | stopped after 38 min: the 30 steps took 26 min, then the Wan 2.2 VAE decode overflowed the 8 GB (11.9 GB on the card, 15.7 GB of shared memory) | — | — | 17.0 GB |
| MiniMax-H3 (12 GB) | 32 GB | done | 9 min 48 s | 5.0 GB | 24.5 GB |
| MiniMax-H3 (12 GB) | 29 GB | killed for lack of memory after 8 min 37 s | — | — | 21.0 GB |
| MiniMax-H3-Fast (12 GB) | 32 GB | killed for lack of memory after 5 min 08 s | — | — | 19.0 GB |
| MiniMax-H3-Fast (12 GB) | 62 GB | done | 6 min 11 s | 5.0 GB | 25.6 GB |

The two MiniMax-H3 presets therefore declare 64 GB: the base one finished with 32 GB but without margin, the Fast one did not.

**Wan 2.2 14B on 12 GB.** Measured on the same card with the whole card given to the engine and its default settings (`gpu_max_vram` 10, `text_encoder_placement` `auto`), in a container without a RAM limit on a Docker VM of 62 GiB:

| Run | Result | Time | VRAM peak (engine) | Process RAM peak |
|---|---|---|---|---|
| Wan 2.2 14B Lightning (12 GB), 832×480, 5 s, models already in memory | done | 3 min 24 s | 8.1 GB | 34.7 GB |
| Core Wan 2.1 / 2.2, image to video, 832×480, 5 s, 6 steps, CFG 1, image-to-video pair read from disk | done | 5 min 21 s, of which 1 min 05 s to load | 6.9 GB | 34.7 GB |
| Recipe `vp-wan22-14b-lightning-12gb` check clip, 1 second, nothing in memory yet | done | 4 min 02 s | — | — |
| Wan 2.2 14B Lightning (12 GB), 832×480, 1 s, models already in memory | done | 56 s | 8.2 GB | 34.7 GB |
| Recipe `vp-wan22-14b-i2v`, text-to-video experts in memory | done | 2 min 51 s, its 1-second clip 2 min 41 s | 8.9 GB | — |

Both 5-second runs failed on this card before the engine change delivered with these presets: the Lightning run killed the PotionUI process (a CUDA out-of-memory error raised while freeing pinned host memory, which no Python handler can catch), and image to video ran out of memory while encoding the first frame, beside a text encoder that was still on the card. The engine now hands the allocator's idle memory back to the driver before it frees pinned memory and after it evicts the text encoder, and clears the card before a first-frame encode. Until 22 October 2026 the Lightning recipe check ran 30 steps at CFG 5 instead of the 6 steps of its speed profile and took 8 min 54 s; the recipe check form now lets the speed profile set them.

**What does not fit on 12 GB yet.** LTX-2.3 22B distilled: see LTX.

**Files.** Each model picker recommends one tier, recognised by SHA-256 or else by file name, so the Wan2GP name works before the catalog has hashed the file. The 8 GB presets recommend the 1.3B DiT (`wan2.1_t2v_1.3B_fp16.safetensors`) or the 5B DiT (`wan2.2_ti2v_5B_fp16.safetensors`, converted to fp8 when it loads on an 8 GB card), the fp8 UMT5-XXL text encoder and the matching VAE (`wan_2.1_vae.safetensors` or `wan2.2_vae.safetensors`). For the MiniMax-H3 presets the int4 `convrot_w4a4` DiT is not recommended: the native engine cannot read it.

| Model | MiniMax-H3 (12 GB) | MiniMax-H3-Fast (12 GB) |
|---|---|---|
| DiT | `minimax_h3_fl2va_pruned_int8_convrot.safetensors` (Comfy-Org) or `MiniMax-H3-FL2VA-pruned_rank8_int8_convrot.safetensors` (Wan2GP) | `fastvideo_fasth3_8step_v2_pruned_int8_convrot.safetensors` |
| Text encoder | `qwen3vl_32b_minimax_h3_nvfp4_awq.safetensors` | the same |
| Video VAE | `minimax_h3_video_vae_int8_convrot.safetensors` | the same |
| Audio VAE | `minimax_h3_audio_vae_fp32.safetensors` | the same |

- **The 8 GB presets.** They copy the pipeline of the core Wan 2.1 / 2.2 preset unchanged and read its I2V Models, SVI Pro and (for the 5B) Advanced tabs, the first two hidden: the pipeline needs their fields, and a hidden field is not required. Their Video Director declares `t2v` alone with shots of up to 5 seconds, so Video Producer never sends them a frame (warning `text_only_preset`). The 5B offers no 720p: on 8 GB its decode overflowed (see the table). The engine samples every Wan model with a shift of 8.0 where the 5B's official setting is 5.0; the form does not expose the shift.
- **Settings of the MiniMax-H3 presets.** 832×480 (480×832, 960×544 and 544×960 are offered, and 1344×768 stays in the list), 124 frames (5.17 s at 24 fps), one clip, sampler Res multistep with the Simple scheduler, a keyframe detail budget of 1× the output area, and the engine's automatic memory handling. The base model runs 20 steps (the Custom speed profile; Quality and Turbo are still there), Fast its fixed 8. In Video Producer a draft follows the `draft_resolution` setting (832×480 by default) and a re-rendered final of a 16:9 project takes 1344×768.
- **Prerequisites.** The native backend option `text_encoder_placement`, delivered by the core change "Stream the text encoder from host RAM when it does not fit in VRAM" (pull request M4-S4/PotionUI#2, merged into this branch): leave it on `auto`, which streams a text encoder that does not fit from system RAM, or set it to `stream`. Without that option the presets load but the text encoder still runs out of GPU memory. The streamed encoder, the part of the 20 GB DiT that does not fit on the card and the rest of the process share the system RAM: `requires` declares 12 GB of VRAM (minimum and recommended) and 64 GB of RAM.
- **Speed.** Everything that does not fit on the card streams from system RAM, so expect the prompt encoding and every step to take noticeably longer than on a card that holds the model; the estimate warns `vram_stream` and does not block. Measured on a 12 GB card (see Hardware): a 5-second draft took 5 min 57 s with MiniMax-H3-Fast (12 GB) and 7 min 26 s with MiniMax-H3 (12 GB) with 67 GB given to Docker, and 9 min 48 s for MiniMax-H3 (12 GB) in a container limited to 32 GB.

### SeedVR2 for finals

- Making a take final upscales it. For a Wan, LTX, MiniMax-H3 Fast, MiniMax-H3 VDN, 12 GB MiniMax-H3 or cloud take that is SeedVR2 (its `video_upscale` mode), to 720p, 1080p, 1440p or 2160p (shown as 4K); for a take of the base MiniMax-H3 preset, which has an `upscale` mode, it is the upscale mode of that preset itself, whose Target Size only has two values, so 720p and 1080p give HD and 1440p and 2160p give 2K. The other choice of the **Make final** window, **Re-render at full resolution**, generates the shot again at the highest resolution of the preset with the same seed. See Generation › Final takes.
- The DiT comes in four sizes: 3B fp8 (3.39 GB), 3B fp16 (6.78 GB), 7B fp8 (8.24 GB) and 7B fp16 (16.48 GB), plus a VAE of about 501 MB. SeedVR2 also needs a prompt embedding file. PotionUI's hardware page says it scales down cleanly to small cards: the batch size follows about 72 % of the free VRAM and is halved on an out-of-memory error.
- When no SeedVR2 preset is assigned to a user, the Upscale choice of the Make final window shows "Upscaler not available" and only the re-render is offered. A take of the base MiniMax-H3 preset still upscales, because its preset has an `upscale` mode. The Fast and VDN variants and the 12 GB presets have none: without SeedVR2 their takes can only be re-rendered, and a client that asks for the upscale anyway gets 409 `blocked` with the block `upscale_unsupported`, whose message invites to install SeedVR2 or to render the take again.
- Time: on the 12 GB card of the Hardware measures, the upscale of a 5-second Wan draft to 1080p took 2 h 27 min 45 s. Plan quotas and expectations on that scale.

### Cloud presets

- **OpenRouter Video** and **Gemini Video** come with their provider plugins. Install and assign them like any other preset, and turn on a video model in the backend's catalog. The page lists each enabled model by name under its backend.
- Their resolution, duration and aspect ratio come from the parameters that the model declares (the canonical parameters `resolution`, `duration_s` and `aspect_ratio` of the cloud catalog). A draft takes the default resolution of the model, a final the largest; the duration is the closest the model accepts, and a shot longer than the model's maximum is cut with `duration_clamped`. A model that can only start from an image blocks a shot without a first frame (`no_model`).
- The preset is tied to a backend through its driver. `GET /me` gives each preset its `driver` and, for a cloud preset, `backend_id`, the first enabled backend with that driver.

## Generation

This section is the reference for how a take is made, estimated, finished and followed, and for its routes, codes and tables. The routes sit under `/api/plugins/video-producer` and need a signed-in user.

### How a take is made

A **take** is one video of one shot, made by one PotionUI generation. **Generate selection** asks for one take per shot and per variant (A, B, and so on), each with its own seed and its own generation. The letters continue for each shot and each quality: a second generation of a shot at the same quality gets the next free letters (C, D…), and a letter freed by deleting a take can be used again. A retry and a final keep the letter of the take they come from, so a failed take and its retry share a letter; Video Producer never asks a generation for several outputs (`quantity` stays 1).

1. The page saves the project, then sends `POST /projects/{id}/generate`. The server builds the requests from the saved project, so a refused save means no generation ("The project could not be saved: generation not started.").
2. For each shot the server builds a Video Director document (`schema_version` 1) with the mode, the settings (frame rate, duration, resolution, seed), one segment and the media. The prompt is the shot prompt linked to the shot, or else the global prompt that covers most of its interval, followed by the five fields of the global direction that are filled in (world, characters, photography, palette, pacing), one per line. Nothing is translated and no label is added.
3. The composition follows the profile. FL2VA: first and last frames linked to the shot give `flf`, a first frame alone gives `i2v`, and no frame gives `t2v` with the warning `fl2va_no_frame`. Ref2VA: mode `refs` of the base MiniMax-H3 preset, with the shot's own references followed by the global ones and the fresh reference videos of its 3D shots (at most 9 images, 3 videos and 3 audio files; see The 3D scene); a shot with no usable reference is blocked (`no_references`). Hybrid AV: the same document as FL2VA on a MiniMax-H3 preset, whose model makes the sound itself; the audio driver of the workshop is not sent.
4. The duration is the one of the shot, cut to the maximum of the preset (`duration_clamped`). The resolution follows the Settings section. The seed is drawn by the server for each take (and kept); a retry and a re-render reuse the seed of the take they come from.
5. The request goes to PotionUI as the owner of the project, even when an admin asks, with the idempotency key `vp:<take id>`. A take past `max_parallel_jobs` is created `queued` with no generation and is submitted later by the follow-up task, from the request that was frozen in its `request` column.

From the project, a take uses the direction, the shot prompts, the frames, the references, the aspect ratio and the shots; from the page it takes the engine, the quality and the number of variants. The other controls of the Advanced workshop are not sent (see What stays simulated).

### Required models

For each `model` field that the chosen mode of the preset requires, Video Producer takes the first recommended file of the preset that is installed and reachable, and passes it as `model:<id>`. The recommendations are matched by SHA-256, and else by file name: when a preset gives no SHA-256 (the SeedVR2 case) or the catalog has not hashed the file (the Wan2GP DiT of MiniMax-H3 (12 GB)). A field with no installed recommendation blocks the generation with `missing_models`, and `data.fields` lists the fields. The fields are:

- Wan: `text_encoder`, `vae`, then `t2v_high_noise_model` (and `t2v_low_noise_model` when it is installed) for text-only shots, `i2v_high_noise_model` (and `i2v_low_noise_model`) for first-frame and first-and-last-frame shots.
- MiniMax H3: `model`, `text_encoder`, `video_vae`, `audio_vae`. The upscale mode of a final of the base MiniMax-H3 preset also needs `upscale_model`, which the fifth setup step checks too.
- SeedVR2: `diffusion_model`, `vae`, `prompt_embedding`. These are also the files of the finals of Wan, LTX, MiniMax-H3 Fast and VDN and cloud takes.

A file that exists on this machine but not on the Studio server worker passes the check and then fails on the worker (see Troubleshooting).

### The estimate

`POST /projects/{id}/estimate` takes the same body as `generate` (`shots`, `quality`, `variants`, `preset_id`, `model_id`, and `production`, which is `render3d_ai` in the “3D render + AI” output mode) and answers without starting anything:

| Key | Content |
|---|---|
| `shots` | One entry per shot: `shot_id`, `director_mode` (`t2v`, `i2v`, `flf`, `refs` or `director`), `seconds`, `resolution`, `fps`. |
| `vram` | `estimate_gb`, `free_gb`, `total_gb`, `streams`, `unknown`, `backend_id`. See GPU memory. |
| `time` | `seconds`, the expected total for all shots and variants, or `null` with no measure, and `samples`, the number of measures behind it. See Time calibration. |
| `quota` | `limit`, `used`, `remaining`, `exempt`, `needed_minutes`, `applies` (false for a cloud engine) and `blocks`. |
| `cost` | For an admin and a cloud model: `total_usd`, `known`, `message`. `null` for a user who is not an admin and for a native preset. |
| `blocks` | What stops the generation. |
| `warnings` | What the user should know. |

The page asks for it half a second after the last change, once the project is saved, with one request in flight at a time ("The estimate updates once the project is saved."). The Production bar shows the time, the memory and the quota (or the cost, for an admin) in a short line; hovering it gives the detail, for example "Time ≈ 4 min on MiniMax H3 (measured on 3 takes)" or "Time: — (no measure yet on MiniMax H3)", "Memory ≈ 22.5 GB, 16.0 GB free on Local Generation", "Quota: 5 min needed, 40 of 60 min left this month" ("Quota: exempt" for an exempt admin, "Cloud: no GPU quota used" for a cloud engine) and, for an admin, "Cost ≈ $0.84" or "Cost: unknown for this model".

### Blocks and warnings

`generate`, `final` and `retry` check the blocks again on the server. When one applies, the answer is 409 `blocked` and `detail.data.blocks` lists them, each as `{code, message, data?}`. The `message` is English; the page writes its own translated text from the `code` for every block, `upscale_unsupported` included (the keys `generation.block.*` of its dictionaries), and falls back to the English message for a code it does not know. The Make final window already greys the Upscale choice for a take that cannot be upscaled, so such a request is rarely sent.

| Block | When | `data` |
|---|---|---|
| `no_shots` | None of the shots exists in the project. | |
| `no_preset` | The preset is unknown, not assigned to the user, or has no mode that the Video Director can run. Also, for an upscale: SeedVR2 is not available to the user and the take does not come from an assigned MiniMax-H3 preset. | `preset_id` |
| `upscale_unsupported` | An upscale of a take of an assigned MiniMax-H3 variant that has no `upscale` mode (Fast, VDN, the 12 GB presets), when SeedVR2 is not available to the user. The message invites to install SeedVR2 for final takes, or to render the take again at full resolution. The page shows its own sentence, "Upscaling this take needs SeedVR2: ask an administrator to install it, or render the take again at full resolution." (`generation.block.upscaleUnsupported`; in French "Agrandir cette prise demande SeedVR2 : demandez à un administrateur de l’installer, ou générez la prise à nouveau en pleine résolution."): in the Make final window under the **Upscaler not available** badge, as the tooltip of the Make final button of the take card, and in the message of a refused request. | `preset_id` |
| `profile_unsupported` | Ref2VA or Hybrid AV on a preset that cannot generate it. | `profile`, `preset_id` |
| `missing_models` | A required model field has no installed recommended file, or a LoRA that the preset selects by default is not installed. Video Producer finds a default LoRA by its file name and sends it as an installed model. | `fields` |
| `quota_exceeded` | The takes need more minutes than the user has left. | `needed_minutes`, `remaining` |
| `no_model` | A cloud preset without a valid video model, or a model that needs a first frame for a shot that has none. | `model_id` or `shot_id` |
| `no_references` | Ref2VA on a shot with no usable reference. | `shot_id` |
| `refs_preset_needed` | The “3D render + AI” output mode on a preset that is neither a MiniMax-H3 preset with its `refs` mode nor LTX-2.5. | `preset_id` |
| `layout_lora_missing` | The “3D render + AI” output mode on LTX-2.5 without the Layout-To-Render IC-LoRA installed (`ltx-2.5-22b-ic-lora-layout-to-render-1.0.safetensors`, from `Lightricks/LTX-2.5-22b-IC-LoRA-Layout-To-Render`). | `file`, `repo` |
| `source_unavailable` | The video of the take to upscale is no longer in the PotionUI history. | |

| Warning | When | `data` |
|---|---|---|
| `vram_stream` | The estimated memory is above the free VRAM: the model will stream through host RAM, slower. | `estimate_gb`, `free_gb` |
| `vram_unknown` | PotionUI could not estimate the memory. | |
| `time_unknown` | No take of this preset was measured at this resolution yet. | |
| `fl2va_no_frame` | The shot has no first frame: it is generated from text only. | `shot_id` |
| `text_only_preset` | The shot has a first frame but the preset only declares the `t2v` composition (the two 8 GB Wan presets): the frames are not used and the shot is generated from text only. | `shot_id` |
| `duration_clamped` | The shot is longer than the preset or the model allows: it is cut. | `shot_id`, `max` |
| `stale_guide` | A 3D shot changed after its reference video was rendered: the old video is still sent. | `shot_id` |
| `guide_needs_refs` | A shot with the FL2VA profile has a 3D reference video, which that composition does not read. | `shot_id` |
| `render_missing` | In “3D render + AI”, a shot without an up-to-date reference video: it is generated without one. | `shot_id` |
| `layout_no_frame` | In “3D render + AI” on LTX-2.5, a shot without a first frame: the take keeps the look of the 3D render. | `shot_id` |
| `layout_guide_short` | In “3D render + AI” on LTX-2.5, a reference video that conditions fewer frames than the shot has (rendered before the 1 + 8k rule): render it again. | `shot_id`, `control_id`, `covered`, `needed` |

The page shows the first block in the Production bar (it disables the buttons) and the first warning next to it, with the full list in the tooltip. `vram_unknown` and `time_unknown` only appear in the estimate tooltip.

### Time calibration

The plugin keeps its own time measures in `video_producer_calibration`. A row is written when a take finishes: the preset, the backend PotionUI used (`backend_id`), the resolution, the seconds of video and the duration of the generation in milliseconds (`duration_ms`). An upscale take is measured under the upscaler preset, at the size it produces.

The estimate is the median of `duration_ms / 1000 / seconds` over the last 20 rows of the preset, the backend and the resolution, times the seconds asked for and the number of variants. A measure serves only the backend that rendered it: two native backends never share their rows, and with no backend known there is no measure. The backend is the one that the memory preview names (a cloud model uses its own backend); when that preview fails, or when there is no row, the time is `null`, the page shows "—" and the estimate carries `time_unknown`. `time.samples` is the number of rows behind it. The same ratio sets the minutes that a take reserves from the quota (see Quotas); for a `final` or a `retry` it is the one measured on the backend of the take they come from. The table is shared by all the users of the instance, and the plugin never deletes its rows, not even with the project or the take they came from.

### GPU memory

For a native preset, the server asks PotionUI for a memory preview of the first shot (`preview_memory`) without starting anything. It reports a checkpoint-based estimate, which is a lower bound made from the size of the model files and an activation term, never a guarantee, and the free and total VRAM of the device of the backend that would run it. `streams` is true when the estimate is above the free VRAM: the native engine then streams the overflow from host RAM, which is slower, and the estimate carries `vram_stream` ("Will stream through host RAM, slower."). It is a warning, never a block. If PotionUI cannot give an estimate the answer is `unknown: true` with `vram_unknown`, again without blocking. A cloud engine has no memory figure.

The overflow needs its size plus about 2 GB of free host RAM; without it the engine refuses to start and the take fails (the core classifies it as `host_ram_oom`).

### Cloud cost

For an admin and a cloud model, the server asks PotionUI for the cost of the shots (`estimate_cloud_cost`). The prices are those of the catalog of the backend, filled in by the provider plugin. When the provider publishes no price for the model, `known` is false and the page says "Cost: unknown for this model". The cost is computed in the name of the admin who calls the estimate; a user who is not an admin gets `cost: null`. Spending is limited by the PotionUI plan limit **Cloud spend per month**, not by the GPU minutes.

### Final takes

`POST /projects/{id}/takes/{take}/final` (202) starts a new take, of quality `final`, linked to the take it comes from (`parent_take_id`) and carrying the same variant letter. The source take must be finished (409 `take_not_done` otherwise). The body is `{method, target}`.

- **`upscale`** enlarges the video of the source take as it is. For a Wan, LTX, MiniMax-H3 Fast, MiniMax-H3 VDN, 12 GB MiniMax-H3 or cloud take: SeedVR2, mode `video_upscale`, with the source video as `input_video`, `resolution_target` set to the target, `restoration_intent` `faithful` and a random seed. For a take of the base MiniMax-H3 preset, whose preset has an `upscale` mode: that mode, with the source video and its Target Size (`hd720` and `fhd1080` give `hd`, `qhd1440` and `uhd2160` give `2k`, or the nearest value the mode offers). The take has `kind` `upscale`; its `resolution` is the size it is expected to produce and its real size is written when it ends.
- **`render`** generates the shot again, with the same seed, preset, profile and model, at the largest resolution of the preset (for a cloud model, the largest the model declares). The request is rebuilt from the current project. The take has `kind` `render`.
- `target` is one of `hd720`, `fhd1080`, `qhd1440`, `uhd2160`, shown as 720p, 1080p, 1440p and 4K. It is required but a render ignores it. The window proposes the resolution of the project as the default.
- A final reserves GPU minutes like any native take and is checked against the quota. The page puts a finished final on the shot at once, in place of the draft (toast "Final version ready and applied to the shot").

### Following the takes

The task that follows the takes (`backend/tracker.py`) runs on the application loop. It is started by the hook `plugin.lifecycle.ready`, stopped by `plugin.lifecycle.disable` for this plugin, and started again by the first `generate`, `final` or `retry` if it is not running (for example when the plugin was enabled after the application started). While takes are `queued` or `running` it runs every 2 seconds, otherwise every 10 seconds. Each round:

- reads the state of the generation of every active take and updates its progress, step (`current_step` or `message`), start time and backend, or ends it;
- hands the queued takes of each user to PotionUI while that user has fewer than `max_parallel_jobs` takes in flight.

A take ends as:

- **done**: the first video file of the generation becomes the take (path, file id, width, height, duration, frame rate, thumbnail), its URL is `/api/media/generations/<generation id>/<file name>` and its thumbnail the same URL with `?size=medium`. The server writes the calibration row, adjusts the reservation of the quota (when the take has one) and sends the notification `video-producer.take_done`.
- **failed**: `error_code` and `error_message` come from PotionUI (the safe user message), the reservation is refunded and the notification `video-producer.take_failed` is sent. A generation that was running when the server restarted is marked failed by PotionUI and the take follows.
- **cancelled**: the reservation is refunded.

Every end is applied once. The two hooks below do the same job as the task, as soon as PotionUI fires them, and whichever comes first wins:

| Hook (manifest) | Handler | Effect |
|---|---|---|
| `generation.after_complete` | `hooks.generation_hooks.on_after_complete` | Ends the take of a generation that completed or was cancelled. |
| `generation.failed` | `hooks.generation_hooks.on_failed` | Ends the take of a generation that failed, with the error code and the message of PotionUI. |

The manifest also declares `plugin.lifecycle.boot` (creates the tables), `plugin.lifecycle.ready`, `plugin.lifecycle.disable` and `notification_type.register`. Calls to PotionUI that need a user are made as the owner of the project (`src.plugin_api.identity`); an owner who no longer exists fails the take with `user_not_found`.

The page follows the takes by the generation progress of PotionUI (`window.__potionui.generation.subscribe`) and, whatever it gives, by `GET /projects/{id}/queue` every 5 seconds while takes are active. Closing the page does not stop the generations: the takes are there when the user comes back.

### Routes

Answers are `{success: true, data}`; errors are described under Projects and media › Errors. A take route needs the project to be the caller's, or the caller to be an admin; otherwise the answer is 404 `project_not_found` or `take_not_found`.

| Route | Body | Answer |
|---|---|---|
| `GET /projects/{id}/takes` | | `{takes}`, oldest first. |
| `POST /projects/{id}/estimate` | `{shots, quality, variants, preset_id, model_id?, production?}` | The estimate above, with `production` and `renders`. `shots` is a list of shot ids, `quality` `draft` or `final`, `variants` an integer from 1 to 16, `model_id` the catalog id of a cloud model or `null`. `production` is `ai` (the default, the page's « Génération IA »), `render3d` (« Rendu 3D », which needs no `preset_id`) or `render3d_ai` (« Rendu 3D + IA »). Each shot also lists in `guides` the ids of the `scene3d` controls sent as its camera references. `renders` lists, for the shots asked for, `{shot_id, control_id, plan_id, asset_id}`: the latest up-to-date rendered 3D guide of the shot, the video the shot takes as it is in the 3D render mode, where `shots` stays empty and nothing is reserved (block `no_render` when no shot has one, warning `render_missing` for each shot without one). In Ref2VA, and always in `render3d_ai`, the videos of the up-to-date `scene3d` controls of a shot are sent first among its reference videos (3 at most); the prompt is the six-section document of the MiniMax-H3 reference mode (see The 3D scene). Warnings: `stale_guide` for a stale guide, left out; `guide_too_short` for a guide video under 2 s; `guide_needs_refs` for a shot with a guide generated without references (FL2VA, Hybrid AV, cloud); `render_missing` in `render3d_ai` for a shot without a guide sent. `render3d_ai` is blocked by `refs_preset_needed` unless the preset is a MiniMax-H3 preset with a `refs` mode or LTX-2.5. On LTX-2.5 a shot with a guide is a `director` shot: its latest up-to-date guide video is the reference of the Layout-To-Render IC-LoRA, and its `guides` names that one control (see The 3D scene). |
| `POST /projects/{id}/generate` (202) | The same, and `label?` (at most 200 characters, validated and not stored) | `{takes, renders}`: one take per shot and variant, and the `renders` of the estimate; in the 3D render mode `takes` is empty and the page puts each render's asset on its shot. 409 `blocked` when a block applies. |
| `GET /projects/{id}/queue` | | `{takes, slots}`: the queued and running takes, and `slots` with `in_flight` (the owner's takes handed to PotionUI) and `max` (`max_parallel_jobs`). |
| `POST /projects/{id}/takes/{take}/choose` | `{chosen}` | `{take}`. Choosing a take unchooses the others of the shot; only a finished take can be chosen (409 `take_not_done`). |
| `POST /projects/{id}/takes/{take}/flag` | `{flag}`: `keep`, `reject` or `null` | `{take}`. |
| `POST /projects/{id}/takes/{take}/final` (202) | `{method, target}` | `{take}`, the new final take. |
| `DELETE /projects/{id}/takes/{take}` | | `{deleted}`, the id. A take in flight is cancelled first and its reservation refunded; the PotionUI generation and its video stay in the history of the user. |
| `POST /takes/{take}/cancel` | | `{take}`. Cancels the generation if it was handed over, refunds the reservation, and the take becomes `cancelled`. |
| `POST /takes/{take}/retry` (202) | | `{take}`, a new take with the same shot, seed, quality, preset and profile (a render is rebuilt from the current project). Only for a failed or cancelled take (409 `take_not_retryable`); the old one stays. |
| `POST /projects/{id}/scenes/from-image` (202) | `{sceneId, assetId, time, name?}` | `{job}`: a Gaussian Splat of an asset of the project made by the Image to Splat preset (`01KX47GSP4TQ0000000000SP3D`, mode `img2splat`), its models resolved like a take's. An image asset is sent as it is; a video asset needs `time`, the second its frame is taken at (stored in the owner's library). `sceneId` is the id of the scene in the document, `name` is validated and not stored. One GPU minute is reserved when the owner's minutes are limited, then adjusted to the time the generation took, and refunded when it fails or is cancelled. 409 `blocked` with `no_preset`, `missing_models` or `quota_exceeded`; 409 `scene_jobs_busy` (with `limit`) while the owner already has 2 scenes queued or running, every project included; 413 `storage_full`, before anything is reserved, when the project's scene files are at their cap or the owner's storage plan has no room left (see `POST /projects/{id}/scene-files`); 404 `asset_not_found` or `media_not_found`; 422 `invalid_source` for an asset that is not an image or a video of the library or the history; 502 `extract_failed`. A request the core refuses gives a `failed` job, and so does a finished splat that does not fit the project's cap or the owner's plan (`storage_full`, refunded). The splat is copied into the project's `work/` folder, checked, then moved into place under its id; a copy that fails three rounds of the follow-up task in a row ends the job `failed` with `finish_failed`, refunded. |
| `GET /projects/{id}/scenes/jobs` | | `{jobs}`, oldest first, each `{id, sceneId, status, progress, error, errorCode, fileId, count, view, generationId, createdAt, finishedAt}`. `status` is `queued`, `running`, `done`, `failed` or `cancelled`; once `done`, `fileId` is the splat copied to the plugin's storage (read it with `GET /projects/{id}/scene-files/{file}`), `count` its gaussians and `view` `{fov, aspect, depth}` from its `potionui_view` header comment, or `null`. The page copies these fields into the splat scene of the document. |
| `POST /projects/{id}/scenes/jobs/{job}/cancel` | | `{job}`. Cancels the generation, refunds the reservation; 404 `job_not_found` for a job of another project. |

`GET /me` is extended for generation. `engines` lists the enabled native and cloud backends (among others `id`, `name`, `kind` `local`, `remote` or `cloud`, `driver`, `execution_device`, `vram_total_gb`, `vram_free_gb` and `is_default`), and a cloud backend carries its enabled video models in `models` (`id`, `name`, `provider_model_id`, `tasks`, `typical_seconds`, `max_seconds`). `presets` lists the video presets and the upscaler preset that the user may run; a video preset carries `requires`, `profile` (the memory profile it is set up for, such as `"12 GB"`, or `null`), `modes`, `video_director`, `resolutions` (the options of the resolution field of the main mode), `fps`, `fps_locked`, `limits` (`default_duration`, `max_duration`), `director_modes`, `profiles` (the ones it can generate), `upscaler`, `driver` and, for a cloud preset, `backend_id`. `features.upscaler` tells whether an upscaler preset is assigned to the user, and `upscale_targets` lists the four targets. `settings` carries the plugin settings, among them `draft_resolution` and `max_parallel_jobs`.

### Take errors

These codes complete the table of Projects and media › Errors:

| Code | Status | When |
|---|---|---|
| `blocked` | 409 | `generate`, `final` or `retry` is refused. `data.blocks` lists the blocks. |
| `take_not_found` | 404 | The take does not exist, is not in that project, or the caller cannot reach its project. |
| `take_not_done` | 409 | Choosing a take that is not finished, making final a take that is not finished, or retrying an upscale whose source is no longer finished. |
| `take_not_retryable` | 409 | Retrying a take that is not failed or cancelled. |
| `owner_not_found` | 409 | An admin acts on a project whose owner no longer exists. |
| `invalid_request` | 422 | A body that is not a JSON object, or a missing or malformed `shots`, `quality`, `variants`, `preset_id`, `model_id`, `label`, `chosen`, `flag`, `method` or `target`. |

When a take itself fails, its `error_code` is one of the plugin's own codes or the category that PotionUI gives the failure:

- the plugin's: `preset_not_available`, `duplicate_submission`, `invalid_request`, `no_backend` (PotionUI has no backend that can run it now), `submit_failed`, `user_not_found`, `generation_not_found`, `no_output` (the generation ended without a video) and `generation_failed` (no more precise code);
- PotionUI's categories: `cuda_oom` (out of GPU memory), `host_ram_oom` (out of host RAM while streaming weights), `missing_model_file`, `disk_full`, `corrupt_weights`, `auth_required`, `backend_unreachable`, `banned_prompt`, `content_blocked`, `content_check_unavailable`, `unclassified`, and for cloud models `cloud_auth`, `cloud_credits`, `cloud_refused`, `cloud_rate_limited`, `cloud_invalid_request`, `cloud_unavailable`, `cloud_timeout`, `cloud_failed` and `cloud_expired`.

The page translates 28 of these codes (all but `invalid_request`) into a sentence in the language of the user: the keys `generation.failed.<code>` of its dictionaries, for example `cuda_oom`: "The server’s GPU ran out of memory: try a lower resolution or fewer frames." For any other code it shows the stored `error_message` (English), and "The generation failed" followed by the code in brackets, when there is none. The translated codes are the list `FAILURE_CODES` of `frontend/src/lib/generation.js`, and a test of the page fails when a code has no sentence in both languages.

### Tables

The tables are described under Projects and media › Tables (`video_producer_takes`, `video_producer_jobs`, `video_producer_calibration`). The table of the video exports, `video_producer_export_jobs`, is described under Exports › Tables.

## ffmpeg

Video Producer calls `ffmpeg` and `ffprobe`, as found on the `PATH` of the PotionUI process, for two things:

- **The assembled video.** ffmpeg joins the shots, the sound and the look of the sequence into an intermediate H.264 file, in one run or, for a long sequence of many files, in parts; then a last ffmpeg run writes the MP4 that the user downloads, with the settings of PotionUI's own video converter (`transcode_video` of `src.plugin_api`). See Exports › The assembled video. ffmpeg needs the `libx264` and `aac` encoders. The plugin's tests ran with ffmpeg 6.1, 8.0 and 9.0, and the export reads its filter graph with the option that the version of ffmpeg knows (see Exports › The assembled video); a build that lacks a filter or an option of the graph (for example `colortemperature`, or `normalize` of `amix`) fails the job with `ffmpeg_failed` and the message of ffmpeg.
- **A frame at a given time.** "Extract a frame at the playhead" asks for the frame at a number of seconds, and PotionUI reads the frame rate of the take with ffprobe to turn that time into a frame number. Without ffprobe the route answers 502 `extract_failed` ("The video's frame rate could not be read"). Without ffprobe the video export also treats every shot file as silent, because it cannot tell whether a file has a soundtrack: only the audio items of the timeline are mixed. The last image of the previous shot needs neither: PotionUI reads it with OpenCV.

How the install is checked and shown:

- The fourth setup step (`FfmpegReady`) is done when `ffmpeg` and `ffprobe` are both found (ffprobe next to ffmpeg, else on the `PATH`). While it is not done it says "Video Producer joins takes and exports the cut with ffmpeg, and reads media with ffprobe; ffmpeg is missing." (or "ffprobe is missing") followed by "Install ffmpeg with ffprobe on the server so both are on the PATH, then restart PotionUI." and offers **Read the guide**, which opens this page.
- `GET /me` carries `ffmpeg`: `true` when ffmpeg and ffprobe are both found, `false` otherwise. When it is `false`, the Video tab of the export window shows "ffmpeg is missing on the server: web and social exports need it." with a **Read the guide** link to this page for an admin and "Ask an administrator to install it." for anyone else, and the **Export** button is disabled. The server refuses a video export by itself with 409 `ffmpeg_unavailable`. The files for other software and the last-image seam frame work without ffmpeg.
- If you run PotionUI in Docker, check that the image contains ffmpeg and ffprobe.

## Exports

Three things are described here: four files for other software, built when the user asks; the assembled video, a background job; and the seam frame, an image taken from a take that joins two shots. The routes sit under `/api/plugins/video-producer` and need a signed-in user. As for every project route, the project must be the caller's, or the caller an admin; otherwise the answer is 404 `project_not_found` (see Projects and media › Access).

### Files for other software

`GET /projects/{id}/exports/{format}`, with `format` one of `fcpxml`, `otio`, `edl` and `srt` and the query parameter `media`: `path` (the default) or `name`. It is a GET and not a POST because the host's `api.download` only sends GET requests. Any other `format` or `media` answers 422 `invalid_request`, and `media` is checked for the SRT too although it changes nothing there.

The server builds the file from the project as saved (`projects.get_project`) and from the table of takes, never from what the page shows. The page saves the project before it asks, and a failed save stops the export ("The project could not be saved: nothing was exported."). The answer is the file as an attachment: `Content-Disposition: attachment; filename="<slug>.<extension>"; filename*=UTF-8''<name>`. The slug is the project name in ASCII: spaces become `_`, accents are dropped, `œ`, `æ`, `ß` and `ø` are spelled `oe`, `ae`, `ss` and `o`, each run of other characters becomes one `_`, and `video-producer` stands in when nothing is left ("Aube sur le port" gives `Aube_sur_le_port.edl`); the second name keeps the accents. A name that Windows reserves before its first dot (`CON`, `PRN`, `AUX`, `NUL`, `COM1` to `COM9`, `LPT1` to `LPT9`, in any case) gets a leading `_`: "nul.v2" gives `_nul.v2.edl`. The page names the files of its previews the same way (`slugify` in `frontend/src/lib/exports.js`), and both test suites check the same examples ("Cœur" gives `Coeur`, "Straße" gives `Strasse`, "CON" gives `_CON`).

| Format | Content-Type | Extension | What the file holds |
|---|---|---|---|
| `fcpxml` | `application/xml` | `.fcpxml` | FCPXML 1.10. One `format` resource named `FFVideoFormat<resolution><fps>` (for example `FFVideoFormat1080p25`), sized from the project resolution taken as a 16:9 frame (1280×720, 1920×1080 or 3840×2160); one `asset` per shot that has a file (the name of the shot, the length of its source, a `media-rep` whose `src` is a `file://` address); an event named "Video Producer" with a project named after the project and a sequence as long as the project (1 second at least). The spine holds an `asset-clip` per shot (`offset` its start in the sequence, `start` its in point in the source, `duration`) or a `gap` for a shot without file. Times are `frames/fps s`, rounded to the frame. Video only: no audio, title, fade or color. |
| `otio` | `application/json` | `.otio` | An OpenTimelineIO `Timeline.1` named after the project, whose `Stack.1` holds the track `V1` (Video) and one Audio track per track of the console, named `<id> · <name>`. `V1` has a `Clip.2` per shot (the name, the `source_range`, an `ExternalReference.1` whose `target_url` is the file, and `metadata.video_producer` with the `stage` and the `take` of the shot) or a `Gap.1` for a shot without file. An audio track has its items in time order with `Gap.1` between them; each item is a `Clip.2` with its name, its range and `metadata.video_producer` (`role`, `gain_db`), and no file reference. Times are `RationalTime.1` at the frame rate of the project. |
| `edl` | `text/plain; charset=utf-8` | `.edl` | CMX 3600, `FCM: NON-DROP FRAME`, CRLF line ends, the title in capitals. One event per shot, V track only: `001  VP001    V     C        <source in> <source out> <record in> <record out>`, then `* FROM CLIP NAME: <shot>` and, when the shot has a file, `* SOURCE FILE: <file>`. A shot without file is an event on the reel `BL` with no `SOURCE FILE` line. Timecodes are non-drop at the frame rate of the project; source timecodes count from the start of the file and record timecodes start at 00:00:00:00. |
| `srt` | `application/x-subrip` | `.srt` | SubRip cues, numbered, `HH:MM:SS,mmm --> HH:MM:SS,mmm`, UTF-8. The cues are the transcripts of the audio items (`transcript` of the asset, preceded by `<character>: ` when the asset has a character, `<character> : ` in French) and the titles of the sequence (the text, then the subtitle on a second line), sorted by start time; each cue lasts as long as its item. The language is the one the user picked in the page. |

Which file a shot has (`fileOf`, the same rule on the page and on the server):

- A shot with no asset, or whose asset has no file, has none: a `gap` in FCPXML, `Gap.1` in OTIO, the reel `BL` in the EDL.
- Otherwise the server looks for the file in this order: the finished take of the asset (its `resultId`, else the generation and file of its history origin), whose `file_path` is the file; the media that the asset's origin resolves to (a library item or a history file, resolved as the owner of the project); finally the name at the end of the asset's `src`, without its query string, which gives a name and no path. A generated asset whose take is unknown keeps the name `<label>_<quality>_<resultId>.mov`.
- `media=path` writes the absolute path of the file on the server's disk: as is in the EDL (`* SOURCE FILE:`) and in OTIO (`target_url`), as a percent-encoded `file://` address in FCPXML. When the storage is not a local disk (object storage) no path exists and the name is written instead; FCPXML then points to `file:///Video%20Producer/<name>`.
- `media=name` writes the base name of the stored file: the file of the take, or for a library source the stored name (`<uuid>.mp4`), not the name the user uploaded it under. The page never asks for it; it exists for clients that relink by name. The files of generated takes all have the same name, `1.mp4`, in different generation folders, so a name does not tell two takes apart.

The page builds the same four files in the browser (`frontend/src/lib/exchange.js`), for the preview in the export window. That copy names files by their base name, so the preview shows names where the downloaded file shows paths. Both generators are tested against the same golden files (see Development).

Opening them elsewhere: editing software that reads FCPXML 1.10 imports the `.fcpxml`, and the project arrives in the event "Video Producer". The addresses in the files are paths on the PotionUI server, so if the editing software runs on another computer the user copies the media there and relinks it. The window says the `.otio` opens in Resolve, in Premiere with a plugin and in Nuke Studio, and the `opentimelineio` Python package reads it. The plugin's tests check the form of the files (well-formed XML with every `asset-clip` pointing at a declared asset, one CMX event per shot, numbered cues, the OTIO read by `opentimelineio` when that package is installed); no test opens them in editing software.

### The assembled video

`POST /projects/{id}/exports/video` with the body `{"format": "web" | "social", "resolution": "720p" | "1080p" | "4K"}` queues an export and answers `202 {"job": …}`. `format` is required. `resolution` is optional and defaults to the resolution of the project, then to 1080p. `master` and `archive` are the simulated formats of the window and, like any other value, answer 422 `invalid_request`. After the body is checked, the refusals are: 409 `ffmpeg_unavailable` (no ffmpeg on the `PATH`), 409 `nothing_to_export` (no shot has a file that can be found), 409 `export_running` (an export of the same project is queued or running) and 429 `export_quota` (see Storage and quota).

| Format | Frame |
|---|---|
| `web` | The aspect ratio of the project. The shots are fitted inside it and the unused area is black (bars at the sides or at the top and bottom). |
| `social` | 9:16 whatever the project. The shots fill the frame and are cropped around their center. |

The short side of the frame comes from the resolution (720, 1080 or 2160 pixels), the long side from the aspect ratio, rounded to an even number. A 16:9 `web` export is 1280×720, 1920×1080 or 3840×2160; a 9:16 one, and every `social` export, 720×1280, 1080×1920 or 2160×3840.

A job is returned as:

| Key | Content |
|---|---|
| `id`, `project_id`, `format`, `resolution` | The job and what it renders. |
| `status` | `queued`, `running`, `done`, `failed` or `cancelled`. |
| `progress` | 0 to 100, with one decimal. |
| `step` | `assemble`, `mix`, `transcode` or `store` while it runs, otherwise `null`. |
| `file` | When `done`: `{name, size, url}`. `name` is `<slug>_<resolution>.mp4` and `url` is `/api/plugins/video-producer/exports/<job id>/file`. Otherwise `null`. |
| `media` | When `done`: `{kind: "library", item_id, url}`, the copy in the user's library (`url` is `/api/media/uploads/<file>`). Otherwise `null`. |
| `error` | When it failed or was cancelled: `{code, message}`. Otherwise `null`. |
| `created_at`, `finished_at` | Times in ISO 8601, UTC. |

How the sequence is assembled, from the saved document, with `filter_complex` graphs:

- **Inputs and command line.** Each shot that has a file reads it through an `-i` input, whose picture is decoded on at most 4 threads (`-threads 4`). Cuts of one file that follow each other forward (each `srcIn` at or after where the previous cut stopped) share one input, so ffmpeg decodes the file once; a cut that reads back, or the same part twice, opens its own input, because with a shared input ffmpeg keeps the frames of every cut that comes later in memory (measured with ffmpeg 6.1 and 8.0: three times the memory of separate inputs on 40 cuts in reverse order). A still image always has its own input. The server runs ffmpeg from the deepest folder that holds all the input files and names them relative to it, behind `./` (so that no file name can read as an option or as a protocol such as `concat:`); the filter graph and the output keep their absolute paths. The graph is written to a file that ffmpeg reads with `-/filter_complex` (FFmpeg 7 and later), or with `-filter_complex_script` before FFmpeg 7; FFmpeg 9 removed that one. The server asks `ffmpeg -version` once for each executable and takes `-/filter_complex` for a git build, for a version it cannot read, and when ffmpeg does not answer. Inputs that do not share a drive are named by their absolute paths.
- **Parts.** ffmpeg opens every input of a run when it starts and keeps a decoder for each. Measured with 720p files on a 24-thread machine: about 72 MB per input with the ffmpeg 6.1 of the Docker image (43 GB for 600 inputs) and 15 MB with ffmpeg 9 on Windows (9 GB); 4 decoding threads bring ffmpeg 6.1 to about 28 MB per input, with no loss of speed measured on 4K sources. Windows also limits a command line to 32,767 characters, about 650 inputs in different folders of the file storage. So a sequence that would open more than 40 inputs is assembled in parts: runs of consecutive shots that open at most 40 inputs each, written as `part-<round>-<n>.mkv` (the picture with the settings of the intermediate file, the sound of the shots in 32-bit float PCM, no audio item yet), then a last run that joins the parts, each read as a shot played whole for the length ffprobe measures, and mixes the audio items in. More than 40 parts take more rounds of parts (two rounds reach 1,600 inputs). More than 200 audio items are first mixed 200 at a time into `lanes-<n>.wav` files (float PCM), which the last run mixes as single items. The memory of ffmpeg and its command line therefore stay bounded whatever the length of the sequence, for one more H.264 encode of the picture per round. A test checks that a sequence in parts gives the picture, the timing and the loudness of its single run, in one round and in three.
- **Shots.** The shots of `clips` in document order, each at its `start`. Black, with silence, fills a shot that has no file, the holes between shots and the time between the last shot and the end of the sequence (the end of the last shot, audio item or title). A shot that has a file is cut from its `srcIn` for its duration, fitted to the frame (see above), and set to the frame rate of the project. An image is held for the duration of the shot, and a file that is shorter than the shot is held on its last image.
- **Look and fades.** The Color settings of the shot, only when they are not neutral: `eq=contrast=<contrast/100>:saturation=<saturation/100>:brightness=<exposure*0.125>` and, when the temperature is not 0, `colortemperature=temperature=<6500 - temperature*20>`. Then the fade in and fade out of the shot.
- **Sound.** The soundtrack of each shot's own file, when it has one, at 0 dB, and silence otherwise; the viewer does not play that sound but the export keeps it. On top, the audio items of the timeline: cut at their `srcIn`, delayed to their start, set to their gain plus the fader of their track in dB, with their fades. Muted tracks are left out, and when any track is soloed only the soloed tracks play. The sum is made by `amix` with `normalize=0`, without automatic leveling. The pan, the inserts (equalizer, compressor, filter), the sends, the automation and the master bus of the console are not applied.
- **Not in the video.** The titles and markers of the timeline, the prompts, reference frames, Control videos and 3D shots (a reference video that the “3D render” mode made the media of a shot is in the video like any media). The subtitles are never burned in: the SRT is a separate export.
- **Intermediate file.** `mezzanine.mp4` in the job folder: H.264 (`libx264 -preset veryfast -crf 14 -pix_fmt yuv420p`), AAC 192 k stereo at 48 kHz, as long as the sequence.
- **Delivery file.** A last ffmpeg run turns the intermediate file into `<slug>_<resolution>.mp4` with the settings of PotionUI's video converter: MP4 H.264 at the frame rate of the project, no wider than the frame, `faststart`, CRF 26 and preset `slow`, AAC 96 k (a test compares them with the converter's). The plugin runs it itself rather than through the converter, so that it reports its progress, can be cancelled and has no fixed time limit: the converter stops an ffmpeg call after 600 seconds, and the `slow` preset writes about 25 frames per second at 1080p and 6 at 4K on two threads (measured on a test pattern), so a 4K sequence of a few minutes on a small server would fail there. The intermediate file is deleted once this run has ended; the filter graphs, the parts and the audio mixes as soon as the assembly stops.
- **Stalled ffmpeg.** Each ffmpeg run of the export is killed when it writes nothing new (`-progress`) for 5 minutes, except in its last second, where ffmpeg finishes the file (`faststart` rewrites it). The job then fails with `ffmpeg_failed`, or `transcode_failed` for the delivery run, and the message "ffmpeg wrote nothing new for 5 minutes and was stopped." A work file that Windows, an antivirus or a synchronisation tool holds open is tried five times, 0.2 seconds apart, and then left: the export still ends `done`, and the leftover is swept (see Storage and quota).

| Stage | Progress | What runs |
|---|---|---|
| `queued` (a status, `step` is `null`) | 0 % | The job waits for its turn. |
| `assemble` | 0 to 50 % | The ffmpeg run. Its progress is the time written (`-progress`) over the length of the sequence, scaled to 0–70 %. In parts, the part runs share 0 to 50 % by their length. |
| `mix` | 50 to 70 % | The same run: the mix is in the same graph and only the label changes from 50 %. In parts, the run that joins them and mixes the audio items. |
| `transcode` | 70 to 95 % | The delivery run, by the time it has written over the length of the sequence. |
| `store` | 95 to 100 % | The copy in the user's library, then `done` at 100 %. |

Jobs:

- **Table and queue.** A job is a row of `video_producer_export_jobs` and, while it runs, a process kept in memory so that it can be killed. The queue is first in, first out, and one job runs at a time on the server, whoever owns it. A project has at most one export queued or running. The runner is a task of the application loop (`run_on_app_loop`): the first export request starts it, and so does the start of the application when jobs are waiting. A job reads the saved project when it starts to run, not when it was requested.
- **Cancel.** `DELETE /exports/{job}` on a queued or running job cancels it: the job becomes `cancelled` with the error code `cancelled`, the ffmpeg process is killed with every process it started (a launcher such as the Chocolatey `ffmpeg.exe` shim runs the real ffmpeg as a child that would otherwise go on) and the folder is deleted. Nobody is notified. This holds for every run of the job, the part runs and the delivery run included; between two runs the job stops before the next one. A cancel during the last step can leave the copy in the library.
- **Restart.** At startup, a job a stop left `running` becomes `failed` (`ffmpeg_failed`, "The server stopped during the export.") and its owner is notified; queued jobs go on. Disabling the plugin kills the ffmpeg process, with the processes it started, and stops the runner without ending the job, which becomes `failed` at the next start.
- **Library copy.** The final MP4 is stored as a video of the library of the user who asked, through `save_user_media`; if that fails, because the storage plan of the user is full for example, the job fails with `store_failed`. The routes serve the file from the export folder, and the library holds its own copy that survives the deletion of the job.
- **Notifications.** When a job ends the owner of the export gets **Video Producer: export ready** (`video-producer.export_done`) or **Video Producer: export failed** (`video-producer.export_failed`). The text reads "<project name>: the web video (1080p) is ready." or "…could not be exported." followed by the reason, and the metadata carry `project_id`, `job_id` and, for a success, the `url` of the file. Both types are on by default, and each user can tune them in their notification preferences. A cancelled export notifies nobody.
- **The page.** The export window asks `GET /exports/{job}` every second while it is open and every three seconds while it is closed, as long as a job of the project is queued or running; the export goes on without the window, a toast with **Download** appears when it ends, and the tracking resumes when the page loads a project (after a reload, from the moment the project opens). Reopening the window lists the jobs again and picks up the active one. When the job ends while the window is open and the host has no library window to show, a toast "<file> is ready" offers **Download**.
- **An admin** who exports another user's project gets the job, the folder and the library copy under their own account, and the media are resolved as the owner of the project.

As one measure, on the test server the 29-second starter sequence at 1080p took 11 seconds (about 6 to assemble and mix, about 5 to convert) and gave a 3.2 MB file. A long 4K sequence on a slow machine takes as long as its delivery run needs, with its progress shown.

### Seam frames

A seam frame is an image taken from a take and stored in the library, that the page sets as the first or last frame of a shot. It lets a shot start from where the previous one ended: the FL2VA profile starts a take on its first frame.

`POST /projects/{id}/shots/{shot_id}/seam-frame`. The body is optional. `{"source": "previous_last"}`, the default, takes the last frame of a take of the shot that comes just before `shot_id` in the order of `clips`. `{"source": {"take_id": "…", "at": "last" | <seconds>}}` takes the frame of that take at that time, `at` being `"last"` or a number of seconds from the start of the take's video, 0 or more.

- **Which take by default.** The take chosen for the previous shot (`clips[].take`) when it is finished and has a file, otherwise the most recent finished take of that shot that has a file.
- **What is stored.** PotionUI cuts the frame (OpenCV) and stores it as a PNG upload in the library of the project owner, even when an admin asks. The file is named after the video of the take, followed by `-frame-last` or `-frame-<seconds>s`, and it counts in the storage plan of the owner.
- **Answer.** `200 {"media": {…}}`: `kind` `library`, `item_id`, `media_type` `image`, `url` (`/api/media/uploads/<file>`), `filename`, `width`, `height` and `origin` (`{"kind": "library", "itemId": …}`), the shape of the answer of `POST /media/resolve`.
- **Errors.** See Export errors: 404 `shot_not_found`, 404 `take_not_found`, 409 `no_previous_take`, 422 `invalid_request`, 502 `extract_failed`. The code of PotionUI's media error is in `detail.data.code` (for example `not_found`, `not_a_video`, `extract_failed`, or `limit_exceeded` when the storage plan is full); the page reads it as `err.data.code`.
- **The route writes nothing in the document** (a test checks it). The page does: it adds an asset of `kind` `image` (name: the file name, or "Seam frame · <shot>"; `src`: the URL; `origin`: `{kind: "library", itemId}`; width, height and `res`) and a frame `{id, shotId, time, assetId, role, strength: 100}` as one undoable change, and the usual autosave saves it. `role` is `first` for "Use the previous shot’s last frame" and for an extraction in the first half of the shot, `last` for the second half; `time` is the start of the shot for `first` and the end of the shot minus 0.04 s for `last`, on the 0.04 s grid. For "Extract a frame at the playhead" the page sends `at` as the position of the playhead in the shot, plus the `srcIn` of the shot when that take is the one the shot plays; a playhead outside the shot counts as its start or its end.
- **Replacement.** A shot keeps one `first` and one `last` frame image. If one exists, the page asks "Replace the first frame?" or "Replace the last frame?" (buttons **Replace** and **Keep the current one**), then changes the frame in place (same id) and removes duplicates of that role. The earlier asset stays in the project's assets.
- **What reads it.** The generation takes the frames with the role `first` and `last` (older documents wrote `Début` and `Fin`, read the same way): a first frame alone gives an image-to-video take, both give a first-and-last-frames take. The color measure of the page (the **Match** fix and the continuity alerts) also uses them: for a seam it measures the last frame image of the previous shot and the first frame image of the shot when they exist, and the thumbnail of the shot for a side that has no frame image. The tooltip of the **Measured** badge of the assistant's check says which: "Measured by this page on the seam frames: last image of the previous shot, first image of this one" or "Measured by this page on the shots’ thumbnails".

Where the page offers the action: **Use the previous shot’s last frame** on each alert of Director IA › Direction › To check and of the Storyboard › Continuity, on the assistant's "no first frame" lines, in the **Frames** section of the shot in the Inspector, and as an icon next to the FL2VA warning of the Production bar; **Extract a frame at the playhead** on the card of a finished take.

### Storage and quota

- **Where.** A job works in `<file storage directory>/video_producer/exports/<user id>/<job id>/`, the user being the one who asked for the export. While it runs the folder holds `graph.txt`, `mezzanine.mp4`, for a sequence in parts its `part-*.mkv` files with their `graph-*.txt` and the `lanes-*.wav` mixes, and, when the storage is not a local disk, a local copy of every source file it reads (`source-<key>`, streamed from the object store in 1 MiB chunks, never read whole into memory). The copies, the graphs, the parts and the mixes are deleted as soon as the assembly stops, whether it succeeded, failed or was cancelled, and `mezzanine.mp4` once the delivery run has ended. A done job keeps only its MP4, `<slug>_<resolution>.mp4`. The folder of a failed or cancelled job is deleted.
- **Sweep.** If a deletion fails (the file is held open), the leftover counts in the budget until the sweep takes it: before each budget check and at each start of the server, the folders of `exports/<user id>/` that no job row claims, the folders that remain of a failed or cancelled job, and the files other than the MP4 in the folder of a done job are deleted. A job that is queued or running, or that the runner is still finishing, is never touched.
- **Budget.** **Export cache per user (MB)** (`export_dir_quota_mb`) is the size of the whole `exports/<user id>/` folder, counted over every file in it. It is checked at each `POST …/exports/video`, before the job is created. After the sweep, when the folder is at or over the budget, the finished jobs of that user (done, failed, cancelled) are deleted with their folders, the oldest first, until it is under; a job that is queued or running is never deleted. If it cannot get under, the answer is 429 `export_quota` with `data.quota_mb`. The check comes before the job, so one export can take the folder over the budget; the next request then clears room.
- **Not counted.** The copy in the library belongs to the storage plan of the user in PotionUI, not to this budget; deleting or evicting a job leaves it there. The files for other software are not stored: they are built at each download.
- **Other deletions.** The user can delete a finished export from the export window (`DELETE`): its folder goes and the library copy stays. Deleting a project cancels its queued or running exports and deletes all its jobs and folders.

### Routes

Answers are `{success: true, data}`; errors are described under Export errors. A job can be read by the user who started it, by an admin, and by the owner of the project; for anyone else the answer is 404 `job_not_found`.

| Route | Body | Answer |
|---|---|---|
| `GET /projects/{id}/exports/{format}?media=path\|name` | | The file, as an attachment. `format` is `fcpxml`, `otio`, `edl` or `srt`. |
| `GET /projects/{id}/exports` | | `{jobs}`: the video exports of the project, newest first. |
| `POST /projects/{id}/exports/video` (202) | `{format, resolution?}` | `{job}`. |
| `GET /exports/{job}` | | `{job}`. |
| `GET /exports/{job}/file` | | The MP4 (`video/mp4`) as an attachment named `<slug of the project name>_<resolution>.mp4`. 409 `not_ready` until the job is done; 404 `job_not_found` when the file is no longer on the disk. |
| `DELETE /exports/{job}` | | On a queued or running job: cancels it and answers `{job}`. On a finished one: deletes the job and its folder and answers `{deleted}`, the id. |
| `POST /projects/{id}/shots/{shot}/seam-frame` | `{source?}` | `{media}`. |
| `POST /projects/{id}/captures` | `{png, name?}` | `{media}` as for the seam frame (`kind` `library`, `item_id`, `media_type` `image`, `url`, `filename`, `width`, `height`, `origin`): the PNG (a base64 data URL of at most 24 MiB) stored in the library of the project owner under the name given, as an ASCII file name that never starts with a dash or a dot (`capture` without one). The request must declare a `Content-Length` of at most 32 MiB and 64 KiB, checked before the body is read (413 `body_too_large`, with `limit`); 422 `invalid_request`; 502 `store_failed`. |
| `POST /projects/{id}/renders` (201) | `{width, height, fps, frames, name?}` | `{render}` with `id`, `width`, `height`, `fps` and `frames`. `width` and `height` are even integers from 16 to 4096, `fps` above 0 and at most 120, `frames` from 1 to 400 (15 s at 24 frames per second, and a margin). A project has at most 2 renders open at once (409 `render_limit`, with `limit`); a render of the project left without a write for an hour is deleted first to make room. |
| `POST /projects/{id}/renders/{render}/frames` | `{start, images}` | `{received}`: how many frames of the render are now on disk. `images` holds 1 to 24 JPEG data URLs of at most 8 MiB each, stored as frames `start`, `start + 1`, and so on; a frame sent again replaces the first one. The request must declare a `Content-Length` of at most 32 MiB, checked before the body is read (413 `body_too_large`, with `limit`); the page sends at most 12 frames or about 6 MB per batch. 409 `render_busy` while the render is being encoded; 404 `render_not_found` once it is deleted; 413 `render_too_large` (with `limit`) when its frames would take more than 2 GiB. |
| `POST /projects/{id}/renders/{render}/finish` | | `{media}` as for a capture, with `media_type` `video`, `fps` and `duration`: the frames encoded by ffmpeg (`image2`, H.264 at crf 18 in yuv420p, scaled to `width`×`height`) into an MP4 named after the render like a capture (`render` without a name) and written as `./<name>.mp4`, stored in the library of the project owner; the render's folder is then deleted. 409 `frames_missing` (with `missing`), `render_busy` or `ffmpeg_unavailable`; 502 `encode_failed` or `store_failed`. |
| `DELETE /projects/{id}/renders/{render}` | | `{}`. Stops the encoding and deletes the render with its frames. A render, an upload or a splat copy left without a write for an hour is deleted by the sweep that runs at startup and every 10 minutes. |
| `GET /me` | | Also `ffmpeg`, `true` when ffmpeg and ffprobe are found, else `false`. |

### Export errors

| Code | Status | When |
|---|---|---|
| `project_not_found` | 404 | See Projects and media › Errors. |
| `job_not_found` | 404 | The job does not exist, is not one the caller may read, or its file is gone. |
| `invalid_request` | 422 | An unknown `format` or `media`; a body that is not a JSON object, or a `format` or `resolution` outside the lists; a seam-frame `source` that is neither `"previous_last"` nor `{take_id, at}`, or an `at` that is neither `"last"` nor a number of seconds. |
| `ffmpeg_unavailable` | 409 | `ffmpeg` is not on the `PATH`. |
| `nothing_to_export` | 409 | No shot of the sequence has a file. |
| `export_running` | 409 | An export of the project is queued or running. |
| `export_quota` | 429 | The export folder is over its budget and nothing more can be evicted. `data.quota_mb` is the budget. |
| `not_ready` | 409 | The file of a job that is not `done`. |
| `owner_not_found` | 409 | An admin acts on a project whose owner no longer exists. |
| `shot_not_found` | 404 | The shot is not in the saved project. |
| `take_not_found` | 404 | The `take_id` is not a take of the project. |
| `no_previous_take` | 409 | The shot is the first, or the shot before it has no finished take with a file, or the take named has no finished file. |
| `extract_failed` | 502 | PotionUI could not cut or store the frame. `detail.data.code` carries its code. |

A job that ends badly carries `error.code`: `ffmpeg_failed` (the assembly failed, no shot file could be read, the project or its owner is gone, or the server stopped), `transcode_failed` (the delivery run failed or stalled), `store_failed` (the library copy failed) or `cancelled`. `error.message` is the last useful line of ffmpeg's error output, 300 characters at most. The page writes its own sentence from the code ("ffmpeg could not assemble the video.", "The video could not be converted.", "The video could not be saved to your library.", "The export was cancelled.") and shows the message under it.

### Tables

`video_producer_export_jobs`: one row per video export: `id`, `project_id`, `user_id` (the user who asked), `format`, `resolution`, `status`, `progress`, `step`, `file_name`, `file_size`, `media_item_id` and `media_url` (the library copy), `error_code`, `error_message`, `created_at`, `started_at`, `finished_at`. The table is created at startup with the others; deleting a project deletes its rows and folders.

## The 3D scene

The 3D scene workspace turns a picture into a Gaussian Splat, lets the user move a camera in it, and gives the generation two kinds of input: stills that change the angle of a shot, and reference videos of a camera move. The **3D shot** row of the timeline holds the camera paths. Nothing in it is simulated.

### What it needs

- **To build a scene from a picture**: the core preset **Image to Splat** (mode `img2splat`, a MoGe-2 depth lift in two layers) assigned to the user, with its model file `moge_2_vitl_normal_fp16.safetensors` (Comfy-Org/MoGe, folder `geometry_estimation/`, 662 MB). The job goes through the PotionUI generation queue like a take, reserves and adjusts the user's GPU minutes, and takes a few seconds to a minute. The plugin follows it and copies the splat into its own storage.
- **To view, capture and render**: a browser with WebGL 2. Everything is drawn in the browser, on the graphics card of the user's machine, with three.js 0.183.2 and Spark 2.3.1 (MIT), which the plugin carries in its own bundle. The server stores the files and encodes the reference videos with ffmpeg (see ffmpeg).
- **To import**: a `.ply` (3DGS), `.spz` or `.splat` splat, or a `.glb` or `.gltf` file exported from Blender (meshes, cameras and their animation), 1 GB at most. A `.gltf` must hold its buffers and textures as `data:` URIs and weigh at most 64 MB: the page reads it, packs it into a `.glb` and sends that, since the server keeps a single file per scene. A `.gltf` that points to separate `.bin` or image files, or a larger one, is refused with a message that asks for a `.glb` export (glTF Binary in Blender). For a `.glb` the page reads only its header and JSON chunk.

### The 3D engine is loaded on demand

`frontend/dist/VideoProducerPage.js` does not contain the 3D engine. It sits in a chunk of its own, `frontend/dist/chunks/engine-<hash>.js` (about 3.1 MB, 1.05 MB gzip, most of it the WebAssembly decoders of Spark), which the page imports only when the 3D scene workspace opens, or when a capture or a render needs it. The browser asks it from the asset route of the page, `/api/plugins/video-producer/assets/chunks/engine-<hash>.js`; the engine makes no other network request. `scripts/build-plugins.mjs` builds every page plugin with code splitting, empties `frontend/dist/chunks/` before the build, and names each chunk after its module and a hash of its content.

### Scenes

`scenes` holds three kinds:

| Kind | Fields | Comes from |
|---|---|---|
| `splat` | `name`, `sourceAssetId`, `sourceTime`, `status` (`queued`, `running`, `done`, `failed`), `progress`, `jobId`, `fileId`, `count`, `view`, `error` | **New scene from image…**: an image of the project, a picture chosen in the PotionUI library (it becomes an asset), or the frame of the shot under the playhead (the video of the shot and the time in it). |
| `splatfile` | `name`, `fileId`, `format` (`ply`, `spz`, `splat`), `view` | **Import splat or Blender file…** with a splat. |
| `glb` | `name`, `fileId`, `cameras` (`name`, `animated`, `duration`) | The same import with a `.glb`, or a self-contained `.gltf` that the page packs into a `.glb`. The page lists the perspective cameras and the length of their animation from the glTF itself. |

`view` is the source camera: vertical field of view in degrees, aspect and median depth, read from the comment `potionui_view` that Image to Splat writes in the PLY header (the page reads the header again when the server gives no view). The splat is in the frame of the source camera (OpenCV: x right, y down, z forward); the page turns it by π around x for three.js, so that the source camera sits at the origin and looks at (0, 0, −depth).

While a job runs, the page asks for the jobs of the project every 2 seconds, one request at a time, and follows only the job of each scene (an earlier failed attempt no longer overwrites a retry). The progress stays in the page: the document records the state of a scene only when its status changes, with the last known `progress`, so a build does not save a version every 2 seconds. The scene list, the viewer, the project bar and the status bar show the progress, with **Cancel**; a failed or cancelled scene offers **Try again**. Undoing the creation of a scene that is building, or removing it, cancels its job. Removing a scene keeps its file on the server; the 3D shots that used it lose their scene and their reference video goes out of date.

### Camera

The viewer draws the scene in the frame of the project, at the resolution of the screen. Drag to orbit around the target, right-drag or Shift-drag to pan, scroll to move in or out, Alt and scroll to change the focal length; the Inspector also sets the focal length (12 to 135 mm, equivalent for a 36 mm wide sensor: horizontal field of view 2·atan(18/focal)), the roll and the distance. **Source view** goes back to the camera of the picture. The view also works with the keyboard once it has the focus (Tab, or a click in it): the arrow keys orbit, Shift and the arrows pan, + and − move in and out, and 0 goes back to the source view; a screen reader announces it as "3D camera view" with these keys. The top left shows the focal length and the vertical and horizontal fields of view; the top view at the bottom right shows the source camera, the target, the current camera and the path of the selected 3D shot.

If the graphics card drops the view (WebGL context lost, after a driver reset or when the card runs out of memory), the view says so and **Try again** builds the 3D engine again; a render in progress stops. If the engine chunk cannot be loaded, for instance because the plugin was rebuilt while the page was open, the view offers **Reload the page**.

A scene built from one picture holds about ±10° of camera movement. For a splat scene that has a source view, a gauge at the bottom left shows the angle from the source camera, seen from the target, and the push along its axis: green, orange, then red with "Holes likely" beyond 15° or 25 %. It never blocks.

### 3D shots and camera paths

A 3D shot (`plans3d`) covers a part of the timeline, belongs to a scene and holds a camera path: keyframes `{t, pos, target, focal, roll}` in the frame of three.js (y up, units of the scene), interpolated with smoothstep, along an arc around the target when the targets match, the focal length linearly. `source` says where the path comes from:

- `trajectory`: **Orbit** (±10° by default, 3 to 45°), **Push in** (15 % of the depth, 5 to 60 %) or **Rise** (+10°, 3 to 45°), set with the amplitude slider of the panel; around (0, 0, −depth) for a splat, and around the center of the bounds, from the current camera, for a Blender scene. `preset` and `amount` keep the choice.
- `manual`: keyframes set with **Keyframe** in the Inspector, at the playhead. Moving or editing a key of another path makes it manual.
- `blender`: an animated camera of the `.glb`, sampled at 24 frames per second (the position, a target 1 m along its −z axis, the focal length from `yfov` and the aspect of the camera, and the roll), with the length of its animation. `camera` keeps its name.

Changing a key, the scene or the length of a 3D shot marks its reference video out of date (`stale`). Moving a 3D shot onto another shot does too, and its Control video follows it to that shot. Deleting a 3D shot deletes its Control video (undo brings both back). While a render, a capture or **Use start and end as first and last frames** runs, the scene commands are locked: choosing or removing a scene, and the scene of a 3D shot.

### Captures

**Capture for a shot…** renders the current camera at the resolution of the project into a PNG, shows the share of empty pixels (holes), and asks for the target shot (the selected one, or the one under the playhead) and the use:

- **First frame** or **Last frame**: the frame `first` or `last` of the shot, with strength 100 and the `sceneId` of the scene, which puts a cube on the Frames row. It replaces the image already there after a confirmation, as a seam frame does. This changes the angle of a shot with FL2VA, and works on 12 GB with the MiniMax-H3 12 GB presets in `i2v` and `flf`.
- **Reference**: a reference of the 3D sets family (`space: "decors3d"`, `type: "Capture 3D"`) limited to the shot, for Ref2VA.

The PNG goes to the server, which stores it as a library item of the user (as a seam frame); it becomes an image asset of the project.

### Reference videos

**Render reference video** renders the 3D shot frame by frame at 24 frames per second, for its length, at the resolution of the project with its long side capped at 1280 pixels, with the aspect ratio of the project and even sides: 1280 × 720 for 1080p or 720p in 16:9, 720 × 1280 in 9:16. The engines bring a reference video down to their own canvas anyway (832 × 480 for the MiniMax-H3 12 GB presets), so a larger one would only be slower to render and to send; captures keep the full resolution of the project. A capture and a reference video share the aspect ratio and so the field of view, and an engine crops both the same way. A 3D shot of length d gets the smallest count of 1 + 8k frames that is at least round(d × 24) (2 at least): LTX-2.5 conditions a run of 1 + 8k frames, so a 3-second take of 73 frames is covered by a reference of 73 frames, where one of 72 left its last 8 frames free. The frames come one every 1/24 s from the start key, the last one exactly on the end key, and the few extra ones hold the end pose. Each pose depends only on the frame number; before each frame the page waits for Spark to finish sorting the splats (level of detail off), then reads the frame back and turns it upright. The frames go to the server as JPEG (quality 92) in batches, and the server encodes them with ffmpeg into an H.264 MP4 (CRF 18, yuv420p) stored in the user's library. The video becomes an asset and a Control video of the shot under the 3D shot (`controls`, `source: "scene3d"`, with `planId` and `assetId`). **Cancel** stops the render and deletes it on the server; once all the frames are sent, the server encodes the video and the render can no longer be cancelled ("Encoding the video…"). A 3D shot changed while its video renders gets a video that is already out of date. A new render replaces the video of the Control video, and the previous video leaves the project when nothing else uses it. A 3D shot shorter than 2 seconds, the minimum of MiniMax, gives a warning. A browser tab in the background renders much more slowly, so the page asks to keep it visible.

**Use start and end as first and last frames** captures the camera at the start and at the end of the path and places the two images as the first and last frames of the shot (`flf`): the engine interpolates a move between two known angles, which works today on 12 GB.

### Output modes

- **AI generation**: with the Ref2VA profile, the fresh reference videos of a shot (Control videos `scene3d` with a video and not out of date) join its video references, 3 at most, first among them. The picture a splat scene was built from is not sent: MiniMax-H3 used to encode a reference image at a short edge of 2048 pixels whatever its size, about 7 100 tokens, which added about a quarter to the sequence of a 3-second 832×480 shot and made each sampling step about three times slower on a 12 GB card. The engine now caps that image at twice the release canvas area (about 2 000 tokens); sending the picture again has not been measured. An out-of-date video gives the warning `stale_guide`; a reference video on an FL2VA shot gives `guide_needs_refs`, because that composition does not read it.
- **Ref2VA prompt**: every Ref2VA shot sends the six-section document of the MiniMax-H3 reference mode, its labels, markers and `<Picture N>`, `<Video N>`, `<Audio N>`, `<Subject N>` and `[Shot 1]` tokens in English, its sentences in the prompt language of the project (English or French):
  - `subject_definitions`: each reference sent. A reference video of a 3D shot is "a rough 3D preview render of the scene, used only as the source of the camera path"; an identity reference or a set reference becomes a `<Subject N>`; a motion reference and an audio file keep their own label;
  - `summary`: `[reference generation]`, the length of the shot and, with 3D guides, the videos its camera movement comes from;
  - `retention_analysis`: one line per label. A 3D guide is `weak_reference - camera movement only, not the look`, its content, colours, textures and rendering defects (blurred or stretched patches, holes, black borders) left out; the scene picture and a set are `partially_preserved`, an identity `fully_preserved`, a motion `attribute_transfer`, an audio file `reference`;
  - `detailed_description`: the filled direction fields, then `[Shot 1]` with the shot instruction, a sentence citing each subject and, for each 3D guide, its move spelled out from the first key of its 3D shot to the last (arc left or right with its degrees around a fixed target, rise or fall, push in or pull out with its percent of the distance; truck, pedestal or push when the target moves with the camera; pan or tilt when only the target moves; zoom from the focal length; "stays still" otherwise), the order it is played in ("forward in time … never in reverse") and a last sentence that makes this move replace any other camera movement written above. A 3D shot without two usable keys falls back to "The camera follows the camera path of <Video N>.";
  - `overall_soundscape`: the ambient sound of the place and the sounds of the action; `non_diegetic_music`: `N/A`, the score being left to the edit.
- **3D render**: no generation. **Place the 3D renders** makes each shot of the selection that has a fresh reference video play that video (as a draft) and leaves the other shots as they are; the undo of the page reverts it. The exports then use the video like any other media of a shot.
- **3D render + AI**: a generation of the selection guided by its reference videos, whatever the profile of the project. With the estimate and the generation, the page sends `production: "render3d_ai"` next to the usual body. The server runs it on two engines; any other preset is blocked with `refs_preset_needed`.
  - **MiniMax-H3 with its `refs` mode**: the Ref2VA profile above. MiniMax-H3 continues the reference video rather than taking only its camera path: the take opens near the last view of the render and copies its look, rendering defects included.
  - **LTX-2.5**: the Layout-To-Render IC-LoRA of Lightricks, made to take the layout and the motion of a rough 3D render and not its look. Each shot with an up-to-date reference video sends a `director` document of one segment (`start` 0, `end` its length) with one `ic_lora` entry: the LoRA `ltx-2.5-22b-ic-lora-layout-to-render-1.0.safetensors` at strength 1, the latest up-to-date reference video of the shot as its `reference`, and the entry `strength` at 1 too, whatever the guidance of its Control video: below 1 the reference tokens are no longer clean and LTX-2.5 copies the render instead of following its layout and camera move (measured at 0.65 and 0.4). A reference video that conditions fewer frames than the shot has, rendered before the 1 + 8k rule of Reference videos, gives the warning `layout_guide_short`. The first frame of the shot, when it has one, becomes the `first` image of the segment: it gives the look of the take, as Lightricks asks (a picture of the finished shot, not the grey render); without one the take keeps the look of the render, with the warning `layout_no_frame`. The capture of the start of the 3D shot (**Use start and end as first and last frames**), or that capture redone by an image model, frames the scene exactly like the first frame of the reference video. The frame rate is the one of the reference video (24 fps) when the mode has an `fps` field, so that each rendered frame meets one generated frame; the prompt is the usual shot prompt, which should describe the finished shot. A shot without an up-to-date reference video runs as an ordinary LTX-2.5 shot from its frames, with the warning `render_missing`. The LoRA has to be installed (block `layout_lora_missing`); the page offers no download for it. When the DiT the plugin finds for the shot is a distilled file, the shot runs the Distilled speed profile of the preset with 8 steps, CFG 1 and `euler_ancestral`, the recipe Lightricks gives for this LoRA; otherwise the preset falls back to its first profile, Balanced (24 steps, CFG 4). Upscale, audio and the other settings of the preset keep their defaults (one pass, no sound); with Upscale on, the core uses the IC-LoRA in the first pass only.

### Older documents

The page and the backend migrate a document written before the 3D scene: the `sample` and `file` scenes go (they held nothing real), the 3D shots that used them lose their scene, the frames of role `Capture 3D` without an image go, and the old camera keys `{az, el, dist, focal, height}` become `{pos, target, focal, roll}` with the formula of the old viewer (`pos = [sin az·cos el·dist, height + sin el·dist, cos az·cos el·dist]`, `target = [0, height, 0]`, `roll = 0`). A 3D shot without the new fields gets `source: "manual"`, `preset`, `amount` and `camera` at null. The Control videos `scene3d` that have neither `assetId` nor `planId`, the old simulated guides, go. The page also turns the 3D set references of the old types `Scène d’essai` and `Gaussian Splat` into `Capture 3D` when they hold an image, and drops them otherwise. A frame may carry `sceneId`, a Control video `planId` and `assetId`.

## Storage and exports

- The web and social videos are written under `video_producer/exports/` and copied to the library of the user; the other exports are built at each download and stored nowhere. See Exports › Storage and quota.
- Takes are ordinary PotionUI generations: their files and thumbnails stay in the user's history and gallery, under the user who owns the project, and the page plays them from `/api/media/generations/<generation id>/<file name>`. Deleting a take, or its project, in Video Producer does not delete the generation or its files. A user who deletes the generation from the gallery breaks the playback of the take.
- Projects are rows of the database, not files (see Projects and media). Imported media are not copied: a project keeps a reference to the library item or to the generation file.
- Seam frames and the copy of each export are library items of the user, and count in that user's storage plan.

## Projects and media

The projects of every user are saved on the server, in the plugin's tables, as the user works. This section is the reference for the tables, the setting, the routes and their error codes, the document schema, the media resolution and the access rules. The routes sit under `/api/plugins/video-producer` and need a signed-in user.

### Tables

| Table | What it holds |
|---|---|
| `video_producer_projects` | One row per project: `id`, `user_id` (the owner), `name` (a copy of the name inside the document), `doc` (the document, as canonical JSON text), `version` (1 at creation, +1 per save), `created_at`, `updated_at`. |
| `video_producer_versions` | One row per stored version: `project_id`, `version`, `doc`, `label`, `source_version`, `created_at`. `source_version` is filled only for a version created by a restore, with the number of the version restored; the column is added at startup to a database that lacks it. |
| `video_producer_takes` | One row per take: `id`, `project_id`, `shot_id`, `user_id` (the owner of the project), `generation_id`, `quality` (`draft` or `final`), `kind` (`render` or `upscale`), `parent_take_id`, `preset_id`, `mode` (the mode of the preset that was submitted), `director_mode` (`t2v`, `i2v`, `flf` or `refs`, the mode really used), `backend_id`, `model_id` (a cloud model), `seed`, `resolution`, `status` (`queued`, `running`, `done`, `failed` or `cancelled`), `progress`, `step`, `variant`, `chosen`, `flag` (`keep` or `reject`), `profile`, `prompt_text`, `file_path`, `thumb_path`, `file_id`, `width`, `height`, `duration_s`, `fps`, `error_code`, `error_message`, `units_reserved` (the GPU minutes reserved; 0 for a cloud take, an exempt user or a user without a limit), `request` (the frozen request, as JSON), `created_at`, `started_at`, `finished_at`. |
| `video_producer_jobs` | One row per hand-over of a take to PotionUI: `id`, `take_id`, `generation_id`, `limit_ref_id` (the reference of the quota event, `video-producer:<take id>`), `units_reserved`, `started_at`, `finished_at`. |
| `video_producer_calibration` | One row per finished take, for the time estimate: `preset_id`, `backend_id`, `resolution`, `seconds`, `duration_ms`, `created_at`. See Generation › Time calibration. |
| `video_producer_export_jobs` | One row per video export: `id`, `project_id`, `user_id`, `format`, `resolution`, `status`, `progress`, `step`, `file_name`, `file_size`, `media_item_id`, `media_url`, `error_code`, `error_message`, `created_at`, `started_at`, `finished_at`. See Exports › Tables. |

The columns of the takes table beyond the first version (`director_mode`, `model_id`, `progress`, `step`, `variant`, `chosen`, `flag`, `profile`, `prompt_text`, `file_id`, `units_reserved`, `started_at`, `user_id`, `request`) are added at startup to a database that lacks them.

The document is stored as canonical JSON: sorted keys, compact, UTF-8; NaN and infinity are refused. A save whose canonical text equals the latest stored version stores nothing: the answer carries `unchanged: true` and the current version. Deleting a project cancels the takes it has in flight (their PotionUI generations are cancelled and their reserved minutes refunded), then cancels its queued or running video exports and deletes their rows and folders (see Exports › Storage and quota), then deletes its rows, with those of its versions, takes and jobs; the library items and the generations it used, the generations of its takes included, and the copies of its exported videos, stay in the user's library and gallery, and the calibration rows stay.

### Versions and the `versions_kept` setting

Each save that changes the document adds a row to `video_producer_versions` with the next version number and updates the project row. The page saves by itself less than a second after each change, so one editing session produces many versions.

**Versions kept per project** (`versions_kept`, 5 to 500, default 50) caps the history. After every save and every restore, a project keeps its most recent N versions and the older rows are deleted; the current version is always one of them. Lowering the setting takes effect at the next save of each project. Every version holds the whole document (at most 4 MiB), so a project can use about N times the size of its document. Restoring a version that was pruned answers 404 `version_not_found`.

A restore never rewrites history: restoring version V stores the document of V as the next version, with `source_version` set to V. It is pruned like any other save.

### Concurrent saves

A save names the version the page read (`version` in the body). The write succeeds only if the project is still at that version. Otherwise nothing is written and the answer is 409 `version_conflict`, with the current version in `data.version`. The page then reloads the project from the server, shows a message and drops what was not saved in that page: there is no merge. Two tabs of the same user on the same project are enough to trigger it. If the project was deleted in the meantime, the save answers 404 `project_not_found` instead: the page stops saving that project, says so, and opens the most recently modified project of the user, or creates the starter project.

### Routes

| Route | Body | Answer |
|---|---|---|
| `GET /projects` | | `{projects}`: the caller's own projects, last updated first, each with `id`, `name`, `version`, `created_at`, `updated_at`, `shots` and `duration_s`. |
| `POST /projects` (201) | `{doc, name?}` | `{project}` at version 1, with its document. `name`, when given (at most 200 characters), replaces the name inside the document. |
| `GET /projects/{id}` | | `{project}` with its document. |
| `PUT /projects/{id}` | `{doc, version, label?}` | `{project}` with `id`, `name`, `version`, `updated_at` and `unchanged`. `version` is the integer the page read; `label`, when given, is at most 200 characters, is stored as given with the version and is returned by `GET /projects/{id}/versions` (`null` without one). The page sends none; the assistant's tools store `Assistant` through the same function. |
| `DELETE /projects/{id}` | | `{deleted}`, the id. Cancels the takes and splat jobs in flight and refunds their reservations, then deletes the versions, takes, jobs, exports, scene files and renders of the project. |
| `GET /projects/{id}/versions` | | `{versions}`, latest first, each with `id`, `version`, `label`, `source_version`, `created_at` and `shots`. |
| `POST /projects/{id}/versions/{version}/restore` | | `{project}` with the restored document, as the next version. |
| `POST /media/resolve` | `{origin}` | `{media}` with `kind`, `media_type`, `url`, `filename` and `origin`. See Media resolution. |
| `POST /projects/{id}/scene-files` (201) | multipart: `file`, and `kind` `splat` or `glb` | `{file}` with `id`, `kind`, `format` (`ply`, `spz`, `splat` or `glb`), `name`, `size`, `count` (gaussians, `null` for a glb), `view` (`{fov, aspect, depth}` from a PLY's `potionui_view` comment, else `null`), `cameras` (for a glb, `[{name, animated, duration}]`, else `null`), `url` and `created_at`. At most 1 GiB: the request must declare its `Content-Length` (411 `length_required`), refused before its body is read beyond 1 GiB and 64 KiB and while the file arrives beyond 1 GiB (413 `file_too_large`). The form is read as it arrives, after the user and the project are checked: one file, in `file`, written once into the project's `work/` folder and moved into place once checked, and at most 8 other fields of 1 KiB each (422 `invalid_request`; 422 `unsupported_format` as soon as the file name has another extension). The file is checked before it is kept: a splat by the splat probe of PotionUI (`probe_splat` of `src.plugin_api`: a binary little-endian PLY with the 3DGS properties in float, a gzip SPZ starting with `NGSP`, a `.splat` of 32 bytes per gaussian), a `.splat` also with finite positions and scales in its first 1,024 gaussians, and a glTF 2.0 binary starting with `glTF` whose JSON chunk is at most 64 MiB and can be read (422 `unsupported_format` or `invalid_file`, whose message never names a path of the server). The scene files count against the storage plan of the project owner: a file is refused with 413 `storage_full` (with `remaining` and `needed`) when the owner's scene files of every project and it would pass what the plan leaves after the generations and library uploads PotionUI measures, or (with `limit`, `used` and `needed`) when the scene files of the project would pass 20 GiB; 413 `file_too_large` (with `limit`) when it is larger than the plan's largest upload. Before the body is read the declared length less 64 KiB is checked, then the size of the file once it has arrived. A file that neither the current document of the project nor any of its stored versions cites by `fileId` is deleted by the sweep (at startup and every 10 minutes), never within 24 hours of its upload, as is a file of the project folder that no row knows. |
| `GET /projects/{id}/scene-files/{file}` | | The file (`model/gltf-binary` for a glb, `application/octet-stream` otherwise). 404 `file_not_found`. |
| `GET /me` | | `{locale, last_project_id, is_admin, limits, settings, plugin, engines, presets, features, upscale_targets, ffmpeg}`: the language and the last project of the user, whether they are an admin, their GPU minutes (`limits.gpu_minutes`), the plugin settings, and the engines, presets and features described under Generation › Routes and Exports › Routes. |
| `PUT /me` | `{locale?, last_project_id?}` | `{locale, last_project_id}`. `locale` is `en` or `fr`; `last_project_id` is one of the caller's projects or `null`. See below. |

The routes of the takes, of the estimate, of the generation and of the splat jobs are in Generation › Routes; those of the exports, of the seam frame, of the scene captures and of the renders are in Exports › Routes.

`GET /me` and `PUT /me` also carry the last project of the user: `last_project_id`, a per-user plugin setting like the locale. `GET /me` returns it as `null` when the stored project no longer exists or is not the caller's, and lists `versions_kept` among its `settings`. `PUT /me` takes `{locale?, last_project_id?}`; a key left out stays as it is, and `last_project_id: null` forgets the project. A body with neither key answers 422 `invalid_locale`.

### Errors

An error answers with its HTTP status and a body `detail` shaped `{"success": false, "error": <code>, "message": <text>, "data": <object, when there is one>}`. The page maps the codes to its own messages. The codes of the projects and media routes:

| Code | Status | When |
|---|---|---|
| `project_not_found` | 404 | No such project, or a project of another user (the caller is neither its owner nor an admin). Also `PUT /me` with a `last_project_id` that is not the caller's, an admin included. |
| `version_not_found` | 404 | The project has no such version: it was pruned, never existed, or the number is not an integer. |
| `version_conflict` | 409 | The project moved on since the version the caller read. `data.version` is the current version. A restore can raise it only when another save lands at the same moment. |
| `invalid_doc` | 422 | The document breaks the schema or holds a value that JSON cannot carry (NaN). The message starts with the JSON path of the offending value, for example `$.clips[0].dur: …`, and is cut to 300 characters. |
| `doc_too_large` | 422 | The canonical document is over 4 MiB (4,194,304 bytes). |
| `invalid_request` | 422 | The body is not a JSON object, has no `doc` (or no `origin`), has a `version` that is not an integer, has a `name`, a `label` or a `last_project_id` of the wrong type, or has a `name` or a `label` over 200 characters. |
| `invalid_ref` | 422 | The media origin has an unknown `kind`, keys other than exactly those of its kind, or an id that is not a non-empty string. |
| `invalid_locale` | 422 | `PUT /me` with a body that is not an object, with neither `locale` nor `last_project_id`, or with a `locale` other than `en` or `fr`. |
| `media_not_found` | 404 | The generation, the file or the library item does not exist, was removed, or is not the caller's to read. |

The codes of the takes, the estimate and the generation are in Generation › Take errors; those of the exports and of the seam frame are in Exports › Export errors.

### The document

The document is the JSON that the page edits: the project settings (`name`, `fps`, `aspect`, `resolution`, `promptLanguage`), the direction and the synopsis, the shots (`clips`), `audio`, `titles`, `prompts`, `frames`, `controls`, `plans3d`, `markers`, `references`, `scenes`, the console (`lanes`, `aux`, `master`), `profiles`, `engine`, `hybrid` and the `assets`, which are the media. Its schema is `DOC_SCHEMA` in `backend/projects.py`, a JSON Schema (draft 2020-12) checked with the `jsonschema` library when a project is created or saved, not when it is read. The fields of the 3D scene (`scenes`, `plans3d`, and `sceneId`, `planId` and `assetId` on frames and Control videos) are described in The 3D scene, with the migration of older documents.

The key `results`, where older pages kept simulated takes, is no longer part of the schema. A document that still holds it is accepted: the backend drops the key when it reads a project or a version, when it restores a version and when it creates or saves a project, without an error, so a browser tab opened before the update goes on saving; a document that differs from the stored one only by `results` answers `unchanged`. Only the schema check itself (`validate_doc`) refuses it.

The schema is strict. Every object lists all its fields as required and refuses any other one (`additionalProperties: false`), at every level, with one exception: `engine.preset` and `engine.model` are optional, so that a document saved by an older page, which did not write them, is still accepted. Fixed vocabularies are enumerations: the clip `stage` and `flag`, the audio roles (`Dialogue`, `Musique`, `Ambiance`, `SFX`), the lane `automation`, the insert types, the reference `space` and `scope`, the scene kinds, the control `source`, and the asset `kind`, `role` and `synth`. Other fields are free text or numbers without bounds (for example `aspect`, `resolution`, `fps`, the marker `kind`, the clip `preset` or the engine `quality`), and `engine.seed`, `steps`, `guidance` and `variants` may be null.

`engine` holds the choice of engine: `backend` (the id of one of the engines of `GET /me`), `preset` (the id of the preset, or null) and `model` (the catalog id of the cloud model, or null for a native preset), and the number of `variants`. A clip holds in `take` the id of the take it plays (a row of `video_producer_takes`). The takes themselves are not in the document.

An asset has `id`, `kind` (`video`, `image` or `audio`), `name`, `src` (the address the page plays, or null), `origin` (`{kind: "history", generationId, fileId}`, `{kind: "library", itemId}` or null), `srcDur`, `width`, `height`, `fps`, `res`, `generated`, `quality`, `resultId`, `role`, `synth`, `transcript`, `character` and `lipSync`. The video of a take that is placed on the timeline is the asset `gen-<take id>`: `kind` `video`, `src` the URL of the take, `origin` the generation and the file, `generated` true, `quality` `draft` or `final` and `resultId` the id of the take.

A refusal (422 `invalid_doc`) means that the document sent does not match the schema of the backend. The page and the backend ship in the same plugin, so it usually means a browser tab opened before the plugin was updated, or a client other than the page: a tab that still runs an older page writes `results` and no `engine.preset` or `engine.model`, which is accepted, but a new page against an older backend (whose schema requires `results`) is refused. The page then shows "The project could not be saved: its content was refused." and keeps the changes in memory; the message of the answer, visible in the network tools of the browser, gives the path of the offending value.

The language of the prompts is the field `promptLanguage` (`en` or `fr`, required, `en` by default in the page). It is a choice per project, independent of the language of the interface, which stays a per-user setting. The backend stores it, and the assistant's tools read it to pick the contradiction rules; the page uses it for the text of the starter project, the templates and the composer of the prompt library, the contradiction rules, and the assistant, which writes shot prompts in it (see The assistant mode). Changing it never rewrites existing text.

### Media resolution

The PotionUI pickers (the library for images, videos and audio, the gallery for images and videos) hand the page an origin: `{kind: "history", generationId, fileId}` or `{kind: "library", itemId}`. The page sends it to `POST /media/resolve`, which asks PotionUI to resolve the reference as the signed-in user and answers with what the page plays:

- `url`: `/api/media/generations/{generationId}/{file name}` for a gallery file, `/api/media/uploads/{file name}` for a library item. These routes belong to PotionUI; the plugin serves no media.
- `media_type`: `image`, `video` or `audio`, in lowercase.
- `filename`: the original file name. `kind`: the kind of the origin. `origin`: the origin as it was sent.

The page stores `url` and `origin` in the asset of the document. Nothing is copied: a project holds references, so removing a file from the library or the history breaks the media of every project that uses it, and `POST /media/resolve` answers 404 `media_not_found` for it from then on. The origin must have exactly the keys of its kind, with non-empty string ids. An origin of another kind answers 422 `invalid_ref` without calling PotionUI. The same resolution is used to give the references and frames of a shot to a generation, and the source video of an upscale.

### Access

A project belongs to the user who created it, and every route checks it.

- The list shows only the caller's own projects, admins included.
- Reading, saving, deleting, listing the versions, restoring, and every route of the takes, the estimate, the generation, the exports and the seam frame need the project to be the caller's, or the caller to be an admin. For anyone else the answer is 404 `project_not_found` (or `take_not_found`, `job_not_found`), never 403, so the existence of a project is not revealed. An admin who knows a project id can therefore read or change any project through the API, and start takes on it: they run as the owner of the project, with the owner's presets, quota and history. An admin who exports a project gets the job, the folder and the library copy under their own account, with the media resolved as the owner; a seam frame is stored in the owner's library. The page offers no way to list the projects of other users.
- `PUT /me` accepts only the caller's own projects as `last_project_id`, admins included.
- `POST /media/resolve` resolves only what the caller can read in PotionUI: their own library items and the generations that are visible to them.

### Liveness

`GET /health` answers `{success: true, data: {status: "ok", plugin: "video-producer", version}}` to any signed-in user and 401 to anyone else. It reads and writes nothing; it only tells that the API of the plugin is mounted. The page does not call it, and `tests/test_health.py` covers it.

## Notifications

Video Producer sends a PotionUI notification to the owner of a take when it is ready (**Video Producer: take ready**, type `video-producer.take_done`) and when it fails (**Video Producer: take failed**, type `video-producer.take_failed`). The text reads "<project name>: the draft take A is ready." or "<project name>: the final take B failed." followed by the reason, and carries `project_id`, `take_id` and `shot_id` as metadata. Both types are on by default, and each user can tune them in their notification preferences. The page also shows a toast when the takes it follows end ("2 draft takes ready", "1 take failed").

A video export sends its own two notifications to the user who asked for it: **Video Producer: export ready** (`video-producer.export_done`) and **Video Producer: export failed** (`video-producer.export_failed`). Both are on by default and tunable like the first two; their text and metadata are described under Exports › The assembled video.

## The assistant mode

The assistant is the PotionUI chat, working in a chat mode that this plugin contributes. The **Assistant** button of the project bar, **Window › PotionUI assistant** and Ctrl+J (⌘J on a Mac) open the chat, and a conversation started from a page under `/plugins/video-producer` is in the mode **Video Producer assistant**. The assistant reads the project that is open on the page and has four tools: write the prompt of a shot, fix the contradictions with the global direction, cut a synopsis into shots and check the continuity between shots. It proposes and the user approves: the three tools that write or propose show a preview card in the chat, and nothing changes until the user approves it. The mode has no plugin setting: the model, the tool switches and the chat belong to PotionUI.

### Requirements

- **A language model, configured and assigned.** In Admin → LLM / Assistant, click **Add configuration**, pick a type (OpenAI for a local llama.cpp `llama-server` or an online provider, or Ollama with its settings adjusted, see Which language model), then assign the configuration to the users or groups who use Video Producer. The plugin calls no model itself: the chat uses the model that PotionUI gives the user, like for every other chat mode. Without an assigned configuration the chat is empty: an admin reads "No enabled LLM configurations", a user "Chat is currently unavailable".
- **A model that can call tools.** The four actions are tools. A model that cannot call them only answers in text.
- **Tools on.** In the composer of the chat, **Tools** must be on (its tooltip reads "Tools ON" or "Tools OFF"). An admin can also turn a tool off, or lock it on, for one configuration: Admin → LLM / Assistant, open the configuration, tab **Toolset**, group **Video Producer**.
- **Where the text goes.** The context block described below is sent to the model with every message. With a hosted provider such as OpenAI it leaves your server for that provider; with a model that runs on your own machines (Native, or a llama-server or Ollama that you host) it does not.

### Which language model

The chat sends the context block and the definitions of the four tools with every message, and the tools only work when the model calls them correctly. The model must also fit in memory next to whatever else runs on the machine. There are two local options, plus the online providers. Both local engines were measured on the RTX 4070 Ti 12 GB, with real conversations of the assistant and the real OpenAI-type and Ollama-type clients of the PotionUI core. With the same settings they run at the same speed, because Ollama 0.30 and later runs the `llama-server` of llama.cpp itself: for Qwen3-8B Q4_K_M, about 5,000 tokens/s of prefill and 74 tokens/s of generation, and a tool turn takes 0.5 to 7.7 s.

- **Recommended when the model shares the video card: llama.cpp `llama-server`, added as an OpenAI configuration.** It reserves its memory at load time, unloads on demand and takes an API key.
  - Simple mode, one model:

    ```
    llama-server -m Qwen3-4B-Q4_K_M.gguf -a qwen3-4b -c 16384 -ctk q8_0 -ctv q8_0 -np 1 --reasoning off --host 127.0.0.1 --port 9931 --api-key-file llm-keys.txt --sleep-idle-seconds 60
    ```

    `-a qwen3-4b` names the model; `-c 16384` opens a context of 16,384 tokens; `-ctk q8_0 -ctv q8_0` keeps the KV cache in q8_0, about 1.1 GB less than f16 at that size; `-np 1` opens a single slot; `--reasoning off` turns the thinking of Qwen3 off on the server; `--host 127.0.0.1` listens locally; `--api-key-file` reads the API keys from a file, one per line; `--sleep-idle-seconds 60` puts the server to sleep after 60 s without a request, which frees its VRAM (measured with Qwen3-8B: about 6.9 GB freed, and the next request woke it in about 2 s).
  - Router mode, to unload on demand:

    ```
    llama-server --models-preset models.ini --models-max 1 --host 127.0.0.1 --port 9931 --api-key-file llm-keys.txt
    ```

    with a preset file of this form:

    ```ini
    [qwen3-4b]
    model = /models/Qwen3-4B-Q4_K_M.gguf
    ctx-size = 16384
    cache-type-k = q8_0
    cache-type-v = q8_0
    parallel = 1
    ```

    Before a video generation, `POST /models/unload` with the body `{"model": "qwen3-4b"}` unloads the model (measured: 1.0 s, VRAM back to its base level); the next chat request loads it again by itself (2 to 3 s). PotionUI has no action for this call yet: send it, with the header `Authorization: Bearer <key>`, from your own script or scheduler.
  - The default port of llama-server is 9931 since llama.cpp v0.7.0 (8080 in its Docker images).
  - In PotionUI, Admin → LLM / Assistant → **Add configuration**:
    - type **OpenAI**;
    - **Base URL** `http://127.0.0.1:9931/v1`, or `http://host.docker.internal:9931/v1` from the PotionUI Docker image under Docker Desktop. Under Docker on Linux, start the container with `--add-host=host.docker.internal:host-gateway` and make llama-server listen beyond 127.0.0.1 (`--host 0.0.0.0`), hence the API key;
    - **API Key**: a key of the file;
    - **Model**: the name given by `-a`, or the section name of the preset file (`qwen3-4b`); the model discovery of the form lists them;
    - under **OpenAI Options**, **Reasoning Effort** **None**. Otherwise Qwen3 thinks before every call: a turn takes about 14 s instead of 1 to 2 s, and the thinking can use up **Max Tokens** without calling a tool;
    - under **OpenAI Options**, **Context window** = the value of `-c` (16384), so that the chat budgets the conversation to what the server accepts.
- **Ollama works once three settings are made under Ollama Options.** Without them the assistant does not work.
  - **Context Size** 16384 or more. Left empty, Ollama opens its default context, 4,096 tokens on a card under 24 GB, and every turn of the assistant is refused with "Ollama returned status 400: request (… tokens) exceeds the available context size (4096 tokens)": the first turn already takes about 4,800 tokens.
  - **Keep Alive** between 5m and 30m. The PotionUI default is 0: the model is unloaded after every answer and loaded again at every turn, which adds 4.5 to 6 s.
  - **Thinking Mode** **Automatic** (it turns thinking off when tools are sent) or **Disabled**.
  - Ollama has no authentication: leave it on 127.0.0.1.
  - To free the VRAM before a generation: the quick action **Clear Ollama VRAM** of the Ollama plugin, or the automation template **Free VRAM before a generation (automatic)**.
- **Measured models**, each with every tool call correct (8 of 8, or 6 of 6):
  - Qwen3-4B Q4_K_M when the video shares the card: about 3.9 GB of VRAM with the q8_0 KV cache at 16,384 tokens, 0.3 to 5.5 s per turn;
  - Qwen3-8B Q4_K_M otherwise: about 6.0 GB with the q8_0 KV cache, 7.1 GB in f16, 0.5 to 7.7 s per turn.
  - In both engines the VRAM does not grow while a long prompt is processed: the memory is reserved at load time, and a prompt that is too long is refused instead of running out of memory.
- **Unload before a video generation, whichever the engine.** Under native Windows an overlap gives no error but silently slows one of the two processes (measured: −50 % on prefill). Under Docker or Linux, a CUDA out of memory error from the video engine is likely.
- **An online provider** (OpenAI or another) stays possible and leaves the whole card to the engine. It was not measured: the assistant was validated end to end against a scripted OpenAI-compatible server (mode, context, tools, approval cards, writes, page updates). Whatever you pick, check one conversation with the model you choose, and pick a model that supports tool calls.
- **Not recommended on a 12 GB card: the Native client.** Measured on the RTX 4070 Ti 12 GB, with the tools sent as part of the prompt (`force_prompt_tools`):
  - Qwen3 4B in nf4 loads (129 s the first time, about 4.4 GB of VRAM for the model) and answers a short question, but the first real turn of the assistant ran out of GPU memory while the prompt was processed: peak 11,971 MiB, CUDA out of memory after 91 s, no tool called. With the thinking mode of the model on, the turn had not ended after 12 minutes. The context block is not the cause (about 1,500 characters for a project of four shots): the native client does not bound its attention memory while it processes the prompt. After the error the CUDA context of the PotionUI process stayed unusable, so every following turn failed within seconds until the container was restarted.
  - Qwen3 1.7B in nf4 loads in 29 s (about 2.6 GB) and never ran out of memory (peak 4.6 GB), and its turns lasted 5 to 91 s, but it produced one well-formed tool call in nine attempts and no approval card: it is too small for the tool protocol.
  - The `nf4` and `int8` quantizations of the Native client need the optional Python package `bitsandbytes`, which the PotionUI image does not contain. The 4B model without quantization (bf16, 7.5 GB) did not fit either.

### Mode and context

The mode is declared in `manifest.yml` under `chat_modes`: `id` `video-producer`, `name` "Video Producer assistant", `icon` `film`, `default_route_prefixes` `/plugins/video-producer`, `context_contributor` `backend.chat.context.build_context`, and a `system_prompt` in English that ends with `{{TOOL_HINTS}}`. The four tools are declared under `tools:` with `modes: ["video-producer"]`, so they are visible in this mode only; disabling the plugin removes the mode and its tools.

- **The mode follows the route.** The chat takes the mode whose route prefix is the longest match for the current page, so the page calls no `declareMode`. A conversation keeps the mode it was started in. When the chat holds a conversation started in another mode, its header says "Started in …" and offers **start a new chat**; until then the Video Producer tools and context are not in that conversation.
- **The system prompt** tells the model to ground its answers in the context block and to name shots by their label; to ask the user to open a project when the block says the page is not open; to write every shot instruction, rewrite and proposed shot in the prompt language of the project and to answer the user in the user's own language, without translating what the user wrote; to keep an instruction to one to three sentences (subject and action, framing, camera movement, light) that does not repeat the global direction; to call the tool instead of writing the new text in its reply; to say nothing is done before the user approves; and, when a tool answers `project_not_found`, `shot_not_found` or `version_conflict`, to say so plainly and suggest reloading the project.
- **The context.** The page registers the provider `video_producer` when it mounts (`startAssistant` in `frontend/src/lib/assistant.svelte.js`) and removes it when it unmounts. With each message, the host adds its result to the request and `build_context` (`backend/chat/context.py`) turns it into one system block. The provider returns fourteen keys: `projectId`, `projectVersion`, `name`, `promptLanguage`, `workspace`, `selection`, `playhead`, `range`, `synopsis`, `direction`, `production`, `shots` (per shot: `id`, `label`, `start`, `dur`, `stage`, `promptId`, `prompt` cut at 300 characters, `hasFirstFrame`, `hasLastFrame`, `take`), `issues` (the conflicts the page flags: `shotId`, `level`, `text`) and `seams` (the continuity the page measured: `fromShotId`, `toShotId`, `issues` with `kind` and `text`, `measured`).
- **The block** holds, in this order: the project (name, id, saved version), the prompt language, where the user is (workspace, playhead and the shot under it, selection, range), the synopsis, the direction (generation profile and the five fields), the shots in timeline order (id, label, start and end, stage, take id, frames `none`, `first`, `last` or `first+last`, prompt), the conflicts of the page, the continuity it measured and the production state (state, progress, mode, quality, target, queue). It is bounded to 8,000 characters: the synopsis to 800, each direction field to 240, each shot prompt to 160, 40 shots, 20 conflicts and 20 continuity lines. When it is too long, the list of shots gives way first and ends with "… N more shots not shown." With no `projectId` the block is one fixed line, "Video Producer: the page is not open on a project this turn, so there is no project context."
- **What is not sent.** Media files and thumbnails, take videos, references, audio tracks, titles, markers, 3D scenes, the engine and the other projects of the user. The model sees no image.

### Tools

Each tool is a class of `backend/chat/tools.py`, in the group **Video Producer**. The label is the one shown on the approval card and in the **Toolset** tab. A successful result is JSON in `ToolResult.data` and carries `project_id`. The project is read from the database with `projects.get_project`, from the `projectId` of the page context; the caller must own it or be an admin, the same rule as the routes (see Projects and media › Access).

| Tool | Label | Approval | Arguments | What it does |
|---|---|---|---|---|
| `vp_write_shot_prompt` | Write shot prompt | Yes | `shot_id` (string, an id from the context), `text` (string, 1 to 4,000 characters, the complete new instruction) | Writes the instruction of one shot. Creates the prompt linked to the shot when it has none, otherwise replaces its `text`. The text is stored as given. Result: `project_id`, `shot_id`, `prompt_id`, `text`, `version`. |
| `vp_fix_conflicts` | Fix conflicts | Yes | `rewrites`: a list of `{shot_id, text}`, 1 to 100 entries, one per shot (a repeated shot is refused) | Rewrites several instructions in one change, typically the conflicts listed in the context. Result: `project_id`, `changes` (each `shot_id`, `prompt_id`, `before`, `after`), `version`. |
| `vp_split_synopsis` | Split synopsis | Yes | `shots`: a list of `{label, prompt, duration_s}`, 1 to 24 entries; `label` 1 to 34 characters, `prompt` not empty (at most 4,000 characters), `duration_s` from 2 to 15 | Proposes a cut of the synopsis (or of a story the user tells) into shots. Writes nothing. Result: `project_id`, `proposal` (the validated shots). |
| `vp_check_continuity` | Check continuity | No | None | Reads the project and lists the seams to check. Writes nothing. Result: `project_id`, `seams`, `checked_at`. |

What the user sees on the approval card (`ToolApprovalPreview`):

- `vp_write_shot_prompt`: kind `text_edit`, action "Write shot prompt", target the label of the shot, one block labelled with the shot, carrying the new text and, as `old_text`, the instruction now in force (the shot's own prompt, else the sequence prompt that covers most of the shot), so that PotionUI shows the old and the new text and refuses a stale confirmation.
- `vp_fix_conflicts`: kind `text_edit`, action "Fix conflicts", target "N shots", one block per shot, labelled with the shot, with `old_text` so that PotionUI shows the old and the new text.
- `vp_split_synopsis`: kind `timeline`, action "Split synopsis", target "N shots, T s", one row per shot with its time range and "label: beginning of the prompt" (90 characters).

`vp_check_continuity` returns, in timeline order, only the seams that have a problem, each as `from_shot_id`, `to_shot_id`, `from_label`, `to_label` and `issues` (`kind`, `text`, `fix`, and `shot_id` or `rule` when they apply). `text` and `fix` are English sentences. The page writes its own translated text from `kind` and keeps the English one as a fallback. Shots at the stage `source` are skipped. The kinds are:

| `kind` | Made by | When |
|---|---|---|
| `no_instruction` | The server | A shot has no instruction: no prompt of its own and no sequence prompt covering it, or an empty one. |
| `conflict` | The server | The instruction breaks a contradiction rule against the global direction (the issue carries `rule`, see Contradiction rules below). |
| `duration` | The server | The shot lasts less than 2 s or more than 15 s. |
| `fl2va_no_frame` | The server | The project profile is FL2VA and the shot has no first frame. |
| `camera_change` | The server | Two consecutive shots each name a camera move and share none. |
| `lum`, `warm` | The page | A brightness or color temperature jump between two shots, measured on their thumbnails and sent in `seams`. |
| `identity` | The page | The similarity score between two takes, sent in `seams`. It stays simulated (see What stays simulated). |

### Approvals and writes to the database

- **Approval.** `vp_write_shot_prompt`, `vp_fix_conflicts` and `vp_split_synopsis` have `requires_approval`. Their `execute` builds the preview and writes nothing; `execute_confirmed` runs once, when the user clicks **Approve** on the card. **Reject**, with or without a reason, runs nothing. `vp_check_continuity` has no approval and runs as soon as the model calls it.
- **What is written.** Only `vp_write_shot_prompt` and `vp_fix_conflicts` write. They change the `text` of the prompt linked to the shot in the `prompts` of the project document, or add a prompt to it (new ULID `id`, `shotId`, the `start` and `dur` of the shot, `strength` 75, `text`). `vp_fix_conflicts` does all its shots in the same document. Neither tool adds, moves or deletes a shot, nor touches the direction, the synopsis, the media, the takes or `engine`, and neither starts a generation.
- **One version per approved call.** The document is saved through `projects.save_project`, with the version the tool has just read and the label `Assistant`, so it goes through the same schema check as a save from the page, adds one row to `video_producer_versions` (the **Version history** window shows "Assistant" in it) and counts toward **Versions kept per project**. Nothing is stored when the text did not change.
- **Concurrent saves.** `execute_confirmed` reads the latest stored document, not the one of the preview, so a save made after the preview is kept and the change goes on top of it. If the project is saved elsewhere between that read and the tool's own save, the save is refused with a version conflict; the tool reads the document again, applies the change again, and fails with `version_conflict` only when that second attempt is refused too.
- **No write for the other two.** `vp_split_synopsis` and `vp_check_continuity` write no row. The split is applied by the user, on the page, from the Storyboard.

### What the page does with a result

The page registers `onToolApplied` for each of the four tools (`frontend/src/lib/assistant.svelte.js`). A tool that needs approval reaches its handler when the user approves; `vp_check_continuity` reaches it when the assistant's reply is final. A result is delivered once: opening an earlier conversation does not replay it.

- **`vp_write_shot_prompt`, `vp_fix_conflicts`.** A result whose `project_id` is not the open project is `stale`: the chat shows "The assistant changed another project, not the one open here." in place of the assistant's narration. A `version` older than the page's own is a `noop`. Otherwise the page applies the same text to its own document as one undoable change, takes the returned `version` as its saved version (no autosave, the server already has it), and shows "Prompt of “…” updated by the assistant" or "N prompts rewritten by the assistant". It reloads the project (`openProject`) instead when the `version` is more than one ahead of its own, when a shot is missing from its document, or when the user has unsaved edits on the same prompts, with "Project reloaded with the assistant’s changes"; a reload drops unsaved local changes and the undo history.
- **`vp_split_synopsis`.** The proposal (kept, numbered, with ULID ids) fills `ui.storyProposal`, the page opens the Storyboard and shows "N shots proposed in Storyboard". The user ticks, renames and clicks **Add N shots at the end** in the **Proposed breakdown**, the same list as the **Propose a breakdown** button. For another project, `stale` with "This answer is about another project, so nothing was shown here."
- **`vp_check_continuity`.** The seams fill the **To check** section of the Direction tab (a dot appears on the tab), and a toast says "N continuity points to check", with a **Show** button when the Direction tab is not on screen, or "Continuity checked: nothing to fix". The section stays until the user dismisses it, leaves the page or opens another project.
- A host that predates the delivery of tools without approval to `onToolApplied` (see "When `onToolApplied` runs" in `docs/plugin-api.md`) passes the page only the approved calls. The chat still works, but the continuity check shows no **To check** list on the page.

### Errors

A failed call returns `ToolResult(success=False)` with `error` set to `<code>: <message>`, the code first and stable. A failure at the preview goes back to the model, which tells the user; a failure after **Approve** puts the card in the state **Failed** with this text, and the user can click **Retry**.

| Code | When |
|---|---|
| `project_not_found` | The page context names no project (the page is not open on one), the project does not exist, or it belongs to another user and the caller is not an admin. |
| `shot_not_found` | A `shot_id` is not a shot of the stored project: it was deleted, or not saved yet. |
| `invalid_arguments` | An argument breaks the limits above: missing or empty `shot_id` or `text`, text over 4,000 characters, empty, repeated or more than 100 `rewrites`, more than 24 shots or a label over 34 characters or a duration outside 2 to 15 s in a split. |
| `version_conflict` | The project was saved elsewhere between the moment the tool read it and the moment it saved, twice in a row (see Concurrent saves). |
| `invalid_doc`, `doc_too_large` | The save was refused for the reasons of Projects and media › Errors. |

### Contradiction rules and prompt language

The tool and the page apply the same contradiction rules, in the same tables. The tables live in `backend/chat/rules.json`: `flags`, `conflicts` (for `en` and for `fr`, a list of `{id, global, local}` where `global` is a pattern for the direction and `local` a pattern for an instruction), `cameraWords` (one pattern per language, the camera moves) and `messages` (one English sentence per rule `id`). There are four rules, in both languages: `noNeon`, `noText`, `naturalColors` and `stableCamera`. A rule fires when the filled fields of the global direction, joined by spaces, match `global` and the instruction matches `local`.

- **Two copies, one parity test per side.** The backend reads `backend/chat/rules.json` through `backend/chat/rules.py`. The page bundles an identical copy, `frontend/src/lib/rules.json`, through `lib/rules.js`. `tests/test_chat_rules.py` fails when the copies differ, and so does `frontend/src/lib/rules.test.js`. The patterns are JavaScript regular expression sources with the flag `i`; `rules.py` rewrites `\b` so that Python matches the same text as the browser.
- **Which table applies.** The language of the prompts of the project (`promptLanguage`, `en` when the value is missing or unknown) picks the table, for the page and for the tools, which read it from the stored document. A text written in the other language is not checked.
- **Where the text of a rule comes from.** The page shows its own translated sentence for a rule (the keys `lib.issue.*` of its dictionaries); the tool result carries the rule `id` and the English `messages` sentence.
- **Camera moves.** `cameraWords` serves the page (a camera instruction under a Control video) and `camera_change`, which compares the first move named in two consecutive instructions.
- **What the model writes.** The plugin translates nothing. The block tells the model the prompt language, the model writes in it, and a text is stored as given.

### Suggestions and `chat.prefill`

Three places of the page start the chat with a request already typed: the button **Ask the assistant to check continuity** (Director IA, tab Direction), the link **Ask the PotionUI assistant** of the prompt library and the link **Ask the assistant** of the Sound design workshop. Each calls `suggest(text)`, which calls `chat.prefill(text)` and then `chat.open()`. The texts are in the language of the interface, from the `assistant.suggest.*` keys. Nothing in the page sends a message for the user: `chat.send` is wired in `frontend/src/lib/host.js` and no button uses it.

| Host | What a suggestion does |
|---|---|
| It offers `chat.prefill` (the second plugin API batch, pull request M4-S4/PotionUI#4: https://github.com/M4-S4/PotionUI/pull/4, merged into this branch and described in `docs/plugin-api.md`) | The chat opens, focused on the composer, with the text in it and not sent. A draft that the user already typed is kept, and the suggestion is then not added. |
| It does not | `prefill` returns false and `open()` alone runs: the chat opens with an empty composer and the user types the request. |

There is nothing to configure for this: the page tests for `chat.prefill` itself before it calls it.

## What stays simulated

Six things are simulated. **Help › Simulated features** lists exactly these six, in this order and under the titles of the first column, and chapter 17 of both user guides repeats the list. The page marks them with a gray dashed badge, **Simulated**, never a yellow one. What the engine you picked cannot do is not a simulation: it has a plain gray badge instead ("MiniMax H3 only" on a profile, "Upscaler not available", "Not sent with this engine"). The Advanced workshop gives that last badge the same dashed outline as **Simulated**, because the setting it marks stays in the project and changes nothing.

| Item (title in the window) | What the window says | What is real next to it | Why, and what it means |
|---|---|---|---|
| Identity score | The identity similarity between two shots, in the continuity check and in the assistant’s review, is simulated. The color match really analyzes the images. | The color match is measured on real images: the seam frames of the shots when they have some, the thumbnails of the takes otherwise. Reference-guided generation (Ref2VA) is real with MiniMax-H3. | PotionUI offers no identity measure to plugins. The assistant's continuity check passes on the identity points of the page (`identity`), which come from this score. |
| Lip sync | No lip sync is computed: the lip sync options of the Sound design workshop and of the Advanced workshop stay in the project and change neither the takes nor the export. | The text of the dialogue feeds the subtitles. | MiniMax-H3 makes picture and soundtrack in one pass, so there is no separate lip-sync step to drive. |
| Generated voices and dialogue | The Sound design workshop generates no voice, dialogue or sound: preparing is simulated and what you hear is a simple synthesis in the browser. The dialogue text feeds the subtitles, and imported audio files play for real. | The audio files that users import play for real through the console, and the dialogue text feeds the subtitles. | PotionUI's marketplace has no speech or sound-effect preset, and the song preset (MiniMax-Music3) is not connected to the workshop. The sounds that the workshop prepares are synthesized by the browser (WebAudio). |
| Console automation and processing | The Auto button only switches a mode: no automation curve is recorded. Pan, inserts, sends and the master bus are heard in the browser but are not applied to the exported video, which keeps the gain, the track faders, mute, solo and the fades. | The console plays the audio files that users import. The web and social videos apply gain, track faders, mute, solo and fades (see Exports › The assembled video). | No curve is recorded, and the export does not apply pan, inserts (equalizer, compressor, filter), sends or the master bus. |
| ProRes, H.265 and stems | The master file (ProRes), the archive (H.265) and the audio stems are simulated: no file is written. The web and social MP4 videos and the FCPXML, OTIO, EDL and SRT files are real. | The web and social MP4 videos, and the FCPXML, OpenTimelineIO, EDL and SRT files. | PotionUI's video converter writes H.264 MP4 or VP9 WebM only, and Video Producer offers its web and social exports as H.264 MP4 only. Nothing renders audio per role. The Video tab of the export window ends these formats with "Simulated render complete: no file is written for this format." |
| Engine settings with no counterpart in the preset | The settings marked “Not sent with this engine” in the Advanced workshop stay in the project but do not change the takes: the seed (each take draws its own), the final resolution, steps, CFG, LoRA, windows, consistency, post-processing and the Hybrid AV audio driver, as well as the Hybrid builder weights and the guidance of the Control videos. | What the server reads from the project to generate: the direction, the shot prompts, the frames, the references, the shots and the choice of engine, plus the quality and the number of variants. | A preset exposes only the controls it declares; MiniMax-H3, for example, has no guidance and no negative prompt. See the list below. |

Everything else in `engine` stays in the project and drives nothing: `seed`, `quality`, `resolution`, `steps`, `guidance`, `overlap`, `windowLen`, `loras`, `post.*`, `consistency`, `lockIdentity`, `motionPriority`, `audioDriver`, `lipSync`, `offset`, `followCut`, `naming` and `autoInsert`, as well as `hybrid` and `profiles`. The Advanced workshop greys these controls, in its three steps and in the expert settings, and marks them with the badge "Not sent with this engine", whose tooltip says that the setting stays in the project but does not change the takes; **Variants per window** stays active. The Hybrid builder weights and the guidance of a Control video are not sent either, and carry no badge. The seed of a take is drawn by the server.

The button **Propose a breakdown** and **Production › Split synopsis into shots…** are not on the list: they are a plain function that cuts the synopsis into sentences, one sentence per shot. The breakdown that understands the story is the assistant's tool `vp_split_synopsis`, whose proposal fills the same Proposed breakdown list.

Everything else works for real: saved projects with their versions, imports through the PotionUI pickers and the gallery, thumbnails, the playback of video, images and audio, and the mixing console playing the audio files that users import; takes as real video files, finals by upscale (SeedVR2 or MiniMax H3) or by re-render, the estimate, the quota, the time calibration and the notifications; the PotionUI chat assistant, in the Video Producer assistant mode with its four tools; the FCPXML, OpenTimelineIO, EDL and SRT files, built by the server from the saved project with the real files of the shots, with the dialogue text in the subtitles; the web and social videos, assembled with ffmpeg; the seam frames; the 3D scene, with its scenes built from a picture, its imports, captures and reference videos; and the color analysis on the thumbnails of the takes and on the seam frames. The page keeps no simulated take: a shot whose media has no source any more shows "Media offline" in the viewer and on the timeline, and a document that still holds `results` is read without it.

## Troubleshooting

- **No engine in the Production bar**: the first setup step is not done, or the backend is turned off, or no video preset is assigned to the user, or a cloud backend has no video model turned on in its catalog. ComfyUI backends are never offered. The pop-up says "No engine" and, for an admin, links to the plugin settings.
- **The estimate shows "—" for the time**: no timing has been measured yet for this preset, engine and resolution on this machine (the calibration table has no row for them). It fills in after a few generations.
- **"Will stream through host RAM, slower"**: the estimated memory is above what the engine has. The generation is not blocked. Check the VRAM cap of the backend (`gpu_max_vram`, Admin → Backends); if the server lacks free RAM for the overflow, the engine refuses to start and the take fails with `host_ram_oom`.
- **A submit is refused for a limit** (409 `blocked`, block `quota_exceeded`): the user reached the monthly **Video Producer GPU minutes** set in Admin → Users → Plans. Takes in flight and takes waiting for a place count with their reservation; failed and cancelled takes are refunded. Until a preset has been measured, each second of video reserves 10 seconds of GPU, so the quota can look consumed faster than the real runs (the adjustment at the end of each take corrects it).
- **Generate selection is disabled**: there is no valid range, or no direction and no shot prompt in the range, or a prompt is empty, or the engine is gone or missing, or the server reports a block (the bar shows the first one): missing models ("Models to install for this preset: …"), a profile the preset cannot generate, a cloud model to pick, a quota spent. The rules are applied on the server too.
- **A take stays Queued**: a take past `max_parallel_jobs` waits for a place, and the user's other takes have to end first. Look at `GET /projects/{id}/queue` (`slots.in_flight` against `slots.max`) and raise **Max generations in flight per user** if the machine can take more. If nothing is in flight, check that the follow-up task is running: the server log shows "[VIDEO-PRODUCER] Take tracker started" after the application is ready, and the next generation starts it again. A take that is also Queued in PotionUI's own queue stays Queued here until its generation runs.
- **A take failed with `missing_model_file`**: a model file that the preset needs is not where PotionUI looks for it. Re-download it in Admin → Downloads or Admin → Models, and check that it was not moved or deleted. For a Studio server, the file must be on the worker too: the plugin only checks the files of this machine.
- **A take failed with `cuda_oom`**: the card ran out of memory. The memory estimate is a lower bound and only warns. Lower the draft resolution (**Draft resolution**), use a shorter shot, close the other applications that use the GPU, or switch to a lighter preset or a cloud model. `host_ram_oom` is the same problem on the host RAM that streaming needs.
- **The Upscale choice says "Upscaler not available"**: no SeedVR2 preset is assigned to the user (third setup step), or its model files are missing; the user can still re-render. A take of the base MiniMax-H3 preset does not depend on SeedVR2, but on its own latent upscaler file (fifth setup step). A final that fails to start with `missing_models` names the SeedVR2 fields (`diffusion_model`, `vae`, `prompt_embedding`) that have no installed file.
- **References are ignored in a MiniMax-H3 run**: the `fl2va` DiT file was picked for the References mode (see the reminder above).
- **A take failed after PotionUI restarted**: a generation that was running when the server stopped is marked failed and cannot resume. The user can start it again with Retry.
- **The export window says "ffmpeg is missing on the server: web and social exports need it."** (or a request answers 409 `ffmpeg_unavailable`): `ffmpeg` is not on the `PATH` of the PotionUI process. Install ffmpeg and ffprobe, make sure that process sees them, and restart PotionUI; the fourth setup step turns green and `GET /me` answers `ffmpeg: true`. In Docker, check the image. The page reads `ffmpeg` when it opens, so the user reloads it.
- **"No shot has a video file to export yet."** (409 `nothing_to_export`): no shot of the saved project has a file the server can find, for example because every shot is still "To generate", or the imported media were removed from the library or the gallery. The user generates or imports the shots and exports again. A single missing shot does not stop an export: it is black in the video.
- **"An export of this project is already running."** (409 `export_running`): a project has one export in flight. The user waits for it, or cancels it in the export window.
- **"The export folder is full: delete older exports and try again."** (429 `export_quota`): the folder of the user is over **Export cache per user (MB)** and nothing finished can be evicted, so the space is held by a job that is queued or running. Raise the setting, or wait for that job. The user can delete exports one by one in the export window (Previous exports).
- **An export stays Queued**: the server runs one export at a time, whoever asks, so it waits for the others. If nothing runs, the runner did not start: look for "[VIDEO-PRODUCER] Could not start the export runner" in the server log; the next export request, or a restart, starts it again.
- **An export moves slowly through "Converting to MP4"**: the delivery run uses the `slow` preset, and on a small server a long 4K sequence takes long; the progress shows how far it is. It fails with `transcode_failed` only when ffmpeg writes nothing for 5 minutes. Export at 1080p or 720p to go faster.
- **An export fails with `ffmpeg_failed`**: the message under the failure is the last line of ffmpeg's error output. Typical causes: a source file ffmpeg cannot read, an ffmpeg build without a filter or an encoder of the graph (see ffmpeg), or a restart of PotionUI during the export ("The server stopped during the export."). The user can start it again.
- **A done export leaves `mezzanine.mp4` or `graph.txt` in its folder**: another program (an antivirus, the indexer, OneDrive) held the file open while the server tried to delete it. Nothing to fix: the next export request of that user, or the next start of the server, sweeps it (see Exports › Storage and quota).
- **Cancelling an export leaves ffmpeg running**: the server kills the whole process tree, so the real ffmpeg behind a launcher such as `C:\ProgramData\chocolatey\bin\ffmpeg.exe` stops with it. If one stays, check that `psutil` is installed in the Python environment of PotionUI (it is in `requirements.txt`).
- **The first setup step says "Takes cannot run on This machine: no GPU is configured."**: the native backend is set to `cpu`, which PotionUI reports as having no GPU, so takes cannot run on it. Set a CUDA device in the backend (Admin → Backends), or use a Studio server or a cloud model.
- **An export fails with `store_failed`**: the MP4 was made but PotionUI refused to store it in the library of the user, for example because the storage plan of that user is full. Free some library space and export again.
- **A shot is black, or has no sound, in the video**: a shot with no file the server can find is black and silent (see Exports › Files for other software, "Which file a shot has"). A shot whose file has no soundtrack is silent too, and so is every shot when ffprobe is missing.
- **The sound differs from the console**: the export applies gain, track faders, mute and solo, and fades, not pan, inserts, sends, automation or the master bus. The levels are added without automatic leveling, so loud tracks can clip.
- **An FCPXML, OpenTimelineIO or EDL file does not find its media**: the paths in the file are paths on the PotionUI server. The user copies the media to the editing computer and relinks them. The files of generated takes are all called `1.mp4`; the folder tells them apart.
- **"This export no longer exists." or "The video is not ready yet." when downloading**: the export was deleted or evicted to make room, or it is not finished. The user exports again.
- **A seam frame is refused**: "This shot has no previous shot." (the first shot cannot use one); "“Shot” has no finished take yet." or "The previous shot has no finished take with a file." (409 `no_previous_take`: the previous shot has no finished take with a file); "The image could not be extracted from the take." (502 `extract_failed`: read `detail.data.code` in the network tools, `limit_exceeded` meaning that the storage plan of the project owner is full, and a frame at a given time also fails without ffprobe); "This shot is not in the saved project." (404 `shot_not_found`: save the project and try again).
- **A user's changes do not save ("Not saved — retry")**: read the answer of the failing `PUT /projects/{id}` in the network tools of the browser. 422 `invalid_doc` gives the path of the refused value (usually a tab opened before a plugin update: the user copies what they need, then reloads); 422 `doc_too_large` means the document is over 4 MiB; 409 `version_conflict` is handled by the page (see below); a 401 means the session expired.
- **"This project was deleted elsewhere"**: a save answered 404 `project_not_found` because the project had been deleted, from another tab or device or through the API. Nothing to fix: the page stopped saving it and opened the most recent project of the user, or created the starter project.
- **"Project reloaded: it changed elsewhere"**: the same project was saved from another tab, window or device, so the save of this page was refused with 409 `version_conflict` and the page loaded the saved version. Nothing to fix: the unsaved changes of that page are dropped, and the other versions are in the history.
- **A user cannot find an earlier version**: the history keeps only the **Versions kept per project** latest versions (50 by default). Raise the setting; versions already pruned do not come back.
- **Imported media do not show or play**: the library item or the generation was removed, so its URL no longer answers (and a new import of it answers 404 `media_not_found`). The user imports the media again. A take whose generation was deleted from the gallery no longer plays either.
- **A user sees the wrong language**: it is stored per user. Change it in Video Producer › Preferences… of the page, or with the `EN` or `FR` reminder of the status bar. Until a user chooses, the page follows the language of the browser.
- **The chat says "Chat is currently unavailable" (an admin reads "No enabled LLM configurations")**: no language model configuration is enabled and assigned to the user. Add one in Admin → LLM / Assistant and assign it to the user or to a group (see The assistant mode › Requirements).
- **The assistant answers in text and never shows an approval card**: **Tools** is off in the composer of the chat (tooltip "Tools OFF"), or the tool is off for that configuration (Admin → LLM / Assistant, the configuration, tab **Toolset**, group **Video Producer**), or the model cannot call tools.
- **The assistant knows nothing of the project, or the chat header says "Started in …"**: the conversation was started in another mode and keeps it. The user opens the chat from the Video Producer page and clicks **start a new chat**.
- **The assistant says the page is not open on a project**: the page sends its context only while it is open on a project. The user opens a project in Video Producer and asks again; a tool called without a project answers `project_not_found`.
- **A card shows Failed with `version_conflict`, `project_not_found` or `shot_not_found`**: the project was saved elsewhere at the very moment of the save, or was deleted, or the shot is no longer in the saved project. The user reloads the project and clicks **Retry** on the card, or asks again (see The assistant mode › Errors).
- **A change is approved and the page shows nothing**: the result was for another project (the chat shows "The assistant changed another project, not the one open here."). Nothing else to fix: the user opens that project.
- **A suggestion opens the chat with an empty box**: the host has no `chat.prefill` (see The assistant mode › Suggestions), or the composer already held a draft, which is kept.
- **A shot says "Media offline"**: the page cannot play the file of that shot any more, because the library item or the generation file was removed, or the shot kept no source. The viewer shows "Media offline" and says that the source file of the media is no longer available (import it again or choose a take). The user imports the media again or chooses a take. The export looks for the file again on the server, and a shot with no file is black and silent in the video.
- **Every take fails within seconds after an out-of-memory error** (native engine): the CUDA context of the PotionUI process can stay unusable after a `cuda_oom` (seen on a 12 GB card, with MiniMax-H3 before the 12 GB presets and with the Native language model). Restart PotionUI, then use the 12 GB presets or a lighter model (see Hardware).
- **The assistant ends with "CUDA out of memory" or never shows a card on the Native language model**: see The assistant mode › Which language model. Move the configuration to a llama-server or an Ollama set up as described there, or to an online provider.
- **Every turn fails with "Ollama returned status 400: request (… tokens) exceeds the available context size (4096 tokens)"**: the Ollama configuration has no **Context Size**, so Ollama opened its default context. Set **Context Size** to 16384 under Ollama Options (see The assistant mode › Which language model).
- **Every turn of the assistant is slow** (about 14 s instead of 1 to 2 s when the model thinks before each call; 6.5 to 14.5 s instead of 0.5 to 7.7 s when Ollama reloads the model at every turn): set **Reasoning Effort** to None for an OpenAI configuration, or **Thinking Mode** to Automatic or Disabled for Ollama, and set **Keep Alive** between 5m and 30m, since its default is 0.
- **A 3D scene from a picture fails at once**: the user has no **Image to Splat** preset, its MoGe-2 file `moge_2_vitl_normal_fp16.safetensors` is not installed, or the GPU minutes are spent; the scene list shows the reason, and **Try again** sends the job again. The job waits in the generation queue like a take.
- **The 3D view says that WebGL 2 is not available**: the browser runs without hardware acceleration (a remote desktop or a virtual machine often does). The rest of the page works.
- **The 3D view never leaves "Loading the 3D engine…"** and the browser shows a 404 on `chunks/engine-<hash>.js`: the `frontend/dist/chunks/` folder of the plugin is missing (a partial copy). Copy the whole `frontend/dist` folder, or rebuild it.


## Development

Run the tests of the plugin from the root of the PotionUI repository, with the Python 3.12 environment of the repository:

```bash
python -m pytest content/plugins/marketplace/video-producer/tests -q -m "not requires_gpu and not requires_models and not gc_sensitive"
python -m pytest tests/architecture tests/plugin_api tests/plugins/marketplace -q
```

When this page was written the first command ran 2,526 tests that pass, 3 that are skipped and 3 expected failures (xfail), in a Linux container. The second one runs `tests/plugins/marketplace/test_video_producer_manifest.py` (67 tests), which loads the mode and the four tools through the plugin registry, checks the routes of the exports, the export notification types, the five setup steps (their exact labels, and the report of the setup with the five steps still to do and their links) and the `FfmpegReady` step, and compares the five hardware-tier presets with the core presets they come from.

The first command covers:

- **The API, in one matrix.** `tests/test_routes_matrix.py` reads the three `### Routes` sections of this page (do not rename those headings) and fails when the routes that the plugin serves and the routes documented there differ; `GET /health` is left out of that comparison and described under Liveness. Every documented route has a success test, a test with no session (401), a refusal test and, for every route that takes a body or a validated parameter, a test with an invalid one. The refusal is that of a signed-in user who is not an admin and does not own the project (404 `project_not_found`, `take_not_found`, `job_not_found` or `media_not_found`; the lists and `GET /me` show nothing of another user's data), and every refusal checks that nothing was written. The routes also have their own files: `tests/test_routes_projects.py`, `test_routes_takes.py`, `test_routes_generation.py`, `test_routes_exports.py`, `test_routes_me.py` and `test_routes_media.py`.
- **The setup checks.** `tests/test_setup_checks.py` (see Setup checks).
- **Projects and generation.** `tests/test_projects.py` and `tests/test_routes_projects.py` check the document, the versions (a label is stored as given and returned by the history, `null` without one), and a document that still holds `results`: it is read without it, saved without it, and a save that differs only by `results` answers `unchanged`. `tests/test_estimate.py` and `tests/test_generation.py` check that the time measure and the quota reservation follow the backend that rendered the take.
- **The assistant.** `tests/test_chat_tools.py` (the four tools, their previews, writes and error codes), `tests/test_chat_context.py` (the context block and its bounds) and `tests/test_chat_rules.py` (the rule tables and their parity with the page copy).
- **The exports and the seam frame.** `tests/test_exports.py` (the four formats against the golden files of `tests/fixtures/exports/`, byte for byte, then their form; the file of a shot with `media=path` and `media=name`; the slug), `tests/test_exports_video.py` (the ffmpeg arguments built without running ffmpeg: trims, fades, look, black shots, mix, solo and mute; the option that reads the graph file for each version banner of `ffmpeg -version`; the jobs, the queue, the quota and eviction, cancel and restart; and, marked `requires_ffmpeg`, real assemblies of clips that ffmpeg generates, which check duration and size), `tests/test_routes_exports.py` (access, refusals, `Content-Disposition`, 202, `not_ready`, `export_running`, `GET /me`) and `tests/test_seam_frame.py` (the route, the choice of take, the errors, with the frame extraction replaced by a stand-in). The `requires_ffmpeg` tests are skipped when `ffmpeg` and `ffprobe` are not on the `PATH`, and the test that reads the OTIO file back is skipped when the `opentimelineio` package is not installed.

The presets of the `presets` folder go through the linter of the PotionUI presets, which also renders their pipelines:

```bash
python scripts/preset_lint.py --render content/plugins/marketplace/video-producer/presets
```

The backend imports only `src.plugin_api` and its submodules. The few reads that `plugin_api` does not offer yet (the media path on disk, the state of a preset, the catalog of cloud models, the stored row of a generation) go through `backend/core_bridge.py`, where they are gathered to be replaced one by one. The frontend is a Svelte 5 bundle that is built and committed; rebuild it after any change in `frontend/src`:

```bash
cd content/plugins && npm ci && node ../../scripts/build-plugins.mjs video-producer
```

Two release builds in a row must produce the same bytes: build twice and compare the sha256 of `frontend/dist/VideoProducerPage.js` and of the 3D chunk in `frontend/dist/chunks/`. The plugin build does not compile the Tailwind classes of the page: the build of the PotionUI app does, because the `content` list of its `tailwind.config.js` scans `frontend/src` of every plugin. After adding or changing a class, run from the root of the PotionUI repository:

```bash
cd frontend && npm run build
```

The tests of the page run with Node, from the folder of the plugin (`content/plugins/marketplace/video-producer`):

```bash
node --test "frontend/src/i18n/*.test.js"
node --test "frontend/src/lib/*.test.js"
```

When this page was written the first command ran 22 tests and the second one 151, all of them passing. The first command checks the two dictionaries. Every string of the page goes through `t()` with a key declared in `frontend/src/i18n/en/<domain>.json` and `fr/<domain>.json`, English being the default and French complete, and the test fails on: a key missing from one language, different parameters between the two languages, a `t()` key that does not exist, and a declared key that nothing uses. A key counts as used when a literal `t()` call names it or when it sits under one of the declared dynamic prefixes (`shell.error.`, `shell.menu.`, `commands.cmd.`, `generation.failed.`), and each prefix must really be used. It also checks that `generation.failed.<code>` matches the failure codes of the take cards, that every command and menu of `lib/commands.js` has a label, and that Help › Simulated features lists the six items of What stays simulated, each with a title and a text.

The second one covers the shortcut notation per platform, the keyboard focus rules, the icons, the engine and take helpers of `lib/generation.js`, the assistant helpers of `lib/assistant.js` (the context, how a tool result is applied, proposals and the check list), the shared rules of `lib/rules.js`, with the parity of `lib/rules.json`, the export helpers of `lib/exports.js` (job normalizing, polling and file names, checked with the same examples as `tests/test_exports_video.py`), the seam-frame helpers of `lib/seam.js`, the 3D scene helpers of `lib/scene3d/camera.js`, `lib/scene3d/files.js`, `lib/scene3d/doc.js` and `lib/scene3d/jobs.js` (the preset paths and their bounds, the interpolation, focal length and field of view, the free camera, the gap from the source view, the sampling of a glTF camera and of a render from its start key to its end key, the `potionui_view` comment, the glTF cameras, the self-contained `.gltf` packed into a `.glb` and the bounded read of a `.glb`, the render size capped at 1280, the signature of a 3D shot, its Control video moved, made stale or dropped with it, the old reference video pruned when unused, the job a scene follows, lost and orphan jobs, and the single polling chain), the migration of older documents in `lib/starter.js`, the scene, capture and render calls of `lib/api.js`, the grade of `lib/grade.js` (the CSS filter of a clip's look, and the same grade computed on the pixels for a browser whose canvas has no `filter`, as Safari before 18), the progress announcements of `lib/announce.js` (a screen reader hears the export and the generation progress at each 10 % or each change of step, and at most once every 3 seconds), and `lib/exchange.test.js`, which rebuilds the four files in the browser from the document of `tests/fixtures/exports/reference-project.json` and compares them byte for byte with the golden files `reference.fcpxml`, `reference.otio`, `reference.edl` and `reference.srt` that the Python tests also check, so that the page and the server cannot drift apart.

To change a contradiction rule, edit `backend/chat/rules.json`, copy the file to `frontend/src/lib/rules.json` and rebuild the page: the Python and node parity tests fail while the two copies differ.

This page and the two user guides are listed under `docs:` in the manifest, with this page first because the Setup section links to the first entry.

## License

GPL-3.0, like PotionUI. The licenses of the models that you use with it are separate: see the MiniMax-H3 reminder above.
