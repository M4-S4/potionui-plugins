import { getClient, onLoaded } from './project.svelte.js';
import { ui } from './state.svelte.js';
import { WRITE_TIMEOUT_MS, canUndo, canWrite, writeBody, writerIdle, writerStep } from './promptwriter.js';

export const STATUS_TTL_MS = 60000;
export const BUSY_RETRIES = 4;
export const BUSY_DELAY_MS = 700;

const known = { status: null, at: 0 };

export function forgetWriterStatus() {
	known.status = null;
	known.at = 0;
}

export function createWriter({ client = getClient, timeout = WRITE_TIMEOUT_MS, now = Date.now, busyDelay = BUSY_DELAY_MS } = {}) {
	const box = $state({ state: writerIdle(), status: known.status, checking: false });
	let controller = null;

	const dispatch = (event) => {
		box.state = writerStep(box.state, event);
	};

	async function check({ force = false } = {}) {
		if (!force && known.status && now() - known.at < STATUS_TTL_MS) {
			box.status = known.status;
			return box.status;
		}
		const api = client();
		if (typeof api?.promptWriter !== 'function') return box.status;
		box.checking = true;
		const result = await api.promptWriter();
		box.checking = false;
		const status = result.ok ? result.data : { available: false, vision: false, name: null, code: result.error?.code || 'writer_unavailable', message: result.error?.message || null };
		if (result.ok) {
			known.status = status;
			known.at = now();
		}
		box.status = status;
		return status;
	}

	async function write({ projectId, shotId, option, doc }) {
		const api = client();
		if (!option || !projectId || typeof api?.writePrompt !== 'function' || !canWrite(box.state, box.status)) return;
		controller?.abort();
		dispatch({ type: 'start' });
		const run = box.state.run;
		const mine = new AbortController();
		controller = mine;
		const timer = setTimeout(() => {
			mine.abort();
			dispatch({ type: 'fail', run, error: { code: 'write_timeout', message: '' } });
		}, timeout);
		const body = writeBody(box.state.request, option, doc);
		let result = await api.writePrompt(projectId, shotId, body, mine.signal);
		for (let attempt = 0; attempt < BUSY_RETRIES && result.error?.code === 'write_busy' && box.state.run === run && !mine.signal.aborted; attempt += 1) {
			await new Promise((resolve) => setTimeout(resolve, busyDelay));
			if (box.state.run !== run || mine.signal.aborted) break;
			result = await api.writePrompt(projectId, shotId, body, mine.signal);
		}
		clearTimeout(timer);
		if (controller === mine) controller = null;
		if (result.ok) dispatch({ type: 'done', run, written: result.data });
		else if (result.error?.code !== 'aborted') dispatch({ type: 'fail', run, error: result.error });
	}

	function cancel() {
		controller?.abort();
		controller = null;
		dispatch({ type: 'cancel' });
	}

	function close() {
		controller?.abort();
		controller = null;
		dispatch({ type: 'close' });
	}

	function accept(current) {
		const text = box.state.proposal?.text ?? null;
		if (text === null) return null;
		dispatch({ type: 'accept', current });
		return text;
	}

	function undo(current) {
		if (!canUndo(box.state, current)) return null;
		const before = box.state.before;
		dispatch({ type: 'undo' });
		return before;
	}

	return {
		get state() {
			return box.state;
		},
		get status() {
			return box.status;
		},
		get checking() {
			return box.checking;
		},
		get busy() {
			return box.state.phase === 'writing';
		},
		ready: () => canWrite(box.state, box.status),
		undoable: (current) => canUndo(box.state, current),
		open: () => dispatch({ type: 'open' }),
		edit: (request) => dispatch({ type: 'edit', request }),
		reject: () => dispatch({ type: 'reject' }),
		forget: () => dispatch({ type: 'forget' }),
		check,
		write,
		cancel,
		close,
		accept,
		undo
	};
}

const parked = new Map();

export function parkWriter(shotId, writer) {
	const before = parked.get(shotId);
	if (before && before !== writer) before.cancel();
	parked.set(shotId, writer);
}

export function writerFor(shotId, resume = false, options = {}) {
	const kept = parked.get(shotId) ?? null;
	parked.delete(shotId);
	if (kept && resume) return kept;
	kept?.cancel();
	return createWriter(options);
}

export const parkedShots = () => [...parked.keys()];

function keptShot(modal) {
	if (modal?.type === 'library' && modal.target?.returnTo?.type === 'shot') return modal.target.returnTo.id ?? null;
	if (modal?.type === 'shot') return modal.id ?? null;
	return null;
}

export function settleParked(modal) {
	const keep = keptShot(modal);
	for (const [shotId, writer] of [...parked]) {
		if (shotId === keep) continue;
		parked.delete(shotId);
		writer.cancel();
	}
}

export const dropParked = () => settleParked(null);

onLoaded(() => dropParked());

$effect.root(() => {
	$effect(() => {
		settleParked(ui.modal);
	});
});
