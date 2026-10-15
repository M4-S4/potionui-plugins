import { test } from 'node:test';
import assert from 'node:assert/strict';
import { familiesFrom, familySpec } from './families.js';

const config = (name, overrides = {}) => ({ name, param_type: 'str', default: null, required: false, choices: null, ...overrides });

const REFERENCE = {
	pipes: [
		{ name: 'gallery', inputs: [], outputs: [], configuration: [] },
		{
			name: 'model_loader/z_image',
			description: 'Load a native Z-Image checkpoint set',
			outputs: [{ name: 'model', io_type: 'MODEL' }, { name: 'text_encoder', io_type: 'TEXT_ENCODER' }],
			configuration: [
				config('diffusion_model', { param_type: 'dict', required: true }),
				config('text_encoder', { param_type: 'dict', required: true }),
				config('vae', { param_type: 'dict', required: true }),
				config('loras', { param_type: 'list', default: [] }),
				config('device', { default: 'cuda' })
			]
		},
		{
			name: 'generator/z_image',
			outputs: [{ name: 'image', io_type: 'IMAGE' }],
			configuration: [
				config('steps', { param_type: 'int', default: 8 }),
				config('guidance', { param_type: 'float', default: 1.0 }),
				config('sampler', { default: 'euler' }),
				config('resolution', { default: '1024x1024' })
			]
		},
		{
			name: 'model_loader/wan22',
			outputs: [{ name: 'model', io_type: 'MODEL' }],
			configuration: [config('diffusion_model', { param_type: 'dict', required: true }), config('vae', { param_type: 'dict', required: true })]
		},
		{
			name: 'generator/txt2vid_wan22',
			configuration: [config('steps', { param_type: 'int', default: '30' }), config('cfg', { param_type: 'float', default: 5 }), config('sampler', { default: 'unipc', choices: ['unipc', 'euler'] })]
		},
		{ name: 'generator/img2vid_wan22', configuration: [] },
		{ name: 'model_loader/orphan', configuration: [config('model', { param_type: 'dict', required: true })] },
		{ name: 'model_loader/nothing', configuration: [] }
	]
};

test('familiesFrom lists every loader with its generator, exact name first, then the first containing one', () => {
	assert.deepEqual(
		familiesFrom(REFERENCE).map((item) => [item.family, item.generator_name]),
		[
			['nothing', null],
			['orphan', null],
			['wan22', 'generator/img2vid_wan22'],
			['z_image', 'generator/z_image']
		]
	);
	assert.equal(familiesFrom(REFERENCE)[3].description, 'Load a native Z-Image checkpoint set');
	assert.deepEqual(familiesFrom(null), []);
	assert.deepEqual(familiesFrom(REFERENCE.pipes).length, 4);
});

test('familySpec derives the scaffold data from the loader and generator specs', () => {
	assert.deepEqual(familySpec(REFERENCE, 'z_image'), {
		family: 'z_image',
		loader_name: 'model_loader/z_image',
		generator_name: 'generator/z_image',
		model_slots: ['diffusion_model', 'text_encoder', 'vae'],
		has_loras: true,
		has_text_encoder_output: true,
		steps_default: 8,
		guidance_key: 'guidance',
		guidance_default: 1,
		sampler_default: 'euler',
		sampler_choices: ['euler'],
		resolution_default: '1024x1024'
	});
});

test('familySpec falls back to defaults and uses cfg when the generator declares it', () => {
	const wan = familySpec({ pipes: REFERENCE.pipes.filter((pipe) => pipe.name !== 'generator/img2vid_wan22') }, 'wan22');
	assert.deepEqual(wan, {
		family: 'wan22',
		loader_name: 'model_loader/wan22',
		generator_name: 'generator/txt2vid_wan22',
		model_slots: ['diffusion_model', 'vae'],
		has_loras: false,
		has_text_encoder_output: false,
		steps_default: 30,
		guidance_key: 'cfg',
		guidance_default: 5,
		sampler_default: 'unipc',
		sampler_choices: ['unipc', 'euler'],
		resolution_default: '1024x1024'
	});
});

test('familySpec is null without a generator, without model slots or for an unknown family', () => {
	assert.equal(familySpec(REFERENCE, 'orphan'), null);
	assert.equal(familySpec(REFERENCE, 'nothing'), null);
	assert.equal(familySpec(REFERENCE, 'flux'), null);
});
