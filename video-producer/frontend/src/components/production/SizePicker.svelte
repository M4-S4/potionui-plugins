<script>
	import { formatNumber, t } from '../../i18n/index.svelte.js';
	import { ui, doc } from '../../lib/state.svelte.js';
	import { aspectOf, presetLabel } from '../../lib/generation.js';
	import { DRAFT, engineOf, framingOf, parseSize, pickSize, ratioText } from '../../lib/formats.js';
	import { BASE_SIZE, customSize, measuredFor, percent, sizeSections } from '../../lib/framing.js';
	import Picker from '../shell/Picker.svelte';

	let { preset, quality, value = null, backend = null, onselect, variant = 'field', triggerId = undefined } = $props();

	const AUTO = 'auto';
	const dims = (text) => String(text ?? '—').replace('x', '×');
	const engine = $derived(presetLabel(preset));
	const ratio = $derived(aspectOf(doc.aspect, doc.resolution));
	const setting = $derived(ui.me?.settings?.draftResolution ?? null);
	const measured = $derived(backend ? measuredFor(ui.me, preset?.id, backend) : null);
	const options = $derived((preset?.resolutions ?? []).map((option) => option.value));
	const offered = $derived(options.some((option) => parseSize(option)));
	const found = $derived(pickSize(options, ratio, quality, setting, value, preset?.id ?? null));
	const picked = $derived(offered ? found : { size: null, chosen: null });
	const data = $derived(sizeSections({ preset, ratio, quality, setting, chosen: picked.chosen ? value : null, measured, framing: framingOf(doc) }));
	const selected = $derived(picked.chosen ? picked.size : AUTO);
	const unmeasured = (size) => measured !== null && size !== null && !measured.includes(size);

	function badges(row) {
		const list = [];
		if (row.value !== BASE_SIZE && row.cost) list.push({ text: t('production.size.cost', { value: formatNumber(row.cost, { maximumFractionDigits: 1 }) }), tip: t('production.size.costTip', { value: formatNumber(row.cost, { maximumFractionDigits: 1 }), base: dims(BASE_SIZE) }) });
		if (row.measured === false) list.push({ text: t('production.size.unmeasured'), tip: t('production.size.unmeasuredTip') });
		if (row.fit === 'crop') list.push({ text: t('production.size.cropped', { loss: percent(row.loss) }), tip: t('production.size.croppedTip', { aspect: doc.aspect }) });
		if (row.fit === 'bars') list.push({ text: t('production.size.bars'), tip: t('production.size.barsTip', { aspect: doc.aspect }) });
		return list;
	}

	function tierText(id) {
		if (id === 'high') return t('production.size.tier.high');
		if (id === 'mid') return t('production.size.tier.mid');
		if (id === 'low') return t('production.size.tier.low');
		return t('production.size.tier.small');
	}

	const sections = $derived([
		{
			id: AUTO,
			title: '',
			rows: [{ value: AUTO, ratio: parseSize(data.auto) ? parseSize(data.auto)[0] / parseSize(data.auto)[1] : null, title: t('production.size.auto'), detail: dims(data.auto), hint: quality === DRAFT ? t('production.size.autoDraft') : t('production.size.autoFinal'), badges: [] }]
		},
		...data.sections.map((section) => ({
			id: section.id,
			title: tierText(section.id),
			rows: section.rows.map((row) => ({ value: row.value, ratio: row.ratio, title: row.own ? t('production.size.own', { ratio: ratioText(row.ratio) }) : ratioText(row.ratio), detail: dims(row.value), badges: badges(row) }))
		}))
	]);

	function message(found) {
		if (found.error === 'bounds') return t('production.size.error.bounds');
		if (found.error === 'ratio') return t('production.size.error.ratio', { engine });
		if (found.error === 'area') return t('production.size.error.area', { engine, max: formatNumber(engineOf(preset?.id).maxPixels ?? 0) });
		return t('production.size.error.invalid');
	}

	const custom = $derived({
		label: t('production.size.custom'),
		separator: '×',
		placeholders: ['1280', '720'],
		fields: [t('production.size.width'), t('production.size.height')],
		check: (width, height) => {
			const found = customSize(width, height, preset?.id ?? null);
			if (!found.ok) return { ok: false, message: message(found) };
			return { ok: true, value: found.value, note: found.snapped ? t('production.size.sent', { size: dims(found.value) }) : '' };
		}
	});
	const tip = $derived(quality === DRAFT ? t('production.size.draftTip', { engine, size: dims(picked.size) }) : t('production.size.finalTip', { engine, size: dims(picked.size) }));
	const badge = $derived(selected === AUTO ? t('production.size.auto') : unmeasured(picked.size) ? t('production.size.unmeasured') : '');
</script>

<Picker
	label={quality === DRAFT ? t('production.size.draftLabel', { engine }) : t('production.size.finalLabel', { engine })}
	{sections}
	value={selected}
	onselect={(v) => onselect(v === AUTO ? null : v)}
	glyph={variant === 'field' && parseSize(picked.size) ? parseSize(picked.size)[0] / parseSize(picked.size)[1] : null}
	text={dims(picked.size)}
	sub={variant === 'field' && parseSize(picked.size) ? ratioText(parseSize(picked.size)[0] / parseSize(picked.size)[1]) : ''}
	badge={variant === 'field' ? badge : ''}
	tip={variant === 'popup' ? tip : ''}
	search={variant === 'field' ? t('production.size.search') : ''}
	{custom}
	{variant}
	{triggerId}
	disabled={!picked.size}
/>
