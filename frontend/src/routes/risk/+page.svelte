<script lang="ts">
	import { onMount, onDestroy } from 'svelte';
	import { apiFetch } from '$lib/api';

	type ContractSummary = {
		id: string;
		filename: string;
		status: string;
		overall_risk?: string | null;
		created_at: string;
	};

	let contracts: ContractSummary[] = $state([]);
	let pollInterval: any;
	let apiBase = $state('http://localhost:9432');

	async function fetchContracts() {
		try {
			const res = await apiFetch('/api/v1/contracts');
			if (!res.ok) return;
			const json = await res.json();
			contracts = json.contracts || [];
		} catch (err) {
			console.error('Failed to fetch contracts:', err);
		}
	}

	function timeAgo(dateString: string) {
		const now = new Date();
		const date = new Date(dateString);
		const seconds = Math.floor((now.getTime() - date.getTime()) / 1000);
		if (seconds < 60) return 'Just now';
		const minutes = Math.floor(seconds / 60);
		if (minutes < 60) return `${minutes}m ago`;
		const hours = Math.floor(minutes / 60);
		if (hours < 24) return `${hours}h ago`;
		const days = Math.floor(hours / 24);
		return `${days}d ago`;
	}

	let risky: ContractSummary[] = $derived(
		contracts.filter(
			(c) => c.status === 'COMPLETED' && (c.overall_risk === 'HIGH' || c.overall_risk === 'CRITICAL')
		)
	);

	onMount(() => {
		const u = new URL(window.location.href);
		apiBase = `${u.protocol}//${u.hostname}:9432`;
		fetchContracts();
		pollInterval = setInterval(fetchContracts, 3000);
	});

	onDestroy(() => {
		if (pollInterval) clearInterval(pollInterval);
	});
</script>

<header class="page-header">
	<div class="page-header-inner">
		<div class="breadcrumbs">
			<span class="crumb">ContractsPulse</span>
			<span class="separator">/</span>
			<span class="crumb active">Risk Inbox</span>
		</div>
		<div class="header-content flex-between">
			<h1>Risk Inbox</h1>
		</div>
	</div>
</header>

<div class="page-content">
	<div class="data-table panel">
		<div class="table-header">
			<div class="col col-name">Document</div>
			<div class="col col-risk">Risk Score</div>
			<div class="col col-date">Uploaded</div>
		</div>

		{#if risky.length === 0}
			<div class="table-row empty-row">
				No high-risk contracts yet.
			</div>
		{/if}

		{#each risky as contract}
			{@const r = (contract.overall_risk || 'HIGH').toLowerCase()}
			<div class="table-row">
				<div class="col col-name">{contract.filename}</div>
				<div class="col col-risk">
					<span class="risk-indicator risk-{r}"></span>
					<span class="risk-label">{r}</span>
				</div>
				<div class="col col-date text-tertiary">{timeAgo(contract.created_at)}</div>
			</div>
		{/each}
	</div>
</div>
