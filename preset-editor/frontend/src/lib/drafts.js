export const PRESET_ID_RE = /^[A-Za-z0-9_-]{3,64}$/;
export const SEGMENT_RE = /^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$/;
export const MAX_NAME_LENGTH = 120;
export const MODE_RE = /^[a-z][a-z0-9_]{0,39}$/;
export const ENGINE_RE = /^[a-z][a-z0-9_]{0,31}$/;
export const DRIVER_RE = /^[a-z][a-z0-9_]*\.[A-Za-z0-9_.-]{1,64}$/;
export const ENGINES = ['native', 'cloud', 'comfyui'];
export const CATEGORIES = ['image', 'video', 'audio', '3d', 'utility'];
export const CLOUD_MODES = ['txt2img', 'edit', 'txt2video', 'img2video'];
export const MAX_MODES = 12;

const LINT_LINE_RE = /^\[(ERROR|WARNING|INFO)\]\s+(.*?):\s+(.*)$/s;
const FILE_PREFIX_RE = /^((?:modes|files|public)\/[^:\s]+|tests\.yml|preset\.yml|styles\.yml|description\.md):\s+/;

export function parseLintLine(line) {
	const raw = typeof line === 'string' ? line : '';
	const match = raw.match(LINT_LINE_RE);
	const level = match ? match[1].toLowerCase() : 'error';
	let message = match ? match[3] : raw;
	let file = 'preset.yml';
	const prefixed = message.match(FILE_PREFIX_RE);
	if (prefixed) {
		file = prefixed[1];
		message = message.slice(prefixed[0].length);
	}
	return { level, file, message, raw };
}

export function lintSummary(lint) {
	const errors = Array.isArray(lint?.errors) ? lint.errors.map(parseLintLine) : [];
	const warnings = Array.isArray(lint?.warnings) ? lint.warnings.map(parseLintLine) : [];
	const files = new Map();
	for (const issue of [...errors, ...warnings]) {
		if (!files.has(issue.file)) files.set(issue.file, []);
		files.get(issue.file).push(issue);
	}
	return {
		errors,
		warnings,
		files: [...files.entries()].map(([file, issues]) => ({ file, issues })),
		at: typeof lint?.at === 'string' ? lint.at : null,
		clean: errors.length === 0
	};
}

export function canPublish(lint) {
	return !!lint && Array.isArray(lint.errors) && lint.errors.length === 0;
}

export function slugify(value, fallback = 'Preset') {
	const slug = String(value ?? '')
		.normalize('NFKD')
		.replace(/[̀-ͯ]/g, '')
		.replace(/[^A-Za-z0-9._-]+/g, '-')
		.replace(/-{2,}/g, '-')
		.replace(/^[^A-Za-z0-9]+/, '')
		.replace(/[-._]+$/, '')
		.slice(0, 64);
	return SEGMENT_RE.test(slug) ? slug : fallback;
}

export function initialCopyForm(source) {
	return {
		from_id: source?.id ?? '',
		name: source ? `${source.name} (copy)` : '',
		preset_id: '',
		model_dir: source ? slugify(source.path.split('/')[0] || source.name) : '',
		variant_dir: 'custom'
	};
}

export function copyFormProblems(form, { sourceIds = [] } = {}) {
	const problems = {};
	const name = (form.name ?? '').trim();
	const presetId = (form.preset_id ?? '').trim();
	const modelDir = (form.model_dir ?? '').trim();
	const variantDir = (form.variant_dir ?? '').trim();
	if (!form.from_id) problems.from_id = 'Choose the preset to copy';
	else if (sourceIds.length && !sourceIds.includes(form.from_id)) problems.from_id = 'This preset is not in the catalogue';
	if (!name) problems.name = 'Give the preset a name';
	else if (name.length > MAX_NAME_LENGTH) problems.name = `At most ${MAX_NAME_LENGTH} characters`;
	if (presetId && !PRESET_ID_RE.test(presetId)) problems.preset_id = "3 to 64 letters, digits, '_' or '-'";
	if (!modelDir) problems.model_dir = 'Name the model folder';
	else if (!SEGMENT_RE.test(modelDir)) problems.model_dir = "Letters, digits, '.', '_' or '-', starting with a letter or a digit";
	if (variantDir && !SEGMENT_RE.test(variantDir)) problems.variant_dir = "Letters, digits, '.', '_' or '-', starting with a letter or a digit";
	return problems;
}

export function copyRequestBody(form) {
	const body = {
		mode: 'copy',
		from_id: form.from_id,
		name: form.name.trim(),
		model_dir: form.model_dir.trim()
	};
	const presetId = (form.preset_id ?? '').trim();
	const variantDir = (form.variant_dir ?? '').trim();
	if (presetId) body.preset_id = presetId;
	if (variantDir) body.variant_dir = variantDir;
	return body;
}

