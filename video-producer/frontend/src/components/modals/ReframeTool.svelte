<script>
	import { untrack } from 'svelte';
	import HostUi from '../../../../../../sdk/HostUi.svelte';
	import { formatNumber, t } from '../../i18n/index.svelte.js';
	import { ui, doc, asset, clipLabel, secs } from '../../lib/state.svelte.js';
	import { sceneLabel } from '../../lib/catalog.js';
	import { assetThumb } from '../../lib/media.js';
	import { pickImage } from '../../lib/importer.js';
	import { framesOf } from '../../lib/seam.js';
	import { hostIconName } from '../../lib/icons.js';
	import {
		sceneState,
		shownScenes,
		sceneOf,
		sceneFor,
		sceneReady,
		sceneBusy,
		sceneLocked,
		sourceOf,
		freeCamera,
		moveCamera,
		resetToSource,
		pickScene,
		createSceneFromImage,
		takeCapture,
		storeCaptures
	} from '../../lib/scene.svelte.js';
	import { FOCAL_RANGE, ROLL_RANGE, lowestFocal } from '../../lib/scene3d/camera.js';
	import Modal from './Modal.svelte';
	import Icon from '../Icon.svelte';
	import SceneViewer from '../scene/SceneViewer.svelte';
	import SliderField from '../inspector/SliderField.svelte';

	let { id, returnTo = null } = $props();

	const clip = $derived(doc.clips.find((c) => c.id === id) ?? null);
	const draft = untrack(() => returnTo?.draft ?? null);
	const startFrame = $derived(framesOf(doc, id, 'first').find((f) => f.assetId) ?? null);
	const startImage = $derived(draft ? draft.first : (startFrame?.assetId ?? null));
	const startSceneId = $derived(draft?.captures?.[startImage] ?? (startFrame?.assetId === startImage ? startFrame?.sceneId : null) ?? null);
	const startScene = $derived(sceneOf(startSceneId) ?? sceneFor(startImage));
	const scenes = $derived(shownScenes());
	const images = $derived(doc.assets.filter((a) => a.kind === 'image' && a.src));

	let source = $state(untrack(() => (startImage ? 'start' : scenes.length ? 'scene' : 'image')));
	let picked = $state(untrack(() => images[0]?.id ?? null));
	let chosen = $state(untrack(() => scenes[0]?.id ?? null));
	let shots = $state({ first: null, last: null });
	let taking = $state(null);
	ui.scene.seeded = null;

	const sources = $derived([
		{ id: 'start', label: t('modals.reframe.fromStart'), disabled: !startImage },
		{ id: 'image', label: t('modals.reframe.fromImage') },
		{ id: 'scene', label: t('modals.reframe.fromScene'), disabled: !scenes.length }
	]);
	const imageId = $derived(source === 'start' ? startImage : source === 'image' ? picked : null);
	const scene = $derived(source === 'scene' ? sceneOf(chosen) : source === 'start' ? startScene : sceneFor(picked));
	const ready = $derived(sceneReady(scene) && sceneState.loadedId === scene?.id && sceneState.status === 'ready');
	const locked = $derived(sceneLocked() || sceneState.saving);
	const origin = $derived(scene ? sourceOf(scene) : null);
	const cam = $derived(freeCamera());
	const placing = $derived(['first', 'last'].filter((usage) => shots[usage]));

	$effect(() => {
		const next = scene?.id ?? null;
		untrack(() => pickScene(next));
	});

	function build() {
		const image = asset(imageId);
		if (!image || locked) return;
		createSceneFromImage({ assetId: image.id, name: image.name });
	}

	function fromLibrary() {
		pickImage(t('modals.reframe.pickTitle'), (assetId) => {
			picked = assetId;
			source = 'image';
		});
	}

	async function take(usage) {
		if (!ready || locked) return;
		taking = usage;
		const shot = await takeCapture(scene);
		taking = null;
		if (shot) shots[usage] = shot;
	}

	const back = () => (ui.modal = returnTo ?? null);

	async function place() {
		const stored = await storeCaptures(id, $state.snapshot(shots), !returnTo);
		if (!stored) return;
		if (!returnTo) return (ui.modal = null);
		const next = { ...returnTo.draft, captures: { ...(returnTo.draft.captures ?? {}) } };
		for (const { usage, sceneId, image } of stored) {
			next[usage] = image.id;
			next.captures[image.id] = sceneId;
		}
		ui.modal = { ...returnTo, draft: next };
	}

	const empty = (shot) => (shot?.coverage == null ? 0 : Math.max(0, 1 - shot.coverage));
	const percent = (v) => formatNumber(v * 100, { maximumFractionDigits: 1 });
