import { test } from 'node:test';
import assert from 'node:assert/strict';
import { createClient, normalizeEstimate, normalizeMe, normalizeQueue, normalizeTake } from './api.js';
import {
	aggregate,
	aspectOf,
	canUpscale,
	draftResolution,
	engineOptions,
	finalResolution,
	isInFlight,
	migrateEngine,
	optionFor,
	presetLabel,
	presetProfiles,
	progressText,
	sortTakes,
	takeAsset,
	upscaleTargetFor,
	withProfile
} from './generation.js';

const H3 = '01KX47H3MINIMAX000000000VA';
const H3_FAST = '01KX47H3FASTH30000000000VA';
const WAN = '01KX47WANVIDEO0000000000TV';
const OPENROUTER = '01M3SV8HJTGT3JPPH2BA5MP6PR';
const SEEDVR2 = '01KXB7C553THYMSMKY1QSYESFM';

const rawMe = {
	is_admin: true,
	settings: { draft_resolution: '832x480', max_parallel_jobs: 2 },
	features: { upscaler: true },
	upscale_targets: ['hd720', 'fhd1080', 'qhd1440', 'uhd2160'],
	engines: [
		{ id: 'native', name: 'Local Generation', kind: 'local', driver: 'native.local', execution_device: 'cuda:0', vram_total_gb: 24, vram_free_gb: 20.5, is_default: true },
		{ id: 'studio', name: 'Studio', kind: 'remote', driver: 'native.remote', vram_total_gb: 96, vram_free_gb: null },
		{ id: 'comfy', name: 'ComfyUI', kind: 'comfy' },
		{
			id: 'openrouter',
			name: 'OpenRouter',
			kind: 'cloud',
			driver: 'cloud.openrouter',
			models: [
				{ id: 'm-veo', name: 'Veo 3', provider_model_id: 'google/veo-3', tasks: ['text_to_video', 'image_to_video'], typical_seconds: 8, max_seconds: 8 },
				{ id: 'm-kling', name: 'Kling 2', tasks: ['text_to_video'] },
				{ name: 'no id' }
			]
		}
	],
	presets: [
		{
			id: WAN,
			name: 'Wan 2.1 / 2.2',
			engine: 'native',
			modes: { video: { default_form: 'default', fields: {} } },
			video_director: { family: 'wan' },
			resolutions: [{ value: '832x480', label: 'SD' }, { value: '1280x720', label: 'HD' }, '960x544'],
			fps: 16,
			fps_locked: false,
			limits: { default_duration: 5, max_duration: 10 },
			director_modes: ['t2v', 'i2v', 'flf'],
			profiles: ['FL2VA'],
			upscaler: false
		},
		{ id: H3, name: 'MiniMax-H3', engine: 'native', modes: { video: {}, refs: {}, upscale: {} }, video_director: { family: 'h3' }, resolutions: [{ value: '1280x720' }, { value: '1920x1080' }], fps: 24, fps_locked: true, profiles: ['FL2VA', 'Ref2VA', 'Hybrid AV'] },
		{ id: H3_FAST, name: 'MiniMax-H3-Fast', engine: 'native', modes: ['video'], director_modes: ['t2v'] },
		{ id: OPENROUTER, name: 'OpenRouter Video', engine: 'cloud', driver: 'cloud.openrouter', modes: ['txt2video', 'img2video'], video_director: { family: 'cloud' }, profiles: ['FL2VA'] },
		{ id: SEEDVR2, name: 'SeedVR2', engine: 'native', modes: { upscale: {}, video_upscale: {} }, video_director: null, upscaler: true }
	]
};

const me = normalizeMe(rawMe);

