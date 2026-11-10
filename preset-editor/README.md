# Preset Editor

Create, edit, validate and publish presets without leaving PotionUI. A preset starts from a
copy of an existing one or from a blank skeleton, lives as a draft, is checked with PotionUI's
own preset linter, then is published into `content/presets/local/` where Admin → Presets picks
it up without a restart. Admins only.

**Status: version 0.2.3, works on the pinned core and has been seen on screen with an
earlier one, `02cce6fdd`, not yet on the marketplace.** The plugin targets the core of
`core.ref` at the root of this repository, `9b079f504` (the `dev` branch of the M4-S4/PotionUI
fork: upstream `master` at `8d54ffc43`, after release 0.1.0, plus the fork's changes), and its
catalogue entry requires it. Its
pytest suite, its core-side tests (`core-tests/preset-editor/`) and its Node tests run in the
CI against that core. Version 0.1.0 was written for PotionUI `master` at `6903cc19` (0.0.15).

## What changed in 0.2.3

- **Preset mirrors.** On a core where an admin can mirror a preset in Admin → Presets (a
  preset with its own id, name, cover, defaults and modes that reads the files of another
  one), Preset Editor refuses to delete, edit or export a mirror, and to publish a draft under
  the id of a mirror, with an error that names the source preset and points to Admin →
  Presets. In 0.2.2, deleting a mirror of a local preset removed the folder of its source,
  which went to the history. Duplicating a mirror copies the files of its source under the
  new id. On a core without mirrors nothing changes.
- **Deleting checks the folder first.** Before it uninstalls or removes anything, deleting a
  local preset checks that its folder is the one its origin names under
  `content/presets/local`, that no folder on the way there is a link, and that its
  `preset.yml` declares the id being deleted.
- **Restoring a version.** A version from the history is restored under the id its
  `preset.yml` declares. A source folder that 0.2.2 removed with a mirror is in the history
  under the mirror's id, which the preset list no longer shows: `GET
  /api/plugins/preset-editor/presets/<mirror id>/history` lists it, `POST
  .../history/<stamp>/restore` opens it as a draft of the source preset, and publishing that
  draft puts the folder back.
- **Name of an edit draft.** An edit draft takes the name written in `preset.yml`, not the
  display name an admin gave the preset.

## What changed in 0.2.2

- **Description preview like Admin → Presets.** The Markdown preview of `description.md` is
  now rendered by a copy of the core's `processMarkdown`, with its HTML and its classes. A
  single line break stays a line break instead of joining the lines, `####` and deeper
  headings stay plain text, GFM tables are rendered, and a relative link (`docs/guide.md`,
  `public/cover.webp`) is a link instead of its text. The Node tests compare the two
  renderers on the same inputs when the plugin sits in a core checkout, as in the CI.

## What changed in 0.2.1

- **Seen on screen.** The plugin was checked on a running instance of the pinned core, with
  its dark theme at 1440 and 1024 px: the buttons and the Edit… menu in the Presets tab
  header, with the zip of a local preset downloaded through the host client; the form builder
  on a copy of a preset with `files/form/` fragments and an include with vars; the form
  settings of a mode; adding and removing modes; the media thumbnails loaded as blobs;
  publishing without a restart, the history it keeps, and publishing from the Admin header;
  the `anchor` field on the tabs and sections of a form.
- **Description preview.** The Markdown preview of `description.md` renders an image line the
  way Admin → Presets does, as its `!` and its link text with no picture: PotionUI shows no
  image in a description.
- **List header.** The installation filter of the preset list keeps its own width, so the
  search, the filter and Refresh stay on one line.
- **Header buttons.** New Preset and Edit… in Admin → Presets are the host's `Button` in size
  `sm`, mounted through `HostUi` like the buttons of the Preset Editor page, so they take the
  size of Refresh catalog beside them.
- **Field tree of the form builder.** Pressing a node of the tree first saves the inspector
  field being typed in to the node it belongs to, then selects the node at once. The tree's
  drag and drop kept the focus in that field, so a value still being typed (an anchor, a
  label, a name) was lost, or written into the node just clicked: a `tabs` container could
  take the anchor of a tab, and a duplicate anchor then went unflagged. Selecting on the
  press also keeps the click when that save adds or removes a problem line above the tree,
  and each node gets an inspector of its own, so no field shows the value of the node before.
- **Zip of a local preset.** In the Edit… menu of Admin → Presets, the zip button of a preset
  shows a spinner and "Downloading…" while the archive is fetched; the other zip buttons and
  Edit… wait meanwhile, and the menu closes once the download is done.

## What changed in 0.2.0

- **Today's presets.** The form builder knows the keys a mode's `form.yml` gained since 0.0.15:
  `prompt` (required, optional or none), `prompt_label`, `prompt_placeholder` and `llm_guide`
  are form settings, `requirements` (the requirements of that mode alone) and
  `segment_templates` are edited as YAML. A `children:` include may be the mapping
  `{ file, vars }`: the builder accepts it, shows its file and lets you edit its vars, and a
  fields fragment may carry `{{ vars.name }}` placeholders in its defaults. The fragments under
  `files/form/` open in the builder (an option list there opens in the YAML view). A field
  whose `formula:` names a group that `preset.yml` does not declare in `formulas.groups` is
  flagged, since the core's lint refuses it and the draft cannot be published until it is
  declared. The pipeline builder no longer offers `cache:` on a pipe: the core dropped it and
  refuses it. A tab or a section may carry `anchor:` (core 0.1.0), the name plugin preset
  extensions use to add fields into it: the inspector edits it, and the builder flags an anchor
  on another type, one that is not lowercase letters, digits, `_` or `-`, and two tabs (or two
  sections) of a form with the same anchor, which the core refuses.
- **Modes.** Adding a mode suggests the mode names the core knows (`GET
  /api/presets/mode-labels`), the new ones included. Removing a mode is refused while another
  mode or a fragment loads one of its files through `{{ paths.preset }}/modes/<mode>/`, the
  way today's presets share a tab between modes; the message lists the citing files.
- **The host's authenticated client.** Every request goes through the client the host gives
  plugins: the page uses its `api` (`fetchRawFromApp`, `fetchRaw`, `download`), and the buttons
  in Admin → Presets build the same client on `window.__potionui.api`. No token is read from
  `localStorage` any more. Draft media load as blobs and the zip downloads go through
  `download`, so the plugin's routes that served them sit behind the admin dependency like the
  others, and the plugin's own reading of the core's media cookie is gone.
- **Core API.** A preset is found with `preset_template` and its installation read with
  `preset_install_state`, both exported by `src.plugin_api.presets`.
- **Tailwind.** The plugin uses only classes the host's build already compiles (tokens of the
  host, an inline style for one grid placement), so it renders on an instance whose frontend
  was built without it.
