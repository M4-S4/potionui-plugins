# Video Producer

Video Producer brings a film workflow to AI video inside PotionUI: write a synopsis, split it into shots, generate draft takes for each shot, choose the best take, turn it into a final, then cut, match color, mix sound and deliver. It all happens in one page with five workspaces (Media, Director IA, Storyboard, 3D scene, Mix). Admins and users can both use it. An admin decides which engines and video presets exist (this machine, a studio server or a cloud model), sets a few plugin settings and, through plans, how many GPU minutes each user gets per month. The interface is in English by default and in French; each user picks the language and it is saved per user.

This page is the administration guide. Every user can read the user guide, in English (`docs/user-guide.md`) and in French (`docs/user-guide.fr.md`). Video Producer is built step by step: a section about something that does not exist yet ends with "Available from step N". Generation (step 4) is delivered: takes are real PotionUI generations, with a real estimate, quota, finals and follow-up. The assistant (step 5) and the video export (step 6) are not.

## Requirements

- PotionUI with plugins enabled, and an admin account to enable this one.
- At least one video engine: the native engine on this machine, a Remote Native worker, or a cloud provider with a video model. See Engines below.
- At least one Video Director preset, installed and assigned to the users who will generate: Wan, LTX, MiniMax-H3 or a cloud video preset. See Models and presets below.
- The model files that these presets need, downloaded. Video Producer picks them itself from the recommendations of each preset (see Generation › Required models); a preset with a missing file is blocked for generation.
- The SeedVR2 preset and its model files, assigned to the users, to turn a chosen draft take into a final. A take of the base MiniMax-H3 preset is enlarged by the upscale mode of its own preset instead.
- ffmpeg on the PotionUI server, to deliver a video file. See ffmpeg below.
- For a local engine, a GPU that meets PotionUI's own Hardware Requirements page: a Turing or newer NVIDIA card, driver 580 or newer, 8 GB of VRAM and 16 GB of system RAM as the supported minimum, 16 to 24 GB of VRAM and 32 GB of RAM recommended. Video families need more than the floor; that page has a verdict per family.
- For a cloud engine, an account and an API key with the provider (OpenRouter or Google AI Studio).
- The `jsonschema` Python package, which checks the project documents. The plugin relies on it; the PotionUI image already contains it, and its version is pinned in `constraints.txt`. There is nothing to install.

## Install and activate

In Admin → Plugins, enable **Video Producer**. A **Video Producer** entry appears in the sidebar; it opens the page `/plugins/video-producer`. The plugin keeps its own database tables (`video_producer_*`, created when the application starts); they hold the projects, the takes and the time measures (see Projects and media and Generation › Tables). A background task that follows running generations is started once the application is ready and stopped when the plugin is disabled (see Generation › Following the takes).