test('normalizeMe: engines, presets, features, upscale targets and settings come camelCased and checked', () => {
	assert.deepEqual(
		me.engines.map((e) => [e.id, e.kind, e.vramFree, e.models.length]),
		[
			['native', 'local', 20.5, 0],
			['studio', 'remote', null, 0],
			['openrouter', 'cloud', null, 2]
		]
	);
	assert.deepEqual(me.engines[2].models[0], { id: 'm-veo', name: 'Veo 3', providerModelId: 'google/veo-3', tasks: ['text_to_video', 'image_to_video'], typicalSeconds: 8, maxSeconds: 8 });
	const wan = me.presets.find((p) => p.id === WAN);
	assert.deepEqual(wan.resolutions, [
		{ value: '832x480', label: 'SD' },
		{ value: '1280x720', label: 'HD' },
		{ value: '960x544', label: '960x544' }
	]);
	assert.deepEqual([wan.video, wan.cloud, wan.fps, wan.fpsLocked, wan.limits.maxDuration, wan.modes], [true, false, 16, false, 10, ['video']]);
	assert.deepEqual(me.presets.find((p) => p.id === SEEDVR2).video, false);
	assert.deepEqual(me.presets.find((p) => p.id === H3_FAST).profiles, null);
	assert.deepEqual(me.features, { upscaler: true });
	assert.deepEqual(me.upscaleTargets, ['hd720', 'fhd1080', 'qhd1440', 'uhd2160']);
	assert.deepEqual(me.settings, { draftResolution: '832x480', maxParallelJobs: 2 });
	assert.deepEqual([normalizeMe({}).engines, normalizeMe({}).presets, normalizeMe({}).features], [[], [], { upscaler: false }]);
});

test('engine popup: one entry per native video preset on the first native backend, one per enabled cloud model under its backend', () => {
	const options = engineOptions(me);
	assert.deepEqual(
		options.map((o) => [o.label, o.group, o.preset, o.model, o.backend]),
		[
			['Wan 2.1 / 2.2', 'Local Generation', WAN, null, 'native'],
			['MiniMax H3', 'Local Generation', H3, null, 'native'],
			['MiniMax H3 Fast', 'Local Generation', H3_FAST, null, 'native'],
			['Veo 3', 'OpenRouter', OPENROUTER, 'm-veo', 'openrouter'],
			['Kling 2', 'OpenRouter', OPENROUTER, 'm-kling', 'openrouter']
		]
	);
	assert.equal(presetLabel({ id: '01KX47H3VDNMINIMAX000000VA', name: 'MiniMax-H3 VDN (experimental)' }), 'MiniMax H3 VDN (experimental)');
	assert.equal(optionFor(options, { preset: OPENROUTER, model: 'm-kling' }).label, 'Kling 2');
	assert.equal(optionFor(options, { preset: null }), null);
	const gemini = { id: '01M48T0Q8Q0V2WNW3WTX3FY1MW', name: 'Gemini Video', cloud: true, video: true, driver: null, modes: [], resolutions: [], profiles: ['FL2VA'] };
	const google = { id: 'google', name: 'Google', kind: 'cloud', driver: 'cloud.google', models: [{ id: 'veo-g', name: 'Veo (Google)', tasks: [] }] };
	const anonymous = { ...me, presets: [...me.presets.map((p) => ({ ...p, driver: null })), gemini], engines: [...me.engines, google] };
	assert.deepEqual(
		engineOptions(anonymous).filter((o) => o.kind === 'cloud').map((o) => [o.preset, o.model]),
		[
			[OPENROUTER, 'm-veo'],
			[OPENROUTER, 'm-kling'],
			[gemini.id, 'veo-g']
		]
	);
	const second = { id: 'openrouter-eu', name: 'OpenRouter EU', kind: 'cloud', driver: 'cloud.openrouter', models: [{ id: 'eu-veo', name: 'Veo EU', tasks: [] }] };
	const byBackend = normalizeMe({ ...rawMe, engines: [...rawMe.engines, second], presets: rawMe.presets.map((p) => (p.id === OPENROUTER ? { ...p, driver: null, backend_id: 'openrouter' } : p)) });
	assert.equal(byBackend.presets.find((p) => p.id === OPENROUTER).backendId, 'openrouter');
	assert.deepEqual(
		engineOptions(byBackend).filter((o) => o.kind === 'cloud').map((o) => [o.backend, o.model]),
		[
			['openrouter', 'm-veo'],
			['openrouter', 'm-kling'],
			['openrouter-eu', 'eu-veo']
		]
	);
	const lone = normalizeMe({ ...rawMe, presets: rawMe.presets.map((p) => (p.id === OPENROUTER ? { ...p, id: 'custom-cloud', driver: null, backend_id: 'openrouter' } : p)) });
	assert.deepEqual(engineOptions({ ...lone, engines: [...lone.engines, normalizeMe({ engines: [second] }).engines[0]] }).filter((o) => o.kind === 'cloud').map((o) => [o.preset, o.backend]), [
		['custom-cloud', 'openrouter'],
		['custom-cloud', 'openrouter']
	]);
	const byDriver = normalizeMe({ ...rawMe, engines: [...rawMe.engines, second] });
	assert.deepEqual(engineOptions(byDriver).filter((o) => o.kind === 'cloud').map((o) => o.backend), ['openrouter', 'openrouter', 'openrouter-eu']);
	const cloudOnly = { ...me, engines: me.engines.filter((e) => e.kind === 'cloud') };
	assert.deepEqual(engineOptions(cloudOnly).map((o) => o.model), ['m-veo', 'm-kling']);
	assert.deepEqual(engineOptions({ engines: [], presets: me.presets }), []);
	assert.deepEqual(presetProfiles(me.presets.find((p) => p.id === H3_FAST)), ['FL2VA', 'Ref2VA', 'Hybrid AV']);
	assert.deepEqual(presetProfiles(me.presets.find((p) => p.id === WAN)), ['FL2VA']);
});

