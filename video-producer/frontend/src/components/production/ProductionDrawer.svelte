<script>
	import { onMount } from 'svelte';
	import { fade } from 'svelte/transition';
	import HostUi from '../../../../../../sdk/HostUi.svelte';
	import { t } from '../../i18n/index.svelte.js';
	import { ms } from '../../lib/motion.js';
	import { ui, doc, act } from '../../lib/state.svelte.js';
	import { currentEngine, engineGroups, engineLabel, selectEngine, supportedProfiles, soundGuides, openEngineSettings } from '../../lib/production.svelte.js';
	import { chosenSize } from '../../lib/formats.js';
	import { commandById } from '../../lib/commands.js';
	import { hasOwnEngine } from '../../lib/engine.js';
	import { optionCount } from '../../lib/options.js';
	import { MAX_MARGIN, referenceMargin, setReferenceMargin } from '../../lib/sound.js';
	import { overlayLayer } from '../../lib/host.js';
	import { hostIconName } from '../../lib/icons.js';
	import { focusables } from '../../lib/keyboard.js';
	import { closeLayer, closeTopLayer, focusWithRing, isTopLayer, openLayer } from '../../lib/focus.js';
	import { setEngineSize } from '../../lib/framing.svelte.js';
	import { withSendings } from '../../lib/vreftracks.svelte.js';
	import { drawerCloses, drawerPlace, drawerRows, profileControl, profileHint, profileOptions, tabTarget } from '../../lib/deck-drawer.js';
	import Icon from '../Icon.svelte';
	import DraftsField from '../shots/DraftsField.svelte';
	import SizePicker from './SizePicker.svelte';

	let { anchor, toggle = null, clips = [], engineTip = '', onclose } = $props();

	const uid = $props.id();
	const ids = { engine: `${uid}-engine`, profile: `${uid}-profile`, draft: `${uid}-draft`, final: `${uid}-final`, drafts: `${uid}-drafts`, margin: `${uid}-margin` };
	const engine = $derived(currentEngine());
	const groups = $derived(engineGroups());
	const cloud = $derived(engine?.kind === 'cloud');
	const profileItems = $derived(supportedProfiles().map((m) => ({ id: m, label: m })));
	const control = $derived(profileControl({ items: profileItems, current: doc.direction.mode }));
	const options = $derived(profileOptions({ items: profileItems, current: doc.direction.mode }));
	const sizes = $derived(Boolean(engine && !cloud && engine.info?.resolutions?.length));
	const guided = $derived(soundGuides());
	const own = $derived(doc.clips.filter(hasOwnEngine).length);
	const setCount = $derived(optionCount(doc.engine, engine?.preset));
	const editTip = $derived(engine ? t('production.editEngineTip', { engine: engine.label }) : t('production.editEngine'));
	const rows = $derived(drawerRows({ engine: Boolean(engine), profile: profileItems.length > 1 || control === 'popup', sizes, guided, own }));

	let dialog = $state();
	let backdrop = $state();
	let place = $state(null);
	let layer = null;

	function setProfile(m) {
		if (m !== doc.direction.mode) withSendings(() => act(() => (doc.direction.mode = m)));
	}

	function setMargin(value) {
		act(() => setReferenceMargin(doc.engine, value));
	}

	function anchorTo() {
		if (!anchor) return;
		place = drawerPlace({ deck: anchor.getBoundingClientRect(), root: anchor.closest('.vp-root')?.getBoundingClientRect() ?? null });
	}

	function initialFocus() {
		const target = focusables(dialog).find((el) => !el.closest('[data-close]'));
		if (target) focusWithRing(target);
		else dialog.focus();
	}

	function keydown(e) {
		if (e.key === 'Escape') {
			e.preventDefault();
			e.stopPropagation();
			closeTopLayer();
			return;
		}
		if (e.key !== 'Tab') return;
		const target = tabTarget({ shift: e.shiftKey, list: focusables(dialog), active: document.activeElement, inside: dialog.contains(document.activeElement) });
		if (!target) return;
		e.preventDefault();
		target.focus();
	}

	function outside(e) {
		if (!drawerCloses({ target: e.target, dialog, toggle, top: isTopLayer(layer) })) return;
		if (e.target === backdrop) e.preventDefault();
		onclose();
	}

	onMount(() => {
		anchorTo();
		layer = openLayer(dialog, { refocus: initialFocus, close: onclose });
		const frame = requestAnimationFrame(initialFocus);
		window.addEventListener('resize', anchorTo);
		window.addEventListener('scroll', anchorTo, true);
		document.addEventListener('pointerdown', outside, true);
		return () => {
			cancelAnimationFrame(frame);
			window.removeEventListener('resize', anchorTo);
			window.removeEventListener('scroll', anchorTo, true);
			document.removeEventListener('pointerdown', outside, true);
			closeLayer(layer);
		};
	});
</script>

<div bind:this={backdrop} class="vp-deck-backdrop" role="presentation" style:height="{place?.space ?? 0}px" use:overlayLayer in:fade|global={{ duration: ms(120) }}></div>
<div
	bind:this={dialog}
	class="vp-deck-drawer"
	role="dialog"
	aria-modal="true"
	aria-label={t('production.drawer.title')}
	tabindex="-1"
	style:width="{place?.width ?? 0}px"
	style:max-height="{place?.maxHeight ?? 0}px"
	use:overlayLayer
	onkeydown={keydown}
