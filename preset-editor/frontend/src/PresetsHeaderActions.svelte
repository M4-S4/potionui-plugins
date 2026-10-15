<script>
	import HostUi from '../../../../sdk/HostUi.svelte';

	const NEW_PRESET_URL = '/plugins/preset-editor?new=1';
</script>

<HostUi
	name="Button"
	props={{
		variant: 'secondary',
		size: 'sm',
		icon: 'plus',
		href: NEW_PRESET_URL,
		title: 'Create a preset with the Preset Editor'
	}}
>
	New Preset
</HostUi>
