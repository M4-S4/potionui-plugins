Potion audit
============

An external API client that audits the presets PotionUI ships by default. It runs on a workstation, connects to the instance to test by its URL and never starts an instance itself. Results are written to an output folder outside this repository and are never committed.

This is lot 0: the skeleton, a read-only `check`, a minimal `run --only` for single cases, the disk probes and the PyAV helpers. The test pack, the full matrix, the report and the Video Producer scenario come later.

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
| `uv run --locked potion-audit check` | Logs in, then only reads: application and plugin versions, the `version` of each installed preset and its assignments, the hardware the API exposes, the disk space it reports, the global queue, and for each case whether its models are on the instance (`GET /api/models/hash/{sha256}`), with the size of the missing ones. Writes `preflight.json` and `preflight.html`. Exits with 2 when something blocks a run (login, non-admin account, busy queue). | no |
| `uv run --locked potion-audit run --only <preset>:<mode> --dry-run` | Checks the queue, looks the models up and writes the request it would submit. Submits nothing. | no |
| `uv run --locked potion-audit run --only <preset>:<mode> --confirm-gpu` | Submits one case (the `fast` one of that mode when there is one), follows it, downloads the export bundle, reads the outputs and the statistics, and writes `result.json`. Refused without `--confirm-gpu`. Exits with 0 on PASS, 1 on FAIL, OOM or TIMEOUT, 2 when refused, 3 when stopped with Ctrl+C (the generation is cancelled). | yes |
| `uv run --locked --group cases potion-audit cases import --core <checkout> --ref <commit> --out cases/<file>.json` | Builds a case file from the `tests.yml` files and recipes of a core checkout, read with `git show` at that commit. Needs PyYAML, in the `cases` group. | no |
| `uv run --locked potion-audit media probe <file> [--preview <out.mp4>]` | Decodes a video or an image with PyAV or Pillow: size, fps, duration, frame count, black check, and an optional reduced H.264 copy. | no |
| `uv run --locked potion-audit media encoders` | Lists the video encoders of the FFmpeg bundled with PyAV. | no |

`<preset>` is the preset folder name (`ZImage`, `Wan2.1-T2V-1.3B-8GB`) or its id. A preset whose mode is driven by a Video Director document gets a minimal one-shot `t2v` document built from the case prompt.

Cases
-----

`cases/d7ff033de.json` holds the 52 cases of the `tests.yml` files of the core and of its marketplace plugins at commit `d7ff033de` of M4-S4/PotionUI, with the 35 presets and 26 recipes found there. A case whose `tests.yml` gives an all-zero sha256 takes the sha256 of a recipe artifact of that preset: the one its form field recommends, or the only one whose id and file name hold the words of the field name, or the only one of the field's model type. When none fits, or the recipe itself has no sha256, the model stays unresolved and `check` lists it apart, with the file name and size of the recipe when there is one.

Probes
------

`probe/probe-windows.ps1 [-Out <file>]` lists, for Windows PowerShell 5.1 or PowerShell 7 without admin rights: physical disks (model, bus, media, size, firmware, health; never a serial number), partitions, volumes with free space, the WSL distributions and Docker Desktop disks with the VHDX file facts, `.wslconfig`, the GPU and its compute processes, and the state of the Windows session. Paths under the user profile are written as `<home>`.

`probe/probe-linux.sh [--read-test <file> --confirm-idle [--max-bytes <n>]] <path>...` is POSIX `sh` for a Linux host or a container: `df`, the file system type and `findmnt` for each path, `lsblk`, and, only with `--confirm-idle`, a sequential read of at most 4 GiB of a real file with `dd iflag=direct`. It refuses the read when `nvidia-smi` lists a compute process; checking that the instance's global queue is empty is the caller's job. To run it in a container:

```bash
docker exec -i <container> sh -s -- --read-test <models>/<file> --confirm-idle <models> <storage> < probe/probe-linux.sh
```
