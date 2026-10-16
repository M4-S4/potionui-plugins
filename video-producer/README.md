# Video Producer

Video Producer brings a film workflow to AI video inside PotionUI: write a synopsis, split it into shots, generate draft takes for each shot, choose the best take, turn it into a final, then cut, match color, mix sound and deliver. It all happens in one page with five workspaces (Media, Director IA, Storyboard, 3D scene, Mix). Admins and users can both use it. An admin decides which engines and video presets exist (this machine, a studio server or a cloud model), sets a few plugin settings and, through plans, how many GPU minutes each user gets per month. The interface is in English by default and in French; each user picks the language and it is saved per user.

This page is the administration guide. Every user can read the user guide, in English (`docs/user-guide.md`) and in French (`docs/user-guide.fr.md`). Video Producer is built step by step: a section about something that does not exist yet ends with "Available from step N".

## Requirements

- PotionUI with plugins enabled, and an admin account to enable this one.
- At least one video engine: the native engine on this machine, a Remote Native worker, or a cloud provider with a video model. See Engines below.
- At least one Video Director preset, installed and assigned to the users who will generate: Wan, LTX, MiniMax-H3 or a cloud video preset. See Models and presets below.
- The SeedVR2 preset and its model files, to turn a chosen draft take into a final.
- ffmpeg on the PotionUI server, to deliver a video file. See ffmpeg below.
- For a local engine, a GPU that meets PotionUI's own Hardware Requirements page: a Turing or newer NVIDIA card, driver 580 or newer, 8 GB of VRAM and 16 GB of system RAM as the supported minimum, 16 to 24 GB of VRAM and 32 GB of RAM recommended. Video families need more than the floor; that page has a verdict per family.
- For a cloud engine, an account and an API key with the provider (OpenRouter or Google AI Studio).
- The `jsonschema` Python package, which checks the project documents. The plugin relies on it; the PotionUI image already contains it, and its version is pinned in `constraints.txt`. There is nothing to install.

## Install and activate

In Admin → Plugins, enable **Video Producer**. A **Video Producer** entry appears in the sidebar; it opens the page `/plugins/video-producer`. The plugin keeps its own database tables (`video_producer_*`, created when the application starts); they hold the projects of the users (see Projects and media). A background task that follows running generations is started once the application is ready and stopped when the plugin is disabled.

