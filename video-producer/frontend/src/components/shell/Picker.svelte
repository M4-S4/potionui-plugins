<script>
	import { tick } from 'svelte';
	import { fade } from 'svelte/transition';
	import HostUi from '../../../../../../sdk/HostUi.svelte';
	import { t } from '../../i18n/index.svelte.js';
	import { ms } from '../../lib/motion.js';
	import { overlayLayer } from '../../lib/host.js';
	import { hostIconName } from '../../lib/icons.js';
	import { ui } from '../../lib/state.svelte.js';
	import Icon from '../Icon.svelte';
	import RatioGlyph from './RatioGlyph.svelte';

	let {
		label,
		sections,
		value,
		onselect,
		glyph = null,
		text = '',
		sub = '',
		badge = '',
		tip = '',
		variant = 'field',
		search = '',
		custom = null,
		disabled = false,
		width = 300,
		triggerId = undefined
	} = $props();

	const uid = $props.id();
	const menu = `picker:${uid}`;
	const open = $derived(ui.menuOpen === menu);
	const PANEL_MAX = 360;

	let trigger = $state();
	let panel = $state();
	let searchInput = $state();
	let firstField = $state();
	let query = $state('');
	let active = $state(0);
	let typing = $state(false);
	let first = $state('');
	let second = $state('');
	let place = $state({ top: 0, bottom: 0, left: 0, width: 0, upward: false });

	const normal = (s) => String(s ?? '').toLowerCase().replaceAll('×', 'x');
	const matches = (row) => {
		const wanted = normal(query).trim();
		return !wanted || [row.value, row.title, row.detail, ...(row.badges ?? []).map((b) => b.text)].some((part) => normal(part).includes(wanted));
	};
	const shown = $derived(sections.map((section) => ({ ...section, rows: section.rows.filter(matches) })).filter((section) => section.rows.length));
	const flat = $derived(shown.flatMap((section) => section.rows));
	const offsets = $derived(shown.reduce((list, section, i) => [...list, i ? list[i - 1] + shown[i - 1].rows.length : 0], []));
	const checked = $derived(custom && typing && (first || second) ? custom.check(first, second) : null);

	function anchor() {
		if (!trigger) return;
		const rect = trigger.getBoundingClientRect();
		const panelWidth = Math.max(rect.width, width);
		const below = window.innerHeight - rect.bottom;
		place = {
			top: rect.bottom + 4,
			bottom: window.innerHeight - rect.top + 4,
			left: Math.max(8, Math.min(rect.left, window.innerWidth - panelWidth - 8)),
			width: panelWidth,
			upward: below < PANEL_MAX && rect.top > below
		};
	}

	async function show() {
		if (disabled) return;
		query = '';
		typing = false;
		first = '';
		second = '';
		active = Math.max(0, flatIndexOf(value));
		anchor();
		ui.menuOpen = menu;
		await tick();
		(searchInput ?? panel?.querySelector('[role="option"]'))?.focus();
		scrollActive();
	}

	function hide(refocus = false) {
		if (ui.menuOpen === menu) ui.menuOpen = null;
		typing = false;
		if (refocus) trigger?.focus();
	}

	function flatIndexOf(v) {
		return sections.flatMap((section) => section.rows).findIndex((row) => row.value === v);
	}

	function choose(v) {
		hide(true);
		if (v !== value) onselect(v);
	}

	function scrollActive() {
		panel?.querySelector(`[data-row="${active}"]`)?.scrollIntoView({ block: 'nearest' });
	}

	async function startTyping() {
		typing = true;
		active = flat.length;
		await tick();
		firstField?.focus();
	}

	async function stopTyping() {
		typing = false;
		await tick();
		(searchInput ?? trigger)?.focus();
	}

	function apply() {
		const result = custom.check(first, second);
		if (result.ok) choose(result.value);
	}

	function keydown(e) {
		if (e.key === 'Escape') {
			e.preventDefault();
			e.stopPropagation();
			if (typing) stopTyping();
			else hide(true);
			return;
		}
		if (typing) {
			if (e.key === 'Enter') {
				e.preventDefault();
				apply();
			}
			return;
		}
		const last = custom ? flat.length : flat.length - 1;
		if (e.key === 'ArrowDown' || e.key === 'ArrowUp') {
			e.preventDefault();
			active = Math.max(0, Math.min(last, active + (e.key === 'ArrowDown' ? 1 : -1)));
			scrollActive();
		} else if (e.key === 'Enter') {
			e.preventDefault();
			if (custom && active >= flat.length) startTyping();
			else if (flat[active]) choose(flat[active].value);
		}
	}

	$effect(() => {
		if (!open) return;
		const again = () => anchor();
		window.addEventListener('scroll', again, true);
		window.addEventListener('resize', again);
		return () => {
			window.removeEventListener('scroll', again, true);
			window.removeEventListener('resize', again);
		};
	});
