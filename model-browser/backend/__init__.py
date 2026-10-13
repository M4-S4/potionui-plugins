"""Backend of the model-browser plugin.

`api.py` is the router PotionUI mounts, `core_bridge.py` the plugin's seam to the
core's download queue, model catalog, user groups, notifications and plan limits
(through `src.plugin_api`), and `tables.py` / `watcher.py` are driven by the lifecycle
handlers in `hooks/lifecycle_hooks.py`.
"""

PLUGIN_ID = "model-browser"

#: Same as `version:` in manifest.yml (tests/test_manifest.py checks it).
PLUGIN_VERSION = "0.1.0"
