import VideoProducerPage from './VideoProducerPage.svelte';
import { mount, unmount } from 'svelte';

export { VideoProducerPage as default };

export function mountPlugin(target, props) {
	return mount(VideoProducerPage, { target, props });
}

export function unmountPlugin(instance) {
	unmount(instance);
}
