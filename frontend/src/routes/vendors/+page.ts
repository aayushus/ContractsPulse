import { apiFetch } from '$lib/api';

export const ssr = false;

export const load: import('./$types').PageLoad = async () => {
	const res = await apiFetch('/api/v1/vendors');
	const data = await res.json().catch(() => ({}));
	return { vendors: data.vendors || [] };
};
