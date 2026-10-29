export const POPOVER_GAP = 6;
export const POPOVER_MARGIN = 8;

const clamp = (v, a, b) => Math.min(b, Math.max(a, v));

export function popoverPosition({ anchor, panel, viewport, gap = POPOVER_GAP, margin = POPOVER_MARGIN }) {
	const a = anchor ?? { left: margin, right: margin + panel.width, top: margin, bottom: margin };
	const below = a.bottom + gap + panel.height <= viewport.height - margin;
	const above = a.top - gap - panel.height >= margin;
	return {
		left: clamp(a.right - panel.width, margin, viewport.width - panel.width - margin),
		top: below ? a.bottom + gap : above ? a.top - panel.height - gap : clamp(viewport.height - margin - panel.height, margin, a.bottom + gap),
		maxHeight: viewport.height - 2 * margin
	};
}

export function anchoredPopover(node, anchorOf) {
	let anchor = anchorOf;
	const place = () => {
		node.style.maxHeight = `${window.innerHeight - 2 * POPOVER_MARGIN}px`;
		const r = node.getBoundingClientRect();
		if (!r.width && !r.height) return;
		const at = popoverPosition({ anchor: anchor?.() ?? null, panel: r, viewport: { width: window.innerWidth, height: window.innerHeight } });
		node.style.left = `${at.left}px`;
		node.style.top = `${at.top}px`;
	};
	place();
	const resized = new ResizeObserver(place);
	resized.observe(node);
	window.addEventListener('resize', place);
	return {
		update(next) {
			anchor = next;
			place();
		},
		destroy() {
			resized.disconnect();
			window.removeEventListener('resize', place);
		}
	};
}