>
	<header class="vp-deck-drawer-header">
		<Icon name="sliders" class="h-4 w-4 shrink-0 text-fg-muted" />
		<div class="vp-deck-drawer-header-copy">
			<h2>{t('production.drawer.title')}<span class="vp-deck-drawer-sub"> {t('production.drawer.subtitle')}</span></h2>
		</div>
		<span data-close>
			<HostUi name="Tooltip" props={{ text: t('production.drawer.close'), kbd: t('commands.kbd.escape'), wrapperClass: 'inline-flex' }}>
				<button type="button" class="vp-deck-drawer-close" aria-label={t('production.drawer.close')} onclick={onclose}><Icon name="x" class="h-4 w-4" /></button>
			</HostUi>
		</span>
	</header>
	<div class="vp-deck-drawer-body">
		<div class="vp-deck-drawer-grid">
			<label class="vp-deck-drawer-label" for={ids.engine}>{t('production.drawer.engine')}</label>
			<div class="vp-deck-drawer-row">
				<HostUi name="Tooltip" props={{ text: engineTip, wrapperClass: 'flex w-full min-w-0 items-center' }}>
					<select id={ids.engine} class="vp-popup w-full min-w-0" value={engine?.key ?? ''} disabled={!groups.length} aria-label={t('production.engine.label')} onchange={(e) => selectEngine(e.currentTarget.value)}>
						{#if !engine}<option value="" disabled>{groups.length ? engineLabel() : t('generation.engine.none')}</option>{/if}
						{#each groups as g (g.label)}
							<optgroup label={g.label}>
								{#each g.options as o (o.key)}<option value={o.key}>{o.label}</option>{/each}
							</optgroup>
						{/each}
					</select>
				</HostUi>
			</div>

			{#if rows.includes('profile')}
				<span class="vp-deck-drawer-label" id={ids.profile}>{t('production.profile.label')}</span>
				<div class="vp-deck-drawer-row">
					<HostUi name="Tooltip" props={{ text: profileHint(doc.direction.mode, t), wrapperClass: 'inline-flex min-w-0' }}>
						{#if control === 'popup'}
							<select class="vp-popup min-w-0" value={doc.direction.mode} aria-labelledby={ids.profile} onchange={(e) => setProfile(e.currentTarget.value)}>
								{#each options as o (o.id)}<option value={o.id} disabled={o.unsupported}>{o.unsupported ? t('production.drawer.unsupported', { profile: o.label }) : o.label}</option>{/each}
							</select>
						{:else}
							<HostUi name="SegmentedControl" props={{ items: profileItems, selected: doc.direction.mode, variant: 'toggle', ariaLabel: t('production.profile.label'), onSelect: setProfile }} />
						{/if}
					</HostUi>
				</div>
			{/if}

			{#if rows.includes('draftSize')}
				<label class="vp-deck-drawer-label" for={ids.draft}>{t('production.drawer.draftSize')}</label>
				<div class="vp-deck-drawer-row">
					<SizePicker preset={engine.info} quality="draft" backend={engine.backend} value={chosenSize(doc, engine.preset, 'draft')} onselect={(v) => setEngineSize(engine.preset, 'draft', v)} variant="field" triggerId={ids.draft} />
				</div>
				<label class="vp-deck-drawer-label" for={ids.final}>{t('production.drawer.finalSize')}</label>
				<div class="vp-deck-drawer-row">
					<SizePicker preset={engine.info} quality="final" backend={engine.backend} value={chosenSize(doc, engine.preset, 'final')} onselect={(v) => setEngineSize(engine.preset, 'final', v)} variant="field" triggerId={ids.final} />
				</div>
			{/if}

			<label class="vp-deck-drawer-label" for={ids.drafts}>{t('production.drawer.drafts')}</label>
			<div class="vp-deck-drawer-row">
				<DraftsField {clips} label={false} disabled={!clips.length} id={ids.drafts} />
				<span class="vp-deck-drawer-hint">{t('production.drawer.draftsHint')}</span>
			</div>

			{#if rows.includes('margin')}
				<label class="vp-deck-drawer-label" for={ids.margin}>{t('production.drawer.margin')}</label>
				<div class="vp-deck-drawer-row">
					<HostUi name="Tooltip" props={{ text: t('production.margin.tip'), wrapperClass: 'inline-flex items-center gap-1.5' }}>
						<input id={ids.margin} class="input vp-dense vp-tc w-16" type="number" min="0" max={MAX_MARGIN} step="0.5" value={referenceMargin(doc.engine)} aria-label={t('production.margin.label')} onchange={(e) => setMargin(e.currentTarget.value)} />
						<span class="vp-deck-drawer-hint">{t('production.margin.unit')}</span>
					</HostUi>
					<span class="vp-deck-drawer-hint">{t('production.drawer.marginHint')}</span>
				</div>
			{/if}

			{#if rows.includes('own')}
				<p class="vp-deck-drawer-help">{t('production.drawer.own', { count: own })}</p>
			{/if}

			<span class="vp-deck-drawer-label"></span>
			<div class="vp-deck-drawer-row">
				<HostUi name="Tooltip" props={{ text: editTip, kbd: commandById('engine')?.key, wrapperClass: 'inline-flex' }}>
					<HostUi name="Button" props={{ variant: 'secondary', size: 'sm', icon: hostIconName('sliders'), onclick: () => openEngineSettings(engine?.preset) }}>
						{t('production.editEngine')}{#if setCount}<span class="vp-deck-badge vp-tc ml-1.5">{setCount}</span>{/if}
					</HostUi>
				</HostUi>
			</div>
		</div>
	</div>
</div>