Admin → Plugins shows a **Setup needed** badge on the plugin until its setup steps are done, and the Overview tab opens with a **Setup** section that links to this page (it is the first entry of the plugin's documentation). The same page is under Admin → Documentation as **Video Producer: administration**. The user guides are in the **User Guide** section of the Documentation page that every signed-in user sees, as **Video Producer: user guide** and **Video Producer : guide utilisateur**; each one starts with a link to the other, because PotionUI has no notion of language for documents.

Available from step 4: the background task that follows generations.

## The editor

The page is a complete editor with five workspaces: Media (the images, videos and audio files of the project, imported from the PotionUI library and gallery), Director IA (direction, references and results), Storyboard (the synopsis and one card per shot), 3D scene and Mix. Around them are ten menus, the project bar, the Production bar, the Inspector, the timeline (the mixing console takes its place in Mix), the status bar and the windows: prompt library and composer, Advanced workshop, Sound design workshop, export, preferences, keyboard shortcuts and command search.

The interface exists in English and in French. Each user picks the language in Video Producer › Preferences… or with the `EN` or `FR` reminder of the status bar; it is saved per user, and until a user chooses, the page follows the language of the browser (French for a French browser, English otherwise). Keyboard shortcuts show the notation of the user's system (⌘, ⌥ and ⇧ on a Mac, Ctrl, Alt and Shift elsewhere). The single-letter shortcuts (A, R, B, I, O, M and N) can be turned off in the Preferences.

What you see on the page at this step, and what comes later:

- The page opens the project that the user opened last, otherwise their most recent project. On a first visit, or when the user has no project left, it creates the starter project "Dawn at the harbour" ("Aube sur le port" in French) and opens it: a synopsis, the global direction in five fields, five shots of 5 seconds to generate, each with its shot prompt, a title, a marker and four empty audio tracks. It has no media, no take, no reference and no 3D scene (a button creates a sample point cloud on demand, marked simulated). Its name, synopsis, shot names, title and marker follow the language of the interface; its global direction and shot prompts follow the prompt language of the project, English by default. Projects are saved on the server as the user works, with a history of versions: File › New project… saves the current project, then starts an empty one, and File › Open… and File › Version history… are real. See Projects and media.
- The user imports images and videos from the PotionUI library (File › Import files…) and from the gallery (File › From the PotionUI gallery), and audio files from the library, with the multi-select pickers of PotionUI. The page resolves each pick with `POST /media/resolve`, shows real thumbnails and durations (and the frame rate when the library knows it), and plays the real video, images and audio. A media that is already in the project, with the same origin, is not imported twice.
- The engines are placeholder engines (This machine · RTX 4090, Studio server · 2 × RTX A6000 and Cloud provider · H100 on demand) and the generation is simulated: the estimate is indicative, no GPU is used, and each simulated take shows a numbered procedural thumbnail marked Simulated. Real generation comes with step 4. Cost figures are for admins only, and the status bar shows a GPU quota only when a plan sets a limit for the user. A shot with the FL2VA profile and no frame in its range is not blocked: the page warns that it will be generated from text only.
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
| **If a MiniMax-H3 preset is installed, install its four model files (DiT, text encoder, video VAE, audio VAE)** (`MiniMaxH3Ready`) | No MiniMax-H3 preset is installed, or every installed one has its four files. | Download the four files, and read the MiniMax-H3 reminder below before you do. | Admin → Downloads, Admin → Models |

How the steps behave, as PotionUI defines them:

- The text under a step comes from the check itself, so it tells you what is missing. An action button appears only when the check offers one, and it disappears once the step is done.
- A check that cannot run shows as a step still to do, with "This step could not be checked. See the server log."
- The checks run on every visit to Admin → Plugins. They only read local state and never call out to the network.

## Settings

In Admin → Plugins → Video Producer → Settings:

- **Draft resolution** (`draft_resolution`, default 832×480): the size of draft takes: 832×480, 960×544 or 1280×720. It does not set the frame rate. A take keeps the frame rate of its preset (16 fps for Wan, 24 fps for MiniMax-H3), while the timeline and the exports use the frame rate of the project.
- **Max generations in flight per user** (`max_parallel_jobs`, default 2): how many Video Producer generations one user can have running at once.
- **Export cache per user (MB)** (`export_dir_quota_mb`, default 2048): the size budget of each user's export folder. It is per user, not for the whole instance. See Storage and exports.
- **Versions kept per project** (`versions_kept`, default 50): how many saved versions each project keeps, from 5 to 500. When a project goes over it, the oldest versions are deleted. See Projects and media.

The first one is a choice between three values; the other three are numbers. Values are saved as text, and the form itself does not enforce a minimum or a maximum, so the plugin applies its own bounds: 1 to 16 parallel generations, 1 to 1,048,576 MB of export budget and 5 to 500 versions. A number outside its range is brought back to the nearest bound; an empty value, or one that is not a whole number, falls back to the default.

The language is not a setting here: each user chooses English or Français in the Preferences of the page, and it is stored for that user. Until a user chooses, the page follows the language of the browser. The language of the prompts is not a setting here either: each project has its own (see Projects and media).

Available from step 4: the effect of the draft resolution and of the number of parallel generations.

## Quotas

Admin → Users → Plans can limit one thing for this plugin: **Video Producer GPU minutes per month** (`video-producer.gpu_minutes`). It is a count in minutes, in a monthly window. To use it:

1. Open Admin → Users → Plans and open a plan you created. The built-in plans cannot take new limits: their **Add limit** button is disabled.
2. Click **Add limit** and pick **Video Producer GPU minutes per month**.
3. Enter the number of minutes, then assign the plan to groups or users in the same editor.

A plan without this limit means unlimited minutes. The **Admins are exempt** switch in the plans list applies as usual, and the usage of exempt admins is still measured.

How it is applied:

- Video Producer applies the limit itself, when a generation is submitted. PotionUI does not count these minutes on its own.
- The estimate that the Production bar shows before generating includes the remaining quota. When the quota is not enough, Generate selection is refused. This is the only resource that blocks: not enough memory only warns.
- A generation that is already running is never stopped by a quota.
- Cloud engines do not use GPU minutes. Their spending belongs to the PotionUI limit **Cloud spend per month** (`cloud_spend_usd_month`), which you add to a plan in the same way.

Available from step 4: counting, refunds when a generation fails or is cancelled, and the adjustment to the real duration.

## Engines

Video Producer offers the engines that you enabled for it:

- **This machine** (`native.local`): the native engine of the PotionUI server, always present. Nothing to add; check that it is enabled in Admin → Backends.
- **Studio server** (`native.remote`): a Remote Native backend, that is another machine or rented compute that runs a PotionUI Remote Native worker. In Admin → Backends add a Remote Native backend and paste the URL of the worker, or provision one from the backend's Infrastructure tab. The model files must also be on the worker; the backend's Models tab shows the exact per-file paths. The Remote Native documentation describes the worker.
- **Cloud**: the presets **OpenRouter Video** and **Gemini Video**. Install the `openrouter-provider` or the `google-gemini-provider` plugin, add its backend with your API key ("Add an OpenRouter backend with your API key" or "Add a Google Gemini backend with your AI Studio API key" in that plugin's setup), then turn on a video model in the backend's Catalog tab. Each shot is one paid request to the provider.

ComfyUI is not offered as an engine. Video Producer builds one Video Director document per shot, and a ComfyUI preset does not run Video Director documents: it keeps its own per-batch prompt relay.

Cloud cost: PotionUI records the cost of every cloud job and shows it to admins only (Admin → Generations, and the spend statistics). Video Producer follows the same rule: only an admin sees a cost estimate, and a price that the provider does not publish is never invented.

Available from step 4: choosing an engine in the Production bar and the live list of engines.

## Models and presets

Video Producer can generate with every installed preset that declares Video Director, once it is assigned to the user: Wan, LTX-2, LTX-2.5, MiniMax-H3 (and its Fast and VDN variants), OpenRouter Video and Gemini Video. The frame rate of a take is set by the preset, and a user sees only the presets assigned to them.

### Wan

- The preset defaults to 832×480 at 16 fps, which is also the default draft resolution of the plugin.
- PotionUI's hardware page lists Wan 2.2 14B (two experts) at 16 GB of VRAM or more, and the 5B variant as the realistic option for a small card (12 GB or more).

### LTX

- PotionUI's hardware page lists the LTX family as not yet recommended at any tier, because GPU validation is still open. LTX-2 and 2.3 are one all-in-one checkpoint of about 27 GB; LTX-2.5 uses separate files.

### MiniMax-H3: read before enabling

Video Producer offers MiniMax-H3 as soon as its presets are installed and assigned. The interface shows no warning badge, so this reminder is for admins.

- **Validation status.** PotionUI's own documentation says that no end-to-end run on real weights has been performed for the MiniMax-H3 family, that GPU validation is pending, and that the family is not recommended on any card size until that is done. Video Producer does not change that status.
- **License.** The weights are published under the MiniMax H3 Community License, not an open-source license. Its Applicable Territory excludes the European Union, the United Kingdom, the United States and the Republic of Korea, and the exclusion extends to what the model generates. Use there needs an individual authorization from MiniMax (https://platform.minimax.io/h3-license). A separate written authorization is required above US$20M of annual revenue, and a commercial product's interface must display "MiniMax H3" prominently. PotionUI ships no weights: the license is between you and MiniMax. The Fast and VDN variants carry the same terms.
- **Files.** Four separate files are needed: the DiT, the text encoder, the video VAE and the audio VAE; the fifth setup step lists them. The Video mode needs the `fl2va` DiT file and the References mode the `ref2va` one. PotionUI cannot tell them apart, so check the file name: a wrong pick runs without an error and ignores the references. The Fast variant has no References mode.
- **Clips.** MiniMax-H3 runs at a fixed 24 fps, for clips up to 15 seconds; its release notes recommend 5 seconds or more. Picture and soundtrack come out of one pass.
- **Hardware.** It is the heaviest family that PotionUI documents. If the card cannot hold it, the engine streams the overflow from host RAM, which is slower; that needs the size of the overflow plus about 2 GB of free host RAM and refuses to start without it. The Production bar warns "will stream through host RAM, slower" and does not block.

In Video Producer, the reference-guided profile (Ref2VA) uses the References mode of MiniMax-H3. If a user says that references are ignored, check the DiT file first. In Admin → Presets → Configuration, the MiniMax-H3 preset has tag filters for its DiT, text encoder and VAE pickers if you want to narrow the choices.

### SeedVR2 for finals

- Making a take final upscales it with SeedVR2 (its `video_upscale` mode), to 720p, 1080p, 1440p or 2160p. A secondary action, Re-render, generates the shot again at the highest resolution of the preset with the same seed.
- The DiT comes in four sizes: 3B fp8 (3.39 GB), 3B fp16 (6.78 GB), 7B fp8 (8.24 GB) and 7B fp16 (16.48 GB), plus a VAE of about 501 MB. PotionUI's hardware page says it scales down cleanly to small cards: the batch size follows about 72 % of the free VRAM and is halved on an out-of-memory error.

Available from step 4: making a take final.

### Cloud presets

- **OpenRouter Video** and **Gemini Video** come with their provider plugins. Install and assign them like any other preset, and turn on a video model in the backend's catalog.

Available from step 4: generating with these presets.

## ffmpeg

Video Producer assembles the sequence of a video export with ffmpeg and converts it to H.264 MP4 or VP9 WebM with PotionUI's own video converter. Install ffmpeg and ffprobe on the server so that the PotionUI process finds them on its `PATH`. Without ffmpeg, the converter fails before it writes any file; the fourth setup step tells you about it beforehand. If you run PotionUI in Docker, check that the image contains ffmpeg.

Available from step 6: video export.

## Storage and exports

- Exports are real files: the video (H.264 MP4 or VP9 WebM), Final Cut Pro XML, OpenTimelineIO, EDL and SRT subtitles. They are written to the storage of the user who exports, under `video_producer/exports/`, and downloaded from the page.
- **Export cache per user (MB)** is the size budget of that folder, for each user.
- Takes are ordinary PotionUI generations: their files and thumbnails stay in the user's history and gallery.
- Projects are rows of the database, not files (see Projects and media). Imported media are not copied: a project keeps a reference to the library item or to the generation file.

Available from step 6: exports. Takes appear from step 4.

## Projects and media

The projects of every user are saved on the server, in the plugin's tables, as the user works. This section is the reference for the tables, the setting, the routes and their error codes, the document schema, the media resolution and the access rules. The routes sit under `/api/plugins/video-producer` and need a signed-in user.

### Tables

| Table | What it holds |
|---|---|
| `video_producer_projects` | One row per project: `id`, `user_id` (the owner), `name` (a copy of the name inside the document), `doc` (the document, as canonical JSON text), `version` (1 at creation, +1 per save), `created_at`, `updated_at`. |
| `video_producer_versions` | One row per stored version: `project_id`, `version`, `doc`, `label`, `source_version`, `created_at`. `source_version` is filled only for a version created by a restore, with the number of the version restored; the column is added at startup to a database that lacks it. |
| `video_producer_takes`, `video_producer_jobs`, `video_producer_calibration` | Created at startup and unused for now: real takes arrive with step 4. The simulated takes live inside the document. Deleting a project already deletes the takes and jobs rows that belong to it. |

The document is stored as canonical JSON: sorted keys, compact, UTF-8; NaN and infinity are refused. A save whose canonical text equals the latest stored version stores nothing: the answer carries `unchanged: true` and the current version. Deleting a project deletes its rows only; the library items and the generations it used stay in the user's library and gallery.

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
| `DELETE /projects/{id}` | | `{deleted}`, the id. Also deletes the versions, takes and jobs of the project. |
| `GET /projects/{id}/versions` | | `{versions}`, latest first, each with `id`, `version`, `label`, `source_version`, `created_at` and `shots`. |
| `POST /projects/{id}/versions/{version}/restore` | | `{project}` with the restored document, as the next version. |
| `POST /media/resolve` | `{origin}` | `{media}` with `kind`, `media_type`, `url`, `filename` and `origin`. See Media resolution. |

`GET /me` and `PUT /me` also carry the last project of the user: `last_project_id`, a per-user plugin setting like the locale. `GET /me` returns it as `null` when the stored project no longer exists or is not the caller's, and lists `versions_kept` among its `settings`. `PUT /me` takes `{locale?, last_project_id?}`; a key left out stays as it is, and `last_project_id: null` forgets the project. A body with neither key answers 422 `invalid_locale`.

### Errors

An error answers with its HTTP status and a body `detail` shaped `{"success": false, "error": <code>, "message": <text>, "data": <object, when there is one>}`. The page maps the codes to its own messages. The codes of this step:

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

### The document

The document is the JSON that the page edits: the project settings (`name`, `fps`, `aspect`, `resolution`, `promptLanguage`), the direction and the synopsis, the shots (`clips`), `audio`, `titles`, `prompts`, `frames`, `controls`, `plans3d`, `markers`, `references`, `scenes`, the console (`lanes`, `aux`, `master`), the simulated `results`, `profiles`, `engine`, `hybrid` and the `assets`, which are the media. Its schema is `DOC_SCHEMA` in `backend/projects.py`, a JSON Schema (draft 2020-12) checked with the `jsonschema` library when a project is created or saved, not when it is read.

The schema is strict. Every object lists all its fields as required and refuses any other one (`additionalProperties: false`), at every level. Fixed vocabularies are enumerations: the clip `stage` and `flag`, the audio roles (`Dialogue`, `Musique`, `Ambiance`, `SFX`), the lane `automation`, the insert types, the reference `space` and `scope`, the scene kinds, the control `source`, the result `quality` and `status`, and the asset `kind`, `role` and `synth`. Other fields are free text or numbers without bounds (for example `aspect`, `resolution`, `fps`, the marker `kind`, the clip `preset` or the engine `quality`), and `engine.seed`, `steps`, `guidance` and `variants` may be null.

An asset has `id`, `kind` (`video`, `image` or `audio`), `name`, `src` (the address the page plays, or null), `origin` (`{kind: "history", generationId, fileId}`, `{kind: "library", itemId}` or null), `srcDur`, `width`, `height`, `fps`, `res`, `generated`, `quality`, `resultId`, `role`, `synth`, `transcript`, `character` and `lipSync`.

A refusal (422 `invalid_doc`) means that the document sent does not match the schema of the backend. The page and the backend ship in the same plugin, so it usually means a browser tab opened before the plugin was updated, or a client other than the page. The page then shows "The project could not be saved: its content was refused." and keeps the changes in memory; the message of the answer, visible in the network tools of the browser, gives the path of the offending value.

The language of the prompts is the field `promptLanguage` (`en` or `fr`, required, `en` by default in the page). It is a choice per project, independent of the language of the interface, which stays a per-user setting. The backend only stores it: the page uses it for the text of the starter project, the templates and the composer of the prompt library, the contradiction rules, and, from step 5, the assistant. Changing it never rewrites existing text.

### Media resolution

The PotionUI pickers (the library for images, videos and audio, the gallery for images and videos) hand the page an origin: `{kind: "history", generationId, fileId}` or `{kind: "library", itemId}`. The page sends it to `POST /media/resolve`, which asks PotionUI to resolve the reference as the signed-in user and answers with what the page plays:

- `url`: `/api/media/generations/{generationId}/{file name}` for a gallery file, `/api/media/uploads/{file name}` for a library item. These routes belong to PotionUI; the plugin serves no media.
- `media_type`: `image`, `video` or `audio`, in lowercase.
- `filename`: the original file name. `kind`: the kind of the origin. `origin`: the origin as it was sent.

The page stores `url` and `origin` in the asset of the document. Nothing is copied: a project holds references, so removing a file from the library or the history breaks the media of every project that uses it, and `POST /media/resolve` answers 404 `media_not_found` for it from then on. The origin must have exactly the keys of its kind, with non-empty string ids. An origin of another kind answers 422 `invalid_ref` without calling PotionUI.

### Access

A project belongs to the user who created it, and every route checks it.

- The list shows only the caller's own projects, admins included.
- Reading, saving, deleting, listing the versions and restoring need the project to be the caller's, or the caller to be an admin. For anyone else the answer is 404 `project_not_found`, never 403, so the existence of a project is not revealed. An admin who knows a project id can therefore read or change any project through the API; the page offers no way to list the projects of other users.
- `PUT /me` accepts only the caller's own projects as `last_project_id`, admins included.
- `POST /media/resolve` resolves only what the caller can read in PotionUI: their own library items and the generations that are visible to them.

Real takes arrive with step 4. Until then a project holds no take file and the takes tables stay empty.

## Notifications

Video Producer sends a PotionUI notification when a take is ready (**Video Producer: take ready**) and when a take fails (**Video Producer: take failed**). Both are on by default, and each user can tune them in their notification preferences.

Available from step 4.

## The assistant mode

The Assistant button, the Window menu and the keyboard shortcut (Ctrl+J) open the PotionUI chat, in a chat mode named **Video Producer**. The mode has four tools: write the prompt of a shot, fix the contradictions with the global direction, split a synopsis into shots, and check the continuity between shots. The first three change the project, so each of them asks the user to approve the change before it is applied; the continuity check only reads.

The chat needs a language model configured in Admin → LLM / Assistant, like any other chat mode.

Available from step 5.

## Simulated at this step

The window Help › Simulated features lists eight items. Three of them change in a later step; the other five (identity check, Gaussian Splat, Control video, voice and sound design, and edit audio for the workshop sounds and the automation curves) stay simulated, as the next section explains.

| Item in the window | At this step | Becomes real |
|---|---|---|
| AI generation and 3D render | Progress, steps and takes are simulated: each take shows a numbered procedural thumbnail marked Simulated, and the estimates of time, memory, quota and cost are indicative. | Step 4. The 3D render modes stay simulated. |
| Synopsis breakdown | One sentence becomes one shot. | Step 5, with the assistant tool that splits a synopsis. |
| Video render | No video file is written. The Final Cut Pro, OpenTimelineIO, EDL and SRT files are real downloads. | Step 6, for H.264 MP4 and VP9 WebM. |

## What stays simulated

These parts keep a simulated interface, are marked with a gray dashed badge (never yellow), and are listed for users in Help › Simulated features and in the user guide.

| Item | Why it stays simulated |
|---|---|
| Identity score between shots | PotionUI offers no identity measure to plugins. Color matching is measured on the real frames, and reference-guided generation (Ref2VA) is real with MiniMax-H3. |
| Lip sync, generated voices and the rest of the Sound design workshop (Ambience, Foley, Texture, Impact, Music) | PotionUI's marketplace has no speech or sound-effect preset; the song preset (MiniMax-Music3) is not connected to the workshop. MiniMax-H3 makes picture and sound in one pass, so there is no separate lip-sync step to drive. The text of the dialogue does feed the subtitles. The sounds that the workshop prepares are synthesized by the browser (WebAudio), and the mixing console plays them like that; the audio files that the user imports play for real. |
| ProRes, H.265 and audio stems | PotionUI's video converter writes H.264 MP4 or VP9 WebM only, and nothing renders audio per role. |
| Automation curves of the mixing console | The Auto button only switches a mode; no curve is recorded. |
| 3D scene, Gaussian Splat, 3D capture, imported Control video, and the production modes 3D render and 3D render + AI | The scene stays a 2D point preview; Gaussian Splat files are referenced and not loaded; the control video is not rendered from the scene. |
| Engine settings with no counterpart in the chosen preset | A preset exposes only the controls it declares; MiniMax-H3, for example, has no guidance and no negative prompt. The fields are `hybrid`, `profiles`, `consistency`, `lockIdentity`, `motionPriority`, `offset`, `followCut`, `guidance`, `overlap`, `windowLen`, `loras`, `post.*`, `audioDriver`, `lipSync`, `naming`, `autoInsert` and `quality`. At this step they drive nothing; with real engines (step 4) they stay visible, grayed and marked simulated. |

Real since step 3: saved projects with their versions, imports through the PotionUI pickers and the gallery, thumbnails, the playback of video, images and audio, and the mixing console playing the audio files that users import. Real once the other steps are delivered: takes as real video files, finals by SeedVR2 upscale, the PotionUI chat assistant, color analysis on the real thumbnails, FCPXML, OTIO, EDL and SRT exports, the assembled MP4 or WebM export, and dialogue text in the subtitles.

## Troubleshooting

- **No engine in the Production bar**: the first setup step is not done, or the backend is turned off or not assigned. ComfyUI backends are never offered.
- **The estimate shows "—" for the time**: no timing has been measured yet for this preset, engine and resolution on this machine. It fills in after a few generations.
- **"Will stream through host RAM, slower"**: the estimated memory is above what the engine has. The generation is not blocked. Check the VRAM cap of the backend (`gpu_max_vram`, Admin → Backends); if the server lacks free RAM for the overflow, the engine refuses to start and the take fails.
- **A submit is refused for a limit**: the user reached the monthly **Video Producer GPU minutes** set in Admin → Users → Plans.
- **Generate selection is disabled**: there is no valid range, or no direction and no shot prompt in the range, or a prompt is empty, or the FL2VA profile has no start or end frame, or the quota is spent. The rules are applied on the server too.
- **References are ignored in a MiniMax-H3 run**: the `fl2va` DiT file was picked for the References mode (see the reminder above).
- **A take failed after PotionUI restarted**: a generation that was running when the server stopped is marked failed and cannot resume. The user can start it again.
- **Export fails, or no video file appears**: the fourth setup step (ffmpeg), or the export folder has reached its budget.
- **A user's changes do not save ("Not saved — retry")**: read the answer of the failing `PUT /projects/{id}` in the network tools of the browser. 422 `invalid_doc` gives the path of the refused value (usually a tab opened before a plugin update: the user copies what they need, then reloads); 422 `doc_too_large` means the document is over 4 MiB; 409 `version_conflict` is handled by the page (see below); a 401 means the session expired.
- **"This project was deleted elsewhere"**: a save answered 404 `project_not_found` because the project had been deleted, from another tab or device or through the API. Nothing to fix: the page stopped saving it and opened the most recent project of the user, or created the starter project.
- **"Project reloaded: it changed elsewhere"**: the same project was saved from another tab, window or device, so the save of this page was refused with 409 `version_conflict` and the page loaded the saved version. Nothing to fix: the unsaved changes of that page are dropped, and the other versions are in the history.
- **A user cannot find an earlier version**: the history keeps only the **Versions kept per project** latest versions (50 by default). Raise the setting; versions already pruned do not come back.
- **Imported media do not show or play**: the library item or the generation was removed, so its URL no longer answers (and a new import of it answers 404 `media_not_found`). The user imports the media again.
- **A user sees the wrong language**: it is stored per user. Change it in Video Producer › Preferences… of the page, or with the `EN` or `FR` reminder of the status bar. Until a user chooses, the page follows the language of the browser.

Available from step 4: everything that concerns generation. Exports from step 6.

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

The first command checks the two dictionaries: same keys and same parameters in English and in French, every key used by the page exists, and every command and menu of `lib/commands.js` has a label. The second one covers the shortcut notation per platform, the keyboard focus rules and the icons.

This page and the two user guides are listed under `docs:` in the manifest, with this page first because the Setup section links to the first entry.

## License

GPL-3.0, like PotionUI. The licenses of the models that you use with it are separate: see the MiniMax-H3 reminder above.
