const query = typeof matchMedia === 'function' ? matchMedia('(prefers-reduced-motion: reduce)') : null;

export const ms = (d) => (query?.matches || document.documentElement.dataset.motion === 'reduce' ? 0 : d);
