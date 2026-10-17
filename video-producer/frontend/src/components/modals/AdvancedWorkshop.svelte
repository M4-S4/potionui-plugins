<script>
	import HostUi from '../../../../../../sdk/HostUi.svelte';
	import { formatNumber, getLocale, t } from '../../i18n/index.svelte.js';
	import { ui, doc, act, toast, globalPrompt, secs, checkpoint, fmtDuration } from '../../lib/state.svelte.js';
	import { readiness, startGeneration, engineChoices, currentEngine, selectEngine, supportedProfiles, estimateState } from '../../lib/production.svelte.js';
	import { modeLabel, audioRoleLabel } from '../../lib/catalog.js';
	import { hostIconName } from '../../lib/icons.js';
	import { ulid } from '../../lib/ulid.js';
	import Modal from './Modal.svelte';
	import Icon from '../Icon.svelte';
	import InfoTip from '../shell/InfoTip.svelte';

	let { step: initial = 0, focus = null } = $props();
	let step = $state(firstStep());
	let expert = $state(false);
	let profileName = $state('');
	const e = $derived(doc.engine);

	function firstStep() {
		return Math.max(0, Math.min(2, Number(initial) || 0));
	}

	const steps = $derived([
		{ title: t('modals.advanced.step.sources'), hint: t('modals.advanced.step.sourcesHint') },
		{ title: t('modals.advanced.step.engine'), hint: t('modals.advanced.step.engineHint') },
		{ title: t('modals.advanced.step.delivery'), hint: t('modals.advanced.step.deliveryHint') }
	]);

	function reveal(el) {
		if (focus !== 'hybrid') return;
		const frame = requestAnimationFrame(() => el.scrollIntoView?.({ block: 'start' }));
		return { destroy: () => cancelAnimationFrame(frame) };
	}

	const ready = $derived(readiness());
	const r = $derived(ready.range);

	const windows = $derived.by(() => {
		const out = [];
		const len = Math.max(1, e.windowLen);
		let at = r[0];
		while (at < r[1] - 0.01 && out.length < 12) {
			out.push([at, Math.min(r[1], at + len)]);
			at += len - Math.min(e.overlap, len - 0.5);
		}
		return out;
	});

	const components = $derived([
		{ k: 'continuite', label: t('modals.hybrid.continuite'), src: 'FL2VA', help: t('modals.hybrid.continuiteHelp') },
		{ k: 'identite', label: t('modals.hybrid.identite'), src: 'Ref2VA', help: t('modals.hybrid.identiteHelp') },
		{ k: 'audio', label: t('modals.hybrid.audio'), src: 'Hybrid AV', help: t('modals.hybrid.audioHelp') },
		{ k: 'mouvement', label: t('modals.hybrid.mouvement'), src: 'Control video', help: t('modals.hybrid.mouvementHelp') },
		{ k: 'style', label: t('modals.hybrid.style'), src: t('modals.hybrid.direction'), help: t('modals.hybrid.styleHelp') }
	]);
	const profileItems = $derived(['FL2VA', 'Ref2VA', 'Hybrid AV'].map((m) => ({ id: m, label: m, disabled: !supportedProfiles().includes(m) })));
	const options = $derived(engineChoices());
	const current = $derived(currentEngine());
	const one = (v) => formatNumber(v ?? 0, { minimumFractionDigits: 1, maximumFractionDigits: 1 });
	const qualities = $derived([
		{ id: 'draft', label: t('modals.advanced.draft') },
		{ id: 'final', label: t('modals.advanced.final') }
	]);

	function word(v) {
		if (v >= 75) return t('modals.hybrid.strong');
		if (v >= 50) return t('modals.hybrid.medium');
		if (v >= 25) return t('modals.hybrid.light');
		return t('modals.hybrid.ignored');
	}

	const intent = $derived.by(() => {
		const lower = (s) => s.toLocaleLowerCase(getLocale());
		const sorted = components.map((c) => ({ ...c, v: doc.hybrid[c.k] })).sort((a, b) => b.v - a.v);
		return t('modals.hybrid.intent', { first: lower(sorted[0].label), firstWeight: word(sorted[0].v), second: lower(sorted[1].label), last: sorted[4].label, lastWeight: word(sorted[4].v) });
	});

	function engineMeta(o) {
		const backend = (ui.me?.engines ?? []).find((x) => x.id === o.backend);
		const vram = backend && backend.kind !== 'cloud' && backend.vramFree != null && backend.vramTotal != null ? t('generation.engine.vram', { free: one(backend.vramFree), total: one(backend.vramTotal) }) : '';
		return [o.group, vram].filter(Boolean).join(' · ');
	}

	function currentEstimate() {
		const seconds = estimateState.data?.time.seconds;
		return seconds != null ? `≈ ${fmtDuration(seconds)}` : '—';
	}

	function saveProfile() {
		const name = profileName.trim() || t('modals.advanced.defaultProfile', { n: doc.profiles.length + 1 });
		act(() => doc.profiles.push({ id: ulid(), name, weights: { ...doc.hybrid } }));
		profileName = '';
		toast(t('modals.advanced.profileSaved', { name }));
	}

	function applyProfile(p) {
		act(() => Object.assign(doc.hybrid, p.weights));
		toast(t('modals.advanced.profileApplied', { name: p.name }));
	}

	function go(target) {
		ui.modal = null;
		Object.assign(ui, target);
	}

	function generate() {
		ui.modal = null;
		startGeneration();
	}
