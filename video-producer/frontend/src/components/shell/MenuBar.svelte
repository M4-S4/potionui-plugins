<script>
	import { fly } from 'svelte/transition';
	import HostUi from '../../../../../../sdk/HostUi.svelte';
	import { t } from '../../i18n/index.svelte.js';
	import { ms } from '../../lib/motion.js';
	import { overlayLayer } from '../../lib/host.js';
	import { ui } from '../../lib/state.svelte.js';
	import { menus } from '../../lib/commands.js';
	import { setReturnFocus } from '../../lib/focus.js';
	import Icon from '../Icon.svelte';

	function open(id) {
		ui.menuOpen = ui.menuOpen === id ? null : id;
	}

	let triggers = {};

	function run(item, menuId) {
		setReturnFocus(triggers[menuId]);
		ui.menuOpen = null;
		item.run();
	}

	function outside(e) {
		if (ui.menuOpen && !e.target?.closest?.('[data-vp-menu]')) ui.menuOpen = null;
	}
</script>

<svelte:window onclick={outside} />

<nav class="vp-menubar" aria-label={t('shell.menubar.label')} data-vp-menu>
	{#each menus as m, i (m.id)}
		<div class="relative">
			<button
				bind:this={triggers[m.id]}
				type="button"
				class="vp-menubar-item"
				class:vp-menubar-app={i === 0}
				aria-haspopup="menu"
				aria-expanded={ui.menuOpen === m.id}
				onclick={() => open(m.id)}
				onmouseenter={() => ui.menuOpen && !ui.menuOpen.startsWith('dropdown:') && (ui.menuOpen = m.id)}
			>
				{m.label}
			</button>
			{#if ui.menuOpen === m.id}
				<div class="vp-menu top-7 left-0" role="menu" use:overlayLayer in:fly={{ y: -4, duration: ms(120) }}>
					{#each m.groups as group, gi}
						{#if gi > 0}<div class="vp-menu-sep" role="separator"></div>{/if}
						{#each group as item (item.id)}
							<button type="button" role="menuitem" onclick={() => run(item, m.id)}>
								<span class="w-3.5 shrink-0 text-signal">
									{#if item.check?.()}<Icon name="check" class="h-3.5 w-3.5" />{/if}
								</span>
								<span class="flex-1">{item.label}</span>
								{#if item.sim}
									<HostUi name="Tooltip" props={{ text: t('shell.menubar.simulated') }}>
										<Icon name="flask" class="h-3.5 w-3.5 text-fg-muted" />
									</HostUi>
								{/if}
								{#if item.key}<span class="vp-menu-key">{item.key}</span>{/if}
							</button>
						{/each}
					{/each}
				</div>
			{/if}
		</div>
	{/each}
</nav>
