# PotionUI plugins

The PotionUI plugins of M4-S4, in one repository: one folder per plugin, a catalogue (`plugins.json`) that lists them with their releases, a CI that tests them against a pinned PotionUI core, and a GitHub release for each plugin version.

## Plugins

| Plugin | Folder | Version | State |
|---|---|---|---|
| Video Producer | `video-producer/` | 0.1.0 | Maintained and tested by the CI against the pinned core. Its working copy is still the M4-S4/PotionUI fork: see [Following the fork](#following-the-fork). |
| Preset Editor | `preset-editor/` | 0.1.0 | Written for PotionUI 0.0.15 and not reviewed since. It is in the catalogue with `"core": "v0.0.15"`, but not in the CI yet. |

`archive/` holds the older copies of `model-browser` and `deepseek-provider`, with their core-side tests and the design variants of Model Browser. Both plugins now live upstream, reworked, in PotionUI/PotionUI (`content/plugins/marketplace/`): install them from PotionUI itself. Nothing in `archive/` is in the catalogue, the CI or the scripts' scope.

## Layout

| Path | What it holds |
|---|---|
| `<id>/` | A plugin: the folder that holds its `manifest.yml`, with its own `tests/`. |
| `core-tests/<id>/` | The tests of a plugin that need the internals of the core. They run from `tests/plugins/marketplace/` of a core checkout. |
| `scripts/` | PowerShell tools (`common.ps1` and the scripts below) and `catalogue.py`. |
| `plugins.json` | The catalogue. |
| `core.ref` | The core commit the CI and the releases build and test against. |
| `.github/workflows/` | `ci.yml` and `release.yml`. |
| `archive/` | Plugins that moved upstream, kept for reference. |

Every text file is stored with LF line endings (`.gitattributes`), whatever `core.autocrlf` says.

## The pinned core

`core.ref` holds the PotionUI commit that the CI and the releases check out. It is a commit of the M4-S4/PotionUI fork as long as the core changes that Video Producer needs are not merged upstream; it then becomes a tag of PotionUI/PotionUI. Each catalogue entry states the core it needs in `requires.core`.

## Day-to-day work

Copy `.env.example` to `.env.local` (ignored by git, never committed) and set `POTIONUI_SRC` to a PotionUI checkout. The scripts read it, or take `-PotionUISrc`:

- `scripts/sync-plugins.ps1 [-Plugin <id>]` mirrors each plugin into `content/plugins/local/<id>` of the checkout, as a real folder (robocopy on Windows, rsync elsewhere).
- `scripts/build-plugins.ps1 [-Plugin <id>] [-Local]` builds the frontend of a plugin with the core's toolchain (`scripts/build-plugins.mjs`) and copies `frontend/dist` back here. `frontend/dist` is ignored by git for every plugin: the CI builds it and the releases carry it.
- `scripts/test-plugins.ps1 [-Plugin <id>]` runs the pytest suite of each plugin in its own process, from the checkout or in the container named by `POTIONUI_CONTAINER`.
- `scripts/import-from-fork.ps1` brings Video Producer here from the fork (next section).

### Following the fork

Until the core loads a CSS file shipped with a plugin installed outside its tree (see [Tailwind classes](#tailwind-classes)), Video Producer is developed in the M4-S4/PotionUI fork, under `content/plugins/marketplace/video-producer/`, which is what the fork's instance and CI run. `scripts/import-from-fork.ps1` copies its current state from a checkout of the fork (`POTIONUI_SRC` or `-PotionUISrc`):

- `content/plugins/marketplace/video-producer/` to `video-producer/`, and `tests/plugins/marketplace/test_video_producer_*.py` to `core-tests/video-producer/`, as a robocopy mirror: a file removed in the fork is removed here;
- never `node_modules`, `frontend/dist`, `__pycache__`, `.pytest_cache` nor `docs/screenshots`: the screenshots are kept here as WebP, and the references of `README.md` and `docs/user-guide.md` are pointed at the `.webp` files. A screenshot added in the fork is listed in a warning: convert it to WebP and add it by hand.

The script then shows `git status`. Review the changes with `git diff` and commit them.

## Installing a plugin on an instance

1. Put the plugin folder, with its built `frontend/dist`, at `content/plugins/local/<id>` of the instance:
   - from a release: unzip `<id>-<version>.zip` into `content/plugins/local/` (the zip holds the folder `<id>/` with its dist and without its tests);
   - from a clone of this repository: copy `<id>/`, then build its dist (`scripts/build-plugins.ps1 -Plugin <id> -Local`, or `node scripts/build-plugins.mjs <id>` from the root of a core checkout that holds the plugin).

   In a Docker container the folder is `/app/content/plugins/local/<id>`: bind-mount it, or copy it with `scripts/potionui-docker.ps1 copy -Plugin <id>`.
2. In PotionUI, open Admin → Plugins, click **Scan for Plugins**, then enable the plugin.

### Tailwind classes

The dist of a plugin carries no Tailwind CSS. The classes a plugin uses are compiled by the build of the host's frontend, which scans `content/plugins/*/*/frontend/src`. A plugin installed after a Docker image was built was not scanned: a class that neither the app nor the plugins bundled in the image already use has no CSS, until the core loads a CSS file shipped with the plugin, or until the app frontend is rebuilt from a checkout that holds the plugin. Write plugin markup with the host's token classes, and use inline styles for a new arbitrary value.

## Catalogue

`plugins.json` is an object `{"schema": 1, "plugins": [...]}` with one entry per plugin hosted here and alive:

| Key | Value |
|---|---|
| `id`, `name`, `description`, `license` | As in the plugin's `manifest.yml`. |
| `version` | The `version` of `manifest.yml`. |
| `source` | `{"repository": "M4-S4/potionui-plugins", "path": "<id>"}`. |
| `requires` | `{"core": "<core ref>", "plugin_api": null}`. |
| `release` | `{"archive": "<URL of the zip>", "sha256": "<hex>"}`, or both `null` while the version has no release. |

`python scripts/catalogue.py --check` checks the schema, that each plugin folder exists, and that each version, id and license equals its manifest's; the CI runs it. When the version of a manifest changes, change the entry's `version` too and set its `release` back to `null` until the new release exists.

## Releases

Push a tag `<id>-v<version>`, where `<version>` is the one of the plugin's `manifest.yml` (for example `video-producer-v0.1.0`). `.github/workflows/release.yml` then:

1. checks the tag against the manifest (`scripts/catalogue.py --tag`);
2. builds the dist against the core of `core.ref`;
3. packages `<id>-<version>.zip`, the plugin folder with its dist and without `tests/`, and writes its sha256 in `<id>-<version>.sha256`;
4. creates the GitHub release with both files.

Recording the release in the catalogue stays manual. Download the zip from the release, then run:

```bash
python scripts/catalogue.py --release <id> <id>-<version>.zip https://github.com/M4-S4/potionui-plugins/releases/download/<id>-v<version>/<id>-<version>.zip
```

and commit `plugins.json`. The command checks the zip (name, manifest version, dist present, no tests) before it writes the URL and the sha256.

## CI

`.github/workflows/ci.yml` runs on every push and pull request, on `ubuntu-latest`:

1. checks the catalogue;
2. checks out M4-S4/PotionUI at `core.ref`, installs Python 3.12 with the core's `requirements-ci.txt` (CPU-only torch) as the core's own `backend-tests.yml` does, and Node 24 with `npm ci` in `content/plugins/`;
3. copies Video Producer into `content/plugins/local/` of the core with `sync-plugins.ps1`, and puts this repository's copy and core-side tests in place of the core's own copies (`content/plugins/marketplace/video-producer/` and `tests/plugins/marketplace/test_video_producer_*.py`), since the core-side tests look for the plugin there;
4. builds the dist and publishes it as the `video-producer-dist` artifact of the run;
5. runs the plugin's pytest suite and the core-side tests with the markers of the core's CI (`not requires_gpu and not requires_models and not gc_sensitive`), and the Node tests of the dictionaries (`frontend/src/i18n/*.test.js`) and of the page modules (`frontend/src/lib/*.test.js`).

Preset Editor is not in the CI yet.

## License

GPL-3.0, as each plugin's manifest declares; the text is in `LICENSE`.
