<script>
	import HostUi from '../../../../../../sdk/HostUi.svelte';
	import { formatNumber, t } from '../../i18n/index.svelte.js';
	import { ui, doc, asset, secs, shotNumber } from '../../lib/state.svelte.js';
	import { SENSITIVITY, SHORTEST, bounded, cuttable } from '../../lib/cuts.js';
	import { cancelCuts, clearCuts, cutFailureText, cuts, findCuts } from '../../lib/cuts.svelte.js';
	import { pickLocalMedia, pickMedia } from '../../lib/importer.js';
	import Modal from './Modal.svelte';

	let { assetId = null, settings = null } = $props();

	let chosen = $state(assetId);
	let sensitivity = $state(settings?.sensitivity ?? SENSITIVITY.value);
	let shortest = $state(settings?.shortest ?? SHORTEST.value);
	let mode = $state(settings?.mode ?? 'source');
	let at = $state(settings?.at ?? 'end');

	const videos = $derived(doc.assets.filter(cuttable));
	const source = $derived(asset(chosen));
	const ready = $derived(cuttable(source));
	const running = $derived(cuts.status === 'running');
	const selectedClip = $derived(ui.selection?.kind === 'clip' ? (doc.clips.find((c) => c.id === ui.selection.id) ?? null) : null);
	const place = $derived(selectedClip ? at : 'end');
	const modes = $derived([
		{ id: 'source', label: t('project.cuts.mode.source') },
		{ id: 'motion', label: t('project.cuts.mode.motion') }
	]);
	const places = $derived([{ id: 'end', label: t('project.cuts.place.end') }, ...(selectedClip ? [{ id: 'after', label: t('project.cuts.place.after', { shot: shotNumber(selectedClip) }) }] : [])]);
	const percent = $derived(Math.round(cuts.progress * 100));
	const failure = $derived(cuts.status === 'failed' ? cuts.failure : null);

	clearCuts();

	const current = () => ({ sensitivity, shortest, mode, at });
	const reopen = (id) => (ui.modal = { type: 'cuts', assetId: id, settings: current() });

	function fromLibrary() {
		const keep = chosen;
		ui.modal = null;
		setTimeout(() => pickMedia('video', t('project.cuts.pickTitle'), reopen, () => reopen(keep)));
	}

	function fromComputer() {
		const keep = chosen;
		ui.modal = null;
		setTimeout(() => pickLocalMedia('video', reopen, () => reopen(keep)));
	}

	function close() {
		if (running) cancelCuts();
		ui.modal = null;
	}

	async function start() {
		if (!ready || running) return;
		const done = await findCuts({ assetId: chosen, sensitivity: bounded(sensitivity, SENSITIVITY), shortest: bounded(shortest, SHORTEST), mode, at: place });
		if (done && ui.modal?.type === 'cuts') ui.modal = null;
	}

	const seconds = (v) => formatNumber(v, { maximumFractionDigits: 1 });
</script>

