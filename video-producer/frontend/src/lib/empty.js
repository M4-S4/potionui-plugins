import { mountHostSlot } from './host.js';

export function emptyActions(buttons, hint = '') {
	return {
		slot(el) {
			const row = el.appendChild(document.createElement('div'));
			row.className = 'flex flex-wrap items-center justify-center gap-1.5';
			const mounted = buttons.map((props) => mountHostSlot(row.appendChild(document.createElement('div')), 'Button', { size: 'xs', ...props }));
			const note = hint ? el.appendChild(document.createElement('p')) : null;
			if (note) {
				note.className = 'w-full text-xs text-fg-subtle';
				note.textContent = hint;
			}
			return () => {
				for (const unmount of mounted) unmount();
				row.remove();
				note?.remove();
			};
		}
	};
}
