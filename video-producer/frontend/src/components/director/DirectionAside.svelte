<script>
	import HostUi from '../../../../../../sdk/HostUi.svelte';
	import { t } from '../../i18n/index.svelte.js';
	import { ui, doc, clipLabel, globalPrompt, witness, followedIssue, issueRule, shotNumber } from '../../lib/state.svelte.js';
	import { instructionPromptOf } from '../../lib/bible.js';
	import { markedPhrases } from '../../lib/director.js';
	import { commandById } from '../../lib/commands.js';
	import { hostIconName } from '../../lib/icons.js';
	import ComposedPrompt from '../shots/ComposedPrompt.svelte';
	import Icon from '../Icon.svelte';

	const chosen = $derived(witness());
	const shot = $derived(chosen.clip);
	const issue = $derived(followedIssue(shot));
	const rule = $derived(issue ? issueRule(issue.id) : null);
	const marks = $derived(rule ? [rule.global, rule.local] : []);
	const phrases = $derived(rule ? { direction: markedPhrases(globalPrompt(), [rule.global])[0] ?? '', instruction: markedPhrases(issue.prompt.text, [rule.local])[0] ?? '' } : null);
	const prompt = $derived(issue?.prompt ?? (shot ? instructionPromptOf(doc, shot) : null));
	let composed = $state(null);

	const follow = $derived.by(() => {
		if (chosen.source === 'pinned') return t('panels.director.aside.pinned');
		if (chosen.source === 'selection') return issue ? t('panels.director.aside.followsIssue') : t('panels.director.aside.follows');
		return t('panels.director.aside.first');
	});

	function edit() {
		ui.modal = prompt ? { type: 'prompt', id: prompt.id } : { type: 'shot', id: shot.id };
	}
</script>

<aside class="flex min-h-0 flex-col overflow-hidden border-l border-line bg-surface-1" aria-label={t('panels.director.aside.prompt')} class:invisible={!ui.inspectorOpen}>
	<div class="vp-panel-head border-b border-line">
		<Icon name="type" class="h-4 w-4 text-fg-muted" />
		<span class="truncate text-sm font-semibold">{t('panels.director.aside.prompt')}</span>
		<div class="flex-1"></div>
		<HostUi name="IconButton" props={{ icon: hostIconName('x'), label: t('inspector.close'), tooltip: t('inspector.closeTip'), kbd: commandById('inspector')?.key, size: 'sm', class: 'vp-h7', onclick: () => (ui.inspectorOpen = false) }} />
	</div>
	<div class="min-h-0 flex-1 space-y-3 overflow-auto p-3">
		{#if shot}
			<label class="block space-y-1">
				<span class="vp-label">{t('panels.director.aside.witness')}</span>
				<select class="vp-popup w-full" value={shot.id} onchange={(e) => (ui.witness = e.currentTarget.value)}>
					{#each doc.clips as c (c.id)}<option value={c.id}>{shotNumber(c)} · {clipLabel(c)}</option>{/each}
				</select>
			</label>
			<div class="flex items-start gap-1.5 text-xs {chosen.source === 'pinned' ? 'text-fg-muted' : 'text-signal'}" data-witness={chosen.source}>
				<Icon name={chosen.source === 'pinned' ? 'lock' : 'target'} class="mt-px h-3.5 w-3.5 shrink-0" />
				<span class="min-w-0 flex-1">{follow}</span>
				{#if chosen.source === 'pinned'}
					<button type="button" class="vp-link-hit shrink-0 text-fg underline decoration-signal underline-offset-2 hover:decoration-2" onclick={() => (ui.witness = null)}>{t('panels.director.aside.unpin')}</button>
				{/if}
			</div>
			<p class="text-xs text-fg-subtle">{t('panels.director.aside.hint')}</p>
			{#if issue}
				<HostUi name="Alert" props={{ variant: 'warning', class: '[&>div]:text-fg', density: 'compact', icon: hostIconName('alert'), live: 'off' }}>
					<p class="text-xs">{issue.text}</p>
					<p class="mt-1 text-xs text-fg-muted">{t('panels.director.aside.issue')}</p>
					{#if !composed && phrases}
						<dl class="mt-1.5 space-y-1 text-xs" data-issue-phrases>
							<dt class="text-fg-subtle">{t('panels.director.aside.fromDirection')}</dt>
							<dd><mark class="rounded-sm text-fg" style:background-color="rgb(var(--warning) / 0.25)">{phrases.direction}</mark></dd>
							<dt class="text-fg-subtle">{t('panels.director.aside.fromInstruction', { shot: shotNumber(shot) })}</dt>
							<dd><mark class="rounded-sm text-fg" style:background-color="rgb(var(--warning) / 0.25)">{phrases.instruction}</mark></dd>
						</dl>
					{/if}
				</HostUi>
			{/if}
			<HostUi name="Button" props={{ variant: 'secondary', size: 'sm', icon: hostIconName('pencil'), class: 'w-full', onclick: edit }}>{t('panels.director.aside.edit', { shot: shotNumber(shot) })}</HostUi>
			<ComposedPrompt source={doc} shotId={shot.id} {marks} bind:current={composed} />
		{:else}
			<HostUi name="EmptyState" props={{ compact: true, icon: 'film', title: t('panels.director.aside.noneTitle'), description: t('panels.director.aside.none') }} />
		{/if}
	</div>
</aside>
