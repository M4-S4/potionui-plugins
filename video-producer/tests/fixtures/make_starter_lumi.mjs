import { writeFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { starterDoc } from '../../frontend/src/lib/starter.js';
import { isUlid } from '../../frontend/src/lib/ulid.js';

const here = dirname(fileURLToPath(import.meta.url));

export const keys = (key) => `[${key}]`;

export const starterImages = {
	lumi: { itemId: 'starter-lumi', url: '/api/media/uploads/starter-lumi.jpg', filename: 'lumi.jpg', width: 1024, height: 1024 },
	bottle: { itemId: 'starter-bottle', url: '/api/media/uploads/starter-bottle.jpg', filename: 'bottle.jpg', width: 1024, height: 576 },
	'bottle-gold': { itemId: 'starter-bottle-gold', url: '/api/media/uploads/starter-bottle-gold.jpg', filename: 'bottle-gold.jpg', width: 1024, height: 576 }
};

export function stableIds(value) {
	const seen = new Map();
	const swap = (item) => {
		if (typeof item === 'string' && isUlid(item)) {
			if (!seen.has(item)) seen.set(item, `01M5R0START${String(seen.size + 1).padStart(15, '0')}`);
			return seen.get(item);
		}
		if (Array.isArray(item)) return item.map(swap);
		if (item && typeof item === 'object') return Object.fromEntries(Object.entries(item).map(([key, inner]) => [key, swap(inner)]));
		return item;
	};
	return swap(value);
}

export const makeStarterDoc = () => stableIds(JSON.parse(JSON.stringify(starterDoc(keys, keys, 'en', starterImages))));

if (process.argv[1] === fileURLToPath(import.meta.url)) {
	writeFileSync(join(here, 'starter_lumi.json'), JSON.stringify(makeStarterDoc(), null, 2) + '\n');
}
