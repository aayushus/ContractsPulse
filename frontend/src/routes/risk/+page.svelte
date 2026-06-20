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

	// UI Expanded drawers
	let expandedRedlines = $state<Record<string, boolean>>({});

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
		<div class="risks-feed">
			{#each filteredRisks as r, i (r.id)}
				{@const isCritical = r.risk_level === 'CRITICAL'}
				{@const isExpanded = expandedRedlines[r.id]}
				<div class="risk-card panel risk-{r.risk_level.toLowerCase()} stagger-entry" style="--index: {i}" class:card-expanded={isExpanded}>
					<!-- Header Section -->
					<div class="risk-card-header flex-between">
						<div class="risk-origin flex-row gap-8">
							<span class="origin-label">Document:</span>
							<button class="doc-chip-btn" onclick={() => goto(`/contracts/${r.contract_id}`)} title="View Contract">
								<svg class="paperclip-icon" style="flex-shrink: 0;" width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21.44 11.05l-9.19 9.19a6 6 0 0 1-8.49-8.49l9.19-9.19a4 4 0 0 1 5.66 5.66l-9.2 9.19a2 2 0 0 1-2.83-2.83l8.49-8.48"/></svg>
								<span class="filename-text" title={r.contract_filename}>{r.contract_filename}</span>
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
								<button class="btn btn-secondary btn-compact text-xs" style="opacity: {isExpanded ? 1 : 0}; pointer-events: {isExpanded ? 'auto' : 'none'}; transition: opacity 150ms var(--ease-out);" onclick={(e) => { e.stopPropagation(); copyRedline(r); }}>
									Copy Redline
								</button>
							</div>

							<div class="redline-drawer-content-wrapper" style="display: grid; grid-template-rows: {isExpanded ? '1fr' : '0fr'}; transition: grid-template-rows 250ms var(--ease-out);">
								<div style="overflow: hidden;">
									<div class="diff-comparison-pane">
										<div class="diff-column diff-column-original">
											<div class="diff-header font-semibold text-xs text-secondary flex-between">
												<span>Current Clause Language</span>
												<span class="diff-badge diff-badge-removed">Original</span>
											</div>
											<div class="diff-content font-mono">{r.text_content}</div>
										</div>
										<div class="diff-column diff-column-suggested">
											<div class="diff-header font-semibold text-xs text-secondary flex-between">
												<span>AI Recommended Redline</span>
												<span class="diff-badge diff-badge-added">Suggested</span>
											</div>
											<div class="diff-content font-mono">{r.redline_suggestion}</div>
										</div>
									</div>
								</div>
							</div>
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
		padding: 24px 24px 24px 28px; /* Extra left padding for organic capsule lightbar */
		background: var(--bg-glass-card);
		backdrop-filter: blur(12px);
		border: 1px solid var(--border-glass);
		border-radius: 8px;
		box-shadow: 
			0 1px 2px rgba(0, 0, 0, 0.01),
			0 10px 30px rgba(0, 0, 0, 0.03),
			inset 0 1px 0 rgba(255, 255, 255, 0.6);
		transition: border-color 220ms var(--ease-spring-gentle), 
		            transform 200ms var(--ease-spring-gentle), 
		            box-shadow 220ms var(--ease-spring-gentle);
		position: relative;
		overflow: hidden;
	}

	:global([data-theme="dark"]) .risk-card {
		box-shadow: 
			0 1px 2px rgba(0, 0, 0, 0.15),
			0 16px 40px rgba(0, 0, 0, 0.35),
			inset 0 1px 0 rgba(255, 255, 255, 0.06);
		background: var(--bg-glass-card);
		border-color: var(--border-glass);
	}

	.risk-card:hover {
		transform: translateY(-3px);
	}

	.risk-card:active {
		transform: translateY(-1px) scale(0.98);
	}

	/* Organic capsule vertical status bars */
	.risk-card::before {
		content: '';
		position: absolute;
		left: 10px;
		top: 24px;
		bottom: 24px;
		width: 4px;
		border-radius: 4px;
		transition: background 180ms ease, box-shadow 180ms ease;
	}

	/* Severity Specific Ambient Back-glow & Outlines */
	.risk-critical {
		border-color: var(--glow-critical-border);
	}
	.risk-critical::before {
		background: linear-gradient(180deg, var(--color-critical) 0%, rgba(217, 56, 58, 0.5) 100%);
		box-shadow: 0 0 10px rgba(217, 56, 58, 0.4);
	}
	.risk-critical:hover {
		border-color: rgba(217, 56, 58, 0.35);
		box-shadow: var(--shadow-lg), 0 0 20px rgba(217, 56, 58, 0.06), inset 0 1px 0 rgba(255, 255, 255, 0.6);
	}
	:global([data-theme="dark"]) .risk-critical:hover {
		box-shadow: var(--shadow-lg), 0 0 20px rgba(217, 56, 58, 0.08), inset 0 1px 0 rgba(255, 255, 255, 0.06);
	}

	.risk-high {
		border-color: var(--glow-high-border);
	}
	.risk-high::before {
		background: linear-gradient(180deg, var(--color-high) 0%, rgba(207, 34, 46, 0.5) 100%);
		box-shadow: 0 0 10px rgba(207, 34, 46, 0.3);
	}
	.risk-high:hover {
		border-color: rgba(207, 34, 46, 0.3);
		box-shadow: var(--shadow-lg), 0 0 20px rgba(207, 34, 46, 0.05), inset 0 1px 0 rgba(255, 255, 255, 0.6);
	}
	:global([data-theme="dark"]) .risk-high:hover {
		box-shadow: var(--shadow-lg), 0 0 20px rgba(207, 34, 46, 0.06), inset 0 1px 0 rgba(255, 255, 255, 0.06);
	}

	.risk-card-header {
		padding-bottom: 16px;
		border-bottom: 1px solid var(--border-subtle);
		margin-bottom: 16px;
	}

	.origin-label {
		font-size: 12px;
		font-weight: 500;
		color: var(--text-tertiary);
	}

	/* High-fidelity paper-clip doc chip */
	.doc-chip-btn {
		background: var(--bg-hover);
		border: 1px solid var(--border-subtle);
		color: var(--text-primary);
		padding: 4px 12px;
		border-radius: 6px;
		font-size: 12px;
		font-weight: 500;
		cursor: pointer;
		display: inline-flex;
		align-items: center;
		gap: 6px;
		max-width: 250px;
		transition: transform 120ms var(--ease-out), background 150ms ease, border-color 150ms ease, box-shadow 150ms ease;
		box-shadow: 0 1px 2px rgba(0, 0, 0, 0.01);
	}

	.doc-chip-btn:hover {
		background: var(--bg-active);
		border-color: var(--border-strong);
		box-shadow: 0 2px 6px rgba(0, 0, 0, 0.02);
	}

	.doc-chip-btn:active {
		transform: scale(0.97);
	}

	.clause-type-badge {
		font-size: 11px;
		font-weight: 600;
		background: var(--bg-hover);
		color: var(--text-secondary);
		border: 1px solid var(--border-subtle);
		padding: 2px 8px;
		border-radius: 4px;
		letter-spacing: 0.5px;
	}

	.risk-card-body {
		margin-bottom: 20px;
	}

	.risk-reasoning {
		font-size: 13.5px;
		font-weight: 500;
		color: var(--text-primary);
		line-height: 1.5;
		margin-bottom: 14px;
	}

	.risk-reasoning strong {
		font-weight: 600;
		color: var(--text-secondary);
	}

	/* ------------------------------------------------------------
	   Sleek Comparative Suggested Redline Drawer
	   ------------------------------------------------------------- */
	.redline-drawer {
		background: rgba(94, 106, 210, 0.015);
		border: 1px solid var(--border-subtle);
		border-radius: 8px;
		margin-bottom: 20px;
		overflow: hidden;
		transition: border-color 220ms ease, background 220ms ease, box-shadow 220ms ease;
	}

	.redline-drawer.open {
		border-color: rgba(94, 106, 210, 0.25);
		background: rgba(94, 106, 210, 0.04);
		box-shadow: inset 0 1px 2px rgba(94, 106, 210, 0.02), 0 2px 10px rgba(94, 106, 210, 0.01);
	}

	.redline-toggle {
		padding: 12px 16px;
		font-size: 12.5px;
		font-weight: 600;
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
		color: var(--text-tertiary);
	}

	.chevron-icon.rotated {
		transform: rotate(90deg);
		color: var(--text-primary);
	}

	.diff-comparison-pane {
		display: grid;
		grid-template-columns: 1fr 1fr;
		gap: 16px;
		padding: 0 16px 16px;
		background: transparent;
	}

	@media (max-width: 768px) {
		.diff-comparison-pane {
			grid-template-columns: 1fr;
			gap: 12px;
		}
	}

	.diff-column {
		border-radius: 8px;
		overflow: hidden;
		border: 1px solid var(--border-subtle);
		display: flex;
		flex-direction: column;
		background: var(--bg-sidebar);
	}

	.diff-column-original {
		background: rgba(217, 56, 58, 0.015);
		border-color: rgba(217, 56, 58, 0.12);
	}

	:global([data-theme="dark"]) .diff-column-original {
		background: rgba(255, 59, 48, 0.015);
		border-color: rgba(255, 59, 48, 0.15);
	}

	.diff-column-suggested {
		background: rgba(46, 160, 67, 0.015);
		border-color: rgba(46, 160, 67, 0.12);
	}

	:global([data-theme="dark"]) .diff-column-suggested {
		background: rgba(63, 185, 80, 0.015);
		border-color: rgba(63, 185, 80, 0.15);
	}

	.diff-header {
		padding: 10px 12px;
		border-bottom: 1px solid var(--border-subtle);
		font-size: 11px;
		font-weight: 600;
		text-transform: uppercase;
		letter-spacing: 0.5px;
		display: flex;
		align-items: center;
		justify-content: space-between;
		background: rgba(0, 0, 0, 0.01);
	}

	.diff-column-original .diff-header {
		border-bottom-color: rgba(217, 56, 58, 0.08);
		color: var(--color-critical);
	}

	.diff-column-suggested .diff-header {
		border-bottom-color: rgba(46, 160, 67, 0.08);
		color: var(--color-low);
	}

	.diff-content {
		padding: 12px;
		font-family: 'JetBrains Mono', 'Fira Code', monospace;
		font-size: 12.5px;
		line-height: 1.65;
		white-space: pre-wrap;
		word-break: break-word;
		flex-grow: 1;
		max-height: 250px;
		overflow-y: auto;
	}

	.diff-column-original .diff-content {
		color: var(--color-critical);
		text-shadow: 0 0 1px rgba(217, 56, 58, 0.15);
	}

	:global([data-theme="dark"]) .diff-column-original .diff-content {
		text-shadow: 0 0 8px rgba(255, 59, 48, 0.2);
	}

	.diff-column-suggested .diff-content {
		color: var(--color-low);
		text-shadow: 0 0 1px rgba(63, 185, 80, 0.15);
	}

	:global([data-theme="dark"]) .diff-column-suggested .diff-content {
		text-shadow: 0 0 8px rgba(63, 185, 80, 0.2);
	}

	.diff-badge {
		font-size: 9px;
		font-weight: 700;
		text-transform: uppercase;
		padding: 2px 6px;
		border-radius: 4px;
		letter-spacing: 0.5px;
	}

	.diff-badge-removed {
		background: rgba(217, 56, 58, 0.1);
		color: var(--color-critical);
	}

	.diff-badge-added {
		background: rgba(46, 160, 67, 0.1);
		color: var(--color-low);
	}

	/* Footer Action Panel */
	.risk-card-footer {
		padding-top: 16px;
		border-top: 1px solid var(--border-subtle);
	}

	.uploaded-time {
		font-size: 11px;
		font-weight: 500;
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

		.risk-card-header {
			flex-direction: column;
			align-items: flex-start;
			gap: 12px;
		}
	}
</style>