test('engine popup: a memory profile preset keeps the MiniMax H3 name and shows its profile once', () => {
	const profiled = normalizeMe({
		...rawMe,
		presets: [
			...rawMe.presets,
			{ id: '01M54HN72B0KY7H63BKQ16T253', name: 'MiniMax-H3 (12 GB)', engine: 'native', modes: { video: {} }, video_director: { family: 'h3' }, profile: '12 GB', profiles: ['FL2VA', 'Hybrid AV'] },
			{ id: '01M54HN72PABVRE54YNQA2Q7ZT', name: 'MiniMax-H3-Fast', engine: 'native', modes: { video: {} }, video_director: { family: 'h3' }, profile: ' 12 GB ' },
			{ id: 'wan-low', name: 'Wan 2.1 / 2.2', engine: 'native', modes: { video: {} }, video_director: { family: 'wan' }, profile: null }
		]
	});
	assert.equal(profiled.presets.find((p) => p.id === '01M54HN72B0KY7H63BKQ16T253').profile, '12 GB');
	assert.equal(profiled.presets.find((p) => p.id === WAN).profile, null);
	const labels = Object.fromEntries(engineOptions(profiled).filter((o) => !o.model).map((o) => [o.preset, o.label]));
	assert.equal(labels['01M54HN72B0KY7H63BKQ16T253'], 'MiniMax H3 (12 GB)');
	assert.equal(labels['01M54HN72PABVRE54YNQA2Q7ZT'], 'MiniMax H3 Fast · 12 GB');
	assert.equal(labels['wan-low'], 'Wan 2.1 / 2.2');
	assert.equal(labels[H3], 'MiniMax H3');
	assert.deepEqual(presetProfiles(profiled.presets.find((p) => p.id === '01M54HN72PABVRE54YNQA2Q7ZT')), ['FL2VA', 'Ref2VA', 'Hybrid AV']);
});

test('withProfile: adds only the parts of the memory profile the label does not already say', () => {
	assert.equal(withProfile('Wan 2.1 T2V 1.3B (8 GB)', '8 GB · 32 GB RAM'), 'Wan 2.1 T2V 1.3B (8 GB) · 32 GB RAM');
	assert.equal(withProfile('Wan 2.2 14B Lightning (12 GB)', '12 GB · 48 GB RAM'), 'Wan 2.2 14B Lightning (12 GB) · 48 GB RAM');
	assert.equal(withProfile('MiniMax H3 Fast', '12 GB · 64 GB RAM'), 'MiniMax H3 Fast · 12 GB · 64 GB RAM');
	assert.equal(withProfile('MiniMax H3 Fast', '12 GB'), 'MiniMax H3 Fast · 12 GB');
	assert.equal(withProfile('Wan 2.1 / 2.2', ''), 'Wan 2.1 / 2.2');
	assert.equal(withProfile('Wan 2.1 / 2.2', null), 'Wan 2.1 / 2.2');
	assert.equal(withProfile('Wan 2.1 / 2.2', undefined), 'Wan 2.1 / 2.2');
	assert.equal(withProfile('Wan 2.1 / 2.2', ' · '), 'Wan 2.1 / 2.2');
	assert.equal(withProfile('MiniMax H3 (12 GB)', '12 GB'), 'MiniMax H3 (12 GB)');
	assert.equal(withProfile('MiniMax H3 (12 GB)', '12 gb'), 'MiniMax H3 (12 GB)');
	assert.equal(withProfile('Wan 2.1 T2V 1.3B (8 GB · 32 GB RAM)', '8 GB · 32 GB RAM'), 'Wan 2.1 T2V 1.3B (8 GB · 32 GB RAM)');
});

