export function shadeOf(scrollLeft, clientWidth, scrollWidth, slack = 1) {
	const start = scrollLeft > slack;
	const end = scrollLeft + clientWidth < scrollWidth - slack;
	if (start && end) return 'both';
	if (start) return 'start';
	return end ? 'end' : 'none';
}

export function scrollShade(node) {
	const update = () => node.setAttribute('data-shade', shadeOf(node.scrollLeft, node.clientWidth, node.scrollWidth));
	const wheel = (event) => {
		if (node.scrollWidth <= node.clientWidth || Math.abs(event.deltaY) <= Math.abs(event.deltaX)) return;
		node.scrollLeft += event.deltaY;
		event.preventDefault();
	};
	update();
	const resized = typeof ResizeObserver === 'function' ? new ResizeObserver(update) : null;
	resized?.observe(node);
	const changed = typeof MutationObserver === 'function' ? new MutationObserver(update) : null;
	changed?.observe(node, { childList: true, subtree: true, characterData: true });
	node.addEventListener('scroll', update, { passive: true });
	node.addEventListener('wheel', wheel, { passive: false });
	return {
		destroy() {
			resized?.disconnect();
			changed?.disconnect();
			node.removeEventListener('scroll', update);
			node.removeEventListener('wheel', wheel);
		}
	};
}
