# Preset Editor

Create, edit, validate and publish presets without leaving PotionUI. A preset starts from a
copy of an existing one (a skeleton comes later), lives as a draft, is checked with PotionUI's
own preset linter, then is published into `content/presets/local/` where Admin → Presets picks
it up without a restart. Admins only.

**Status: in development (phase 1).** Duplicating, editing in place, publishing, the version
history and deleting work; the file editor and the structured editors come with the next
phases.

## What you can do

- **New Preset** (header of Admin → Presets, or the Preset Editor page): pick a preset of the
  catalogue, a name, the folder `content/presets/local/<Model>/<variant>` and optionally an id,
  and get a draft copy. The id is generated like the ids of the presets PotionUI ships.
- **Edit…** (same header) lists the local presets and opens one as a draft; publishing writes
  it back over its folder, and the previous version goes to the history.
- A draft shows its lint report; **Publish** needs a report without errors, writes the preset
  atomically, reloads the catalogue and, by default, installs the preset on the instance.
  Assigning it to users and groups stays in Admin → Presets, as for any preset.
- **History** lists the versions kept when a local preset was published over or deleted;
  **Restore** opens one as a draft. **Delete** uninstalls a local preset and moves its folder
  to the history.

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
