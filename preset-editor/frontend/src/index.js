import { mount, unmount } from 'svelte';
import PresetEditorPage from './PresetEditorPage.svelte';

export { PresetEditorPage as default };

export function mountPlugin(target, props) {
	return mount(PresetEditorPage, { target, props });
}

export function unmountPlugin(instance) {
	unmount(instance);
}
