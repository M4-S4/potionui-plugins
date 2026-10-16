<script>
	import { onDestroy } from 'svelte';
	import HostUi from '../../../../../../sdk/HostUi.svelte';
	import { getLocale, t } from '../../i18n/index.svelte.js';
	import { ui, doc, assets, act, toast, productionRange, secs, round } from '../../lib/state.svelte.js';
	import { audition } from '../../lib/playback.svelte.js';
	import { audioRoleLabel } from '../../lib/catalog.js';
	import { chat } from '../../lib/host.js';
	import { hostIconName } from '../../lib/icons.js';
	import { ulid } from '../../lib/ulid.js';
	import Modal from './Modal.svelte';
	import Icon from '../Icon.svelte';

	let { type: initialType = 'Ambiance' } = $props();
	const types = ['Ambiance', 'Bruitage', 'Texture', 'Impact', 'Musique', 'Voix'];
	const presets = {
		Ambiance: ['windAlpine', 'woodsDusk', 'hutFire'],
		Bruitage: ['gravelSteps', 'backpackRub', 'woodDoor'],
		Texture: ['grainyBreath', 'lowDrone', 'shimmer'],
		Impact: ['dullHit', 'iceCrack', 'cutBreath'],
		Musique: ['etherealPad', 'sparsePiano', 'heldStrings'],
		Voix: ['line', 'voiceOver', 'murmur', 'breath']
	};
	const roleFor = { Ambiance: 'Ambiance', Bruitage: 'SFX', Texture: 'Ambiance', Impact: 'SFX', Musique: 'Musique', Voix: 'Dialogue' };
	const synthFor = { Ambiance: 'wind', Bruitage: 'steps', Texture: 'wind', Impact: 'steps', Musique: 'pad', Voix: 'voice' };
	const emotions = ['contemplation', 'tension', 'mystery', 'joy', 'melancholy'];
	const timbres = ['soft', 'deep', 'breathless', 'whisper'];
	const intents = ['intensity', 'rhythm', 'space'];

	function firstType() {
		return types.includes(initialType) ? initialType : 'Ambiance';
	}

	function identityName() {
		const ref = doc.references.find((r) => r.role === 'Identité' && r.type === 'Personnage');
		return ref?.name ? ref.name.split(/\s+[—–-]\s+/)[0].trim() : '';
	}

	const lead = identityName();
	const characters = $derived([lead, t('modals.sound.narrator'), t('modals.sound.supporting')].filter(Boolean));

	let type = $state(firstType());
	let preset = $state(presets[firstType()][0]);
	let brief = $state(t('modals.sound.defaultBrief'));
	const r0 = productionRange();
	let start = $state(round(r0[0], 0.1));
	let end = $state(round(r0[1], 0.1));
	let intent = $state({ intensity: 45, rhythm: 30, space: 80, emotion: 'contemplation' });
	let voice = $state({ character: lead || t('modals.sound.narrator'), timbre: 'soft', script: '', lipSync: true });
	const isVoice = $derived(type === 'Voix');
	let st = $state('idle');
	let progress = $state(0);
	let made = $state(null);
	let timer = null;

	const typeItems = $derived(types.map((id) => ({ id, label: typeLabel(id) })));

	function typeLabel(id) {
		if (id === 'Ambiance') return t('modals.sound.type.ambience');
		if (id === 'Bruitage') return t('modals.sound.type.foley');
		if (id === 'Texture') return t('modals.sound.type.texture');
		if (id === 'Impact') return t('modals.sound.type.impact');
		if (id === 'Musique') return t('modals.sound.type.music');
		return t('modals.sound.type.voice');
	}

	function presetLabel(id) {
		if (id === 'windAlpine') return t('modals.sound.preset.windAlpine');
		if (id === 'woodsDusk') return t('modals.sound.preset.woodsDusk');
		if (id === 'hutFire') return t('modals.sound.preset.hutFire');
		if (id === 'gravelSteps') return t('modals.sound.preset.gravelSteps');
		if (id === 'backpackRub') return t('modals.sound.preset.backpackRub');
		if (id === 'woodDoor') return t('modals.sound.preset.woodDoor');
		if (id === 'grainyBreath') return t('modals.sound.preset.grainyBreath');
		if (id === 'lowDrone') return t('modals.sound.preset.lowDrone');
		if (id === 'shimmer') return t('modals.sound.preset.shimmer');
		if (id === 'dullHit') return t('modals.sound.preset.dullHit');
		if (id === 'iceCrack') return t('modals.sound.preset.iceCrack');
		if (id === 'cutBreath') return t('modals.sound.preset.cutBreath');
		if (id === 'etherealPad') return t('modals.sound.preset.etherealPad');
		if (id === 'sparsePiano') return t('modals.sound.preset.sparsePiano');
		if (id === 'heldStrings') return t('modals.sound.preset.heldStrings');
		if (id === 'line') return t('modals.sound.preset.line');
		if (id === 'voiceOver') return t('modals.sound.preset.voiceOver');
		if (id === 'murmur') return t('modals.sound.preset.murmur');
		return t('modals.sound.preset.breath');
	}

	function emotionLabel(id) {
		if (id === 'tension') return t('modals.sound.emotion.tension');
		if (id === 'mystery') return t('modals.sound.emotion.mystery');
		if (id === 'joy') return t('modals.sound.emotion.joy');
		if (id === 'melancholy') return t('modals.sound.emotion.melancholy');
		return t('modals.sound.emotion.contemplation');
	}

	function timbreLabel(id) {
		if (id === 'deep') return t('modals.sound.timbre.deep');
		if (id === 'breathless') return t('modals.sound.timbre.breathless');
		if (id === 'whisper') return t('modals.sound.timbre.whisper');
		return t('modals.sound.timbre.soft');
	}

	function intentLabel(id) {
		if (id === 'rhythm') return t('modals.sound.rhythm');
		if (id === 'space') return t('modals.sound.space');
		return t('modals.sound.intensity');
	}

	function pickType(id) {
		type = id;
		preset = presets[id][0];
	}

	function askAssistant() {
		ui.modal = null;
		chat.open();
	}

	function prepare() {
		clearInterval(timer);
		st = 'running';
		progress = 0;
		timer = setInterval(() => {
			progress = Math.min(100, progress + 7 + Math.random() * 8);
			if (progress < 100) return;
			clearInterval(timer);
			timer = null;
			st = 'done';
			const srcDur = Math.max(1, end - start) + 2;
			const lower = (s) => s.toLocaleLowerCase(getLocale());
			made = isVoice
				? {
						id: ulid(),
						name: t('modals.sound.voiceAsset', { character: voice.character, line: voice.script.slice(0, 28) + (voice.script.length > 28 ? '…' : '') }),
						kind: 'audio',
						synth: 'voice',
						srcDur,
						role: 'Dialogue',
						generated: true,
						transcript: voice.script,
						character: voice.character,
						lipSync: voice.lipSync
					}
				: { id: ulid(), name: t('modals.sound.assetName', { preset: presetLabel(preset), type: lower(typeLabel(type)) }), kind: 'audio', synth: synthFor[type], srcDur, role: roleFor[type], generated: true };
		}, 110);
	}

	function addToTimeline() {
		assets.push(made);
		const lane = doc.lanes.find((l) => l.role === made.role) ?? doc.lanes[0];
		act(() => doc.audio.push({ id: ulid(), assetId: made.id, lane: lane.id, start: +start, dur: +end - +start, srcIn: 0, fadeIn: 0.5, fadeOut: 0.8, gain: -6 }));
		toast(t('modals.sound.added', { name: made.name, lane: lane.id }), 'success', { label: t('modals.sound.console'), run: () => ((ui.workspace = 'mixer'), (ui.bottomView = 'console')) });
		ui.modal = null;
	}

	onDestroy(() => clearInterval(timer));
