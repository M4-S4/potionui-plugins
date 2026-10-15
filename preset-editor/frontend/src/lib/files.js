export const TEXT_EXTENSIONS = ['.yml', '.yaml', '.md', '.json', '.txt'];
export const MEDIA_EXTENSIONS = ['.jpg', '.jpeg', '.png', '.webp', '.gif', '.mp4', '.webm'];

function extensionOf(path) {
	const name = path.split('/').pop() ?? '';
	const dot = name.lastIndexOf('.');
	return dot >= 0 ? name.slice(dot).toLowerCase() : '';
}

export function fileKind(path) {
	const parts = path.split('/');
	const name = parts[parts.length - 1];
	if (path === 'preset.yml') return 'manifest';
	if (path === 'description.md') return 'description';
	if (path === 'tests.yml') return 'tests';
	if (path === 'styles.yml') return 'styles';
	if (parts[0] === 'public') return 'media';
	if (parts[0] === 'modes') {
		if (name === 'pipeline.yml') return 'pipeline';
		if (name === 'form.yml') return 'form';
		if (parts.includes('tabs')) return 'tab';
		if (parts.includes('files')) return 'options';
	}
	if (parts[0] === 'files') return 'options';
	return TEXT_EXTENSIONS.includes(extensionOf(path)) ? 'text' : 'other';
}

export function isEditable(path) {
	return path.split('/')[0] !== 'public' && TEXT_EXTENSIONS.includes(extensionOf(path));
}

export function isMedia(path) {
	return path.split('/')[0] === 'public' && MEDIA_EXTENSIONS.includes(extensionOf(path));
}

export function modeOf(path) {
	const parts = path.split('/');
	return parts[0] === 'modes' && parts.length > 2 ? parts[1] : null;
}

export function buildTree(files) {
	const root = { name: '', path: '', kind: 'dir', children: [] };
	for (const file of Array.isArray(files) ? files : []) {
		if (!file || typeof file.path !== 'string') continue;
		const parts = file.path.split('/');
		let node = root;
		parts.forEach((part, index) => {
			const path = parts.slice(0, index + 1).join('/');
			let child = node.children.find((entry) => entry.name === part);
			if (!child) {
				child = index === parts.length - 1
					? { name: part, path, kind: 'file', size: file.size ?? 0, fileKind: fileKind(path), editable: isEditable(path), media: isMedia(path) }
					: { name: part, path, kind: 'dir', children: [] };
				node.children.push(child);
			}
			node = child;
		});
	}
	const sort = (node) => {
		if (!node.children) return;
		node.children.sort((a, b) => (a.kind === b.kind ? a.name.localeCompare(b.name) : a.kind === 'dir' ? -1 : 1));
		node.children.forEach(sort);
	};
	sort(root);
	return root.children;
}

export function flattenTree(nodes, depth = 0, out = []) {
	for (const node of nodes) {
		out.push({ ...node, depth });
		if (node.children) flattenTree(node.children, depth + 1, out);
	}
	return out;
}

export function lineCount(text) {
	if (typeof text !== 'string' || text === '') return 1;
	return text.split('\n').length;
}

export function insertAt(text, position, snippet) {
	const at = Math.max(0, Math.min(typeof position === 'number' ? position : text.length, text.length));
	const before = text.slice(0, at);
	const after = text.slice(at);
	const lead = before === '' || before.endsWith('\n') ? '' : '\n';
	const tail = after === '' || after.startsWith('\n') ? '' : '\n';
	const inserted = `${lead}${snippet}${tail}`;
	return { text: before + inserted + after, cursor: at + inserted.length };
}

export const SNIPPETS = [
	{
		id: 'shared-options',
		label: 'Options file from _shared',
		kinds: ['tab', 'form'],
		build: (shared = 'resolutions/sdxl.yml') =>
			`  - name: "resolution"\n    type: "resolution"\n    label: "Resolution"\n    configuration:\n      files:\n        - { path: "{{ paths._shared }}/${shared}", group: "Standard" }\n    default: "1024x1024"`
	},
	{
		id: 'tab-reference',
		label: 'Tab loaded from a file',
		kinds: ['form'],
		build: () => `      - type: "tab"\n        label: "Advanced"\n        audience: "advanced"\n        children: "{{ paths.preset }}/modes/<mode>/tabs/advanced.yml"`
	},
	{
		id: 'native-chain',
		label: 'Standard native chain',
		kinds: ['pipeline'],
		build: () =>
			`pipeline:\n  - name: "model_loader/<family>"\n    enabled: true\n    configuration:\n      diffusion_model: { file_path: "{{ form.diffusion_model }}", name: "{{ form.diffusion_model }}" }\n\n  - name: "prompt_encoder"\n    enabled: true\n    configuration:\n      pairs: "{{ generation.prompts.pairs }}"\n      quantity: "{{ form.quantity }}"\n\n  - name: "seed_generator"\n    enabled: true\n    configuration:\n      seed: "{{ form.seed }}"\n      quantity: "{{ form.quantity }}"\n\n  - name: "generator/<family>"\n    input:\n      - ["model", "model_loader/<family>", "model"]\n      - ["conditioning", "prompt_encoder", "conditioning"]\n      - ["seed", "seed_generator", "seed"]\n    enabled: true\n    configuration:\n      steps: "{{ form.steps }}"\n      resolution: "{{ form.resolution }}"\n      quantity: "{{ form.quantity }}"\n\n  - name: "gallery"\n    input:\n      - ["image", "generator/<family>", "image"]\n      - ["seed", "seed_generator", "seed"]\n    enabled: true`
	},
	{
		id: 'loop-block',
		label: '@loop block (LoRAs)',
		kinds: ['pipeline'],
		build: () => `      loras:\n        "@loop":\n          items: "{{ form.loras }}"\n          template:\n            file_path: "{{ item.model }}"\n            weight: "{{ item.strength }}"`
	},
	{
		id: 'cloud-chain',
		label: 'Cloud chain',
		kinds: ['pipeline'],
		build: () =>
			`pipeline:\n  - name: "dynamic_prompts_renderer"\n    id: "dynamic_prompts_renderer"\n    enabled: true\n    configuration:\n      pairs: "{{ generation.prompts.pairs }}"\n      quantity: "{{ form.count or 1 }}"\n\n  - name: "seed_generator"\n    id: "seed_generator"\n    enabled: true\n    configuration:\n      seed: "{{ form.seed }}"\n      quantity: "{{ form.count or 1 }}"\n\n  - name: "cloud_generate"\n    id: "cloud_generate"\n    enabled: true\n    input:\n      - ["seed", "seed_generator", "seed"]\n    configuration:\n      task: "txt2img"\n      model: "{{ form.model }}"\n      quantity: "{{ form.count or 1 }}"\n      prompts: "{{ generation.prompts.pairs }}"\n      params: {}\n      options: "{{ form.provider_options }}"\n\n  - name: "gallery"\n    id: "gallery"\n    enabled: true\n    input:\n      - ["image", "cloud_generate", "image"]\n      - ["seed", "cloud_generate", "seed"]`
	},
	{
		id: 'field',
		label: 'Field',
		kinds: ['tab', 'form'],
		build: () => `  - name: "steps"\n    type: "slider"\n    label: "Steps"\n    default: 30\n    configuration: {min: 1, max: 100, step: 1}`
	}
];

export function snippetsFor(kind) {
	return SNIPPETS.filter((snippet) => snippet.kinds.includes(kind));
}
