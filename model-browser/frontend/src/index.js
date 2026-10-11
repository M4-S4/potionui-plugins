import { mount, unmount } from 'svelte';
import ModelBrowserPage from './ModelBrowserPage.svelte';

export { ModelBrowserPage as default };

// Called by the host's plugin page with `{ pluginId, route, api, user, navigate, hostComponents,
// headerActions, setHeaderTitleHidden, setHeaderHidden }`.
export function mountPlugin(target, props) {
	return mount(ModelBrowserPage, { target, props });
}

export function unmountPlugin(instance) {
	unmount(instance);
}
