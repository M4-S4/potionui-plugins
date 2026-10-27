<script>
	import { t } from '../../i18n/index.svelte.js';
	import { doc } from '../../lib/state.svelte.js';
	import { deliverySize, formatValue, ratioOf } from '../../lib/formats.js';
	import { customFormat, formatSections } from '../../lib/framing.js';
	import { formatGroupText, formatNameText, setFormat } from '../../lib/framing.svelte.js';
	import Picker from './Picker.svelte';

	let { triggerId = undefined } = $props();

	const dims = (size) => `${size[0]}×${size[1]}`;
	const current = $derived(formatValue(doc.aspect));
	const sections = $derived(
		formatSections(doc).map((section) => ({
			id: section.id,
			title: formatGroupText(section.id),
			rows: section.rows.map((row) => ({ value: row.value, ratio: row.ratio, title: [row.value, formatNameText(row.value)].filter(Boolean).join(' · '), detail: dims(row.size) }))
		}))
	);
	const custom = $derived({
		label: t('project.format.custom'),
		separator: ':',
		placeholders: ['21', '9'],
		fields: [t('project.format.customWidth'), t('project.format.customHeight')],
		check: (width, height) => {
			const found = customFormat(width, height);
			if (found.ok) return { ok: true, value: found.value, note: t('project.format.customNote', { size: dims(deliverySize(ratioOf(found.value), doc.resolution)) }) };
			return { ok: false, message: found.error === 'range' ? t('project.format.customRange') : t('project.format.customInvalid') };
		}
	});
</script>

<Picker
	label={t('project.format.label')}
	{sections}
	value={current}
	onselect={setFormat}
	glyph={ratioOf(current)}
	text={current}
	sub={dims(deliverySize(ratioOf(current), doc.resolution))}
	badge={formatNameText(current) || formatGroupText('custom')}
	search={t('project.format.search')}
	{custom}
	{triggerId}
/>
