import { t } from '../i18n/index.svelte.js';
import { doc, act, toast, clipLabel } from './state.svelte.js';
import { project, getClient, flushSave, projectGone } from './project.svelte.js';
import { takeStore } from './takes.svelte.js';
import { frameAsset, stillAsset } from './chain.js';
import { frameErrorText } from './seam.js';
import { draftChained, inPlace, neighborSources, sidesOf } from './shotimages.js';

export const shotImages = $state({ busy: false });

export const neighborsOf = (clip, draft) => neighborSources(doc, clip, draft, takeStore.list);

const sameSource = (a, b) => a && b && a.shotId === b.shotId && a.assetId === b.assetId && a.at === b.at;

async function taken(side, source, name) {
	if (source.at === null) {
		const kept = doc.assets.find((a) => a.kind === 'image' && sameSource(a.frameOf, source));
		return kept ?? stillAsset(doc, source, name);
	}
	if (!(await flushSave()) || !project.id) {
		toast(t('lib.seam.saveFirst'), 'error');
		return null;
	}
	const projectId = project.id;
	const result = await getClient()[side === 'previous' ? 'endFrame' : 'startFrame'](projectId, source.shotId);
	if (projectId !== project.id) return null;
	if (result.ok) return frameAsset(result.data.media, result.data.source, name);
	if (result.error.code === 'project_not_found') projectGone(projectId);
	else toast(frameErrorText(result.error, t, { noMedia: t('keyframes.retrieve.error.noMedia') }), result.error.status === 409 ? 'warning' : 'error');
	return null;
}

function keep(asset) {
	if (!doc.assets.some((a) => a.id === asset.id)) act(() => doc.assets.push(asset));
	return asset.id;
}

async function fromPrevious(source, draft) {
	const names = { shot: clipLabel(source.shot) };
	if (source.state === 'pending') {
		draft.first = null;
		if (!draftChained(doc, draft)) draft.firstFromPrevious = true;
		return t('keyframes.retrieve.linked', names);
	}
	const asset = await taken('previous', source.source, t('lib.chain.assetName', names));
	if (!asset) return null;
	draft.first = keep(asset);
	if (!draftChained(doc, draft)) draft.firstFromPrevious = true;
	return t('keyframes.retrieve.tookPrevious', names);
}

async function fromNext(source, draft) {
	const names = { shot: clipLabel(source.shot) };
	if (source.image) {
		draft.last = source.image.id;
		return t('keyframes.retrieve.tookNextStart', names);
	}
	const asset = await taken('next', source.source, t('keyframes.retrieve.assetName', names));
	if (!asset) return null;
	draft.last = keep(asset);
	return t('keyframes.retrieve.tookNext', names);
}

export async function retrieveImages(clip, draft, choice) {
	if (shotImages.busy || !clip) return;
	shotImages.busy = true;
	try {
		const sources = neighborsOf(clip, draft);
		const said = [];
		for (const side of sidesOf(choice).filter((x) => !inPlace(sources[x]))) {
			const text = side === 'previous' ? await fromPrevious(sources.previous, draft) : await fromNext(sources.next, draft);
			if (!text) return;
			said.push(text);
		}
		if (said.length) toast(said.join(' · '), 'success');
	} finally {
		shotImages.busy = false;
	}
}
