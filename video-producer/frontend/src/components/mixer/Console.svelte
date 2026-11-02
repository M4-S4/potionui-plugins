<script>
	import HostUi from '../../../../../../sdk/HostUi.svelte';
	import { formatNumber, t } from '../../i18n/index.svelte.js';
	import { ui, doc, select, act, checkpoint, addAudioLane, tc, toast } from '../../lib/state.svelte.js';
	import { meters, togglePlay } from '../../lib/playback.svelte.js';
	import { roleColor, audioRoleLabel } from '../../lib/catalog.js';
	import { commandById } from '../../lib/commands.js';
	import { hostIconName } from '../../lib/icons.js';
	import { laneCode, videoTrack } from '../../lib/tracks.js';
	import { isReferenceLane, setReferenceLane } from '../../lib/sound.js';
	import ImportButtons from '../panels/ImportButtons.svelte';
	import FilterPills from '../shell/FilterPills.svelte';
	import ZoneHeader from '../shell/ZoneHeader.svelte';
	import Icon from '../Icon.svelte';

	const roles = ['Dialogue', 'Musique', 'Ambiance', 'SFX'];
	const filters = ['Tous', ...roles];
	const lanes = $derived(doc.lanes.filter((l) => ui.mixerFilter === 'Tous' || l.role === ui.mixerFilter));
	const pills = $derived(filters.map((f) => ({ id: f, label: filterLabel(f), count: doc.lanes.filter((l) => f === 'Tous' || l.role === f).length })));
	const dbFmt = (v) => (v <= -59 ? '−∞' : formatNumber(v, { minimumFractionDigits: 1, maximumFractionDigits: 1, signDisplay: 'exceptZero' }));
	const video = $derived(videoTrack(doc));

	function toggleVideo(key) {
		doc.video = { ...videoTrack(doc), [key]: !videoTrack(doc)[key] };
	}

	function filterLabel(f) {
		return f === 'Tous' ? t('mixer.filter.all') : audioRoleLabel(f);
	}

	function fxName(type) {
		if (type === 'eq') return t('mixer.fx.eq');
		if (type === 'comp') return t('mixer.fx.comp');
		if (type === 'filter') return t('mixer.fx.filter');
		return t('mixer.fx.reverb');
	}

	function addInsert(l) {
		const has = new Set(l.inserts.map((i) => i.type));
		const next = ['eq', 'comp', 'filter'].find((type) => !has.has(type));
		if (!next) return toast(t('mixer.allFx'), 'warning');
		act(() =>
			l.inserts.push(
				next === 'filter' ? { type: 'filter', on: true, cutoff: 8000 } : next === 'comp' ? { type: 'comp', on: true, threshold: -18, ratio: 3, attack: 10, release: 120 } : { type: 'eq', on: true, low: 0, mid: 0, high: 0 }
			)
		);
		select('lane', l.id);
		ui.inspectorOpen = true;
	}

	function openStrip(l) {
		select('lane', l.id);
		ui.inspectorOpen = true;
	}
</script>

