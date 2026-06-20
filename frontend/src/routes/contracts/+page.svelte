<script lang="ts">
	import { onMount, onDestroy } from 'svelte';
	import { goto } from '$app/navigation';
	import { apiFetch } from '$lib/api';
	import { toast } from '$lib/toastStore';
	let { data } = $props();
	// In dev hydration / fast refresh, `data` can briefly be undefined.
	const initialContracts = (data && (data as any).contracts) ? (data as any).contracts : [];

	type ContractSummary = {
		id: string;
		filename: string;
		status: string;
		metadata_json?: any;
		overall_risk?: string | null;
		created_at: string;
	};

	let contracts: ContractSummary[] = $state(initialContracts || []);
	let isLoading = $state(false);
	let isUploading = $state(false);
	let fileInput: HTMLInputElement;
	let pollInterval: any;
	let apiBase = $state('http://localhost:9432');

	// Filtering states
	let searchQuery = $state('');
	let statusFilter = $state('ALL'); // 'ALL' | 'COMPLETED' | 'PROCESSING' | 'FAILED'
	let riskFilter = $state('ALL'); // 'ALL' | 'CRITICAL' | 'HIGH' | 'MEDIUM' | 'LOW'

	// Modals
	let deleteModalOpen = $state(false);
	let contractToDelete = $state<string | null>(null);
	let pasteModalOpen = $state(false);
	let pastedText = $state('');

	function groupLatestContracts(all: ContractSummary[]): ContractSummary[] {
		if (!all || all.length === 0) return [];
		const byId = new Map<string, ContractSummary>();
		for (const c of all) byId.set(c.id, c);

		function rootIdOf(c: ContractSummary): string {
			let cur: ContractSummary | undefined = c;
			let guard = 0;
			while (cur?.metadata_json?.parent_contract_id && guard < 20) {
				const parent = byId.get(cur.metadata_json.parent_contract_id);
				if (!parent) break;
				cur = parent;
				guard += 1;
			}
			return cur?.id || c.id;
		}

		const groups = new Map<string, ContractSummary[]>();
		for (const c of all) {
			const rootId = rootIdOf(c);
			const arr = groups.get(rootId) || [];
			arr.push(c);
			groups.set(rootId, arr);
		}

		const latest: ContractSummary[] = [];
		for (const [rootId, arr] of groups.entries()) {
			const sorted = [...arr].sort((a, b) => {
				const av = Number(a.metadata_json?.version_number || 1);
				const bv = Number(b.metadata_json?.version_number || 1);
				if (bv !== av) return bv - av;
				return new Date(b.created_at).getTime() - new Date(a.created_at).getTime();
			});
			const head = sorted[0];
			// Attach version metadata for display (do not mutate reactive objects)
			const enriched = {
				...head,
				__version_count: sorted.length,
				__latest_version: Number(head.metadata_json?.version_number || sorted.length || 1),
				__root_contract_id: rootId
			} as any;
			latest.push(enriched);
		}

		// Preserve newest-first ordering at the portfolio level
		latest.sort((a, b) => new Date(b.created_at).getTime() - new Date(a.created_at).getTime());
		return latest;
	}

	let latestContracts = $derived(groupLatestContracts(contracts));

	// Stats (use latest only, so revisions don't double-count)
	let totalCount = $derived(latestContracts.length);
	let queueCount = $derived(latestContracts.filter(c => c.status === 'PROCESSING').length);
	let completedCount = $derived(latestContracts.filter(c => c.status === 'COMPLETED').length);
	
	let riskyCount = $derived(
		latestContracts.filter(c => c.status === 'COMPLETED' && (c.overall_risk === 'CRITICAL' || c.overall_risk === 'HIGH')).length
	);
	let riskyRate = $derived(completedCount > 0 ? ((riskyCount / completedCount) * 100).toFixed(0) + '%' : '0%');
	
	let totalObligationsCount = $derived(
		(latestContracts as any[]).reduce((sum, c: any) => {
			const counts = c.metadata_json?.risk_counts || {};
			return sum + Object.values(counts).reduce((a: any, b: any) => a + Number(b), 0);
		}, 0)
	);

	// Derived filtered contracts
	let filteredContracts = $derived(
		latestContracts.filter(c => {
			const matchesSearch = c.filename.toLowerCase().includes(searchQuery.toLowerCase());
			const matchesStatus = statusFilter === 'ALL' || c.status === statusFilter;
			
			let matchesRisk = true;
			if (riskFilter !== 'ALL') {
				matchesRisk = c.status === 'COMPLETED' && c.overall_risk === riskFilter;
			}
			
			return matchesSearch && matchesStatus && matchesRisk;
		})
	);

	async function fetchContracts(silent = false) {
		if (!silent) isLoading = true;
		try {
			const res = await apiFetch('/api/v1/contracts');
			if (!res.ok) return;
			const json = await res.json();
			contracts = json.contracts || [];
		} catch (err) {
			console.error('Failed to fetch contracts:', err);
		} finally {
			if (!silent) isLoading = false;
		}
	}

	function triggerUpload() {
		if (fileInput) fileInput.click();
	}

	async function handleFileChange(event: Event) {
		const target = event.target as HTMLInputElement;
		if (!target.files || target.files.length === 0) return;
		
		const file = target.files[0];
		isUploading = true;
		const formData = new FormData();
		formData.append('file', file);
		
		let loadingToastId = toast.loading(`Uploading ${file.name}...`);
		try {
			const response = await apiFetch('/api/v1/contracts/upload', {
				method: 'POST',
				body: formData
			});
			
			if (response.ok) {
				toast.dismiss(loadingToastId);
				toast.success('Document uploaded. AI processing started.');
				fetchContracts(true);
			} else {
				throw new Error('Upload failed');
			}
		} catch (error) {
			console.error("Upload error:", error);
			toast.dismiss(loadingToastId);
			toast.error('Failed to upload document.');
		} finally {
			isUploading = false;
		}
	}

	async function handlePasteAnalyze() {
		const text = (pastedText || '').trim();
		if (!text) {
			toast.error('Paste contract text first.');
			return;
		}

		isUploading = true;
		const loadingToastId = toast.loading('Submitting text for analysis...');
		try {
			const response = await apiFetch('/api/v1/contracts/text', {
				method: 'POST',
				headers: { 'Content-Type': 'application/json' },
				body: JSON.stringify({ text })
			});

			if (response.ok) {
				toast.dismiss(loadingToastId);
				toast.success('Text submitted. AI processing started.');
				pasteModalOpen = false;
				pastedText = '';
				fetchContracts(true);
			} else {
				const err = await response.json().catch(() => ({}));
				throw new Error(err?.detail || 'Submit failed');
			}
		} catch (error) {
			console.error('Paste analyze error:', error);
			toast.dismiss(loadingToastId);
			toast.error('Failed to submit text for analysis.');
		} finally {
			isUploading = false;
		}
	}

	async function handleReprocess(id: string) {
		const loadingToastId = toast.loading('Restarting AI pipeline...');
		try {
			const response = await apiFetch(`/api/v1/contracts/${id}/reprocess`, {
				method: 'POST'
			});
			if (response.ok) {
				toast.dismiss(loadingToastId);
				toast.success('Reprocessing started.');
				fetchContracts(true);
			} else {
				throw new Error('Reprocess failed');
			}
		} catch (error) {
			toast.dismiss(loadingToastId);
			toast.error('Failed to reprocess contract.');
		}
	}

	function promptDelete(id: string) {
		contractToDelete = id;
		deleteModalOpen = true;
	}

	async function handleDelete() {
		if (!contractToDelete) return;
		const contractId = contractToDelete;
		deleteModalOpen = false;
		contractToDelete = null;
		
		const loadingToastId = toast.loading('Deleting contract...');
		try {
			const response = await apiFetch(`/api/v1/contracts/${contractId}`, {
				method: 'DELETE'
			});
			if (response.ok) {
				toast.dismiss(loadingToastId);
				toast.success('Contract deleted.');
				fetchContracts(true);
			} else {
				throw new Error('Delete failed');
			}
		} catch (error) {
			toast.dismiss(loadingToastId);
			toast.error('Failed to delete contract.');
		}
	}

	function getProcessingPhase(step: string | undefined | null) {
		if (!step) return "Initializing";
		const s = step.toLowerCase();
		if (s.includes('segment')) return "Planning";
		if (s.includes('analyz')) return "Thinking";
		if (s.includes('sav')) return "Executing";
		return "Processing";
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
		// Load already populated via `+page.ts`, but keep a fast refresh + polling.
		fetchContracts(true);
		pollInterval = setInterval(() => fetchContracts(true), 3000);
	});

	onDestroy(() => {
		if (pollInterval) clearInterval(pollInterval);
	});
