# Model Browser

Browse models on CivitAI (civitai.com and civitai.red), Hugging Face, OpenModelDB and
CivArchive from inside PotionUI, and download the file you pick into the right model folder
through PotionUI's own download queue. The model then shows up on the Models page with its
description, previews, tags, base model and license filled in. Admins and users can both use
it: an admin decides per user group who may browse, request or download, and what users see
follows the instance's NSFW content policy.

## Status: phase 5 (requests, notifications, plan quotas)

The **Model Browser** page (`/plugins/model-browser`) searches CivitAI and Hugging Face,
shows a model's versions, previews, files and licence, and downloads a file into PotionUI
for every signed-in user with the `browse` / `download` rights. A user with `request` but
not `download` asks for a file instead; an admin (or a holder of `approve`) approves or
declines the request from the page, and the model lands in the requester's models. Admins
edit the rights per user group in Admin → Plugins → Model Browser → Permissions, and can cap
downloads per month through PotionUI's plans.

- Search box with `#tag`, `@creator`, `$#id1,id2` and pasted model links, filters (types,
  base model, period), sort, infinite scroll; badges for NSFW, installed, early access,
  login-gated and non-downloadable models. The state lives in the URL.
- NSFW previews arrive blurred (a blurhash, no URL) and are revealed on click when the
  content policy allows; the "Sensitive content" control changes the app-wide
  `media_nsfw_filter_mode` within the policy's ceiling.
- Detail drawer with versions, previews, trigger words, files, licence and the source link;
  download dialog with model type, subfolder, file name, remote destination and target
  group (when allowed); downloads tray with live status.

- `POST /downloads` queues one file on PotionUI's download queue (checksum, provider
  credentials, model type folder, optional subfolder, remote destination); the background
  watcher follows it, assigns the indexed model to the requester (or their group) and fills
  the description, safe previews, trigger words, tags, `mb_base_model` / `mb_license` and a
  "Mirrors" link through the plugin's own `model-browser` provider. A file already on disk
  is only assigned. `GET /downloads` lists the caller's downloads with their live status;
  `POST /installed` tells which SHA256s are installed and visible to the caller.
- The requester gets a notification when the model is ready or the download failed.
- Admin → Plugins shows setup steps for the CivitAI and Hugging Face provider plugins.

- **Requests**: a file row shows **Request** to a user who may request but not download it;
  the dialog takes the model type and a note for the admin. The **Requests** drawer (toolbar
  button, with the count of requests to review) lists the user's own requests, and for
  approvers every open request with Approve (type override, note) and Reject (note); the
  author can cancel an open request. Approving re-checks the requester's own rights and NSFW
  context and queues the file for them (or only assigns an already installed model); other
  approved requesters of the same file get it when it arrives.
- Notification types `model-browser.request_received` (to approvers), `request_approved`,
  `request_rejected`, `download_done` and `download_failed` appear in each user's notification
  preferences; the request notifications link to the page's drawer (`?tab=requests`).
- **Quotas**: two limit kinds for Admin → Plans, "Model downloads per month" and "Downloaded
  model bytes per month". The plugin enforces them itself before queueing a file (direct
  download or approval, 403 `limit_exceeded`), records the usage in the core's limit ledger
  and refunds a failed download. Admins are exempt when the plans say so.

- A **Model Browser** entry in the sidebar; `GET /api/plugins/model-browser/health`.
- `GET /me`: the caller's capabilities, download parameters (`params`, merged from the groups
  that grant `download`), request parameters (`request_params`, from the groups that grant
  `request`), NSFW context and open request count.
- Admin `GET`/`PUT /permissions`: rights per user group (`browse`, `request`, `download`,
  `approve`, plus the parameters that bound the group's downloads and requests: sources,
  model types, file size, assignment, remote destination). Defaults: everyone may browse and
  request, admins may do everything.
- `POST /requests`, `GET /requests`, `POST /requests/{id}/approve`, `POST /requests/{id}/reject`,
  `DELETE /requests/{id}`: the request flow above.
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