- **Windows.** A zip entry whose name holds a backslash is refused on every OS; Python turned
  it into a slash on Windows only.

## What is left to do

- **Workarounds the core still calls for** (none of the matching suggestions has landed):
  `admin.presets.header-actions` is mounted by the Presets tab but not declared in the core's
  list of extension slots, and there is no `admin.presets.card.actions` slot, so the Edit…
  menu stays in the tab header; the linter does not check field types, so a preset that lints
  clean can still be refused by the loader at publish time and is then rolled back;
  `src.plugin_api.presets` has no `reload_presets()`, so the plugin reloads through
  `get_container().preset_template_loader.reload()`, the way the module's docstring names, while
  the core's own reload route still clears the catalogue before it loads it again;
  `content/presets/local` is still not a volume of the official Docker setup; Generate has no
  `?preset=<id>` parameter; the pipeline preview still needs every value the pipeline reads.
- **Host tooltips.** The plugin's own buttons still show their hints with a native `title`,
  where the host now uses its `Tooltip` and `IconButton` tooltips.
- **Page bundle.** The page is one bundle; the core's build can now split it on dynamic
  imports, which the workbench could use.
- **Not seen on screen yet.** The light theme and widths under 1024 px; drag and drop in the
  form builder, a zip import, Restore, the pipeline builder and the form preview of a
  published preset; the rollback of a preset whose field `type:` the loader refuses; the
  0.2.2 description preview; the 0.2.3 refusals for a mirror, whose Edit, Delete and zip
  buttons the preset list still shows.

