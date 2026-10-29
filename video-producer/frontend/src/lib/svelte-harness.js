import { register } from 'node:module';

const HOST_UI = `<script>
	let { name, props = {}, children } = $props();
	const shown = $derived(JSON.stringify(props, (key, value) => (typeof value === 'function' ? undefined : value)));
</script>
<host-ui data-host={name} data-props={shown}>{@render children?.()}</host-ui>`;

const hooks = `
import { readFile } from 'node:fs/promises';
import { compile, compileModule } from ${JSON.stringify(import.meta.resolve('svelte/compiler'))};
const HOST_UI = ${JSON.stringify(HOST_UI)};
export async function load(url, context, next) {
	if (url.endsWith('/sdk/HostUi.svelte')) return { format: 'module', shortCircuit: true, source: compile(HOST_UI, { generate: 'server', filename: url }).js.code };
	if (url.endsWith('.svelte')) return { format: 'module', shortCircuit: true, source: compile(await readFile(new URL(url), 'utf8'), { generate: 'server', filename: url }).js.code };
	if (url.endsWith('.svelte.js')) return { format: 'module', shortCircuit: true, source: compileModule(await readFile(new URL(url), 'utf8'), { generate: 'client', filename: url }).js.code };
	if (url.endsWith('.json')) return { format: 'module', shortCircuit: true, source: 'export default ' + (await readFile(new URL(url), 'utf8')) };
	return next(url, context);
}`;
register(`data:text/javascript,${encodeURIComponent(hooks)}`, import.meta.url);

globalThis.window ??= Object.assign(new EventTarget(), { __potionui: { confirm: async () => true, notifications: { toast() {} }, components: {} } });

export async function renderComponent(url, props = {}) {
	const { render } = await import('svelte/server');
	const component = (await import(url)).default;
	return render(component, { props }).body;
}

export const hostUis = (html, name) => [...html.matchAll(/<host-ui data-host="([^"]*)" data-props="([^"]*)">/g)].filter(([, found]) => !name || found === name).map(([, , props]) => JSON.parse(props.replaceAll('&quot;', '"').replaceAll('&#39;', "'").replaceAll('&amp;', '&')));

export const textOf = (html) => html.replace(/<[^>]+>/g, ' ').replace(/<!--[^>]*-->/g, ' ').replace(/\s+/g, ' ').trim();