test('engine popup: a hardware tier preset shows its VRAM once and its RAM after the name', () => {
	const WAN_1_3B = '01M57QPEMDPKHHW83YSEYBN0WZ';
	const WAN_LIGHTNING = '01M57QPEMDPKHHW83YSEYBN0X1';
	const tiers = normalizeMe({
		...rawMe,
		presets: [
			...rawMe.presets,
			{ id: WAN_1_3B, name: 'Wan 2.1 T2V 1.3B (8 GB)', engine: 'native', modes: { video: {} }, video_director: { family: 'wan' }, profile: '8 GB · 32 GB RAM' },
			{ id: WAN_LIGHTNING, name: 'Wan 2.2 14B Lightning (12 GB)', engine: 'native', modes: { video: {} }, video_director: { family: 'wan' }, profile: '12 GB · 32 GB RAM' }
		]
	});
	const labels = Object.fromEntries(engineOptions(tiers).filter((o) => !o.model).map((o) => [o.preset, o.label]));
	assert.equal(labels[WAN_1_3B], 'Wan 2.1 T2V 1.3B (8 GB) · 32 GB RAM');
	assert.equal(labels[WAN_LIGHTNING], 'Wan 2.2 14B Lightning (12 GB) · 32 GB RAM');
	assert.equal(labels[WAN], 'Wan 2.1 / 2.2');
	assert.deepEqual(presetProfiles(tiers.presets.find((p) => p.id === WAN_1_3B)), ['FL2VA']);
});

test('migrateEngine: legacy local / studio / cloud backends map to the first engine of that kind and get a default entry', () => {
	assert.deepEqual(migrateEngine({ backend: 'local' }, me), { backend: 'native', preset: WAN, model: null });
	assert.deepEqual(migrateEngine({ backend: 'studio' }, me), { backend: 'native', preset: WAN, model: null });
	assert.deepEqual(migrateEngine({ backend: 'cloud', preset: null, model: null }, me), { backend: 'openrouter', preset: OPENROUTER, model: 'm-veo' });
	assert.deepEqual(migrateEngine({ backend: 'studio', preset: H3, model: null }, me), { backend: 'native', preset: H3, model: null });
	assert.deepEqual(migrateEngine({ backend: 'gone', preset: 'unassigned', model: null }, me), { backend: 'native', preset: 'unassigned', model: null });
	assert.deepEqual(migrateEngine({ backend: 'local' }, { engines: [], presets: [] }), { backend: 'local', preset: null, model: null });
	assert.deepEqual(migrateEngine({ backend: 'cloud' }, { engines: [me.engines[0]], presets: [] }), { backend: 'native', preset: null, model: null });
});

test('normalizeTake: the take row of the contract becomes camelCase with safe defaults', () => {
	const take = normalizeTake({
		id: 't1',
		project_id: 'p1',
		shot_id: 's1',
		generation_id: 'g1',
		quality: 'draft',
		kind: 'render',
		parent_take_id: null,
		preset_id: WAN,
		mode: 'video',
		director_mode: 't2v',
		backend_id: 'native',
		model_id: null,
		seed: 1234,
		resolution: '832x480',
		status: 'done',
		progress: 100,
		step: null,
		variant: 'B',
		chosen: 1,
		flag: 'keep',
		profile: 'FL2VA',
		prompt_text: 'A lighthouse',
		file_path: '/x.mp4',
		url: '/api/media/generations/g1/x.mp4',
		thumb_url: '/api/media/generations/g1/x.mp4?size=medium',
		file_id: 7,
		width: 832,
		height: 480,
		duration_s: 5,
		fps: 16,
		error_code: null,
		error_message: null,
		units_reserved: 0.83,
		created_at: '2026-10-17T10:00:00Z',
		started_at: '2026-10-17T10:00:05Z',
		finished_at: '2026-10-17T10:01:05Z'
	});
	assert.deepEqual(
		[take.shotId, take.generationId, take.directorMode, take.chosen, take.flag, take.fileId, take.durationS, take.promptText, take.unitsReserved],
		['s1', 'g1', 't2v', true, 'keep', '7', 5, 'A lighthouse', 0.83]
	);
	const odd = normalizeTake({ id: 't2', status: 'paused', director_mode: 'x', flag: 'maybe', quality: 'ultra' });
	assert.deepEqual([odd.status, odd.directorMode, odd.flag, odd.quality, odd.kind, odd.variant, odd.generationId, odd.progress], ['queued', null, null, 'draft', 'render', 'A', null, null]);
	assert.equal(normalizeTake({ status: 'done' }), null);
});