<div class="flex h-full flex-col bg-surface-1">
	<ZoneHeader icon="sliders" title={t('mixer.title')}>
		<FilterPills label={t('mixer.filter.label')} items={pills} value={ui.mixerFilter} onselect={(f) => (ui.mixerFilter = f)} />
		<div class="vp-divider"></div>
		<HostUi name="Button" props={{ variant: 'ghost', size: 'xs', icon: 'plus', class: 'shrink-0', onclick: addAudioLane }}>{t('mixer.addLane')}</HostUi>
		<div class="flex shrink-0 items-center gap-1"><ImportButtons kind="audio" /></div>
		<div class="flex-1"></div>
		<HostUi
			name="IconButton"
			props={{ icon: hostIconName(ui.playing ? 'pause' : 'play'), label: ui.playing ? t('mixer.pause') : t('mixer.play'), tooltip: t('mixer.transport'), kbd: commandById('play')?.key, size: 'sm', class: 'vp-h7', onclick: togglePlay }}
		/>
		<span class="vp-tc text-sm">{tc(ui.playhead, doc.fps)}</span>
		<div class="vp-divider"></div>
		<HostUi name="IconButton" props={{ icon: 'film', label: t('mixer.backToTimeline'), tooltip: t('mixer.backToTimeline'), size: 'sm', class: 'vp-h7', onclick: () => (ui.bottomView = 'timeline') }} />
	</ZoneHeader>

	<div class="flex min-h-0 flex-1 gap-px overflow-auto bg-line p-px">
		{@render videoStrip()}
		{#each lanes as l (l.id)}
			{@render strip(l, roleColor[l.role] ?? 'viz-1')}
		{/each}
		<div class="w-2 shrink-0 bg-canvas"></div>
		{#each doc.aux as a (a.id)}
			{@render auxStrip(a)}
		{/each}
		<div class="w-2 shrink-0 bg-canvas"></div>
		{@render masterStrip()}
		<div class="flex-1 bg-surface-1"></div>
	</div>
</div>

{#snippet meter(v)}
	<div class="relative h-full w-1.5 overflow-hidden rounded-sm bg-canvas" aria-hidden="true">
		<div
			class="absolute inset-x-0 bottom-0"
			style:height="{v * 100}%"
			style:background="linear-gradient(to top, rgb(var(--success)) 0%, rgb(var(--success)) 70%, rgb(var(--warning)) 85%, rgb(var(--danger-solid)) 100%)"
			style:background-size="100% {100 / Math.max(v, 0.01)}%"
			style:background-position="bottom"
		></div>
	</div>
{/snippet}

{#snippet fader(value, onchange, label)}
	<HostUi name="Tooltip" props={{ text: t('mixer.faderTip'), wrapperClass: 'flex h-full' }}>
		<input
			type="range"
			min="-60"
			max="6"
			step="0.5"
			{value}
			aria-label={label}
			class="h-full w-6 cursor-pointer accent-[rgb(var(--fg))]"
			style="writing-mode: vertical-lr; direction: rtl;"
			onpointerdown={checkpoint}
			oninput={(e) => onchange(+e.currentTarget.value)}
			ondblclick={() => (checkpoint(), onchange(0))}
		/>
	</HostUi>
{/snippet}

{#snippet strip(l, color)}
	{@const sel = ui.selection?.kind === 'lane' && ui.selection.id === l.id}
	<div class="flex w-28 shrink-0 flex-col gap-1.5 bg-surface-1 p-1.5 {sel ? 'ring-1 ring-inset ring-signal' : ''}" role="group" aria-label={t('mixer.strip', { id: laneCode(doc.lanes, l.id), name: l.name })}>
		<button type="button" class="flex min-h-6 items-center gap-1.5 text-left" onclick={() => openStrip(l)}>
			<span class="h-3 w-1 rounded-sm" style:background="rgb(var(--{color}))"></span>
			<span class="truncate text-xs font-medium">{laneCode(doc.lanes, l.id)} · {l.name}</span>
		</button>
		<select class="input vp-dense w-full" value={l.role} onchange={(e) => act(() => (l.role = e.currentTarget.value))} aria-label={t('mixer.role', { name: l.name })}>
			{#each roles as r (r)}<option value={r}>{audioRoleLabel(r)}</option>{/each}
		</select>
		<div class="space-y-0.5">
			{#each l.inserts as fx, i (i)}
				<HostUi name="Tooltip" props={{ text: t('mixer.fxTip', { name: fxName(fx.type) }), wrapperClass: 'flex w-full' }}>
					<button
						type="button"
						class="flex h-6 w-full items-center gap-1 rounded-sm border px-1 text-left text-2xs {fx.on ? 'border-signal/60 bg-surface-2 text-fg' : 'border-line-strong text-fg-muted'}"
						onclick={() => openStrip(l)}
					>
						<span class="h-1.5 w-1.5 rounded-full {fx.on ? 'bg-signal' : 'bg-fg-disabled'}"></span>{fxName(fx.type)}
					</button>
				</HostUi>
			{/each}
			<button type="button" class="flex h-6 w-full items-center justify-center rounded-sm border border-dashed border-line-strong text-2xs text-fg-muted hover:text-fg" onclick={() => addInsert(l)}>{t('mixer.addFx')}</button>
		</div>
		<div class="text-2xs text-fg-muted">
			<label class="flex items-center gap-1">{t('mixer.send.reverbShort')}<input class="vp-slider" type="range" min="-60" max="0" value={l.sends.R1} onpointerdown={checkpoint} oninput={(e) => (l.sends.R1 = +e.currentTarget.value)} aria-label={t('mixer.send.reverb')} /></label>
			<label class="flex items-center gap-1">{t('mixer.send.delayShort')}<input class="vp-slider" type="range" min="-60" max="0" value={l.sends.D1} onpointerdown={checkpoint} oninput={(e) => (l.sends.D1 = +e.currentTarget.value)} aria-label={t('mixer.send.delay')} /></label>
		</div>
		<label class="flex items-center gap-1 text-2xs text-fg-muted">
			{t('mixer.pan.left')}<input
				class="vp-slider"
				type="range"
				min="-1"
				max="1"
				step="0.05"
				value={l.pan}
				onpointerdown={checkpoint}
				oninput={(e) => (l.pan = +e.currentTarget.value)}
				ondblclick={() => (l.pan = 0)}
				aria-label={t('mixer.pan.label')}
			/>{t('mixer.pan.right')}
		</label>
		<div class="flex min-h-[72px] flex-1 justify-center gap-2">
			{@render fader(l.vol, (v) => (l.vol = v), t('mixer.volume', { name: l.name }))}
			{@render meter(meters.lanes[l.id] ?? 0)}
		</div>
		<div class="vp-tc text-center text-xs">{t('mixer.db', { value: dbFmt(l.vol) })}</div>
		<div class="grid grid-cols-2 gap-1">
			<button type="button" class="vp-toggle h-6 rounded-sm bg-surface-2 text-xs font-semibold {l.mute ? '!text-warning' : 'text-fg-muted hover:text-fg'}" aria-pressed={l.mute} aria-label={t('mixer.mute', { name: l.name })} onclick={() => (l.mute = !l.mute)}>{t('mixer.muteShort')}</button>
			<button type="button" class="vp-toggle h-6 rounded-sm bg-surface-2 text-xs font-semibold {l.solo ? '!text-signal' : 'text-fg-muted hover:text-fg'}" aria-pressed={l.solo} aria-label={t('mixer.solo', { name: l.name })} onclick={() => (l.solo = !l.solo)}>{t('mixer.soloShort')}</button>
		</div>
		<HostUi name="Tooltip" props={{ text: t('mixer.referenceTip'), wrapperClass: 'flex w-full' }}>
			<button
				type="button"
				class="vp-toggle flex h-6 w-full items-center justify-center gap-1 rounded-sm bg-surface-2 text-xs font-semibold {isReferenceLane(l) ? '!text-signal' : 'text-fg-muted hover:text-fg'}"
				aria-pressed={isReferenceLane(l)}
				aria-label={t('mixer.reference', { name: l.name })}
				onclick={() => act(() => setReferenceLane(l, !isReferenceLane(l)))}
			><Icon name="sparkles" class="h-3 w-3" />{t('mixer.referenceShort')}</button>
		</HostUi>
	</div>
{/snippet}

{#snippet videoStrip()}
	<div class="flex w-24 shrink-0 flex-col gap-1.5 bg-surface-1 p-1.5" role="group" aria-label={t('mixer.video.label')}>
		<div class="flex min-h-6 items-center gap-1.5">
			<span class="h-3 w-1 rounded-sm bg-viz-1"></span>
			<span class="truncate text-xs font-medium">{t('mixer.video.name')}</span>
		</div>
		<div class="text-2xs text-fg-muted">{t('mixer.video.info')}</div>
		<div class="flex min-h-[72px] flex-1 justify-center">{@render meter(meters.video)}</div>
		<div class="grid grid-cols-2 gap-1">
			<button type="button" class="vp-toggle h-6 rounded-sm bg-surface-2 text-xs font-semibold {video.mute ? '!text-warning' : 'text-fg-muted hover:text-fg'}" aria-pressed={video.mute} aria-label={t('mixer.mute', { name: t('mixer.video.name') })} onclick={() => toggleVideo('mute')}>{t('mixer.muteShort')}</button>
			<button type="button" class="vp-toggle h-6 rounded-sm bg-surface-2 text-xs font-semibold {video.solo ? '!text-signal' : 'text-fg-muted hover:text-fg'}" aria-pressed={video.solo} aria-label={t('mixer.solo', { name: t('mixer.video.name') })} onclick={() => toggleVideo('solo')}>{t('mixer.soloShort')}</button>
		</div>
	</div>
{/snippet}

{#snippet auxStrip(a)}
	<div class="flex w-24 shrink-0 flex-col gap-1.5 bg-surface-2 p-1.5" role="group" aria-label={t('mixer.aux', { name: a.name })}>
		<div class="text-xs font-medium">{a.id} · {a.name}</div>
		<div class="text-2xs text-fg-muted">{t('mixer.auxBus')}</div>
		<div class="flex min-h-[72px] flex-1 justify-center gap-2">{@render fader(a.vol, (v) => (a.vol = v), t('mixer.volume', { name: a.name }))}</div>
		<div class="vp-tc text-center text-xs">{t('mixer.db', { value: dbFmt(a.vol) })}</div>
		<button type="button" class="vp-toggle h-6 rounded-sm bg-surface-3 text-xs font-semibold {a.mute ? '!text-warning' : 'text-fg-muted'}" aria-pressed={a.mute} aria-label={t('mixer.mute', { name: a.name })} onclick={() => (a.mute = !a.mute)}>{t('mixer.muteShort')}</button>
	</div>
{/snippet}

{#snippet masterStrip()}
	<div class="flex w-28 shrink-0 flex-col gap-1.5 bg-surface-2 p-1.5" role="group" aria-label={t('mixer.masterOut')}>
		<div class="text-xs font-semibold">{t('mixer.master')}</div>
		<div class="text-2xs text-fg-muted">{t('mixer.masterInfo')}</div>
		<div class="flex min-h-[72px] flex-1 justify-center gap-1.5">
			{@render fader(doc.master.vol, (v) => (doc.master.vol = v), t('mixer.masterVolume'))}
			{@render meter(meters.master[0])}
			{@render meter(meters.master[1])}
		</div>
		<div class="vp-tc text-center text-xs">{t('mixer.db', { value: dbFmt(doc.master.vol) })}</div>
	</div>
{/snippet}