</script>

<Modal
	title={isVoice ? t('modals.sound.titleVoice') : t('modals.sound.title')}
	subtitle={isVoice ? t('modals.sound.subtitleVoice', { start: secs(+start), end: secs(+end) }) : t('modals.sound.subtitle', { start: secs(+start), end: secs(+end) })}
	icon="wave"
	width={820}
	sim
>
	<div class="grid grid-cols-[1fr_280px]">
		<div class="space-y-4 border-r border-line p-4">
			<div>
				<div class="vp-label mb-1.5">{t('modals.sound.typeLabel')}</div>
				<HostUi name="SegmentedControl" props={{ items: typeItems, selected: type, variant: 'toggle', ariaLabel: t('modals.sound.typeLabel'), onSelect: pickType }} />
			</div>
			<div>
				<div class="vp-label mb-1.5">{t('modals.sound.presets')}</div>
				<div class="flex flex-wrap gap-1.5">
					{#each presets[type] as p (p)}<button type="button" class="vp-pill" aria-pressed={preset === p} onclick={() => (preset = p)}>{presetLabel(p)}</button>{/each}
				</div>
			</div>
			{#if isVoice}
				<div class="grid grid-cols-2 gap-3">
					<label class="space-y-1">
						<span class="vp-label">{t('modals.sound.character')}</span>
						<select class="input vp-dense w-full" bind:value={voice.character}>{#each characters as c (c)}<option value={c}>{c}</option>{/each}</select>
					</label>
					<label class="space-y-1">
						<span class="vp-label">{t('modals.sound.timbreLabel')}</span>
						<select class="input vp-dense w-full" bind:value={voice.timbre}>{#each timbres as tb (tb)}<option value={tb}>{timbreLabel(tb)}</option>{/each}</select>
					</label>
				</div>
				<div>
					<div class="mb-1 flex items-center justify-between">
						<label class="vp-label" for="vp-sd-script">{t('modals.sound.script')}</label>
						<span class="vp-tc text-xs text-fg-subtle">{t('modals.sound.spoken', { seconds: Math.max(1, Math.round(voice.script.split(/\s+/).filter(Boolean).length / 2.4)) })}</span>
					</div>
					<textarea id="vp-sd-script" class="input w-full text-md" rows="3" bind:value={voice.script}></textarea>
				</div>
				<div class="flex min-h-7 items-center gap-2 text-sm">
					<HostUi name="Switch" props={{ id: 'vp-sd-lipsync', checked: voice.lipSync, size: 'lg', label: t('modals.sound.lipSync'), onchange: (v) => (voice.lipSync = v) }} />
					<label for="vp-sd-lipsync">{t('modals.sound.lipSync')}</label>
				</div>
			{:else}
				<div>
					<div class="mb-1 flex items-center justify-between">
						<label class="vp-label" for="vp-sd-brief">{t('modals.sound.brief')}</label>
						<button type="button" class="flex min-h-6 items-center gap-1 text-xs text-fg-muted hover:text-fg" onclick={askAssistant}><Icon name="wand" class="h-3.5 w-3.5" />{t('modals.sound.askAssistant')}</button>
					</div>
					<textarea id="vp-sd-brief" class="input w-full" rows="3" bind:value={brief}></textarea>
				</div>
			{/if}
			<div class="grid grid-cols-2 gap-x-5 gap-y-3">
				{#each intents as k (k)}
					<label class="block">
						<span class="flex justify-between text-sm"><span>{intentLabel(k)}</span><span class="vp-tc text-xs">{intent[k]} %</span></span>
						<input class="vp-slider" type="range" min="0" max="100" bind:value={intent[k]} />
					</label>
				{/each}
				<label class="block space-y-1">
					<span class="text-sm">{t('modals.sound.emotionLabel')}</span>
					<select class="input vp-dense w-full" bind:value={intent.emotion}>{#each emotions as e (e)}<option value={e}>{emotionLabel(e)}</option>{/each}</select>
				</label>
			</div>
			<div class="flex items-center gap-2">
				<span class="vp-label">{t('modals.sound.range')}</span>
				<input class="input vp-dense vp-tc w-20" type="number" step="0.1" bind:value={start} aria-label={t('modals.sound.start')} /><span class="text-fg-subtle">→</span>
				<input class="input vp-dense vp-tc w-20" type="number" step="0.1" bind:value={end} aria-label={t('modals.sound.end')} /><span class="text-xs text-fg-subtle">{t('modals.sound.seconds')}</span>
			</div>
		</div>
		<div class="flex flex-col gap-3 p-4">
			<div class="vp-section-title">{t('modals.sound.result')}</div>
			{#if st === 'idle'}
				<div class="flex flex-1 flex-col justify-center">
					<HostUi name="EmptyState" props={{ compact: true, icon: hostIconName('wave'), title: t('modals.sound.idle') }} />
				</div>
			{:else if st === 'running'}
				<div class="flex flex-1 flex-col justify-center gap-2 rounded-lg border border-line-strong p-4">
					<div class="text-sm">{t('modals.sound.preparing')}</div>
					<div class="h-1 overflow-hidden rounded-full bg-surface-3" role="progressbar" aria-label={t('modals.sound.preparing')} aria-valuemin="0" aria-valuemax="100" aria-valuenow={Math.round(progress)}>
						<div class="h-full bg-signal" style:width="{progress}%"></div>
					</div>
				</div>
			{:else if made}
				<div class="flex-1 space-y-2 rounded-lg border border-line-strong p-3">
					<div class="text-sm font-medium">{made.name}</div>
					<div class="text-xs text-fg-subtle">{t('modals.sound.meta', { role: audioRoleLabel(made.role), duration: secs(+end - +start), emotion: emotionLabel(intent.emotion).toLocaleLowerCase(getLocale()) })}</div>
					{#if made.transcript}<p class="rounded-md bg-surface-2 p-2 text-xs italic text-fg-muted">{t('modals.sound.quote', { text: made.transcript })}</p>{/if}
					<svg viewBox="0 0 100 24" class="h-10 w-full" aria-hidden="true">
						{#each Array.from({ length: 50 }) as _, i (i)}
							{@const hh = 3 + Math.abs(Math.sin(i * 0.7) * Math.cos(i * 0.23)) * (intent.intensity / 6)}
							<rect x={i * 2} y={12 - hh / 2} width="1.2" height={hh} fill="rgb(var(--viz-3))" />
						{/each}
					</svg>
					<HostUi name="Button" props={{ variant: 'secondary', size: 'xs', icon: hostIconName('play'), class: 'w-full', onclick: () => audition(type) }}>{t('modals.sound.preview')}</HostUi>
				</div>
			{/if}
			{#if st === 'done'}
				<HostUi name="Button" props={{ variant: 'primary', size: 'sm', icon: 'plus', class: 'w-full', onclick: addToTimeline }}>{t('modals.sound.add')}</HostUi>
				<HostUi name="Button" props={{ variant: 'ghost', size: 'xs', class: 'w-full', onclick: prepare }}>{t('modals.sound.again')}</HostUi>
			{:else}
				<HostUi name="Button" props={{ variant: 'primary', size: 'sm', icon: 'sparkles', class: 'w-full', disabled: st === 'running' || +end <= +start, onclick: prepare }}>{t('modals.sound.prepare')}</HostUi>
			{/if}
		</div>
	</div>
</Modal>