test('normalizeEstimate and normalizeQueue: every block of the contract, null where the server says so', () => {
	const est = normalizeEstimate({
		shots: [{ shot_id: 's1', director_mode: 'flf', seconds: 5, resolution: '832x480', fps: 16 }, { bad: true }],
		vram: { estimate_gb: 21.4, free_gb: 18, total_gb: 24, streams: true, unknown: false, backend_id: 'native' },
		time: { seconds: null, samples: 0 },
		quota: { limit: 600, used: 590, remaining: 10, exempt: false, needed_minutes: 12.5, applies: true, blocks: true },
		cost: null,
		blocks: [{ code: 'quota_exceeded', message: 'Quota exceeded' }, { message: 'no code' }],
		warnings: [{ code: 'vram_stream', message: 'will stream through host RAM, slower' }, { code: 'fl2va_no_frame', message: 'x', data: { shot_id: 's1' } }]
	});
	assert.deepEqual(est.shots, [{ shotId: 's1', directorMode: 'flf', seconds: 5, resolution: '832x480', fps: 16 }]);
	assert.deepEqual(est.vram, { estimateGb: 21.4, freeGb: 18, totalGb: 24, streams: true, unknown: false, backendId: 'native' });
	assert.deepEqual(est.time, { seconds: null, samples: 0 });
	assert.deepEqual(est.quota, { limit: 600, used: 590, remaining: 10, exempt: false, neededMinutes: 12.5, applies: true, blocks: true });
	assert.equal(est.cost, null);
	assert.deepEqual(est.blocks.map((b) => b.code), ['quota_exceeded']);
	assert.deepEqual(est.warnings[1].data, { shot_id: 's1' });
	const cloud = normalizeEstimate({ vram: null, quota: { applies: false, needed_minutes: 0 }, cost: { total_usd: '0.84', known: true, message: null } });
	assert.deepEqual([cloud.vram, cloud.quota.applies, cloud.cost], [null, false, { totalUsd: '0.84', known: true, message: null }]);
	const queue = normalizeQueue({ takes: [{ id: 't1', status: 'running', progress: 40 }], slots: { in_flight: 1, max: 2 } });
	assert.deepEqual([queue.takes[0].progress, queue.slots], [40, { inFlight: 1, max: 2 }]);
});

