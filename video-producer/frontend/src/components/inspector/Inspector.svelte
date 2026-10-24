<script>
	import HostUi from '../../../../../../sdk/HostUi.svelte';
	import { formatNumber, t } from '../../i18n/index.svelte.js';
	import {
		ui,
		doc,
		asset,
		selected,
		select,
		act,
		relayout,
		clamp,
		round,
		secs,
		bladeAt,
		duplicateSelection,
		deleteSelection,
		deleteLane,
		promptIssues,
		globalPrompt,
		clipLabel,
		shotIdAt,
		sourceLength,
		promptEdited
	} from '../../lib/state.svelte.js';
	import { seek } from '../../lib/playback.svelte.js';
	import { clipFilter } from '../../lib/look.js';
	import { assetThumb, clipThumb } from '../../lib/media.js';
	import { stages, audioRoleLabel, frameRoleLabel } from '../../lib/catalog.js';
	import { takesOf, promoteToFinal, startGeneration, findTake, shotActivity, engineLabel, soundBehaviorOf, shotDurationLimit, fitShot } from '../../lib/production.svelte.js';
	import { refMediaKind, refRoleLabel, refTypeLabel, typesOf } from '../../lib/references.js';
	import { isReferenceLane, setReferenceLane } from '../../lib/sound.js';
	import AudioPicker from '../shots/AudioPicker.svelte';
	import MediaPicker from '../shots/MediaPicker.svelte';
	import SoundNote from '../shots/SoundNote.svelte';
	import { commandById } from '../../lib/commands.js';
	import {
		currentPlan,
		currentScene,
		sceneOf,
		sourceOf,
		controlOf,
		planOfControl,
		addKeyframe,
		deleteKeyframe,
		editKey,
		selectKey,
		takeOver,
		freeCamera,
		setFreeCamera,
		shownCamera,
		resetToSource,
		renderPlan,
		useStartEnd,
		setPlanDur,
		setPlanScene,
		setPlanStart,
		presetLabel,
		sceneReady,
		sceneLocked
	} from '../../lib/scene.svelte.js';
	import { FOCAL_RANGE, ROLL_RANGE, distance, dollyCamera, pose } from '../../lib/scene3d/camera.js';
	import { hostIconName } from '../../lib/icons.js';
	import { clipSoundAudible, laneCode, laneItemCount, laneTitle, videoTrack } from '../../lib/tracks.js';
	import { framesOf, roleKind } from '../../lib/seam.js';
	import Tabs from '../shell/Tabs.svelte';
	import SeamAction from '../takes/SeamAction.svelte';
	import Icon from '../Icon.svelte';
	import TakesSection from './TakesSection.svelte';
	import DraftsField from '../shots/DraftsField.svelte';
	import CastField from '../shots/CastField.svelte';
	import { instructionOf, setCast } from '../../lib/bible.js';
	import { touch } from '../../lib/shots.js';
	import ColorSection from './ColorSection.svelte';
	import NumField from './NumField.svelte';
	import SliderField from './SliderField.svelte';

	const s = $derived(ui.selection);
	const item = $derived(selected());

	const icons = { clip: 'film', audio: 'wave', title: 'type', prompt: 'sparkles', frame: 'image', control: 'route', plan3d: 'cube', marker: 'bookmark', reference: 'bookmark', lane: 'sliders' };

	function kindTitle(kind) {
		if (kind === 'clip') return t('inspector.kind.clip');
		if (kind === 'audio') return t('inspector.kind.audio');
		if (kind === 'title') return t('inspector.kind.title');
		if (kind === 'prompt') return t('inspector.kind.prompt');
		if (kind === 'frame') return t('inspector.kind.frame');
		if (kind === 'control') return t('inspector.kind.control');
		if (kind === 'plan3d') return t('inspector.kind.plan3d');
		if (kind === 'marker') return t('inspector.kind.marker');
		if (kind === 'reference') return t('inspector.kind.reference');
		return t('inspector.kind.lane');
	}

	function fxName(type) {
		if (type === 'eq') return t('inspector.fx.eq');
		if (type === 'comp') return t('inspector.fx.comp');
		return t('inspector.fx.filter');
	}

	const name = $derived.by(() => {
		if (!item) return '';
		if (s.kind === 'clip' || s.kind === 'audio' || s.kind === 'frame') return asset(item.assetId)?.name;
		if (s.kind === 'lane') return laneTitle(doc.lanes, item);
		return item.name ?? item.text ?? item.label ?? '';
	});

	const busy = $derived(s?.kind === 'clip' && item ? shotActivity(item.id).state === 'running' : false);
	const set = (k, v) => (item[k] = v);
	const setClipDur = (v) => {
		const before = item.dur;
		item.dur = round(clamp(v, 0.4, shotDurationLimit(item).max), 0.04);
		fitShot(item, before);
		relayout();
	};
	const setClipIn = (v) => {
		const max = sourceLength(item);
		item.srcIn = round(clamp(v, 0, max - 0.4), 0.04);
		item.dur = Math.min(item.dur, max - item.srcIn);
		relayout();
	};
	const headThumb = $derived(!item ? null : s.kind === 'clip' ? clipThumb(item) : s.kind === 'frame' ? assetThumb(asset(item.assetId)) : null);
	const frameImages = $derived(doc.assets.filter((x) => x.kind !== 'audio' && assetThumb(x)));
	const fadeMax = $derived(item?.dur ? item.dur / 2 : 0);
	const issues = $derived(s?.kind === 'prompt' ? promptIssues(item) : []);
	const plan = $derived(ui.workspace === 'scene' && (!s || s.kind === 'plan3d') ? currentPlan() : null);
	const cameraPanel = $derived(!item && ui.workspace === 'scene' && doc.scenes.length > 0);
	const gain = (v) => `${formatNumber(v, { minimumFractionDigits: 1, maximumFractionDigits: 1, signDisplay: 'exceptZero' })} dB`;

	const shown = $derived(shownCamera());
	const sceneDepth = $derived.by(() => {
		const scene = currentScene();
		const source = scene ? sourceOf(scene) : null;
		return source ? distance(source.pos, source.target) : 4;
	});
	const camFields = $derived([
		{ k: 'focal', label: t('inspector.camera.focal'), min: FOCAL_RANGE[0], max: FOCAL_RANGE[1], step: 1, unit: ' mm', value: shown.focal },
		{ k: 'roll', label: t('inspector.camera.roll'), min: ROLL_RANGE[0], max: ROLL_RANGE[1], step: 1, unit: '°', value: shown.roll ?? 0 },
		{ k: 'dist', label: t('inspector.camera.dist'), min: +(sceneDepth * 0.05).toFixed(2), max: Math.max(1, +(sceneDepth * 4).toFixed(1)), step: 0.01, unit: '', value: distance(shown.pos, shown.target) }
	]);
	const flags = $derived([
		{ id: 'none', label: t('inspector.flag.none') },
		{ id: 'favori', label: t('inspector.flag.favorite') },
		{ id: 'rejet', label: t('inspector.flag.rejected') }
	]);
	const scopes = $derived([
		{ id: 'global', label: t('inspector.scope.global') },
		{ id: 'shot', label: t('inspector.scope.shot') }
	]);
	const shortcuts = $derived([
		[t('inspector.empty.keyPlay'), commandById('play')?.key],
		[t('inspector.empty.keyGenerate'), commandById('generate')?.key],
		[t('inspector.empty.keyAssistant'), commandById('assistant')?.key],
		[t('inspector.empty.keyCommands'), commandById('palette')?.key]
	]);

	function camSet(k, v) {
		const owner = plan ?? (s?.kind === 'plan3d' ? item : null);
		const key = owner?.keyframes.find((x) => x.id === ui.scene.keyframe);
		const base = key ? pose(key) : ui.scene.keyframe === null ? takeOver() : freeCamera();
		const next = k === 'dist' ? dollyCamera(base, v / Math.max(1e-6, distance(base.pos, base.target)), 1e-3) : { ...base, [k]: v };
		setFreeCamera(next);
		if (key) editKey(key, { pos: [...next.pos], target: [...next.target], focal: next.focal, roll: next.roll });
	}

	function sourceText(p) {
		if (p.source === 'trajectory' && p.preset) return t('inspector.plan.preset', { preset: presetLabel(p.preset), amount: p.amount ?? 0, unit: p.preset === 'dolly' ? '%' : '°' });
		if (p.source === 'blender') return t('inspector.plan.blender', { camera: p.camera ?? '—' });
		return t('inspector.plan.manual');
	}

	const seamFrame = (shotId, kind) => framesOf(doc, shotId, kind).find((f) => f.assetId) ?? null;
	const roleOption = (role) => (roleKind(role) === 'first' ? 'Début' : roleKind(role) === 'last' ? 'Fin' : role);

	function editPrompt(p, text) {
		const before = p.text;
		p.text = text;
		promptEdited(p, before);
	}

	function recast(clip, cast) {
		act(() => {
			setCast(clip, cast);
			touch(clip);
		});
	}

	function openBible() {
		ui.workspace = 'director';
		ui.dockTab = 'direction';
		ui.sidebarOpen = true;
	}

	function setScope(id) {
		if (id === item.scope.type) return;
		act(() => (item.scope = id === 'global' ? { type: 'global' } : { type: 'shot', shotId: shotIdAt(ui.playhead) ?? doc.clips[0]?.id ?? null }));
	}