</script>

<header class="page-header">
	<div class="page-header-inner flex-between">
		<div>
			<div class="breadcrumbs">
				<span class="crumb">ContractsPulse</span>
				<span class="separator">›</span>
				<span class="crumb active">Contract Repository</span>
			</div>
			<div class="header-content">
				<h1>Contracts Portfolio</h1>
				<p class="subtitle text-secondary">Manage, search, and analyze your legal repository and obligations density.</p>
			</div>
		</div>
		
		<div class="header-actions">
			<input 
				type="file" 
				accept="application/pdf" 
				bind:this={fileInput} 
				onchange={handleFileChange} 
				style="display: none;" 
			/>
			<button class="btn btn-primary" onclick={triggerUpload} disabled={isUploading}>
				{#if isUploading}
					<span class="spinner spinner-sm"></span> Uploading...
				{:else}
					<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="17 8 12 3 7 8"/><line x1="12" y1="3" x2="12" y2="15"/></svg>
					Upload Contract
				{/if}
			</button>
			<button class="btn btn-secondary" onclick={() => pasteModalOpen = true} disabled={isUploading}>
				<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/><line x1="16" y1="13" x2="8" y2="13"/><line x1="16" y1="17" x2="8" y2="17"/><polyline points="10 9 9 9 8 9"/></svg>
				Paste contract text
			</button>
		</div>
	</div>
</header>

<div class="page-content">
	<!-- Glassmorphic Portfolio Metrics Grid -->
	<div class="metric-row">
		<div class="metric-card panel bg-glass-card">
			<div class="metric-label">Total Documents</div>
			<div class="metric-value text-primary">{totalCount}</div>
		</div>
		<div class="metric-card panel bg-glass-card">
			<div class="metric-label">Processing Queue</div>
			<div class="metric-value" class:text-warning={queueCount > 0} class:text-tertiary={queueCount === 0}>{queueCount}</div>
		</div>
		<div class="metric-card panel bg-glass-card">
			<div class="metric-label">Vulnerability Rate</div>
			<div class="metric-value" class:text-danger={riskyCount > 0} class:text-primary={riskyCount === 0}>{riskyRate}</div>
		</div>
		<div class="metric-card panel bg-glass-card">
			<div class="metric-label">Obligations Analyzed</div>
			<div class="metric-value text-secondary">{totalObligationsCount}</div>
		</div>
	</div>

	<!-- Dashboard Advanced Filters -->
	<div class="filters-panel panel bg-panel-glow">
		<div class="filters-layout">
			<!-- Realtime Search -->
			<div class="search-input-wrapper">
				<svg class="search-icon" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/></svg>
				<input 
					type="text" 
					placeholder="Search files by name..." 
					bind:value={searchQuery}
					class="contract-search-bar"
				/>
			</div>

			<!-- Status Filter Pills -->
			<div class="filter-group flex-row gap-8">
				<span class="filter-group-label">Status:</span>
				<div class="filter-pills flex-row gap-4">
					<button class="filter-pill" class:active={statusFilter === 'ALL'} onclick={() => statusFilter = 'ALL'}>All</button>
					<button class="filter-pill" class:active={statusFilter === 'COMPLETED'} onclick={() => statusFilter = 'COMPLETED'}>Completed</button>
					<button class="filter-pill" class:active={statusFilter === 'PROCESSING'} onclick={() => statusFilter = 'PROCESSING'}>Queue</button>
					<button class="filter-pill" class:active={statusFilter === 'FAILED'} onclick={() => statusFilter = 'FAILED'}>Failed</button>
				</div>
			</div>

			<!-- Risk Filter Pills -->
			<div class="filter-group flex-row gap-8">
				<span class="filter-group-label">Severity:</span>
				<div class="filter-pills flex-row gap-4">
					<button class="filter-pill" class:active={riskFilter === 'ALL'} onclick={() => riskFilter = 'ALL'}>All</button>
					<button class="filter-pill filter-pill-critical" class:active={riskFilter === 'CRITICAL'} onclick={() => riskFilter = 'CRITICAL'}>Critical</button>
					<button class="filter-pill filter-pill-high" class:active={riskFilter === 'HIGH'} onclick={() => riskFilter = 'HIGH'}>High</button>
					<button class="filter-pill filter-pill-medium" class:active={riskFilter === 'MEDIUM'} onclick={() => riskFilter = 'MEDIUM'}>Med</button>
					<button class="filter-pill filter-pill-low" class:active={riskFilter === 'LOW'} onclick={() => riskFilter = 'LOW'}>Low</button>
				</div>
			</div>
		</div>
	</div>

	<!-- Portfolio Table Panel -->
	<div class="data-table panel">
		<div class="table-header">
			<div class="col col-name">Document</div>
			<div class="col col-vendor">Vendor</div>
			<div class="col col-status">Status</div>
			<div class="col col-risk">Severity Bar</div>
			<div class="col col-date">Uploaded</div>
			<div class="col col-actions"></div>
		</div>

		{#if isLoading}
			{#each Array(6) as _, i (i)}
				<div class="table-row">
					<div class="col col-name"><div class="skeleton" style="height: 14px; width: 70%;"></div></div>
					<div class="col col-vendor"><div class="skeleton" style="height: 14px; width: 60%;"></div></div>
					<div class="col col-status"><div class="skeleton" style="height: 14px; width: 50%;"></div></div>
					<div class="col col-risk"><div class="skeleton" style="height: 10px; width: 120px;"></div></div>
					<div class="col col-date"><div class="skeleton" style="height: 14px; width: 70px; margin-left: auto;"></div></div>
					<div class="col col-actions"><div class="skeleton" style="height: 14px; width: 22px; margin-left: auto;"></div></div>
				</div>
			{/each}
		{:else if filteredContracts.length === 0}
			<div class="table-row empty-row">
				No contracts found matching filter criteria.
			</div>
		{/if}

		{#each filteredContracts as contract, i}
			<div
				class="table-row clickable-row stagger-entry"
				style="--index: {i}"
				role="button"
				tabindex="0"
				onclick={(e: MouseEvent) => {
					const target = e.target as HTMLElement | null;
					if (!target || !target.closest('.btn-icon') && !target.closest('.btn-inline')) {
						goto(`/contracts/${contract.id}`);
					}
				}}
				onkeydown={(e: KeyboardEvent) => {
					if (e.key === 'Enter' || e.key === ' ') {
						const target = e.target as HTMLElement | null;
						if (!target || !target.closest('.btn-icon') && !target.closest('.btn-inline')) {
							e.preventDefault();
							goto(`/contracts/${contract.id}`);
						}
					}
				}}
			>
				<!-- Name column -->
				<div class="col col-name" style="min-width: 0;">
					<svg class="file-icon" style="flex-shrink: 0;" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/></svg>
					<span class="filename-text font-semibold" title={contract.filename}>{contract.filename}</span>
					{#if (contract as any).__version_count && (contract as any).__version_count > 1}
						<span class="version-pill" title="This contract has {(contract as any).__version_count} versions">v{(contract as any).__latest_version}</span>
					{/if}
				</div>

				<!-- Vendor -->
				<div class="col col-vendor" title={contract.metadata_json?.company || ''}>
					<span class="vendor-text">{contract.metadata_json?.company || '—'}</span>
				</div>

				<!-- Status Badge -->
				<div class="col col-status">
					{#if contract.status === 'COMPLETED'}
						<span class="badge badge-success">Completed</span>
					{:else if contract.status === 'FAILED'}
						<span class="badge badge-danger">Failed</span>
					{:else}
						{@const phase = getProcessingPhase(contract.metadata_json?.processing_step)}
						<div class="processing-pulse" title={contract.metadata_json?.processing_step || "Processing"}>
							<span class="spinner spinner-sm"></span>
							<span class="pulse-label font-medium">{phase}</span>
						</div>
					{/if}
				</div>

				<!-- Miniature Risk Severity Stacked Density Bar -->
				<div class="col col-risk">
					{#if contract.status === 'COMPLETED' && contract.metadata_json?.risk_counts}
						{@const counts = contract.metadata_json.risk_counts}
						{@const crit = Number(counts.CRITICAL || 0)}
						{@const high = Number(counts.HIGH || 0)}
						{@const med = Number(counts.MEDIUM || 0)}
						{@const low = Number(counts.LOW || 0)}
						{@const total = crit + high + med + low}
						
						{#if total > 0}
							<div class="risk-density-bar-container" title="Critical: {crit}, High: {high}, Medium: {med}, Low: {low}">
								<div class="risk-density-bar">
									{#if crit > 0}<div class="r-seg r-seg-critical" style="flex: {crit}"></div>{/if}
									{#if high > 0}<div class="r-seg r-seg-high" style="flex: {high}"></div>{/if}
									{#if med > 0}<div class="r-seg r-seg-medium" style="flex: {med}"></div>{/if}
									{#if low > 0}<div class="r-seg r-seg-low" style="flex: {low}"></div>{/if}
								</div>
								<div class="risk-density-counts text-tertiary">
									{#if crit > 0}
										<span class="severity-chip text-critical" title="Critical clauses: {crit}">
											<span class="sev-dot sev-critical"></span>
											{crit}
										</span>
									{/if}
									{#if high > 0}
										<span class="severity-chip text-high" title="High clauses: {high}">
											<span class="sev-dot sev-high"></span>
											{high}
										</span>
									{/if}
									{#if med > 0}
										<span class="severity-chip text-medium" title="Medium clauses: {med}">
											<span class="sev-dot sev-medium"></span>
											{med}
										</span>
									{/if}
								</div>
							</div>
						{:else}
							<span class="text-tertiary font-mono">No risks</span>
						{/if}
					{:else if contract.status === 'PROCESSING'}
						<span class="text-tertiary font-mono italic">Calculating...</span>
					{:else}
						<span class="text-tertiary font-mono">--</span>
					{/if}
				</div>

				<!-- Uploaded Time -->
				<div class="col col-date text-tertiary">{timeAgo(contract.created_at)}</div>

				<!-- Row Actions -->
				<div class="col col-actions" style="display: flex; gap: 8px; justify-content: flex-end;">
					{#if contract.status === 'FAILED' || contract.status === 'COMPLETED'}
						<button class="btn-icon" onclick={(e) => { e.stopPropagation(); handleReprocess(contract.id); }} aria-label="Reprocess" title="Reprocess Contract">
							<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M3 12a9 9 0 1 0 9-9 9.75 9.75 0 0 0-6.74 2.74L3 8"/><path d="M3 3v5h5"/></svg>
						</button>
					{/if}
					<button class="btn-icon btn-danger-action" onclick={(e) => { e.stopPropagation(); promptDelete(contract.id); }} aria-label="Delete" title="Delete Contract">
						<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M3 6h18"></path><path d="M19 6v14c0 1-1 2-2 2H7c-1 0-2-1-2-2V6"></path><path d="M8 6V4c0-1 1-2 2-2h4c1 0 2 1 2 2v2"></path></svg>
					</button>
				</div>
			</div>
		{/each}
	</div>
</div>

<!-- Modals Parity -->
{#if deleteModalOpen}
	<div class="modal-root">
		<button type="button" class="modal-backdrop" aria-label="Close" onclick={() => deleteModalOpen = false}></button>
		<div class="modal-content" role="dialog" aria-modal="true">
			<div class="modal-header">
				<div class="modal-icon warning">
					<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"></path><line x1="12" y1="9" x2="12" y2="13"></line><line x1="12" y1="17" x2="12.01" y2="17"></line></svg>
				</div>
				<h3>Delete Contract</h3>
			</div>
			<div class="modal-body">
				<p>Are you sure you want to completely remove this contract? This will delete all extracted clauses, AI reasoning, and traces. This action cannot be undone.</p>
			</div>
			<div class="modal-footer flex-end gap-12">
				<button class="btn btn-secondary" onclick={() => deleteModalOpen = false}>Cancel</button>
				<button class="btn btn-danger" onclick={handleDelete}>Delete Permanently</button>
			</div>
		</div>
	</div>
{/if}

{#if pasteModalOpen}
	<div class="modal-root">
		<button type="button" class="modal-backdrop" aria-label="Close" onclick={() => pasteModalOpen = false}></button>
		<div class="modal-content modal-content-wide" role="dialog" aria-modal="true">
			<div class="modal-header">
				<div class="modal-icon info">
					<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/></svg>
				</div>
				<h3>Analyze Pasted Contract Text</h3>
			</div>
			<div class="modal-body">
				<p class="text-tertiary modal-help">
					Paste the contract text below (Google Docs, plaintext). We will analyze it like a PDF.
				</p>
				<textarea
					bind:value={pastedText}
					class="input-field mono-textarea"
					rows="14"
					placeholder="Paste contract text here..."
				></textarea>
			</div>
			<div class="modal-footer flex-end gap-12">
				<button class="btn btn-secondary" onclick={() => pasteModalOpen = false}>Cancel</button>
				<button class="btn btn-primary" onclick={handlePasteAnalyze} disabled={isUploading}>Analyze</button>
			</div>
		</div>
	</div>
{/if}

<style>
	.page-header {
		padding: 32px 40px 24px;
		border-bottom: 1px solid var(--border-subtle);
		background: var(--bg-sidebar);
	}

	.breadcrumbs {
		display: flex;
		align-items: center;
		gap: 8px;
		font-size: 13px;
		margin-bottom: 12px;
	}

	.crumb {
		color: var(--text-tertiary);
	}

	.crumb.active {
		color: var(--text-primary);
		font-weight: 500;
	}

	.separator {
		color: var(--border-strong);
	}

	.header-content h1 {
		font-size: 20px;
		font-weight: 600;
		margin: 0;
	}

	.subtitle {
		font-size: 13px;
		margin-top: 4px;
	}

	.header-actions {
		display: flex;
		gap: 8px;
	}

	.version-pill {
		display: inline-flex;
		align-items: center;
		height: 20px;
		padding: 0 8px;
		border-radius: 999px;
		border: 1px solid var(--border-subtle);
		background: var(--bg-panel);
		color: var(--text-secondary);
		font-size: 11px;
		font-weight: 650;
		white-space: nowrap;
	}

	.page-content {
		padding: 32px 40px;
		max-width: 1200px;
		margin: 0 auto;
		width: 100%;
	}

	/* Portfolio Stats Grid */
	.metric-row {
		display: grid;
		grid-template-columns: repeat(4, 1fr);
		gap: 16px;
		margin-bottom: 32px;
	}

	.metric-card {
		padding: 20px;
		background: var(--bg-glass-card);
		border: 1px solid var(--border-glass);
		border-radius: 8px;
		transition: border-color 220ms var(--ease-spring-gentle), 
		            transform 200ms var(--ease-spring-gentle), 
		            box-shadow 220ms var(--ease-spring-gentle);
	}

	.metric-card:hover {
		border-color: var(--border-glass-hover);
		box-shadow: var(--shadow-premium);
	}



	.metric-label {
		font-size: 11px;
		font-weight: 600;
		color: var(--text-secondary);
		text-transform: uppercase;
		letter-spacing: 0.5px;
	}

	.metric-value {
		font-size: 24px;
		font-weight: 600;
		margin-top: 8px;
		line-height: 1;
	}

	/* Filter panel */
	.filters-panel {
		padding: 16px 20px;
		background: var(--bg-panel);
		border: 1px solid var(--border-subtle);
		margin-bottom: 24px;
	}

	.filters-layout {
		display: grid;
		grid-template-columns: 1fr auto auto;
		gap: 20px;
		align-items: center;
	}

	.search-input-wrapper {
		position: relative;
		display: flex;
		align-items: center;
	}

	.search-icon {
		position: absolute;
		left: 12px;
		color: var(--text-tertiary);
		pointer-events: none;
	}

	.contract-search-bar {
		width: 100%;
		padding: 8px 12px 8px 36px;
		background: var(--bg-app);
		border: 1px solid var(--border-subtle);
		border-radius: 6px;
		color: var(--text-primary);
		font-size: 13px;
		outline: none;
		transition: border-color 150ms var(--ease-out);
	}

	.contract-search-bar:focus {
		border-color: var(--text-secondary);
	}

	.filter-group {
		font-size: 12px;
	}

	.filter-group-label {
		color: var(--text-secondary);
		font-weight: 500;
	}

	.filter-pill {
		background: transparent;
		border: 1px solid var(--border-subtle);
		color: var(--text-secondary);
		font-size: 11px;
		font-weight: 500;
		padding: 4px 10px;
		border-radius: 6px;
		cursor: pointer;
		transition: color 150ms var(--ease-out), background-color 150ms var(--ease-out), border-color 150ms var(--ease-out);
	}

	.filter-pill:hover {
		color: var(--text-primary);
		border-color: var(--border-strong);
	}

	.filter-pill.active {
		background: var(--bg-hover);
		color: var(--text-primary);
		border-color: var(--text-secondary);
	}

	.filter-pill-critical.active {
		border-color: rgba(var(--color-critical-rgb), 0.4);
		background: rgba(var(--color-critical-rgb), 0.08);
		color: var(--color-critical);
	}

	.filter-pill-high.active {
		border-color: rgba(var(--color-high-rgb), 0.4);
		background: rgba(var(--color-high-rgb), 0.08);
		color: var(--color-high);
	}

	.filter-pill-medium.active {
		border-color: rgba(var(--color-medium-rgb), 0.4);
		background: rgba(var(--color-medium-rgb), 0.08);
		color: var(--color-medium);
	}

	.filter-pill-low.active {
		border-color: rgba(var(--color-low-rgb), 0.4);
		background: rgba(var(--color-low-rgb), 0.08);
		color: var(--color-low);
	}

	/* Processing status line */
	.processing-pulse {
		display: inline-flex;
		align-items: center;
		gap: 8px;
		color: var(--text-secondary);
	}

	/* Miniature Severity Stacked Density Bar */
	.risk-density-bar-container {
		display: flex;
		flex-direction: column;
		gap: 6px;
		width: 100%;
		max-width: 180px;
	}

	.risk-density-bar {
		display: flex;
		height: 6px;
		background: var(--bg-hover);
		border-radius: 4px;
		overflow: hidden;
		border: 1px solid var(--border-subtle);
	}

	.r-seg {
		height: 100%;
	}
	.r-seg-critical { background: var(--color-critical); }
	.r-seg-high { background: var(--color-high); }
	.r-seg-medium { background: var(--color-medium); }
	.r-seg-low { background: var(--color-low); }

	.risk-density-counts {
		display: flex;
		align-items: center;
		gap: 6px;
		font-size: 10px;
	}

	.severity-chip {
		display: inline-flex;
		align-items: center;
		gap: 6px;
		padding: 2px 7px;
		border-radius: 999px;
		border: 1px solid var(--border-subtle);
		background: var(--bg-panel);
		font-size: 11px;
		font-weight: 650;
		color: var(--text-secondary);
	}
	.sev-dot {
		width: 6px;
		height: 6px;
		border-radius: 999px;
		display: inline-block;
	}
	.sev-critical { background: var(--color-critical); }
	.sev-high { background: var(--color-high); }
	.sev-medium { background: var(--color-medium); }

	.btn-danger-action {
		color: var(--text-tertiary);
		transition: color 150ms ease;
	}

	.btn-danger-action:hover {
		color: var(--color-high) !important;
	}

	.empty-row {
		display: flex;
		align-items: center;
		justify-content: center;
		padding: 48px 0 !important;
		color: var(--text-tertiary);
	}

	@media (max-width: 900px) {
		.metric-row {
			grid-template-columns: 1fr 1fr;
		}

		.filters-layout {
			grid-template-columns: 1fr;
			gap: 16px;
		}
	}

	/* Modal styles */
	.modal-root {
		position: fixed;
		top: 0;
		left: 0;
		width: 100vw;
		height: 100vh;
		z-index: 1000;
		display: flex;
		align-items: center;
		justify-content: center;
		animation: fadeIn 200ms ease-out forwards;
	}

	.modal-backdrop {
		position: absolute;
		inset: 0;
		background: rgba(0, 0, 0, 0.6);
		backdrop-filter: blur(4px);
		border: none;
		padding: 0;
		margin: 0;
		cursor: pointer;
	}

	.modal-content {
		background: var(--bg-panel);
		border: 1px solid var(--border-subtle);
		border-radius: 12px;
		width: 100%;
		max-width: 440px;
		box-shadow: var(--shadow-lg);
		transform: scale(0.95);
		opacity: 0;
		animation: modalIn 200ms cubic-bezier(0.23, 1, 0.32, 1) forwards;
		position: relative;
		z-index: 1;
	}

	.modal-content-wide { max-width: 720px; }

	.modal-header {
		padding: 24px 24px 16px;
		display: flex;
		align-items: center;
		gap: 16px;
	}

	.modal-header h3 {
		margin: 0;
		font-size: 18px;
		font-weight: 600;
		color: var(--text-primary);
	}

	.modal-icon.warning {
		width: 40px;
		height: 40px;
		border-radius: 50%;
		background: rgba(var(--color-critical-rgb), 0.15);
		color: var(--color-critical);
		display: flex;
		align-items: center;
		justify-content: center;
	}

	.modal-icon.info {
		width: 40px;
		height: 40px;
		border-radius: 50%;
		background: rgba(var(--accent-primary-rgb), 0.15);
		color: var(--accent-primary);
		display: flex;
		align-items: center;
		justify-content: center;
	}

	.modal-body {
		padding: 0 24px 24px;
		color: var(--text-secondary);
		font-size: 14px;
		line-height: 1.5;
	}

	.modal-body p { margin: 0; }
	.modal-help { margin-bottom: 12px; }

	.mono-textarea {
		width: 100%;
		resize: vertical;
		font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, "Liberation Mono", "Courier New", monospace;
		min-height: 220px;
	}

	.modal-footer {
		padding: 16px 24px;
		border-top: 1px solid var(--border-subtle);
		background: var(--bg-panel);
		border-radius: 0 0 12px 12px;
	}

	.btn-danger {
		background: var(--color-critical);
		color: var(--text-on-accent);
		border: 1px solid var(--color-critical);
	}

	.btn-danger:hover {
		opacity: 0.9;
	}

	@keyframes fadeIn {
		from { opacity: 0; }
		to { opacity: 1; }
	}

	@keyframes modalIn {
		to {
			transform: scale(1);
			opacity: 1;
		}
	}
</style>
