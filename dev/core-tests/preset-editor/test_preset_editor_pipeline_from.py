import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest
import yaml

pipeline_source = pytest.importorskip(
    "src.features.presets.pipeline_source", reason="this core has no pipeline_from"
)

PLUGIN_ID = "preset-editor"
REPO_ROOT = Path(__file__).resolve().parents[3]
PLUGIN_ROOTS = [REPO_ROOT / "content" / "plugins" / kind / PLUGIN_ID for kind in ("local", "marketplace")]
PLUGIN_ROOT = next((root for root in PLUGIN_ROOTS if (root / "manifest.yml").is_file()), PLUGIN_ROOTS[0])
MODEL = PLUGIN_ROOT / "frontend" / "src" / "lib" / "pipelineModel.js"
MARKETPLACE = REPO_ROOT / "content" / "presets" / "marketplace"
CASES = {
    "plain": "pipeline_from: video\n",
    "quoted": 'pipeline_from: "video"\n',
    "with an empty pipeline": "pipeline_from: video\npipeline: []\n",
    "with a pipeline": "pipeline_from: video\npipeline:\n- name: seed_generator\n",
    "with another key": "pipeline_from: video\nnote: x\n",
    "parent folder": "pipeline_from: ../video\n",
    "hidden folder": "pipeline_from: .video\n",
    "nested folder": "pipeline_from: video/sub\n",
    "backslash": "pipeline_from: 'video\\\\sub'\n",
    "empty": "pipeline_from: ''\n",
    "number": "pipeline_from: 3\n",
    "missing mode": "pipeline_from: nowhere\n",
    "itself": "pipeline_from: case\n",
    "own pipeline": "pipeline:\n- name: seed_generator\n",
}
TARGET = "pipeline:\n- name: seed_generator\n"
TARGETS = {
    "target is a pointer": "pipeline_from: other\n",
    "target does not parse": "pipeline: [\n",
    "target is empty": "",
    "target is a list": "- name: seed_generator\n",
}
CASES.update({name: "pipeline_from: video\n" for name in TARGETS})
SCRIPT = (
    "const m = await import(process.argv[1]);"
    "const cases = JSON.parse(process.argv[2]);"
    "const files = JSON.parse(process.argv[3]);"
    "const targets = JSON.parse(process.argv[4]);"
    "const out = {};"
    "for (const [name, text] of Object.entries(cases)) {"
    " const doc = m.parsePipelineDocument(text);"
    " const targetText = name in targets ? targets[name] : null;"
    " out[name] = doc.ok ? { problems: m.pointerProblems(doc, { mode: 'case', files, targetText }), text: m.serializePipelineDocument(doc) } : { error: doc.error.message };"
    "}"
    "console.log(JSON.stringify(out));"
)


def _node(cases, files, targets=None):
    node = shutil.which("node")
    if node is None:
        pytest.skip("node is not on the PATH")
    result = subprocess.run(
        [node, "--input-type=module", "-e", SCRIPT, MODEL.as_uri(), json.dumps(cases), json.dumps(files), json.dumps(targets or {})],
        capture_output=True, text=True, encoding="utf-8", cwd=PLUGIN_ROOT, timeout=60,
    )
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout.splitlines()[-1])


def _kind(problem):
    return re.split(r" got | \(| failed to parse", problem, maxsplit=1)[0]


def _preset(tmp_path, text, target=TARGET):
    modes = tmp_path / "preset" / "modes"
    (modes / "video").mkdir(parents=True)
    (modes / "video" / "pipeline.yml").write_text(target, encoding="utf-8")
    (modes / "case").mkdir()
    (modes / "case" / "pipeline.yml").write_text(text, encoding="utf-8")
    return modes / "case"


def test_the_pipeline_builder_refuses_a_pipeline_from_exactly_where_and_why_the_core_does(tmp_path):
    files = ["modes/video/pipeline.yml", "modes/case/pipeline.yml"]
    plugin = _node(CASES, files, TARGETS)

    for name, text in CASES.items():
        core = pipeline_source.pointer_problems(_preset(tmp_path / name.replace(" ", "-"), text, TARGETS.get(name, TARGET)))
        assert "error" not in plugin[name], f"{name}: {plugin[name]}"
        mine = [_kind(problem) for problem in plugin[name]["problems"]]
        assert mine == [_kind(problem) for problem in core], f"{name}: plugin {plugin[name]['problems']}, core {core}"
    assert sum(bool(plugin[name]["problems"]) for name in CASES) == 13


def test_a_pipeline_from_the_builder_accepts_is_saved_back_as_the_core_reads_it(tmp_path):
    plugin = _node(CASES, ["modes/video/pipeline.yml", "modes/case/pipeline.yml"], TARGETS)

    for name, text in CASES.items():
        if plugin[name]["problems"] or "pipeline_from" not in text:
            continue
        target = TARGETS.get(name, TARGET)
        mode_dir = _preset(tmp_path / name.replace(" ", "-"), plugin[name]["text"], target)
        data, problems = pipeline_source.load_mode_pipeline(mode_dir)
        loaded = yaml.safe_load(target)
        assert problems == [], name
        assert data == (loaded if isinstance(loaded, dict) else {}), name


def test_every_pipeline_from_of_the_core_presets_is_saved_back_byte_for_byte():
    pointers = {
        path.relative_to(MARKETPLACE).as_posix(): path.read_text(encoding="utf-8")
        for path in sorted(MARKETPLACE.glob("**/modes/*/pipeline.yml"))
        if pipeline_source.POINTER_KEY in path.read_text(encoding="utf-8")
    }
    assert pointers, "no core preset mode takes the pipeline of another mode"

    plugin = _node(pointers, [])

    for path, text in pointers.items():
        assert plugin[path]["text"] == text, path
