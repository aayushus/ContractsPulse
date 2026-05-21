<script lang="ts">
	import { onMount, onDestroy } from 'svelte';
	import { goto } from '$app/navigation';
	import { toast } from '$lib/toastStore';
	import { apiFetch } from '$lib/api';

	type ContractSummary = {
		id: string;
		filename: string;
		status: string;
		metadata_json?: any;
		overall_risk?: string | null;
		created_at: string;
	};

	
	let contracts: ContractSummary[] = $state([]);
	let pollInterval: any;
	
	// Track which contracts were previously in PROCESSING state
	let processingIds = new Set<string>();

	async function fetchContracts() {
		try {
			const res = await apiFetch('/api/v1/contracts');
			if (res.ok) {
				const json = await res.json();
				
				// Check for transitions from PROCESSING -> COMPLETED
				json.contracts.forEach((c: any) => {
					if (processingIds.has(c.id) && c.status === 'COMPLETED') {
						toast.success(`${c.filename} AI analysis complete!`);
						processingIds.delete(c.id);
					} else if (processingIds.has(c.id) && c.status === 'FAILED') {
						toast.error(`${c.filename} AI analysis failed.`);
						processingIds.delete(c.id);
					} else if (c.status === 'PROCESSING') {
						processingIds.add(c.id);
					}
				});
				
				contracts = json.contracts;
			}
		} catch (err) {
			console.error("Failed to fetch contracts:", err);
		}
	}

	onMount(() => {
		fetchContracts();
		pollInterval = setInterval(fetchContracts, 3000);
	});

	onDestroy(() => {
		if (pollInterval) clearInterval(pollInterval);
	});



	// -------------------------------------------------------------
	// Executive KPI Metrics Calculation (Svelte 5 Derived Runes)
	// -------------------------------------------------------------
	let totalContracts = $derived(contracts.length);
	
	let allRiskCounts = $derived.by(() => {
		let critical = 0;
		let high = 0;
		let medium = 0;
		let low = 0;
		contracts.forEach(c => {
			if (c.status !== 'COMPLETED') return;
			const rc = c.metadata_json?.risk_counts || {};
			critical += Number(rc.CRITICAL || 0);
			high += Number(rc.HIGH || 0);
			medium += Number(rc.MEDIUM || 0);
			low += Number(rc.LOW || 0);
		});
		return { critical, high, medium, low };
	});

	let totalObligations = $derived(
		allRiskCounts.critical + allRiskCounts.high + allRiskCounts.medium + allRiskCounts.low
	);

	let portfolioHealthIndex = $derived.by(() => {
		if (totalObligations === 0) return 100;
		const rawScore = 100 - ((10 * allRiskCounts.critical + 5 * allRiskCounts.high + 2 * allRiskCounts.medium) / totalObligations) * 10;
		return Math.max(0, Math.min(100, Math.round(rawScore)));
	});

	let vulnerabilityConcentration = $derived.by(() => {
		const completed = contracts.filter(c => c.status === 'COMPLETED');
		if (completed.length === 0) return 0;
		const vulnerable = completed.filter(c => {
			const rc = c.metadata_json?.risk_counts || {};
			return Number(rc.CRITICAL || 0) > 0 || Number(rc.HIGH || 0) > 0;
		});
		return Math.round((vulnerable.length / completed.length) * 100);
	});

	let processingContracts = $derived(contracts.filter(c => c.status === 'PROCESSING'));

	let topExposureVectors = $derived.by(() => {
		const counts: Record<string, { critical: number; high: number; total: number }> = {};
		contracts.forEach(c => {
			if (c.status !== 'COMPLETED') return;
			const topRisks = c.metadata_json?.top_risks || [];
			topRisks.forEach((r: any) => {
				const type = r.clause_type || 'Other';
				if (!counts[type]) {
					counts[type] = { critical: 0, high: 0, total: 0 };
				}
				if (r.risk_level === 'CRITICAL') counts[type].critical++;
				else if (r.risk_level === 'HIGH') counts[type].high++;
				counts[type].total++;
			});
		});

		return Object.entries(counts)
			.map(([type, score]) => ({
				type,
				critical: score.critical,
				high: score.high,
				total: score.total,
				severityScore: score.critical * 10 + score.high * 5
			}))
			.sort((a, b) => b.severityScore - a.severityScore)
			.slice(0, 5);
	});

	let recentCriticalTriggers = $derived.by(() => {
		const triggers: any[] = [];
		contracts.forEach(c => {
			if (c.status !== 'COMPLETED') return;
			const topRisks = c.metadata_json?.top_risks || [];
			topRisks.forEach((r: any) => {
				if (r.risk_level === 'HIGH' || r.risk_level === 'CRITICAL') {
					triggers.push({
						contractId: c.id,
						filename: c.filename,
						clause_type: r.clause_type,
						risk_level: r.risk_level,
						risk_reasoning: r.risk_reasoning,
						text_excerpt: r.text_excerpt || r.risk_reasoning || '',
						created_at: c.created_at
					});
				}
			});
		});
		// Sort chronologically descending
		return triggers
			.sort((a, b) => new Date(b.created_at).getTime() - new Date(a.created_at).getTime())
			.slice(0, 5);
	});

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
</script>

