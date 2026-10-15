export function isAdmin(user) {
	return user?.account_type === 'ADMIN';
}

export function pageIntent(search) {
	const params = new URLSearchParams(typeof search === 'string' ? search : '');
	const draft = params.get('draft');
	if (draft) return { kind: 'draft', id: draft };
	const preset = params.get('preset');
	if (preset) return { kind: 'preset', id: preset };
	if (params.get('new') === '1') return { kind: 'new', id: null };
	return { kind: 'list', id: null };
}
