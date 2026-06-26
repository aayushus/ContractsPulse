<script lang="ts">
	import { onMount, onDestroy } from 'svelte';
	import { goto } from '$app/navigation';
	import { toast } from '$lib/toastStore';
	import { apiFetch } from '$lib/api';
	import { createAdaptivePoller, type AdaptivePoller } from '$lib/poller';

	type ContractSummary = {
		id: string;
		filename: string;
		status: string;
		metadata_json?: any;
		overall_risk?: string | null;
		created_at: string;
	};

	
	let contracts: ContractSummary[] = $state([]);
	let loaded = $state(false);
	let poller: AdaptivePoller;
	
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
		} finally {
			loaded = true;
		}
	}

	onMount(() => {
		poller = createAdaptivePoller({
			fn: fetchContracts,
			// Poll fast only while the AI pipeline is working; otherwise back off.
			isActive: () => processingContracts.length > 0,
			activeMs: 3000,
			idleMs: 30000
		});
		poller.start();
	});

	onDestroy(() => {
		poller?.stop();
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

	let maxExposureScore = $derived(topExposureVectors.length > 0 ? Math.max(...topExposureVectors.map(v => v.severityScore)) : 0);

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

{#snippet infoTip(text: string)}
	<button class="info-tip" type="button" aria-label={text}>
		<svg aria-hidden="true" width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><line x1="12" y1="16" x2="12" y2="12"/><line x1="12" y1="8" x2="12.01" y2="8"/></svg>
		<span class="info-tip-content" aria-hidden="true">{text}</span>
	</button>
{/snippet}

<header class="page-header">
	<div class="page-header-inner">
		<div class="breadcrumbs">
			<span class="crumb">ContractsPulse</span>
			<span class="separator">›</span>
			<span class="crumb active">Dashboard</span>
		</div>
		
		<div class="header-content">
			<div class="header-title-row">
				<span class="header-icon">
					<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="3" y="3" width="18" height="18" rx="2"/><path d="M3 9h18M9 21V9"/></svg>
				</span>
				<h1>Executive Risk Intelligence</h1>
			</div>
		</div>
	</div>
</header>

<div class="page-content" id="dashboard-main-content">
	{#if !loaded}
		<!-- Loading skeletons while the first fetch resolves -->
		<div class="metric-row">
			{#each Array.from({ length: 4 }) as _, i (i)}
				<div class="metric-card panel">
					<div class="skeleton sk-line sk-label"></div>
					<div class="skeleton sk-line sk-value"></div>
					<div class="skeleton sk-line sk-desc"></div>
				</div>
			{/each}
		</div>

		<div class="heatmap-section panel">
			<div class="skeleton sk-line sk-title"></div>
			<div class="skeleton sk-bar"></div>
			<div class="sk-legend-row">
				{#each Array.from({ length: 4 }) as _, i (i)}
					<div class="skeleton sk-line sk-legend"></div>
				{/each}
			</div>
		</div>

		<div class="dashboard-grid">
			{#each Array.from({ length: 2 }) as _, i (i)}
				<div class="grid-card panel">
					<div class="skeleton sk-line sk-title"></div>
					{#each Array.from({ length: 4 }) as __, j (j)}
						<div class="skeleton sk-line sk-row"></div>
					{/each}
				</div>
			{/each}
		</div>
	{:else if totalContracts === 0}
		<!-- First-run onboarding: no contracts yet -->
		<div class="empty-hero panel">
			<div class="empty-hero-icon">
				<svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/><line x1="12" y1="18" x2="12" y2="12"/><line x1="9" y1="15" x2="15" y2="15"/></svg>
			</div>
			<h2>Bring your contracts to life</h2>
			<p>Upload your first agreement and ContractsPulse will surface portfolio health, an obligation risk heatmap, and AI-flagged critical clauses — all on this dashboard.</p>
			<button type="button" class="btn btn-primary empty-hero-cta" onclick={() => goto('/contracts')}>
				<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="17 8 12 3 7 8"/><line x1="12" y1="3" x2="12" y2="15"/></svg>
				Upload your first contract
			</button>
		</div>
	{:else}
	<!-- Vercel-style premium executive KPI row -->
	<div class="metric-row">
		<div class="metric-card panel" id="kpi-portfolio-health">
			<div class="metric-label">Portfolio Health{@render infoTip("A 0–100 score. Starts at 100 and drops based on risk-weighted obligations (Critical ×10, High ×5, Medium ×2) as a share of all obligations. Higher is better.")}</div>
			<div class="metric-value-container">
				<div class="metric-value" class:text-success={portfolioHealthIndex >= 90} class:text-warning={portfolioHealthIndex >= 70 && portfolioHealthIndex < 90} class:text-danger={portfolioHealthIndex < 70}>
					{portfolioHealthIndex}%
				</div>
				<span class="badge" class:badge-success={portfolioHealthIndex >= 90} class:badge-warning={portfolioHealthIndex >= 70 && portfolioHealthIndex < 90} class:badge-danger={portfolioHealthIndex < 70}>
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
			<div class="metric-label">Contracts at Risk{@render infoTip("The share of analyzed contracts that contain at least one High or Critical risk clause.")}</div>
			<div class="metric-value-container">
				<div class="metric-value" class:text-danger={vulnerabilityConcentration > 30} class:text-warning={vulnerabilityConcentration > 0 && vulnerabilityConcentration <= 30} class:text-success={vulnerabilityConcentration === 0}>
					{vulnerabilityConcentration}%
				</div>
				<span class="badge" class:badge-danger={vulnerabilityConcentration > 30} class:badge-warning={vulnerabilityConcentration > 0 && vulnerabilityConcentration <= 30} class:badge-success={vulnerabilityConcentration === 0}>
					{#if vulnerabilityConcentration > 0}
						At risk
					{:else}
						All protected
					{/if}
				</span>
			</div>
			<p class="metric-description">% of contracts with High or Critical risk factors</p>
		</div>

		<div class="metric-card panel" id="kpi-obligations-count">
			<div class="metric-label">Obligations Analyzed{@render infoTip("Total contract clauses extracted and risk-categorized by the AI across all uploaded documents.")}</div>
			<div class="metric-value-container">
				<div class="metric-value">{totalObligations}</div>
				<span class="badge badge-secondary">
					{totalContracts} docs
				</span>
			</div>
			<p class="metric-description">Individual contract clauses extracted and categorized</p>
		</div>

		<div class="metric-card panel" id="kpi-queue-status">
			<div class="metric-label">Analysis Status{@render infoTip("How many contracts the AI is processing right now. \"Ready\" means the queue is empty and all uploads are done.")}</div>
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
					<span class="badge badge-success">
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
				<h3>Risk Distribution</h3>
				<p class="text-tertiary">How your obligations break down by risk severity</p>
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
						<div class="bar-segment bar-critical" style="width: {critPct}%" title="Critical: {allRiskCounts.critical} ({Math.round(critPct)}%)">
							{#if critPct >= 12}<span class="bar-label">Crit {Math.round(critPct)}%</span>{:else if critPct >= 7}<span class="bar-label">{Math.round(critPct)}%</span>{/if}
						</div>
					{/if}
					{#if allRiskCounts.high > 0}
						<div class="bar-segment bar-high" style="width: {highPct}%" title="High: {allRiskCounts.high} ({Math.round(highPct)}%)">
							{#if highPct >= 12}<span class="bar-label">High {Math.round(highPct)}%</span>{:else if highPct >= 7}<span class="bar-label">{Math.round(highPct)}%</span>{/if}
						</div>
					{/if}
					{#if allRiskCounts.medium > 0}
						<div class="bar-segment bar-medium" style="width: {medPct}%" title="Medium: {allRiskCounts.medium} ({Math.round(medPct)}%)">
							{#if medPct >= 12}<span class="bar-label">Med {Math.round(medPct)}%</span>{:else if medPct >= 7}<span class="bar-label">{Math.round(medPct)}%</span>{/if}
						</div>
					{/if}
					{#if allRiskCounts.low > 0}
						<div class="bar-segment bar-low" style="width: {lowPct}%" title="Low: {allRiskCounts.low} ({Math.round(lowPct)}%)">
							{#if lowPct >= 12}<span class="bar-label">Low {Math.round(lowPct)}%</span>{:else if lowPct >= 7}<span class="bar-label">{Math.round(lowPct)}%</span>{/if}
						</div>
					{/if}
				</div>

				<div class="bar-legend">
					<div class="legend-item">
						<span class="legend-dot dot-critical"></span>
						<span class="legend-label">Critical</span>
						<span class="legend-count">{allRiskCounts.critical} · {Math.round(critPct)}%</span>
					</div>
					<div class="legend-item">
						<span class="legend-dot dot-high"></span>
						<span class="legend-label">High</span>
						<span class="legend-count">{allRiskCounts.high} · {Math.round(highPct)}%</span>
					</div>
					<div class="legend-item">
						<span class="legend-dot dot-medium"></span>
						<span class="legend-label">Medium</span>
						<span class="legend-count">{allRiskCounts.medium} · {Math.round(medPct)}%</span>
					</div>
					<div class="legend-item">
						<span class="legend-dot dot-low"></span>
						<span class="legend-label">Low</span>
						<span class="legend-count">{allRiskCounts.low} · {Math.round(lowPct)}%</span>
					</div>
				</div>
			</div>
		{:else}
			<div class="empty-state">
				<div class="empty-state-icon">
					<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="18" y1="20" x2="18" y2="10"/><line x1="12" y1="20" x2="12" y2="4"/><line x1="6" y1="20" x2="6" y2="14"/></svg>
				</div>
				<div class="empty-state-title">No obligations analyzed yet</div>
				<p class="empty-state-text">Upload a contract or paste text and your risk distribution heatmap will appear here once analysis completes.</p>
			</div>
		{/if}
	</div>

	<!-- Analytics Split View: Clause Taxonomy & Critical Feed -->
	<div class="dashboard-grid">
		<!-- Left: Top Exposure Vectors -->
		<div class="grid-card panel" id="kpi-exposure-vectors">
			<div class="grid-card-header">
				<h3>Top Risk Categories</h3>
				<p class="text-tertiary font-xs">Clause types with the most High and Critical findings</p>
			</div>

			<div class="vector-list">
				{#if topExposureVectors.length > 0}
					{#each topExposureVectors as v, i}
						<div class="vector-item stagger-entry" style="--index: {i}">
							<div class="vector-row">
								<span class="vector-title">{v.type}</span>
								<div class="vector-meta">
									{#if v.critical > 0}
										<span class="badge badge-sm badge-danger">{v.critical} Crit</span>
									{/if}
									{#if v.high > 0}
										<span class="badge badge-sm badge-danger">{v.high} High</span>
									{/if}
									<span class="vector-obligations-count text-tertiary">({v.total})</span>
								</div>
							</div>
							<div class="vector-track">
								<div 
									class="vector-progress" 
									class:progress-critical={v.critical > 0}
									class:progress-high={v.critical === 0 && v.high > 0}
									style="width: {Math.max(8, (v.severityScore / maxExposureScore) * 100)}%"
								></div>
							</div>
						</div>
					{/each}
				{:else}
					<div class="empty-state">
						<div class="empty-state-icon">
							<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M22 12h-4l-3 9L9 3l-3 9H2"/></svg>
						</div>
						<div class="empty-state-title">No exposures classified yet</div>
						<p class="empty-state-text">Clause risk categories appear here once a contract finishes analysis.</p>
					</div>
				{/if}
			</div>
		</div>

		<!-- Right: Recent Critical Triggers Feed -->
		<div class="grid-card panel" id="kpi-critical-feed">
			<div class="grid-card-header">
				<h3>Recent High-Risk Findings</h3>
				<p class="text-tertiary font-xs">Latest High and Critical issues across your contracts</p>
			</div>

			<div class="triggers-feed">
				{#if recentCriticalTriggers.length > 0}
					{#each recentCriticalTriggers as trigger, i}
						<div class="trigger-card stagger-entry" style="--index: {i}">
							<div class="trigger-top">
								<div class="trigger-title-container">
									<span class="badge badge-sm badge-danger">
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
									<svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="5" y1="12" x2="19" y2="12"/><polyline points="12 5 19 12 12 19"/></svg>
								</button>
							</div>
						</div>
					{/each}
				{:else}
					<div class="empty-state">
						<div class="empty-state-icon success">
							<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/><polyline points="9 12 11 14 15 10"/></svg>
						</div>
						<div class="empty-state-title">No critical risks found</div>
						<p class="empty-state-text">High and critical findings will surface here as your contracts are analyzed.</p>
					</div>
				{/if}
			</div>
		</div>
	</div>
	{/if}
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
	}

	.metric-label {
		display: flex;
		align-items: center;
		gap: 6px;
		font-size: var(--fs-2xs);
		text-transform: uppercase;
		letter-spacing: 0.8px;
		color: var(--text-secondary);
		font-weight: 600;
		margin-bottom: 8px;
	}

	/* Info tooltip (explains how a KPI is computed) */
	.info-tip {
		position: relative;
		display: inline-flex;
		align-items: center;
		justify-content: center;
		padding: 0;
		border: none;
		background: none;
		color: var(--text-tertiary);
		cursor: help;
		line-height: 0;
	}

	.info-tip:hover {
		color: var(--text-secondary);
	}

	.info-tip svg {
		display: block;
	}

	.info-tip-content {
		position: absolute;
		top: calc(100% + 8px);
		left: 50%;
		transform: translate(-50%, -4px);
		width: 210px;
		padding: 8px 10px;
		background: var(--bg-panel);
		border: 1px solid var(--border-strong);
		border-radius: 8px;
		box-shadow: var(--shadow-lg);
		color: var(--text-secondary);
		font-size: var(--fs-xs);
		font-weight: 400;
		line-height: 1.45;
		text-transform: none;
		letter-spacing: normal;
		text-align: left;
		opacity: 0;
		visibility: hidden;
		transition: opacity 120ms ease, transform 120ms ease, visibility 120ms;
		z-index: 50;
		pointer-events: none;
	}

	.info-tip:hover .info-tip-content,
	.info-tip:focus .info-tip-content,
	.info-tip:focus-visible .info-tip-content {
		opacity: 1;
		visibility: visible;
		transform: translate(-50%, 0);
	}

	.metric-value-container {
		display: flex;
		align-items: baseline;
		justify-content: space-between;
		margin-bottom: 4px;
	}

	.metric-value {
		font-size: var(--fs-3xl);
		font-weight: var(--fw-bold);
		color: var(--text-primary);
		line-height: var(--lh-tight);
		font-variant-numeric: tabular-nums;
	}

	.metric-description {
		font-size: var(--fs-xs);
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
		font-size: var(--fs-md);
		font-weight: 600;
		color: var(--text-primary);
	}

	.heatmap-header p {
		margin: 0;
		font-size: var(--fs-sm);
	}

	.total-badge {
		font-size: var(--fs-2xs);
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
		height: 28px;
		border-radius: 8px;
		overflow: hidden;
		display: flex;
		background: var(--bg-hover);
	}

	.bar-segment {
		height: 100%;
		display: flex;
		align-items: center;
		justify-content: center;
		min-width: 0;
		transition: opacity 150ms ease;
		cursor: default;
	}

	.bar-segment:hover {
		opacity: 0.85;
	}

	.bar-label {
		font-size: var(--fs-2xs);
		font-weight: 700;
		color: #fff;
		font-variant-numeric: tabular-nums;
		white-space: nowrap;
		padding: 0 4px;
		text-shadow: 0 1px 2px rgba(0, 0, 0, 0.45);
		pointer-events: none;
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
		font-size: var(--fs-xs);
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
		font-size: var(--fs-md);
		font-weight: 600;
		color: var(--text-primary);
	}

	.font-xs {
		font-size: var(--fs-xs);
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
		font-size: var(--fs-sm);
		font-weight: 500;
		color: var(--text-primary);
	}

	.vector-meta {
		display: flex;
		align-items: center;
		gap: 6px;
	}

	.vector-obligations-count {
		font-size: var(--fs-2xs);
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

	.trigger-clause-type {
		font-size: var(--fs-xs);
		font-weight: 600;
		color: var(--text-primary);
	}

	.trigger-time {
		font-size: var(--fs-2xs);
		color: var(--text-tertiary);
	}

	.trigger-doc-info {
		display: flex;
		align-items: center;
		gap: 6px;
		font-size: var(--fs-2xs);
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
		font-size: var(--fs-xs);
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
		font-size: var(--fs-2xs);
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
		font-size: var(--fs-sm);
		display: flex;
		flex-direction: column;
		align-items: center;
		gap: 4px;
	}

	.empty-state-icon {
		width: 40px;
		height: 40px;
		border-radius: 10px;
		display: flex;
		align-items: center;
		justify-content: center;
		background: var(--bg-hover);
		color: var(--text-tertiary);
		margin-bottom: 8px;
	}

	.empty-state-icon.success {
		background: rgba(var(--color-low-rgb), 0.12);
		color: var(--color-low);
	}

	.empty-state-title {
		font-size: var(--fs-sm);
		font-weight: 600;
		color: var(--text-secondary);
	}

	.empty-state-text {
		margin: 0;
		font-size: var(--fs-xs);
		color: var(--text-tertiary);
		max-width: 300px;
		line-height: 1.45;
	}

	/* Loading skeletons */
	.skeleton {
		background: linear-gradient(90deg, var(--bg-hover) 25%, var(--bg-active) 37%, var(--bg-hover) 63%);
		background-size: 400% 100%;
		animation: skeleton-shimmer 1.4s ease infinite;
		border-radius: 6px;
	}

	@keyframes skeleton-shimmer {
		0% { background-position: 100% 50%; }
		100% { background-position: 0 50%; }
	}

	.sk-line { height: 12px; margin-bottom: 10px; }
	.sk-label { width: 50%; height: 10px; }
	.sk-value { width: 70%; height: 28px; margin: 6px 0 10px; }
	.sk-desc { width: 90%; height: 10px; margin-bottom: 0; }
	.sk-title { width: 240px; max-width: 60%; height: 16px; margin-bottom: 18px; }
	.sk-bar { width: 100%; height: 10px; border-radius: 99px; margin-bottom: 16px; }
	.sk-legend-row { display: flex; gap: 16px; }
	.sk-legend { width: 70px; height: 12px; margin-bottom: 0; }
	.sk-row { width: 100%; height: 14px; margin-bottom: 14px; }

	/* First-run onboarding hero */
	.empty-hero {
		display: flex;
		flex-direction: column;
		align-items: center;
		text-align: center;
		padding: 56px 32px;
		gap: 8px;
	}

	.empty-hero-icon {
		width: 56px;
		height: 56px;
		border-radius: 14px;
		display: flex;
		align-items: center;
		justify-content: center;
		background: rgba(var(--accent-primary-rgb), 0.1);
		color: var(--accent-primary);
		margin-bottom: 8px;
	}

	.empty-hero h2 {
		font-size: var(--fs-lg);
		font-weight: 600;
		margin: 0;
		color: var(--text-primary);
	}

	.empty-hero p {
		font-size: var(--fs-sm);
		color: var(--text-secondary);
		max-width: 460px;
		line-height: 1.5;
		margin: 0 0 16px;
	}

	.empty-hero-cta {
		display: inline-flex;
		align-items: center;
		gap: 8px;
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
		.skeleton {
			animation: none !important;
		}
	}
</style>
