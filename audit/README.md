Potion audit
============

An external API client that audits the presets PotionUI ships by default. It runs on a workstation, connects to the instance to test by its URL and never starts an instance itself. Results are written to an output folder outside this repository and are never committed.

Lot 0 brought the skeleton, a read-only `check`, a minimal `run --only` for single cases, the disk probes and the PyAV helpers. Lot 1 adds the potion pack: the prompts, the frozen inputs and one cell per preset and mode, with `pack verify`, `pack make-inputs`, `check --pack` and `run --pack --profile <profile> --dry-run`. Lot 2 runs the cells of a profile on the instance with `run --pack --profile <profile> --confirm-gpu`. The report and the Video Producer scenario come later.

Setup
-----

The project uses [uv](https://docs.astral.sh/uv/) with a uv-managed Python 3.13 and the committed `uv.lock`:

```bash
cd audit
uv sync --locked
uv run --locked pytest
```

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
| `uv run --locked potion-audit pack verify [--pack <pack.toml>] [--allow-pending]` | Checks the pack against its case file and its input files (see Verification). Exits with 1 when it finds an error. | no |
| `uv run --locked potion-audit pack make-inputs --confirm-gpu [--only <input>]` | Makes the frozen inputs: the generations on the instance first, in the pack's order, then the transforms by code, and writes each input's sha256, size and origin into `pack.toml`. Refused without `--confirm-gpu`. `--transforms-only` redoes the transforms from inputs already made, without the instance and without `--confirm-gpu`. | yes |
| `uv run --locked --group cases potion-audit cases import --core <checkout> --ref <commit> --out cases/<file>.json` | Builds a case file from the `tests.yml` files, forms and recipes of a core checkout, read with `git show` at that commit. Needs PyYAML, in the `cases` group. | no |
| `uv run --locked potion-audit media probe <file> [--preview <out.mp4>]` | Decodes a video or an image with PyAV or Pillow: size, fps, duration, frame count, black check, and an optional reduced H.264 copy. | no |
| `uv run --locked potion-audit media encoders` | Lists the video encoders of the FFmpeg bundled with PyAV. | no |

`<preset>` is the preset folder name (`ZImage`, `Wan2.1-T2V-1.3B-8GB`) or its id. A preset whose mode is driven by a Video Director document gets a minimal one-shot `t2v` document built from the prompt.

Cases
-----

A case file holds the cases of the `tests.yml` files of the core and of its marketplace plugins at one commit of M4-S4/PotionUI, with the presets, their modes and the recipes found there. `cases/02cce6fdd.json` is the one the pack and the default configuration use: 78 cases of 35 presets at `02cce6fdd`, the fork's `dev` on release 0.1.0. `cases/d7ff033de.json` is the lot 0 file, kept for comparison.

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
- `[[cells]]`: one cell per preset and mode, sometimes more (`variant`). A cell either takes a case of the case file (`case`), or corrects it (`case` and `fix`: what was wrong and how the cell fixes it), or defines a new case (no `case`, with `sources`: where each setting comes from), or excludes the preset or the mode (`exclude`, with `mode = "*"` for a whole preset).

A cell may set:

| Key | Meaning |
|---|---|
| `prompt`, `negative` | Keys of `[prompts]` and `[negatives]` |
| `seed` | Replaces the pack's `seed` (12345), which replaces the case's seed |
| `form`, `drop` | Settings that replace those of the case, and case settings to remove |
| `models`, `drop_models`, `models_from` | Model fields by sha256 (`"<sha256>"` or `{sha256 = …, alternatives = […]}`) or by file name (`{filename = …}`), fields to remove, and a case of the same preset whose models the cell copies |
| `bind` | Form fields bound to frozen inputs: `field = "<input>"` places the media item the upload gives, as the browser's media loader does; `"<input>:path"` places the upload's path alone (inpaint masks); a path may reach into lists and documents (`"references[0]"`, `"video_director.media[1].media"`) |
| `profiles`, `repeat_warm` | `smoke`, `full` or both; `repeat_warm` runs the cell a second time, warm, in `full` |
| `requires_plugin` | The cell counts only when that plugin is enabled |
| `checks`, `sources`, `notes` | Output checks (the case's own by default), where the settings come from, free notes |

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

`check --pack` gives each cell one status: `ready`, `input_pending` (an input is not made yet), `beyond_tier`, `model_missing` (a model is not on the instance, alternatives included), `model_unresolved` (no sha256 and no file name to look up), `preset_not_installed`, `plugin_inactive`, or `excluded`. Preset modes of the instance that the pack does not cover are listed as `no_case`, and cloud presets as `excluded`.

Runs
----

`run --pack --profile <profile> --confirm-gpu` takes the cells of the profile in the order of the plan. Before the first cell, the instance must answer `/health` with `healthy` and its global queue must be empty, or the run is refused. Then, for each cell:

- a cell that is not `ready`, or `beyond_tier` with `--beyond-tier`, is listed with its status and is not run;
- `/health` and the queue are checked again; when the instance is not healthy or the queue is busy, the run stops and the cells left are `not_run`;
- the frozen inputs the cell binds are uploaded, once per sha256 and per run;
- the request is submitted and followed, its export bundle is read and checked as with `run --only`, and the result goes to `cells/<cell>/result.json`; a warm repeat has its own folder and its own idempotency key;
- a FAIL, a TIMEOUT or a request the server refuses (REJECTED) is recorded and the run goes on; an OOM stops the run, since the instance then needs a restart, which is the operator's call.

`run.json` holds the sha256 of the pack and of its case file, the application version and the machine, every cell with its status, verdict, generation id, measured and estimated seconds and peak VRAM, the reason the run stopped if it did, and the totals.

Probes
------

`probe/probe-windows.ps1 [-Out <file>]` lists, for Windows PowerShell 5.1 or PowerShell 7 without admin rights: physical disks (model, bus, media, size, firmware, health; never a serial number), partitions, volumes with free space, the WSL distributions and Docker Desktop disks with the VHDX file facts, `.wslconfig`, the GPU and its compute processes, and the state of the Windows session. Paths under the user profile are written as `<home>`.

`probe/probe-linux.sh [--read-test <file> --confirm-idle [--max-bytes <n>]] <path>...` is POSIX `sh` for a Linux host or a container: `df`, the file system type and `findmnt` for each path, `lsblk`, and, only with `--confirm-idle`, a sequential read of at most 4 GiB of a real file with `dd iflag=direct`. It refuses the read when `nvidia-smi` lists a compute process; checking that the instance's global queue is empty is the caller's job. To run it in a container:

```bash
docker exec -i <container> sh -s -- --read-test <models>/<file> --confirm-idle <models> <storage> < probe/probe-linux.sh
```
