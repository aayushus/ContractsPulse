<script lang="ts">
	import { onMount, onDestroy } from 'svelte';
	import { page } from '$app/stores';
	import { goto } from '$app/navigation';
	import { apiFetch } from '$lib/api';
	import { toast } from '$lib/toastStore';
	import { premiumCard } from '$lib/actions';

	type ContractDetail = {
		id: string;
		filename: string;
		status: string;
		metadata_json?: any;
		overall_risk?: string | null;
		created_at: string;
	};

	type Clause = {
		id: string;
		clause_type: string;
		text_content: string;
		risk_level: string;
		risk_reasoning?: string | null;
		redline_suggestion?: string | null;
		risk_debug_json?: any;
	};

	const contractId = $derived($page.params.id);

	let contract = $state<ContractDetail | null>(null);
	let clauses = $state<Clause[]>([]);
	let isLoading = $state(true);
	let isClausesLoading = $state(false);
	
	// Polling and live steps for processing state
	let pollInterval: any;
	let stopwatchInterval: any;
	let now = $state(Date.now());
	let liveSteps = $state<{text: string, startTime: number, endTime: number | null}[]>([]);
	let processingStatus = $state<any>(null);

	// Tabs state
	let activeTab = $state('overview'); // 'overview' | 'risks' | 'clauses' | 'trace'

	// Filters for clauses
	let clauseSearchQuery = $state('');
	let clauseRiskFilter = $state('ALL'); // 'ALL' | 'CRITICAL' | 'HIGH' | 'MEDIUM' | 'LOW'
	let expandedClauses = $state<Record<string, boolean>>({});

	// Modals
	let deleteModalOpen = $state(false);

	// Highlight & Bi-directional sync states
	let hoveredClauseId = $state<string | null>(null);
	let selectedClauseId = $state<string | null>(null);

	function escapeHtml(text: string) {
		return text
			.replace(/&/g, '&amp;')
			.replace(/</g, '&lt;')
			.replace(/>/g, '&gt;')
			.replace(/"/g, '&quot;')
			.replace(/'/g, '&#039;');
	}

	let highlightedHtml = $derived.by(() => {
		const rawText = contract?.metadata_json?.raw_text;
		if (!rawText) return '';
		if (clauses.length === 0) return escapeHtml(rawText);

		interface Match {
			start: number;
			end: number;
			clause: Clause;
		}
		const matches: Match[] = [];

		clauses.forEach((clause) => {
			const textToFind = clause.text_content.trim();
			if (!textToFind) return;

			let index = rawText.indexOf(textToFind);
			while (index !== -1) {
				const overlaps = matches.some(m => 
					(index >= m.start && index < m.end) || 
					(index + textToFind.length > m.start && index + textToFind.length <= m.end) ||
					(m.start >= index && m.start < index + textToFind.length)
				);

				if (!overlaps) {
					matches.push({
						start: index,
						end: index + textToFind.length,
						clause
					});
				}

				index = rawText.indexOf(textToFind, index + 1);
			}
		});

		matches.sort((a, b) => a.start - b.start);

		let result = '';
		let currentIndex = 0;

		matches.forEach((match) => {
			if (match.start > currentIndex) {
				result += escapeHtml(rawText.slice(currentIndex, match.start));
			}

			const isHovered = hoveredClauseId === match.clause.id;
			const isSelected = selectedClauseId === match.clause.id;
			const activeClass = (isHovered || isSelected) ? 'active-highlight' : '';
			const riskClass = `risk-${match.clause.risk_level.toLowerCase()}`;
			
			const badgePrefixMap: Record<string, string> = {
				'LIMITATION OF LIABILITY': 'LOB',
				'INDEMNIFICATION': 'IND',
				'TERMINATION': 'TRM',
				'INTELLECTUAL PROPERTY': 'IP',
				'CONFIDENTIALITY': 'CON',
				'WARRANTY': 'WRN',
				'GOVERNING LAW': 'GOV',
				'LIQUIDATED DAMAGES': 'LIQ',
				'FORCE MAJEURE': 'FOR',
				'PAYMENT': 'PAY'
			};
			const cleanType = match.clause.clause_type.toUpperCase().trim();
			let badgeText = badgePrefixMap[cleanType] || cleanType.slice(0, 3);

			result += `<span class="clause-highlight ${riskClass} ${activeClass}" data-clause-id="${match.clause.id}" id="highlight-${match.clause.id}"><span class="highlight-badge">${escapeHtml(badgeText)}</span>${escapeHtml(match.clause.text_content)}</span>`;

			currentIndex = match.end;
		});

		if (currentIndex < rawText.length) {
			result += escapeHtml(rawText.slice(currentIndex));
		}

		return result;
	});

	function handleDocumentClick(e: MouseEvent) {
		const target = e.target as HTMLElement;
		const highlightSpan = target.closest('.clause-highlight');
		if (highlightSpan) {
			const clauseId = highlightSpan.getAttribute('data-clause-id');
			if (clauseId) {
				selectedClauseId = clauseId;
				activeTab = 'clauses';
				
				expandedClauses = {
					...expandedClauses,
					[clauseId]: true
				};

				setTimeout(() => {
					const cardEl = document.getElementById(`clause-card-${clauseId}`);
					if (cardEl) {
						cardEl.scrollIntoView({ behavior: 'smooth', block: 'center' });
					}
				}, 100);
			}
		}
	}

	function handleDocumentMouseOver(e: MouseEvent) {
		const target = e.target as HTMLElement;
		const highlightSpan = target.closest('.clause-highlight');
		if (highlightSpan) {
			hoveredClauseId = highlightSpan.getAttribute('data-clause-id');
		} else {
			hoveredClauseId = null;
		}
	}

	function handleDocumentMouseOut(e: MouseEvent) {
		hoveredClauseId = null;
	}

	function handleClauseCardClick(clauseId: string) {
		selectedClauseId = clauseId;
		toggleClauseExpand(clauseId);
		syncScrollToHighlight(clauseId);
	}

	function syncScrollToHighlight(clauseId: string) {
		setTimeout(() => {
			const highlightEl = document.getElementById(`highlight-${clauseId}`);
			if (highlightEl) {
				highlightEl.scrollIntoView({ behavior: 'smooth', block: 'center' });
			}
		}, 80);
	}

	// Reactively initialize live processing trace steps
	$effect(() => {
		if (contract && contract.status === 'PROCESSING') {
			const step = contract.metadata_json?.processing_step;
			if (step) {
				const lastStep = liveSteps[liveSteps.length - 1];
				if (!lastStep || lastStep.text !== step) {
					if (lastStep && !lastStep.endTime) {
						lastStep.endTime = Date.now();
					}
					liveSteps = [...liveSteps, { text: step, startTime: Date.now(), endTime: null }];
				}
			}
		} else if (contract && (contract.status === 'COMPLETED' || contract.status === 'FAILED')) {
			const lastStep = liveSteps[liveSteps.length - 1];
			if (lastStep && !lastStep.endTime) {
				lastStep.endTime = Date.now();
			}
		}
	});

	// Dynamic search and severity filtering for clauses
	let filteredClauses = $derived(
		clauses.filter((c) => {
			const matchesSearch = 
				c.clause_type.toLowerCase().includes(clauseSearchQuery.toLowerCase()) ||
				c.text_content.toLowerCase().includes(clauseSearchQuery.toLowerCase()) ||
				(c.risk_reasoning || '').toLowerCase().includes(clauseSearchQuery.toLowerCase());
			
			const matchesRisk = 
				clauseRiskFilter === 'ALL' || 
				c.risk_level.toUpperCase() === clauseRiskFilter;
			
			return matchesSearch && matchesRisk;
		})
	);

	function formatStopwatch(ms: number) {
		if (!ms || ms < 0) return "0.0s";
		return (ms / 1000).toFixed(1) + "s";
	}

	function formatEta(seconds: number | null | undefined) {
		if (seconds === null || seconds === undefined) return '--';
		if (seconds <= 1) return '< 1s';
		const s = Math.max(0, Math.floor(seconds));
		const m = Math.floor(s / 60);
		const r = s % 60;
		if (m <= 0) return `~${r}s`;
		return `~${m}m ${r}s`;
	}

	function getProcessingPhase(step: string | undefined | null) {
		if (!step) return "Initializing";
		const s = step.toLowerCase();
		if (s.includes('segment')) return "Planning";
		if (s.includes('analyz')) return "Thinking";
		if (s.includes('sav')) return "Executing";
		return "Processing";
	}

	async function fetchContractStatus() {
		try {
			const res = await apiFetch(`/api/v1/contracts/${contractId}/status`);
			if (!res.ok) return;
			processingStatus = await res.json();
		} catch {
			// non-fatal
		}
	}

	async function fetchContractDetails(silent = false) {
		if (!silent) isLoading = true;
		try {
			const res = await apiFetch(`/api/v1/contracts/${contractId}`);
			if (res.ok) {
				const data = await res.json();
				contract = data.contract;

				if (contract) {
					if (contract.status === 'PROCESSING') {
						fetchContractStatus();
						if (activeTab === 'overview') {
							// If processing, default tab is Overview to see trace
							activeTab = 'overview';
						}
					} else {
						processingStatus = null;
						if (clauses.length === 0 && !isClausesLoading) {
							fetchClauses();
						}
					}
				}
			} else if (res.status === 404) {
				toast.error('Contract not found.');
				goto('/contracts');
			}
		} catch (err) {
			console.error('Error loading contract:', err);
			toast.error('Failed to load contract details.');
		} finally {
			if (!silent) isLoading = false;
		}
	}

	async function fetchClauses() {
		isClausesLoading = true;
		try {
			const res = await apiFetch(`/api/v1/contracts/${contractId}/clauses`);
			if (res.ok) {
				const data = await res.json();
				clauses = data.clauses || [];
			}
		} catch (error) {
			console.error('Failed to fetch clauses:', error);
			toast.error('Failed to load contract details.');
		} finally {
			isClausesLoading = false;
		}
	}

	async function handleReprocess() {
		const loadingToastId = toast.loading('Restarting AI pipeline...');
		try {
			const response = await apiFetch(`/api/v1/contracts/${contractId}/reprocess`, {
				method: 'POST'
			});
			if (response.ok) {
				toast.dismiss(loadingToastId);
				toast.success('Reprocessing started.');
				fetchContractDetails();
			} else {
				throw new Error('Reprocess failed');
			}
		} catch (error) {
			toast.dismiss(loadingToastId);
			toast.error('Failed to reprocess contract.');
		}
	}

	async function handleDelete() {
		deleteModalOpen = false;
		const loadingToastId = toast.loading('Deleting contract...');
		try {
			const response = await apiFetch(`/api/v1/contracts/${contractId}`, {
				method: 'DELETE'
			});
			if (response.ok) {
				toast.dismiss(loadingToastId);
				toast.success('Contract deleted.');
				goto('/contracts');
			} else {
				throw new Error('Delete failed');
			}
		} catch (error) {
			toast.dismiss(loadingToastId);
			toast.error('Failed to delete contract.');
		}
	}

	async function copyClauseRedline(clause: Clause) {
		if (!clause?.redline_suggestion) return;
		const payload =
			`${clause.clause_type ? `Clause: ${clause.clause_type}\n\n` : ''}` +
			`Original:\n${clause.text_content || ''}\n\n` +
			`Suggested replacement:\n${clause.redline_suggestion}\n\n` +
			`Rationale:\n${clause.risk_reasoning || ''}\n`;
		try {
			await navigator.clipboard.writeText(payload);
			toast.success('Redline copied to clipboard.');
		} catch (e) {
			try {
				const ta = document.createElement('textarea');
				ta.value = payload;
				ta.style.position = 'fixed';
				ta.style.left = '-9999px';
				document.body.appendChild(ta);
				ta.focus();
				ta.select();
				document.execCommand('copy');
				document.body.removeChild(ta);
				toast.success('Redline copied to clipboard.');
			} catch {
				toast.error('Failed to copy. Select text and copy manually.');
			}
		}
	}

	function toggleClauseExpand(clauseId: string) {
		expandedClauses = {
			...expandedClauses,
			[clauseId]: !expandedClauses[clauseId]
		};
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
		fetchContractDetails();
		
		// Parse query parameters for deep linking
		const params = new URL(window.location.href).searchParams;
		const tabParam = params.get('tab');
		if (tabParam) activeTab = tabParam;
		const searchParam = params.get('search');
		if (searchParam) clauseSearchQuery = searchParam;
		const riskParam = params.get('risk');
		if (riskParam) clauseRiskFilter = riskParam.toUpperCase();
		
		// Auto-poll if it's processing
		pollInterval = setInterval(() => {
			if (contract && contract.status === 'PROCESSING') {
				fetchContractDetails(true);
			}
		}, 3000);

		stopwatchInterval = setInterval(() => {
			now = Date.now();
		}, 100);
	});

	onDestroy(() => {
		if (pollInterval) clearInterval(pollInterval);
		if (stopwatchInterval) clearInterval(stopwatchInterval);
	});
</script>

{#if isLoading}
	<div class="cockpit-loading">
		<span class="spinner spinner-lg"></span>
		<p>Opening cockpit workspace...</p>
	</div>
{:else if contract}
	<div class="cockpit-header">
		<div class="breadcrumbs">
			<a href="/contracts" class="crumb crumb-link">All Contracts</a>
			<span class="separator">/</span>
			<span class="crumb active">{contract.filename}</span>
		</div>
		<div class="cockpit-actions">
			{#if contract.status === 'FAILED' || contract.status === 'COMPLETED'}
				<button class="btn btn-secondary btn-compact" onclick={handleReprocess} title="Reprocess Contract">
					<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M3 12a9 9 0 1 0 9-9 9.75 9.75 0 0 0-6.74 2.74L3 8"/><path d="M3 3v5h5"/></svg>
					Reprocess
				</button>
			{/if}
			<button class="btn btn-secondary btn-danger-action btn-compact" onclick={() => deleteModalOpen = true} title="Delete Contract">
				<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M3 6h18"></path><path d="M19 6v14c0 1-1 2-2 2H7c-1 0-2-1-2-2V6"></path><path d="M8 6V4c0-1 1-2 2-2h4c1 0 2 1 2 2v2"></path></svg>
				Delete
			</button>
		</div>
	</div>

	<div class="cockpit-wrapper">
		<!-- Left Panel: Raw Document OCR Text -->
		<div class="document-panel">
			<div class="pane-header">
				<div class="pane-title flex-row">
					<svg class="file-icon" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/><line x1="16" y1="13" x2="8" y2="13"/><line x1="16" y1="17" x2="8" y2="17"/><polyline points="10 9 9 9 8 9"/></svg>
					<span>Document OCR Text</span>
				</div>
				<div class="document-meta-info text-tertiary">
					{#if contract.metadata_json?.raw_text}
						{contract.metadata_json.raw_text.length.toLocaleString()} characters
					{:else}
						OCR Loading...
					{/if}
				</div>
			</div>
			
			<div class="document-body" id="document-body-container">
				<!-- svelte-ignore a11y_click_events_have_key_events -->
				<!-- svelte-ignore a11y_no_static_element_interactions -->
				<div class="document-paper" onclick={handleDocumentClick} onmouseover={handleDocumentMouseOver} onmouseout={handleDocumentMouseOut}>
					{#if contract.metadata_json?.raw_text}
						{@html highlightedHtml}
					{:else if contract.status === 'PROCESSING'}
						<div class="document-placeholder">
							<span class="spinner spinner-md"></span>
							<p>Raw text is being extracted by AI pipeline...</p>
						</div>
					{:else}
						<div class="document-placeholder">
							<p class="text-tertiary">Raw contract text could not be loaded.</p>
						</div>
					{/if}
				</div>
			</div>
		</div>

		<!-- Right Panel: AI Analysis panel -->
		<div class="analysis-panel">
			<!-- Sleek Tabs Navigation -->
			<div class="analysis-tabs">
				<button class="tab-btn" class:active={activeTab === 'overview'} onclick={() => activeTab = 'overview'}>
					<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="3" y="3" width="18" height="18" rx="2"/><path d="M3 9h18M9 21V9"/></svg>
					Overview
				</button>
				{#if contract.status === 'COMPLETED'}
					<button class="tab-btn" class:active={activeTab === 'risks'} onclick={() => activeTab = 'risks'}>
						<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"/><line x1="12" y1="9" x2="12" y2="13"/><line x1="12" y1="17" x2="12.01" y2="17"/></svg>
						Key Risks
					</button>
					<button class="tab-btn" class:active={activeTab === 'clauses'} onclick={() => activeTab = 'clauses'}>
						<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="8" y1="6" x2="21" y2="6"/><line x1="8" y1="12" x2="21" y2="12"/><line x1="8" y1="18" x2="21" y2="18"/><line x1="3" y1="6" x2="3.01" y2="6"/><line x1="3" y1="12" x2="3.01" y2="12"/><line x1="3" y1="18" x2="3.01" y2="18"/></svg>
						Smart Clauses ({clauses.length})
					</button>
				{/if}
				{#if contract.status === 'PROCESSING'}
					<button class="tab-btn" class:active={activeTab === 'trace'} onclick={() => activeTab = 'trace'}>
						<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M22 12h-4l-3 9L9 3l-3 9H2"/></svg>
						System Trace
					</button>
				{/if}
			</div>

			<!-- Tab Content Viewport -->
			<div class="analysis-viewport">
				<!-- OVERVIEW TAB -->
				{#if activeTab === 'overview'}
					<div class="tab-content flex-col">
						<div class="overview-section">
							<h3 class="subsection-title">Executive Summary</h3>
							<div class="metadata-grid">
								<div class="meta-card bg-panel-glow" use:premiumCard>
									<span class="mc-label">Filename</span>
									<span class="mc-value truncate" title={contract.filename}>{contract.filename}</span>
								</div>
								<div class="meta-card bg-panel-glow" use:premiumCard>
									<span class="mc-label">Analysis Status</span>
									<div class="flex-row gap-6">
										{#if contract.status === 'COMPLETED'}
											<span class="badge badge-success">Completed</span>
										{:else if contract.status === 'FAILED'}
											<span class="badge badge-danger">Failed</span>
										{:else}
											{@const phase = getProcessingPhase(contract.metadata_json?.processing_step)}
											<span class="badge badge-warning spinner-badge">
												<span class="spinner spinner-sm"></span>
												{phase}
											</span>
										{/if}
									</div>
								</div>
								<div class="meta-card bg-panel-glow" use:premiumCard>
									<span class="mc-label">Uploaded</span>
									<span class="mc-value">{timeAgo(contract.created_at)}</span>
								</div>
								<div class="meta-card bg-panel-glow" use:premiumCard>
									<span class="mc-label">Risk Rating</span>
									{#if contract.status === 'COMPLETED' && contract.overall_risk}
										<div class="flex-row gap-8">
											<span class="risk-indicator risk-{contract.overall_risk.toLowerCase()}"></span>
											<span class="mc-value risk-label font-bold text-{contract.overall_risk.toLowerCase()}">{contract.overall_risk.toLowerCase()}</span>
										</div>
									{:else}
										<span class="mc-value text-tertiary">--</span>
									{/if}
								</div>
							</div>
						</div>

						{#if contract.status === 'COMPLETED'}
							<div class="overview-section">
								<h3 class="subsection-title">Risk Severity Matrix</h3>
								<div class="risk-matrix">
									<div class="matrix-item bg-critical-glow" use:premiumCard={{ color: 'var(--color-critical)' }}>
										<span class="matrix-count text-critical">{contract.metadata_json?.risk_counts?.CRITICAL || 0}</span>
										<span class="matrix-label">Critical</span>
									</div>
									<div class="matrix-item bg-high-glow" use:premiumCard={{ color: 'var(--color-high)' }}>
										<span class="matrix-count text-high">{contract.metadata_json?.risk_counts?.HIGH || 0}</span>
										<span class="matrix-label">High</span>
									</div>
									<div class="matrix-item bg-medium-glow" use:premiumCard={{ color: 'var(--color-medium)' }}>
										<span class="matrix-count text-medium">{contract.metadata_json?.risk_counts?.MEDIUM || 0}</span>
										<span class="matrix-label">Medium</span>
									</div>
									<div class="matrix-item bg-low-glow" use:premiumCard={{ color: 'var(--color-low)' }}>
										<span class="matrix-count text-low">{contract.metadata_json?.risk_counts?.LOW || 0}</span>
										<span class="matrix-label">Low</span>
									</div>
								</div>
							</div>

							{#if contract.metadata_json?.routing_summary}
								<div class="overview-section">
									<h3 class="subsection-title">AI Routing Recommendation</h3>
									<div class="routing-card bg-panel-glow">
										<p>{contract.metadata_json.routing_summary}</p>
									</div>
								</div>
							{/if}
						{/if}

						{#if contract.status === 'PROCESSING'}
							<div class="overview-section">
								<h3 class="subsection-title">Pipeline Progress</h3>
								{#if processingStatus}
									<div class="processing-stats bg-panel-glow">
										<div class="ps-row">
											<span class="ps-label">Stage</span>
											<span class="ps-value">{processingStatus.stage?.label || 'Processing'} ({processingStatus.stage?.index || 0}/{processingStatus.stage?.count || 3})</span>
										</div>
										<div class="ps-row">
											<span class="ps-label">Estimated ETA</span>
											<span class="ps-value font-mono">{formatEta(processingStatus.eta_seconds)}</span>
										</div>
										{#if processingStatus.progress}
											<div class="ps-row">
												<span class="ps-label">Processed Clauses</span>
												<span class="ps-value">{processingStatus.progress.current} of {processingStatus.progress.total}</span>
											</div>
											<div class="progress-bar-container">
												<div class="progress-bar-fill" style="width: {(processingStatus.progress.current / processingStatus.progress.total) * 100}%"></div>
											</div>
										{/if}
									</div>
								{/if}

								<div class="trace-timeline margin-top-16">
									{#each liveSteps as step, i}
										<div class="timeline-step">
											<div class="timeline-icon {step.endTime ? 'done' : 'active'}">
												{#if step.endTime}
													<svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3"><polyline points="20 6 9 17 4 12"></polyline></svg>
												{:else}
													<span class="spinner" style="width: 10px; height: 10px; border-width: 2px;"></span>
												{/if}
											</div>
											<div class="timeline-content">
												<div class="timeline-text">{step.text}</div>
												<div class="timeline-time {step.endTime ? 'text-tertiary' : 'time-active'}">
													{#if step.endTime}
														{formatStopwatch(step.endTime - step.startTime)}
													{:else}
														{formatStopwatch(now - step.startTime)}
													{/if}
												</div>
											</div>
										</div>
									{/each}
								</div>
							</div>
						{/if}
					</div>
				{/if}

				<!-- KEY RISKS TAB -->
				{#if activeTab === 'risks'}
					<div class="tab-content">
						{#if !contract.metadata_json?.top_risks || contract.metadata_json.top_risks.length === 0}
							<div class="empty-tab-state">
								<p class="text-tertiary">No critical or high risks detected in this contract.</p>
							</div>
						{:else}
							<div class="risks-list">
								{#each contract.metadata_json.top_risks as r}
									<div class="risk-glow-card risk-{(r.risk_level || 'LOW').toLowerCase()}" use:premiumCard={{ color: 'var(--color-' + (r.risk_level || 'LOW').toLowerCase() + ')' }}>
										<div class="risk-glow-header">
											<span class="risk-glow-type">{r.clause_type || 'Clause'}</span>
											<span class="badge badge-{r.risk_level === 'CRITICAL' || r.risk_level === 'HIGH' ? 'danger' : r.risk_level === 'MEDIUM' ? 'warning' : 'success'}">{r.risk_level}</span>
										</div>
										
										{#if r.auto_renewal}
											<div class="auto-renewal-badge">
												<svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21.5 2v6h-6M21.34 15.57a10 10 0 1 1-.57-8.38l5.67-5.67"/></svg>
												<span>
													<strong>Auto-renewal detected:</strong> 
													{#if r.auto_renewal.opt_out_days_before_renewal}
														Must opt-out {r.auto_renewal.opt_out_days_before_renewal} days prior.
													{:else}
														Verify renewal terms.
													{/if}
												</span>
											</div>
										{/if}

										<div class="risk-glow-reasoning">
											<strong>Why it matters:</strong> {r.risk_reasoning || 'Flagged clause requires strict visual inspection.'}
										</div>

										{#if r.text_excerpt}
											<div class="risk-glow-excerpt">
												"{r.text_excerpt}"
											</div>
										{/if}
									</div>
								{/each}
							</div>
						{/if}
					</div>
				{/if}

				<!-- SMART CLAUSES TAB -->
				{#if activeTab === 'clauses'}
					<div class="tab-content flex-col scroll-container">
						<!-- Filters Panel -->
						<div class="clauses-filters bg-panel-glow">
							<div class="search-input-wrapper">
								<svg class="search-icon" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/></svg>
								<input 
									type="text" 
									placeholder="Search clauses by keyword..." 
									bind:value={clauseSearchQuery}
									class="clause-search-bar"
								/>
							</div>

							<div class="filter-pills flex-row gap-6">
								<button class="filter-pill" class:active={clauseRiskFilter === 'ALL'} onclick={() => clauseRiskFilter = 'ALL'}>
									All
								</button>
								<button class="filter-pill filter-pill-critical" class:active={clauseRiskFilter === 'CRITICAL'} onclick={() => clauseRiskFilter = 'CRITICAL'}>
									Critical
								</button>
								<button class="filter-pill filter-pill-high" class:active={clauseRiskFilter === 'HIGH'} onclick={() => clauseRiskFilter = 'HIGH'}>
									High
								</button>
								<button class="filter-pill filter-pill-medium" class:active={clauseRiskFilter === 'MEDIUM'} onclick={() => clauseRiskFilter = 'MEDIUM'}>
									Medium
								</button>
								<button class="filter-pill filter-pill-low" class:active={clauseRiskFilter === 'LOW'} onclick={() => clauseRiskFilter = 'LOW'}>
									Low
								</button>
							</div>
						</div>

						<!-- Clause List -->
						{#if isClausesLoading}
							<div class="clauses-loading">
								<span class="spinner spinner-md"></span>
								<p>Loading clauses...</p>
							</div>
						{:else if filteredClauses.length === 0}
							<div class="empty-tab-state">
								<p class="text-tertiary">No clauses match the filter parameters.</p>
							</div>
						{:else}
							<div class="clauses-list">
								{#each filteredClauses as clause (clause.id)}
									{@const isExpanded = expandedClauses[clause.id]}
									<!-- svelte-ignore a11y_click_events_have_key_events -->
									<!-- svelte-ignore a11y_no_static_element_interactions -->
									<div 
										id="clause-card-{clause.id}"
										class="clause-interactive-card risk-{clause.risk_level.toLowerCase()} {isExpanded ? 'expanded' : ''} {selectedClauseId === clause.id || hoveredClauseId === clause.id ? 'active-card' : ''}" 
										use:premiumCard={{ color: 'var(--color-' + clause.risk_level.toLowerCase() + ')' }}
										onmouseenter={() => { hoveredClauseId = clause.id; }}
										onmouseleave={() => { if (hoveredClauseId === clause.id) hoveredClauseId = null; }}
										onclick={() => handleClauseCardClick(clause.id)}
									>
										<div class="clause-interactive-header">
											<div class="flex-row gap-8">
												<svg class="chevron-icon" class:rotated={isExpanded} width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="9 18 15 12 9 6"/></svg>
												<span class="clause-type font-semibold">{clause.clause_type}</span>
											</div>
											<span class="badge badge-{clause.risk_level === 'CRITICAL' || clause.risk_level === 'HIGH' ? 'danger' : clause.risk_level === 'MEDIUM' ? 'warning' : 'success'}">
												{clause.risk_level}
											</span>
										</div>

										<div class="clause-interactive-excerpt font-mono">
											{isExpanded ? clause.text_content : (clause.text_content.slice(0, 140) + (clause.text_content.length > 140 ? '...' : ''))}
										</div>

										{#if isExpanded}
											<div class="clause-expanded-section" onclick={(e) => e.stopPropagation()}>
												<div class="clause-reasoning">
													<strong>Rationale:</strong> {clause.risk_reasoning || 'Flagged for strict visual audit.'}
												</div>

												{#if clause.redline_suggestion}
													<div class="clause-redline">
														<div class="clause-redline-head flex-between">
															<strong>Suggested Redline</strong>
															<button class="btn btn-secondary btn-compact text-xs" onclick={() => copyClauseRedline(clause)}>
																Copy Redline
															</button>
														</div>
														<pre class="clause-redline-block">{clause.redline_suggestion}</pre>
													</div>
												{/if}

												{#if clause.risk_debug_json && Object.keys(clause.risk_debug_json).length}
													<details class="clause-tech" onclick={(e) => e.stopPropagation()}>
														<summary class="font-medium text-xs text-secondary cursor-pointer">Technical Details</summary>
														<div class="tech-grid">
															<div class="tech-row">
																<span class="tech-label">Model</span>
																<span class="tech-value font-mono">{clause.risk_debug_json.model || '--'}</span>
															</div>
															<div class="tech-row">
																<span class="tech-label">Latency</span>
																<span class="tech-value font-mono">{clause.risk_debug_json.latency_ms ?? '--'}ms</span>
															</div>
															<div class="tech-row">
																<span class="tech-label">Composite Score</span>
																<span class="tech-value font-mono">{clause.risk_debug_json.composite_score ?? '--'}</span>
															</div>
															<div class="tech-row">
																<span class="tech-label">Confidence</span>
																<span class="tech-value font-mono">{clause.risk_debug_json.confidence ?? '--'}</span>
															</div>
														</div>
													</details>
												{/if}
											</div>
										{/if}
									</div>
								{/each}
							</div>
						{/if}
					</div>
				{/if}

				<!-- SYSTEM TRACE TAB (only for PROCESSING status) -->
				{#if activeTab === 'trace' && contract.status === 'PROCESSING'}
					<div class="tab-content flex-col">
						<div class="overview-section">
							<h3 class="subsection-title">Live Pipeline Activity</h3>
							{#if processingStatus}
								<div class="processing-stats bg-panel-glow">
									<div class="ps-row">
										<span class="ps-label">Active Step</span>
										<span class="ps-value">{contract.metadata_json?.processing_step || 'Processing...'}</span>
									</div>
									<div class="ps-row">
										<span class="ps-label">Stage Index</span>
										<span class="ps-value">{processingStatus.stage?.label || 'Processing'} ({processingStatus.stage?.index || 0}/{processingStatus.stage?.count || 3})</span>
									</div>
									<div class="ps-row">
										<span class="ps-label">Pipeline ETA</span>
										<span class="ps-value font-mono">{formatEta(processingStatus.eta_seconds)}</span>
									</div>
								</div>
							{/if}

							<div class="trace-timeline margin-top-24">
								{#each liveSteps as step, i}
									<div class="timeline-step">
										<div class="timeline-icon {step.endTime ? 'done' : 'active'}">
											{#if step.endTime}
												<svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3"><polyline points="20 6 9 17 4 12"></polyline></svg>
											{:else}
												<span class="spinner" style="width: 10px; height: 10px; border-width: 2px;"></span>
											{/if}
										</div>
										<div class="timeline-content">
											<div class="timeline-text">{step.text}</div>
											<div class="timeline-time {step.endTime ? 'text-tertiary' : 'time-active'}">
												{#if step.endTime}
													{formatStopwatch(step.endTime - step.startTime)}
												{:else}
													{formatStopwatch(now - step.startTime)}
												{/if}
											</div>
										</div>
									</div>
								{/each}
							</div>
						</div>
					</div>
				{/if}
			</div>
		</div>
	</div>
{/if}

<!-- Delete Confirmation Modal -->
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
				<p>Are you sure you want to completely delete this contract? This will remove all parsed text segments, AI evaluations, and historical traces. This action is final.</p>
			</div>
			<div class="modal-footer flex-end gap-12">
				<button class="btn btn-secondary" onclick={() => deleteModalOpen = false}>Cancel</button>
				<button class="btn btn-danger" onclick={handleDelete}>Delete Permanently</button>
			</div>
		</div>
	</div>
{/if}

<style>
	/* Loading Screen */
	.cockpit-loading {
		display: flex;
		flex-direction: column;
		align-items: center;
		justify-content: center;
		flex: 1;
		gap: 16px;
		background: var(--bg-app);
		color: var(--text-secondary);
		height: 100vh;
	}

	/* Compact Header */
	.cockpit-header {
		display: flex;
		align-items: center;
		justify-content: space-between;
		padding: 16px 24px;
		background: var(--bg-sidebar);
		border-bottom: 1px solid var(--border-subtle);
		height: 68px;
		flex-shrink: 0;
	}

	.crumb-link {
		color: var(--text-tertiary);
		text-decoration: none;
		transition: color 150ms ease;
	}

	.crumb-link:hover {
		color: var(--text-secondary);
	}

	.cockpit-actions {
		display: flex;
		align-items: center;
		gap: 8px;
	}

	.btn-compact {
		height: 28px;
		padding: 0 10px;
		font-size: 12px;
	}

	.btn-danger-action {
		background: rgba(248, 81, 73, 0.08);
		border-color: rgba(248, 81, 73, 0.2);
		color: #f85149;
	}

	.btn-danger-action:hover {
		background: rgba(248, 81, 73, 0.15);
		border-color: rgba(248, 81, 73, 0.35);
	}

	/* Main Split Screen Wrapper */
	.cockpit-wrapper {
		display: grid;
		grid-template-columns: 50% 50%;
		height: calc(100vh - 68px);
		background: var(--bg-app);
		overflow: hidden;
	}

	@media (max-width: 1024px) {
		.cockpit-wrapper {
			grid-template-columns: 1fr;
			height: auto;
			overflow-y: auto;
		}
		
		.document-panel, .analysis-panel {
			height: 600px !important;
		}
	}

	/* Left Panel: OCR Document */
	.document-panel {
		display: flex;
		flex-direction: column;
		border-right: 1px solid var(--border-subtle);
		height: 100%;
		overflow: hidden;
		background: var(--bg-app);
	}

	.pane-header {
		display: flex;
		align-items: center;
		justify-content: space-between;
		padding: 16px 20px;
		background: var(--bg-sidebar);
		border-bottom: 1px solid var(--border-subtle);
		height: 48px;
		flex-shrink: 0;
	}

	.pane-title {
		font-size: 13px;
		font-weight: 600;
		color: var(--text-primary);
		gap: 8px;
	}

	.document-meta-info {
		font-size: 12px;
	}

	.document-body {
		flex: 1;
		overflow-y: auto;
		padding: 24px;
		display: flex;
		justify-content: center;
		background: var(--bg-app);
	}

	.document-paper {
		width: 100%;
		max-width: 800px;
		background: var(--bg-panel);
		border: 1px solid var(--border-subtle);
		border-radius: 8px;
		padding: 32px;
		font-family: 'JetBrains Mono', 'SF Mono', Consolas, monospace;
		font-size: 13px;
		line-height: 1.7;
		color: var(--text-primary);
		white-space: pre-wrap;
		word-break: break-word;
		box-shadow: var(--shadow-premium);
		height: fit-content;
		min-height: 100%;
	}

	.document-placeholder {
		display: flex;
		flex-direction: column;
		align-items: center;
		justify-content: center;
		height: 200px;
		color: var(--text-tertiary);
		gap: 12px;
		width: 100%;
	}

	/* Right Panel: AI Analysis Workspace */
	.analysis-panel {
		display: flex;
		flex-direction: column;
		height: 100%;
		overflow: hidden;
		background: var(--bg-app);
	}

	.analysis-tabs {
		display: flex;
		padding: 8px 16px;
		background: var(--bg-sidebar);
		border-bottom: 1px solid var(--border-subtle);
		gap: 6px;
		height: 48px;
		flex-shrink: 0;
		align-items: center;
	}

	.tab-btn {
		background: transparent;
		border: 1px solid transparent;
		color: var(--text-secondary);
		padding: 4px 10px;
		border-radius: 4px;
		font-size: 12px;
		font-weight: 500;
		cursor: pointer;
		transition: all 120ms var(--ease-out);
		display: flex;
		align-items: center;
		gap: 6px;
		user-select: none;
	}

	.tab-btn:hover {
		color: var(--text-primary);
		background: var(--bg-hover);
	}

	.tab-btn.active {
		color: var(--text-primary);
		background: var(--bg-active);
		border-color: var(--border-strong);
	}

	.tab-btn:active {
		transform: scale(0.96);
	}

	.analysis-viewport {
		flex: 1;
		overflow-y: auto;
		background: var(--bg-app);
	}

	.tab-content {
		padding: 24px;
		display: flex;
		flex-direction: column;
		gap: 20px;
	}

	.flex-col {
		display: flex;
		flex-direction: column;
	}

	.gap-6 { gap: 6px; }
	.gap-8 { gap: 8px; }
	.gap-12 { gap: 12px; }
	.margin-top-16 { margin-top: 16px; }
	.margin-top-24 { margin-top: 24px; }
	.font-semibold { font-weight: 600; }
	.font-medium { font-weight: 500; }
	.font-bold { font-weight: 700; }
	.font-mono { font-family: monospace; }
	.truncate { white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }

	/* Overview tab styling */
	.subsection-title {
		font-size: 13px;
		font-weight: 600;
		text-transform: uppercase;
		letter-spacing: 0.5px;
		color: var(--text-secondary);
		margin-bottom: 12px;
	}

	.overview-section {
		display: flex;
		flex-direction: column;
	}

	.metadata-grid {
		display: grid;
		grid-template-columns: repeat(2, 1fr);
		gap: 12px;
	}

	.meta-card {
		padding: 14px;
		border-radius: 6px;
		border: 1px solid var(--border-subtle);
		display: flex;
		flex-direction: column;
		gap: 6px;
		min-width: 0;
	}

	.bg-panel-glow {
		background: var(--bg-panel);
		transition: border-color 150ms ease;
	}
	.bg-panel-glow:hover {
		border-color: var(--border-strong);
	}

	.mc-label {
		font-size: 11px;
		color: var(--text-tertiary);
		text-transform: uppercase;
		font-weight: 500;
	}

	.mc-value {
		font-size: 13px;
		color: var(--text-primary);
		font-weight: 500;
	}

	.spinner-badge {
		display: inline-flex;
		align-items: center;
		gap: 6px;
		padding: 2px 8px;
	}

	/* Risk matrix styling */
	.risk-matrix {
		display: grid;
		grid-template-columns: repeat(4, 1fr);
		gap: 8px;
	}

	.matrix-item {
		padding: 12px 8px;
		border-radius: 6px;
		border: 1px solid var(--border-subtle);
		text-align: center;
		display: flex;
		flex-direction: column;
		gap: 4px;
	}

	.matrix-count {
		font-size: 20px;
		font-weight: 700;
	}

	.matrix-label {
		font-size: 11px;
		color: var(--text-secondary);
		font-weight: 500;
	}

	/* Risk glowing ambient tokens */
	.bg-critical-glow { background: var(--glow-critical); border-color: var(--glow-critical-border); }
	.bg-high-glow { background: var(--glow-high); border-color: var(--glow-high-border); }
	.bg-medium-glow { background: var(--glow-medium); border-color: var(--glow-medium-border); }
	.bg-low-glow { background: var(--glow-low); border-color: var(--glow-low-border); }

	.text-critical { color: #ff3b30; }
	.text-high { color: #f85149; }
	.text-medium { color: #d29922; }
	.text-low { color: #3fb950; }

	.routing-card {
		padding: 16px;
		border-radius: 8px;
		border: 1px solid var(--border-subtle);
		font-size: 13px;
		line-height: 1.6;
		color: var(--text-primary);
	}

	/* Top Risks tab styling */
	.risks-list {
		display: flex;
		flex-direction: column;
		gap: 16px;
	}

	.risk-glow-card {
		padding: 16px;
		border-radius: 8px;
		border: 1px solid var(--border-subtle);
		display: flex;
		flex-direction: column;
		gap: 12px;
		transition: all 200ms var(--ease-out);
	}

	.risk-glow-card:hover {
		transform: translateY(-2px);
	}

	.risk-glow-header {
		display: flex;
		align-items: center;
		justify-content: space-between;
	}

	.risk-glow-type {
		font-size: 14px;
		font-weight: 600;
		color: var(--text-primary);
	}

	.auto-renewal-badge {
		display: inline-flex;
		align-items: center;
		gap: 8px;
		padding: 6px 10px;
		border-radius: 6px;
		font-size: 12px;
		background: rgba(210, 153, 34, 0.08);
		border: 1px solid rgba(210, 153, 34, 0.2);
		color: #d29922;
	}

	.risk-glow-reasoning {
		font-size: 13px;
		line-height: 1.5;
		color: var(--text-primary);
	}

	.risk-glow-excerpt {
		font-family: monospace;
		font-size: 12px;
		background: var(--bg-hover);
		padding: 10px 12px;
		border-radius: 6px;
		border: 1px solid var(--border-subtle);
		color: var(--text-secondary);
		line-height: 1.5;
	}

	/* Ambient card glows by risk level */
	.risk-critical {
		background: var(--glow-critical);
		border-color: var(--glow-critical-border);
	}
	.risk-critical:hover {
		border-color: rgba(255, 59, 48, 0.4);
		box-shadow: 0 4px 20px rgba(255, 59, 48, 0.06);
	}

	.risk-high {
		background: var(--glow-high);
		border-color: var(--glow-high-border);
	}
	.risk-high:hover {
		border-color: rgba(248, 81, 73, 0.35);
		box-shadow: 0 4px 20px rgba(248, 81, 73, 0.05);
	}

	.risk-medium {
		background: var(--glow-medium);
		border-color: var(--glow-medium-border);
	}
	.risk-medium:hover {
		border-color: rgba(210, 153, 34, 0.3);
		box-shadow: 0 4px 16px rgba(210, 153, 34, 0.04);
	}

	.risk-low {
		background: var(--glow-low);
		border-color: var(--glow-low-border);
	}
	.risk-low:hover {
		border-color: rgba(63, 185, 80, 0.3);
		box-shadow: 0 4px 16px rgba(63, 185, 80, 0.03);
	}

	/* Clauses Filters and Lists */
	.clauses-filters {
		display: flex;
		flex-direction: column;
		gap: 12px;
		padding: 14px;
		border-radius: 8px;
		border: 1px solid var(--border-subtle);
	}

	.search-input-wrapper {
		position: relative;
		display: flex;
		align-items: center;
		width: 100%;
	}

	.search-icon {
		position: absolute;
		left: 12px;
		color: var(--text-tertiary);
		pointer-events: none;
	}

	.clause-search-bar {
		width: 100%;
		padding: 8px 12px 8px 34px;
		background: var(--bg-hover);
		border: 1px solid var(--border-subtle);
		border-radius: 6px;
		color: var(--text-primary);
		font-size: 13px;
		outline: none;
		transition: border-color 150ms ease;
	}

	.clause-search-bar:focus {
		border-color: var(--border-strong);
	}

	.filter-pills {
		overflow-x: auto;
		padding-bottom: 2px;
	}

	.filter-pill {
		background: transparent;
		border: 1px solid var(--border-subtle);
		color: var(--text-secondary);
		padding: 3px 10px;
		font-size: 11px;
		font-weight: 500;
		border-radius: 100px;
		cursor: pointer;
		transition: all 120ms ease;
		user-select: none;
	}

	.filter-pill:hover {
		color: var(--text-primary);
		border-color: var(--border-strong);
	}

	.filter-pill.active {
		color: #fff;
		border-color: var(--border-strong);
		background: var(--bg-hover);
	}

	.filter-pill-critical.active {
		background: rgba(255, 59, 48, 0.15);
		color: #ff3b30;
		border-color: rgba(255, 59, 48, 0.4);
	}

	.filter-pill-high.active {
		background: rgba(248, 81, 73, 0.15);
		color: #f85149;
		border-color: rgba(248, 81, 73, 0.4);
	}

	.filter-pill-medium.active {
		background: rgba(210, 153, 34, 0.12);
		color: #d29922;
		border-color: rgba(210, 153, 34, 0.35);
	}

	.filter-pill-low.active {
		background: rgba(63, 185, 80, 0.12);
		color: #3fb950;
		border-color: rgba(63, 185, 80, 0.35);
	}

	/* Interactive Clause Card */
	.clauses-list {
		display: flex;
		flex-direction: column;
		gap: 12px;
	}

	.clause-interactive-card {
		border: 1px solid var(--border-subtle);
		border-radius: 8px;
		padding: 14px;
		display: flex;
		flex-direction: column;
		gap: 10px;
		cursor: pointer;
		transition: all 200ms var(--ease-out);
		user-select: none;
	}

	.clause-interactive-card:active {
		transform: scale(0.99);
	}

	.clause-interactive-header {
		display: flex;
		align-items: center;
		justify-content: space-between;
	}

	.chevron-icon {
		color: var(--text-tertiary);
		transition: transform 180ms var(--ease-out);
	}

	.chevron-icon.rotated {
		transform: rotate(90deg);
		color: var(--text-secondary);
	}

	.clause-interactive-excerpt {
		font-size: 12.5px;
		color: var(--text-secondary);
		line-height: 1.6;
		padding-left: 24px;
	}

	.clause-interactive-card.expanded {
		cursor: default;
	}
	.clause-interactive-card.expanded:active {
		transform: none;
	}

	.clause-expanded-section {
		padding-left: 24px;
		display: flex;
		flex-direction: column;
		gap: 12px;
		margin-top: 4px;
		animation: slideDown 220ms var(--ease-out) forwards;
	}

	@keyframes slideDown {
		from { opacity: 0; transform: translateY(-4px); }
		to { opacity: 1; transform: translateY(0); }
	}

	.clause-reasoning {
		font-size: 13px;
		line-height: 1.5;
		color: var(--text-primary);
	}

	.clause-redline {
		border: 1px solid var(--border-subtle);
		border-radius: 6px;
		background: var(--bg-hover);
		overflow: hidden;
	}

	.clause-redline-head {
		padding: 8px 12px;
		border-bottom: 1px solid var(--border-subtle);
		background: var(--bg-active);
		font-size: 12px;
		color: var(--text-secondary);
	}

	.clause-redline-block {
		padding: 12px;
		font-family: 'JetBrains Mono', 'SF Mono', Consolas, monospace;
		font-size: 12px;
		line-height: 1.6;
		color: var(--color-low);
		white-space: pre-wrap;
		word-break: break-all;
		margin: 0;
	}

	.clause-tech {
		border: 1px solid var(--border-subtle);
		border-radius: 6px;
		padding: 8px 12px;
		background: rgba(0,0,0,0.1);
	}

	.clause-tech[open] summary {
		margin-bottom: 10px;
		color: var(--text-primary);
	}

	.tech-grid {
		display: grid;
		grid-template-columns: repeat(2, 1fr);
		gap: 8px;
		font-size: 11.5px;
	}

	.tech-row {
		display: flex;
		flex-direction: column;
		gap: 2px;
	}

	.tech-label {
		color: var(--text-tertiary);
		text-transform: uppercase;
		font-size: 9.5px;
		font-weight: 500;
	}

	.tech-value {
		color: var(--text-secondary);
	}

	/* Processing States in Workspace */
	.processing-stats {
		padding: 14px;
		border-radius: 6px;
		border: 1px solid var(--border-subtle);
		display: flex;
		flex-direction: column;
		gap: 10px;
	}

	.ps-row {
		display: flex;
		justify-content: space-between;
		font-size: 13px;
	}

	.ps-label {
		color: var(--text-secondary);
	}

	.ps-value {
		color: var(--text-primary);
		font-weight: 500;
	}

	.progress-bar-container {
		width: 100%;
		height: 4px;
		background: rgba(255, 255, 255, 0.08);
		border-radius: 99px;
		overflow: hidden;
		margin-top: 4px;
	}

	.progress-bar-fill {
		height: 100%;
		background: var(--accent-primary);
		border-radius: 99px;
		transition: width 300ms ease;
	}

	/* System Trace Timeline */
	.trace-timeline {
		display: flex;
		flex-direction: column;
		gap: 16px;
	}

	.timeline-step {
		display: flex;
		gap: 12px;
		position: relative;
	}

	.timeline-step::before {
		content: '';
		position: absolute;
		left: 7px;
		top: 18px;
		bottom: -22px;
		width: 1px;
		background: var(--border-subtle);
	}

	.timeline-step:last-child::before {
		display: none;
	}

	.timeline-icon {
		width: 16px;
		height: 16px;
		border-radius: 50%;
		display: flex;
		align-items: center;
		justify-content: center;
		flex-shrink: 0;
		z-index: 1;
		font-size: 8px;
		font-weight: bold;
	}

	.timeline-icon.done {
		background: rgba(63, 185, 80, 0.15);
		border: 1px solid rgba(63, 185, 80, 0.4);
		color: #3fb950;
	}

	.timeline-icon.active {
		background: var(--bg-hover);
		border: 1px solid var(--border-strong);
	}

	.timeline-content {
		display: flex;
		justify-content: space-between;
		width: 100%;
		align-items: baseline;
		font-size: 13px;
	}

	.timeline-text {
		color: var(--text-primary);
		font-weight: 500;
	}

	.timeline-time {
		font-size: 12px;
		font-family: monospace;
	}

	.time-active {
		color: var(--accent-primary);
	}

	.empty-tab-state, .clauses-loading {
		display: flex;
		flex-direction: column;
		align-items: center;
		justify-content: center;
		height: 180px;
		color: var(--text-tertiary);
		gap: 10px;
	}

	/* Global modal overrides for dynamic cockpit context */
	.modal-root {
		position: fixed;
		top: 0;
		left: 0;
		right: 0;
		bottom: 0;
		display: flex;
		align-items: center;
		justify-content: center;
		z-index: 200;
	}

	.modal-backdrop {
		position: absolute;
		top: 0;
		left: 0;
		right: 0;
		bottom: 0;
		background: rgba(0,0,0,0.6);
		backdrop-filter: blur(4px);
		border: none;
		width: 100%;
		height: 100%;
		cursor: default;
	}

	.modal-content {
		background: var(--bg-panel);
		border: 1px solid var(--border-subtle);
		border-radius: 8px;
		width: 100%;
		max-width: 440px;
		padding: 24px;
		display: flex;
		flex-direction: column;
		gap: 16px;
		z-index: 201;
		box-shadow: 0 20px 50px rgba(0,0,0,0.6);
		animation: modalReveal 180ms var(--ease-out) forwards;
	}

	@keyframes modalReveal {
		from { opacity: 0; transform: scale(0.96); }
		to { opacity: 1; transform: scale(1); }
	}

	.modal-header {
		display: flex;
		align-items: center;
		gap: 12px;
	}

	.modal-icon {
		width: 32px;
		height: 32px;
		border-radius: 50%;
		display: flex;
		align-items: center;
		justify-content: center;
		flex-shrink: 0;
	}

	.modal-icon.warning {
		background: rgba(248, 81, 73, 0.1);
		border: 1px solid rgba(248, 81, 73, 0.3);
		color: #f85149;
	}

	.modal-header h3 {
		font-size: 15px;
		font-weight: 600;
		margin: 0;
	}

	.modal-body {
		font-size: 13px;
		color: var(--text-secondary);
		line-height: 1.6;
	}

	.modal-footer {
		display: flex;
		gap: 8px;
	}

	.clause-interactive-card.active-card {
		border-color: var(--accent-primary) !important;
		box-shadow: 0 4px 16px var(--glow-low);
	}
</style>
