const ALPHABET = '0123456789ABCDEFGHJKMNPQRSTVWXYZ';
const TIME_LENGTH = 10;
const RANDOM_LENGTH = 16;
const PATTERN = /^[0-7][0-9A-HJKMNP-TV-Z]{25}$/;

export function ulid(now = Date.now()) {
	let time = Math.max(0, Math.floor(now));
	let head = '';
	for (let i = 0; i < TIME_LENGTH; i++) {
		head = ALPHABET[time % 32] + head;
		time = Math.floor(time / 32);
	}
	const bytes = new Uint8Array(RANDOM_LENGTH);
	globalThis.crypto.getRandomValues(bytes);
	let tail = '';
	for (const byte of bytes) tail += ALPHABET[byte & 31];
	return head + tail;
}

export function isUlid(value) {
	return typeof value === 'string' && PATTERN.test(value);
}

export function ulidTime(value) {
	if (!isUlid(value)) return null;
	let time = 0;
	for (const char of value.slice(0, TIME_LENGTH)) time = time * 32 + ALPHABET.indexOf(char);
	return time;
}