test('client: take, estimate, generation and queue routes with their bodies', async () => {
	const calls = [];
	const take = { id: 't1', status: 'queued' };
	const responses = [
		{ success: true, data: { takes: [take] } },
		{ success: true, data: { take: { ...take, chosen: true } } },
		{ success: true, data: { take: { ...take, flag: 'reject' } } },
		{ success: true, data: { deleted: 't1' } },
		{ success: true, data: { take: { id: 't9', quality: 'final', kind: 'upscale', parent_take_id: 't1' } } },
		{ success: true, data: { shots: [], vram: null, time: { seconds: 30, samples: 3 }, quota: null, cost: null, blocks: [], warnings: [] } },
		Object.assign(new Error('blocked'), { status: 409, body: { detail: { success: false, error: 'blocked', message: 'Blocked', data: { blocks: [{ code: 'no_preset', message: 'x' }] } } } }),
		{ success: true, data: { take: { ...take, status: 'cancelled' } } },
		{ success: true, data: { take: { id: 't3', status: 'queued' } } },
		{ success: true, data: { takes: [], slots: { in_flight: 0, max: 2 } } }
	];
	const client = createClient({
		async request(method, path, data) {
			calls.push([method, path, data]);
			const next = responses.shift();
			if (next instanceof Error) throw next;
			return next;
		}
	});
	assert.equal((await client.listTakes('p1')).data[0].id, 't1');
	assert.equal((await client.chooseTake('p1', 't1', true)).data.chosen, true);
	assert.equal((await client.flagTake('p1', 't1', 'reject')).data.flag, 'reject');
	assert.deepEqual((await client.deleteTake('p1', 't1')).data, { deleted: 't1' });
	assert.equal((await client.finalTake('p1', 't1', 'upscale', 'fhd1080')).data.parentTakeId, 't1');
	const body = { shots: ['s1'], quality: 'draft', variants: 2, preset_id: WAN, model_id: null };
	assert.equal((await client.estimate('p1', body)).data.time.samples, 3);
	const blocked = await client.generate('p1', body);
	assert.deepEqual([blocked.ok, blocked.error.status, blocked.error.code, blocked.error.data.blocks[0].code], [false, 409, 'blocked', 'no_preset']);
	assert.equal((await client.cancelTake('t1')).data.status, 'cancelled');
	assert.equal((await client.retryTake('t2')).data.id, 't3');
	assert.deepEqual((await client.queue('p1')).data.slots, { inFlight: 0, max: 2 });
	assert.deepEqual(calls, [
		['GET', '/projects/p1/takes', undefined],
		['POST', '/projects/p1/takes/t1/choose', { chosen: true }],
		['POST', '/projects/p1/takes/t1/flag', { flag: 'reject' }],
		['DELETE', '/projects/p1/takes/t1', undefined],
		['POST', '/projects/p1/takes/t1/final', { method: 'upscale', target: 'fhd1080' }],
		['POST', '/projects/p1/estimate', body],
		['POST', '/projects/p1/generate', body],
		['POST', '/takes/t1/cancel', {}],
		['POST', '/takes/t2/retry', {}],
		['GET', '/projects/p1/queue', undefined]
	]);
});

test('client: an estimate with a signal goes through fetchRaw and can be aborted', async () => {
	const seen = [];
	const api = {
		async fetchRaw(path, init) {
			seen.push([path, init.method, JSON.parse(init.body), init.signal instanceof AbortSignal]);
			if (init.signal.aborted) throw Object.assign(new Error('aborted'), { name: 'AbortError' });
			return { ok: true, status: 200, json: async () => ({ success: true, data: { time: { seconds: 12, samples: 1 } } }) };
		}
	};
	const client = createClient(api);
	const controller = new AbortController();
	assert.equal((await client.estimate('p1', { shots: ['s1'] }, controller.signal)).data.time.seconds, 12);
	controller.abort();
	assert.equal((await client.estimate('p1', { shots: ['s1'] }, controller.signal)).error.code, 'aborted');
	assert.deepEqual(seen[0], ['/projects/p1/estimate', 'POST', { shots: ['s1'] }, true]);
});

test('aggregate: the Production bar follows the takes in flight, mean progress, first step', () => {
	assert.deepEqual(aggregate([]), { state: 'idle', progress: 0, step: '', count: 0, running: 0 });
	assert.deepEqual(aggregate([{ status: 'done' }, { status: 'failed' }]).state, 'idle');
	const running = aggregate([
		{ status: 'running', progress: 60, step: 'Denoising 18/30' },
		{ status: 'queued', progress: null },
		{ status: 'running', progress: 150, step: null },
		{ status: 'done', progress: 100 }
	]);
	assert.deepEqual(running, { state: 'running', progress: (60 + 0 + 100) / 3, step: 'Denoising 18/30', count: 3, running: 2 });
	assert.ok(isInFlight({ status: 'queued' }) && isInFlight({ status: 'running' }) && !isInFlight({ status: 'cancelled' }));
});

