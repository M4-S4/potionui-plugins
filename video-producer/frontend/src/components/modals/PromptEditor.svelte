<script>
	import HostUi from '../../../../../../sdk/HostUi.svelte';
	import { t } from '../../i18n/index.svelte.js';
	import { ui, doc, act, promptIssues, globalPrompt, itemsIn, secs, deleteSelection, select, discardLast, promptEdited } from '../../lib/state.svelte.js';
	import Modal from './Modal.svelte';
	import Icon from '../Icon.svelte';

	let { id, isNew = false } = $props();
	const p = $derived(doc.prompts.find((x) => x.id === id));
	const textId = $props.id();

	function initial() {
		const x = doc.prompts.find((q) => q.id === id);
		return { text: x?.text ?? '', start: x?.start ?? 0, dur: x?.dur ?? 4, strength: x?.strength ?? 75 };
	}

	let draft = $state(initial());
	const issues = $derived(promptIssues({ ...draft, shotId: p?.shotId ?? null }));
	const ctx = $derived(itemsIn([+draft.start, +draft.start + +draft.dur]));
	const summary = $derived(
		[
			t('modals.count.frames', { count: ctx.frames.length }),
			t('modals.count.references', { count: ctx.references.length }),
			ctx.controls.length ? t('modals.count.controls', { count: ctx.controls.length }) : ''
		]
			.filter(Boolean)
			.join(' · ')
	);

	function saveIt() {
		act(() => {
			const before = p.text;
			Object.assign(p, { text: draft.text.trim(), start: +draft.start, dur: +draft.dur, strength: +draft.strength });
			promptEdited(p, before);
		});
		ui.modal = null;
	}
	function cancel() {
		if (isNew && p && !p.text) {
			discardLast();
			select(null);
		}
		ui.modal = null;
	}
	function remove() {
		ui.modal = null;
		deleteSelection();
	}
	function openLibrary() {
		Object.assign(p, { text: draft.text });
		ui.modal = { type: 'library', target: { kind: 'prompt', id, returnTo: { type: 'prompt', id } } };
	}
</script>

{#if p}
	<Modal title={isNew ? t('modals.prompt.titleNew') : t('modals.prompt.titleEdit')} subtitle={t('modals.prompt.subtitle')} icon="sparkles" width={640} onclose={cancel}>
		<div class="grid grid-cols-[1fr_200px] gap-4 p-4">
			<div class="space-y-3">
				<div>
					<div class="mb-1 flex items-center justify-between">
						<label for={textId} class="vp-label">{t('modals.prompt.instruction')}</label>
						<button type="button" class="flex min-h-6 items-center gap-1 text-xs text-fg-muted hover:text-fg" onclick={openLibrary}><Icon name="wand" class="h-3.5 w-3.5" />{t('modals.prompt.library')}</button>
					</div>
					<!-- svelte-ignore a11y_autofocus -->
					<textarea id={textId} class="input w-full text-md" rows="6" bind:value={draft.text} autofocus placeholder={t('modals.prompt.placeholder')}></textarea>
				</div>
				{#each issues as issue, i (i)}
					{#if issue.level === 'conflict'}
						<HostUi name="Alert" props={{ variant: 'warning', class: '[&>div]:text-fg', density: 'compact', icon: true }}>{issue.text}</HostUi>
					{:else}
						<div class="flex gap-2 rounded-lg border border-line-hover p-2 text-xs text-fg-muted">
							<Icon name={issue.level === 'control' ? 'route' : 'alert'} class="mt-px h-3.5 w-3.5 shrink-0" />{issue.text}
						</div>
					{/if}
				{/each}
				<details class="rounded-lg border border-line-strong p-2.5 text-xs" open>
					<summary class="-mb-1 -mt-1 min-h-6 cursor-pointer py-1 font-medium text-fg-muted">{t('modals.prompt.global')}</summary>
					<p class="mt-1.5 leading-5 text-fg-subtle">{globalPrompt()}</p>
				</details>
			</div>
			<div class="space-y-3">
				<label class="block space-y-1"><span class="vp-label">{t('modals.prompt.start')}</span><input class="input vp-dense vp-tc w-full" type="number" step="0.04" min="0" bind:value={draft.start} /></label>
				<label class="block space-y-1"><span class="vp-label">{t('modals.prompt.duration')}</span><input class="input vp-dense vp-tc w-full" type="number" step="0.04" min="0.3" bind:value={draft.dur} /></label>
				<label class="block space-y-1">
					<span class="flex justify-between"><span class="vp-label">{t('modals.prompt.influence')}</span><span class="vp-tc text-xs">{draft.strength} %</span></span>
					<input class="vp-slider" type="range" min="0" max="100" bind:value={draft.strength} />
				</label>
				<div class="rounded-lg border border-line-strong p-2 text-xs text-fg-muted">
					<div class="mb-1 font-medium text-fg">{t('modals.prompt.range')}</div>
					{summary}
					<div class="vp-tc mt-1 text-fg-subtle">{secs(+draft.start)} → {secs(+draft.start + +draft.dur)}</div>
				</div>
			</div>
		</div>
		{#snippet footer()}
			{#if !isNew}
				<HostUi name="Button" props={{ variant: 'ghost', size: 'sm', icon: 'trash', class: 'mr-auto !text-danger', onclick: remove }}>{t('modals.prompt.delete')}</HostUi>
			{/if}
			<HostUi name="Button" props={{ variant: 'secondary', size: 'sm', onclick: cancel }}>{t('modals.prompt.cancel')}</HostUi>
			<HostUi name="Button" props={{ variant: 'primary', size: 'sm', onclick: saveIt }}>{t('modals.prompt.save')}</HostUi>
		{/snippet}
	</Modal>
{/if}
