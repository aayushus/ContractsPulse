import type { PageLoad } from './$types';
import { apiFetch } from '$lib/api';

export const ssr = false;

export const load: PageLoad = async () => {
	const res = await apiFetch('/api/v1/vendors');
	const data = await res.json().catch(() => ({}));
	return { vendors: data.vendors || [] };
};