</script>

{#if clip}
	<Modal title={t('modals.reframe.title')} subtitle={t('modals.reframe.subtitle', { shot: clipLabel(clip), start: secs(clip.start), end: secs(clip.start + clip.dur) })} icon="cube" width={1000} onclose={back}>
		<div class="grid gap-4 p-4" style:grid-template-columns="260px minmax(0, 1fr)">
			<div class="min-w-0 space-y-4">
				<section class="space-y-2">
					<div class="vp-section-title">{t('modals.reframe.source')}</div>
					<div class="flex flex-col gap-1" role="radiogroup" aria-label={t('modals.reframe.source')}>
						{#each sources as s (s.id)}
							<label class="flex items-center gap-2 text-sm {s.disabled ? 'text-fg-subtle' : ''}">
								<input type="radio" name="reframe-source" value={s.id} checked={source === s.id} disabled={s.disabled || locked} onchange={() => (source = s.id)} />
								{s.label}
							</label>
						{/each}
					</div>
					{#if source === 'start'}
						{#if startImage && assetThumb(asset(startImage))}<img src={assetThumb(asset(startImage))} alt="" class="aspect-video w-full rounded border border-line-strong object-cover" />{/if}
					{:else if source === 'image'}
						{#if images.length}
							<div class="grid max-h-36 grid-cols-3 gap-1 overflow-auto" role="radiogroup" aria-label={t('modals.reframe.fromImage')}>
								{#each images as a (a.id)}
									<button type="button" role="radio" aria-checked={picked === a.id} aria-label={a.name} title={a.name} disabled={locked} class="block overflow-hidden rounded border {picked === a.id ? 'border-signal ring-1 ring-signal' : 'border-line-strong hover:border-line-hover'}" onclick={() => (picked = a.id)}>
										<img src={assetThumb(a)} alt="" class="aspect-video w-full object-cover" />
									</button>
								{/each}
							</div>
						{:else}
							<p class="text-xs text-fg-subtle">{t('modals.reframe.noImage')}</p>
						{/if}
						<HostUi name="Button" props={{ variant: 'ghost', size: 'xs', icon: 'folder', disabled: locked, onclick: fromLibrary }}>{t('modals.reframe.pick')}</HostUi>
					{:else}
						<ul class="max-h-40 space-y-1 overflow-auto" role="radiogroup" aria-label={t('modals.reframe.fromScene')}>
							{#each scenes as s (s.id)}
								{@const thumb = s.kind === 'splat' ? assetThumb(asset(s.sourceAssetId)) : null}
								<li>
									<button type="button" role="radio" aria-checked={chosen === s.id} disabled={locked} class="flex w-full items-center gap-2 rounded-lg border p-1 text-left {chosen === s.id ? 'border-signal ring-1 ring-signal' : 'border-line-strong hover:border-line-hover'}" onclick={() => (chosen = s.id)}>
										{#if thumb}<img src={thumb} alt="" class="h-7 w-12 shrink-0 rounded object-cover" />{:else}<span class="flex h-7 w-12 shrink-0 items-center justify-center rounded bg-surface-3"><Icon name="cube" class="h-3.5 w-3.5 text-fg-muted" /></span>{/if}
										<span class="min-w-0 flex-1">
											<span class="block truncate text-xs">{s.name}</span>
											<span class="block truncate text-2xs text-fg-subtle">{sceneLabel(s)}</span>
										</span>
									</button>
								</li>
							{/each}
						</ul>
					{/if}
					{#if imageId && !scene}
						<div class="space-y-1.5 rounded-lg border border-dashed border-line-hover p-2">
							<p class="text-xs text-fg-muted">{t('modals.reframe.buildHint')}</p>
							<HostUi name="Button" props={{ variant: 'secondary', size: 'sm', icon: 'cube', class: 'w-full', disabled: locked, onclick: build }}>{t('modals.reframe.build')}</HostUi>
						</div>
					{:else if scene && imageId && source !== 'scene'}
						<p class="flex gap-1.5 text-xs text-fg-subtle"><Icon name="check" class="mt-px h-3.5 w-3.5 shrink-0" />{sceneBusy(scene) ? t('modals.reframe.building') : t('modals.reframe.reused', { scene: scene.name })}</p>
					{/if}
				</section>

				<section class="space-y-2">
					<div class="vp-section-title">{t('modals.reframe.frame')}</div>
					<SliderField label={t('modals.reframe.focal')} value={cam.focal} min={lowestFocal(scene, origin)} max={FOCAL_RANGE[1]} step={1} unit=" mm" onchange={(v) => moveCamera(scene, { ...freeCamera(), focal: v })} />
					<SliderField label={t('modals.reframe.roll')} value={cam.roll ?? 0} min={ROLL_RANGE[0]} max={ROLL_RANGE[1]} step={1} unit="°" onchange={(v) => moveCamera(scene, { ...freeCamera(), roll: v })} />
					<HostUi name="Button" props={{ variant: 'ghost', size: 'xs', icon: hostIconName('target'), class: 'w-full', disabled: !ready, onclick: () => resetToSource(scene) }}>{t('scene.sourceView')}</HostUi>
					<p class="text-xs text-fg-subtle">{t('modals.reframe.bounds')}</p>
				</section>
			</div>

			<div class="min-w-0 space-y-3">
				<div class="overflow-hidden rounded-lg border border-line-strong" style:height="380px">
					{#if scene || !asset(imageId)?.src}
						<SceneViewer {scene} />
					{:else}
						<img src={asset(imageId).src} alt="" class="h-full w-full bg-black object-contain" />
					{/if}
				</div>
				<p class="truncate text-xs text-fg-subtle">{t('scene.hint')}</p>
				<div class="grid grid-cols-2 gap-3">
					{#each ['first', 'last'] as usage (usage)}
						{@const shot = shots[usage]}
						<div class="space-y-1.5">
							<div class="flex items-center justify-between gap-2">
								<span class="vp-label">{usage === 'first' ? t('modals.reframe.first') : t('modals.reframe.last')}</span>
								{#if shot}<HostUi name="IconButton" props={{ icon: hostIconName('x'), label: t('modals.reframe.clear'), tooltip: t('modals.reframe.clear'), size: 'xs', disabled: locked, onclick: () => (shots[usage] = null) }} />{/if}
							</div>
							<div class="relative overflow-hidden rounded-md border border-line-strong bg-surface-3" style:aspect-ratio={shot ? `${shot.width} / ${shot.height}` : '16 / 9'}>
								{#if shot}
									<img src={shot.url} alt={usage === 'first' ? t('modals.reframe.first') : t('modals.reframe.last')} class="h-full w-full object-contain" />
								{:else if taking === usage}
									<span class="absolute inset-0 flex items-center justify-center"><HostUi name="Spinner" props={{ size: 'sm' }} /></span>
								{:else}
									<span class="absolute inset-0 flex items-center justify-center text-2xs text-fg-subtle">{t('modals.reframe.none')}</span>
								{/if}
							</div>
							{#if shot && empty(shot) > 0.005}
								<p class="text-xs {empty(shot) > 0.03 ? 'text-warning' : 'text-fg-subtle'}">{t('modals.reframe.empty', { value: percent(empty(shot)) })}</p>
							{/if}
							<HostUi name="Button" props={{ variant: 'secondary', size: 'xs', icon: 'camera', class: 'w-full', disabled: !ready || locked, onclick: () => take(usage) }}>{usage === 'first' ? t('modals.reframe.takeFirst') : t('modals.reframe.takeLast')}</HostUi>
						</div>
					{/each}
				</div>
			</div>
		</div>
		{#snippet footer()}
			<span class="mr-auto text-xs text-fg-subtle">{returnTo ? t('modals.reframe.toDraft') : t('modals.reframe.toShot')}</span>
			<HostUi name="Button" props={{ variant: 'secondary', size: 'sm', onclick: back }}>{t('modals.reframe.cancel')}</HostUi>
			<HostUi name="Button" props={{ variant: 'primary', size: 'sm', icon: 'check', disabled: !placing.length || locked, onclick: place }}>{sceneState.saving ? t('modals.reframe.saving') : t('modals.reframe.place')}</HostUi>
		{/snippet}
	</Modal>
{/if}
