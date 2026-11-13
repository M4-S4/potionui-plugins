# PotionUI plugins

Plugins for [PotionUI](https://github.com/PotionUI/PotionUI), the self-hosted app for AI images and video. Install them from the catalogue of this repository, in a few clicks, from the admin pages of your PotionUI.

## Plugins

| Plugin | What it does | Who uses it | Version | Read first |
|---|---|---|---|---|
| Video Producer | A page for making short films with AI video: write a synopsis, split it into shots, generate takes, pick the best ones, then edit, match colors, mix the sound and export the film. | Every user; an admin sets it up. | 0.5.1 | [Administration](video-producer/README.md), [user guide](video-producer/docs/user-guide.md) |
| Preset Editor | Create, edit, check and publish presets without leaving PotionUI. | Admins only. | 0.2.4 | [README](preset-editor/README.md) |

Both are free software under the GPL-3.0 license.

## Install a plugin from the catalogue

You need an admin account on a PotionUI whose **Admin › Plugins** page shows the **Install from catalog** button.

1. Open **Admin › Plugins** and click **Install from catalog**.
2. Paste the catalogue URL of this repository and click **Read catalog**:

   ```text
   https://raw.githubusercontent.com/M4-S4/potionui-plugins/main/plugins.json
   ```

3. Click **Install** next to the plugin you want. PotionUI downloads the release, checks its checksum and says whether the plugin is running or waits, disabled, in the list.
4. If it is disabled, open it in the list and turn it on with its **Enable plugin** switch.
5. Follow the plugin's **Setup** steps in its **Overview** tab, then read its documentation in **Admin › Documentation**.

A plugin runs with the same rights as PotionUI: install only from a catalogue you trust. To update a plugin, open the catalogue again: a newer version shows **Update to** and its version number in place of **Install**.

Video Producer needs more than the plugin itself: a video engine, video presets and their model files, and ffmpeg on the server. Its [administration page](video-producer/README.md) says what to prepare. Preset Editor needs nothing else.

### Install by hand

Without the catalogue, put the plugin folder in `content/plugins/local/<id>` of the instance, then click **Scan for Plugins** in **Admin › Plugins** and enable it:

- from a release: unzip `<id>-<version>.zip` from the [releases page](https://github.com/M4-S4/potionui-plugins/releases) into `content/plugins/local/` (the zip holds the folder `<id>/` with its built frontend);
- from a clone of this repository: copy `<id>/`, then build its frontend (see [Day-to-day work](#day-to-day-work)).

In a Docker container the folder is `/app/content/plugins/local/<id>`: bind-mount it, or copy it with `scripts/potionui-docker.ps1 copy -Plugin <id>`.

## For maintainers

The rest of this page is for the people who develop, test and release these plugins.

This repository holds one folder per plugin, a catalogue (`plugins.json`) that lists them with their releases, a CI that tests them against a pinned PotionUI core, and a GitHub release for each plugin version.

Video Producer is developed in the M4-S4/PotionUI fork and imported here (see [Following the fork](#following-the-fork)); its page ships its own stylesheet (see [Tailwind classes](#tailwind-classes)). Preset Editor is developed here; [its README](preset-editor/README.md#what-is-left-to-do) lists what is left to do.

`archive/` holds the older copies of `model-browser` and `deepseek-provider`, with their core-side tests and the design variants of Model Browser. Both plugins now live upstream, reworked, in PotionUI/PotionUI (`content/plugins/marketplace/`): install them from PotionUI itself. Nothing in `archive/` is in the catalogue, the CI or the scripts' scope.

### Layout

| Path | What it holds |
|---|---|
| `<id>/` | A plugin: the folder that holds its `manifest.yml`, with its own `tests/`. |
| `core-tests/<id>/` | The tests of a plugin that need the internals of the core. They run from `tests/plugins/marketplace/` of a core checkout. |
| `scripts/` | PowerShell tools (`common.ps1` and the scripts below) and `catalogue.py`. |
| `plugins.json` | The catalogue. |
| `core.ref` | The core commit the CI and the releases build and test against. |
| `.github/workflows/` | `ci.yml` and `release.yml`. |
| `.githooks/` | The `pre-commit` hook that runs the public hygiene check (see [Day-to-day work](#day-to-day-work)). |
| `archive/` | Plugins that moved upstream, kept for reference. |
| `audit/` | `potion-audit`, an external API client that audits the default presets of an instance (see [its README](audit/README.md)). Not a plugin: outside the catalogue and the plugin jobs of the CI. The `audit` job of `ci.yml` runs its tests on Ubuntu and Windows, without the core. |

Every text file is stored with LF line endings (`.gitattributes`), whatever `core.autocrlf` says.

### The pinned core

`core.ref` holds the PotionUI commit that the CI and the releases check out from the official repository, PotionUI/PotionUI. Every core change that Video Producer needs is merged there, so it is a commit of its `master` branch, after release 0.1.0; it becomes a tag once a release of the core holds it. Each catalogue entry states the PotionUI version it needs in `requires.core` (see [Catalogue](#catalogue)).

### Day-to-day work

Copy `.env.example` to `.env.local` (ignored by git, never committed) and set `POTIONUI_SRC` to a PotionUI checkout. The scripts read it, or take `-PotionUISrc`:

- `scripts/sync-plugins.ps1 [-Plugin <id>]` mirrors each plugin into `content/plugins/local/<id>` of the checkout, as a real folder (robocopy on Windows, rsync elsewhere).
- `scripts/build-plugins.ps1 [-Plugin <id>] [-Local]` builds the frontend of a plugin with the core's toolchain (`scripts/build-plugins.mjs`) and copies `frontend/dist` back here. `frontend/dist` is ignored by git for every plugin: the CI builds it and the releases carry it. The script installs the plugin toolchain (`npm install` in `content/plugins/`) when it is missing, but not the packages of the core's `frontend/`: for a plugin whose page ships a stylesheet, such as Video Producer, run `npm ci` in `frontend/` of the checkout first, or the build stops when it compiles the sheet. From the root of a core checkout that holds the plugin, `node scripts/build-plugins.mjs <id>` does the same build; it needs the packages of the core's `content/plugins/` and, for a page that ships a stylesheet, of its `frontend/` (`npm ci` in each).
- `scripts/test-plugins.ps1 [-Plugin <id>]` runs the pytest suite of each plugin in its own process, from the checkout or in the container named by `POTIONUI_CONTAINER`.
- `scripts/import-from-fork.ps1` brings Video Producer here from the fork (next section).

This repository is public, and no file in it names a folder of one machine. `scripts/check-public-hygiene.py` reads every tracked file, or with `--staged` the staged files as the index holds them, or the files and folders it is given (a folder: its tracked files and its new files that git does not ignore). It lists the file, the line and the pattern of each finding and exits with 1 on: an account path under a `Users` or `home` folder, a WSL or Docker Desktop path to the host, the PotionUI folder of drive `E:`, a path into a OneDrive folder (the name alone is fine), the folder of internal notes, a `.secrets` folder, or an Apple private relay address. The same patterns are in `video-producer/tests/test_public_hygiene.py`, for the plugin's own suite. A fake value that a test needs goes in `scripts/public-hygiene-allow.txt`, one `<path><TAB><exact text>` line each; an entry whose text is no longer in its file fails the check too. `scripts/test_check_public_hygiene.py` holds its self-tests (`python -B -m unittest discover -s scripts -p "test_check_public_hygiene.py"`).

Activate the versioned hooks once in each clone, so that a commit whose staged files fail the check is refused:

```bash
git config core.hooksPath .githooks
```

### Following the fork

Video Producer is still developed in the M4-S4/PotionUI fork, under `content/plugins/marketplace/video-producer/`, which is what the fork's development instance and CI run. The plugin no longer needs the fork to run: every core change it relies on is in PotionUI/PotionUI, and its page ships its own stylesheet. Keeping the fork as its working copy is a working choice, until the plugin is developed here. `scripts/import-from-fork.ps1` copies its current state from a checkout of the fork (`POTIONUI_SRC` or `-PotionUISrc`):

- `content/plugins/marketplace/video-producer/` to `video-producer/`, and `tests/plugins/marketplace/test_video_producer_*.py` to `core-tests/video-producer/`, as a robocopy mirror: a file removed in the fork is removed here;
- never `node_modules`, `frontend/dist`, `__pycache__`, `.pytest_cache` nor `docs/screenshots`: the screenshots are kept here as WebP, and the references of `README.md` and `docs/user-guide.md` are pointed at the `.webp` files. A screenshot added in the fork is listed in a warning: convert it to WebP and add it by hand.

The script then runs `scripts/check-public-hygiene.py` on `video-producer/` and `core-tests/video-producer/` and stops with an error when a file fails (fix it in the fork, then import again), and shows `git status`. Review the changes with `git diff` and commit them.

### Tailwind classes

The build of the host's frontend compiles the Tailwind classes of the plugins that are on disk when it runs (it scans `content/plugins/*/*/frontend/src`). A plugin installed later, from a release or the catalogue on a Docker image for example, was not scanned: a class that neither the app nor the plugins bundled in the image use has no CSS there.

A page plugin therefore ships its own stylesheet. When `frontend/src/` holds `<Component>.css` next to the page component, the core's `scripts/build-plugins.mjs` compiles it into `frontend/dist/<Component>.css`, with the app's `frontend/tailwind.config.js` as a preset, over the plugin's own `frontend/src` only and without Tailwind's base styles; `@tailwind utilities;` is usually the whole file. The page route of the core loads that sheet with the page and confines every rule to the page element, so it follows the app's light and dark themes and touches nothing outside the page. Video Producer ships `frontend/src/VideoProducerPage.css`; Preset Editor ships none and relies on the host's classes. Compiling the sheet needs the packages of the core's `frontend/` (`npm ci` there), which the CI and the release workflows install.

The sheet does not reach content that a plugin renders outside its page element, such as a menu or a dialog moved to `document.body`: render those with the host components, which carry the app's own classes, or give their root the attribute `data-potionui-plugin` with the plugin id, which brings the sheet to the descendants of that root but not to the root itself. See "Shipping a stylesheet with a plugin page" in the core's `docs/plugin-api.md`.

### Catalogue

`plugins.json` is an object `{"schema": 1, "plugins": [...]}` with one entry per plugin hosted here and alive:

| Key | Value |
|---|---|
| `id`, `name`, `description`, `license` | As in the plugin's `manifest.yml`. |
| `version` | The `version` of `manifest.yml`. |
| `source` | `{"repository": "M4-S4/potionui-plugins", "path": "<id>"}`. |
| `requires` | `{"core": "<version or range>", "plugin_api": null}`. `core` is a PotionUI version or a PEP 440 version range, which the core compares with its own version when it reads the catalogue: a bare version means that version or later (`0.1.0` reads as `>=0.1.0`), and a core that does not match, or a value that is not a version, lists the plugin as incompatible. Every core that installs from a catalogue reports 0.1.0 until the next release of PotionUI. |
| `release` | `{"archive": "<URL of the zip>", "sha256": "<hex>"}`, or both `null` while the version has no release. |

`python scripts/catalogue.py --check` checks the schema, that each plugin folder exists, and that each version, id and license equals its manifest's; the CI runs it. When the version of a manifest changes, change the entry's `version` too and set its `release` back to `null` until the new release exists.

### Releases

Push a tag `<id>-v<version>`, where `<version>` is the one of the plugin's `manifest.yml` (for example `video-producer-v0.1.0`). `.github/workflows/release.yml` then:

1. checks the tag against the manifest (`scripts/catalogue.py --tag`);
2. builds the dist against the core of `core.ref`, after `npm ci` in its `content/plugins/` and `frontend/`, so that the zip carries the page stylesheet of a plugin that ships one;
3. packages `<id>-<version>.zip`, the plugin folder with its dist and without `tests/`, and writes its sha256 in `<id>-<version>.sha256`;
4. creates the GitHub release with both files.

Recording the release in the catalogue stays manual. Download the zip from the release, then run:

```bash
python scripts/catalogue.py --release <id> <id>-<version>.zip https://github.com/M4-S4/potionui-plugins/releases/download/<id>-v<version>/<id>-<version>.zip
```

and commit `plugins.json`. The command checks the zip (name, manifest version, dist present, no tests) before it writes the URL and the sha256.

### CI

`.github/workflows/ci.yml` runs on every push and pull request, on `ubuntu-latest`. Its `hygiene` job needs no core: it runs `scripts/check-public-hygiene.py` on every tracked file, then the check's self-tests. Next to it runs one job per plugin of its matrix (`video-producer`, `preset-editor`; each entry names the plugin's core-side test files and Node test globs). Each of these jobs:

1. checks the catalogue;
2. checks out PotionUI/PotionUI at `core.ref`, installs Python 3.12 with the core's `requirements-ci.txt` (CPU-only torch) as the core's own `backend-tests.yml` does, and Node 24 with `npm ci` in `content/plugins/` and in `frontend/`, whose packages compile the stylesheet a plugin page ships;
3. copies its plugin into `content/plugins/local/` of the core with `sync-plugins.ps1`, puts this repository's copy in place of the core's own `content/plugins/marketplace/<id>/` when the core has one (the fork's core has Video Producer there; PotionUI/PotionUI has neither plugin), and puts the plugin's core-side tests from `core-tests/<id>/` in place of the core's copies in `tests/plugins/marketplace/`;
4. builds the dist and publishes it as the `<id>-dist` artifact of the run;
5. runs the plugin's pytest suite and its core-side tests with the markers of the core's CI (`not requires_gpu and not requires_models and not gc_sensitive`), and its Node tests (`frontend/src/i18n/*.test.js` and `frontend/src/lib/*.test.js` for Video Producer, `frontend/src/lib/*.test.js` for Preset Editor).
6. copies the built plugin, without its `tests/`, into `content/plugins/marketplace/<id>/` of the core as well, then runs five of the core's own tests with the same markers: `tests/features/presets/test_mode_labels.py`, `tests/features/recipes/test_shipped_recipes_lint.py`, `tests/features/recipes/executors/test_fixture_form_reactions.py`, `tests/features/plugins/test_default_enabled.py` and `tests/platform/plugins/test_manifest_categories.py`. Most of them read only `content/plugins/marketplace/`, never `local/`, so this pass checks the plugin as a core that ships it would: every mode key of its presets has a plain name, its recipes pass the core's lint, it is not enabled by default, and its manifest has a current category. Preset Editor ships no preset and no recipe, so only the last two bite for it; `test_fixture_form_reactions.py` reads the core's own presets only. The steps before this one still see the plugin in `local/` only.

To add a plugin to the CI, add an entry to the matrix.

## License

GPL-3.0, as each plugin's manifest declares; the text is in `LICENSE`.
