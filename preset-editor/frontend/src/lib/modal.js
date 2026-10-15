import { mount, unmount } from 'svelte';

export function openPluginModal({
	title,
	subtitle,
	size = 'md',
	confirmLabel = 'Confirm',
	confirmVariant = 'primary',
	body,
	props = {},
	onConfirm,
	onCancel
}) {
	const PluginModal = globalThis.window?.__potionui?.components?.PluginModal;
	if (!PluginModal || typeof document === 'undefined') return null;
	const host = document.createElement('div');
	document.body.appendChild(host);
	let inner = null;
	let instance = null;
	let closed = false;

	const handle = {
		update(patch) {
			if (!closed && instance) PluginModal.update(instance, patch);
		},
		close() {
			if (closed) return;
			closed = true;
			if (inner) {
				unmount(inner);
				inner = null;
			}
			if (instance) PluginModal.unmount(instance);
			host.remove();
		}
	};

	instance = PluginModal.mount(host, {
		isOpen: true,
		title,
		subtitle,
		size,
		confirmLabel,
		confirmVariant,
		busy: false,
		confirmDisabled: true,
		onConfirm: () => onConfirm?.(handle),
		onCancel: () => {
			onCancel?.(handle);
			handle.close();
		},
		mountBody: (target) => {
			inner = mount(body, { target, props });
			return () => {
				if (inner) {
					unmount(inner);
					inner = null;
				}
			};
		}
	});
	return handle;
}