test('resolutions: only the sizes in the project aspect count; drafts use the admin setting or the nearest, finals the largest', () => {
	const wan = me.presets.find((p) => p.id === WAN);
	const h3 = me.presets.find((p) => p.id === H3);
	const wide = aspectOf('16:9', '1080p');
	assert.equal(draftResolution(wan, '832x480', wide), '832x480');
	assert.equal(draftResolution(h3, '832x480', wide), '1280x720');
	assert.equal(draftResolution(h3, null, wide), null);
	assert.equal(finalResolution(wan, wide), '1280x720');
	assert.equal(finalResolution(h3, wide), '1920x1080');
	const square = { resolutions: ['832x480', '480x832', '960x544', '1280x720', '720x1280', '512x512', '1024x1024'].map((value) => ({ value, label: value })) };
	assert.equal(finalResolution(square, wide), '1280x720');
	assert.equal(finalResolution(square, aspectOf('1:1')), '1024x1024');
	assert.equal(finalResolution(square, aspectOf('9:16')), '720x1280');
	assert.equal(draftResolution(square, '832x480', aspectOf('9:16')), '480x832');
	assert.equal(draftResolution(square, '832x480', aspectOf('1:1')), '512x512');
	assert.equal(finalResolution(square, aspectOf('2.39:1')), '1280x720');
	assert.equal(aspectOf('nope', '1280x720'), 1280 / 720);
	assert.equal(aspectOf(undefined, '1080p'), 16 / 9);
	assert.equal(draftResolution({ resolutions: [] }, '832x480', wide), null);
	assert.equal(finalResolution(null, wide), null);
	assert.equal(upscaleTargetFor('4K'), 'uhd2160');
	assert.equal(upscaleTargetFor('1080p', ['hd720', 'qhd1440']), 'qhd1440');
	assert.equal(upscaleTargetFor('720p'), 'hd720');
});

test('progress text: core markers become readable labels, a marker-only message gives way to current_step', () => {
	assert.equal(progressText('<<PIPE:Generating>>', null), 'Generating');
	assert.equal(progressText('<<PIPE:Generating>>', 'Sampling 12/30'), 'Sampling 12/30');
	assert.equal(progressText('<<PIPE:Generating>> <<MODEL:wan2.2_t2v_high_noise>>', null), 'Generating · wan2.2_t2v_high_noise');
	assert.equal(progressText('Generation completed in <<TIME:93.40s>>', 'x'), 'Generation completed in 93.40s');
	assert.equal(progressText('Loading <<MODEL:umt5_xxl:cpu>> on <<GPU:RTX 4090>>', null), 'Loading umt5_xxl on RTX 4090');
	assert.equal(progressText('<<UNKNOWN:x>>', '<<PIPE:Decoding>>'), 'Decoding');
	assert.equal(progressText('', ''), null);
	assert.equal(progressText(null, 'sampling'), 'sampling');
	assert.equal(normalizeTake({ id: 't', step: '<<PIPE:Generating>>' }).step, 'Generating');
});

test('takes: a done take becomes a gen-<takeId> asset, H3 upscales by itself', () => {
	const take = normalizeTake({ id: 't1', shot_id: 's1', generation_id: 'g1', file_id: 'f1', quality: 'final', status: 'done', url: '/api/media/generations/g1/a.mp4', width: 1920, height: 1080, duration_s: 5, fps: 24 });
	assert.deepEqual(takeAsset(take, 'Dawn · Final A'), {
		id: 'gen-t1',
		kind: 'video',
		name: 'Dawn · Final A',
		src: '/api/media/generations/g1/a.mp4',
		origin: { kind: 'history', generationId: 'g1', fileId: 'f1' },
		srcDur: 5,
		width: 1920,
		height: 1080,
		fps: 24,
		res: '1920×1080',
		generated: true,
		quality: 'final',
		resultId: 't1',
		role: null,
		synth: null,
		transcript: null,
		character: null,
		lipSync: null
	});
	assert.equal(takeAsset({ ...take, fileId: null }, 'x').origin, null);
	assert.equal(canUpscale(null, me), false);
	assert.equal(canUpscale({ presetId: WAN }, me), true);
	assert.equal(canUpscale({ presetId: WAN }, { ...me, features: { upscaler: false } }), false);
	assert.equal(canUpscale({ presetId: H3 }, { ...me, features: { upscaler: false } }), true);
	assert.equal(canUpscale({ presetId: H3_FAST }, { ...me, features: { upscaler: false } }), false);
	assert.equal(canUpscale({ presetId: H3_FAST }, me), true);
	assert.equal(canUpscale({ presetId: '01KX47H3VDNMINIMAX000000VA' }, me), true);
	assert.equal(canUpscale({ presetId: H3 }, { ...me, presets: me.presets.filter((p) => p.id !== H3) }), false);
	assert.deepEqual(
		sortTakes([
			{ id: 'c', quality: 'final', createdAt: '1', variant: 'A' },
			{ id: 'b', quality: 'draft', createdAt: '2', variant: 'A' },
			{ id: 'a', quality: 'draft', createdAt: '1', variant: 'B' }
		]).map((x) => x.id),
		['a', 'b', 'c']
	);
});
