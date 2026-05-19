<script lang="ts">
	import { onMount, onDestroy } from 'svelte';
	import { apiFetch } from '$lib/api';

	let contracts: any[] = $state([]);
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
			<span class="crumb active">All Contracts</span>
		</div>
		<div class="header-content flex-between">
			<h1>All Contracts</h1>
		</div>
	</div>
</header>

<div class="page-content">
	<div class="data-table panel">
		<div class="table-header">
			<div class="col col-name">Document</div>
			<div class="col col-status">Status</div>
			<div class="col col-risk">Risk Score</div>
			<div class="col col-date">Uploaded</div>
		</div>

		{#if contracts.length === 0}
			<div class="table-row empty-row">
				No contracts analyzed yet.
			</div>
		{/if}

		{#each contracts as contract}
			<div class="table-row">
				<div class="col col-name">{contract.filename}</div>
				<div class="col col-status">
					{#if contract.status === 'COMPLETED'}
						<span class="badge badge-success">Completed</span>
					{:else if contract.status === 'FAILED'}
						<span class="badge badge-danger">Failed</span>
					{:else}
						<span class="badge badge-warning">Processing</span>
					{/if}
				</div>
				<div class="col col-risk">
					{#if contract.status === 'COMPLETED' && contract.overall_risk}
						<span class="risk-indicator risk-{contract.overall_risk.toLowerCase()}"></span>
						<span class="risk-label">{contract.overall_risk.toLowerCase()}</span>
					{:else}
						<span class="text-tertiary">--</span>
					{/if}
				</div>
				<div class="col col-date text-tertiary">{timeAgo(contract.created_at)}</div>
			</div>
		{/each}
	</div>
</div>
