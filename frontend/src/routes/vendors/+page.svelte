<script lang="ts">
	import { goto } from '$app/navigation';
	let { data } = $props();
	const initialVendors = (data && (data as any).vendors) ? (data as any).vendors : [];

	type VendorContract = {
		id: string;
		filename: string;
		status: string;
		overall_risk: string | null;
		contract_type: string | null;
		expiry_date: string | null;
		created_at: string;
	};

	type VendorGroup = {
		name: string;
		contracts: VendorContract[];
		worst_risk: string;
		total_critical: number;
		total_high: number;
	};

	let vendors = $state<VendorGroup[]>(initialVendors || []);
	let expanded = $state<Record<string, boolean>>({});
	let isLoading = $state(false);

	function formatDocumentName(filename: string) {
		if (!filename) return '';
		let clean = filename.replace(/\.[a-zA-Z0-9]+$/, '');
		clean = clean.replace(/[_-]/g, ' ');
		return clean.replace(/\b\w/g, (c) => c.toUpperCase());
	}

</script>

<svelte:head>
	<title>Vendors — ContractsPulse</title>
</svelte:head>

<header class="page-header">
	<div class="page-header-inner">
		<div class="breadcrumbs">
			<span class="crumb">ContractsPulse</span>
			<span class="separator">›</span>
			<span class="crumb active">Vendors</span>
		</div>
		<div class="header-content">
			<div class="header-title-row">
				<span class="header-icon">
					<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M3 7l9-4 9 4-9 4-9-4z"/><path d="M3 17l9 4 9-4"/><path d="M3 12l9 4 9-4"/></svg>
				</span>
				<h1>Vendor Directory</h1>
			</div>
			<p class="text-tertiary">Group contracts by counterparty and prioritize review by risk exposure.</p>
		</div>
	</div>
</header>

<div class="page-content">
	{#if isLoading}
		<div class="loading-state">
			<span class="spinner spinner-lg"></span>
			<p class="text-tertiary">Loading vendors…</p>
		</div>
	{:else if vendors.length === 0}
		<div class="empty-state panel">
			<h3>No vendors yet</h3>
			<p class="text-tertiary">Upload and analyze contracts in the Repository to populate this directory.</p>
			<button class="btn btn-primary" onclick={() => goto('/contracts')}>Go to Contract Repository</button>
		</div>
	{:else}
		<div class="vendors-grid">
			{#each vendors as v (v.name)}
				<div class="vendor-card panel">
					<button class="vendor-head" onclick={() => (expanded[v.name] = !expanded[v.name])}>
						<div class="vendor-title">
							<div class="vendor-name">{v.name}</div>
							<div class="vendor-sub text-tertiary">{v.contracts.length} contracts</div>
						</div>
						<div class="vendor-badges">
							<span class="badge badge-{v.worst_risk === 'CRITICAL' || v.worst_risk === 'HIGH' ? 'danger' : v.worst_risk === 'MEDIUM' ? 'warning' : 'success'}">
								{v.worst_risk}
							</span>
							<svg class="chev" class:open={expanded[v.name]} width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="6 9 12 15 18 9"/></svg>
						</div>
					</button>

					{#if expanded[v.name]}
						<div class="vendor-contracts">
							{#each v.contracts as c (c.id)}
								<button class="vendor-contract" onclick={() => goto(`/contracts/${c.id}`)}>
									<div class="vc-left">
										<div class="vc-name">{formatDocumentName(c.filename)}</div>
										<div class="vc-meta text-tertiary">{c.contract_type || 'Contract'} · {c.status}</div>
									</div>
									{#if c.overall_risk}
										<span class="badge badge-{c.overall_risk === 'CRITICAL' || c.overall_risk === 'HIGH' ? 'danger' : c.overall_risk === 'MEDIUM' ? 'warning' : 'success'}">{c.overall_risk}</span>
									{:else}
										<span class="badge badge-secondary">--</span>
									{/if}
								</button>
							{/each}
						</div>
					{/if}
				</div>
			{/each}
		</div>
	{/if}
</div>

<style>
	.vendors-grid {
		display: grid;
		grid-template-columns: repeat(auto-fit, minmax(340px, 1fr));
		gap: 12px;
	}
	.vendor-card {
		padding: 0;
		overflow: hidden;
	}
	.vendor-head {
		width: 100%;
		display: flex;
		justify-content: space-between;
		align-items: center;
		padding: 14px 14px;
		background: transparent;
		border: none;
		color: inherit;
		cursor: pointer;
	}
	.vendor-name {
		font-weight: 650;
	}
	.vendor-sub {
		font-size: 12px;
		margin-top: 2px;
	}
	.vendor-badges {
		display: flex;
		align-items: center;
		gap: 10px;
	}
	.chev {
		transition: transform 150ms ease;
	}
	.chev.open {
		transform: rotate(180deg);
	}
	.vendor-contracts {
		border-top: 1px solid var(--border-subtle);
		padding: 10px;
		display: flex;
		flex-direction: column;
		gap: 8px;
	}
	.vendor-contract {
		width: 100%;
		display: flex;
		align-items: center;
		justify-content: space-between;
		gap: 10px;
		padding: 10px 10px;
		border-radius: 10px;
		border: 1px solid var(--border-subtle);
		background: var(--bg-panel);
		color: inherit;
		text-align: left;
		cursor: pointer;
		transition: background 150ms ease, border-color 150ms ease;
	}
	.vendor-contract:hover {
		background: var(--bg-active);
		border-color: var(--border-strong);
	}
	.vc-left {
		min-width: 0;
	}
	.vc-name {
		font-weight: 550;
		color: var(--text-primary);
		white-space: nowrap;
		overflow: hidden;
		text-overflow: ellipsis;
	}
	.vc-meta {
		font-size: 12px;
		margin-top: 2px;
	}
</style>
