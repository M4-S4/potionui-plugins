# Preset Editor

Create, edit, validate and publish presets without leaving PotionUI. A preset starts from a
copy of an existing one (a skeleton comes later), lives as a draft, is checked with PotionUI's
own preset linter, then is published into `content/presets/local/` where Admin → Presets picks
it up without a restart. Admins only.

**Status: in development (phase 6).** Drafts from a copy, a blank skeleton or a zip
archive, a text editor for every YAML and Markdown file of a draft, a form for
`preset.yml`, the cover and gallery media, builders for forms and pipelines, publishing, zip
export, the version history and deleting work; the last phase finishes the documentation.

## Getting started

Put the plugin folder under `content/plugins/local/preset-editor/` (or install it from the
marketplace), then Admin → Plugins → Scan and Enable. Two things appear for admins only: a
**Preset Editor** entry in the sidebar (the page `/plugins/preset-editor`) and, in the header
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
  preview that shows the images under `public/`.
- `form.yml` and `tabs/*.yml` open in a builder: the field tree (drag and drop, containers,
  tabs backed by files), a palette of every field type this instance knows, an inspector for
  the attributes PotionUI's schema defines (typed default, width, audience, flags, the type's
  own configuration keys, option lists, `_shared` option files) and raw YAML for the rest
  (`when`, `reactions`, …). What the core would refuse shows before saving. Form settings
  (label, description, examples, default variant, order, `negative_prompt`) and new variants
  (`variants/<name>/form.yml`) are edited there too. Saving rewrites the whole file, so its
  comments go away; the YAML view keeps them.
- `pipeline.yml` opens in a builder too: the ordered pipe list, the pipe catalogue of this
  instance, inputs as `[input, source pipe, output]` triples checked against the catalogue
  (a source must come earlier in the list, its output must exist and match the input's
  type), each pipe's declared configuration keys with their choices, Jinja values kept as
  text, and two start chains (a native family, cloud). Once the preset is published, the
  form preview can render the pipeline with the form's current values through PotionUI's
  own pipeline builder, which needs every value the pipeline reads, models included.
- **Download zip** on a draft, and the `zip` link of each local preset in the Edit… menu,
  give the folder as an archive. **Import zip** turns such an archive, or any zipped preset
  folder with `preset.yml` at its root, into a draft: every entry is checked before
  anything is written (no path escape, no link, caps on size and count, allowed extensions
  only), then the draft is linted.
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
- The form preview and the rendered pipeline exist only for a published version, and the
  pipeline renders only when every form value it reads is filled in, models included.
- Media uploads are capped at 20 MB and limited to PotionUI's own extensions (`.jpg`,
  `.jpeg`, `.png`, `.webp`, `.gif`, `.mp4`, `.webm`; no SVG). Images become 1024 px WebP.
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

## Settings

In Admin → Plugins → Preset Editor → Settings:

- **Versions kept per preset** (default 10).
- **Install a published preset on this instance** (on by default; the publish dialog can
  override it each time).
