<script>
	import HostUi from '../../../../../../sdk/HostUi.svelte';
	import { formatNumber, t } from '../../i18n/index.svelte.js';
	import { ui, doc, tc, clamp } from '../../lib/state.svelte.js';
	import { togglePlay } from '../../lib/playback.svelte.js';
	import { sceneLabel } from '../../lib/catalog.js';
	import { currentPlan, cameraAt, currentScene, addSampleScene } from '../../lib/scene.js';
	import { mountHostSlot } from '../../lib/host.js';
	import { drag, cancelDrag } from '../../lib/timeline.js';
	import { commandById } from '../../lib/commands.js';
	import { hostIconName } from '../../lib/icons.js';
	import Icon from '../Icon.svelte';

	let canvas = $state();
	let w = $state(0);
	let h = $state(0);
	const scene = $derived(currentScene());
	const emptyProps = $derived({
		icon: 'cube',
		title: t('scene.empty.title'),
		description: t('scene.empty.text'),
		actions: { slot: (el) => mountHostSlot(el, 'Button', { variant: 'secondary', size: 'sm', icon: 'plus', onclick: addSampleScene, children: t('scene.sample.name') }) }
	});
	const plan = $derived(currentPlan());
	const inPlan = $derived(!!plan && ui.playhead >= plan.start && ui.playhead <= plan.start + plan.dur);
	const cam = $derived(inPlan && plan.keyframes.length && (ui.playing || !ui.scene.keyframe) ? cameraAt(plan, ui.playhead - plan.start) : ui.scene);

	function rand(seed) {
		let s = seed;
		return () => (s = (s * 16807) % 2147483647) / 2147483647;
	}
	const points = (() => {
		const r = rand(7);
		const p = [];
		for (let i = 0; i < 3200; i++) {
			const x = (r() - 0.5) * 24;
			const z = (r() - 0.5) * 24;
			const y = Math.max(0, Math.sin(x * 0.25) * 1.2 + Math.cos(z * 0.2) * 1.4 + (Math.abs(z) > 8 ? (Math.abs(z) - 8) * 0.9 : 0));
			const g = 90 + y * 25;
			p.push([x, y, z, `rgb(${60 + y * 18},${g},${70 + y * 12})`, 0.16]);
		}
		for (let i = 0; i < 2600; i++) {
			const side = Math.floor(r() * 5);
			let x = (r() - 0.5) * 3;
			let y = r() * 2.2;
			let z = (r() - 0.5) * 3;
			if (side === 0) x = -1.5;
			else if (side === 1) x = 1.5;
			else if (side === 2) z = -1.5;
			else if (side === 3) z = 1.5;
			else y = 2.2 + (1.5 - Math.abs(x)) * 0.8;
			p.push([x, y + 0.6, z, side === 4 ? 'rgb(150,70,55)' : 'rgb(205,195,175)', 0.12]);
		}
		for (let tree = 0; tree < 26; tree++) {
			const tx = (r() - 0.5) * 20;
			const tz = (r() - 0.5) * 20;
			if (Math.hypot(tx, tz) < 3.5) continue;
			for (let i = 0; i < 90; i++) {
				const hh = r() * 3;
				const rad = (1 - hh / 3) * 0.7;
				const a = r() * Math.PI * 2;
				p.push([tx + Math.cos(a) * rad * r(), hh + 0.8, tz + Math.sin(a) * rad * r(), `rgb(30,${70 + r() * 30},45)`, 0.18]);
			}
		}
		return p;
	})();

	function eye(c) {
		const az = (c.az * Math.PI) / 180;
		const el = (c.el * Math.PI) / 180;
		return [Math.sin(az) * Math.cos(el) * c.dist, c.height + Math.sin(el) * c.dist, Math.cos(az) * Math.cos(el) * c.dist];
	}

	$effect(() => {
		if (!canvas || !w || !h || !scene) return;
		const c = cam;
		const g = canvas.getContext('2d');
		if (!g) return;
		const dpr = window.devicePixelRatio || 1;
		canvas.width = w * dpr;
		canvas.height = h * dpr;
		g.setTransform(dpr, 0, 0, dpr, 0, 0);
		const sky = g.createLinearGradient(0, 0, 0, h);
		sky.addColorStop(0, '#2b3a4f');
		sky.addColorStop(1, '#0e1218');
		g.fillStyle = sky;
		g.fillRect(0, 0, w, h);
		if (scene.kind === 'file') return;
		const [ex, ey, ez] = eye(c);
		const tgt = [0, c.height, 0];
		let fx = tgt[0] - ex,
			fy = tgt[1] - ey,
			fz = tgt[2] - ez;
		const fl = Math.hypot(fx, fy, fz);
		fx /= fl;
		fy /= fl;
		fz /= fl;
		let rx = fz,
			rz = -fx;
		const rl = Math.hypot(rx, rz) || 1;
		rx /= rl;
		rz /= rl;
		const ux = -rz * fy,
			uy = rz * fx - rx * fz,
			uz = rx * fy;
		const f = (c.focal / 36) * w;
		const proj = [];
		for (const [x, y, z, col, s] of points) {
			const dx = x - ex,
				dy = y - ey,
				dz = z - ez;
			const d = dx * fx + dy * fy + dz * fz;
			if (d < 0.3) continue;
			const px = w / 2 + ((dx * rx + dz * rz) / d) * f;
			const py = h / 2 - ((dx * ux + dy * uy + dz * uz) / d) * f;
			proj.push([d, px, py, col, (s * f * 0.22) / d]);
		}
		proj.sort((a, b) => b[0] - a[0]);
		for (const [d, px, py, col, rad] of proj) {
			g.globalAlpha = clamp(1.2 - d / 30, 0.25, 0.9);
			g.fillStyle = col;
			g.beginPath();
			g.arc(px, py, Math.max(0.7, rad), 0, Math.PI * 2);
			g.fill();
		}
		g.globalAlpha = 1;
	});

	$effect(() => cancelDrag);

	function orbit(e) {
		if (e.button !== 0) return;
		if (ui.playing) togglePlay();
		if (cam !== ui.scene) Object.assign(ui.scene, { az: Math.round(cam.az), el: Math.round(cam.el), dist: +cam.dist.toFixed(1), focal: Math.round(cam.focal), height: +cam.height.toFixed(2) });
		ui.scene.keyframe = 'free';
		const az0 = ui.scene.az;
		const el0 = ui.scene.el;
		drag(e, {
			undoable: false,
			onMove: (dx, dy) => {
				ui.scene.az = Math.round(az0 + dx * 0.4);
				ui.scene.el = clamp(Math.round(el0 + dy * 0.3), -5, 80);
			}
		});
	}
	function wheel(e) {
		e.preventDefault();
		ui.scene.dist = clamp(+(ui.scene.dist * (e.deltaY > 0 ? 1.08 : 0.92)).toFixed(1), 2, 30);
	}

	const path = $derived(plan?.keyframes.length ? Array.from({ length: 30 }, (_, i) => cameraAt(plan, (i / 29) * plan.dur)) : []);
	const map = (c) => {
		const [x, , z] = eye(c);
		return [60 + x * 2.6, 60 + z * 2.6];
	};
	const hud = $derived(
		t('scene.hud', {
			focal: Math.round(cam.focal),
			az: Math.round(cam.az),
			el: Math.round(cam.el),
			dist: formatNumber(cam.dist, { minimumFractionDigits: 1, maximumFractionDigits: 1 })
		})
	);
