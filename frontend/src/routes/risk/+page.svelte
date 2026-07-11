<script lang="ts">
	import { onMount, onDestroy } from 'svelte';
	import { goto } from '$app/navigation';
	import { apiFetch } from '$lib/api';
	import { toast } from '$lib/toastStore';

	type RiskItem = {
		id: string;
		contract_id: string;
		contract_filename: string;
		clause_type: string;
		text_content: string;
		risk_level: string;
		risk_reasoning?: string | null;
		redline_suggestion?: string | null;
		created_at: string;
	};

	let risks: RiskItem[] = $state([]);
	let isLoading = $state(true);
	let pollInterval: any;

	// Filters
	let searchQuery = $state('');
	let severityFilter = $state('ALL'); // 'ALL' | 'CRITICAL' | 'HIGH'
	let clauseTypeFilter = $state('ALL');
	let contractFilter = $state('ALL');

	// UI Dropdown States
	let isClauseDropdownOpen = $state(false);
	let isContractDropdownOpen = $state(false);

	// UI Expanded rows
	let expandedRows = $state<Record<string, boolean>>({});

	// Base metrics that only depend on the 'risks' array
	let baseMetrics = $derived.by(() => {
		let critical = 0;
		let high = 0;
		const docIds = new Set<string>();
		const clauses = new Set<string>();
		const contracts = new Set<string>();

		for (const r of risks) {
			if (r.risk_level === 'CRITICAL') critical++;
			else if (r.risk_level === 'HIGH') high++;

			docIds.add(r.contract_id);
			if (r.clause_type) clauses.add(r.clause_type);
			if (r.contract_filename) contracts.add(r.contract_filename);
		}

		return {
			criticalCount: critical,
			highCount: high,
			affectedDocsCount: docIds.size,
			uniqueClauseTypes: ['ALL', ...clauses],
			uniqueContracts: ['ALL', ...contracts]
		};
	});

	let totalRisksCount = $derived(risks.length);
	let criticalCount = $derived(baseMetrics.criticalCount);
	let highCount = $derived(baseMetrics.highCount);
	let affectedDocsCount = $derived(baseMetrics.affectedDocsCount);
	let avgRisksPerDoc = $derived(affectedDocsCount > 0 ? (totalRisksCount / affectedDocsCount).toFixed(1) : '0.0');

	// Dynamic unique list of clause types and contracts for dropdown filters
	let uniqueClauseTypes = $derived(baseMetrics.uniqueClauseTypes);
	let uniqueContracts = $derived(baseMetrics.uniqueContracts);

	// Filtered feed that depends on both 'risks' and filter values
	let filteredRisks = $derived.by(() => {
		const filtered: RiskItem[] = [];
		const searchLower = searchQuery.toLowerCase();

		for (const r of risks) {
			const matchesSearch = 
				r.clause_type.toLowerCase().includes(searchLower) ||
				r.text_content.toLowerCase().includes(searchLower) ||
				(r.risk_reasoning || '').toLowerCase().includes(searchLower) ||
				r.contract_filename.toLowerCase().includes(searchLower);
			
			const matchesSeverity = 
				severityFilter === 'ALL' || 
				r.risk_level.toUpperCase() === severityFilter;
				
			const matchesClause = 
				clauseTypeFilter === 'ALL' || 
				r.clause_type === clauseTypeFilter;
				
			const matchesContract = 
				contractFilter === 'ALL' || 
				r.contract_filename === contractFilter;
				
			if (matchesSearch && matchesSeverity && matchesClause && matchesContract) {
				filtered.push(r);
			}
		}

		return filtered;
	});

	async function fetchRisks(silent = false) {
		if (!silent) isLoading = true;
		try {
			const res = await apiFetch('/api/v1/risks');
			if (!res.ok) return;
			const json = await res.json();
			risks = json.risks || [];
		} catch (err) {
			console.error('Failed to fetch risks:', err);
		} finally {
			if (!silent) isLoading = false;
		}
	}

	function toggleRow(id: string) {
		expandedRows = {
			...expandedRows,
			[id]: !expandedRows[id]
		};
	}

	async function copyRedline(r: RiskItem) {
		if (!r.redline_suggestion) return;
		const payload = 
			`Document: ${r.contract_filename}\n` +
			`Clause Type: ${r.clause_type}\n\n` +
			`Original Language:\n${r.text_content}\n\n` +
			`AI Suggested Redline:\n${r.redline_suggestion}\n\n` +
			`Risk Rationale:\n${r.risk_reasoning || 'Flagged for visual inspection.'}\n`;
		
		try {
			await navigator.clipboard.writeText(payload);
			toast.success('Redline & risk details copied!');
		} catch (e) {
			toast.error('Failed to copy.');
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

	// Svelte custom action for clicking outside dropdown menus
	function clickOutside(node: HTMLElement, callback: () => void) {
		const handleClick = (event: MouseEvent) => {
			if (node && !node.contains(event.target as Node) && !event.defaultPrevented) {
				callback();
			}
		};
		document.addEventListener('click', handleClick);
		return {
			destroy() {
				document.removeEventListener('click', handleClick);
			}
		};
	}

	onMount(() => {
		fetchRisks();
		pollInterval = setInterval(() => fetchRisks(true), 3000);
	});

	onDestroy(() => {
		if (pollInterval) clearInterval(pollInterval);
	});
</script>

<header class="page-header">
	<div class="page-header-inner">
		<div class="breadcrumbs">
			<span class="crumb">ContractsPulse</span>
			<span class="separator">›</span>
			<span class="crumb active">Risk Inbox</span>
		</div>
		<div class="header-content">
			<div class="header-title-row">
				<span class="header-icon">
					<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"/><line x1="12" y1="9" x2="12" y2="13"/><line x1="12" y1="17" x2="12.01" y2="17"/></svg>
				</span>
				<h1>Risk Inbox</h1>
			</div>
			<p class="subtitle text-secondary">Portfolio-wide consolidated feed of active high-severity contract vulnerabilities.</p>
		</div>
	</div>
</header>

<div class="page-content">
	<div class="metric-row">
		<div class="metric-card panel bg-glass-card">
			<div class="metric-header flex-between">
				<span class="metric-label">Critical Vulnerabilities</span>
				<span class="m-dot m-dot-critical"></span>
			</div>
			<div class="metric-value text-critical font-bold">{criticalCount}</div>
		</div>
		<div class="metric-card panel bg-glass-card">
			<div class="metric-header flex-between">
				<span class="metric-label">High-Risk Clauses</span>
				<span class="m-dot m-dot-high"></span>
			</div>
			<div class="metric-value text-high font-bold">{highCount}</div>
		</div>
		<div class="metric-card panel bg-glass-card">
			<div class="metric-header flex-between">
				<span class="metric-label">Affected Documents</span>
				<span class="m-dot m-dot-neutral"></span>
			</div>
			<div class="metric-value text-primary">{affectedDocsCount}</div>
		</div>
		<div class="metric-card panel bg-glass-card">
			<div class="metric-header flex-between">
				<span class="metric-label">Average Risks/Document</span>
				<span class="m-dot m-dot-neutral"></span>
			</div>
			<div class="metric-value text-secondary">{avgRisksPerDoc}</div>
		</div>
	</div>

	<!-- Inbox Filter Controls -->
	<div class="filters-panel panel bg-panel-glow">
		<div class="search-and-severity flex-row gap-12">
			<div class="search-input-wrapper">
				<svg class="search-icon" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/></svg>
				<input 
					type="text" 
					placeholder="Search risks by keyword, type, or contract..." 
					bind:value={searchQuery}
					class="risk-search-bar"
					aria-label="Search risks by keyword, type, or contract"
				/>
			</div>

			<div class="severity-pills flex-row gap-6">
				<button type="button" class="filter-pill" class:active={severityFilter === 'ALL'} onclick={() => severityFilter = 'ALL'}>
					All Severe ({totalRisksCount})
				</button>
				<button type="button" class="filter-pill filter-pill-critical" class:active={severityFilter === 'CRITICAL'} onclick={() => severityFilter = 'CRITICAL'}>
					Critical ({criticalCount})
				</button>
				<button type="button" class="filter-pill filter-pill-high" class:active={severityFilter === 'HIGH'} onclick={() => severityFilter = 'HIGH'}>
					High ({highCount})
				</button>
			</div>
		</div>

		<div class="dropdown-filters-row flex-row gap-16">
			<!-- Custom Clause Type Dropdown Selector -->
			<div class="select-wrapper flex-row gap-8">
				<span class="select-label">Clause Type:</span>
				<div class="custom-select-container">
					<button 
						type="button"
						class="custom-select-trigger" 
						aria-haspopup="listbox"
						aria-expanded={!!isClauseDropdownOpen}
						class:active={isClauseDropdownOpen}
						onclick={(e) => { e.stopPropagation(); isClauseDropdownOpen = !isClauseDropdownOpen; isContractDropdownOpen = false; }}
					>
						<span>{clauseTypeFilter === 'ALL' ? 'All Types' : clauseTypeFilter}</span>
						<svg class="dropdown-arrow-icon" class:rotated={isClauseDropdownOpen} width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><polyline points="6 9 12 15 18 9"/></svg>
					</button>
					{#if isClauseDropdownOpen}
						<div class="custom-select-popover" use:clickOutside={() => isClauseDropdownOpen = false}>
							{#each uniqueClauseTypes as type}
								<button 
									type="button"
									class="dropdown-item" 
									class:selected={clauseTypeFilter === type} 
									onclick={() => { clauseTypeFilter = type; isClauseDropdownOpen = false; }}
								>
									<span>{type === 'ALL' ? 'All Types' : type}</span>
									{#if clauseTypeFilter === type}
										<svg class="check-icon" width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3"><polyline points="20 6 9 17 4 12"/></svg>
									{/if}
								</button>
							{/each}
						</div>
					{/if}
				</div>
			</div>

			<!-- Custom Contract Source Dropdown Selector -->
			<div class="select-wrapper flex-row gap-8">
				<span class="select-label">Document Source:</span>
				<div class="custom-select-container">
					<button 
						type="button"
						class="custom-select-trigger" 
						aria-haspopup="listbox"
						aria-expanded={!!isContractDropdownOpen}
						class:active={isContractDropdownOpen}
						onclick={(e) => { e.stopPropagation(); isContractDropdownOpen = !isContractDropdownOpen; isClauseDropdownOpen = false; }}
						style="max-width: 250px;"
					>
						<span class="truncate">{contractFilter === 'ALL' ? 'All Contracts' : contractFilter}</span>
						<svg class="dropdown-arrow-icon" class:rotated={isContractDropdownOpen} width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><polyline points="6 9 12 15 18 9"/></svg>
					</button>
					{#if isContractDropdownOpen}
						<div class="custom-select-popover" use:clickOutside={() => isContractDropdownOpen = false} style="min-width: 280px;">
							{#each uniqueContracts as filename}
								<button 
									type="button"
									class="dropdown-item" 
									class:selected={contractFilter === filename} 
									onclick={() => { contractFilter = filename; isContractDropdownOpen = false; }}
								>
									<span class="truncate" style="max-width: 230px;" title={filename}>{filename === 'ALL' ? 'All Contracts' : filename}</span>
									{#if contractFilter === filename}
										<svg class="check-icon" width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3"><polyline points="20 6 9 17 4 12"/></svg>
									{/if}
								</button>
							{/each}
						</div>
					{/if}
				</div>
			</div>
		</div>
	</div>

	<!-- Unified Risk Feed -->
	{#if isLoading}
		<div class="feed-loading">
			<span class="spinner spinner-lg"></span>
			<p>Retrieving active vulnerabilities...</p>
		</div>
	{:else if filteredRisks.length === 0}
		<div class="empty-feed panel bg-glass-card">
			<svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" class="empty-icon"><path d="M22 11.08V12a10 10 0 1 1-5.93-9.14"/><polyline points="22 4 12 14.01 9 11.01"/></svg>
			<h3>Risk Inbox Clean</h3>
			<p class="text-secondary">No severe contract vulnerabilities match your active filter settings.</p>
		</div>
	{:else}
		<div class="inbox-count text-tertiary">{filteredRisks.length} {filteredRisks.length === 1 ? 'finding' : 'findings'}</div>
		<div class="risk-feed">
			{#each filteredRisks as r (r.id)}
				{@const isExpanded = expandedRows[r.id]}
				{@const sevClass = r.risk_level === 'CRITICAL' ? 'badge-danger' : r.risk_level === 'HIGH' ? 'badge-warning' : 'badge-secondary'}
				<div class="risk-item" class:expanded={isExpanded}>
					<button type="button" class="risk-item-summary" aria-expanded={isExpanded} onclick={() => toggleRow(r.id)}>
						<div class="risk-item-top">
							<div class="risk-item-title">
								<span class="badge badge-sm {sevClass}">{r.risk_level}</span>
								<span class="risk-item-clause">{r.clause_type || 'General clause'}</span>
								{#if r.redline_suggestion}
									<span class="redline-flag" title="AI redline available">
										<svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><path d="M12 20h9"/><path d="M16.5 3.5a2.12 2.12 0 0 1 3 3L7 19l-4 1 1-4Z"/></svg>
										Redline
									</span>
								{/if}
							</div>
							<div class="risk-item-meta">
								<span class="risk-item-time">{timeAgo(r.created_at)}</span>
								<svg class="row-chevron" class:rotated={isExpanded} width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="6 9 12 15 18 9"/></svg>
							</div>
						</div>

						<div class="risk-item-doc text-tertiary">
							<svg class="file-icon" width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/></svg>
							<span class="risk-item-filename" title={r.contract_filename}>{r.contract_filename}</span>
						</div>

						<p class="risk-item-reason" class:clamp={!isExpanded}>{r.risk_reasoning || 'Clause contains terms that require legal review.'}</p>
					</button>

					<!-- Expandable detail -->
					<div class="risk-detail-wrap" style="display:grid; grid-template-rows: {isExpanded ? '1fr' : '0fr'}; transition: grid-template-rows 240ms var(--ease-out);">
						<div style="overflow:hidden;">
							<div class="risk-detail">
								<div class="detail-section">
									<div class="detail-label">Clause excerpt</div>
									<blockquote class="clause-quote">{r.text_content}</blockquote>
								</div>

								{#if r.redline_suggestion}
									<div class="detail-section">
										<div class="detail-label">Suggested redline</div>
										<div class="redline-suggest">{r.redline_suggestion}</div>
									</div>
								{/if}

								<div class="detail-actions">
									<button class="btn btn-secondary btn-compact" onclick={() => copyRedline(r)}>Copy details</button>
									<button class="btn btn-secondary btn-compact" onclick={() => goto(`/contracts/${r.contract_id}`)}>View document</button>
									<button class="btn btn-primary btn-compact" onclick={() => goto(`/contracts/${r.contract_id}?tab=clauses&search=${encodeURIComponent(r.clause_type)}&risk=${r.risk_level}`)}>
										Resolve in Cockpit
										<svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><line x1="5" y1="12" x2="19" y2="12"/><polyline points="12 5 19 12 12 19"/></svg>
									</button>
								</div>
							</div>
						</div>
					</div>
				</div>
			{/each}
		</div>
	{/if}
</div>

<style>
	.page-content {
		padding: 32px 40px;
		max-width: 1200px;
		margin: 0 auto;
		width: 100%;
	}

	/* Overview Metric Row */
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
	}

	.metric-header {
		font-size: 11px;
		font-weight: 600;
		color: var(--text-secondary);
		text-transform: uppercase;
		letter-spacing: 0.5px;
	}

	.metric-value {
		font-size: 24px;
		margin-top: 12px;
		line-height: 1;
	}

	.m-dot {
		width: 6px;
		height: 6px;
		border-radius: 50%;
	}
	.m-dot-critical { background: var(--color-critical); }
	.m-dot-high { background: var(--color-high); }
	.m-dot-neutral { background: var(--text-tertiary); }

	/* Filter Control Panel */
	.filters-panel {
		padding: 20px;
		display: flex;
		flex-direction: column;
		gap: 16px;
		margin-bottom: 24px;
		background: var(--bg-panel);
		border: 1px solid var(--border-subtle);
	}

	.search-and-severity {
		display: grid;
		grid-template-columns: 1fr auto;
		align-items: center;
	}

	.search-input-wrapper {
		position: relative;
		display: flex;
		align-items: center;
		flex: 1;
	}

	.search-icon {
		position: absolute;
		left: 12px;
		color: var(--text-tertiary);
		pointer-events: none;
	}

	.risk-search-bar {
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

	.risk-search-bar:focus {
		border-color: var(--text-secondary);
	}

	.filter-pill {
		background: transparent;
		border: 1px solid var(--border-subtle);
		color: var(--text-secondary);
		font-size: 12px;
		font-weight: 500;
		padding: 6px 12px;
		border-radius: 6px;
		cursor: pointer;
		transition: all 150ms var(--ease-out);
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
		border-color: rgba(var(--color-critical-rgb), 0.3);
		background: rgba(var(--color-critical-rgb), 0.08);
		color: var(--color-critical);
	}

	.filter-pill-high.active {
		border-color: rgba(var(--color-high-rgb), 0.3);
		background: rgba(var(--color-high-rgb), 0.08);
		color: var(--color-high);
	}

	.dropdown-filters-row {
		display: flex;
		flex-wrap: wrap;
		align-items: center;
		padding-top: 14px;
		border-top: 1px solid var(--border-subtle);
	}

	.select-wrapper {
		font-size: 12px;
		color: var(--text-secondary);
	}

	.select-dropdown {
		background: var(--bg-app);
		border: 1px solid var(--border-subtle);
		color: var(--text-primary);
		font-size: 12px;
		border-radius: 6px;
		padding: 4px 8px;
		outline: none;
		cursor: pointer;
		transition: border-color 150ms ease;
	}

	.select-dropdown:focus {
		border-color: var(--text-secondary);
	}

	.select-dropdown-wide {
		max-width: 200px;
	}

	/* Feed Loading */
	.feed-loading {
		display: flex;
		flex-direction: column;
		align-items: center;
		justify-content: center;
		padding: 80px 0;
		gap: 16px;
		color: var(--text-secondary);
	}

	/* Empty Feed */
	.empty-feed {
		display: flex;
		flex-direction: column;
		align-items: center;
		justify-content: center;
		padding: 60px 40px;
		text-align: center;
		border: 1px dashed var(--border-strong);
	}

	.empty-icon {
		color: var(--color-low);
		margin-bottom: 16px;
	}

	.empty-feed h3 {
		font-size: 16px;
		margin-bottom: 6px;
	}

	.empty-feed p {
		font-size: 13px;
	}

	/* ------------------------------------------------------------
	   Risk findings — dashboard-style cards with inline expand
	   ------------------------------------------------------------- */
	.inbox-count {
		font-size: var(--fs-xs, 12px);
		font-weight: 500;
		margin-bottom: 12px;
	}

	.risk-feed {
		display: flex;
		flex-direction: column;
		gap: 12px;
	}

	.risk-item {
		border-radius: 8px;
		background: var(--bg-glass-card);
		border: 1px solid var(--border-subtle);
		overflow: hidden;
		transition: border-color 150ms ease, box-shadow 150ms ease;
	}
	.risk-item:hover,
	.risk-item.expanded {
		border-color: var(--border-glass-hover);
		box-shadow: var(--shadow-sm);
	}

	.risk-item-summary {
		width: 100%;
		display: flex;
		flex-direction: column;
		gap: 8px;
		padding: 16px;
		background: transparent;
		border: none;
		text-align: left;
		cursor: pointer;
	}

	.risk-item-top {
		display: flex;
		justify-content: space-between;
		align-items: center;
		gap: 12px;
	}

	.risk-item-title {
		display: flex;
		align-items: center;
		gap: 8px;
		min-width: 0;
	}
	.risk-item-clause {
		font-size: var(--fs-sm, 13px);
		font-weight: 600;
		color: var(--text-primary);
		white-space: nowrap;
		overflow: hidden;
		text-overflow: ellipsis;
	}
	.redline-flag {
		display: inline-flex;
		align-items: center;
		gap: 4px;
		flex-shrink: 0;
		font-size: 9.5px;
		font-weight: 700;
		text-transform: uppercase;
		letter-spacing: 0.4px;
		color: var(--accent-primary);
		background: rgba(var(--accent-primary-rgb), 0.10);
		padding: 2px 7px;
		border-radius: 999px;
	}

	.risk-item-meta {
		display: flex;
		align-items: center;
		gap: 8px;
		flex-shrink: 0;
		color: var(--text-tertiary);
	}
	.risk-item-time { font-size: var(--fs-2xs, 11px); white-space: nowrap; }
	.row-chevron { transition: transform 200ms var(--ease-out); color: var(--text-tertiary); }
	.row-chevron.rotated { transform: rotate(180deg); color: var(--text-secondary); }

	.risk-item-doc {
		display: flex;
		align-items: center;
		gap: 6px;
		font-size: var(--fs-2xs, 11px);
		min-width: 0;
	}
	.file-icon { color: var(--text-tertiary); flex-shrink: 0; }
	.risk-item-filename {
		white-space: nowrap;
		overflow: hidden;
		text-overflow: ellipsis;
	}

	.risk-item-reason {
		margin: 0;
		font-size: var(--fs-xs, 12px);
		color: var(--text-secondary);
		line-height: 1.5;
	}
	.risk-item-reason.clamp {
		display: -webkit-box;
		-webkit-line-clamp: 2;
		line-clamp: 2;
		-webkit-box-orient: vertical;
		overflow: hidden;
	}

	/* Expanded detail */
	.risk-detail {
		padding: 0 16px 16px;
		display: flex;
		flex-direction: column;
		gap: 14px;
	}

	.detail-section { display: flex; flex-direction: column; gap: 6px; }
	.detail-label {
		font-size: 10px;
		font-weight: 700;
		text-transform: uppercase;
		letter-spacing: 0.6px;
		color: var(--text-tertiary);
	}

	.clause-quote {
		margin: 0;
		padding: 12px 14px;
		border-left: 2px solid var(--border-strong);
		background: var(--bg-sidebar);
		border-radius: 0 6px 6px 0;
		font-size: 12.5px;
		line-height: 1.6;
		color: var(--text-secondary);
		white-space: pre-wrap;
		word-break: break-word;
		max-height: 170px;
		overflow-y: auto;
	}

	.redline-suggest {
		padding: 12px 14px;
		border-left: 2px solid rgba(var(--color-low-rgb), 0.5);
		background: var(--bg-sidebar);
		border-radius: 0 6px 6px 0;
		font-size: 12.5px;
		line-height: 1.6;
		color: var(--text-primary);
		white-space: pre-wrap;
		word-break: break-word;
		max-height: 220px;
		overflow-y: auto;
	}

	.detail-actions {
		display: flex;
		flex-wrap: wrap;
		gap: 8px;
		justify-content: flex-end;
	}

	.btn-compact {
		height: 28px;
		padding: 0 12px;
		font-size: 12px;
		border-radius: 6px;
	}

	@media (max-width: 768px) {
		.metric-row {
			grid-template-columns: 1fr 1fr;
		}

		.search-and-severity {
			grid-template-columns: 1fr;
			gap: 12px;
		}
	}
</style>
