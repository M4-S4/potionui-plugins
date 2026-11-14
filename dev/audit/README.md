Potion audit
============

An external API client that audits the presets PotionUI ships by default. It runs on a workstation, connects to the instance to test by its URL and never starts an instance itself. Results are written to an output folder outside this repository and are never committed.

It is for the operator of a PotionUI instance, or a coding agent working for them, who wants to know which presets of that instance work on its hardware. It runs one short generation per preset and mode, checks each output (duration, size, frames, sound, the run report of the server), and writes a report that can be read in a browser and compared with the report of another machine. It can also run a Video Producer scenario: a small film made through the plugin's API.

What it needs and what it costs: an admin account on the instance, the models already installed there, and the GPU of the instance for as long as the run lasts. Only the commands marked "yes" in the GPU column of [Commands](#commands) use the GPU, and each of them asks for `--confirm-gpu`.

Replaying the audit on another machine
--------------------------------------

The audit is made to be replayed as it is: the pack, its frozen inputs and its case file are in this folder, so two machines that run the same pack can be compared cell by cell with `merge`.

What the machine needs:

- a PotionUI instance its owner agrees to have audited, reachable by its URL, and an admin account on it;
- the models of the presets to audit, installed on the instance by its operator: the audit downloads none and lists the ones that are missing;
- `git` and [uv](https://docs.astral.sh/uv/);
- a folder outside the checkout for the runs and the reports, with tens of GB free for the `full` profile;
- the two environment variables of the account, set by the operator (see Setup).

Then give the prompt below to a coding agent on that machine, with the values filled in. It sends the agent to [PROMPT.md](PROMPT.md), which holds the steps, the three stops where the agent waits for the operator, and the traps. An operator can follow PROMPT.md by hand instead.

```text
Run the Potion audit on this machine.

1. Get the tool: clone https://github.com/M4-S4/potionui-plugins, or update the
   checkout that is already here, and work from its dev/audit/ folder.
2. Read dev/audit/PROMPT.md in full, then follow it step by step. dev/audit/README.md is
   the reference for every command.
3. Use these parameters:
   URL = <base URL of the instance, for example http://127.0.0.1:8000>
   MODE = <dedicated | shared>
   PROFILE = <smoke | full>
   SCENARIO = <yes | no>
   MODELS_DIR = <where the instance keeps its models>
   OUTPUT_DIR = <folder for the runs and the reports, outside the checkout>
   DOWNLOADS_ALLOWED = <yes | no>
   PREVIOUS_RUN = <run folders of the previous audit of this machine, or empty>
   GPU_OWNER = <who decides when the GPU may be used>
4. Stop at each of the three stops of PROMPT.md and wait for my answer. Ask me
   for any parameter that is empty; do not guess.
5. Never show, write or log a credential. Never use the GPU, restart the
   instance or delete anything without my explicit consent. Never publish the
   report.
6. At the end, give me the verdict counts, what failed and why, what the
   comparison flags, the path of the report folder, and the list of what the
   audit left on the instance.
```

The report folder holds every file its page points to, so it can be sent as it is. To put several machines side by side, bring their run folders together and use `merge` (see Commands): the runs must be of the same pack.

Setup
-----

The project uses [uv](https://docs.astral.sh/uv/) with a uv-managed Python 3.13 and the committed `uv.lock`:

```bash
cd dev/audit
uv sync --locked
uv run --locked pytest
```

The `audit` job of the repository's CI does the same on Ubuntu and Windows with a pinned uv, then checks that the FFmpeg bundled with the PyAV wheel has `libx264`, or at least `mpeg4`, for the reduced copies of the report. It needs neither the core nor an instance: the tests use a fake API and generate their own outputs.

Copy `audit.example.toml` to `audit.toml` (ignored by git) and set the URL of the instance, its mode (`dedicated` for a test instance, `shared` for one in service), the output folder and a machine name. Relative paths are read from the folder of `audit.toml`. The file holds no credential: the account is read from the environment variables it names, `POTION_AUDIT_USER` and `POTION_AUDIT_PASSWORD` by default. `scripts/Invoke-WithEnvFile.ps1 -EnvFile <file> -UserKey <key> -PasswordKey <key> -- <command>` reads them from an env file, sets them for the command only and prints nothing.

The audit account must be an admin of the instance: the global queue, failure details, run reports and profiles are admin routes.

Commands
--------

| Command | What it does | GPU |
|---|---|---|
| `uv run --locked potion-audit check [--pack [<pack.toml>]]` | Logs in, then only reads: application and plugin versions, the `version` of each installed preset and its assignments, the hardware the API exposes, the disk space it reports, the global queue, and for each case whether its models are on the instance (`GET /api/models/hash/{sha256}`), with the size of the missing ones. With `--pack`, it adds the status of every cell of the pack (see Coverage). Writes `preflight.json` and `preflight.html`. Exits with 2 when something blocks a run (login, non-admin account, busy queue). | no |
| `uv run --locked potion-audit run --only <preset>:<mode> --dry-run` | Checks the queue, looks the models up and writes the request it would submit. Submits nothing. | no |
| `uv run --locked potion-audit run --only <preset>:<mode> --confirm-gpu` | Submits one case of the case file (the `fast` one of that mode when there is one), follows it, downloads the export bundle, reads the outputs and the statistics, and writes `result.json`. Refused without `--confirm-gpu`. Exits with 0 on PASS, 1 on FAIL, OOM or TIMEOUT, 2 when refused, 3 when stopped with Ctrl+C (the generation is cancelled). | yes |
| `uv run --locked potion-audit run --pack [<pack.toml>] --profile smoke\|full --dry-run [--beyond-tier] [--only <cell or preset>]` | Builds the request of every cell of the profile, in the order they would run, without submitting or uploading anything. A frozen input appears as `input:<id>`. Writes `plan.json` and one `request.json` per cell, and prints each cell with its status and estimated duration, then the total. | no |
| `uv run --locked potion-audit run --pack [<pack.toml>] --profile smoke\|full --confirm-gpu [--beyond-tier] [--only <cell or preset>]` | Runs the cells of the profile on the instance, in the order of the plan (see Runs), and writes `run.json` with one `request.json` and one `result.json` per cell. Refused without `--confirm-gpu`. Exits with 0 when every cell that ran passed, 1 on a FAIL, OOM, TIMEOUT or REJECTED cell or when the run stopped, 2 when refused, 3 when stopped with Ctrl+C (the running generation is cancelled). | yes |
| `uv run --locked potion-audit reevaluate <run>… [--pack <pack.toml>]` | Checks the outputs and the run report of every cell again with the current checks (see Re-evaluation). Writes `result.reevaluated.json` beside each `result.json`, which it never rewrites. | no |
| `uv run --locked potion-audit report <run>… [--out <dir>] [--compare <run>…] [--probe <file>] [--preflight <file>] [--note <text>]` | Writes `index.html` and `report.json` for one run, made of one or more segment folders or a night folder, and for a Video Producer scenario folder, alone or with the run (see Reports). `--compare` adds the comparison with an earlier run, or an earlier scenario, of the same pack. | no |
| `uv run --locked potion-audit merge <run>… --out <dir>` | One page with a column per machine, for runs of the same pack. The segments of one machine are put together; a scenario folder goes in the column of its machine. | no |
| `uv run --locked potion-audit pack verify [--pack <pack.toml>] [--allow-pending]` | Checks the pack against its case file and its input files (see Verification). Exits with 1 when it finds an error. | no |
| `uv run --locked potion-audit pack make-inputs --confirm-gpu [--only <input>]` | Makes the frozen inputs: the generations on the instance first, in the pack's order, then the transforms by code, and writes each input's sha256, size and origin into `pack.toml`. Refused without `--confirm-gpu`. `--transforms-only` redoes the transforms from inputs already made, without the instance and without `--confirm-gpu`. | yes |
| `uv run --locked --group cases potion-audit cases import --core <checkout> --ref <commit> --out cases/<file>.json` | Builds a case file from the `tests.yml` files, forms and recipes of a core checkout, read with `git show` at that commit. Needs PyYAML, in the `cases` group. | no |
| `uv run --locked potion-audit media probe <file> [--preview <out.mp4>]` | Decodes a video or an image with PyAV or Pillow: size, fps, duration, frame count, black check, and an optional reduced H.264 copy. | no |
| `uv run --locked potion-audit media encoders` | Lists the video encoders of the FFmpeg bundled with PyAV. | no |

`<preset>` is the preset folder name (`ZImage`, `Wan2.1-T2V-1.3B-8GB`) or its id. A preset whose mode is driven by a Video Director document gets a minimal one-shot `t2v` document built from the prompt.

Cases
-----

A case file holds the cases of the `tests.yml` files of the core and of its marketplace plugins at one commit of M4-S4/PotionUI, with the presets, their modes and the recipes found there. `cases/54c51e21d.json` is the one the pack and the default configuration use: 83 cases of 37 presets at `54c51e21d`, the fork's `dev` on core 0.2.0 with Video Producer 0.6.0. Two imports at that commit give the same file byte for byte. `cases/02cce6fdd.json` (78 cases of 35 presets, core 0.1.0) and `cases/d7ff033de.json` (lot 0) stay for the reports that cite them.

The import reads the preset folders directly under `content/presets/marketplace/` and under each plugin's `presets/`. The core also ships `content/presets/marketplace/FieldCatalog/all-fields`, one level deeper: that preset is not in the case file.

A case whose `tests.yml` gives an all-zero sha256 takes, in this order:

1. the sha256 of a recipe artifact of that preset: the one its form field recommends, or the only one whose id and file name hold the words of the field name, or the only one of the field's model type;
2. the first recommendation of the field that carries a sha256, read in the form of the case's own mode and in the preset files that form includes (`{{ paths.preset }}/…`). The other recommendations of that field are kept as `alternatives`, which `check` and `run` look up in order when the first one is not on the instance;
3. the file name of the first recommendation, when no recommendation has a sha256. The model stays unresolved in the case file; the pack resolves it on the instance by its exact file name (`GET /api/presets/{id}/models?search=…`).

When none fits, the model stays unresolved and `check` lists it apart, with the file name and size of the recipe or the recommendation when there is one. Sizes read from a recommendation's label (`13.31 GB`) are decimal and approximate.

The pack
--------

`pack/v1/pack.toml`, read with `tomllib`, is the potion pack `potion-v1`. Its runs compare only with runs of the same pack: the pack's sha256 and the case file's sha256 go into every plan and result. It holds:

- `[cases]`: the case file it builds on and its sha256;
- `[bible]`: the texts of the potion world, reused by the prompts: the bottle (a small round glass potion bottle, long neck, cork, glowing violet liquid, a cream label hand-lettered "PotionUI", on an old oak workbench), Lumi the witch, her workshop, the realistic cinema look and the lyrics of an original short song;
- `[prompts.<key>]`: one English prompt per kind of output, written with `{bible key}` fields; a prompt may also set form fields (`description` and `style` for the songs, `current_text` and `new_text` for the text edit);
- `[negatives]`: a negative prompt per model family, used where the case of origin has one;
- `[inputs.<id>]`: the frozen inputs (see below);
- `[[cells]]`: one cell per preset and mode, sometimes more (`variant`). A cell either takes a case of the case file (`case`), or corrects it (`case` and `fix`: what was wrong and how the cell fixes it), or defines a new case (no `case`, with `sources`: where each setting comes from), or excludes the preset or the mode (`exclude`, with `mode = "*"` for a whole preset). An excluded cell may name by its id a preset that the case file does not hold (`preset = "field-catalog-all-fields"`), and `pack verify` prints an `info` line for each such exclusion, so that a mistyped id shows; any other cell names a preset of the case file.

Version 1.1.0 of the pack builds on `cases/54c51e21d.json` and gives every mode of core 0.2.0 and of Video Producer 0.6.0 a cell or an exclusion, except the modes of the cloud presets, which have neither (`check --pack` lists them as `excluded`): it adds `txt2video`, `img2video`, `first_last` and `loop` of MiniMax-H3, `ingredients` of LTX-2.5, `extend` of MiniMax-H3-12GB and MiniMax-H3-Fast-12GB, the `video` mode of Wan2.2-14B-Lightning-I2V-12GB and the `txt2img` and `edit` modes of MiniMax-H3-Image (24 GB, so `beyond_tier` on a 12 GB GPU). The `long` mode of MiniMax-H3, which core 0.2.0 removed in favour of its Video Director `video` mode, has no cell any more, and the Frontend Field Catalog, an inert development preset, is excluded. It also adds `flex` variants of the `video` and `refs` modes of MiniMax-H3 and a `quality` variant of MiniMax-H3-VDN, which runs without the dense time embedder its turbo cells need. The cells that set their own values were read again against the 0.2.0 forms. 1.1.0 has the same keys as 1.0.0, and this version of the tool reads both; the tool from before 1.1.0 does not read 1.1.0, since it refuses the exclusion of a preset that the case file does not hold; as with any change of the pack, a report on a 1.0.0 run lists the cells that run left out only when given the 1.0.0 pack with `--pack`.

A cell may set:

| Key | Meaning |
|---|---|
| `prompt`, `negative` | Keys of `[prompts]` and `[negatives]` |
| `seed` | Replaces the pack's `seed` (12345), which replaces the case's seed |
| `form`, `drop` | Settings that replace those of the case, and case settings to remove |
| `models`, `drop_models`, `models_from` | Model fields by sha256 (`"<sha256>"` or `{sha256 = …, alternatives = […]}`) or by file name (`{filename = …}`), fields to remove, and a case of the same preset whose models the cell copies |
| `bind` | Form fields bound to frozen inputs: `field = "<input>"` places the upload: a top-level field gets the upload's path, as the browser form sends it, and an item of a list or of a Video Director document gets the media item the upload gives; `"<input>:path"` places the upload's path alone (inpaint masks); a path may reach into lists and documents (`"references[0]"`, `"video_director.media[1].media"`) |
| `profiles`, `repeat_warm` | `smoke`, `full` or both; `repeat_warm` runs the cell a second time, warm, in `full` |
| `requires_plugin` | The cell counts only when that plugin is enabled |
| `checks`, `sources`, `notes` | Output checks (the case's own by default), where the settings come from, free notes. A cell in an `img2img`, `edit` or `inpaint` mode also forbids the `TXT2IMG` step, and a cell bound to an `input_video` or `source_video` forbids `TXT2VID` |

Nothing that depends on the server goes into the pack: model ids are looked up by sha256 or file name at run time, and an input becomes a server path only once it is uploaded.

Profiles: `smoke` has one cell per preset, on its main mode, the first generation mode of the preset (`txt2img`, `video`, `song`, `img2mesh`, `upscale` for the video utilities, `prepare` for the image tools); `full` has every cell, plus a warm repeat of the main cell of each video preset. Excluded cells belong to no profile. A preset whose `min_vram_gb` is above the GPU is planned only with `--beyond-tier`.

Run order: the cells of one preset run one after the other, so its models stay loaded, in the order of the pack; a warm repeat follows its cell. The estimated duration of a cell is the preset's average from `/api/stats/presets/timing`: the cold average for the first cell of a preset, the warm average for the next ones. The API gives these averages per preset, all modes mixed.

Frozen inputs
-------------

The inputs live in `pack/v1/inputs/` and are versioned with the pack, a few MB in all. Each `[inputs.<id>]` gives its file, kind (`image`, `video`, `audio`), size in pixels or seconds, sha256, size in bytes, origin, licence and how it is made (`[inputs.<id>.make]`):

- `method = "generate"`: a request built like a cell (preset, mode, case, prompt, seed, settings, bindings to earlier inputs), submitted to the instance, then its output finished by code: a picture is checked against the expected size and saved as JPEG, at quality 92 unless `output.quality` says otherwise and without chroma subsampling; a video is cut to the expected seconds and encoded again with `libx264`, without sound;
- `method = "transform"`: code only, from an earlier input: `rect_mask` (a white rectangle on black, in fractions of the source picture), `edges` (a black and white edge map), both saved as PNG, and `desaturate_video`.

Only models under a permissive licence make the inputs; each input names the licence and where it was read. A mode whose input no such model can make is excluded: the `talk` mode of MiniMax-H3 needs a voice recording, and no local preset under a permissive licence produces speech. `pack make-inputs` writes the sha256, the size in bytes and the origin (preset, mode, generation id, application version, date, or the transform and the sha256 of its source) back into `pack.toml`. Uploads go through `POST /api/media/upload`, once per sha256 and per run (`uploads.json` in the run folder). Each generation's idempotency key holds the run id and the input id. A generated input whose file is already there with the sha256 of the pack is skipped, unless `--only` names it; the transforms are always made again, by code.

Verification
------------

`pack verify` reports, and exits with 1 on any error:

- an input whose file is missing, whose size or sha256 differ from the pack, or that is not made yet (a `pending` line instead with `--allow-pending`);
- an unknown prompt, negative prompt, bible field, input or case, a case of another mode, a binding to an input that is not defined, or a model that is not a sha256;
- a PLACEHOLDER value of a case that no binding replaces;
- a case with a negative prompt whose cell names none;
- a preset mode of the case file with no cell, a cell defined twice, more than one smoke cell for a preset, a cell in no profile, an unknown key;
- a case file whose sha256 is not the one the pack records.

Coverage
--------

`check --pack` gives each cell one status: `ready`, `input_pending` (an input is not made yet), `beyond_tier`, `model_missing` (a model is not on the instance, alternatives included), `model_unresolved` (no sha256 and no file name to look up), `preset_not_installed`, `mode_missing` (the installed preset no longer offers the cell's mode; the reason names the mode that replaced it when the preset says so in `retired_modes`), `plugin_inactive`, or `excluded`. `run --pack --dry-run` gives the same statuses and builds a request only for the cells that can run: `ready`, `input_pending`, and `beyond_tier` with `--beyond-tier`. Preset modes of the instance that the pack does not cover are listed as `no_case`, and cloud presets as `excluded`.

`check --pack` also reads, once per preset and mode, the form of the mode of each cell whose status is `ready`, `input_pending`, `beyond_tier`, `model_missing` or `model_unresolved` (`GET /api/presets/{id}/form?mode=…`; excluded cells and those of a preset not installed, a missing mode or an inactive plugin are not read), and lists, as a warning and in `undeclared_fields`, the fields the cell would send that the form does not declare. The server strips such a field, or, for a model reference, passes it on to a pipeline that does not read it. Not counted: `video_director`, `music_director`, `llm`, `prompt_timeline` and `timeline`, which the server passes through, `regional_prompt` when the preset offers it in that mode (`vars.regional_prompt.modes`), `<field>_inpaint_mask` beside a declared image, video, audio, media or file field, and `<field>__origin` beside a declared field. A form that cannot be read (an instance that does not answer or times out, an answer that is not an object or has no `form_schema`) is recorded in `form_error`, and `check` still writes its preflight; a cell whose models the pack cannot list is not read. The status of the cell does not change.

Runs
----

`run --pack --profile <profile> --confirm-gpu` takes the cells of the profile in the order of the plan. Before the first cell, the instance must answer `/health` with `healthy` and its global queue must be empty, or the run is refused. Then, for each cell:

- a cell that is not `ready`, or `beyond_tier` with `--beyond-tier`, is listed with its status and is not run;
- `/health` and the queue are checked again; when the instance is not healthy or the queue is busy, the run stops and the cells left are `not_run`;
- the frozen inputs the cell binds are uploaded, once per sha256 and per run;
- the request is submitted and followed, its export bundle is read and checked as with `run --only`, and the result goes to `cells/<cell>/result.json`; a warm repeat has its own folder and its own idempotency key;
- the run report is checked too: a generation that processed media files and loaded fewer of them fails `media_loaded`, and a generation that took a forbidden step fails `generation_step`; the server would otherwise fall back to text-to-image or text-to-video without a word. A `TXT2VID` step that comes after `Encoding source video` is allowed: the latent upscalers encode the source, upscale its latent, then refine it with the text-to-video generator, which reports `TXT2VID`;
- a FAIL, a TIMEOUT or a request the server refuses (REJECTED) is recorded and the run goes on. After a TIMEOUT the run asks the server to cancel the generation, then polls its status until it is completed, failed or cancelled, for at most 300 seconds, before the next cell checks the queue; `result.json` records the wait in `cancel`; an OOM stops the run, since the instance then needs a restart, which is the operator's call.

Each output is kept once, as the file taken out of the export bundle; the bundle itself is deleted unless `run` gets `--keep-bundle`. `instance.json` holds what the API says about the hardware and the plugins when the run starts. When `audit.toml` sets `[probe] source = "file"`, that probe file is copied into the run folder as `host-probe.json`.

`run.json` holds the sha256 of the pack and of its case file, the application version, the machine, the mode (`dedicated` or `shared`), every cell with its status, verdict, generation id, measured and estimated seconds and peak VRAM, the reason the run stopped if it did, and the totals.

Statistics of a run
-------------------

The core writes one row per completed generation into its `generation_stats` table: duration, cold or warm start, model load time, peak VRAM, RAM at the end and CPU. The API serves no row on its own, only aggregates per preset: `/api/stats/presets/timing` (counts and averages of times) and `/api/stats/presets/resources` (`total_runs`, the maximum and the average of `peak_vram_mb`, the maximum and the average of `peak_ram_mb`, the average CPU). The audit reads them for the preset before the order and again once the generation is done, and recovers the run's own values from the averages: when the count grew by exactly one, `average after × count after − average before × count before` is the new row.

The peak VRAM the core records is the high-water mark of the PyTorch allocator during the generation: `reset_peak_memory_stats()` when the generation starts, `max_memory_allocated()` when it ends, summed over the CUDA devices. It counts every tensor allocated in that window, the models the generation loads and whatever the model cache still holds on the card from earlier generations while it is there, and it varies with what the generation keeps resident or streams. Two presets that share their heaviest stage (the same text encoder, the same decoder) can record the same peak to the tenth of a MiB. `Peak VRAM (whole device, sampled)` in the report is another measure: the memory of the whole card, polled.

The core averages skip a row with no peak while its count includes it, so a preset that holds such rows would give a wrong difference. The derived peak is therefore checked against the preset's maximum, and `generation_stats` says where it comes from in `peak_vram_source` (`end_ram_source` for the RAM):

- the preset had no peak before: the run's peak is the maximum after;
- the maximum rose: the run's peak is the new maximum, if the averages give the same value within 1 MiB; otherwise the peak is not derivable;
- the maximum did not move: the difference of the averages, if it lies between 0 and the maximum; otherwise the peak is not derivable;
- no resource average moved at all (VRAM, RAM and CPU): the core recorded no resources for the run, and the peak, the RAM and the CPU are not derivable, rather than being given the average.

A peak that is not derivable is `null`, and the report prints `not derivable` with the reason. A run with no peak whose resource averages still moved (the VRAM missing alone) cannot be told apart from a run whose peak equals the average, and is taken as such. `generation_stats.preset_stats` keeps the aggregates read before and after the run, so `reevaluate` can derive the values again.

Re-evaluation
-------------

Checks change between versions of potion-audit; `CHECKS_VERSION` in `run.py` counts them, and every `result.json` records the version it was checked with (a result without one was checked with version 1). `reevaluate` takes each cell of a run that completed, reads its output files again with PyAV and Pillow, reads its `run_report.json`, and applies the checks of the pack's cell with the current code. It writes `result.reevaluated.json` with the new verdict and checks, the previous verdict and checks version, and whether the pack is the one the run used. It also derives the statistics of the run again from `generation_stats.preset_stats` with the current rules (see Statistics of a run), and records the previous peak beside the new one; the report then shows the new values. A run made before potion-audit kept these aggregates has only the derived values: its statistics are kept as they are, and `generation_stats.kept` says so. A cell that did not complete (OOM, TIMEOUT, a failed generation) keeps its verdict. Nothing is sent to the instance.

Reports
-------

`report <run>…` reads the run folders given, the segments of one run in their order: they must come from one machine and one pack. A cell that appears in several segments takes its last entry that ran. The page, `index.html`, is in English, holds its CSS and its few lines of script inline, loads nothing from the network and reads at phone width without scrolling the page sideways. It looks like a page of PotionUI: its colours, status colours, borders, radii, type scale and fonts are copied from the application's "Instrument" tokens (`frontend/src/lib/styles/tokens.css` and `frontend/tailwind.config.js` of the core), under the report's own variable names. It follows the light or dark theme of the browser; a button in the bar switches between system, dark and light and remembers the choice in the browser. The sans-serif face is the application's system stack; the monospace stack names IBM Plex Mono first, which the page uses when it is installed, and falls back to the system monospace faces, since the page embeds no font file. Under the title, the machine, pack, profile, period, runs and scenario are given as labelled pairs. A bar under them links the sections, marks the one being read (an `IntersectionObserver`, no scroll listener) and stays at the top while the page scrolls; a button goes back to the top. Every text colour, verdict badges included, keeps a WCAG AA contrast of at least 4.5 to 1 in both themes: the light theme tints status backgrounds more lightly than the application, and a badge on a tinted card sits on the plain card colour. It shows:

- the summary: one sentence with the outcome, then a tile each for the matrix (cells passed out of those run, the other verdicts, the cells not run by status), the scenario (steps passed out of those offered), the duration (from the first start to the last end, and the run time measured; when segments are more than ten minutes apart, the run time measured comes first, then the time the series was active, the span end to end and the pause between segments), the restarts (from the `night.json` that lists the segments, when there is one) and, with `--compare`, what changed against the earlier run: the cells and steps fixed (a failure then, PASS now), regressed (PASS then, a failure now), no longer run and run for the first time, and how many cells the comparison flags;
- the machine card: GPU, driver, RAM, host OS, application, plugins, pack and case file, runner, mode and profile, then the bias factors (a shared instance, a segment that stopped, a Windows session that was locked or remote at probe time, compute processes on the GPU, notes given with `--note`). The hardware comes from `instance.json`, or from `--preflight` for older runs; the driver and the OS come from a probe. The OS is named from the build number and the edition id, never from the caption Windows translates (see Probes);
- Storage, from the probe files of the run folder (`*probe*.json`) or `--probe`, otherwise "not probed": the container mounts, then only the host storage the instance uses. A volume is listed when it holds a container mount (its `findmnt` source or `drvfs` path names a drive), a virtual disk of Docker Desktop or of a WSL distribution, or a storage path the API declares; a physical disk is listed when it holds one of these volumes. One line says how many disks and volumes of the host are left out. A virtual disk that Docker Desktop and a WSL distribution share is listed once, with both. When the container probe recorded no mount, the page says so, gives the probe's notes and says that a volume holding only a mounted folder cannot be recognised. The space the API reports is always shown;
- the matrix: one row per preset, one card per mode. A card gives its verdict, the run time, the peak VRAM derived from the preset statistics and a thumbnail; a cell that did not run gives its status and its reason (`model_unresolved`, `model_missing`, `beyond_tier`, `not_run`, and, when `--pack` is the pack of the run, `excluded` and `not_in_run` for cells of the profile the run left out);
- the cells, grouped by preset, each group headed by the count of its verdicts. The folded line of a cell gives its verdict, its run time and its peak VRAM, or why it did not run. Opened, it shows the media (a reduced H.264 copy of a video, a reduced WebP copy of a picture, a copy of the original for sound and meshes), the run time, the model load and the compute time apart, the time per step, the peak VRAM and RAM, the checks, the failure, the pipe times, the prompt, the settings and seed, and the start of the run report. A re-evaluated cell shows its new verdict, with the old one struck through.

A verdict is always written out, never shown by its colour alone. Numbers in tables are right-aligned in tabular figures; durations are in seconds, peak VRAM in GiB in the matrix and the folded lines and in MiB in the details.

The run folders given to `report` may be segment folders (with `run.json`), the folder of a night (with `night.json`, whose segments are read from the sibling folders) and one scenario folder (with `scenario.json`). The report holds the matrix alone, the scenario alone, or both when the matrix and the scenario come from the same machine and the same application version; otherwise it refuses and points to `merge`. The folder of a dry run (`plan.json` only) is refused.

With a scenario, the page adds a section "Video Producer scenario":

- the run, machine, application and plugin versions, pack and case file, settings, the state of the final pass, the matrix files the scenario read, and the reason it stopped if it did;
- a table with one row per engine and one column per step: shot 1, shot 2 chained, shot 3 Ref2VA, shot 4 first and last, the final pass and the export. A cell gives the verdict, the time (the run seconds of the generation, the polled seconds of the export), the peak VRAM when the preset statistics derived it, the preset the take ran on when it is not the one the audit ordered (`on Wan 2.2 14B Lightning I2V (12 GB)`), and a thumbnail. A step the engine does not offer (no `refs` mode, so no Ref2VA profile; no last image, so no shot 4) is `not offered`, drawn dashed, apart from the failures; a step that did not run is `not run` with its reason; an engine left out of the run is `left out`. The shot checks (`chain_frame`, `chain_start`, `chain_mode`, `chain_warning`, `flf_start`, `image_preset`) are printed in the cell with their recorded `actual` value, green when they passed and red when they failed, and a check the engine does not offer is printed grey with `not offered`;
- the measures: the seam of shots 1 and 2 by code (mean absolute difference and PSNR), the seam scores of the plugin, and the identity and card scores of shot 3 against the Lumi card;
- one section per step, grouped by engine: the video (a player on a reduced H.264 copy made with PyAV), the take and generation ids, the profile and director mode, the preset whose statistics were read and where that preset came from, the times, the steps the generation status reported, the peak VRAM, the failure or the plugin's refusal, the checks not offered with their reason, and every check with its expected and actual values as recorded.

`scenario.json` written on Windows holds paths with backslashes; the report reads them on any system.

The report folder holds everything its page points to, so it can be zipped and sent to someone else: thumbnails and reduced copies go to `<out>/media/` (`<out>/media/vp/` for the scenario, `<out>/media/previous/` for the earlier side of a compared pair). A picture or video is shown by its reduced copy, and its original stays in the run folder: the page names it and the run folder it is in, without a link. An output with no reduced copy (sound, a mesh) is copied into `media/` when it weighs at most 64 MiB, and the page plays or links that copy. The page never links a file outside its folder and never prints the path of the Python that ran the audit. Paths under a user profile are written `<home>`.

`--note` adds a bias factor to the machine card. Write it in English, like the rest of the page, and name no one: say "the machine was in use", not who used it. The page is meant to be shared.

`--compare <run>…` reads an earlier run of the same pack (the same id and sha256, or the command refuses) and lists, cell by cell, a changed verdict, a run time more than 20 % away, a peak VRAM more than 512 MiB away, and the SSIM of the first output when both cells used the same seed and gave a picture or video of the same size (five frames spread over a video), then the changes of disks and mounts when both runs have probe files. Each cell whose SSIM is under 0.9 gets its two outputs side by side, the earlier one first; they stack on a narrow screen. A scenario folder given to `--compare` is compared with the scenario of the report, when both ran the same pack: step by step, a changed verdict, a time more than 20 % away, a peak VRAM more than 512 MiB away and a take whose statistics were read on another preset (the chained shot of Wan2.2-14B-Lightning-12GB on its I2V companion, for instance, where its times and VRAM are not comparable), then the settings, machine, application or plugin that changed.

`merge` takes run folders, night folders and scenario folders of several machines, at most one scenario per machine. Under the matrix, a table "Video Producer scenario" has one row per engine and step and one column per machine, each cell drawn as in the report (verdict, time, VRAM, the preset of the take when it is another, the shot checks); a machine with a scenario and no matrix run gets its column too.

Probes
------

`probe/probe-windows.ps1 [-Out <file>]` lists, for Windows PowerShell 5.1 or PowerShell 7 without admin rights: physical disks (model, bus, media, size, firmware, health; never a serial number), partitions, volumes with free space and the numbers of the disks they sit on (`disk_numbers`), the WSL distributions and Docker Desktop disks with the VHDX file facts, `.wslconfig`, the GPU and its compute processes, and the state of the Windows session. Paths under the user profile are written as `<home>`. The OS is recorded the same way whatever the language of Windows: `name` (`Windows 11 Pro`) is built from the build number and the `EditionID` of the registry, beside `edition_id`, `display_version`, `version` and `build`; the translated caption is not recorded. A step that fails adds a note with its error category and id, which do not depend on the language either. The report reads older probes too: it names their OS from the build alone, and links their volumes to disks through `partitions`.

`probe/probe-linux.sh [--read-test <file> --confirm-idle [--max-bytes <n>]] <path>...` is POSIX `sh` for a Linux host or a container: `df`, the file system type and `findmnt` for each path, `lsblk`, and, only with `--confirm-idle`, a sequential read of at most 4 GiB of a real file with `dd iflag=direct`. It refuses the read when `nvidia-smi` lists a compute process; checking that the instance's global queue is empty is the caller's job. To run it in a container:

```bash
docker exec -i <container> sh -s -- --read-test <models>/<file> --confirm-idle <models> <storage> < probe/probe-linux.sh
```

From Git Bash on Windows, prefix the command with `MSYS_NO_PATHCONV=1`: otherwise Git Bash rewrites `/work/models` into `C:/Program Files/Git/work/models` before `docker exec` passes it on, the paths do not exist in the container and the probe records no mount. The probe then says so in its notes.

Video Producer scenario
-----------------------

The matrix measures each preset on its own. The scenario measures what only the Video Producer plugin does, through its routes (`/api/plugins/video-producer/…`): the project document, the chaining of a shot on the last image of the previous one (`firstFromPrevious`), Ref2VA with references, a shot between a first and a last image (`flf`), the final pass and the export.

| Command | What it does | GPU |
|---|---|---|
| `uv run --locked potion-audit vp run --matrix <run> --dry-run` | Picks the engines, builds each project document and the list of its generations in memory, with their estimated durations and, for each take, the checks it will run and those the engine does not offer, and writes `plan.json` and `projects/<engine>.json`. Only reads on the instance (health, global queue, plugin, preset timings). | no |
| `uv run --locked potion-audit vp run --matrix <run> --confirm-gpu` | Runs the scenario (see below) and writes `scenario.json`. Refused without `--confirm-gpu`. Exits with 0 when every step that ran passed, 1 otherwise or when the run stopped, 2 when refused, 3 when stopped with Ctrl+C (the running take is cancelled). | yes |
| `uv run --locked potion-audit vp cleanup <run folder> [--confirm]` | Lists the projects, the generations and the uploads of a scenario run: the projects recorded in `scenario.json` and those whose name starts with `potion-audit <run id> `, the generations of their takes, and the files the run uploaded, recorded in `uploads.json`. With `--confirm`, deletes the projects (with their takes, versions and exports), then the generations, then the uploads (`DELETE /api/media/uploads/{filename}`, after `GET …/{filename}/info` says the file is still there), and writes `cleanup.json`. | no |

Options of `vp run`: `--matrix` (repeatable) takes a `run.json` or `results.json` of a matrix, a run folder, or the folder of a night with `night.json`, whose segments are read from the sibling folders; `--engines a,b` names presets of the plugin; `--quality draft|final` (draft by default), `--upscaler seedvr2|rtx` (SeedVR2 by default), `--target` of the final pass (`fhd1080` by default), `--companion-steps N` (the steps of the image-to-video companion an engine hands its image shots to, written in the project's engine options for that companion: `{"speed_profile": "custom", "steps": N, "cfg": 1.0}`, since the custom profile otherwise takes the CFG of the form, 5, which burns a distilled LoRA's frames; only Wan2.2-14B-Lightning-12GB has one), `--timeout` per take, `--interval`, `--run-id` (default `<date>-<machine>-vp`).

Engines: the five presets of the plugin, Wan2.1-T2V-1.3B-8GB, Wan2.2-TI2V-5B-8GB, Wan2.2-14B-Lightning-12GB, MiniMax-H3-12GB and MiniMax-H3-Fast-12GB. With `--matrix`, an engine plays only when every run of its `video` cell passed; with `--engines` too, only the named ones among those. An engine offers Ref2VA when its preset has a `refs` mode and, with a matrix, its `refs` cell passed: only MiniMax-H3-12GB today. Wan2.2-14B-Lightning-12GB hands its image shots (the chained shot and the first and last image shot) to Wan2.2-14B-Lightning-I2V-12GB, a companion that Video Producer 0.6.0 does not list as an engine (`listed: false`); with a matrix, those shots play only when the companion's `video` cell passed too, otherwise they are `skipped` with the reason, and the plan estimates them on the companion's cell and timings. The final pass runs only when the upscaler's cell passed the matrix (`core/SeedVR2:video_upscale` or `plugin:nvidia-rtx-upscale/RTX-Upscale:video_upscale`); otherwise it is `not_run` with the reason, and the export goes on without it.

One project per engine, named `potion-audit <run id> <engine>`, its synopsis and a marker holding the run id. Four shots of 5 s at 24 fps, written from the bible of the pack:

1. `s1-workshop`: a wide shot of the workshop, text-to-video;
2. `s2-bottle`: a close-up of the bottle, chained on shot 1 (`firstFromPrevious`);
3. `s3-lumi`: Lumi lifting the bottle, in Ref2VA, cast with the Lumi card, whose reference is the frozen input `lumi`, and with `bottle` as a global reference. It has no spoken line: `talk` is excluded for want of a voice under a permissive licence. An engine without Ref2VA skips it (`skipped`).
4. `s4-gold`: the violet potion turning to gold, between a first and a last image: the frozen inputs `bottle` and `bottle-gold`, checked against their sha256 in the pack and uploaded like the references, placed as the shot's `first` and `last` frames. An engine whose model takes no last image does not offer it (`skipped`): Wan2.1-T2V-1.3B-8GB, a text-to-video model, and Wan2.2-TI2V-5B-8GB, whose model knows only a first image.

What each engine is expected to do with its image shots:

| Engine | Shot 2, chained | Shot 4, first and last |
|---|---|---|
| Wan2.1-T2V-1.3B-8GB | text to video: the plugin starts it from its text and warns `chain_text_only`; `chain_frame` and `chain_start` are not offered, `chain_mode` (`t2v`) and `chain_warning` are checked | not offered |
| Wan2.2-TI2V-5B-8GB | from the last image of shot 1 (`chain_frame`, `chain_start`), once the plugin passes it images through the core's TI2V image input | not offered |
| Wan2.2-14B-Lightning-12GB | from the last image of shot 1, on its I2V companion Wan2.2-14B-Lightning-I2V-12GB (`image_preset`) | `flf` on the companion (`flf_start`, `image_preset`) |
| MiniMax-H3-12GB, MiniMax-H3-Fast-12GB | from the last image of shot 1 | `flf` (`flf_start`) |

Steps, one generation at a time, each after a check that the global queue is empty:

- the two references and the two frames of shot 4 are uploaded (three files, `bottle` serving both as a reference and as a frame: `POST /api/media/upload`, then `POST …/media/uploaded` for their library origin) and the project is created (`POST …/projects`);
- each shot is estimated (`POST …/projects/{id}/estimate`, the same order: its warnings and blocks are kept in the take's `result.json`), then ordered alone (`POST …/projects/{id}/generate`, one variant), followed by `GET …/projects/{id}/takes` and the status of its generation, and placed on its clip once done (`PUT …/projects/{id}`). Shot 2 is ordered once shot 1's take is placed, so the plugin takes the last image of that take;
- the final pass of shot 1's take (`POST …/projects/{id}/final-pass`, method `upscale`), placed on clip 1 once done;
- the export (`POST …/projects/{id}/exports/video`, format `web`), followed by `GET …/exports/{job}` and downloaded from `…/exports/{job}/file`;
- the looks the plugin measures (`POST …/projects/{id}/looks`, then `GET` until nothing is queued): its seam scores and the identity and card scores of shot 3's take against the Lumi card.

A take refused by the plugin is `BLOCKED` with its answer; a failed one is `FAIL`, `TIMEOUT` or `OOM`. An OOM stops the scenario, as in the matrix: the steps and engines left are `not_run`.

Checks of a take: an output that is not black, the profile it ran with, `media_loaded` and `generation_step` from the run report (a take whose director mode starts from an image, `i2v` or `flf`, forbids `TXT2VID`); for shot 2 also `chain_frame` (the take started from shot 1's last image) and `chain_start` (its director mode starts from an image), or, on a text-to-video engine, `chain_mode` (`t2v`) and `chain_warning` (`chain_text_only` among the warnings of the estimate) with `chain_frame` and `chain_start` recorded as `not_offered`, which is not a failure; for shot 4 `flf_start` (its director mode is `flf`); and for the image shots of an engine with a companion, `image_preset` (the take's `preset_id` is the companion). Checks of the export: a duration of 20 s within 0.1 s, 24 fps, 480 frames within one, not black.

Statistics of a take: the per-preset averages of `/api/stats/presets/timing` and `/resources` are read for every preset before the order, then, once the take is done, for the preset the generation actually ran on: the `preset_id` of the generation record (`GET /api/generations/history/{id}`), which is the preset the core counts the run under, else the take's `preset_id`, else the preset the audit ordered. `result.json` records it in `stats_preset` (the preset, its name from the statistics, where it came from, the record's and the take's values, and whether it differs from the ordered one), and the step in `scenario.json` keeps the preset, its name and `differs`. Without this, a shot handed to a companion would wait for statistics of the ordered preset that never move, and derive nothing. The values are then derived and checked as for a matrix cell (see Statistics of a run), each take on its own preset: a shot whose take ran on the companion gets the row of that generation, not the peak of the shot before. `reevaluate` reads matrix runs only. The seam of shots 1 and 2 is also measured by code: the mean absolute difference and the PSNR between the last frame of shot 1's take and the first frame of shot 2's.

Output, in `<output_dir>/<run id>/`:

- `plan.json` for a dry run, `scenario.json` for a run: `kind = "vp-scenario"`, the run id, the application, plugin, pack and case file versions, the matrix files read, the settings, the state of the final pass, the reason the run stopped if it did, the totals (`summary`), and one entry per engine with whether it was selected and why, Ref2VA and why not, what it is expected to do with its image shots (`chain`, `flf` and why not, `image_preset`), its project, its steps (status, verdict, take and generation ids, director mode, the preset of the take and the preset its statistics were read on, run seconds, seconds per step, peak VRAM, the path of its `result.json` and of its video) and its measures (`seam`, `looks`);
- `projects/<engine>.json`: the document the project was created from, and `looks.json` there for a run;
- `takes/<engine>--<shot>/` and `final/<engine>/`: `result.json` in the format of a matrix cell (`cell` is `vp:<engine>:<shot>` or `vp:<engine>:final-pass`; the plugin's take, samples, final status, derived statistics, timing, memory, outputs, checks, verdict), plus `run_report.json`, `bundle.zip` and the extracted outputs;
- `exports/<engine>/`: `result.json` (the export job, the probe of the file, its checks and verdict) and `export.mp4`;
- `uploads.json`, and `cleanup.json` after `vp cleanup --confirm`.

An upload is the library item the project's references and frames point to: once the projects are gone, `vp cleanup --confirm` deletes the three files the run uploaded, and only those. `cleanup.json` records for each one whether it existed, was deleted, and still exists after.
