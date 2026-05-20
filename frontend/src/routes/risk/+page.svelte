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

	// UI Expanded drawers
	let expandedRedlines = $state<Record<string, boolean>>({});

	// Derived metrics
	let totalRisksCount = $derived(risks.length);
	let criticalCount = $derived(risks.filter(r => r.risk_level === 'CRITICAL').length);
	let highCount = $derived(risks.filter(r => r.risk_level === 'HIGH').length);
	let affectedDocsCount = $derived(new Set(risks.map(r => r.contract_id)).size);
	let avgRisksPerDoc = $derived(affectedDocsCount > 0 ? (totalRisksCount / affectedDocsCount).toFixed(1) : '0.0');

	// Dynamic unique list of clause types and contracts for dropdown filters
	let uniqueClauseTypes = $derived(['ALL', ...new Set(risks.map(r => r.clause_type).filter(Boolean))]);
	let uniqueContracts = $derived(['ALL', ...new Set(risks.map(r => r.contract_filename).filter(Boolean))]);

	// Filtered feed
	let filteredRisks = $derived(
		risks.filter(r => {
			const matchesSearch = 
				r.clause_type.toLowerCase().includes(searchQuery.toLowerCase()) ||
				r.text_content.toLowerCase().includes(searchQuery.toLowerCase()) ||
				(r.risk_reasoning || '').toLowerCase().includes(searchQuery.toLowerCase()) ||
				r.contract_filename.toLowerCase().includes(searchQuery.toLowerCase());
			
			const matchesSeverity = 
				severityFilter === 'ALL' || 
				r.risk_level.toUpperCase() === severityFilter;
				
			const matchesClause = 
				clauseTypeFilter === 'ALL' || 
				r.clause_type === clauseTypeFilter;
				
			const matchesContract = 
				contractFilter === 'ALL' || 
				r.contract_filename === contractFilter;
				
			return matchesSearch && matchesSeverity && matchesClause && matchesContract;
		})
	);

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

	function toggleRedline(id: string) {
		expandedRedlines = {
			...expandedRedlines,
			[id]: !expandedRedlines[id]
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
			<span class="separator">/</span>
			<span class="crumb active">Risk Inbox</span>
		</div>
		<div class="header-content">
			<h1>Risk Inbox</h1>
			<p class="subtitle text-secondary">Portfolio-wide consolidated feed of active high-severity contract vulnerabilities.</p>
		</div>
	</div>
</header>

<div class="page-content">
	<!-- Workspace Overview Metrics Grid -->
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
				/>
			</div>

			<div class="severity-pills flex-row gap-6">
				<button class="filter-pill" class:active={severityFilter === 'ALL'} onclick={() => severityFilter = 'ALL'}>
					All Severe ({totalRisksCount})
				</button>
				<button class="filter-pill filter-pill-critical" class:active={severityFilter === 'CRITICAL'} onclick={() => severityFilter = 'CRITICAL'}>
					Critical ({criticalCount})
				</button>
				<button class="filter-pill filter-pill-high" class:active={severityFilter === 'HIGH'} onclick={() => severityFilter = 'HIGH'}>
					High ({highCount})
				</button>
			</div>
		</div>

		<div class="dropdown-filters-row flex-row gap-16">
			<div class="select-wrapper flex-row gap-8">
				<span class="select-label">Clause Type:</span>
				<select bind:value={clauseTypeFilter} class="select-dropdown">
					{#each uniqueClauseTypes as type}
						<option value={type}>{type === 'ALL' ? 'All Types' : type}</option>
					{/each}
				</select>
			</div>

			<div class="select-wrapper flex-row gap-8">
				<span class="select-label">Document Source:</span>
				<select bind:value={contractFilter} class="select-dropdown select-dropdown-wide">
					{#each uniqueContracts as filename}
						<option value={filename}>{filename === 'ALL' ? 'All Contracts' : filename}</option>
					{/each}
				</select>
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
		<div class="risks-feed">
			{#each filteredRisks as r (r.id)}
				{@const isCritical = r.risk_level === 'CRITICAL'}
				{@const isExpanded = expandedRedlines[r.id]}
				<div class="risk-card panel risk-{r.risk_level.toLowerCase()}" class:card-expanded={isExpanded}>
					<!-- Header Section -->
					<div class="risk-card-header flex-between">
						<div class="risk-origin flex-row gap-8">
							<span class="origin-label">Document:</span>
							<button class="doc-chip-btn truncate" onclick={() => goto(`/contracts/${r.contract_id}`)} title="View Contract">
								<svg class="file-icon" width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/></svg>
								{r.contract_filename}
							</button>
						</div>

						<div class="risk-severity flex-row gap-8">
							<span class="clause-type-badge font-mono">{r.clause_type}</span>
							<span class="badge badge-{isCritical ? 'danger' : 'warning'} font-bold">
								{r.risk_level}
							</span>
						</div>
					</div>

					<!-- Body Section: Reasoning & Clause Text excerpt -->
					<div class="risk-card-body">
						<div class="risk-reasoning">
							<strong>Why it matters:</strong> {r.risk_reasoning || 'Clause contains terms that require immediate legal audit.'}
						</div>

						<div class="clause-text-block font-mono">
							{r.text_content}
						</div>
					</div>

					<!-- Redline Suggested Drawer -->
					{#if r.redline_suggestion}
						<div class="redline-drawer" class:open={isExpanded}>
							<!-- svelte-ignore a11y_click_events_have_key_events -->
							<!-- svelte-ignore a11y_no_static_element_interactions -->
							<div class="redline-toggle flex-between" onclick={() => toggleRedline(r.id)}>
								<span class="flex-row gap-6 font-semibold">
									<svg class="chevron-icon" class:rotated={isExpanded} width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="9 18 15 12 9 6"/></svg>
									Suggested Alternative (Redline)
								</span>
								{#if isExpanded}
									<button class="btn btn-secondary btn-compact text-xs" onclick={(e) => { e.stopPropagation(); copyRedline(r); }}>
										Copy Redline
									</button>
								{/if}
							</div>

							{#if isExpanded}
								<pre class="redline-suggestion-content font-mono">{r.redline_suggestion}</pre>
							{/if}
						</div>
					{/if}

					<!-- Footer Action Panel -->
					<div class="risk-card-footer flex-between">
						<span class="uploaded-time text-tertiary">Found {timeAgo(r.created_at)}</span>
						
						<div class="footer-actions flex-row gap-12">
							<button class="btn btn-secondary btn-compact" onclick={() => copyRedline(r)}>
								Copy Details
							</button>
							<button class="btn btn-primary btn-compact" onclick={() => goto(`/contracts/${r.contract_id}?tab=clauses&search=${encodeURIComponent(r.clause_type)}&risk=${r.risk_level}`)}>
								Resolve in Cockpit
								<svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><line x1="5" y1="12" x2="19" y2="12"/><polyline points="12 5 19 12 12 19"/></svg>
							</button>
						</div>
					</div>
				</div>
			{/each}
		</div>
	{/if}
</div>

<style>
	.page-header {
		padding: 32px 40px 24px;
		border-bottom: 1px solid var(--border-subtle);
		background: #111112;
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
	.m-dot-critical { background: var(--color-critical); box-shadow: 0 0 8px var(--color-critical); }
	.m-dot-high { background: var(--color-high); box-shadow: 0 0 8px var(--color-high); }
	.m-dot-neutral { background: var(--text-tertiary); }

	/* Filter Control Panel */
	.filters-panel {
		padding: 20px;
		display: flex;
		flex-direction: column;
		gap: 16px;
		margin-bottom: 24px;
		background: #171719;
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
		border-radius: 99px;
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
		border-color: rgba(255, 59, 48, 0.4);
		background: rgba(255, 59, 48, 0.08);
		color: var(--color-critical);
	}

	.filter-pill-high.active {
		border-color: rgba(248, 81, 73, 0.4);
		background: rgba(248, 81, 73, 0.08);
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

	/* Risks Feed */
	.risks-feed {
		display: flex;
		flex-direction: column;
		gap: 16px;
	}

	.risk-card {
		padding: 24px;
		background: var(--bg-panel);
		transition: border-color 200ms var(--ease-out), transform 150ms var(--ease-out);
		position: relative;
		overflow: hidden;
	}

	.risk-card::before {
		content: '';
		position: absolute;
		left: 0;
		top: 0;
		bottom: 0;
		width: 4px;
		transition: background 150ms ease;
	}

	/* Risk Ambient Glow Borders */
	.risk-critical {
		border-color: var(--glow-critical-border);
	}
	.risk-critical::before {
		background: var(--color-critical);
	}
	.risk-critical:hover {
		border-color: rgba(255, 59, 48, 0.4);
		box-shadow: 0 4px 20px rgba(255, 59, 48, 0.05);
	}

	.risk-high {
		border-color: var(--glow-high-border);
	}
	.risk-high::before {
		background: var(--color-high);
	}
	.risk-high:hover {
		border-color: rgba(248, 81, 73, 0.35);
		box-shadow: 0 4px 20px rgba(248, 81, 73, 0.04);
	}

	.risk-card-header {
		padding-bottom: 16px;
		border-bottom: 1px solid var(--border-subtle);
		margin-bottom: 16px;
	}

	.origin-label {
		font-size: 12px;
		color: var(--text-tertiary);
	}

	.doc-chip-btn {
		background: var(--bg-hover);
		border: 1px solid var(--border-subtle);
		color: var(--text-primary);
		padding: 4px 10px;
		border-radius: 4px;
		font-size: 12px;
		font-weight: 500;
		cursor: pointer;
		display: inline-flex;
		align-items: center;
		gap: 6px;
		max-width: 250px;
		transition: transform 100ms var(--ease-out), background 150ms ease;
	}

	.doc-chip-btn:active {
		transform: scale(0.97);
	}

	.doc-chip-btn:hover {
		background: var(--bg-active);
		border-color: var(--border-strong);
	}

	.clause-type-badge {
		font-size: 11px;
		background: rgba(255, 255, 255, 0.04);
		color: var(--text-secondary);
		border: 1px solid var(--border-subtle);
		padding: 2px 8px;
		border-radius: 4px;
	}

	.risk-card-body {
		margin-bottom: 20px;
	}

	.risk-reasoning {
		font-size: 13px;
		color: var(--text-primary);
		line-height: 1.5;
		margin-bottom: 14px;
	}

	.clause-text-block {
		background: #111112;
		border: 1px solid var(--border-subtle);
		border-radius: 6px;
		padding: 14px 18px;
		color: #a9a9b3;
		font-size: 12px;
		line-height: 1.6;
		max-height: 180px;
		overflow-y: auto;
		white-space: pre-wrap;
	}

	/* Redline Drawer */
	.redline-drawer {
		background: rgba(255, 255, 255, 0.02);
		border: 1px solid var(--border-subtle);
		border-radius: 6px;
		margin-bottom: 20px;
		overflow: hidden;
		transition: all 200ms var(--ease-out);
	}

	.redline-drawer.open {
		border-color: var(--border-strong);
		background: rgba(255, 255, 255, 0.03);
	}

	.redline-toggle {
		padding: 10px 14px;
		font-size: 12px;
		cursor: pointer;
		user-select: none;
		color: var(--text-secondary);
		transition: color 150ms ease;
	}

	.redline-toggle:hover {
		color: var(--text-primary);
	}

	.chevron-icon {
		transition: transform 200ms var(--ease-out);
	}

	.chevron-icon.rotated {
		transform: rotate(90deg);
	}

	.redline-suggestion-content {
		padding: 0 14px 14px;
		margin: 0;
		font-size: 12px;
		line-height: 1.6;
		color: #3fb950;
		background: transparent;
		white-space: pre-wrap;
		overflow-x: auto;
	}

	/* Footer Action Panel */
	.risk-card-footer {
		padding-top: 16px;
		border-top: 1px solid var(--border-subtle);
	}

	.uploaded-time {
		font-size: 11px;
	}

	.btn-compact {
		height: 28px;
		padding: 0 10px;
		font-size: 12px;
	}

	@media (max-width: 768px) {
		.metric-row {
			grid-template-columns: 1fr 1fr;
		}

		.search-and-severity {
			grid-template-columns: 1fr;
			gap: 12px;
		}

		.risk-card-header {
			flex-direction: column;
			align-items: flex-start;
			gap: 12px;
		}
	}
</style>
