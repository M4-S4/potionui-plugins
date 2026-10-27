export function compileRules(shared) {
	const flags = shared.flags;
	const conflicts = {};
	for (const [language, list] of Object.entries(shared.conflicts)) conflicts[language] = list.map((rule) => ({ id: rule.id, global: new RegExp(rule.global, flags), local: new RegExp(rule.local, flags) }));
	const cameraWords = {};
	for (const [language, source] of Object.entries(shared.cameraWords)) cameraWords[language] = new RegExp(source, flags);
	return { conflicts, cameraWords };
}

export function conflictIds(rules, language, globalText, promptText) {
	return rules.conflicts[language].filter((rule) => rule.global.test(globalText) && rule.local.test(promptText)).map((rule) => rule.id);
}

export function conflictRule(rules, language, id) {
	return rules.conflicts[language]?.find((rule) => rule.id === id) ?? null;
}

export function namesCamera(rules, language, text) {
	return rules.cameraWords[language].test(text);
}
