import { apiFetch } from '$lib/api';

export const ssr = false;

export const load = async () => {
	const res = await apiFetch('/api/v1/contracts');
	const data = await res.json().catch(() => ({}));
	return { contracts: data.contracts || [] };
};

