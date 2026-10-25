<script>
	import { onMount, untrack } from 'svelte';
	import HostUi from '../../../../../../sdk/HostUi.svelte';
	import { formatNumber, t } from '../../i18n/index.svelte.js';
	import { ui } from '../../lib/state.svelte.js';
	import { sceneLabel } from '../../lib/catalog.js';
	import {
		sceneState,
		currentScene,
		sceneReady,
		sceneBusy,
		sourceOf,
		freeCamera,
		setFreeCamera,
		seedCamera,
		resetToSource,
		syncStage,
		retryLoad,
		loadEngine,
		ensureStage,
		getStage,
		retryEngine,
		projectAspect,
		retryScene,
		cancelScene,
		sceneErrorText,
		sceneProgress
	} from '../../lib/scene.svelte.js';
	import { FOCAL_RANGE, clamp, deviation, deviationLevel, distance, dollyCamera, focalToFov, holesMatter, horizontalFov, orbitCamera, panCamera } from '../../lib/scene3d/camera.js';
	import { mountHostSlot } from '../../lib/host.js';
	import { hostIconName } from '../../lib/icons.js';
	import Icon from '../Icon.svelte';

	const ORBIT_STEP = 2;
	const PAN_STEP = 0.02;
	const DOLLY_STEP = 0.92;
	const ARROWS = { ArrowLeft: [-1, 0], ArrowRight: [1, 0], ArrowUp: [0, 1], ArrowDown: [0, -1] };

	let w = $state(0);
	let h = $state(0);
	let host = $state();
	let gesture = null;
	const stage = $derived(getStage());

	const scene = $derived(currentScene());
	const ready = $derived(sceneReady(scene));
	const aspect = $derived(projectAspect());
	const frameW = $derived(Math.max(0, Math.floor(Math.min(w, h * aspect))));
	const frameH = $derived(Math.max(0, Math.floor(frameW / aspect)));
	const cam = $derived(freeCamera());
	const fov = $derived(focalToFov(cam.focal, aspect));
	const source = $derived(scene ? sourceOf(scene) : null);
	const depth = $derived(source ? distance(source.pos, source.target) : 1);
	const gap = $derived(source && holesMatter(scene) ? deviation(cam, source) : null);
	const level = $derived(gap ? deviationLevel(gap) : 'ok');
	const one = (v) => formatNumber(v, { maximumFractionDigits: 1 });
	const hud = $derived(t('scene.hud', { focal: Math.round(cam.focal), fov: one(fov), hfov: one(horizontalFov(cam.focal)), roll: Math.round(cam.roll ?? 0) }));
	const progress = $derived(sceneProgress(scene));
	const live = $derived(ready && sceneState.status === 'ready');

	const emptyProps = $derived({
		icon: 'cube',
		title: t('scene.empty.title'),
		description: t('scene.empty.text'),
		actions: {
			slot: (el) => mountHostSlot(el, 'Button', { variant: 'primary', size: 'sm', icon: 'plus', onclick: () => (ui.modal = { type: 'scene-new' }), children: t('scene.new') })
		}
	});

	onMount(() => {
		loadEngine();
		ensureStage();
		return () => {
			gesture = null;
		};
	});

	$effect(() => {
		const st = stage;
		const el = host;
		if (!st || !el) return;
		el.appendChild(st.canvas);
		st.refresh();
		return () => st.canvas.remove();
	});

	$effect(() => {
		if (stage && frameW && frameH) stage.resize(frameW, frameH);
	});

	$effect(() => {
		const s = scene;
		const key = s ? `${s.id}:${s.fileId}:${ready}` : '';
		untrack(() => (key && ready ? syncStage(s) : syncStage(null)));
	});

	$effect(() => {
		if (scene) seedCamera(scene);
	});

	$effect(() => {
		if (!stage || sceneState.status !== 'ready') return;
		stage.setPose({ ...cam, fov });
	});

	function down(e) {
		if (!live || (e.button !== 0 && e.button !== 1 && e.button !== 2)) return;
		e.preventDefault();
		e.currentTarget.focus({ preventScroll: true });
		e.currentTarget.setPointerCapture?.(e.pointerId);
		gesture = { id: e.pointerId, x: e.clientX, y: e.clientY, pan: e.button !== 0 || e.shiftKey, moved: false };
	}

	function move(e) {
		if (!gesture || e.pointerId !== gesture.id) return;
		const dx = e.clientX - gesture.x;
		const dy = e.clientY - gesture.y;
		if (!gesture.moved && Math.hypot(dx, dy) < 2) return;
		gesture.moved = true;
		gesture.x = e.clientX;
		gesture.y = e.clientY;
		const base = freeCamera();
		const k = (2 * Math.tan(((fov * Math.PI) / 180) / 2)) / Math.max(1, frameH);
		setFreeCamera(gesture.pan ? panCamera(base, -dx * k, dy * k) : orbitCamera(base, -dx * 0.25, dy * 0.25));
	}

	function up(e) {
		if (gesture && e.pointerId === gesture.id) gesture = null;
	}

	function wheel(e) {
		if (!live) return;
		e.preventDefault();
		const base = freeCamera();
		if (e.altKey) setFreeCamera({ ...base, focal: clamp(base.focal * Math.exp(-e.deltaY * 0.001), FOCAL_RANGE[0], FOCAL_RANGE[1]) });
		else setFreeCamera(dollyCamera(base, Math.exp(e.deltaY * 0.001), depth * 0.02));
	}

	function key(e) {
		if (!live || e.ctrlKey || e.metaKey || e.altKey) return;
		const arrow = ARROWS[e.key];
		if (arrow) {
			const base = freeCamera();
			const [x, y] = arrow;
			setFreeCamera(e.shiftKey ? panCamera(base, x * PAN_STEP, y * PAN_STEP) : orbitCamera(base, x * ORBIT_STEP, y * ORBIT_STEP));
		} else if (e.key === '+' || e.key === '=') setFreeCamera(dollyCamera(freeCamera(), DOLLY_STEP, depth * 0.02));
		else if (e.key === '-' || e.key === '_') setFreeCamera(dollyCamera(freeCamera(), 1 / DOLLY_STEP, depth * 0.02));
		else if (e.key === '0') resetToSource();
		else return;
		e.preventDefault();
		e.stopPropagation();
	}

	const mapBox = $derived.by(() => {
		const points = [cam.pos, cam.target, ...(source ? [source.pos, source.target] : [])];
		const xs = points.map((p) => p[0]);
		const zs = points.map((p) => p[2]);
		const cx = (Math.min(...xs) + Math.max(...xs)) / 2;
		const cz = (Math.min(...zs) + Math.max(...zs)) / 2;
		const span = Math.max(Math.max(...xs) - Math.min(...xs), Math.max(...zs) - Math.min(...zs), 1e-3);
		return { cx, cz, s: 92 / span };
	});
	const map = (p) => [60 + (p[0] - mapBox.cx) * mapBox.s, 60 + (p[2] - mapBox.cz) * mapBox.s];
	const camDot = $derived(map(cam.pos));
	const looking = $derived.by(() => {
		const [ax, ay] = map(cam.pos);
		const [bx, by] = map(cam.target);
		const l = Math.hypot(bx - ax, by - ay) || 1;
		return [ax + ((bx - ax) / l) * 14, ay + ((by - ay) / l) * 14];
	});
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
			<span class="truncate text-sm font-semibold">{scene.name}</span>
			<HostUi name="Badge" props={{ variant: 'neutral', size: 'md' }}>{sceneLabel(scene)}</HostUi>
			<div class="flex-1"></div>
			<span class="hidden truncate text-xs text-fg-subtle 2xl:inline">{t('scene.hint')}</span>
			<HostUi
				name="Button"
				props={{ variant: 'secondary', size: 'xs', icon: hostIconName('target'), disabled: !ready, onclick: resetToSource }}
			>{t('scene.sourceView')}</HostUi>
		</div>

		<div class="relative min-h-0 flex-1 overflow-hidden" bind:clientWidth={w} bind:clientHeight={h}>
			<div class="absolute overflow-hidden bg-black" style:left="{(w - frameW) / 2}px" style:top="{(h - frameH) / 2}px" style:width="{frameW}px" style:height="{frameH}px">
				<!-- svelte-ignore a11y_no_noninteractive_tabindex, a11y_no_noninteractive_element_interactions -->
				<div
					bind:this={host}
					class="vp-touch-none vp-scene-surface absolute inset-0 {live ? 'cursor-grab active:cursor-grabbing' : ''}"
					role="application"
					tabindex={live ? 0 : -1}
					aria-label={t('scene.surface')}
					aria-describedby="vp-scene-keys"
					onpointerdown={down}
					onpointermove={move}
					onpointerup={up}
					onpointercancel={up}
					onwheel={wheel}
					onkeydown={key}
					oncontextmenu={(e) => e.preventDefault()}
				></div>
				<p id="vp-scene-keys" class="sr-only">{t('scene.keys')}</p>

				{#if sceneBusy(scene)}
					<div class="absolute inset-0 flex flex-col items-center justify-center gap-2 p-6 text-center">
						<HostUi name="Spinner" props={{ size: 'md' }} />
						<div class="text-sm text-white">{scene.status === 'queued' ? t('scene.status.queued') : t('scene.status.running')}</div>
						<div class="h-1 w-48 overflow-hidden rounded-full bg-white/20" role="progressbar" aria-label={t('scene.status.running')} aria-valuemin="0" aria-valuemax="100" aria-valuenow={Math.round(progress)}>
							<div class="h-full rounded-full bg-signal transition-[width] duration-150" style:width="{progress}%"></div>
						</div>
						<HostUi name="Button" props={{ variant: 'secondary', size: 'xs', onclick: () => cancelScene(scene) }}>{t('scene.cancel')}</HostUi>
					</div>
				{:else if scene.kind === 'splat' && scene.status === 'failed'}
					<div class="absolute inset-0 flex flex-col items-center justify-center gap-2 p-6 text-center">
						<Icon name="alert" class="h-6 w-6 text-warning" />
						<div class="max-w-sm text-sm text-white">{sceneErrorText(scene.error)}</div>
						<HostUi name="Button" props={{ variant: 'secondary', size: 'xs', icon: 'refresh', onclick: () => retryScene(scene) }}>{t('scene.retry')}</HostUi>
					</div>
				{:else if sceneState.engine === 'lost'}
					<div class="absolute inset-0 flex flex-col items-center justify-center gap-2 p-6 text-center" role="alert">
						<Icon name="alert" class="h-6 w-6 text-warning" />
						<div class="max-w-sm text-sm text-white">{t('scene.engine.lost')}</div>
						<HostUi name="Button" props={{ variant: 'secondary', size: 'xs', icon: 'refresh', onclick: retryEngine }}>{t('scene.retry')}</HostUi>
					</div>
				{:else if sceneState.engine === 'unsupported' || sceneState.engine === 'failed'}
					<div class="absolute inset-0 flex flex-col items-center justify-center gap-2 p-6 text-center">
						<Icon name="alert" class="h-6 w-6 text-warning" />
						<div class="max-w-sm text-sm text-white">{sceneState.engine === 'unsupported' ? t('scene.engine.unsupported') : t('scene.engine.failed')}</div>
						{#if sceneState.engine === 'failed'}
							<HostUi name="Button" props={{ variant: 'secondary', size: 'xs', icon: 'refresh', onclick: () => location.reload() }}>{t('scene.engine.reload')}</HostUi>
						{/if}
					</div>
				{:else if sceneState.status === 'failed'}
					<div class="absolute inset-0 flex flex-col items-center justify-center gap-2 p-6 text-center">
						<Icon name="alert" class="h-6 w-6 text-warning" />
						<div class="max-w-sm text-sm text-white">{sceneState.error === 'fetch_failed' ? t('scene.load.fetchFailed') : t('scene.load.failed')}</div>
						<HostUi name="Button" props={{ variant: 'secondary', size: 'xs', icon: 'refresh', onclick: retryLoad }}>{t('scene.retry')}</HostUi>
					</div>
				{:else if sceneState.engine !== 'ready' || sceneState.status === 'loading'}
					<div class="pointer-events-none absolute inset-0 flex flex-col items-center justify-center gap-2 text-center">
						<HostUi name="Spinner" props={{ size: 'md' }} />
						<div class="text-sm text-white/70">{sceneState.engine !== 'ready' ? t('scene.engine.loading') : t('scene.load.loading')}</div>
					</div>
				{/if}

				{#if live}
					<div class="vp-tc pointer-events-none absolute left-2 top-2 rounded bg-black/60 px-2 py-1 text-xs text-white">{hud}</div>
					{#if gap}
						<div class="pointer-events-none absolute bottom-2 left-2 rounded bg-black/60 px-2 py-1 text-xs text-white" role="status">
							<div class="flex items-center gap-2">
								<span class="h-1 w-16 overflow-hidden rounded-full bg-white/20">
									<span class="block h-full rounded-full {level === 'holes' ? 'bg-danger' : level === 'near' ? 'bg-warning' : 'bg-success'}" style:width="{Math.min(100, Math.max(gap.angle / 15, gap.shift / 0.25) * 100)}%"></span>
								</span>
								<span class="vp-tc">{t('scene.gap', { angle: Math.round(gap.angle), shift: Math.round(gap.shift * 100) })}</span>
							</div>
							{#if level === 'holes'}<div class="mt-0.5 text-warning">{t('scene.holes')}</div>{/if}
						</div>
					{/if}
					<svg class="pointer-events-none absolute bottom-2 right-2 rounded-lg border border-line-strong bg-surface-1/90" width="120" height="120" viewBox="0 0 120 120" role="img" aria-label={t('scene.topView')}>
						{#if source}
							{@const [sx, sy] = map(source.pos)}
							{@const [tx, ty] = map(source.target)}
							<rect x={tx - 3} y={ty - 3} width="6" height="6" fill="rgb(var(--fg-subtle))" />
							<circle cx={sx} cy={sy} r="3" fill="none" stroke="rgb(var(--fg-subtle))" />
						{/if}
						<line x1={camDot[0]} y1={camDot[1]} x2={looking[0]} y2={looking[1]} stroke="rgb(var(--signal))" stroke-width="1.5" />
						<circle cx={camDot[0]} cy={camDot[1]} r="4" fill="rgb(var(--signal))" />
					</svg>
				{/if}
			</div>
		</div>
	{/if}
</section>
