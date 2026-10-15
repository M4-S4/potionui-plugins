# Preset Editor

Create, edit, validate and publish presets without leaving PotionUI. A preset starts from a
skeleton or from a copy of an existing one, is edited as a draft, checked with PotionUI's own
preset linter, then published into `content/presets/local/` where Admin → Presets and Generate
pick it up without a restart. Admins only.

**Status: in development (phase 0).** The page, the sidebar entry and the **New Preset** button
in the header of Admin → Presets are in place; drafts, the editor and publishing come with the
next phases.

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
- **Install a published preset on this instance** (on by default).
