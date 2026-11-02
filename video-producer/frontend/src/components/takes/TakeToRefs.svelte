<script>
	import HostUi from '../../../../../../sdk/HostUi.svelte';
	import { t } from '../../i18n/index.svelte.js';
	import { ui } from '../../lib/state.svelte.js';
	import { overlayLayer } from '../../lib/host.js';
	import { heardSound } from '../../lib/sources.svelte.js';
	import { MAX_VREF_TRACKS } from '../../lib/vrefs.js';
	import { vrefLabel } from '../../lib/vreftracks.js';
	import { roleLabel, sendTakeToTrack, takeChoices, trackName } from '../../lib/vreftracks.svelte.js';
	import Icon from '../Icon.svelte';

	let { take, clip } = $props();

	const id = $derived(`take-refs:${take.id}`);
	const open = $derived(ui.menuOpen === id);
	let at = $state({ x: 0, y: 0 });
	let move = $state(true);
	const choices = $derived(open ? takeChoices(take, clip) : null);
	const moving = $derived(Boolean(choices?.placed) && move);
	const heard = $derived(open ? heardSound(take.url) : null);
	const sound = $derived(ui.vrefSound === true && heard !== false);
	const verb = (track) => (moving ? t('generation.card.refs.moveTo', { track }) : t('generation.card.refs.copyTo', { track }));

	function toggle(e) {
		if (open) return void (ui.menuOpen = null);
		const r = e.currentTarget.getBoundingClientRect();
		at = { x: r.left, y: r.bottom + 4 };
		move = true;
		ui.menuOpen = id;
	}

	function place(node, where) {
		const r = node.getBoundingClientRect();
		node.style.left = `${Math.min(Math.max(where.x, 8), window.innerWidth - r.width - 8)}px`;
		node.style.top = `${Math.min(Math.max(where.y, 8), window.innerHeight - r.height - 8)}px`;
		node.querySelector('[role="menuitem"], [role="menuitemradio"], [role="menuitemcheckbox"]')?.focus();
	}

	function send(trackId) {
		ui.menuOpen = null;
		sendTakeToTrack(take, { trackId, move: moving, sound });
	}

	function toggleSound() {
		if (heard !== false) ui.vrefSound = !ui.vrefSound;
	}
</script>

<span class="inline-flex" data-vp-menu>
	<HostUi
		name="IconButton"
		props={{ icon: 'film', label: t('generation.card.refs.open', { variant: take.variant }), tooltip: t('generation.card.refs.tip'), size: 'xs', ariaExpanded: open, 'aria-haspopup': 'menu', onclick: toggle }}
	/>
</span>

{#if open && choices}
	{#key at}
		<div class="vp-menu w-72" style:position="fixed" style:left="{at.x}px" style:top="{at.y}px" role="menu" aria-label={t('generation.card.refs.menu', { variant: take.variant })} data-vp-menu data-take-refs={take.id} use:overlayLayer use:place={at}>
			<div class="px-2 pb-1 pt-0.5 text-2xs font-medium text-fg-subtle">{t('generation.card.refs.title')}</div>
			{#if choices.placed}
				<button type="button" role="menuitemradio" aria-checked={moving} onclick={() => (move = true)}>
					<Icon name="check" class="h-3.5 w-3.5 {moving ? 'text-fg' : 'opacity-0'}" /><span class="flex-1">{t('generation.card.refs.move')}</span><span class="vp-menu-key">{t('generation.card.refs.moveKey', { shot: choices.shot })}</span>
				</button>
				<button type="button" role="menuitemradio" aria-checked={!moving} onclick={() => (move = false)}>
					<Icon name="check" class="h-3.5 w-3.5 {moving ? 'opacity-0' : 'text-fg'}" /><span class="flex-1">{t('generation.card.refs.copy')}</span><span class="vp-menu-key">{t('generation.card.refs.copyKey', { shot: choices.shot })}</span>
				</button>
				<div class="vp-menu-sep" role="separator"></div>
			{/if}
			<button type="button" role="menuitemcheckbox" aria-checked={sound} aria-disabled={heard === false ? 'true' : null} class={heard === false ? 'opacity-50' : ''} onclick={toggleSound}>
				<Icon name="check" class="h-3.5 w-3.5 {sound ? 'text-fg' : 'opacity-0'}" /><span class="flex-1">{t('generation.card.refs.sound')}</span>
			</button>
			<p class="px-2 pb-1.5 pl-8 text-2xs text-fg-subtle" style:max-width="18rem">{heard === false ? t('generation.card.refs.silent') : heard === null ? t('generation.card.refs.listening') : t('generation.card.refs.soundHint')}</p>
			<div class="vp-menu-sep" role="separator"></div>
			{#each choices.targets as target (target.track.id)}
				<button type="button" role="menuitem" aria-disabled={target.busy ? 'true' : null} class={target.busy ? 'opacity-50' : ''} data-take-target={target.track.slot} onclick={() => !target.busy && send(target.track.id)}>
					<Icon name="film" class="h-3.5 w-3.5 text-fg-muted" /><span class="min-w-0 flex-1 truncate">{verb(trackName(target.track))}</span><span class="vp-menu-key">{roleLabel(target.track.role)}</span>
				</button>
				{#if target.busy}<p class="px-2 pb-1.5 pl-8 text-2xs text-fg-subtle" style:max-width="18rem">{target.reason}</p>{/if}
			{/each}
			{#if choices.slot === null}
				<button type="button" role="menuitem" aria-disabled="true" class="opacity-50" data-take-target="new">
					<Icon name="plus" class="h-3.5 w-3.5 text-fg-muted" /><span class="flex-1">{t('generation.card.refs.newTrack')}</span>
				</button>
				<p class="px-2 pb-1.5 pl-8 text-2xs text-fg-subtle" style:max-width="18rem">{t('generation.card.refs.full', { max: MAX_VREF_TRACKS })}</p>
			{:else}
				<button type="button" role="menuitem" data-take-target="new" onclick={() => send(null)}>
					<Icon name="plus" class="h-3.5 w-3.5 text-fg-muted" /><span class="flex-1">{moving ? t('generation.card.refs.moveNew') : t('generation.card.refs.copyNew')}</span><span class="vp-menu-key rounded-sm border border-line-strong px-1">{vrefLabel(choices.slot)}</span>
				</button>
			{/if}
		</div>
	{/key}
{/if}
