import { t } from '../i18n/index.svelte.js';
import { ui, doc, act, toast, undo, asset, selected } from './state.svelte.js';
import { confirm } from './host.js';
import { releaseTake } from './production.svelte.js';
import { USE_KINDS, assetUses, removeAsset } from './usage.js';

function useText(kind, count) {
	if (kind === 'shots') return t('lib.media.use.shots', { count });
	if (kind === 'sounds') return t('lib.media.use.sounds', { count });
	if (kind === 'references') return t('lib.media.use.references', { count });
	if (kind === 'edges') return t('lib.media.use.edges', { count });
	return t('lib.media.use.frames', { count });
}

function deleteText(a, uses) {
	const listed = USE_KINDS.filter((kind) => uses[kind].length)
		.map((kind) => useText(kind, uses[kind].length))
		.join(t('lib.media.useSeparator'));
	const message = listed ? t('lib.media.deleteUsed', { name: a.name, uses: listed }) : t('lib.media.deleteUnused', { name: a.name });
	return a.generated ? `${message} ${t('lib.media.deleteTake')}` : message;
}

let confirming = false;

export async function deleteAsset(id) {
	const a = asset(id);
	if (!a || confirming) return false;
	const name = a.name;
	confirming = true;
	let ok = false;
	try {
		ok = await confirm({ title: t('lib.media.deleteTitle', { name }), message: deleteText(a, assetUses(doc, id)), variant: 'danger', confirmLabel: t('lib.media.deleteConfirm') });
	} finally {
		confirming = false;
	}
	if (!ok || !asset(id)) return false;
	let removed = null;
	act(() => (removed = removeAsset(doc, id)));
	for (const released of removed.released) releaseTake(released);
	if (ui.preview?.kind === 'asset' && ui.preview.id === id) ui.preview = null;
	if (ui.selection && !selected()) ui.selection = null;
	toast(t('lib.toast.mediaRemoved', { name }), 'info', { label: t('shell.toast.undo'), run: undo });
	return true;
}