</script>

<aside class="flex min-h-0 flex-col overflow-hidden border-l border-line bg-surface-1" aria-label={t('inspector.title')} class:invisible={!ui.inspectorOpen}>
	<div class="vp-panel-head border-b border-line">
		<Icon name={item ? icons[s.kind] : cameraPanel ? 'camera' : 'info'} class="h-4 w-4 text-fg-muted" />
		<span class="truncate text-sm font-semibold">{item ? kindTitle(s.kind) : cameraPanel ? t('inspector.camera.title') : t('inspector.title')}</span>
		<div class="flex-1"></div>
		<HostUi
			name="IconButton"
			props={{ icon: hostIconName('x'), label: t('inspector.close'), tooltip: t('inspector.closeTip'), kbd: commandById('inspector')?.key, size: 'sm', class: 'vp-h7', onclick: () => (ui.inspectorOpen = false) }}
		/>
	</div>

	{#if item && s.kind === 'clip'}
		<Tabs
			label={t('inspector.tabs')}
			value={ui.inspectorTab}
			onselect={(id) => (ui.inspectorTab = id)}
			items={[
				{ id: 'video', label: t('inspector.tab.video') },
				{ id: 'takes', label: t('inspector.tab.takes'), badge: takesOf(item).length || null },
				{ id: 'color', label: t('inspector.tab.color') }
			]}
		/>
	{/if}
	<div class="min-h-0 flex-1 space-y-4 overflow-auto p-3">
		{#if cameraPanel}
			{@render camera()}
		{:else if !item}
			<div class="space-y-3">
				<div class="text-sm font-medium">{doc.name}</div>
				<dl class="grid grid-cols-[auto_1fr] gap-x-3 gap-y-1 text-xs">
					<dt class="text-fg-subtle">{t('inspector.project.format')}</dt>
					<dd class="text-fg-muted">{t('inspector.project.formatValue', { resolution: doc.resolution, fps: doc.fps, aspect: doc.aspect })}</dd>
					<dt class="text-fg-subtle">{t('inspector.project.profile')}</dt>
					<dd class="text-fg-muted">{doc.direction.mode}</dd>
					<dt class="text-fg-subtle">{t('inspector.project.content')}</dt>
					<dd class="text-fg-muted">
						{t('inspector.count.shots', { count: doc.clips.length })} · {t('inspector.count.prompts', { count: doc.prompts.length })} · {t('inspector.count.frames', { count: doc.frames.length })}
					</dd>
				</dl>
				<div class="space-y-2 rounded-xl border border-dashed border-line-hover p-3 text-xs text-fg-muted">
					<p class="text-sm text-fg">{ui.workspace === 'storyboard' ? t('inspector.empty.storyboardTitle') : t('inspector.empty.title')}</p>
					<p>{ui.workspace === 'storyboard' ? t('inspector.empty.storyboardText') : t('inspector.empty.text')}</p>
					<ul class="space-y-1 pt-1">
						{#each shortcuts as [label, keys] (label)}
							<li class="flex justify-between gap-2"><span>{label}</span><kbd class="vp-kbd">{keys}</kbd></li>
						{/each}
					</ul>
				</div>
				<HostUi name="Button" props={{ variant: 'secondary', size: 'sm', class: 'w-full', onclick: () => (ui.modal = { type: 'project' }) }}>{t('inspector.projectProps')}</HostUi>
			</div>
		{:else}
			<div class="flex items-center gap-2.5">
				{#if headThumb}
					<img src={headThumb} alt="" class="h-10 w-16 rounded-md object-cover" style:filter={s.kind === 'clip' ? clipFilter(item) : null} />
				{:else if s.kind === 'clip'}
					<span class="flex h-10 w-16 items-center justify-center rounded-md bg-surface-3 bg-[repeating-linear-gradient(135deg,rgb(var(--line-strong))_0_1px,transparent_1px_8px)]"><Icon name="sparkles" class="h-4 w-4 text-fg-muted" /></span>
				{/if}
				<div class="min-w-0 flex-1">
					{#if s.kind === 'clip'}
						<input
							class="-ml-1 w-full truncate rounded border border-transparent bg-transparent px-1 py-1 text-sm font-medium hover:border-line-strong focus:border-signal focus:outline-none"
							value={clipLabel(item)}
							onchange={(e) => act(() => (item.label = e.currentTarget.value))}
							aria-label={t('inspector.shotName')}
						/>
					{:else}
						<div class="truncate text-sm font-medium">{name || '—'}</div>
					{/if}
					<div class="flex items-center gap-2 text-xs text-fg-subtle">
						{#if s.kind === 'clip'}<span class="flex items-center gap-1 {stages[item.stage].tone}"><span class="h-1.5 w-1.5 rounded-full {stages[item.stage].dot}"></span>{stages[item.stage].label}</span>{/if}
						{#if 'start' in item}<span class="vp-tc">{secs(item.start)} → {secs(item.start + item.dur)}</span>{/if}
						{#if 'time' in item}<span class="vp-tc">{t('inspector.at', { time: secs(item.time) })}</span>{/if}
					</div>
				</div>
			</div>

			{#if s.kind === 'clip'}
				{@const a = asset(item.assetId)}
				{@const take = findTake(item.take)}
				{#if ui.inspectorTab === 'takes'}
					<TakesSection clip={item} />
				{:else if ui.inspectorTab === 'color'}
					<ColorSection clip={item} />
				{:else}
					<div class="flex items-center gap-2">
						<HostUi name="Button" props={{ variant: 'secondary', size: 'sm', icon: hostIconName('pencil'), class: 'min-w-0 flex-1', onclick: () => (ui.modal = { type: 'shot', id: item.id }) }}>{t('inspector.editShot')}</HostUi>
						<DraftsField clips={[item]} label={false} disabled={busy} />
					</div>
					{#if item.stage !== 'final' && item.stage !== 'source'}
						{@const promote = item.stage === 'draft' && Boolean(take)}
						<button
							type="button"
							class="flex w-full items-center gap-3 rounded-lg border border-line-strong bg-surface-2/60 p-2.5 text-left transition-colors hover:border-line-hover disabled:opacity-50"
							onclick={() => (take && promote ? promoteToFinal(take.id) : startGeneration({ clips: [item], quality: 'draft' }))}
							disabled={busy}
						>
							<span class="flex h-8 w-8 items-center justify-center rounded-full bg-surface-3 text-fg"><Icon name={promote ? 'arrow-up' : 'sparkles'} class="h-4 w-4" /></span>
							<span class="min-w-0 flex-1">
								<span class="block text-sm font-medium">{promote ? t('inspector.promoteTake', { variant: take?.variant ?? '' }) : t('inspector.generateDrafts')}</span>
								<span class="block truncate text-xs text-fg-muted">{t('inspector.engineOn', { engine: engineLabel() })}</span>
							</span>
						</button>
					{/if}
					<section class="space-y-2">
						<div class="vp-section-title">{t('inspector.section.duration')}</div>
						<NumField label={t('inspector.field.duration')} value={item.dur} min={0.4} step={0.04} unit="s" onchange={setClipDur} />
						{#if a}
							<NumField label={t('inspector.field.sourceIn')} value={item.srcIn} min={0} step={0.04} unit="s" onchange={setClipIn} hint={t('inspector.field.sourceInHint')} />
							{#if a.srcDur}
								<div class="flex items-center gap-2 text-xs text-fg-subtle">
									<div class="relative h-1.5 flex-1 rounded-full bg-surface-3">
										<div class="absolute inset-y-0 rounded-full bg-viz-1" style:left="{(item.srcIn / a.srcDur) * 100}%" style:width="{(item.dur / a.srcDur) * 100}%"></div>
									</div>
									<span>{t('inspector.sourceLength', { duration: secs(a.srcDur) })}</span>
								</div>
							{/if}
							<div class="text-xs text-fg-subtle">
								{#if a.generated}
									{take?.quality === 'final' ? t('inspector.takeInfoFinal', { variant: take?.variant ?? '', res: a.res }) : t('inspector.takeInfoDraft', { variant: take?.variant ?? '', res: a.res })}
								{:else}
									{t('inspector.mediaInfo', { res: a.res ?? '—', fps: a.fps || '—' })}
								{/if}
							</div>
						{/if}
					</section>
					<section class="space-y-2">
						<div class="vp-section-title">{t('inspector.section.cast')}</div>
						<CastField cast={item.cast} text={instructionOf(doc, item)} onchange={(cast) => recast(item, cast)} onopen={openBible} />
					</section>
					<section class="space-y-2">
						<div class="vp-section-title">{t('inspector.section.frames')}</div>
						<div class="grid grid-cols-2 gap-2">
							{#each [['first', t('inspector.frames.first')], ['last', t('inspector.frames.last')]] as [kind, title] (kind)}
								{@const f = seamFrame(item.id, kind)}
								{@const thumb = f ? assetThumb(asset(f.assetId)) : null}
								<button
									type="button"
									class="overflow-hidden rounded-md border border-line-strong text-left transition-colors {f ? 'hover:border-line-hover' : ''} disabled:cursor-default"
									disabled={!f}
									onclick={() => f && select('frame', f.id)}
								>
									{#if thumb}
										<img src={thumb} alt="" class="aspect-video w-full object-cover" />
									{:else}
										<span class="flex aspect-video w-full items-center justify-center bg-surface-3 text-2xs text-fg-subtle">{t('inspector.frames.none')}</span>
									{/if}
									<span class="block truncate px-1.5 py-0.5 text-2xs text-fg-muted">{title}</span>
								</button>
							{/each}
						</div>
						<SeamAction clip={item} variant="button" />
						<p class="text-xs text-fg-subtle">{t('inspector.frames.hint')}</p>
					</section>
					{@render fadeFields(true)}
					{#if a?.kind === 'video'}
						{@const video = videoTrack(doc)}
						<section class="space-y-2">
							<div class="vp-section-title">{t('inspector.section.sound')}</div>
							<div class="flex min-h-6 items-center justify-between gap-2 text-xs text-fg-muted">
								<label for="vp-clip-mute">{t('inspector.sound.mute')}</label>
								<HostUi name="Switch" props={{ id: 'vp-clip-mute', checked: Boolean(item.mute), size: 'lg', label: t('inspector.sound.mute'), onchange: (v) => act(() => (item.mute = v)) }} />
							</div>
							<p class="text-xs text-fg-subtle">
								{#if item.mute}
									{t('inspector.sound.muted')}
								{:else if video.mute}
									{t('inspector.sound.trackMuted')}
								{:else if !clipSoundAudible(doc, item)}
									{t('inspector.sound.otherSolo')}
								{:else}
									{t('inspector.sound.hint')}
								{/if}
							</p>
						</section>
					{/if}
					<section class="space-y-2">
						<div class="vp-section-title">{t('inspector.section.flag')}</div>
						<HostUi
							name="SegmentedControl"
							props={{ items: flags, selected: item.flag ?? 'none', variant: 'toggle', fullWidth: true, ariaLabel: t('inspector.section.flag'), onSelect: (id) => act(() => (item.flag = id === 'none' ? null : id)) }}
						/>
					</section>
					<div class="flex items-center gap-0.5 border-t border-line pt-2">
						<HostUi
							name="IconButton"
							props={{ icon: 'scissors', label: t('inspector.splitMiddle'), tooltip: t('inspector.splitMiddle'), size: 'xs', onclick: () => (seek(item.start + item.dur / 2), bladeAt()) }}
						/>
						<HostUi name="IconButton" props={{ icon: 'copy', label: t('inspector.duplicate'), kbd: commandById('duplicate')?.key, size: 'xs', onclick: duplicateSelection }} />
						<div class="flex-1"></div>
						<HostUi name="IconButton" props={{ icon: 'trash', label: t('inspector.delete'), kbd: commandById('delete')?.key, size: 'xs', onclick: deleteSelection }} />
					</div>
				{/if}
			{:else if s.kind === 'audio'}
				<section class="space-y-2">
					<label class="flex items-center gap-2">
						<span class="w-24 shrink-0 text-xs text-fg-muted">{t('inspector.field.lane')}</span>
						<select class="input vp-dense min-w-0 flex-1" value={item.lane} onchange={(e) => act(() => (item.lane = e.currentTarget.value))}>
							{#each doc.lanes as l (l.id)}<option value={l.id}>{laneCode(doc.lanes, l.id)} · {l.name} ({audioRoleLabel(l.role)})</option>{/each}
						</select>
					</label>
					<NumField label={t('inspector.field.start')} value={item.start} min={0} step={0.04} unit="s" onchange={(v) => set('start', v)} />
					<NumField label={t('inspector.field.duration')} value={item.dur} min={0.3} max={(asset(item.assetId)?.srcDur ?? Infinity) - item.srcIn} step={0.04} unit="s" onchange={(v) => set('dur', v)} />
					<SliderField label={t('inspector.field.gain')} value={item.gain} min={-30} max={12} step={0.5} format={gain} onchange={(v) => set('gain', v)} />
				</section>
				{@render fadeFields(false)}
				<HostUi name="Button" props={{ variant: 'secondary', size: 'sm', icon: hostIconName('sliders'), class: 'w-full', onclick: () => ((ui.workspace = 'mixer'), select('lane', item.lane)) }}>
					{t('inspector.openStrip', { lane: laneCode(doc.lanes, item.lane) })}
				</HostUi>
			{:else if s.kind === 'prompt'}
				<section class="space-y-2">
					<textarea class="input w-full text-sm" rows="5" value={item.text} onchange={(e) => act(() => editPrompt(item, e.currentTarget.value))} placeholder={t('inspector.prompt.placeholder')} aria-label={t('inspector.prompt.text')}></textarea>
					<div class="flex gap-1.5">
						<HostUi name="Button" props={{ variant: 'secondary', size: 'xs', icon: hostIconName('wand'), class: 'flex-1', onclick: () => (ui.modal = { type: 'library', target: { kind: 'prompt', id: item.id } }) }}>
							{t('inspector.prompt.library')}
						</HostUi>
						<HostUi name="Button" props={{ variant: 'secondary', size: 'xs', onclick: () => (ui.modal = { type: 'prompt', id: item.id }) }}>{t('inspector.prompt.editor')}</HostUi>
					</div>
					{#each issues as issue, i (i)}
						{#if issue.level === 'conflict'}
							<HostUi name="Alert" props={{ variant: 'warning', class: '[&>div]:text-fg', density: 'compact', icon: true }}>{issue.text}</HostUi>
						{:else}
							<div class="flex gap-1.5 rounded border p-2 text-xs text-fg-muted {issue.level === 'control' ? 'border-viz-8/50' : 'border-line-hover'}">
								<Icon name={issue.level === 'control' ? 'route' : 'alert'} class="mt-px h-3.5 w-3.5 shrink-0" />{issue.text}
							</div>
						{/if}
					{/each}
					<NumField label={t('inspector.field.start')} value={item.start} min={0} step={0.04} unit="s" onchange={(v) => set('start', v)} />
					<NumField label={t('inspector.field.duration')} value={item.dur} min={0.3} step={0.04} unit="s" onchange={(v) => set('dur', v)} />
					<SliderField label={t('inspector.field.influence')} value={item.strength} unit=" %" onchange={(v) => set('strength', v)} />
				</section>
				<details class="rounded-lg border border-line-strong p-2 text-xs">
					<summary class="-mb-1 -mt-1 min-h-6 cursor-pointer py-1 text-fg-muted">{t('inspector.prompt.global')}</summary>
					<p class="mt-1.5 text-fg-subtle">{globalPrompt()}</p>
				</details>
			{:else if s.kind === 'frame'}
				<section class="space-y-2">
					<div class="vp-label">{t('inspector.field.image')}</div>
					{#if !frameImages.length}<p class="text-xs text-fg-subtle">{t('inspector.field.noImage')}</p>{/if}
					<div class="grid grid-cols-3 gap-1.5">
						{#each frameImages as a (a.id)}
							<HostUi name="Tooltip" props={{ text: a.name, wrapperClass: 'block' }}>
								<button
									type="button"
									class="block w-full overflow-hidden rounded border {item.assetId === a.id ? 'border-signal ring-1 ring-signal' : 'border-line-strong'}"
									aria-pressed={item.assetId === a.id}
									onclick={() => act(() => (item.assetId = a.id))}
								>
									<img src={assetThumb(a)} alt={a.name} class="aspect-video w-full object-cover" />
								</button>
							</HostUi>
						{/each}
					</div>
					<NumField label={t('inspector.field.position')} value={item.time} min={0} step={0.04} unit="s" onchange={(v) => set('time', v)} />
					<label class="flex items-center gap-2">
						<span class="w-24 shrink-0 text-xs text-fg-muted">{t('inspector.field.role')}</span>
						<select class="input vp-dense min-w-0 flex-1" value={roleOption(item.role)} onchange={(e) => act(() => (item.role = e.currentTarget.value))}>
							{#each ['Début', 'Fin', 'Transition', 'Identité', 'Style', ...(item.role === 'Capture 3D' ? ['Capture 3D'] : [])] as r (r)}<option value={r}>{frameRoleLabel(r)}</option>{/each}
						</select>
					</label>
					{#if item.sceneId}
						<div class="flex items-center gap-2 text-xs text-fg-muted"><Icon name="cube" class="h-3.5 w-3.5 shrink-0" />{t('inspector.frame.fromScene', { scene: sceneOf(item.sceneId)?.name ?? t('inspector.frame.removedScene') })}</div>
					{/if}
					<SliderField label={t('inspector.field.strength')} value={item.strength} unit=" %" onchange={(v) => set('strength', v)} />
				</section>
			{:else if s.kind === 'control'}
				{@const owner = planOfControl(item)}
				{#if item.stale}
					<HostUi name="Alert" props={{ variant: 'warning', class: '[&>div]:text-fg', density: 'compact', icon: true }}>
						<div class="flex items-center gap-2">
							<span class="flex-1">{t('inspector.control.stale')}</span>
							{#if owner}<HostUi name="Button" props={{ variant: 'secondary', size: 'xs', disabled: sceneLocked(), onclick: () => renderPlan(owner) }}>{t('inspector.control.rerender')}</HostUi>{/if}
						</div>
					</HostUi>
				{/if}
				<section class="space-y-2">
					<label class="flex items-center gap-2">
						<span class="w-24 shrink-0 text-xs text-fg-muted">{t('inspector.field.name')}</span>
						<input class="input vp-dense min-w-0 flex-1" value={item.name} onchange={(e) => act(() => (item.name = e.currentTarget.value))} />
					</label>
					<div class="flex items-center gap-2 text-xs">
						<span class="w-24 shrink-0 text-fg-muted">{t('inspector.field.source')}</span>
						<HostUi name="Badge" props={{ variant: 'neutral', size: 'md' }}>{item.source === 'scene3d' ? t('inspector.control.scene3d') : t('inspector.control.imported')}</HostUi>
					</div>
					{#if item.source === 'scene3d'}
						<div class="flex items-center gap-2 text-xs">
							<span class="w-24 shrink-0 text-fg-muted">{t('inspector.control.video')}</span>
							<span class="min-w-0 flex-1 truncate {asset(item.assetId) ? 'text-fg' : 'text-fg-subtle'}">{asset(item.assetId)?.name ?? t('inspector.control.noVideo')}</span>
						</div>
						{#if owner}
							<HostUi name="Button" props={{ variant: 'secondary', size: 'xs', icon: 'cube', class: 'w-full', onclick: () => (select('plan3d', owner.id), (ui.workspace = 'scene')) }}>{t('inspector.control.openPlan', { name: owner.name })}</HostUi>
						{/if}
					{/if}
					<NumField label={t('inspector.field.start')} value={item.start} min={0} step={0.04} unit="s" onchange={(v) => set('start', v)} />
					<NumField label={t('inspector.field.duration')} value={item.dur} min={0.3} step={0.04} unit="s" onchange={(v) => set('dur', v)} />
					<SliderField label={t('inspector.field.guidance')} value={item.guidance} unit=" %" onchange={(v) => set('guidance', v)} />
					<p class="text-xs text-fg-subtle">{t('inspector.control.note')}</p>
				</section>
			{:else if s.kind === 'plan3d'}
				{@const control = controlOf(item)}
				{@const planScene = sceneOf(item.sceneId)}
				{@const locked = !sceneReady(planScene) || !item.keyframes.length || sceneLocked()}
				<section class="space-y-2">
					<label class="flex items-center gap-2">
						<span class="w-24 shrink-0 text-xs text-fg-muted">{t('inspector.field.scene')}</span>
						<select class="input vp-dense min-w-0 flex-1" value={item.sceneId ?? ''} disabled={sceneLocked()} onchange={(e) => setPlanScene(item, e.currentTarget.value)}>
							<option value="">{t('inspector.field.noScene')}</option>
							{#each doc.scenes as sc (sc.id)}<option value={sc.id}>{sc.name}</option>{/each}
						</select>
					</label>
					<NumField label={t('inspector.field.start')} value={item.start} min={0} step={0.04} unit="s" onchange={(v) => setPlanStart(item, v)} />
					<NumField label={t('inspector.field.duration')} value={item.dur} min={0.5} step={0.04} unit="s" onchange={(v) => setPlanDur(item, v)} />
					<div class="flex items-center gap-2 text-xs">
						<span class="w-24 shrink-0 text-fg-muted">{t('inspector.plan.path')}</span>
						<span class="min-w-0 flex-1 truncate text-fg">{sourceText(item)}</span>
					</div>
					<div class="flex items-center gap-2 text-xs">
						<span class="w-24 shrink-0 text-fg-muted">{t('inspector.plan.video')}</span>
						<span class="min-w-0 flex-1 truncate {control?.stale ? 'text-warning' : control?.assetId ? 'text-fg' : 'text-fg-subtle'}">
							{control?.stale ? t('inspector.plan.videoStale') : control?.assetId ? t('inspector.plan.videoReady') : t('inspector.plan.videoNone')}
						</span>
					</div>
					<div class="grid grid-cols-2 gap-1.5">
						<HostUi name="Button" props={{ variant: 'secondary', size: 'xs', icon: hostIconName('route'), disabled: locked, onclick: () => renderPlan(item) }}>{t('inspector.plan.render')}</HostUi>
						<HostUi name="Button" props={{ variant: 'secondary', size: 'xs', icon: hostIconName('image'), disabled: locked, onclick: () => useStartEnd(item) }}>{t('inspector.plan.ends')}</HostUi>
					</div>
				</section>
				{@render camera()}
			{:else if s.kind === 'title'}
				<section class="space-y-2">
					<label class="block space-y-1">
						<span class="text-xs text-fg-muted">{t('inspector.field.text')}</span>
						<input class="input vp-dense w-full" value={item.text} onchange={(e) => act(() => (item.text = e.currentTarget.value))} />
					</label>
					<label class="block space-y-1">
						<span class="text-xs text-fg-muted">{t('inspector.field.subtitle')}</span>
						<input class="input vp-dense w-full" value={item.sub} onchange={(e) => act(() => (item.sub = e.currentTarget.value))} />
					</label>
					<NumField label={t('inspector.field.start')} value={item.start} min={0} step={0.04} unit="s" onchange={(v) => set('start', v)} />
					<NumField label={t('inspector.field.duration')} value={item.dur} min={0.3} step={0.04} unit="s" onchange={(v) => set('dur', v)} />
				</section>
			{:else if s.kind === 'marker'}
				<section class="space-y-2">
					<label class="block space-y-1">
						<span class="text-xs text-fg-muted">{t('inspector.field.label')}</span>
						<input class="input vp-dense w-full" value={item.label} onchange={(e) => act(() => (item.label = e.currentTarget.value))} />
					</label>
					<NumField label={t('inspector.field.position')} value={item.time} min={0} step={0.04} unit="s" onchange={(v) => set('time', v)} />
					<HostUi name="Button" props={{ variant: 'secondary', size: 'sm', icon: 'trash', class: 'w-full', onclick: deleteSelection }}>{t('inspector.marker.delete')}</HostUi>
				</section>
			{:else if s.kind === 'reference'}
				{@const refKind = refMediaKind(item.space, item.type)}
				<section class="space-y-2">
					<label class="block space-y-1">
						<span class="text-xs text-fg-muted">{t('inspector.field.name')}</span>
						<input class="input vp-dense w-full" value={item.name} onchange={(e) => act(() => (item.name = e.currentTarget.value))} />
					</label>
					<label class="flex items-center gap-2">
						<span class="w-24 shrink-0 text-xs text-fg-muted">{t('inspector.field.type')}</span>
						<select class="input vp-dense min-w-0 flex-1" value={item.type} onchange={(e) => act(() => (item.type = e.currentTarget.value))}>
							{#each typesOf(item.space) as type (type)}<option value={type}>{refTypeLabel(type)}</option>{/each}
						</select>
					</label>
					{#if refKind === 'audio'}
						<div class="space-y-1">
							<span class="text-xs text-fg-muted">{t('inspector.reference.sound')}</span>
							<AudioPicker title={item.name} value={item.assetId} onpick={(id) => act(() => (item.assetId = id))} />
						</div>
						{@const shot = item.scope?.type === 'shot' ? doc.clips.find((c) => c.id === item.scope.shotId) : (doc.clips.find((c) => c.id === shotIdAt(ui.playhead)) ?? doc.clips[0])}
						{#if item.assetId && shot}<SoundNote behavior={soundBehaviorOf(shot)} />{/if}
					{:else}
						<div class="space-y-1">
							<span class="text-xs text-fg-muted">{refKind === 'video' ? t('inspector.reference.video') : t('inspector.reference.image')}</span>
							<MediaPicker kind={refKind ?? 'image'} title={item.name} value={item.assetId} onpick={(id) => act(() => (item.assetId = id))} />
						</div>
						<label class="flex items-center gap-2">
							<span class="w-24 shrink-0 text-xs text-fg-muted">{t('inspector.field.role')}</span>
							<select class="input vp-dense min-w-0 flex-1" value={item.role} onchange={(e) => act(() => (item.role = e.currentTarget.value))}>
								{#each ['Identité', 'Style', 'Décor', 'Objet', 'Décor 3D', 'Mouvement', 'Caméra'] as r (r)}<option value={r}>{refRoleLabel(r)}</option>{/each}
							</select>
						</label>
					{/if}
					{#if item.file}<div class="text-xs text-fg-subtle">{t('inspector.reference.file', { file: item.file })}</div>{/if}
					<div class="vp-label pt-1">{t('inspector.field.scope')}</div>
					<HostUi name="SegmentedControl" props={{ items: scopes, selected: item.scope.type === 'global' ? 'global' : 'shot', variant: 'toggle', fullWidth: true, ariaLabel: t('inspector.field.scope'), onSelect: setScope }} />
					{#if item.scope.type === 'shot'}
						<label class="flex items-center gap-2">
							<span class="w-24 shrink-0 text-xs text-fg-muted">{t('inspector.field.shot')}</span>
							<select class="input vp-dense min-w-0 flex-1" value={item.scope.shotId} onchange={(e) => act(() => (item.scope = { type: 'shot', shotId: e.currentTarget.value }))}>
								{#each doc.clips as c (c.id)}<option value={c.id}>{clipLabel(c)} · {secs(c.start)}–{secs(c.start + c.dur)}</option>{/each}
							</select>
						</label>
					{/if}
					<HostUi name="Button" props={{ variant: 'secondary', size: 'sm', icon: 'trash', class: 'w-full', onclick: deleteSelection }}>{t('inspector.reference.remove')}</HostUi>
				</section>
			{:else if s.kind === 'lane'}
				<section class="space-y-2">
					<label class="block space-y-1">
						<span class="text-xs text-fg-muted">{t('inspector.field.name')}</span>
						<input class="input vp-dense w-full" value={item.name} onchange={(e) => act(() => (item.name = e.currentTarget.value))} />
					</label>
					<label class="flex items-center gap-2">
						<span class="w-24 shrink-0 text-xs text-fg-muted">{t('inspector.field.role')}</span>
						<select class="input vp-dense min-w-0 flex-1" value={item.role} onchange={(e) => act(() => (item.role = e.currentTarget.value))}>
							{#each ['Dialogue', 'Musique', 'Ambiance', 'SFX'] as r (r)}<option value={r}>{audioRoleLabel(r)}</option>{/each}
						</select>
					</label>
					<div class="flex min-h-6 items-center justify-between gap-2 text-xs text-fg-muted">
						<label for="vp-lane-reference">{t('inspector.lane.reference')}</label>
						<HostUi name="Switch" props={{ id: 'vp-lane-reference', checked: isReferenceLane(item), size: 'lg', label: t('inspector.lane.reference'), onchange: (v) => act(() => setReferenceLane(item, v)) }} />
					</div>
					{#if isReferenceLane(item)}<p class="text-xs text-fg-subtle">{t('inspector.lane.referenceHint')}</p>{/if}
				</section>
				{#each item.inserts as fx, i (i)}
					<section class="space-y-2 rounded-lg border border-line-strong p-2.5">
						<div class="flex items-center justify-between">
							<span class="text-sm font-medium">{fxName(fx.type)}</span>
							<div class="flex min-h-6 items-center gap-2 text-xs text-fg-muted">
								<label for="vp-fx-on-{i}">{t('inspector.fx.active')}</label>
								<HostUi name="Switch" props={{ id: `vp-fx-on-${i}`, checked: fx.on, size: 'lg', label: t('inspector.fx.active'), onchange: (v) => act(() => (fx.on = v)) }} />
							</div>
						</div>
						{#if fx.type === 'eq'}
							<svg viewBox="0 0 100 30" class="h-12 w-full rounded bg-canvas" aria-hidden="true">
								<line x1="0" y1="15" x2="100" y2="15" stroke="rgb(var(--line-hover))" stroke-width="0.4" />
								<path d="M0 {15 - fx.low} C 20 {15 - fx.low}, 25 {15 - fx.mid}, 50 {15 - fx.mid} S 80 {15 - fx.high}, 100 {15 - fx.high}" fill="none" stroke="rgb(var(--signal))" stroke-width="1" />
							</svg>
							<SliderField label={t('inspector.eq.low')} value={fx.low} min={-12} max={12} step={0.5} unit=" dB" onchange={(v) => (fx.low = v)} />
							<SliderField label={t('inspector.eq.mid')} value={fx.mid} min={-12} max={12} step={0.5} unit=" dB" onchange={(v) => (fx.mid = v)} />
							<SliderField label={t('inspector.eq.high')} value={fx.high} min={-12} max={12} step={0.5} unit=" dB" onchange={(v) => (fx.high = v)} />
						{:else if fx.type === 'comp'}
							<SliderField label={t('inspector.comp.threshold')} value={fx.threshold} min={-60} max={0} unit=" dB" onchange={(v) => (fx.threshold = v)} />
							<SliderField label={t('inspector.comp.ratio')} value={fx.ratio} min={1} max={20} step={0.5} format={(v) => `${v}:1`} onchange={(v) => (fx.ratio = v)} />
							<SliderField label={t('inspector.comp.attack')} value={fx.attack} min={1} max={100} unit=" ms" onchange={(v) => (fx.attack = v)} />
							<SliderField label={t('inspector.comp.release')} value={fx.release} min={20} max={1000} step={10} unit=" ms" onchange={(v) => (fx.release = v)} />
						{:else if fx.type === 'filter'}
							<SliderField label={t('inspector.filter.cutoff')} value={fx.cutoff} min={200} max={20000} step={100} unit=" Hz" onchange={(v) => (fx.cutoff = v)} />
						{/if}
					</section>
				{/each}
				<section class="space-y-2">
					<div class="vp-section-title">{t('inspector.section.sends')}</div>
					<SliderField label={t('inspector.send.reverb')} value={item.sends.R1} min={-60} max={0} unit=" dB" onchange={(v) => (item.sends.R1 = v)} />
					<SliderField label={t('inspector.send.delay')} value={item.sends.D1} min={-60} max={0} unit=" dB" onchange={(v) => (item.sends.D1 = v)} />
				</section>
				<section class="space-y-2 border-t border-line pt-3">
					<HostUi name="Button" props={{ variant: 'secondary', size: 'sm', icon: 'trash', class: 'w-full', onclick: () => deleteLane(item.id) }}>{t('inspector.lane.delete', { lane: laneCode(doc.lanes, item.id) })}</HostUi>
					<p class="text-xs text-fg-subtle">{laneItemCount(doc, item.id) ? t('inspector.lane.deleteHint', { count: laneItemCount(doc, item.id) }) : t('inspector.lane.deleteEmpty')}</p>
				</section>
			{/if}
		{/if}
	</div>
</aside>

{#snippet fadeFields(video)}
	<section class="space-y-2">
		<div class="vp-section-title">{t('inspector.section.fades')}</div>
		<NumField label={t('inspector.field.fadeIn')} value={item.fadeIn} min={0} max={fadeMax} step={0.04} unit="s" onchange={(v) => set('fadeIn', v)} />
		<NumField label={t('inspector.field.fadeOut')} value={item.fadeOut} min={0} max={fadeMax} step={0.04} unit="s" onchange={(v) => set('fadeOut', v)} />
		<p class="text-xs text-fg-subtle">{video ? t('inspector.fades.video') : t('inspector.fades.audio')}</p>
	</section>
{/snippet}

{#snippet camera()}
	{@const p = plan ?? (s?.kind === 'plan3d' ? item : null)}
	<section class="space-y-2">
		<div class="flex items-center justify-between gap-2">
			<span class="vp-section-title">{t('inspector.camera.title')}</span>
			{#if ui.scene.keyframe && ui.scene.keyframe !== 'free'}
				<HostUi name="Badge" props={{ variant: 'neutral', size: 'md', class: '!border-signal !text-fg' }}>{t('inspector.camera.keySelected')}</HostUi>
			{:else if ui.scene.keyframe === 'free'}
				<HostUi name="Badge" props={{ variant: 'neutral', size: 'md' }}>{t('scene.freeCamera')}</HostUi>
			{:else}
				<HostUi name="Badge" props={{ variant: 'neutral', size: 'md' }}>{t('inspector.camera.follow')}</HostUi>
			{/if}
		</div>
		{#each camFields as f (f.k)}
			<SliderField label={f.label} value={f.value} min={f.min} max={f.max} step={f.step} unit={f.unit} onchange={(v) => camSet(f.k, v)} />
		{/each}
		<div class="grid grid-cols-2 gap-1.5">
			<HostUi name="Button" props={{ variant: 'secondary', size: 'sm', icon: hostIconName('diamond'), onclick: addKeyframe }}>{t('inspector.camera.addKey')}</HostUi>
			<HostUi name="Button" props={{ variant: 'secondary', size: 'sm', disabled: ui.scene.keyframe == null, onclick: () => (ui.scene.keyframe = null) }}>{t('inspector.camera.followPath')}</HostUi>
		</div>
		<HostUi name="Button" props={{ variant: 'ghost', size: 'xs', icon: hostIconName('target'), class: 'w-full', onclick: resetToSource }}>{t('scene.sourceView')}</HostUi>
	</section>
	{#if p}
		<section class="space-y-1.5">
			<div class="vp-section-title">{t('inspector.camera.keys', { name: p.name })}</div>
			{#if p.source === 'blender'}
				<p class="text-xs text-fg-subtle">{t('inspector.camera.sampled', { count: p.keyframes.length, camera: p.camera ?? '—' })}</p>
			{:else}
				{#each p.keyframes as k (k.id)}
					<div class="flex items-center gap-2 rounded px-2 py-0.5 text-xs {ui.scene.keyframe === k.id ? 'bg-surface-3 text-fg ring-1 ring-inset ring-signal' : 'text-fg-muted hover:bg-surface-2'}">
						<button type="button" class="flex min-h-6 flex-1 items-center gap-2 text-left" aria-pressed={ui.scene.keyframe === k.id} onclick={() => selectKey(p, k)}>
							<Icon name="diamond" class="h-3 w-3" /><span class="vp-tc">{secs(p.start + k.t)}</span><span class="text-fg-muted">{t('inspector.camera.keyMeta', { focal: Math.round(k.focal), dist: formatNumber(distance(k.pos, k.target), { maximumFractionDigits: 2 }) })}</span>
						</button>
						<HostUi name="IconButton" props={{ icon: 'trash', label: t('inspector.camera.deleteKey'), tooltip: t('inspector.camera.deleteKey'), size: 'xs', onclick: () => deleteKeyframe(p, k) }} />
					</div>
				{:else}
					<p class="text-xs text-fg-subtle">{t('inspector.camera.noKeys')}</p>
				{/each}
			{/if}
		</section>
	{/if}
{/snippet}
