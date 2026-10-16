<script>
	import { fade, scale } from 'svelte/transition';
	import { cubicOut } from 'svelte/easing';
	import { t } from '../../i18n/index.svelte.js';
	import { ms } from '../../lib/motion.js';
	import { overlayLayer } from '../../lib/host.js';
	import { ui } from '../../lib/state.svelte.js';
	import { allCommands } from '../../lib/commands.js';
	import Icon from '../Icon.svelte';

	let q = $state('');
	let idx = $state(0);
	const norm = (s) => s.normalize('NFD').replace(/[̀-ͯ]/g, '').toLowerCase();
	const results = $derived(allCommands.filter((c) => !q || norm(`${c.label} ${c.menu}`).includes(norm(q))).slice(0, 12));

	function run(c) {
		ui.paletteOpen = false;
		q = '';
		c.run();
	}

	function key(e) {
		if (e.key === 'ArrowDown') {
			idx = Math.min(results.length - 1, idx + 1);
			e.preventDefault();
		}
		if (e.key === 'ArrowUp') {
			idx = Math.max(0, idx - 1);
			e.preventDefault();
		}
		if (e.key === 'Enter' && results[idx]) run(results[idx]);
	}

	function focus(el) {
		el.focus();
	}
</script>

{#if ui.paletteOpen}
	<div class="vp-palette-backdrop" role="presentation" use:overlayLayer transition:fade={{ duration: ms(120) }} onclick={(e) => e.target === e.currentTarget && (ui.paletteOpen = false)}>
		<div class="vp-palette" role="dialog" aria-label={t('shell.palette.label')} transition:scale={{ start: 0.98, duration: ms(160), easing: cubicOut }}>
			<div class="vp-palette-search">
				<Icon name="search" class="h-4 w-4 text-fg-muted" />
				<input use:focus placeholder={t('shell.palette.placeholder')} aria-label={t('shell.palette.label')} bind:value={q} oninput={() => (idx = 0)} onkeydown={key} />
				<span class="vp-kbd">{t('commands.kbd.escape')}</span>
			</div>
			<ul class="max-h-96 overflow-auto p-1">
				{#each results as c, i (c.id)}
					<li>
						<button type="button" class="vp-palette-item" data-active={i === idx} onclick={() => run(c)} onmouseenter={() => (idx = i)}>
							<span class="flex-1">{c.label}</span>
							{#if c.sim}<Icon name="flask" class="h-3.5 w-3.5 text-fg-muted" />{/if}
							<span class="text-xs text-fg-muted">{c.menu}</span>
							{#if c.key}<span class="vp-menu-key w-24 text-right">{c.key}</span>{/if}
						</button>
					</li>
				{:else}
					<li class="px-3 py-6 text-center text-sm text-fg-muted">{t('shell.palette.empty', { query: q })}</li>
				{/each}
			</ul>
		</div>
	</div>
{/if}