export function initialBlankForm() {
	return {
		name: '',
		preset_id: '',
		model_dir: '',
		variant_dir: 'custom',
		engine: 'native',
		category: '',
		driver: '',
		modes: 'txt2img',
		cloudModes: ['txt2img'],
		family: ''
	};
}

export function blankModes(form) {
	if (form.engine === 'cloud') return [...new Set((form.cloudModes ?? []).filter((mode) => CLOUD_MODES.includes(mode)))];
	return [...new Set(String(form.modes ?? '').split(/[\s,]+/).map((mode) => mode.trim()).filter(Boolean))];
}

export function blankFormProblems(form) {
	const problems = {};
	const name = (form.name ?? '').trim();
	const presetId = (form.preset_id ?? '').trim();
	const modelDir = (form.model_dir ?? '').trim();
	const variantDir = (form.variant_dir ?? '').trim();
	const engine = (form.engine ?? '').trim();
	const driver = (form.driver ?? '').trim();
	const modes = blankModes(form);
	if (!name) problems.name = 'Give the preset a name';
	else if (name.length > MAX_NAME_LENGTH) problems.name = `At most ${MAX_NAME_LENGTH} characters`;
	if (presetId && !PRESET_ID_RE.test(presetId)) problems.preset_id = "3 to 64 letters, digits, '_' or '-'";
	if (!modelDir) problems.model_dir = 'Name the model folder';
	else if (!SEGMENT_RE.test(modelDir)) problems.model_dir = "Letters, digits, '.', '_' or '-', starting with a letter or a digit";
	if (variantDir && !SEGMENT_RE.test(variantDir)) problems.variant_dir = "Letters, digits, '.', '_' or '-', starting with a letter or a digit";
	if (!ENGINE_RE.test(engine)) problems.engine = "Lowercase letters, digits and '_'";
	if (engine === 'cloud' && !driver) problems.driver = 'A cloud preset needs a driver, such as cloud.openrouter';
	if (driver && (!DRIVER_RE.test(driver) || !driver.startsWith(`${engine}.`))) problems.driver = `Looks like ${engine || '<engine>'}.<name>`;
	if (modes.length === 0) problems.modes = 'List at least one mode';
	else if (modes.length > MAX_MODES) problems.modes = `At most ${MAX_MODES} modes`;
	else if (modes.some((mode) => !MODE_RE.test(mode))) problems.modes = "A mode is lowercase letters, digits and '_', starting with a letter";
	if (form.category && !CATEGORIES.includes(form.category)) problems.category = 'Unknown category';
	return problems;
}

export function blankRequestBody(form, family = null) {
	const body = {
		mode: 'blank',
		name: form.name.trim(),
		model_dir: form.model_dir.trim(),
		engine: form.engine.trim(),
		modes: blankModes(form)
	};
	const presetId = (form.preset_id ?? '').trim();
	const variantDir = (form.variant_dir ?? '').trim();
	const driver = (form.driver ?? '').trim();
	if (presetId) body.preset_id = presetId;
	if (variantDir) body.variant_dir = variantDir;
	if (form.category) body.category = form.category;
	if (driver) body.driver = driver;
	if (family && body.engine !== 'cloud' && body.engine !== 'comfyui') body.family = family;
	return body;
}

export function targetDirOf(form) {
	const modelDir = (form.model_dir ?? '').trim();
	const variantDir = (form.variant_dir ?? '').trim();
	return variantDir ? `${modelDir}/${variantDir}` : modelDir;
}

export function describeSource(source) {
	const text = typeof source === 'string' ? source : '';
	const [kind, rest = ''] = text.split(/:(.*)/s);
	if (kind === 'copy_of') return `Copy of ${rest}`;
	if (kind === 'edit_of') return `Edit of ${rest}`;
	if (kind === 'restore_of') {
		const [id, stamp] = rest.split('@');
		return `Restored version of ${id}${stamp ? ` (${formatStamp(stamp)})` : ''}`;
	}
	return text || 'Draft';
}

export function formatStamp(stamp) {
	const match = typeof stamp === 'string' ? stamp.match(/^(\d{4})(\d{2})(\d{2})T(\d{2})(\d{2})(\d{2})/) : null;
	if (!match) return typeof stamp === 'string' ? stamp : '';
	const [, year, month, day, hour, minute, second] = match;
	return `${year}-${month}-${day} ${hour}:${minute}:${second} UTC`;
}

export function formatTimestamp(value) {
	if (typeof value !== 'string') return '';
	const date = new Date(value);
	if (Number.isNaN(date.getTime())) return value;
	return date.toLocaleString();
}
