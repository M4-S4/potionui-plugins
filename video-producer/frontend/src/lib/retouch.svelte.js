import { formatNumber, t } from '../i18n/index.svelte.js';
import { ui, toast, clipAt, selected } from './state.svelte.js';
import { getClient } from './project.svelte.js';
import { findTake, sendRetouch } from './production.svelte.js';
import { REFINE, REMIX, blockReason, canRetouch, initialRange, moveEdge, offerOf, retouchBody } from './retouch.js';

export const retouch = $state({
	takeId: null,
	task: REFINE,
	presetId: null,
	range: null,
	strength: 'balanced',
	faces: true,
	hands: true,
	prompt: '',
	time: 0,
	busy: false,
	offers: null
});

export const retouchTake = () => (retouch.takeId ? findTake(retouch.takeId) : null);

export const retouchOffer = () => offerOf(retouch.offers, retouch.task);

export async function loadOffers() {
	const result = await getClient().retouchOffers();
	retouch.offers = result.ok ? result.data : [];
}

function pickEngine() {
	const engines = retouchOffer()?.engines ?? [];
	if (!engines.some((engine) => engine.presetId === retouch.presetId)) retouch.presetId = engines[0]?.presetId ?? null;
}

export function openRetouch(take, at = null) {
	if (!canRetouch(take)) return toast(t('generation.retouch.notDone'), 'warning');
	retouch.takeId = take.id;
	retouch.range = initialRange(take, at);
	retouch.time = retouch.range.start;
	retouch.prompt = '';
	ui.compare = null;
	ui.preview = { kind: 'result', id: take.id };
	loadOffers().then(pickEngine);
}

export function retouchCurrent() {
	const previewed = ui.preview?.kind === 'result' ? findTake(ui.preview.id) : null;
	const clip = ui.selection?.kind === 'clip' ? selected() : clipAt(ui.playhead);
	const take = previewed ?? (clip?.take ? findTake(clip.take) : null);
	if (!take) return toast(t('generation.retouch.pickTake'), 'warning');
	openRetouch(take);
}

export function closeRetouch() {
	retouch.takeId = null;
	retouch.range = null;
	retouch.busy = false;
}

export const retouchOpen = () => Boolean(retouch.takeId && retouch.range && ui.preview?.kind === 'result' && ui.preview.id === retouch.takeId);

export function setTask(task) {
	retouch.task = task === REMIX ? REMIX : REFINE;
	pickEngine();
}

export function setEdge(edge, time = retouch.time) {
	const take = retouchTake();
	if (!take || !retouch.range) return;
	retouch.range = moveEdge(take, retouch.range, edge, time);
}

export function retouchBlock() {
	return blockReason(retouch, retouchTake(), retouchOffer());
}

export function blockText(reason) {
	const offer = retouchOffer();
	if (reason === 'takeNotDone') return t('generation.retouch.notDone');
	if (reason === 'loading') return t('generation.retouch.loading');
	if (reason === 'engineMissing') return t('generation.retouch.engineMissing');
	if (reason === 'detectorMissing') return t('generation.retouch.detectorMissing', { files: (offer?.missing ?? []).join(', ') });
	if (reason === 'nothingToRefine') return t('generation.retouch.nothingToRefine');
	if (reason === 'promptRequired') return t('generation.retouch.promptRequired');
	if (reason === 'tooShort') return t('generation.retouch.tooShort', { seconds: offer?.minS ?? 0 });
	if (reason === 'tooLong') return t('generation.retouch.tooLong', { seconds: offer?.maxS ?? 0 });
	return '';
}

export async function startRetouch() {
	const take = retouchTake();
	if (!take || retouch.busy || retouchBlock()) return null;
	retouch.busy = true;
	const made = await sendRetouch(take.id, retouchBody(retouch));
	retouch.busy = false;
	if (!made) return null;
	toast(t('generation.retouch.started', { source: take.variant, variant: made.variant }), 'success');
	closeRetouch();
	return made;
}

export function compareRetouch(take) {
	const source = take?.parentTakeId ? findTake(take.parentTakeId) : null;
	if (!source) return;
	ui.preview = null;
	ui.compare = [source.id, take.id];
}

export const rangeSecs = (value) => `${formatNumber(+(value ?? 0), { minimumFractionDigits: 2, maximumFractionDigits: 2 })} s`;
