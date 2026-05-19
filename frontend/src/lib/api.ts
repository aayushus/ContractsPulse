import { authState } from './auth.svelte';

export function getApiBase(): string {
	if (typeof window !== 'undefined') {
		const u = new URL(window.location.href);
		// If running in local development or default docker setup on port 5173,
		// direct backend queries to port 9432.
		// If running behind a reverse proxy (e.g. exposed on port 80, 443, etc.),
		// route backend queries on the same host/port so the proxy can handle routing.
		if (u.port === '5173') {
			return `${u.protocol}//${u.hostname}:9432`;
		}
		return `${u.protocol}//${u.host}`;
	}
	return 'http://localhost:9432';
}

export async function apiFetch(path: string, options: RequestInit = {}): Promise<Response> {
	const apiBase = getApiBase();
	const url = path.startsWith('http') ? path : `${apiBase}${path.startsWith('/') ? '' : '/'}${path}`;
	
	const headers = new Headers(options.headers || {});
	if (authState.token) {
		headers.set('Authorization', `Bearer ${authState.token}`);
	}
	
	const res = await fetch(url, {
		...options,
		headers
	});
	
	if (res.status === 401) {
		authState.logout();
	}
	
	return res;
}