Admin → Plugins shows a **Setup needed** badge on the plugin until its setup steps are done, and the Overview tab opens with a **Setup** section that links to this page (it is the first entry of the plugin's documentation). The same page is under Admin → Documentation as **Video Producer: administration**. The user guides are in the **User Guide** section of the Documentation page that every signed-in user sees, as **Video Producer: user guide** and **Video Producer : guide utilisateur**; each one starts with a link to the other, because PotionUI has no notion of language for documents.

## The editor

The page is a complete editor with five workspaces: Media (the images, videos and audio files of the project, imported from the PotionUI library and gallery), Director IA (direction, references and results), Storyboard (the synopsis and one card per shot), 3D scene and Mix. Around them are ten menus, the project bar, the Production bar, the Inspector, the timeline (the mixing console takes its place in Mix), the status bar and the windows: prompt library and composer, Advanced workshop, Sound design workshop, export, preferences, keyboard shortcuts and command search.

The interface exists in English and in French. Each user picks the language in Video Producer › Preferences… or with the `EN` or `FR` reminder of the status bar; it is saved per user, and until a user chooses, the page follows the language of the browser (French for a French browser, English otherwise). Keyboard shortcuts show the notation of the user's system (⌘, ⌥ and ⇧ on a Mac, Ctrl, Alt and Shift elsewhere). The single-letter shortcuts (A, R, B, I, O, M and N) can be turned off in the Preferences.

What you see on the page at this step, and what comes later:

- The page opens the project that the user opened last, otherwise their most recent project. On a first visit, or when the user has no project left, it creates the starter project "Dawn at the harbour" ("Aube sur le port" in French) and opens it: a synopsis, the global direction in five fields, five shots of 5 seconds to generate, each with its shot prompt, a title, a marker and four empty audio tracks. It has no media, no take, no reference and no 3D scene (a button creates a sample point cloud on demand, marked simulated). Its name, synopsis, shot names, title and marker follow the language of the interface; its global direction and shot prompts follow the prompt language of the project, English by default. Projects are saved on the server as the user works, with a history of versions: File › New project… saves the current project, then starts an empty one, and File › Open… and File › Version history… are real. See Projects and media.
- The user imports images and videos from the PotionUI library (File › Import files…) and from the gallery (File › From the PotionUI gallery), and audio files from the library, with the multi-select pickers of PotionUI. The page resolves each pick with `POST /media/resolve`, shows real thumbnails and durations (and the frame rate when the library knows it), and plays the real video, images and audio. A media that is already in the project, with the same origin, is not imported twice.
- The **Generation engine** pop-up of the Production bar is filled from `GET /me` with the engines and presets that the user may run (see Engines). **Generate selection** starts real takes: they are PotionUI generations, and their videos play in the viewer, the Inspector and the Results tab. The estimate shows the time (measured on previous takes of the same preset, engine and resolution), the memory, the quota and, for admins only, the cloud cost. The status bar shows a GPU quota only when a plan sets a limit for the user. A shot with the FL2VA profile and no frame is not blocked: the page warns that it will be generated from text only, and the take card says "text only".
- The Assistant button, the Window menu and Ctrl+J open the PotionUI chat. The four tools of the Video Producer mode come with step 5.
- The Final Cut Pro, OpenTimelineIO, EDL and SRT files are real: the browser builds them and the user downloads them. Nothing is written to the export folder yet, and the video export is simulated. Video export comes with step 6.
- The mixing console plays the audio files that the user imported, for real. It synthesizes (WebAudio) the sounds that the Sound design workshop prepares.

## Setup checks

Admin → Plugins → Video Producer → Overview lists five setup steps, each backed by a check. Each one reads the state of the instance as it is now, so the list updates as you work through it.

| Step | Done when | What to do | Where |
|---|---|---|---|
| **Enable a native backend or a cloud video model** (`VideoEngineReady`) | An engine that can run Video Director presets is enabled: This machine, a Studio server, or a cloud backend with a video model turned on. ComfyUI backends do not count. | This machine: nothing to add, check that it is enabled. Studio server: add a Remote Native backend. Cloud: install the provider plugin, add its backend with the API key, turn on a video model in its catalog. | Admin → Backends, Admin → Plugins |
| **Install and assign at least one Video Director preset (Wan, MiniMax-H3, LTX or a cloud video preset)** (`VideoPresetsReady`) | At least one installed preset that declares Video Director is assigned to a user or a group. | Install the preset, then assign it to the people who will generate. Download its model files. | Admin → Presets, Admin → Downloads, Admin → Models |
| **Install SeedVR2 for final takes** (`UpscalerReady`) | The SeedVR2 preset is ready to upscale a take. | Install and assign the SeedVR2 preset and download its model files (a DiT and a VAE). | Admin → Presets, Admin → Downloads, Admin → Models |
| **Install ffmpeg for video delivery** (`FfmpegReady`) | The PotionUI server process can find ffmpeg. | Install ffmpeg and ffprobe so that they are on the `PATH` of the PotionUI process. In Docker, check the image. | The server |
| **If a MiniMax-H3 preset is installed, install its five model files (DiT, text encoder, video VAE, audio VAE, and the latent upscaler of its Upscale mode)** (`MiniMaxH3Ready`) | No MiniMax-H3 preset is installed, or every installed one has its four files, and, for a preset that has an Upscale mode (the base MiniMax-H3 preset, not Fast or VDN), the file of its latent upscaler (`upscale_model`). Each file is recognised by its SHA-256, among the files that the preset's model pickers recommend. | Download the files, and read the MiniMax-H3 reminder below before you do. | Admin → Downloads, Admin → Models |

How the steps behave, as PotionUI defines them:

- The text under a step comes from the check itself, so it tells you what is missing. An action button appears only when the check offers one, and it disappears once the step is done.
- A check that cannot run shows as a step still to do, with "This step could not be checked. See the server log."
- The checks run on every visit to Admin → Plugins. They only read local state and never call out to the network.

## Settings

In Admin → Plugins → Video Producer → Settings:

- **Draft resolution** (`draft_resolution`, default 832×480): the size of draft takes: 832×480, 960×544 or 1280×720. For a native preset, a draft is made at this size, turned to the orientation of the project (a portrait project gets the reversed size), when the preset offers it among the resolutions that fit the aspect ratio of the project; otherwise the preset's option that is closest in area is used. A cloud model uses its own default resolution (its smallest one when it declares no default). The final quality and a re-render use the largest option of the preset or of the model, whatever this setting says. It does not set the frame rate. A take keeps the frame rate of its preset (16 fps for Wan, 24 fps for MiniMax H3), while the timeline and the exports use the frame rate of the project.
- **Max generations in flight per user** (`max_parallel_jobs`, default 2): how many takes of one user PotionUI holds at once, whether running or waiting in its own queue, across all the projects of that user. Takes past that number stay **Queued** in Video Producer, with no PotionUI generation yet, and the follow-up task hands them over as soon as a place frees up (it looks every 2 seconds while takes are active). A waiting take already reserves its GPU minutes when its user's minutes are limited. See Quotas and Generation › Following the takes.
- **Export cache per user (MB)** (`export_dir_quota_mb`, default 2048): the size budget of each user's export folder. It is per user, not for the whole instance. See Storage and exports.
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
- **Reservation.** Each native take of a user whose minutes are limited (a plan limit, and not an exempt admin) reserves minutes as soon as it is created, even while it waits for a free place (`max_parallel_jobs`). The reservation is the measured time of the preset, engine and resolution when there is one (see Generation › Time calibration), otherwise 10 seconds of GPU work for every second of video: a 5-second shot reserves about 0.83 minute.
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

Video Producer can generate with every installed preset that declares Video Director, once it is assigned to the user: Wan, LTX-2, LTX-2.5, MiniMax-H3 (and its Fast and VDN variants), OpenRouter Video and Gemini Video. The frame rate of a take is set by the preset, and a user sees only the presets assigned to them.

| Preset | Profiles | What Video Producer asks of it |
|---|---|---|
| Wan 2.1 / 2.2, LTX-2 / 2.3, LTX-2.5 | FL2VA | Mode `video` of the preset, with a text-only, first-frame or first-and-last-frame composition. Wan runs at 16 fps by default. |
| MiniMax-H3 | FL2VA, Ref2VA, Hybrid AV | Mode `video` for FL2VA and Hybrid AV, mode `refs` for Ref2VA, mode `upscale` for a final. Fixed 24 fps, clips up to 15 seconds. |
| MiniMax-H3 Fast and MiniMax-H3 VDN | FL2VA, Hybrid AV | Mode `video` only. They have no `refs` mode, so no Ref2VA, and no `upscale` mode, so their finals go through SeedVR2 like those of Wan. Fixed 24 fps. |
| OpenRouter Video, Gemini Video | FL2VA | Mode `txt2video`, or `img2video` when the shot has a first frame and the model accepts one. |

The profiles that a preset cannot generate are greyed in the page and marked "MiniMax H3 only" (Ref2VA and Hybrid AV need a MiniMax H3 preset, and Ref2VA the base one), and the server answers the block `profile_unsupported` if a client asks for one anyway.

### Wan

- The preset defaults to 832×480 at 16 fps, which is also the default draft resolution of the plugin.
- PotionUI's hardware page lists Wan 2.2 14B (two experts) at 16 GB of VRAM or more, and the 5B variant as the realistic option for a small card (12 GB or more).

### LTX

- PotionUI's hardware page lists the LTX family as not yet recommended at any tier, because GPU validation is still open. LTX-2 and 2.3 are one all-in-one checkpoint of about 27 GB; LTX-2.5 uses separate files.

### MiniMax-H3: read before enabling

Video Producer offers MiniMax-H3 as soon as its presets are installed and assigned, on the same footing as Wan. The interface shows no warning badge, so this reminder is for admins. The page writes the name of the model as **MiniMax H3** in the engine pop-up, on the take cards and in its messages (for example "MiniMax H3 only" next to the profiles that need it).

- **Validation status.** PotionUI's own documentation says that no end-to-end run on real weights has been performed for the MiniMax-H3 family, that GPU validation is pending, and that the family is not recommended on any card size until that is done. Video Producer does not change that status.
- **License.** The weights are published under the MiniMax H3 Community License, not an open-source license. Its Applicable Territory excludes the European Union, the United Kingdom, the United States and the Republic of Korea, and the exclusion extends to what the model generates. Use there needs an individual authorization from MiniMax (https://platform.minimax.io/h3-license). A separate written authorization is required above US$20M of annual revenue, and a commercial product's interface must display "MiniMax H3" prominently. PotionUI ships no weights: the license is between you and MiniMax. The Fast and VDN variants carry the same terms. Showing the name in the pop-up and on the cards is a display choice of the page; whether it meets the license for your use is for you to judge.
- **Files.** Four separate files are needed: the DiT, the text encoder, the video VAE and the audio VAE. The base MiniMax-H3 preset needs a fifth one for its Upscale mode, the latent upscaler; the fifth setup step lists all of them. The Video mode needs the `fl2va` DiT file and the References mode the `ref2va` one. PotionUI cannot tell them apart, so check the file name: a wrong pick runs without an error and ignores the references. The Fast and VDN variants have neither a References mode nor an Upscale mode (their finals go through SeedVR2).
- **Clips.** MiniMax-H3 runs at a fixed 24 fps, for clips up to 15 seconds; its release notes recommend 5 seconds or more. Picture and soundtrack come out of one pass. A shot longer than 15 seconds is cut and the estimate warns `duration_clamped`.
- **Hardware.** It is the heaviest family that PotionUI documents. If the card cannot hold it, the engine streams the overflow from host RAM, which is slower; that needs the size of the overflow plus about 2 GB of free host RAM and refuses to start without it. The Production bar warns "will stream through host RAM, slower" and does not block.

In Video Producer, the reference-guided profile (Ref2VA) uses the References mode of MiniMax-H3. If a user says that references are ignored, check the DiT file first. In Admin → Presets → Configuration, the MiniMax-H3 preset has tag filters for its DiT, text encoder and VAE pickers if you want to narrow the choices.

### SeedVR2 for finals

- Making a take final upscales it. For a Wan, LTX, MiniMax-H3 Fast, MiniMax-H3 VDN or cloud take that is SeedVR2 (its `video_upscale` mode), to 720p, 1080p, 1440p or 2160p (shown as 4K); for a take of the base MiniMax-H3 preset, which has an `upscale` mode, it is the upscale mode of that preset itself, whose Target Size only has two values, so 720p and 1080p give HD and 1440p and 2160p give 2K. The other choice of the **Make final** window, **Re-render at full resolution**, generates the shot again at the highest resolution of the preset with the same seed. See Generation › Final takes.
- The DiT comes in four sizes: 3B fp8 (3.39 GB), 3B fp16 (6.78 GB), 7B fp8 (8.24 GB) and 7B fp16 (16.48 GB), plus a VAE of about 501 MB. SeedVR2 also needs a prompt embedding file. PotionUI's hardware page says it scales down cleanly to small cards: the batch size follows about 72 % of the free VRAM and is halved on an out-of-memory error.
- When no SeedVR2 preset is assigned to a user, the Upscale choice of the Make final window shows "Upscaler not available" and only the re-render is offered. A take of the base MiniMax-H3 preset still upscales, because its preset has an `upscale` mode. The Fast and VDN variants have none: without SeedVR2 their takes can only be re-rendered, and a client that asks for the upscale anyway gets 409 `blocked` with the block `upscale_unsupported`, whose message invites to install SeedVR2 or to render the take again.

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
3. The composition follows the profile. FL2VA: first and last frames linked to the shot give `flf`, a first frame alone gives `i2v`, and no frame gives `t2v` with the warning `fl2va_no_frame`. Ref2VA: mode `refs` of the base MiniMax-H3 preset, with the shot's own references followed by the global ones (at most 9 images, 3 videos and 3 audio files); a shot with no usable reference is blocked (`no_references`). Hybrid AV: the same document as FL2VA on a MiniMax-H3 preset, whose model makes the sound itself; the audio driver of the workshop is not sent.
4. The duration is the one of the shot, cut to the maximum of the preset (`duration_clamped`). The resolution follows the Settings section. The seed is drawn by the server for each take (and kept); a retry and a re-render reuse the seed of the take they come from.
5. The request goes to PotionUI as the owner of the project, even when an admin asks, with the idempotency key `vp:<take id>`. A take past `max_parallel_jobs` is created `queued` with no generation and is submitted later by the follow-up task, from the request that was frozen in its `request` column.

From the project, a take uses the direction, the shot prompts, the frames, the references, the aspect ratio and the shots; from the page it takes the engine, the quality and the number of variants. The other controls of the Advanced workshop are not sent (see What stays simulated).

### Required models

For each `model` field that the chosen mode of the preset requires, Video Producer takes the first recommended file of the preset that is installed and reachable, and passes it as `model:<id>`. The recommendations are matched by SHA-256, and by file name when a preset gives no SHA-256 (the SeedVR2 case). A field with no installed recommendation blocks the generation with `missing_models`, and `data.fields` lists the fields. The fields are:

- Wan: `text_encoder`, `vae`, then `t2v_high_noise_model` (and `t2v_low_noise_model` when it is installed) for text-only shots, `i2v_high_noise_model` (and `i2v_low_noise_model`) for first-frame and first-and-last-frame shots.
- MiniMax H3: `model`, `text_encoder`, `video_vae`, `audio_vae`. The upscale mode of a final of the base MiniMax-H3 preset also needs `upscale_model`, which the fifth setup step checks too.
- SeedVR2: `diffusion_model`, `vae`, `prompt_embedding`. These are also the files of the finals of Wan, LTX, MiniMax-H3 Fast and VDN and cloud takes.

A file that exists on this machine but not on the Studio server worker passes the check and then fails on the worker (see Troubleshooting).

### The estimate

`POST /projects/{id}/estimate` takes the same body as `generate` (`shots`, `quality`, `variants`, `preset_id`, `model_id`) and answers without starting anything:

| Key | Content |
|---|---|
| `shots` | One entry per shot: `shot_id`, `director_mode` (`t2v`, `i2v`, `flf` or `refs`), `seconds`, `resolution`, `fps`. |
| `vram` | `estimate_gb`, `free_gb`, `total_gb`, `streams`, `unknown`, `backend_id`. See GPU memory. |
| `time` | `seconds`, the expected total for all shots and variants, or `null` with no measure, and `samples`, the number of measures behind it. See Time calibration. |
| `quota` | `limit`, `used`, `remaining`, `exempt`, `needed_minutes`, `applies` (false for a cloud engine) and `blocks`. |
| `cost` | For an admin and a cloud model: `total_usd`, `known`, `message`. `null` for a user who is not an admin and for a native preset. |
| `blocks` | What stops the generation. |
| `warnings` | What the user should know. |

The page asks for it half a second after the last change, once the project is saved, with one request in flight at a time ("The estimate updates once the project is saved."). The Production bar shows the time, the memory and the quota (or the cost, for an admin) in a short line; hovering it gives the detail, for example "Time ≈ 4 min on MiniMax H3 (measured on 3 takes)" or "Time: — (no measure yet on MiniMax H3)", "Memory ≈ 22.5 GB, 16.0 GB free on Local Generation", "Quota: 5 min needed, 40 of 60 min left this month" ("Quota: exempt" for an exempt admin, "Cloud: no GPU quota used" for a cloud engine) and, for an admin, "Cost ≈ $0.84" or "Cost: unknown for this model".

### Blocks and warnings

`generate`, `final` and `retry` check the blocks again on the server. When one applies, the answer is 409 `blocked` and `detail.data.blocks` lists them, each as `{code, message, data?}`. The `message` is English; the page writes its own translated text from the `code` for every block except `upscale_unsupported`, for which it would show the English message (the page greys the Upscale choice instead of sending such a request).

| Block | When | `data` |
|---|---|---|
| `no_shots` | None of the shots exists in the project. | |
| `no_preset` | The preset is unknown, not assigned to the user, or has no mode that the Video Director can run. Also, for an upscale: SeedVR2 is not available to the user and the take does not come from an assigned MiniMax-H3 preset. | `preset_id` |
| `upscale_unsupported` | An upscale of a take of an assigned MiniMax-H3 variant that has no `upscale` mode (Fast, VDN), when SeedVR2 is not available to the user. The message invites to install SeedVR2 for final takes, or to render the take again at full resolution. | `preset_id` |
| `profile_unsupported` | Ref2VA or Hybrid AV on a preset that cannot generate it. | `profile`, `preset_id` |
| `missing_models` | A required model field has no installed recommended file. | `fields` |
| `quota_exceeded` | The takes need more minutes than the user has left. | `needed_minutes`, `remaining` |
| `no_model` | A cloud preset without a valid video model, or a model that needs a first frame for a shot that has none. | `model_id` or `shot_id` |
| `no_references` | Ref2VA on a shot with no usable reference. | `shot_id` |
| `source_unavailable` | The video of the take to upscale is no longer in the PotionUI history. | |

| Warning | When | `data` |
|---|---|---|
| `vram_stream` | The estimated memory is above the free VRAM: the model will stream through host RAM, slower. | `estimate_gb`, `free_gb` |
| `vram_unknown` | PotionUI could not estimate the memory. | |
| `time_unknown` | No take of this preset was measured at this resolution yet. | |
| `fl2va_no_frame` | The shot has no first frame: it is generated from text only. | `shot_id` |
| `duration_clamped` | The shot is longer than the preset or the model allows: it is cut. | `shot_id`, `max` |

The page shows the first block in the Production bar (it disables the buttons) and the first warning next to it, with the full list in the tooltip. `vram_unknown` and `time_unknown` only appear in the estimate tooltip.

### Time calibration

The plugin keeps its own time measures in `video_producer_calibration`. A row is written when a take finishes: the preset, the backend PotionUI used, the resolution, the seconds of video and the duration of the generation in milliseconds (`duration_ms`). An upscale take is measured under the upscaler preset, at the size it produces.

The estimate is the median of `duration_ms / 1000 / seconds` over the last 20 rows of the preset, backend and resolution, times the seconds asked for and the number of variants. `time.samples` is the number of rows behind it. With no row the time is `null` and the page shows "—"; the estimate also carries `time_unknown`. The same ratio sets the minutes that a take reserves from the quota (see Quotas). The table is shared by all the users of the instance, and the plugin never deletes its rows, not even with the project or the take they came from.

### GPU memory

For a native preset, the server asks PotionUI for a memory preview of the first shot (`preview_memory`) without starting anything. It reports a checkpoint-based estimate, which is a lower bound made from the size of the model files and an activation term, never a guarantee, and the free and total VRAM of the device of the backend that would run it. `streams` is true when the estimate is above the free VRAM: the native engine then streams the overflow from host RAM, which is slower, and the estimate carries `vram_stream` ("Will stream through host RAM, slower."). It is a warning, never a block. If PotionUI cannot give an estimate the answer is `unknown: true` with `vram_unknown`, again without blocking. A cloud engine has no memory figure.

The overflow needs its size plus about 2 GB of free host RAM; without it the engine refuses to start and the take fails (the core classifies it as `host_ram_oom`).

### Cloud cost

For an admin and a cloud model, the server asks PotionUI for the cost of the shots (`estimate_cloud_cost`). The prices are those of the catalog of the backend, filled in by the provider plugin. When the provider publishes no price for the model, `known` is false and the page says "Cost: unknown for this model". The cost is computed in the name of the admin who calls the estimate; a user who is not an admin gets `cost: null`. Spending is limited by the PotionUI plan limit **Cloud spend per month**, not by the GPU minutes.

### Final takes

`POST /projects/{id}/takes/{take}/final` (202) starts a new take, of quality `final`, linked to the take it comes from (`parent_take_id`) and carrying the same variant letter. The source take must be finished (409 `take_not_done` otherwise). The body is `{method, target}`.

- **`upscale`** enlarges the video of the source take as it is. For a Wan, LTX, MiniMax-H3 Fast, MiniMax-H3 VDN or cloud take: SeedVR2, mode `video_upscale`, with the source video as `input_video`, `resolution_target` set to the target, `restoration_intent` `faithful` and a random seed. For a take of the base MiniMax-H3 preset, whose preset has an `upscale` mode: that mode, with the source video and its Target Size (`hd720` and `fhd1080` give `hd`, `qhd1440` and `uhd2160` give `2k`, or the nearest value the mode offers). The take has `kind` `upscale`; its `resolution` is the size it is expected to produce and its real size is written when it ends.
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
| `POST /projects/{id}/estimate` | `{shots, quality, variants, preset_id, model_id?}` | The estimate above. `shots` is a list of shot ids, `quality` `draft` or `final`, `variants` an integer from 1 to 16, `model_id` the catalog id of a cloud model or `null`. |
| `POST /projects/{id}/generate` (202) | The same, and `label?` (at most 200 characters, validated and not stored) | `{takes}`: one per shot and variant. 409 `blocked` when a block applies. |
| `GET /projects/{id}/queue` | | `{takes, slots}`: the queued and running takes, and `slots` with `in_flight` (the owner's takes handed to PotionUI) and `max` (`max_parallel_jobs`). |
| `POST /projects/{id}/takes/{take}/choose` | `{chosen}` | `{take}`. Choosing a take unchooses the others of the shot; only a finished take can be chosen (409 `take_not_done`). |
| `POST /projects/{id}/takes/{take}/flag` | `{flag}`: `keep`, `reject` or `null` | `{take}`. |
| `POST /projects/{id}/takes/{take}/final` (202) | `{method, target}` | `{take}`, the new final take. |
| `DELETE /projects/{id}/takes/{take}` | | `{deleted}`, the id. A take in flight is cancelled first and its reservation refunded; the PotionUI generation and its video stay in the history of the user. |
| `POST /takes/{take}/cancel` | | `{take}`. Cancels the generation if it was handed over, refunds the reservation, and the take becomes `cancelled`. |
| `POST /takes/{take}/retry` (202) | | `{take}`, a new take with the same shot, seed, quality, preset and profile (a render is rebuilt from the current project). Only for a failed or cancelled take (409 `take_not_retryable`); the old one stays. |

`GET /me` is extended for generation. `engines` lists the enabled native and cloud backends (among others `id`, `name`, `kind` `local`, `remote` or `cloud`, `driver`, `execution_device`, `vram_total_gb`, `vram_free_gb` and `is_default`), and a cloud backend carries its enabled video models in `models` (`id`, `name`, `provider_model_id`, `tasks`, `typical_seconds`, `max_seconds`). `presets` lists the video presets and the upscaler preset that the user may run; a video preset carries `modes`, `video_director`, `resolutions` (the options of the resolution field of the main mode), `fps`, `fps_locked`, `limits` (`default_duration`, `max_duration`), `director_modes`, `profiles` (the ones it can generate), `upscaler`, `driver` and, for a cloud preset, `backend_id`. `features.upscaler` tells whether an upscaler preset is assigned to the user, and `upscale_targets` lists the four targets. `settings` carries the plugin settings, among them `draft_resolution` and `max_parallel_jobs`.

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
- PotionUI's categories, for example `cuda_oom` (out of GPU memory), `host_ram_oom` (out of host RAM while streaming weights), `missing_model_file`, `disk_full`, `corrupt_weights`, `auth_required`, `backend_unreachable`, and for cloud models `cloud_auth`, `cloud_credits`, `cloud_refused`, `cloud_rate_limited`, `cloud_unavailable`, `cloud_timeout` and `cloud_failed`.

### Tables

The tables are described under Projects and media › Tables (`video_producer_takes`, `video_producer_jobs`, `video_producer_calibration`).

## ffmpeg

Video Producer assembles the sequence of a video export with ffmpeg and converts it to H.264 MP4 or VP9 WebM with PotionUI's own video converter. Install ffmpeg and ffprobe on the server so that the PotionUI process finds them on its `PATH`. Without ffmpeg, the converter fails before it writes any file; the fourth setup step tells you about it beforehand. If you run PotionUI in Docker, check that the image contains ffmpeg.

Available from step 6: video export.

## Storage and exports

- Exports are real files: the video (H.264 MP4 or VP9 WebM), Final Cut Pro XML, OpenTimelineIO, EDL and SRT subtitles. They are written to the storage of the user who exports, under `video_producer/exports/`, and downloaded from the page.
- **Export cache per user (MB)** is the size budget of that folder, for each user.
- Takes are ordinary PotionUI generations: their files and thumbnails stay in the user's history and gallery, under the user who owns the project, and the page plays them from `/api/media/generations/<generation id>/<file name>`. Deleting a take, or its project, in Video Producer does not delete the generation or its files. A user who deletes the generation from the gallery breaks the playback of the take.
- Projects are rows of the database, not files (see Projects and media). Imported media are not copied: a project keeps a reference to the library item or to the generation file.

Available from step 6: exports.

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

The columns of the takes table beyond the first version (`director_mode`, `model_id`, `progress`, `step`, `variant`, `chosen`, `flag`, `profile`, `prompt_text`, `file_id`, `units_reserved`, `started_at`, `user_id`, `request`) are added at startup to a database that lacks them.

The document is stored as canonical JSON: sorted keys, compact, UTF-8; NaN and infinity are refused. A save whose canonical text equals the latest stored version stores nothing: the answer carries `unchanged: true` and the current version. Deleting a project cancels the takes it has in flight (their PotionUI generations are cancelled and their reserved minutes refunded), then deletes its rows, with those of its versions, takes and jobs; the library items and the generations it used, the generations of its takes included, stay in the user's library and gallery, and the calibration rows stay.

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
| `PUT /projects/{id}` | `{doc, version, label?}` | `{project}` with `id`, `name`, `version`, `updated_at` and `unchanged`. `version` is the integer the page read; `label`, when given, is at most 200 characters. |
| `DELETE /projects/{id}` | | `{deleted}`, the id. Cancels the takes in flight and refunds their reservations, then deletes the versions, takes and jobs of the project. |
| `GET /projects/{id}/versions` | | `{versions}`, latest first, each with `id`, `version`, `label`, `source_version`, `created_at` and `shots`. |
| `POST /projects/{id}/versions/{version}/restore` | | `{project}` with the restored document, as the next version. |
| `POST /media/resolve` | `{origin}` | `{media}` with `kind`, `media_type`, `url`, `filename` and `origin`. See Media resolution. |

The routes of the takes, of the estimate and of the generation are in Generation › Routes.

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
| `media_not_found` | 404 | The generation, the file or the library item does not exist, was removed, or is not the caller's to read. |

The codes of the takes, the estimate and the generation are in Generation › Take errors.

### The document

The document is the JSON that the page edits: the project settings (`name`, `fps`, `aspect`, `resolution`, `promptLanguage`), the direction and the synopsis, the shots (`clips`), `audio`, `titles`, `prompts`, `frames`, `controls`, `plans3d`, `markers`, `references`, `scenes`, the console (`lanes`, `aux`, `master`), `results` (the simulated takes of earlier versions, which the page reads and no longer writes), `profiles`, `engine`, `hybrid` and the `assets`, which are the media. Its schema is `DOC_SCHEMA` in `backend/projects.py`, a JSON Schema (draft 2020-12) checked with the `jsonschema` library when a project is created or saved, not when it is read.

The schema is strict. Every object lists all its fields as required and refuses any other one (`additionalProperties: false`), at every level, with one exception: `engine.preset` and `engine.model` are optional, so that a document saved before step 4 is still accepted. Fixed vocabularies are enumerations: the clip `stage` and `flag`, the audio roles (`Dialogue`, `Musique`, `Ambiance`, `SFX`), the lane `automation`, the insert types, the reference `space` and `scope`, the scene kinds, the control `source`, the result `quality` and `status`, and the asset `kind`, `role` and `synth`. Other fields are free text or numbers without bounds (for example `aspect`, `resolution`, `fps`, the marker `kind`, the clip `preset` or the engine `quality`), and `engine.seed`, `steps`, `guidance` and `variants` may be null.

`engine` holds the choice of engine: `backend` (the id of one of the engines of `GET /me`), `preset` (the id of the preset, or null) and `model` (the catalog id of the cloud model, or null for a native preset), and the number of `variants`. A clip holds in `take` the id of the take it plays (a row of `video_producer_takes`). The takes themselves are not in the document.

An asset has `id`, `kind` (`video`, `image` or `audio`), `name`, `src` (the address the page plays, or null), `origin` (`{kind: "history", generationId, fileId}`, `{kind: "library", itemId}` or null), `srcDur`, `width`, `height`, `fps`, `res`, `generated`, `quality`, `resultId`, `role`, `synth`, `transcript`, `character` and `lipSync`. The video of a take that is placed on the timeline is the asset `gen-<take id>`: `kind` `video`, `src` the URL of the take, `origin` the generation and the file, `generated` true, `quality` `draft` or `final` and `resultId` the id of the take.

A refusal (422 `invalid_doc`) means that the document sent does not match the schema of the backend. The page and the backend ship in the same plugin, so it usually means a browser tab opened before the plugin was updated, or a client other than the page: a tab that still runs a page from before step 4 does not write `engine.preset` and `engine.model`, which is accepted, but a new page against an old backend is refused. The page then shows "The project could not be saved: its content was refused." and keeps the changes in memory; the message of the answer, visible in the network tools of the browser, gives the path of the offending value.

The language of the prompts is the field `promptLanguage` (`en` or `fr`, required, `en` by default in the page). It is a choice per project, independent of the language of the interface, which stays a per-user setting. The backend only stores it: the page uses it for the text of the starter project, the templates and the composer of the prompt library, the contradiction rules, and, from step 5, the assistant. Changing it never rewrites existing text.

### Media resolution

The PotionUI pickers (the library for images, videos and audio, the gallery for images and videos) hand the page an origin: `{kind: "history", generationId, fileId}` or `{kind: "library", itemId}`. The page sends it to `POST /media/resolve`, which asks PotionUI to resolve the reference as the signed-in user and answers with what the page plays:

- `url`: `/api/media/generations/{generationId}/{file name}` for a gallery file, `/api/media/uploads/{file name}` for a library item. These routes belong to PotionUI; the plugin serves no media.
- `media_type`: `image`, `video` or `audio`, in lowercase.
- `filename`: the original file name. `kind`: the kind of the origin. `origin`: the origin as it was sent.

The page stores `url` and `origin` in the asset of the document. Nothing is copied: a project holds references, so removing a file from the library or the history breaks the media of every project that uses it, and `POST /media/resolve` answers 404 `media_not_found` for it from then on. The origin must have exactly the keys of its kind, with non-empty string ids. An origin of another kind answers 422 `invalid_ref` without calling PotionUI. The same resolution is used to give the references and frames of a shot to a generation, and the source video of an upscale.

### Access

A project belongs to the user who created it, and every route checks it.

- The list shows only the caller's own projects, admins included.
- Reading, saving, deleting, listing the versions, restoring, and every route of the takes, the estimate and the generation need the project to be the caller's, or the caller to be an admin. For anyone else the answer is 404 `project_not_found` (or `take_not_found`), never 403, so the existence of a project is not revealed. An admin who knows a project id can therefore read or change any project through the API, and start takes on it: they run as the owner of the project, with the owner's presets, quota and history. The page offers no way to list the projects of other users.
- `PUT /me` accepts only the caller's own projects as `last_project_id`, admins included.
- `POST /media/resolve` resolves only what the caller can read in PotionUI: their own library items and the generations that are visible to them.

## Notifications

Video Producer sends a PotionUI notification to the owner of a take when it is ready (**Video Producer: take ready**, type `video-producer.take_done`) and when it fails (**Video Producer: take failed**, type `video-producer.take_failed`). The text reads "<project name>: the draft take A is ready." or "<project name>: the final take B failed." followed by the reason, and carries `project_id`, `take_id` and `shot_id` as metadata. Both types are on by default, and each user can tune them in their notification preferences. The page also shows a toast when the takes it follows end ("2 draft takes ready", "1 take failed").

## The assistant mode

The Assistant button, the Window menu and the keyboard shortcut (Ctrl+J) open the PotionUI chat, in a chat mode named **Video Producer**. The mode has four tools: write the prompt of a shot, fix the contradictions with the global direction, split a synopsis into shots, and check the continuity between shots. The first three change the project, so each of them asks the user to approve the change before it is applied; the continuity check only reads.

The chat needs a language model configured in Admin → LLM / Assistant, like any other chat mode.

Available from step 5.

## Simulated in this version

The window Help › Simulated features lists eight items. Two of them change in a later step; the other six (the 3D render modes and engine settings, identity check, Gaussian Splat, Control video, voice and sound design, and edit audio for the workshop sounds and the automation curves) stay simulated, as the next section explains. The generation, the takes, the estimate and the engines left the window with step 4.

| Item in the window | In this version | Becomes real |
|---|---|---|
| 3D render modes and engine settings | The output modes "3D render" and "3D render + AI" start nothing. The settings greyed in the Advanced workshop are not sent to the engine: the seed (each take draws its own), the final resolution (the final uses the largest resolution of the engine), steps, CFG, LoRA, windows, consistency, post-processing and the Hybrid AV audio driver; nor are the Control videos and the Hybrid builder weights. Takes made by earlier versions keep their numbered thumbnail, marked Simulated, and are read only. | Stays simulated. |
| Synopsis breakdown | One sentence becomes one shot. | Step 5, with the assistant tool that splits a synopsis. |
| Video render | No video file is written. The Final Cut Pro, OpenTimelineIO, EDL and SRT files are real downloads. | Step 6, for H.264 MP4 and VP9 WebM. |

## What stays simulated

These parts keep a simulated interface, are marked with a gray dashed badge (never yellow), and are listed for users in Help › Simulated features and in the user guide.

| Item | Why it stays simulated |
|---|---|
| Identity score between shots | PotionUI offers no identity measure to plugins. Color matching is measured on the real frames, and reference-guided generation (Ref2VA) is real with MiniMax-H3. |
| Lip sync, generated voices and the rest of the Sound design workshop (Ambience, Foley, Texture, Impact, Music) | PotionUI's marketplace has no speech or sound-effect preset; the song preset (MiniMax-Music3) is not connected to the workshop. MiniMax-H3 makes picture and soundtrack in one pass, so there is no separate lip-sync step to drive. The text of the dialogue does feed the subtitles. The sounds that the workshop prepares are synthesized by the browser (WebAudio), and the mixing console plays them like that; the audio files that the user imports play for real. |
| ProRes, H.265 and audio stems | PotionUI's video converter writes H.264 MP4 or VP9 WebM only, and nothing renders audio per role. |
| Automation curves of the mixing console | The Auto button only switches a mode; no curve is recorded. |
| 3D scene, Gaussian Splat, 3D capture, imported Control video, and the production modes 3D render and 3D render + AI | The scene stays a 2D point preview; Gaussian Splat files are referenced and not loaded; the control video is not rendered from the scene and not sent to an engine. The "3D render" and "3D render + AI" modes start nothing. |
| Engine settings that are not sent | A preset exposes only the controls it declares; MiniMax-H3, for example, has no guidance and no negative prompt. What the server reads from the project to generate is the direction, the shot prompts, the frames, the references, the shots and the choice of engine, plus the quality and the number of variants. Everything else in `engine` stays in the project and drives nothing: `seed`, `quality`, `resolution`, `steps`, `guidance`, `overlap`, `windowLen`, `loras`, `post.*`, `consistency`, `lockIdentity`, `motionPriority`, `audioDriver`, `lipSync`, `offset`, `followCut`, `naming` and `autoInsert`, as well as `hybrid` and `profiles`. The Advanced workshop greys these controls, in its three steps and in the expert settings, and marks them with the badge "Not sent with this engine", whose tooltip says that the setting stays in the project but does not change the takes; **Variants per window** stays active. The Hybrid builder weights and the guidance of a Control video are not sent either, and carry no badge. The seed of a take is drawn by the server. |

Real since step 3: saved projects with their versions, imports through the PotionUI pickers and the gallery, thumbnails, the playback of video, images and audio, and the mixing console playing the audio files that users import. Real since step 4: takes as real video files, finals by upscale (SeedVR2 or MiniMax H3) or by re-render, the estimate, the quota, the time calibration and the notifications. Real once the other steps are delivered: the PotionUI chat assistant, color analysis on the real thumbnails of every take, FCPXML, OTIO, EDL and SRT exports, the assembled MP4 or WebM export, and dialogue text in the subtitles.

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
- **Export fails, or no video file appears**: the fourth setup step (ffmpeg), or the export folder has reached its budget.
- **A user's changes do not save ("Not saved — retry")**: read the answer of the failing `PUT /projects/{id}` in the network tools of the browser. 422 `invalid_doc` gives the path of the refused value (usually a tab opened before a plugin update: the user copies what they need, then reloads); 422 `doc_too_large` means the document is over 4 MiB; 409 `version_conflict` is handled by the page (see below); a 401 means the session expired.
- **"This project was deleted elsewhere"**: a save answered 404 `project_not_found` because the project had been deleted, from another tab or device or through the API. Nothing to fix: the page stopped saving it and opened the most recent project of the user, or created the starter project.
- **"Project reloaded: it changed elsewhere"**: the same project was saved from another tab, window or device, so the save of this page was refused with 409 `version_conflict` and the page loaded the saved version. Nothing to fix: the unsaved changes of that page are dropped, and the other versions are in the history.
- **A user cannot find an earlier version**: the history keeps only the **Versions kept per project** latest versions (50 by default). Raise the setting; versions already pruned do not come back.
- **Imported media do not show or play**: the library item or the generation was removed, so its URL no longer answers (and a new import of it answers 404 `media_not_found`). The user imports the media again. A take whose generation was deleted from the gallery no longer plays either.
- **A user sees the wrong language**: it is stored per user. Change it in Video Producer › Preferences… of the page, or with the `EN` or `FR` reminder of the status bar. Until a user chooses, the page follows the language of the browser.

Exports come with step 6.

## Development

Run the tests of the plugin from the root of the PotionUI repository, with the Python 3.12 environment of the repository:

```bash
python -m pytest content/plugins/marketplace/video-producer/tests -q -m "not requires_gpu and not requires_models and not gc_sensitive"
python -m pytest tests/architecture tests/plugin_api tests/plugins/marketplace -q
```

The backend imports only `src.plugin_api` and its submodules. The frontend is a Svelte 5 bundle that is built and committed; rebuild it after any change in `frontend/src`:

```bash
cd content/plugins && npm ci && node ../../scripts/build-plugins.mjs video-producer
```

Two release builds in a row must produce the same bytes. The plugin build does not compile the Tailwind classes of the page: the build of the PotionUI app does, because the `content` list of its `tailwind.config.js` scans `frontend/src` of every plugin. After adding or changing a class, run from the root of the PotionUI repository:

```bash
cd frontend && npm run build
```

The tests of the page run with Node, from the folder of the plugin (`content/plugins/marketplace/video-producer`):

```bash
node --test "frontend/src/i18n/*.test.js"
node --test "frontend/src/lib/*.test.js"
```

The first command checks the two dictionaries: same keys and same parameters in English and in French, every key used by the page exists, and every command and menu of `lib/commands.js` has a label. The second one covers the shortcut notation per platform, the keyboard focus rules, the icons and the engine and take helpers of `lib/generation.js`.

This page and the two user guides are listed under `docs:` in the manifest, with this page first because the Setup section links to the first entry.

## License

GPL-3.0, like PotionUI. The licenses of the models that you use with it are separate: see the MiniMax-H3 reminder above.