## Getting started

Put the plugin folder under `content/plugins/local/preset-editor/` (or install it from the
marketplace), build its frontend (`node scripts/build-plugins.mjs preset-editor` from the root
of a core checkout), then Admin → Plugins → Scan and Enable. Two things appear for admins only:
a **Preset Editor** entry in the sidebar (the page `/plugins/preset-editor`) and, in the header
of Admin → Presets, the buttons **New Preset** and **Edit…**. The plugin needs no setting to
work and keeps no database table: drafts and the history are folders under
`storage/plugins/preset-editor/`.

## What you can do

- **New Preset** (header of Admin → Presets, or the Preset Editor page): either copy a
  preset of the catalogue, or start from a blank skeleton (engine, category, modes, a cloud
  driver, or a native model family whose standard chain is wired from the pipe catalogue).
  Give it a name, the folder `content/presets/local/<Model>/<variant>` and optionally an id;
  the id is otherwise generated like the ids of the presets PotionUI ships. From the Admin
  header, "Publish right away" publishes the copy as it is and opens it there.
- **Edit…** (same header) lists the local presets and opens one as a draft; publishing writes
  it back over its folder, and the previous version goes to the history.
- The draft workbench lists the files, opens any YAML, Markdown, JSON or text file in a text
  editor with line numbers, insertable fragments (a `_shared` options file, the standard
  native chain, a `@loop` block, the cloud chain, a field) and a save that refuses to
  overwrite a file changed elsewhere. Modes are added from the skeleton or removed.
- `preset.yml` opens as a form: name, version, category, engine, driver and tags as fields,
  the advanced sections (`vars`, `configuration`, `llm`, `speed_profiles`, `formulas`,
  `requires`, `requirements`, `prompt_resources`, `prompt_syntax`, `negative_prompt`) as
  YAML, `id` and `schema` read-only. Saving rewrites only the keys you changed, keeps the
  rest of the file as it is, and asks before dropping a comment inside a rewritten section.
  The YAML view edits the whole file.
- The Media view uploads the cover and the gallery examples (images are downscaled to
  1024 px WebP as PotionUI does for style previews, videos are stored as they are), declares
  them in `media:` with a caption, a mode, a seed and a prompt, reorders the gallery, picks a
  cover among the files already there and deletes files. `description.md` has a Markdown
  preview built by a copy of the core's `processMarkdown`, the renderer of Admin → Presets,
  with the same HTML and classes: a single line break stays a line break, headings stop at
  `###`, GFM tables are tables, a relative link is a link, and an image line appears as its `!`
  and its link, since PotionUI shows no image in a description.
- `form.yml`, `tabs/*.yml` and the fragments under `files/` open in a builder: the field tree
  (drag and drop, containers, tabs and includes backed by files), a palette of every field
  type this instance knows, an inspector for the attributes PotionUI's schema defines (typed
  default, width, audience, flags, formula group, the type's own configuration keys, option
  lists, `_shared` option files, the vars of an include) and raw YAML for the rest (`when`,
  `reactions`, …). What the core would refuse shows before saving. Form settings (label,
  description, prompt, prompt label and placeholder, assistant guide, examples, default
  variant, order, `negative_prompt`, `requirements`, `segment_templates`) and new variants
  (`variants/<name>/form.yml`) are edited there too. Saving rewrites the whole file, so its
  comments go away; the YAML view keeps them.