<Modal title={t('project.cuts.title')} subtitle={t('project.cuts.subtitle')} icon="film" width={520} onclose={close}>
	<div class="space-y-4 p-4" data-cut-import>
		<section class="space-y-1.5">
			<label class="vp-label block" for="vp-cuts-video">{t('project.cuts.video')}</label>
			{#if videos.length}
				<select id="vp-cuts-video" class="input vp-dense w-full" value={ready ? chosen : ''} disabled={running} onchange={(e) => (chosen = e.currentTarget.value || null)}>
					<option value="" disabled>{t('project.cuts.videoNone')}</option>
					{#each videos as v (v.id)}<option value={v.id}>{v.srcDur ? t('project.cuts.videoOption', { name: v.name, duration: secs(v.srcDur) }) : v.name}</option>{/each}
				</select>
			{:else}
				<p id="vp-cuts-video" class="text-xs text-fg-subtle">{t('project.cuts.videoEmpty')}</p>
			{/if}
			<div class="flex gap-1.5">
				<HostUi name="Button" props={{ variant: 'secondary', size: 'sm', icon: 'folder', class: 'flex-1', disabled: running, onclick: fromLibrary }}>{t('project.cuts.fromLibrary')}</HostUi>
				<HostUi name="Button" props={{ variant: 'ghost', size: 'sm', icon: 'upload', class: 'flex-1', disabled: running, onclick: fromComputer }}>{t('project.cuts.fromComputer')}</HostUi>
			</div>
		</section>

		<section class="grid grid-cols-2 gap-3">
			<label class="space-y-1">
				<span class="vp-label block">{t('project.cuts.sensitivity')}</span>
				<span class="flex items-center gap-2">
					<input class="vp-slider min-w-0 flex-1" type="range" min={SENSITIVITY.min} max={SENSITIVITY.max} step={SENSITIVITY.step} bind:value={sensitivity} disabled={running} aria-label={t('project.cuts.sensitivity')} />
					<span class="vp-tc w-8 text-right text-xs text-fg-muted">{sensitivity}</span>
				</span>
				<span class="block text-xs text-fg-subtle">{t('project.cuts.sensitivityHelp')}</span>
			</label>
			<label class="space-y-1">
				<span class="vp-label block">{t('project.cuts.shortest')}</span>
				<span class="flex items-center gap-2">
					<input class="input vp-dense vp-tc w-20" type="number" min={SHORTEST.min} max={SHORTEST.max} step={SHORTEST.step} bind:value={shortest} disabled={running} onchange={() => (shortest = bounded(shortest, SHORTEST))} />
					<span class="text-xs text-fg-muted">{t('project.cuts.secondsUnit')}</span>
				</span>
				<span class="block text-xs text-fg-subtle">{t('project.cuts.shortestHelp', { min: seconds(SHORTEST.min), max: seconds(SHORTEST.max) })}</span>
			</label>
		</section>

		<section class="space-y-1">
			<div class="flex items-center justify-between gap-3">
				<span class="vp-label">{t('project.cuts.becomes')}</span>
				<HostUi name="SegmentedControl" props={{ items: modes, selected: mode, onSelect: (id) => !running && (mode = id), ariaLabel: t('project.cuts.becomes'), variant: 'toggle' }} />
			</div>
			<p class="text-xs text-fg-subtle" data-cut-mode={mode}>{mode === 'motion' ? t('project.cuts.mode.motionHelp') : t('project.cuts.mode.sourceHelp')}</p>
		</section>

		<section class="space-y-1">
			<div class="flex items-center justify-between gap-3">
				<span class="vp-label">{t('project.cuts.place')}</span>
				<HostUi name="SegmentedControl" props={{ items: places, selected: place, onSelect: (id) => !running && (at = id), ariaLabel: t('project.cuts.place'), variant: 'toggle' }} />
			</div>
			<p class="text-xs text-fg-subtle">{t('project.cuts.libraryNote')}</p>
		</section>

		{#if running}
			<section class="space-y-1" aria-live="polite">
				<p class="text-xs text-fg-muted">{t('project.cuts.running', { percent })}</p>
				<div class="h-1 overflow-hidden rounded-full bg-surface-3" role="progressbar" aria-label={t('project.cuts.progress')} aria-valuemin="0" aria-valuemax="100" aria-valuenow={percent}>
					<div class="h-full bg-signal" style:width="{percent}%"></div>
				</div>
			</section>
		{:else if failure}
			<p class="text-xs text-warning" role="alert" data-cut-failure={failure}>{cutFailureText(failure, cuts.message)}</p>
		{:else if !ready}
			<p class="text-xs text-fg-subtle">{t('project.cuts.needVideo')}</p>
		{/if}
	</div>
	{#snippet footer()}
		<HostUi name="Button" props={{ variant: 'ghost', size: 'sm', onclick: running ? cancelCuts : close }}>{running ? t('project.cuts.stop') : t('project.cuts.cancel')}</HostUi>
		<HostUi name="Button" props={{ variant: 'primary', size: 'sm', icon: 'scissors', disabled: !ready || running, onclick: start }}>{t('project.cuts.start')}</HostUi>
	{/snippet}
</Modal>
