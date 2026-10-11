// The download dialog's form: its starting values, the checks it runs before sending (the same
// rules as backend/downloads.py, so most mistakes are caught before the request), its warnings,
// and the body of `POST /downloads`. No Svelte in here: tested with `node --test`
// (see downloadForm.test.js).

import { allowedTypes, exceedsSizeLimit, sizeLimitBytes } from './capabilities.js';
import { formatBytes } from './format.js';

export const MAX_SUBDIR_LENGTH = 255;
export const MAX_FILENAME_LENGTH = 255;

// eslint-disable-next-line no-control-regex
const CONTROL = /[\u0000-\u001f\u007f]/;

/** The last segment of a source file name (Hugging Face names hold folders: `unet/x.safetensors`). */
export function baseName(name) {
	const text = typeof name === 'string' ? name : '';
	const parts = text.split(/[\\/]/).filter(Boolean);
	return parts.length ? parts[parts.length - 1] : '';
}

/** The extension of a file name, lower case with its dot ('.safetensors'), or ''. */
export function extensionOf(name) {
	const base = baseName(name);
	const dot = base.lastIndexOf('.');
	return dot > 0 ? base.slice(dot).toLowerCase() : '';
}

/**
 * Check a subfolder (relative to the type's folder). '' when it is fine, else why not.
 *
 * @param {string} text
 */
export function validateSubdir(text) {
	const value = typeof text === 'string' ? text.trim() : '';
	if (!value) return '';
	if (CONTROL.test(value) || value.includes('\\') || value.includes(':')) {
		return 'Separate folders with /; no backslash, colon or control character';
	}
	if (value.startsWith('/')) return 'The folder must be relative: remove the leading /';
	const segments = value.replace(/\/+$/, '').split('/');
	if (segments.some((segment) => ['', '.', '..'].includes(segment.trim()))) {
		return "No empty, '.' or '..' folder";
	}
	if (value.length > MAX_SUBDIR_LENGTH) return `At most ${MAX_SUBDIR_LENGTH} characters`;
	return '';
}

/** The subfolder as sent: trimmed, without trailing slashes. */
export function cleanSubdir(text) {
	return (typeof text === 'string' ? text.trim() : '').replace(/\/+$/, '');
}

/**
 * Check a file name typed in the dialog against the source file's name. '' when fine.
 *
 * @param {string} text
 * @param {string} original  The source file name (may hold folders).
 */
export function validateFilename(text, original) {
	const value = typeof text === 'string' ? text.trim() : '';
	if (!value || value === '.' || value === '..') return 'Enter a file name';
	if (value.includes('/') || value.includes('\\') || value.includes(':') || CONTROL.test(value)) {
		return 'A plain file name: no folder, colon or control character';
	}
	const wanted = extensionOf(original);
	if (wanted && extensionOf(value) !== wanted) return `Keep the ${wanted} extension`;
	if (value.length > MAX_FILENAME_LENGTH) return `At most ${MAX_FILENAME_LENGTH} characters`;
	return '';
}

/** Whether the user changed the file name (it is only sent then). */
export function filenameEdited(text, original) {
	return (typeof text === 'string' ? text.trim() : '') !== baseName(original);
}

/** Why the file is too large for the user, or ''. */
export function sizeProblem(me, sizeBytes) {
	if (!exceedsSizeLimit(me, sizeBytes)) return '';
	const limitGb = sizeLimitBytes(me) / 1024 ** 3;
	return `This file is ${formatBytes(sizeBytes)}: your permissions allow files of at most ${limitGb} GB`;
}

/**
 * The form's starting values.
 *
 * @returns {{ modelType: string, subdir: string, filename: string, destination: string, group: string }}
 */
export function initialForm(me, detail, file) {
	return {
		modelType: allowedTypes(me, detail?.mb_type).selected,
		subdir: '',
		filename: baseName(file?.name),
		destination: '',
		group: ''
	};
}

/**
 * What stops the form from being sent, per field ('' when nothing): the model type, the
 * subfolder, the file name and the size.
 */
export function formProblems(form, { me, detail, file }) {
	const { types } = allowedTypes(me, detail?.mb_type);
	let modelType = '';
	if (!form.modelType) modelType = 'Choose what to file this model as';
	else if (!types.includes(form.modelType)) modelType = 'Your permissions do not allow this model type';
	return {
		modelType,
		subdir: validateSubdir(form.subdir),
		filename: filenameEdited(form.filename, file?.name) ? validateFilename(form.filename, file?.name) : '',
		size: sizeProblem(me, file?.size_bytes)
	};
}

/** Whether `formProblems` found nothing. */
export function canSubmit(problems) {
	return Object.values(problems).every((problem) => !problem);
}

/**
 * The body of `POST /downloads`: the ids, and only what the user chose (the file name only when
 * edited, no empty field).
 */
export function buildDownloadBody({ detail, version, file, form }) {
	const body = {
		source: detail.source,
		model_id: String(detail.id),
		version_id: String(version.id),
		file_id: String(file.id)
	};
	if (form.modelType) body.model_type = form.modelType;
	const subdir = cleanSubdir(form.subdir);
	if (subdir) body.subdir = subdir;
	if (filenameEdited(form.filename, file.name)) body.filename = form.filename.trim();
	if (form.destination) body.destination_backend_id = form.destination;
	if (form.group) body.assign_group_id = form.group;
	return body;
}

/**
 * Warnings shown before confirming: early access, a login the source needs, a licence that
 * restricts use.
 *
 * @returns {{ tone: 'warning' | 'info', title: string, text: string }[]}
 */
export function downloadWarnings({ detail, version, file }) {
	const warnings = [];
	if (version?.early_access) {
		warnings.push({
			tone: 'warning',
			title: 'Early access',
			text: 'This version is in early access on the source: the download fails unless the source account used by the server has access.'
		});
	}
	if (detail?.gated && file?.auth_provider_id) {
		warnings.push({
			tone: 'warning',
			title: 'Needs a login',
			text: 'The source only serves this file to signed-in accounts that accepted its terms: the server uses the provider plugin’s credentials.'
		});
	}
	const license = detail?.license;
	if (license && Array.isArray(license.commercial_use) && license.commercial_use.length === 0) {
		warnings.push({ tone: 'info', title: 'No commercial use', text: 'The licence does not allow commercial use of this model.' });
	}
	return warnings;
}

/**
 * The licence flags as short lines ('Commercial use: Image, Rent', 'Credit required', ...).
 *
 * @param {any} license  `{summary, commercial_use, no_credit, derivatives, different_license, url}` or null.
 * @returns {string[]}
 */
export function licenseFlags(license) {
	if (!license || typeof license !== 'object') return [];
	const flags = [];
	if (Array.isArray(license.commercial_use)) {
		flags.push(license.commercial_use.length ? `Commercial use: ${license.commercial_use.join(', ')}` : 'No commercial use');
	}
	if (license.no_credit === true) flags.push('No credit required');
	if (license.no_credit === false) flags.push('Credit required');
	if (license.derivatives === true) flags.push('Derivatives allowed');
	if (license.derivatives === false) flags.push('No derivatives');
	if (license.different_license === true) flags.push('Derivatives may use another licence');
	if (license.different_license === false) flags.push('Derivatives keep this licence');
	return flags;
}
