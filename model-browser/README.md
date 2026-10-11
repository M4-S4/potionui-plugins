# Model Browser

Browse models on CivitAI (civitai.com and civitai.red), Hugging Face, OpenModelDB and
CivArchive from inside PotionUI, and download the file you pick into the right model folder
through PotionUI's own download queue. The model then shows up on the Models page with its
description, previews, tags, base model and license filled in. Admins and users can both use
it: an admin decides per user group who may browse, request or download, and what users see
follows the instance's NSFW content policy.

## Status: phase 1 (API only)

CivitAI browsing works through the API for every signed-in user with the `browse` right;
the page at `/plugins/model-browser` is still the phase 0 placeholder (phase 4 builds it),
and nothing can be downloaded yet (phase 3).

- A **Model Browser** entry in the sidebar; `GET /api/plugins/model-browser/health`.
- `GET /me`: the caller's capabilities, download parameters and NSFW context.
- Admin `GET`/`PUT /permissions`: rights per user group (`browse`, `request`, `download`,
  `approve`, plus the download parameters). Defaults: everyone may browse and request,
  admins may do everything.
- `GET /sources`, `GET /civitai/search`, `GET /civitai/models/{id}` and
  `GET /civitai/models/{id}/nsfw-media`: search and detail, filtered per user from the
  core's content policy, the plugin's `nsfw_ceiling` / `nsfw_max_level` settings and the
  user's own `media_nsfw_filter_mode`. Raw answers are cached in the database
  (`cache_ttl_minutes`) and filtered on every request.
- Settings in Admin → Plugins → Model Browser → Settings.
- The plugin's tables (`model_browser_*`), created at every start, and an idle background
  task (the download watcher) started with the application and stopped when the plugin is
  disabled. Look for `[MODEL-BROWSER]` lines in the server log.

The design and the roadmap are in [PLAN.md](PLAN.md) (in French).

## Development

PotionUI only builds and loads the plugins under `content/plugins/marketplace` and
`content/plugins/local`, so the plugin is mirrored into a PotionUI checkout, set as
`POTIONUI_SRC` in `.env.local`. The scripts below are in `scripts/` at the root of this
repository.

1. **Mirror the plugin**: `scripts/sync-plugins.ps1 -Plugin model-browser` copies it to
   `<PotionUI>/content/plugins/local/model-browser`. A copy rather than a junction: esbuild
   resolves a junction to its target, from where the build no longer reaches
   `content/plugins/sdk` and `content/plugins/node_modules`. Run it again after each change.
2. **Build the frontend**: `scripts/build-plugins.ps1 -Plugin model-browser` mirrors the
   plugin, runs PotionUI's build (`npm install` once in `content/plugins`, then
   `node ../../scripts/build-plugins.mjs model-browser` from there) and copies the release
   `frontend/dist/` back here. `-DebugBuild` adds source maps; never commit a debug build.
3. **Run the tests** in a pytest process of their own, from the PotionUI root:
   `python -m pytest content/plugins/local/model-browser/tests -q`, or
   `scripts/test-plugins.ps1 -Plugin model-browser`. With PotionUI in Docker,
   `scripts/potionui-docker.ps1 pytest -Plugin model-browser` runs them inside the container,
   from `/app`. PotionUI's `pytest.ini` applies: the network is blocked, so every HTTP call
   is faked.

4. **Docker dev instance** (`POTIONUI_CONTAINER` in `.env.local`): the plugin folder is
   bind-mounted on `/app/content/plugins/local/model-browser`, so edits are live. New or changed
   plugin: `scripts/potionui-docker.ps1 scan`, then `enable -Plugin model-browser`; changed
   manifest or Python code: `scripts/potionui-docker.ps1 restart` (a rescan reloads the
   plugin without firing `disable`, so its old background task would keep running).

Restart PotionUI after changing Python code: disabling and enabling the plugin re-imports
only the modules the manifest names, not the ones they import.