</script>

<div class="relative {variant === 'field' ? 'w-full' : 'inline-flex'}" data-vp-menu>
	{#snippet button()}
		<button
			bind:this={trigger}
			id={triggerId}
			type="button"
			class={variant === 'field' ? 'input vp-dense flex w-full items-center gap-2 text-left hover:bg-surface-3' : 'vp-popup inline-flex items-center gap-1.5'}
			class:ring-2={open && variant === 'field'}
			class:ring-signal={open && variant === 'field'}
			aria-haspopup="listbox"
			aria-expanded={open}
			aria-label={label}
			{disabled}
			onclick={() => (open ? hide() : show())}
		>
			{#if glyph}<RatioGlyph ratio={glyph} class="h-4 w-4 {variant === 'field' ? 'text-signal' : 'text-fg-muted'}" />{/if}
			<span class="vp-tc truncate {variant === 'field' ? 'font-semibold text-fg' : ''}">{text}</span>
			{#if sub}<span class="vp-tc shrink-0 text-2xs text-fg-subtle">{sub}</span>{/if}
			{#if badge}<span class="ml-auto shrink-0 rounded-sm border border-line-strong px-1 text-2xs text-fg-muted">{badge}</span>{/if}
			{#if variant === 'field'}<Icon name="chevron-down" class="h-3.5 w-3.5 shrink-0 text-fg-subtle {badge ? '' : 'ml-auto'} transition-transform {open ? 'rotate-180' : ''}" />{/if}
		</button>
	{/snippet}
	{#if tip}
		<HostUi name="Tooltip" props={{ text: tip, wrapperClass: variant === 'field' ? 'flex w-full' : 'inline-flex' }}>{@render button()}</HostUi>
	{:else}
		{@render button()}
	{/if}

	{#if open}
		<div
			bind:this={panel}
			class="flex flex-col overflow-hidden rounded-xl border border-line-strong bg-surface-1 shadow-floating"
			style:position="fixed"
			style:top={place.upward ? null : `${place.top}px`}
			style:bottom={place.upward ? `${place.bottom}px` : null}
			style:left="{place.left}px"
			style:width="{place.width}px"
			style:max-height="{PANEL_MAX}px"
			role="listbox"
			tabindex="-1"
			aria-label={label}
			use:overlayLayer
			onkeydown={keydown}
			transition:fade={{ duration: ms(120) }}
		>
			{#if search}
				<div class="shrink-0 border-b border-line p-2">
					<div class="relative">
						<Icon name="search" class="pointer-events-none absolute left-2.5 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-fg-subtle" />
						<input bind:this={searchInput} bind:value={query} oninput={() => (active = 0)} type="text" class="input vp-dense w-full pl-8" placeholder={search} aria-label={search} />
					</div>
				</div>
			{/if}
			<div class="min-h-0 flex-1 overflow-y-auto py-1">
				{#if !shown.length}
					<p class="px-3 py-6 text-center text-xs text-fg-subtle">{t('shell.picker.none', { query })}</p>
				{/if}
				{#each shown as section, s (section.id)}
					{#if section.title}<div class="vp-tc sticky top-0 z-10 bg-surface-1 px-3 py-1 text-2xs font-semibold uppercase tracking-[0.1em] text-fg-subtle">{section.title}</div>{/if}
					{#each section.rows as row, r (row.value)}
						{@const index = offsets[s] + r}
						{@const selected = row.value === value}
						<button
							type="button"
							role="option"
							aria-selected={selected}
							data-row={index}
							class="flex w-full items-center gap-2.5 border-l-2 px-3 py-1.5 text-left transition-colors {selected ? 'border-signal bg-gradient-to-b from-signal/[0.16] to-signal/[0.05]' : index === active ? 'border-transparent bg-surface-2' : 'border-transparent hover:bg-surface-2'}"
							title={row.hint || undefined}
							onclick={() => choose(row.value)}
							onmouseenter={() => (active = index)}
						>
							{#if row.ratio}<RatioGlyph ratio={row.ratio} class="h-3.5 w-3.5 {selected ? 'text-signal' : 'text-fg-subtle'}" />{/if}
							<span class="min-w-0 flex-1 truncate text-xs {selected ? 'font-medium text-signal' : 'text-fg-muted'}">{row.title}</span>
							{#each row.badges ?? [] as b (b.text)}
								<span class="shrink-0 rounded-sm border border-line-strong px-1 text-2xs text-fg-muted" title={b.tip || undefined}>{b.text}</span>
							{/each}
							{#if row.detail}<span class="vp-tc shrink-0 text-2xs {selected ? 'text-signal' : 'text-fg-subtle'}">{row.detail}</span>{/if}
						</button>
					{/each}
				{/each}
				{#if custom}
					<div class="px-1.5 pt-1">
						{#if !typing}
							<button
								type="button"
								data-row={flat.length}
								class="flex w-full items-center gap-2 rounded border border-dashed px-2.5 py-1.5 transition-colors {active === flat.length ? 'border-line-hover bg-surface-2 text-fg' : 'border-line-strong text-fg-subtle hover:border-line-hover hover:text-fg'}"
								onclick={startTyping}
								onmouseenter={() => (active = flat.length)}
							>
								<Icon name="plus" class="h-3.5 w-3.5" />
								<span class="text-2xs">{custom.label}</span>
							</button>
						{:else}
							<div class="flex flex-col gap-1.5 px-1 py-1">
								<div class="flex items-center gap-1.5">
									<input bind:this={firstField} bind:value={first} type="text" inputmode="decimal" class="input vp-dense vp-tc text-right" style:width="4.5rem" placeholder={custom.placeholders[0]} aria-label={custom.fields[0]} />
									<span class="text-xs text-fg-subtle">{custom.separator}</span>
									<input bind:value={second} type="text" inputmode="decimal" class="input vp-dense vp-tc" style:width="4.5rem" placeholder={custom.placeholders[1]} aria-label={custom.fields[1]} />
									<span class="ml-auto inline-flex">
										<HostUi name="Button" props={{ variant: 'primary', size: 'xs', disabled: !checked?.ok, onclick: apply }}>{t('shell.picker.apply')}</HostUi>
									</span>
									<HostUi name="IconButton" props={{ icon: hostIconName('x'), label: t('shell.picker.cancel'), size: 'sm', onclick: stopTyping }} />
								</div>
								{#if checked?.ok && checked.note}<span class="text-2xs text-fg-muted">{checked.note}</span>{/if}
								{#if checked && !checked.ok}<span class="text-2xs text-danger">{checked.message}</span>{/if}
							</div>
						{/if}
					</div>
				{/if}
			</div>
		</div>
	{/if}
</div>
