<script>
	import { t } from '../../i18n/index.svelte.js';
	import { ui, doc, clipAt, clipLabel, seqDuration, tc } from '../../lib/state.svelte.js';
	import { seek } from '../../lib/playback.svelte.js';
	import { cancelDrag, drag } from '../../lib/timeline.js';
	import { fractionOf, shotMarks, timeAt } from '../../lib/player.js';

	let track = $state();

	const duration = $derived(seqDuration());
	const marks = $derived(shotMarks(doc.clips, duration));
	const shot = $derived(clipAt(ui.playhead));
	const shotText = $derived(shot ? t('viewer.bar.shot', { index: doc.clips.indexOf(shot) + 1, count: doc.clips.length, name: clipLabel(shot) }) : t('viewer.bar.noShot'));
	const now = $derived(tc(ui.playhead, doc.fps));
	const at = $derived(fractionOf(ui.playhead, duration) * 100);

	const seekTo = (x) => seek(timeAt(x, track.getBoundingClientRect(), duration));

	function down(e) {
		if (e.button !== 0) return;
		seekTo(e.clientX);
		drag(e, { undoable: false, onMove: (dx, dy, ev) => seekTo(ev.clientX) });
	}

	$effect(() => cancelDrag);
</script>

<div class="vp-playbar">
	<div class="flex h-6 min-w-0 items-center gap-3">
		<span class="vp-tc text-md text-fg">{now}</span>
		<span class="min-w-0 flex-1 truncate text-sm text-fg-muted">{shotText}</span>
		<span class="vp-tc text-xs text-fg-subtle">{tc(duration, doc.fps)}</span>
	</div>
	<div
		bind:this={track}
		class="vp-playbar-track"
		role="slider"
		tabindex="0"
		aria-label={t('viewer.bar.label')}
		aria-valuemin="0"
		aria-valuemax={Math.round(duration * 100) / 100}
		aria-valuenow={Math.round(ui.playhead * 100) / 100}
		aria-valuetext={t('viewer.bar.value', { tc: now, shot: shotText })}
		onpointerdown={down}
	>
		<div class="vp-playbar-rail">
			{#each marks as m (m.id)}
				<div class="vp-playbar-shot" class:vp-playbar-current={m.id === shot?.id} style:left="{m.left}%" style:width="{m.width}%"></div>
			{/each}
			<div class="vp-playbar-played" style:clip-path="inset(0 {100 - at}% 0 0)">
				{#each marks as m (m.id)}
					<div class="vp-playbar-shot" style:left="{m.left}%" style:width="{m.width}%"></div>
				{/each}
			</div>
			{#if ui.range}
				<div class="vp-playbar-range" style:left="{fractionOf(ui.range.in, duration) * 100}%" style:width="{(fractionOf(ui.range.out, duration) - fractionOf(ui.range.in, duration)) * 100}%"></div>
			{/if}
		</div>
		<div class="vp-playbar-head" style:left="{at}%"></div>
	</div>
</div>
