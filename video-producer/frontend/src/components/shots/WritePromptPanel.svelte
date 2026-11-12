<script>
	import HostUi from '../../../../../../sdk/HostUi.svelte';
	import { requestCause, t } from '../../i18n/index.svelte.js';
	import { MAX_REQUEST, writerCode } from '../../lib/promptwriter.js';

	let { writer, text, frames = 0, onwrite, onaccept, onundo } = $props();

	const requestId = $props.id();
	const view = $derived(writer.state);
	const status = $derived(writer.status);
	const name = $derived(status?.name || t('modals.shot.writer.model'));
	const seeing = $derived(frames > 0 && status?.vision === true);
	const errorCode = $derived(writerCode(view.error));
	const error = $derived(view.error ? (errorCode ? t(`modals.shot.writer.error.${errorCode}`) : requestCause(view.error)) : '');
	const proposal = $derived(view.proposal);
	const lostTags = $derived(proposal?.lostTags ?? []);
	const keptTags = $derived(proposal?.keptTags ?? []);

	function keydown(event) {
		if (event.key === 'Enter' && (event.ctrlKey || event.metaKey)) {
			event.preventDefault();
			if (writer.ready()) onwrite();
		}
	}
</script>

{#if view.phase !== 'closed'}
	<div class="space-y-2 rounded-lg border border-line-strong p-2.5 text-xs" data-writer={view.phase}>
		<label for={requestId} class="vp-label block">{t('modals.shot.writer.request')}</label>
		<!-- svelte-ignore a11y_autofocus -->
		<textarea id={requestId} class="input w-full text-xs" rows="2" maxlength={MAX_REQUEST} autofocus value={view.request} oninput={(e) => writer.edit(e.currentTarget.value)} onkeydown={keydown} disabled={writer.busy} placeholder={t('modals.shot.writer.placeholder')}></textarea>
		<p class="text-fg-subtle" data-writer-sources>{seeing ? t('modals.shot.writer.sourcesFrames', { name, count: frames }) : t('modals.shot.writer.sources', { name })}</p>
		{#if frames > 0 && status && !status.vision}<p class="text-fg-subtle" data-writer-blind>{t('modals.shot.writer.blind', { name, count: frames })}</p>{/if}
		{#if view.phase === 'writing'}
			<div class="flex items-center justify-between gap-2" aria-live="polite">
				<span class="flex items-center gap-2 text-fg-muted" data-writer-waiting><span class="vp-writer-spin" aria-hidden="true"></span>{t('modals.shot.writer.writing', { name })}</span>
				<HostUi name="Button" props={{ variant: 'secondary', size: 'xs', onclick: () => writer.cancel() }}>{t('modals.shot.writer.cancel')}</HostUi>
			</div>
		{:else if view.phase === 'failed'}
			<div aria-live="polite" data-writer-error={view.error?.code ?? ''}>
				<HostUi name="Alert" props={{ variant: 'danger', class: '[&>div]:text-fg', density: 'compact', icon: true }}>{error}</HostUi>
			</div>
		{:else if view.phase === 'proposed' && proposal}
			<div class="space-y-1.5" aria-live="polite">
				<div class="font-medium text-fg-muted">{t('modals.shot.writer.proposal', { name: proposal.name || name })}</div>
				<p class="max-h-40 overflow-auto whitespace-pre-wrap rounded border border-line bg-surface-2 p-2 leading-5 text-fg" data-writer-proposal>{proposal.text}</p>
				{#if proposal.imagesDropped}<p class="text-fg-subtle" data-writer-dropped={proposal.imagesDropped}>{t('modals.shot.writer.dropped', { count: proposal.imagesDropped })}</p>{/if}
				{#if keptTags.length}<p class="text-warning" data-writer-kept-tags={keptTags.join(' ')}>{t('modals.shot.writer.keptTags', { tags: keptTags.join(', '), count: keptTags.length })}</p>{/if}
				{#if lostTags.length}<p class="text-warning" data-writer-lost-tags={lostTags.join(' ')}>{t('modals.shot.writer.lostTags', { tags: lostTags.join(', '), count: lostTags.length })}</p>{/if}
				{#if text.trim()}<p class="text-fg-subtle">{t('modals.shot.writer.replaces')}</p>{/if}
				<div class="flex flex-wrap items-center gap-1.5">
					<HostUi name="Button" props={{ variant: 'primary', size: 'xs', icon: 'check', onclick: onaccept }}>{t('modals.shot.writer.accept')}</HostUi>
					<HostUi name="Button" props={{ variant: 'ghost', size: 'xs', onclick: () => writer.reject() }}>{t('modals.shot.writer.reject')}</HostUi>
				</div>
			</div>
		{/if}
		{#if view.phase !== 'writing' && view.phase !== 'proposed'}
			<div class="flex items-center justify-end gap-1.5">
				<HostUi name="Button" props={{ variant: 'ghost', size: 'xs', onclick: () => writer.close() }}>{t('modals.shot.writer.close')}</HostUi>
				<HostUi name="Button" props={{ variant: 'primary', size: 'xs', icon: 'sparkles', disabled: !writer.ready(), onclick: onwrite }}>{view.phase === 'failed' ? t('modals.shot.writer.retry') : t('modals.shot.writer.write')}</HostUi>
			</div>
		{/if}
	</div>
{:else if writer.undoable(text)}
	<p class="flex flex-wrap items-center gap-x-2 text-xs text-fg-subtle" data-writer-applied>
		<span>{t('modals.shot.writer.applied', { name })}</span>
		<button type="button" class="vp-link-hit underline decoration-line-hover underline-offset-2 hover:text-fg" onclick={onundo}>{t('modals.shot.writer.undo')}</button>
	</p>
{/if}

<style>
	.vp-writer-spin {
		display: inline-block;
		width: 0.75rem;
		height: 0.75rem;
		border-radius: 9999px;
		border: 2px solid rgb(var(--line-hover));
		border-top-color: currentColor;
		animation: vp-writer-spin 0.8s linear infinite;
	}

	@keyframes vp-writer-spin {
		to {
			transform: rotate(360deg);
		}
	}

	@media (prefers-reduced-motion: reduce) {
		.vp-writer-spin {
			animation-duration: 2.4s;
		}
	}
</style>