</script>

<section class="isolate flex min-w-0 flex-col bg-canvas" aria-label={t('scene.label')}>
	{#if !scene}
		<div class="flex min-h-0 flex-1 items-center justify-center p-6">
			<div class="w-full max-w-md">
				<HostUi name="EmptyState" props={emptyProps} />
			</div>
		</div>
	{:else}
		<div class="flex h-10 min-w-0 shrink-0 items-center gap-2 overflow-hidden whitespace-nowrap border-b border-line px-3">
			<span class="text-sm font-semibold">{scene.name}</span>
			<HostUi name="Badge" props={{ variant: 'neutral', size: 'md' }}>{sceneLabel(scene)}</HostUi>
			{#if scene.kind === 'sample'}<span class="vp-sim"><Icon name="flask" class="h-3 w-3" />{t('shell.window.simulated')}</span>{/if}
			{#if inPlan}
				<HostUi name="Badge" props={{ variant: 'neutral', size: 'md', class: '!text-fg' }}><span class="h-2 w-2 rounded-sm bg-viz-8"></span>{t('scene.planCamera', { plan: plan.name })}</HostUi>
			{:else}
				<HostUi name="Badge" props={{ variant: 'neutral', size: 'md' }}>{t('scene.freeCamera')}</HostUi>
			{/if}
			<div class="flex-1"></div>
			<span class="hidden truncate text-xs text-fg-subtle 2xl:inline">{t('scene.hint')}</span>
		</div>

		<div class="relative min-h-0 flex-1" bind:clientWidth={w} bind:clientHeight={h}>
			<!-- svelte-ignore a11y_no_static_element_interactions -->
			<canvas bind:this={canvas} class="vp-touch-none absolute inset-0 h-full w-full cursor-grab active:cursor-grabbing" style:width="{w}px" style:height="{h}px" onpointerdown={orbit} onwheel={wheel}></canvas>

			{#if scene.kind === 'file'}
				<div class="absolute inset-0 flex flex-col items-center justify-center gap-2 text-center">
					<Icon name="link" class="h-8 w-8 text-white/60" />
					<div class="text-sm text-white">{scene.file}</div>
					<div class="max-w-sm text-xs text-white/70">{t('scene.fileNote')}</div>
					<span class="vp-sim"><Icon name="flask" class="h-3 w-3" />{t('scene.simPreview')}</span>
				</div>
			{/if}

			<div class="pointer-events-none absolute inset-[8%] border border-white/15"></div>

			<svg class="absolute bottom-3 right-3 rounded-lg border border-line-strong bg-surface-1/90" width="120" height="120" viewBox="0 0 120 120" role="img" aria-label={t('scene.topView')}>
				<rect x="55" y="55" width="10" height="10" fill="rgb(var(--fg-subtle))" />
				{#if path.length}
					<polyline points={path.map((c) => map(c).join(',')).join(' ')} fill="none" stroke="rgb(var(--viz-8))" stroke-width="1.5" />
					{#each plan.keyframes as k (k.id)}
						{@const [x, y] = map(k)}
						<rect x={x - 3} y={y - 3} width="6" height="6" transform="rotate(45 {x} {y})" fill={ui.scene.keyframe === k.id ? 'rgb(var(--signal))' : 'rgb(var(--fg))'} />
					{/each}
				{/if}
				{#if cam}
					{@const [cx, cy] = map(cam)}
					<circle {cx} {cy} r="4" fill="rgb(var(--signal))" />
					<line x1={cx} y1={cy} x2="60" y2="60" stroke="rgb(var(--signal))" stroke-dasharray="2 2" />
				{/if}
			</svg>

			<div class="vp-tc absolute left-3 top-3 rounded bg-black/60 px-2 py-1 text-xs text-white">{hud}</div>
		</div>

		<div class="flex h-11 shrink-0 items-center gap-2 border-t border-line px-3">
			<HostUi
				name="IconButton"
				props={{
					icon: hostIconName(ui.playing ? 'pause' : 'play'),
					label: ui.playing ? t('scene.pause') : t('scene.play'),
					tooltip: ui.playing ? t('scene.pause') : t('scene.play'),
					kbd: commandById('play')?.key || undefined,
					variant: 'secondary',
					size: 'sm',
					class: '!rounded-full',
					onclick: togglePlay
				}}
			/>
			<span class="text-xs text-fg-muted">{t('scene.preview')}</span>
			<div class="flex-1"></div>
			<span class="vp-tc text-md">{tc(ui.playhead, doc.fps)}</span>
		</div>
	{/if}
</section>
