# Preset Editor

Create, edit, check and publish presets without leaving PotionUI. For admins only.

Version 0.2.5. It needs PotionUI 0.1.0 or later. Install it from the catalogue of this repository:

```text
https://raw.githubusercontent.com/M4-S4/potionui-plugins/main/plugins.json
```

1. In **Admin › Plugins**, click **Install from catalog**, paste the catalogue URL and click **Read catalog**.
2. Click **Install** next to **Preset Editor**.
3. Enable it.

Without the catalogue, put the plugin folder under `content/plugins/local/preset-editor/`, build its frontend (`node scripts/build-plugins.mjs preset-editor` from the root of a core checkout), then click **Scan for Plugins** in **Admin › Plugins** and enable it.

To update from 0.2.4 to 0.2.5, disable Preset Editor in **Admin › Plugins**, restart PotionUI, update it from the catalogue, then enable it. An update started while 0.2.4 is enabled is refused with the message that 0.2.5 did not start, and 0.2.4 stays in place; restarting and updating again gives the same refusal.

## What it needs on the server

Nothing else: the plugin needs no setting to work and keeps no database table. Drafts and the history are folders under `storage/plugins/preset-editor/`, which are not part of the core backup. Published presets go to `content/presets/local/`: in Docker, mount that folder as a volume, or a published preset vanishes when the container is recreated. Its routes are for a signed-in admin only: on PotionUI 0.2.0 and later, no API key reaches them, whatever its scope.

## What you can do

Two things appear, for admins only: a **Preset Editor** entry in the sidebar (the page `/plugins/preset-editor`) and, in the header of **Admin › Presets**, the buttons **New Preset** and **Edit…**.

- **New Preset** copies a preset of the catalogue or starts from a blank skeleton, as a draft in `content/presets/local/<Model>/<variant>`; **Edit…** opens a local preset as a draft.
- The draft workbench edits every file of the preset: `preset.yml` as a form, `form.yml`, its tabs and fragments in a form builder, `pipeline.yml` in a pipeline builder, any file in a text editor, and the cover and gallery in the Media view, with a preview of `description.md` as **Admin › Presets** shows it.
- A draft shows the report of PotionUI's own preset linter. **Publish** needs a report without errors, writes the preset, reloads the catalogue without a restart and checks that PotionUI loads it; when the loader refuses it, the previous state is put back.
- **History** keeps the versions replaced or deleted, and **Restore** opens one as a draft. **Download zip** and **Import zip** move a preset folder in and out as an archive.

Every option, check and setting is in the [reference](docs/reference.md), which PotionUI also shows in **Admin › Documentation** as "Preset Editor: reference".

## Limits worth knowing

- The form and pipeline builders rewrite the whole file they save: comments and the original formatting go away. The YAML view keeps them.
- The form preview and the rendered pipeline exist only for a published version.
- The linter does not check field types: a preset that lints clean but uses a `type:` the loader refuses is rolled back at publish time, with the loader's messages.
- Media uploads are capped at 20 MB, with PotionUI's own extensions only (no SVG).

The [reference](docs/reference.md#limits-worth-knowing) lists them all. What is left to do and how to run the tests are in [docs/development.md](docs/development.md).

## Changes

### What changed in 0.2.5

- **Modes that take the pipeline of another mode.** PotionUI 0.2.0 lets a mode's
  `pipeline.yml` be the single line `pipeline_from: <mode>`, as in the Text to Video, Image to
  Video and First to Last Frame modes of its MiniMax-H3 preset. The pipeline builder of 0.2.4
  wrote such a file back with `pipeline: []` beside that line, which PotionUI refuses, so
  saving it broke the mode. The builder now opens it read-only and names the mode whose
  pipeline runs, and removing a mode that another mode names this way is refused.
- **Links in the description preview.** The preview follows the link rule of PotionUI 0.2.0
  (`safeUrl`): an encoded `javascript:` link, a `data:` link, `//host` and a bare relative
  target are text, as in Admin → Presets.
- **API keys.** On PotionUI 0.2.0, an API key with the `admin` scope could reach every route
  of the plugin. Every route now refuses every API key; a signed-in admin works as before.

### What changed in 0.2.4

- **Preset mirrors in the list.** The preset list and the Edit… menu no longer offer Edit,
  History, Delete or the zip export for a preset mirror, which the server refuses since
  0.2.3: a mirror has no files of its own. The list marks it with a *mirror* pill whose hint
  names its source preset. Duplicate stays and copies the files of the source. The page tells
  a mirror by the `source_preset_id` that the core's admin preset list gives each preset; on a
  core without mirrors nothing changes.

### What changed in 0.2.3

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

### What changed in 0.2.2

- **Description preview like Admin → Presets.** The Markdown preview of `description.md` is
  now rendered by a copy of the core's `processMarkdown`, with its HTML and its classes. A
  single line break stays a line break instead of joining the lines, `####` and deeper
  headings stay plain text, GFM tables are rendered, and a relative link (`docs/guide.md`,
  `public/cover.webp`) is a link instead of its text. The Node tests compare the two
  renderers on the same inputs when the plugin sits in a core checkout, as in the CI.

### What changed in 0.2.1

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

### What changed in 0.2.0

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

## License

GPL-3.0, like the other plugins of this repository; the text is in the [LICENSE](../LICENSE) of the repository.
