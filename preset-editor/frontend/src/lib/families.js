const LOADER_PREFIX = 'model_loader/';
const GENERATOR_PREFIX = 'generator/';

function pipesOf(reference) {
	const list = Array.isArray(reference?.pipes) ? reference.pipes : Array.isArray(reference) ? reference : [];
	return new Map(list.filter((pipe) => pipe && typeof pipe.name === 'string').map((pipe) => [pipe.name, pipe]));
}

function generatorFor(family, generators) {
	if (generators.includes(family)) return family;
	return generators.filter((name) => name.includes(family)).sort()[0] ?? null;
}

export function familiesFrom(reference) {
	const pipes = pipesOf(reference);
	const names = [...pipes.keys()];
	const loaders = names.filter((name) => name.startsWith(LOADER_PREFIX)).map((name) => name.slice(LOADER_PREFIX.length)).sort();
	const generators = names.filter((name) => name.startsWith(GENERATOR_PREFIX)).map((name) => name.slice(GENERATOR_PREFIX.length));
	return loaders.map((family) => {
		const generator = generatorFor(family, generators);
		return {
			family,
			loader_name: `${LOADER_PREFIX}${family}`,
			generator_name: generator ? `${GENERATOR_PREFIX}${generator}` : null,
			description: pipes.get(`${LOADER_PREFIX}${family}`)?.description ?? ''
		};
	});
}

function number(value, fallback) {
	const parsed = typeof value === 'number' ? value : Number(value);
	return Number.isFinite(parsed) ? parsed : fallback;
}

export function familySpec(reference, family) {
	const pipes = pipesOf(reference);
	const entry = familiesFrom(reference).find((item) => item.family === family);
	if (!entry || !entry.generator_name) return null;
	const loader = pipes.get(entry.loader_name);
	const generator = pipes.get(entry.generator_name);
	const loaderConfig = Array.isArray(loader?.configuration) ? loader.configuration : [];
	const generatorConfig = new Map((Array.isArray(generator?.configuration) ? generator.configuration : []).map((item) => [item.name, item]));
	const modelSlots = loaderConfig.filter((item) => item.required && item.param_type === 'dict').map((item) => item.name);
	if (modelSlots.length === 0) return null;
	const guidanceKey = generatorConfig.has('guidance') ? 'guidance' : generatorConfig.has('cfg') ? 'cfg' : 'guidance';
	const sampler = generatorConfig.get('sampler');
	const choices = Array.isArray(sampler?.choices) && sampler.choices.length ? sampler.choices.map(String) : ['euler'];
	return {
		family,
		loader_name: entry.loader_name,
		generator_name: entry.generator_name,
		model_slots: modelSlots,
		has_loras: loaderConfig.some((item) => item.name === 'loras'),
		has_text_encoder_output: (Array.isArray(loader?.outputs) ? loader.outputs : []).some((item) => item.name === 'text_encoder'),
		steps_default: Math.round(number(generatorConfig.get('steps')?.default, 20)),
		guidance_key: guidanceKey,
		guidance_default: number(generatorConfig.get(guidanceKey)?.default, 4.0),
		sampler_default: String(sampler?.default || 'euler'),
		sampler_choices: choices,
		resolution_default: String(generatorConfig.get('resolution')?.default || '1024x1024')
	};
}
