<script>
	import { t } from '../../i18n/index.svelte.js';
	import { doc } from '../../lib/state.svelte.js';
	import { projectReceptionFor, engineTitle } from '../../lib/references.js';
	import { isGlobal } from '../../lib/shots.js';
	import ReceptionList from './ReceptionList.svelte';
	import Icon from '../Icon.svelte';

	const globals = $derived(doc.references.filter(isGlobal).length);
	const owns = $derived(doc.references.length - globals);
	const groups = $derived(projectReceptionFor());

	function verdict(group) {
		if (group.state === 'unknown') return { text: t('panels.director.refs.unknown'), tone: 'text-fg-subtle', ok: false };
		if (group.state === 'blocked') return { text: t('panels.director.refs.blocked', { profile: group.engine.profile }), tone: 'text-warning', ok: false };
		if (group.references) return { text: t('panels.director.refs.verdictSent'), tone: 'text-success', ok: true };
		if (group.counts.mixed) return { text: t('panels.director.refs.verdictMixed', { count: group.counts.mixed }), tone: 'text-fg-muted', ok: false };
		return { text: t('panels.director.refs.verdictNone'), tone: 'text-fg-subtle', ok: false };
	}

	const rows = $derived(groups.map((g) => ({ key: g.key, status: g.state, title: engineTitle(g.engine), shots: g.shots.map((shot) => shot.clip), ...verdict(g) })));
</script>

<div class="space-y-4 p-3" data-reference-project>
	<dl class="grid grid-cols-[auto_1fr] gap-x-3 gap-y-1.5 text-xs">
		<dt class="text-fg-subtle">{t('panels.director.refs.total')}</dt>
		<dd class="vp-tc text-fg-muted">{doc.references.length}</dd>
		<dt class="text-fg-subtle">{t('inspector.scope.global')}</dt>
		<dd class="text-fg-muted">{t('panels.director.refs.globalsValue', { count: globals })}</dd>
		<dt class="text-fg-subtle">{t('panels.director.refs.ownsTitle')}</dt>
		<dd class="text-fg-muted">{t('panels.director.refs.ownsValue', { count: owns })}</dd>
	</dl>

	<section class="space-y-2" data-reference-engines>
		<div class="vp-section-title">{t('panels.director.refs.byEngine')}</div>
		{#if rows.length}
			<ReceptionList {rows} label={t('panels.director.refs.byEngine')} />
			<p class="text-xs text-fg-subtle">{t('panels.director.refs.rule')}</p>
		{:else}
			<p class="text-xs text-fg-subtle">{t('panels.director.refs.noShots')}</p>
		{/if}
	</section>

	<div class="flex flex-col items-center gap-1.5 rounded-lg border border-dashed border-line-strong px-3 py-4 text-center">
		<Icon name="bookmark" class="h-5 w-5 text-fg-muted" />
		<div class="text-sm font-medium">{t('panels.director.refs.emptyTitle')}</div>
		<p class="text-xs text-fg-subtle">{t('panels.director.refs.emptyText')}</p>
	</div>
</div>
