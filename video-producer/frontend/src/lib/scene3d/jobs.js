export const RUNNING = ['queued', 'running'];

export function jobScene(scenes, job, pending = null) {
	const scene = scenes.find((s) => s?.kind === 'splat' && (s.id === job?.sceneId || (job?.id && s.jobId === job.id)));
	if (!scene) return null;
	if (scene.jobId ? job.id !== scene.jobId : pending?.has(scene.id)) return null;
	return scene;
}

export function reusableScene(scenes, assetId) {
	if (!assetId) return null;
	const built = scenes.filter((s) => s?.kind === 'splat' && s.sourceAssetId === assetId && s.sourceTime == null);
	return built.find((s) => s.status === 'done' && s.fileId) ?? built.find((s) => RUNNING.includes(s.status)) ?? built[0] ?? null;
}

export function lostScene(scene, jobs) {
	return scene.jobId ? !jobs.some((j) => j.id === scene.jobId) : !jobs.some((j) => j.sceneId === scene.id);
}

export function orphanJobs(live, scenes) {
	const out = [];
	for (const [sceneId, jobId] of live) {
		const scene = scenes.find((s) => s?.id === sceneId);
		if (!scene || scene.kind !== 'splat' || !RUNNING.includes(scene.status) || (scene.jobId && scene.jobId !== jobId)) out.push([sceneId, jobId]);
	}
	return out;
}

export function createPoller({ every, run, active, timers = globalThis }) {
	let timer = null;
	let running = false;
	let halted = false;

	function schedule() {
		if (timer !== null || running || halted || !active()) return;
		timer = timers.setTimeout(fire, every);
	}

	async function fire() {
		timer = null;
		running = true;
		let again = true;
		try {
			again = (await run()) !== false;
		} catch {
			again = true;
		} finally {
			running = false;
		}
		if (again) schedule();
	}

	return {
		arm() {
			halted = false;
			schedule();
		},
		stop() {
			halted = true;
			if (timer !== null) timers.clearTimeout(timer);
			timer = null;
		},
		get armed() {
			return timer !== null;
		},
		get running() {
			return running;
		}
	};
}