<header class="page-header">
	<div class="page-header-inner">
		<div class="breadcrumbs">
			<span class="crumb">ContractsPulse</span>
			<span class="separator">›</span>
			<span class="crumb active">Dashboard</span>
		</div>
		
		<div class="header-content">
			<h1>Executive Risk Intelligence</h1>
		</div>
	</div>
</header>

<div class="page-content" id="dashboard-main-content">
	<!-- Vercel-style premium executive KPI row -->
	<div class="metric-row">
		<div class="metric-card panel" id="kpi-portfolio-health">
			<div class="metric-label">Portfolio Health Index</div>
			<div class="metric-value-container">
				<div class="metric-value" class:text-success={portfolioHealthIndex >= 90} class:text-warning={portfolioHealthIndex >= 70 && portfolioHealthIndex < 90} class:text-danger={portfolioHealthIndex < 70}>
					{portfolioHealthIndex}%
				</div>
				<span class="metric-trend" class:trend-up={portfolioHealthIndex >= 90} class:trend-warn={portfolioHealthIndex >= 70 && portfolioHealthIndex < 90} class:trend-down={portfolioHealthIndex < 70}>
					{#if portfolioHealthIndex >= 90}
						Healthy
					{:else}
						Action Needed
					{/if}
				</span>
			</div>
			<p class="metric-description">Risk-weighted score of obligations across repository</p>
		</div>

		<div class="metric-card panel" id="kpi-vulnerability-ratio">
			<div class="metric-label">Vulnerability Ratio</div>
			<div class="metric-value-container">
				<div class="metric-value" class:text-danger={vulnerabilityConcentration > 30} class:text-warning={vulnerabilityConcentration > 0 && vulnerabilityConcentration <= 30} class:text-success={vulnerabilityConcentration === 0}>
					{vulnerabilityConcentration}%
				</div>
				<span class="metric-trend" class:trend-down={vulnerabilityConcentration > 30} class:trend-up={vulnerabilityConcentration === 0}>
					{#if vulnerabilityConcentration > 0}
						Liable
					{:else}
						Fully Shielded
					{/if}
				</span>
			</div>
			<p class="metric-description">% of contracts with High or Critical risk factors</p>
		</div>

		<div class="metric-card panel" id="kpi-obligations-count">
			<div class="metric-label">Analyzed Obligations</div>
			<div class="metric-value-container">
				<div class="metric-value">{totalObligations}</div>
				<span class="metric-trend trend-neutral">
					{totalContracts} docs
				</span>
			</div>
			<p class="metric-description">Individual contract clauses extracted and categorized</p>
		</div>

		<div class="metric-card panel" id="kpi-queue-status">
			<div class="metric-label">Insight Velocity</div>
			<div class="metric-value-container">
				{#if processingContracts.length > 0}
					<div class="metric-value text-warning">
						{processingContracts.length} active
					</div>
					<div class="queue-mini-spinner">
						<span class="spinner spinner-sm"></span>
					</div>
				{:else}
					<div class="metric-value text-success">
						Ready
					</div>
					<span class="metric-trend trend-up">
						Idle
					</span>
				{/if}
			</div>
			<p class="metric-description">
				{#if processingContracts.length > 0}
					{@const phase = getProcessingPhase(processingContracts[0].metadata_json?.processing_step)}
					Running standard AI pipeline ({phase}...)
				{:else}
					All uploaded agreements have been processed
				{/if}
			</p>
		</div>
	</div>

	<!-- Obligation Risk Heatmap Component -->
	<div class="heatmap-section panel" id="kpi-obligation-heatmap">
		<div class="heatmap-header">
			<div>
				<h3>Obligation Risk Distribution</h3>
				<p class="text-tertiary">Real-time mapping of severity and liability categories across your portfolio</p>
			</div>
			<div class="total-badge">{totalObligations} Obligations</div>
		</div>

		{#if totalObligations > 0}
			{@const critPct = (allRiskCounts.critical / totalObligations) * 100}
			{@const highPct = (allRiskCounts.high / totalObligations) * 100}
			{@const medPct = (allRiskCounts.medium / totalObligations) * 100}
			{@const lowPct = (allRiskCounts.low / totalObligations) * 100}
			<!-- stacked bar chart -->
			<div class="stacked-bar-container">
				<div class="stacked-bar-progress">
					{#if allRiskCounts.critical > 0}
						<div class="bar-segment bar-critical" style="width: {critPct}%" title="Critical: {allRiskCounts.critical} ({Math.round(critPct)}%)"></div>
					{/if}
					{#if allRiskCounts.high > 0}
						<div class="bar-segment bar-high" style="width: {highPct}%" title="High: {allRiskCounts.high} ({Math.round(highPct)}%)"></div>
					{/if}
					{#if allRiskCounts.medium > 0}
						<div class="bar-segment bar-medium" style="width: {medPct}%" title="Medium: {allRiskCounts.medium} ({Math.round(medPct)}%)"></div>
					{/if}
					{#if allRiskCounts.low > 0}
						<div class="bar-segment bar-low" style="width: {lowPct}%" title="Low: {allRiskCounts.low} ({Math.round(lowPct)}%)"></div>
					{/if}
				</div>

				<div class="bar-legend">
					<div class="legend-item">
						<span class="legend-dot dot-critical"></span>
						<span class="legend-label">Critical</span>
						<span class="legend-count">({allRiskCounts.critical})</span>
					</div>
					<div class="legend-item">
						<span class="legend-dot dot-high"></span>
						<span class="legend-label">High</span>
						<span class="legend-count">({allRiskCounts.high})</span>
					</div>
					<div class="legend-item">
						<span class="legend-dot dot-medium"></span>
						<span class="legend-label">Medium</span>
						<span class="legend-count">({allRiskCounts.medium})</span>
					</div>
					<div class="legend-item">
						<span class="legend-dot dot-low"></span>
						<span class="legend-label">Low</span>
						<span class="legend-count">({allRiskCounts.low})</span>
					</div>
				</div>
			</div>
		{:else}
			<div class="heatmap-empty text-tertiary">
				Upload contracts or paste text to display your risk distribution heatmap.
			</div>
		{/if}
	</div>

	<!-- Analytics Split View: Clause Taxonomy & Critical Feed -->
	<div class="dashboard-grid">
		<!-- Left: Top Exposure Vectors -->
		<div class="grid-card panel" id="kpi-exposure-vectors">
			<div class="grid-card-header">
				<h3>Top Exposure Vectors</h3>
				<p class="text-tertiary font-xs">Most vulnerable agreement clause categories</p>
			</div>

			<div class="vector-list">
				{#if topExposureVectors.length > 0}
					{@const maxScore = Math.max(...topExposureVectors.map(v => v.severityScore))}
					{#each topExposureVectors as v, i}
						<div class="vector-item stagger-entry" style="--index: {i}">
							<div class="vector-row">
								<span class="vector-title">{v.type}</span>
								<div class="vector-meta">
									{#if v.critical > 0}
										<span class="mini-badge badge-critical">{v.critical} Crit</span>
									{/if}
									{#if v.high > 0}
										<span class="mini-badge badge-high">{v.high} High</span>
									{/if}
									<span class="vector-obligations-count text-tertiary">({v.total})</span>
								</div>
							</div>
							<div class="vector-track">
								<div 
									class="vector-progress" 
									class:progress-critical={v.critical > 0}
									class:progress-high={v.critical === 0 && v.high > 0}
									style="width: {Math.max(8, (v.severityScore / maxScore) * 100)}%"
								></div>
							</div>
						</div>
					{/each}
				{:else}
					<div class="empty-state text-tertiary">
						No exposures classified. Complete standard contract reviews first.
					</div>
				{/if}
			</div>
		</div>

		<!-- Right: Recent Critical Triggers Feed -->
		<div class="grid-card panel" id="kpi-critical-feed">
			<div class="grid-card-header">
				<h3>Recent Critical Triggers</h3>
				<p class="text-tertiary font-xs">Chronological alerts for high-liability findings</p>
			</div>

			<div class="triggers-feed">
				{#if recentCriticalTriggers.length > 0}
					{#each recentCriticalTriggers as trigger, i}
						<div class="trigger-card stagger-entry" style="--index: {i}">
							<div class="trigger-top">
								<div class="trigger-title-container">
									<span class="trigger-risk-pill" class:pill-critical={trigger.risk_level === 'CRITICAL'} class:pill-high={trigger.risk_level === 'HIGH'}>
										{trigger.risk_level}
									</span>
									<span class="trigger-clause-type">{trigger.clause_type}</span>
								</div>
								<span class="trigger-time">{timeAgo(trigger.created_at)}</span>
							</div>
							<div class="trigger-doc-info text-tertiary">
								<svg class="file-icon" width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/></svg>
								<span class="trigger-filename">{trigger.filename}</span>
							</div>
							<p class="trigger-snippet" title={trigger.risk_reasoning}>
								{trigger.risk_reasoning}
							</p>
							<div class="trigger-footer">
								<button class="btn-review" onclick={() => goto(`/contracts/${trigger.contractId}`)}>
									Review Redlines
									<svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><line x1="5" y1="12" x2="19" y2="12"/><polyline points="12 5 19 12 12 19"/></svg>
								</button>
							</div>
						</div>
					{/each}
				{:else}
					<div class="empty-state text-tertiary">
						No active risk alerts. Standard portfolio health remains secure.
					</div>
				{/if}
			</div>
		</div>
	</div>
</div>



<style>
	.page-content {
		padding: 32px 40px;
		max-width: 1200px;
		width: 100%;
		box-sizing: border-box;
	}

	/* Vercel-style metric grid */
	.metric-row {
		display: grid;
		grid-template-columns: repeat(4, 1fr);
		gap: 16px;
		margin-bottom: 24px;
	}

	.metric-card {
		background: var(--bg-glass-card);
		border: 1px solid var(--border-glass);
		border-radius: 8px;
		padding: 20px;
		display: flex;
		flex-direction: column;
		position: relative;
		overflow: hidden;
		transition: border-color 200ms cubic-bezier(0.23, 1, 0.32, 1), 
		            box-shadow 200ms cubic-bezier(0.23, 1, 0.32, 1),
		            transform 160ms cubic-bezier(0.23, 1, 0.32, 1);
	}

	.metric-card:hover {
		border-color: var(--border-glass-hover);
		box-shadow: var(--shadow-md);
	}

	.metric-card:active {
		transform: scale(0.975);
	}

	.metric-label {
		font-size: 11px;
		text-transform: uppercase;
		letter-spacing: 0.8px;
		color: var(--text-secondary);
		font-weight: 600;
		margin-bottom: 8px;
	}

	.metric-value-container {
		display: flex;
		align-items: baseline;
		justify-content: space-between;
		margin-bottom: 4px;
	}

	.metric-value {
		font-size: 28px;
		font-weight: 700;
		color: var(--text-primary);
		line-height: 1.1;
		font-variant-numeric: tabular-nums;
	}

	.metric-trend {
		font-size: 11px;
		font-weight: 600;
		padding: 2px 6px;
		border-radius: 4px;
	}

	.trend-up {
		background: rgba(var(--color-low-rgb), 0.1);
		color: var(--color-low);
	}

	.trend-warn {
		background: rgba(var(--color-medium-rgb), 0.1);
		color: var(--color-medium);
	}

	.trend-down {
		background: rgba(var(--color-critical-rgb), 0.1);
		color: var(--color-critical);
	}

	.trend-neutral {
		background: var(--bg-hover);
		color: var(--text-secondary);
	}

	.metric-description {
		font-size: 12px;
		color: var(--text-tertiary);
		margin: 4px 0 0 0;
		line-height: 1.4;
	}

	.queue-mini-spinner {
		display: flex;
		align-items: center;
	}

	/* stacked bar heatmap chart */
	.heatmap-section {
		padding: 24px;
		margin-bottom: 24px;
		border-radius: 8px;
		background: var(--bg-panel);
		border: 1px solid var(--border-subtle);
	}

	.heatmap-header {
		display: flex;
		justify-content: space-between;
		align-items: flex-start;
		margin-bottom: 20px;
	}

	.heatmap-header h3 {
		margin: 0 0 4px 0;
		font-size: 16px;
		font-weight: 600;
		color: var(--text-primary);
	}

	.heatmap-header p {
		margin: 0;
		font-size: 13px;
	}

	.total-badge {
		font-size: 11px;
		font-weight: 600;
		background: var(--bg-hover);
		color: var(--text-secondary);
		border: 1px solid var(--border-subtle);
		padding: 4px 8px;
		border-radius: 6px;
	}

	.stacked-bar-container {
		display: flex;
		flex-direction: column;
		gap: 16px;
	}

	.stacked-bar-progress {
		height: 10px;
		border-radius: 99px;
		overflow: hidden;
		display: flex;
		background: var(--bg-hover);
	}

	.bar-segment {
		height: 100%;
		transition: opacity 150ms ease;
		cursor: pointer;
	}

	.bar-segment:hover {
		opacity: 0.85;
	}

	.bar-critical { background: var(--color-critical); }
	.bar-high { background: var(--color-high); }
	.bar-medium { background: var(--color-medium); }
	.bar-low { background: var(--color-low); }

	.bar-legend {
		display: flex;
		flex-wrap: wrap;
		gap: 16px;
	}

	.legend-item {
		display: flex;
		align-items: center;
		gap: 6px;
		font-size: 12px;
	}

	.legend-dot {
		width: 8px;
		height: 8px;
		border-radius: 50%;
	}

	.dot-critical { background: var(--color-critical); }
	.dot-high { background: var(--color-high); }
	.dot-medium { background: var(--color-medium); }
	.dot-low { background: var(--color-low); }

	.legend-label {
		color: var(--text-primary);
		font-weight: 500;
	}

	.legend-count {
		color: var(--text-tertiary);
	}

	.heatmap-empty {
		padding: 24px;
		text-align: center;
		font-size: 13px;
	}

	/* Split grids */
	.dashboard-grid {
		display: grid;
		grid-template-columns: 1fr 1.2fr;
		gap: 24px;
	}

	.grid-card {
		padding: 24px;
		border-radius: 8px;
		background: var(--bg-panel);
		border: 1px solid var(--border-subtle);
		display: flex;
		flex-direction: column;
	}

	.grid-card-header {
		margin-bottom: 20px;
	}

	.grid-card-header h3 {
		margin: 0 0 4px 0;
		font-size: 16px;
		font-weight: 600;
		color: var(--text-primary);
	}

	.font-xs {
		font-size: 12px;
	}

	.vector-list {
		display: flex;
		flex-direction: column;
		gap: 16px;
	}

	.vector-item {
		display: flex;
		flex-direction: column;
		gap: 6px;
	}

	.vector-row {
		display: flex;
		justify-content: space-between;
		align-items: center;
	}

	.vector-title {
		font-size: 13px;
		font-weight: 500;
		color: var(--text-primary);
	}

	.vector-meta {
		display: flex;
		align-items: center;
		gap: 6px;
	}

	.mini-badge {
		font-size: 9px;
		font-weight: 700;
		padding: 1px 4px;
		border-radius: 3px;
		text-transform: uppercase;
	}

	.badge-critical {
		background: rgba(var(--color-critical-rgb), 0.1);
		color: var(--color-critical);
		border: 1px solid rgba(var(--color-critical-rgb), 0.2);
	}

	.badge-high {
		background: rgba(var(--color-high-rgb), 0.1);
		color: var(--color-high);
		border: 1px solid rgba(var(--color-high-rgb), 0.2);
	}

	.vector-obligations-count {
		font-size: 11px;
	}

	.vector-track {
		height: 4px;
		background: var(--bg-hover);
		border-radius: 99px;
		overflow: hidden;
	}

	.vector-progress {
		height: 100%;
		border-radius: 99px;
		background: var(--accent-primary);
	}

	.progress-critical { background: var(--color-critical); }
	.progress-high { background: var(--color-high); }

	/* Triggers feed */
	.triggers-feed {
		display: flex;
		flex-direction: column;
		gap: 12px;
		max-height: 500px;
		overflow-y: auto;
		padding-right: 4px;
	}

	.trigger-card {
		padding: 14px;
		border-radius: 6px;
		background: var(--bg-glass-card);
		border: 1px solid var(--border-subtle);
		display: flex;
		flex-direction: column;
		gap: 8px;
		transition: border-color 150ms ease, box-shadow 150ms ease;
	}

	.trigger-card:hover {
		border-color: var(--border-glass-hover);
		box-shadow: var(--shadow-sm);
	}

	.trigger-top {
		display: flex;
		justify-content: space-between;
		align-items: center;
	}

	.trigger-title-container {
		display: flex;
		align-items: center;
		gap: 8px;
	}

	.trigger-risk-pill {
		font-size: 9px;
		font-weight: 700;
		padding: 2px 6px;
		border-radius: 3px;
		text-transform: uppercase;
	}

	.pill-critical {
		background: var(--color-critical);
		color: var(--text-on-accent);
	}

	.pill-high {
		background: var(--color-high);
		color: var(--text-on-accent);
	}

	.trigger-clause-type {
		font-size: 12px;
		font-weight: 600;
		color: var(--text-primary);
	}

	.trigger-time {
		font-size: 11px;
		color: var(--text-tertiary);
	}

	.trigger-doc-info {
		display: flex;
		align-items: center;
		gap: 6px;
		font-size: 11px;
	}

	.file-icon {
		color: var(--text-tertiary);
	}

	.trigger-filename {
		white-space: nowrap;
		overflow: hidden;
		text-overflow: ellipsis;
		max-width: 250px;
	}

	.trigger-snippet {
		margin: 0;
		font-size: 12px;
		color: var(--text-secondary);
		line-height: 1.4;
		display: -webkit-box;
		-webkit-line-clamp: 2;
		-webkit-box-orient: vertical;
		overflow: hidden;
		text-overflow: ellipsis;
	}

	.trigger-footer {
		display: flex;
		justify-content: flex-end;
		margin-top: 4px;
	}

	.btn-review {
		background: transparent;
		border: none;
		color: var(--accent-primary);
		font-size: 11px;
		font-weight: 600;
		cursor: pointer;
		display: flex;
		align-items: center;
		gap: 4px;
		padding: 4px 8px;
		border-radius: 4px;
		transition: background 150ms ease, transform 100ms ease;
	}

	.btn-review:hover {
		background: rgba(var(--accent-primary-rgb), 0.08);
	}

	.btn-review:active {
		transform: scale(0.97);
	}

	.empty-state {
		padding: 32px;
		text-align: center;
		font-size: 13px;
	}



	/* Stagger Animations */
	.stagger-entry {
		opacity: 0;
		transform: translateY(8px);
		animation: itemIn 250ms cubic-bezier(0.23, 1, 0.32, 1) forwards;
		animation-delay: calc(var(--index, 0) * 30ms);
	}

	@keyframes itemIn {
		to {
			opacity: 1;
			transform: translateY(0);
		}
	}

	@media (max-width: 900px) {
		.metric-row {
			grid-template-columns: repeat(2, 1fr);
		}
		.dashboard-grid {
			grid-template-columns: 1fr;
		}
	}

	@media (prefers-reduced-motion: reduce) {
		.stagger-entry {
			animation: none !important;
			opacity: 1 !important;
			transform: none !important;
		}
	}
</style>
