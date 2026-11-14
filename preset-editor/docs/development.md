# Preset Editor: development

What is left to do and how to run the tests. How the repository is laid out, tested and released is in [dev/README.md](../../dev/README.md).

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
- **Not seen on screen yet.** The light theme beyond the preset list and its Edit… menu, and
  widths under 1024 px; drag and drop in the form builder, a zip import, Restore, the pipeline
  builder and the form preview of a published preset; the rollback of a preset whose field
  `type:` the loader refuses; the 0.2.2 description preview.

## Tests

The CI runs these suites against the core of `dev/core.ref` in this repository.

From the root of a core checkout that holds the plugin in `content/plugins/local/preset-editor`
(`dev/scripts/sync-plugins.ps1 -Plugin preset-editor`) and its core-side tests in
`tests/plugins/marketplace/`:

```bash
python -m pytest content/plugins/local/preset-editor/tests -n 4 -m "not requires_gpu and not requires_models and not gc_sensitive"
python -m pytest tests/plugins/marketplace/test_preset_editor_*.py -m "not requires_gpu and not requires_models and not gc_sensitive"
cd content/plugins/local/preset-editor && node --test "frontend/src/lib/*.test.js"
```

The Node tests include a check of every form, fragment and pipeline of the core's
`content/presets/` against the builders; it is skipped when the plugin is not inside a core
checkout.