</script>

<Modal title={t('modals.advanced.title')} subtitle={t('modals.advanced.subtitle', { start: secs(r[0]), end: secs(r[1]), mode: modeLabel(ui.production.mode) })} icon="sliders" width={980}>
	<div class="grid h-[540px] grid-cols-[220px_1fr]">
		<ol class="space-y-0.5 border-r border-line p-3" aria-label={t('modals.advanced.stepsNav')}>
			{#each steps as s, i (i)}
				<li>
					<button
						type="button"
						class="flex h-12 w-full items-center gap-2.5 rounded-lg border px-2 text-left text-sm {step === i ? 'border-signal bg-surface-2 text-fg' : 'border-transparent text-fg-muted hover:bg-surface-2'}"
						onclick={() => (step = i)}
						aria-current={step === i ? 'step' : undefined}
					>
						<span class="flex h-5 w-5 shrink-0 items-center justify-center rounded-full border text-xs {step === i ? 'border-signal bg-surface-1 text-signal' : i < step ? 'border-success text-success' : 'border-line-hover'}">
							{#if i < step}<Icon name="check" class="h-3 w-3" />{:else}{i + 1}{/if}
						</span>
						<span class="min-w-0"><span class="block">{s.title}</span><span class="block text-xs text-fg-muted">{s.hint}</span></span>
					</button>
				</li>
			{/each}
		</ol>

		<div class="min-h-0 space-y-5 overflow-auto p-5">
			<h3 class="text-lg font-semibold">{steps[step].title}</h3>

			{#if step === 0}
				<div class="rounded-lg border border-line-strong p-3">
					<div class="mb-1 flex items-center justify-between">
						<span class="text-sm font-medium">{t('modals.advanced.global')}</span>
						<button type="button" class="vp-link-hit text-xs text-signal hover:underline" onclick={() => go({ workspace: 'director', dockTab: 'direction' })}>{t('modals.advanced.edit')}</button>
					</div>
					<p class="line-clamp-3 text-xs text-fg-muted">{globalPrompt()}</p>
				</div>
				<div class="grid grid-cols-3 gap-3 text-sm">
					<div class="rounded-lg border border-line-strong p-3"><div class="text-xl font-semibold">{ready.items.prompts.length}</div><div class="text-xs text-fg-subtle">{t('modals.advanced.statPrompts', { count: ready.items.prompts.length })}</div></div>
					<div class="rounded-lg border border-line-strong p-3"><div class="text-xl font-semibold">{ready.items.frames.length}</div><div class="text-xs text-fg-subtle">{t('modals.advanced.statFrames', { count: ready.items.frames.length })}</div></div>
					<div class="rounded-lg border border-line-strong p-3"><div class="text-xl font-semibold">{ready.items.references.length}</div><div class="text-xs text-fg-subtle">{t('modals.advanced.statReferences', { count: ready.items.references.length })}</div></div>
				</div>
				{@render unsentSlider(t('modals.advanced.consistency'), e.consistency, (v) => (e.consistency = v), 0, 100, 1, ' %', t('modals.advanced.consistencyHelp'))}
				{@render unsentToggle(t('modals.advanced.lockIdentity'), e.lockIdentity, (v) => (e.lockIdentity = v), t('modals.advanced.lockIdentityHelp'))}
				<div class="h-px bg-line"></div>
				<h4 class="text-md font-semibold">{t('modals.advanced.motion')}</h4>
				{#if ready.items.controls.length || ready.items.plans3d.length}
					<ul class="space-y-2">
						{#each ready.items.controls as c (c.id)}
							<li class="flex items-center gap-3 rounded-lg border border-line-strong p-3">
								<Icon name="route" class="h-4 w-4 text-fg-muted" />
								<div class="flex-1">
									<div class="text-sm">{c.name}</div>
									<div class="text-xs text-fg-subtle">
										{[`${secs(c.start)}–${secs(c.start + c.dur)}`, c.source === 'scene3d' ? t('modals.advanced.fromScene') : t('modals.advanced.imported'), c.stale ? t('modals.advanced.stale') : ''].filter(Boolean).join(' · ')}
									</div>
								</div>
								<input class="vp-slider !w-32" type="range" min="0" max="100" value={c.guidance} onpointerdown={checkpoint} oninput={(ev) => (c.guidance = +ev.currentTarget.value)} aria-label={t('modals.advanced.guidance')} />
								<span class="vp-tc w-10 text-right text-xs">{c.guidance} %</span>
							</li>
						{/each}
						{#each ready.items.plans3d as p (p.id)}
							<li class="flex items-center gap-3 rounded-lg border border-line-strong p-3">
								<Icon name="cube" class="h-4 w-4 text-fg-muted" />
								<div class="flex-1"><div class="text-sm">{p.name}</div><div class="text-xs text-fg-subtle">{t('modals.advanced.keyframes', { count: p.keyframes.length })}</div></div>
								<HostUi name="Button" props={{ variant: 'secondary', size: 'xs', onclick: () => go({ workspace: 'scene' }) }}>{t('modals.advanced.openScene')}</HostUi>
							</li>
						{/each}
					</ul>
				{:else}
					<div class="flex items-center gap-3 rounded-lg border border-dashed border-line-hover p-3">
						<Icon name="route" class="h-4 w-4 shrink-0 text-fg-muted" />
						<p class="min-w-0 flex-1 text-sm text-fg-muted">{t('modals.advanced.noGuide')}</p>
						<HostUi name="Button" props={{ variant: 'secondary', size: 'xs', class: 'shrink-0', onclick: () => go({ workspace: 'scene' }) }}>{t('modals.advanced.prepareCamera')}</HostUi>
					</div>
				{/if}
				{@render unsentToggle(t('modals.advanced.motionPriority'), e.motionPriority, (v) => (e.motionPriority = v), t('modals.advanced.motionPriorityHelp'))}
			{:else if step === 1}
				<div>
					<div class="vp-label mb-1.5">{t('modals.advanced.engine')}</div>
					{#if options.length}
						<div class="grid grid-cols-3 gap-2" role="radiogroup" aria-label={t('modals.advanced.engine')}>
							{#each options as o (o.key)}
								{@const on = current?.key === o.key}
								<button
									type="button"
									role="radio"
									class="min-w-0 rounded-xl border p-3 text-left transition-colors {on ? 'border-signal ring-1 ring-signal' : 'border-line-strong hover:border-line-hover'}"
									aria-checked={on}
									onclick={() => selectEngine(o.key)}
								>
									<span class="block truncate text-sm font-medium">{o.label}</span>
									<span class="block truncate text-xs text-fg-subtle">{engineMeta(o)}</span>
									{#if on}<span class="vp-tc mt-2 block text-xs text-fg-muted">{currentEstimate()}</span>{/if}
								</button>
							{/each}
						</div>
					{:else}
						<p class="rounded-lg border border-dashed border-line-hover p-3 text-sm text-fg-muted">
							{t('generation.engine.empty')}
							{#if ui.isAdmin}<a class="vp-link-hit text-fg underline decoration-signal underline-offset-2 hover:decoration-2" href="/admin?tab=plugins">{t('generation.engine.settings')}</a>{/if}
						</p>
					{/if}
				</div>
				<div>
					<div class="vp-label mb-1.5">{t('modals.advanced.mode')}</div>
					<HostUi name="SegmentedControl" props={{ items: profileItems, selected: doc.direction.mode, variant: 'toggle', ariaLabel: t('modals.advanced.mode'), onSelect: (m) => act(() => (doc.direction.mode = m)) }} />
				</div>
				<div class="grid grid-cols-3 gap-3">
					<div class="space-y-1">
						<span class="vp-label block">{t('modals.advanced.quality')}</span>
						<HostUi name="SegmentedControl" props={{ items: qualities, selected: ui.production.quality, variant: 'toggle', fullWidth: true, ariaLabel: t('modals.advanced.quality'), onSelect: (q) => (ui.production.quality = q) }} />
						<span class="block text-xs text-fg-subtle">{ui.production.quality === 'draft' ? t('modals.advanced.draftHint') : t('modals.advanced.finalHint')}</span>
					</div>
					<div class="space-y-1">
						<label class="vp-label block" for="vp-aw-resolution">{t('modals.advanced.resolution')}</label>
						<select id="vp-aw-resolution" class="input vp-dense w-full disabled:opacity-50" disabled bind:value={e.resolution}><option value="720p">720p</option><option value="1080p">1080p</option><option value="4K">4K</option></select>
						{@render unsent()}
					</div>
					<label class="space-y-1">
						<span class="vp-label block">{t('modals.advanced.variants')}</span>
						<input class="input vp-dense vp-tc w-full" type="number" min="1" max="4" bind:value={e.variants} />
					</label>
				</div>
				<div>
					<div class="mb-1.5 flex items-center justify-between gap-2">
						<span class="flex items-center gap-2"><span class="vp-label">{t('modals.advanced.windows')}</span>{@render unsent()}</span>
						<span class="text-xs text-fg-subtle">{t('modals.advanced.windowCount', { count: windows.length })}</span>
					</div>
					<div class="relative h-14 rounded-lg border border-line-strong bg-canvas opacity-50">
						{#each windows as [a, b], i (i)}
							<div
								class="absolute h-4 rounded-sm border border-signal/60 bg-signal/20"
								style:left="{((a - r[0]) / Math.max(0.001, r[1] - r[0])) * 100}%"
								style:width="{((b - a) / Math.max(0.001, r[1] - r[0])) * 100}%"
								style:top="{8 + (i % 2) * 22}px"
							></div>
						{/each}
					</div>
					<div class="mt-2 grid grid-cols-2 gap-3">
						{@render unsentSlider(t('modals.advanced.windowLen'), e.windowLen, (v) => (e.windowLen = v), 2, 10, 0.5, ' s')}
						{@render unsentSlider(t('modals.advanced.overlap'), e.overlap, (v) => (e.overlap = v), 0, 3, 0.25, ' s')}
					</div>
				</div>
				<button type="button" class="flex min-h-6 items-center gap-1.5 text-sm text-fg-muted hover:text-fg" onclick={() => (expert = !expert)} aria-expanded={expert}>
					<Icon name={expert ? 'chevron-down' : 'chevron-right'} class="h-4 w-4" />{t('modals.advanced.expert')}
				</button>
				{#if expert}
					{@render unsent()}
					<div class="grid grid-cols-3 gap-3">
						<div class="space-y-1">
							<label class="vp-label block" for="vp-aw-seed">{t('modals.advanced.seed')}</label>
							<div class="flex gap-1">
								<input id="vp-aw-seed" class="input vp-dense vp-tc min-w-0 flex-1 disabled:opacity-50" type="number" disabled bind:value={e.seed} />
								<HostUi name="IconButton" props={{ icon: 'refresh', label: t('modals.advanced.randomSeed'), tooltip: t('modals.advanced.randomSeed'), size: 'xs', disabled: true, onclick: () => (e.seed = Math.floor(Math.random() * 99999)) }} />
							</div>
						</div>
						<label class="space-y-1"><span class="vp-label block">{t('modals.advanced.steps')}</span><input class="input vp-dense vp-tc w-full disabled:opacity-50" type="number" min="8" max="80" disabled bind:value={e.steps} /></label>
						<label class="space-y-1"><span class="vp-label block">{t('modals.advanced.cfg')}</span><input class="input vp-dense vp-tc w-full disabled:opacity-50" type="number" min="1" max="15" step="0.5" disabled bind:value={e.guidance} /></label>
					</div>
					<div>
						<div class="mb-1.5 flex items-center justify-between">
							<span class="vp-label">{t('modals.advanced.loras')}</span>
							<HostUi name="Button" props={{ variant: 'ghost', size: 'xs', icon: 'plus', disabled: true, onclick: () => e.loras.push({ name: t('modals.advanced.newLora'), weight: 0.5 }) }}>{t('modals.advanced.add')}</HostUi>
						</div>
						<ul class="space-y-1.5">
							{#each e.loras as l, i (i)}
								<li class="flex items-center gap-2">
									<input class="input vp-dense w-48 disabled:opacity-50" disabled bind:value={l.name} aria-label={t('modals.advanced.loraName')} />
									<input class="vp-slider flex-1 disabled:cursor-not-allowed disabled:opacity-50" type="range" min="0" max="1.5" step="0.05" disabled bind:value={l.weight} aria-label={t('modals.advanced.weight')} />
									<span class="vp-tc w-10 text-xs">{formatNumber(+l.weight, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}</span>
									<HostUi name="IconButton" props={{ icon: 'trash', label: t('modals.advanced.remove'), tooltip: t('modals.advanced.remove'), size: 'xs', disabled: true, onclick: () => e.loras.splice(i, 1) }} />
								</li>
							{/each}
						</ul>
					</div>
				{/if}
				<div class="h-px bg-line"></div>
				<h4 class="text-md font-semibold" use:reveal>{t('modals.advanced.hybrid')}</h4>
				<p class="text-sm text-fg-muted">{t('modals.advanced.hybridIntro')}</p>
				<div class="grid grid-cols-[1fr_240px] gap-5">
					<div class="space-y-3">
						{#each components as c (c.k)}
							<div>
								<div class="flex items-center gap-2">
									<span class="text-sm">{c.label}</span>
									<HostUi name="Badge" props={{ variant: 'neutral', size: 'md' }}>{c.src}</HostUi>
									<span class="vp-tc ml-auto text-xs">{doc.hybrid[c.k]} %</span>
								</div>
								<input class="vp-slider" type="range" min="0" max="100" value={doc.hybrid[c.k]} onpointerdown={checkpoint} oninput={(ev) => (doc.hybrid[c.k] = +ev.currentTarget.value)} aria-label={c.label} />
								<div class="text-xs text-fg-subtle">{c.help}</div>
							</div>
						{/each}
						<div class="rounded-lg border border-signal/40 bg-signal/5 p-3 text-sm text-fg">{intent}</div>
					</div>
					<div>
						<div class="vp-section-title mb-1.5">{t('modals.advanced.profiles')}</div>
						<ul class="mb-3 space-y-1">
							{#each doc.profiles as p (p.id)}
								<li>
									<button type="button" class="flex min-h-8 w-full items-center rounded px-2 py-1.5 text-left text-sm hover:bg-surface-2" onclick={() => applyProfile(p)}>
										<span class="flex-1">{p.name}</span><span class="text-xs text-fg-muted">{t('modals.advanced.apply')}</span>
									</button>
								</li>
							{/each}
						</ul>
						<input class="input vp-dense mb-1.5 w-full" placeholder={t('modals.advanced.profileName')} bind:value={profileName} aria-label={t('modals.advanced.profileName')} />
						<HostUi name="Button" props={{ variant: 'secondary', size: 'sm', icon: hostIconName('save'), class: 'w-full', onclick: saveProfile }}>{t('modals.advanced.saveProfile')}</HostUi>
					</div>
				</div>
			{:else}
				<div class="max-w-sm space-y-1">
					<span class="flex items-center gap-2"><label class="vp-label" for="vp-aw-audio-driver">{t('modals.advanced.audioDriver')}</label>{@render unsent()}</span>
					<select id="vp-aw-audio-driver" class="input vp-dense w-full disabled:opacity-50" disabled bind:value={e.audioDriver}>
						{#each doc.lanes as l (l.id)}<option value={l.id}>{l.id} · {l.name} ({audioRoleLabel(l.role)})</option>{/each}
						<option value="">{t('modals.advanced.none')}</option>
					</select>
				</div>
				{@render unsentToggle(t('modals.advanced.lipSync'), e.lipSync, (v) => (e.lipSync = v), t('modals.advanced.lipSyncHelp'))}
				{@render unsentToggle(t('modals.advanced.followCut'), e.followCut, (v) => (e.followCut = v), t('modals.advanced.followCutHelp'))}
				{@render unsentSlider(t('modals.advanced.offset'), e.offset, (v) => (e.offset = v), -200, 200, 10, ' ms')}
				{#if doc.direction.mode !== 'Hybrid AV'}<p class="text-xs text-fg-subtle">{t('modals.advanced.hybridTip')}</p>{/if}
				<div class="h-px bg-line"></div>
				<h4 class="text-md font-semibold">{t('modals.advanced.delivery')}</h4>
				<div class="grid grid-cols-2 gap-3">
					<label class="space-y-1"><span class="vp-label block">{t('modals.advanced.variants')}</span><input class="input vp-dense vp-tc w-full" type="number" min="1" max="4" bind:value={e.variants} /></label>
					<div class="space-y-1">
						<span class="flex items-center gap-2"><label class="vp-label" for="vp-aw-naming">{t('modals.advanced.naming')}</label>{@render unsent()}</span>
						<input id="vp-aw-naming" class="input vp-dense w-full disabled:opacity-50" disabled bind:value={e.naming} />
					</div>
				</div>
				<div class="space-y-2">
					<div class="vp-label">{t('modals.advanced.post')}</div>
					{@render unsentToggle(t('modals.advanced.interpolation'), e.post.interpolation, (v) => (e.post.interpolation = v))}
					{@render unsentToggle(t('modals.advanced.denoise'), e.post.denoise, (v) => (e.post.denoise = v))}
					{@render unsentToggle(t('modals.advanced.upscale'), e.post.upscale, (v) => (e.post.upscale = v), t('modals.advanced.upscaleHelp'))}
				</div>
				{@render unsentToggle(t('modals.advanced.autoInsert'), e.autoInsert, (v) => (e.autoInsert = v))}
				<HostUi name="Button" props={{ variant: 'secondary', size: 'sm', icon: hostIconName('export'), onclick: () => (ui.modal = { type: 'export' }) }}>{t('modals.advanced.prepareDelivery')}</HostUi>
			{/if}
		</div>
	</div>
	{#snippet footer()}
		<HostUi name="Button" props={{ variant: 'ghost', size: 'sm', icon: 'chevron-left', class: 'mr-auto', disabled: step === 0, onclick: () => (step = Math.max(0, step - 1)) }}>{t('modals.advanced.previous')}</HostUi>
		{#if step < steps.length - 1}
			<HostUi name="Button" props={{ variant: 'secondary', size: 'sm', onclick: () => (step += 1) }}>
				{t('modals.advanced.next')}<Icon name="chevron-right" class="h-3.5 w-3.5" />
			</HostUi>
		{/if}
		<HostUi name="Button" props={{ variant: 'secondary', size: 'sm', onclick: () => (ui.modal = null) }}>{t('modals.advanced.close')}</HostUi>
		<HostUi name="Tooltip" props={{ text: ready.missing[0] ?? (ui.production.mode === 'Rendu 3D' ? t('production.prepareRender') : t('production.generate')) }}>
			<HostUi name="Button" props={{ variant: 'primary', size: 'sm', icon: 'sparkles', disabled: ready.missing.length > 0, onclick: generate }}>
				{ui.production.mode === 'Rendu 3D' ? t('production.prepareRender') : t('production.generate')}
			</HostUi>
		</HostUi>
	{/snippet}
</Modal>

{#snippet unsent()}
	<InfoTip lines={[t('generation.workshop.notSentWhy')]} wrapperClass="inline-flex shrink-0">
		<span class="vp-sim"><Icon name="flask" class="h-3 w-3" />{t('generation.workshop.notSent')}</span>
	</InfoTip>
{/snippet}

{#snippet unsentSlider(label, value, set, min, max, stepSize, unit, help = '')}
	<div class="max-w-md">
		<div class="flex items-center justify-between gap-2"><span class="flex items-center gap-2 text-sm">{label}{@render unsent()}</span><span class="vp-tc text-xs">{formatNumber(value)}{unit}</span></div>
		<input class="vp-slider disabled:cursor-not-allowed disabled:opacity-50" type="range" disabled {min} {max} step={stepSize} {value} onpointerdown={checkpoint} oninput={(ev) => set(+ev.currentTarget.value)} aria-label={label} />
		{#if help}<div class="text-xs text-fg-subtle">{help}</div>{/if}
	</div>
{/snippet}

{#snippet unsentToggle(label, value, set, help = '')}
	<div class="flex max-w-lg items-start gap-3">
		<span class="mt-0.5 inline-flex shrink-0">
			<HostUi name="Switch" props={{ checked: value, size: 'lg', label, disabled: true, onchange: (v) => set(v) }} />
		</span>
		<span><span class="flex items-center gap-2 text-sm">{label}{@render unsent()}</span>{#if help}<span class="block text-xs text-fg-subtle">{help}</span>{/if}</span>
	</div>
{/snippet}