- `pipeline.yml` opens in a builder too: the ordered pipe list, the pipe catalogue of this
  instance, inputs as `[input, source pipe, output]` triples checked against the catalogue
  (a source must come earlier in the list, its output must exist and match the input's
  type), each pipe's declared configuration keys with their choices, Jinja values kept as
  text, and two start chains (a native family, cloud). Once the preset is published, the
  form preview can render the pipeline with the form's current values through PotionUI's
  own pipeline builder, which needs every value the pipeline reads, models included.
- **Download zip** on a draft, and the `zip` button of each local preset in the Edit… menu,
  give the folder as an archive. **Import zip** turns such an archive, or any zipped preset
  folder with `preset.yml` at its root, into a draft: every entry is checked before
  anything is written (no path escape, no link, no backslash, caps on size and count, allowed
  extensions only), then the draft is linted.
- A draft shows its lint report; **Publish** needs a report without errors, writes the preset
  atomically, reloads the catalogue and checks that PotionUI loads it. When the loader
  refuses the preset (the linter does not check everything, field types for one), the
  previous state is put back and the loader's messages are shown. By default a published
  preset is installed on the instance; assigning it to users and groups stays in
  Admin → Presets, as for any preset. Once published, the form of each mode can be previewed
  in the workbench with PotionUI's own form renderer.
- **History** lists the versions kept when a local preset was published over or deleted;
  **Restore** opens one as a draft. **Delete** uninstalls a local preset and moves its folder
  to the history.

## Limits worth knowing

- The form and pipeline builders rewrite the whole file they save: comments and the
  original formatting go away (the YAML view keeps them, and the `preset.yml` form rewrites
  only the sections you change). Every attribute a builder does not show is kept as raw YAML.
- A fragment with `{{ vars.name }}` placeholders is checked by the builder as a fragment; the
  core's lint, run on every save, tells whether each include gives it the vars it needs.
- The form preview and the rendered pipeline exist only for a published version, and the
  pipeline renders only when every form value it reads is filled in, models included.
- Media uploads are capped at 20 MB and limited to PotionUI's own extensions (`.jpg`,
  `.jpeg`, `.png`, `.webp`, `.gif`, `.mp4`, `.webm`; no SVG). Images become 1024 px WebP.
  Draft media are fetched whole before they show, videos included.
- A zip import is unpacked only after every entry passed the checks (64 MB archive, 256 MB
  unpacked, 2000 entries, no link, no path escape, text and media files only).
- The linter does not check field types: a preset that lints clean but uses a `type:` the
  loader refuses is rolled back at publish time, with the loader's messages.
- Preset ids are generated like PotionUI's own (ULID) unless you set one; a published id
  must be free across every scanned root, marketplace included, because the loader keeps
  the first preset it finds for an id.

## Where things live

- Published presets: `content/presets/local/<Model>/<variant>/`, the user-owned preset root
  PotionUI scans and backs up. In Docker, mount that folder as a volume: the official image
  only mounts `/app/models` and `/app/storage`, so a published preset would otherwise vanish
  when the container is recreated.
- Drafts and history: `storage/plugins/preset-editor/`. They are not part of the core backup.
- A transient staging area, `content/presets/.preset-editor/staging/`, is emptied when the
  application starts.

## Tests

From the root of a core checkout that holds the plugin in `content/plugins/local/preset-editor`
(`scripts/sync-plugins.ps1 -Plugin preset-editor`) and its core-side tests in
`tests/plugins/marketplace/`:

```bash
python -m pytest content/plugins/local/preset-editor/tests -n 4 -m "not requires_gpu and not requires_models and not gc_sensitive"
python -m pytest tests/plugins/marketplace/test_preset_editor_*.py -m "not requires_gpu and not requires_models and not gc_sensitive"
cd content/plugins/local/preset-editor && node --test "frontend/src/lib/*.test.js"
```

The Node tests include a check of every form, fragment and pipeline of the core's
`content/presets/` against the builders; it is skipped when the plugin is not inside a core
checkout.

## Settings

In Admin → Plugins → Preset Editor → Settings:

- **Versions kept per preset** (default 10).
- **Install a published preset on this instance** (on by default; the publish dialog can
  override it each time).
