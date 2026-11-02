export const NARROW_WIDTH = 1280;
export const TINY_WIDTH = 640;
export const COMPACT_WIDTH = 1024;

const NARROW = `(max-width: ${NARROW_WIDTH - 1}px)`;
const TINY = `(max-width: ${TINY_WIDTH - 1}px)`;
const COMPACT = `(max-width: ${COMPACT_WIDTH - 1}px)`;

const query = (media) => (typeof window === 'undefined' || typeof window.matchMedia !== 'function' ? null : window.matchMedia(media));

export const viewport = $state({ narrow: Boolean(query(NARROW)?.matches), tiny: Boolean(query(TINY)?.matches), compact: Boolean(query(COMPACT)?.matches) });

export function watchViewport() {
	const narrow = query(NARROW);
	const tiny = query(TINY);
	const compact = query(COMPACT);
	if (!narrow || !tiny || !compact) return () => {};
	const read = () => {
		viewport.narrow = narrow.matches;
		viewport.tiny = tiny.matches;
		viewport.compact = compact.matches;
	};
	read();
	narrow.addEventListener('change', read);
	tiny.addEventListener('change', read);
	compact.addEventListener('change', read);
	return () => {
		narrow.removeEventListener('change', read);
		tiny.removeEventListener('change', read);
		compact.removeEventListener('change', read);
	};
}
