<script lang="ts">
	import { onMount, onDestroy } from 'svelte';
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

	type Clause = {
		id: string;
		clause_type: string;
		text_content: string;
		risk_level: string;
		risk_reasoning?: string | null;
		redline_suggestion?: string | null;
		risk_debug_json?: any;
	};

	let fileInput: HTMLInputElement;
	let isUploading = $state(false);
	let pasteModalOpen = $state(false);
	let pastedText = $state('');
	
	let contracts: ContractSummary[] = $state([]);
	let pollInterval: any;
	
	// Track which contracts were previously in PROCESSING state
	let processingIds = new Set<string>();

	let now = $state(Date.now());
	let stopwatchInterval: any;
	let liveSteps = $state<{text: string, startTime: number, endTime: number | null}[]>([]);
	let apiBase = $state('http://localhost:9432');
	let processingStatus = $state<any>(null);

	$effect(() => {
		if (selectedContract && selectedContract.status === 'PROCESSING') {
			const step = selectedContract.metadata_json?.processing_step;
			if (step) {
				const lastStep = liveSteps[liveSteps.length - 1];
				if (!lastStep || lastStep.text !== step) {
					// Mark previous step as done
					if (lastStep && !lastStep.endTime) {
						lastStep.endTime = Date.now();
					}
					// Add new step
					liveSteps = [...liveSteps, { text: step, startTime: Date.now(), endTime: null }];
				}
			}
		} else if (selectedContract && (selectedContract.status === 'COMPLETED' || selectedContract.status === 'FAILED')) {
			// Cap the last step if it finishes
			const lastStep = liveSteps[liveSteps.length - 1];
			if (lastStep && !lastStep.endTime) {
				lastStep.endTime = Date.now();
			}
		}
	});

	function formatStopwatch(ms: number) {
		if (!ms || ms < 0) return "0.0s";
		return (ms / 1000).toFixed(1) + "s";
	}

	async function formatEta(seconds: number | null | undefined) {
		if (seconds === null || seconds === undefined) return '--';
		if (seconds <= 1) return '< 1s';
		const s = Math.max(0, Math.floor(seconds));
		const m = Math.floor(s / 60);
		const r = s % 60;
		if (m <= 0) return `~${r}s`;
		return `~${m}m ${r}s`;
	}

	async function fetchProcessingStatus(contractId: string) {
		try {
			const res = await apiFetch(`/api/v1/contracts/${contractId}/status`);
			if (!res.ok) return;
			processingStatus = await res.json();
		} catch {
			// non-fatal
		}
	}

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
				
				const sc = selectedContract;
				if (sc) {
					const updated = contracts.find((c: any) => c.id === sc.id);
					if (updated) {
						selectedContract = updated;
						// If it just completed while drawer is open, fetch clauses automatically
						if ((updated.status === 'COMPLETED' || updated.status === 'FAILED') && drawerClauses.length === 0 && !isDrawerLoading) {
							loadDrawerClauses(updated.id);
						}
						if (updated.status === 'PROCESSING') {
							fetchProcessingStatus(updated.id);
						} else {
							processingStatus = null;
						}
					}
				}
			}
		} catch (err) {
			console.error("Failed to fetch contracts:", err);
		}
	}

	onMount(() => {
		// If the UI is accessed via a LAN IP/hostname, avoid "localhost" which points at the viewer's machine.
		const u = new URL(window.location.href);
		apiBase = `${u.protocol}//${u.hostname}:9432`;

		fetchContracts();
		pollInterval = setInterval(fetchContracts, 3000);
		stopwatchInterval = setInterval(() => { now = Date.now(); }, 100);
	});

	onDestroy(() => {
		if (pollInterval) clearInterval(pollInterval);
		if (stopwatchInterval) clearInterval(stopwatchInterval);
	});

	function triggerUpload() {
		if (fileInput) fileInput.click();
	}

	async function copyClauseRedline(clause: any) {
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
			// Fallback for older browsers / stricter permissions
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
				toast.error('Failed to copy. Select the text and copy manually.');
			}
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
				await fetchContracts();
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
				fetchContracts(); // Immediately fetch to show the new 'PROCESSING' row
				isUploading = false;
			} else {
				throw new Error('Upload failed');
			}
		} catch (error) {
			console.error("Upload error:", error);
			toast.dismiss(loadingToastId);
			toast.error('Failed to upload document.');
			isUploading = false;
		}
	}

	async function handleReprocess(contractId: string) {
		const loadingToastId = toast.loading('Restarting AI pipeline...');
		try {
			const response = await apiFetch(`/api/v1/contracts/${contractId}/reprocess`, {
				method: 'POST'
			});
			if (response.ok) {
				toast.dismiss(loadingToastId);
				toast.success('Reprocessing started.');
				fetchContracts();
			} else {
				throw new Error('Reprocess failed');
			}
		} catch (error) {
			toast.dismiss(loadingToastId);
			toast.error('Failed to reprocess contract. (Need to re-upload)');
		}
	}

	let deleteModalOpen = $state(false);
	let contractToDelete = $state<string | null>(null);

	function promptDelete(contractId: string) {
		contractToDelete = contractId;
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
				fetchContracts();
				if (selectedContract?.id === contractId) {
					closeDrawer();
				}
			} else {
				throw new Error('Delete failed');
			}
		} catch (error) {
			toast.dismiss(loadingToastId);
			toast.error('Failed to delete contract.');
		}
	}

	let selectedContract: ContractSummary | null = $state(null);
	let drawerOpen = $state(false);
	let drawerClauses: Clause[] = $state([]);
	let isDrawerLoading = $state(false);

	function getProcessingPhase(step: string | undefined | null) {
		if (!step) return "Initializing";
		const s = step.toLowerCase();
		if (s.includes('segment')) return "Planning";
		if (s.includes('analyz')) return "Thinking";
		if (s.includes('sav')) return "Executing";
		return "Processing";
	}

	async function loadDrawerClauses(contractId: string) {
		isDrawerLoading = true;
		try {
			const res = await apiFetch(`/api/v1/contracts/${contractId}/clauses`);
			const data = await res.json();
			drawerClauses = (data.clauses || []) as Clause[];
		} catch (error) {
			console.error("Failed to fetch clauses:", error);
			toast.error("Failed to load contract details");
		}
		isDrawerLoading = false;
	}

	async function openDrawer(contract: ContractSummary) {
		selectedContract = contract;
		drawerOpen = true;
		drawerClauses = [];
		processingStatus = null;
		
		if (contract.status === 'PROCESSING') {
			// Initialize liveSteps from current step if empty or mismatched
			const step = contract.metadata_json?.processing_step;
			if (step) {
				liveSteps = [{ text: step, startTime: Date.now(), endTime: null }];
			} else {
				liveSteps = [];
			}
			fetchProcessingStatus(contract.id);
		} else if (contract.status === 'COMPLETED' || contract.status === 'FAILED') {
			await loadDrawerClauses(contract.id);
		}
	}
	
	function closeDrawer() {
		drawerOpen = false;
		setTimeout(() => {
			selectedContract = null;
			drawerClauses = [];
		}, 300); // Wait for transition
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
			<span class="separator">/</span>
			<span class="crumb active">Dashboard</span>
		</div>
		
		<div class="header-content flex-between">
			<h1>Contract Overview</h1>
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
					Paste Text
				</button>
			</div>
		</div>
	</div>
</header>

<div class="page-content">
	<div class="metric-row">
		<div class="metric-card panel">
			<div class="metric-label">Active Contracts</div>
			<div class="metric-value">{contracts.length}</div>
		</div>
		<div class="metric-card panel">
			<div class="metric-label">High Risk Clauses</div>
			<div class="metric-value text-danger">{contracts.filter(c => c.overall_risk === 'HIGH' || c.overall_risk === 'CRITICAL').length}</div>
		</div>
		<div class="metric-card panel">
			<div class="metric-label">Expiring &lt; 30 Days</div>
			<div class="metric-value text-warning">--</div>
		</div>
		<div class="metric-card panel">
			<div class="metric-label">In Negotiation</div>
			<div class="metric-value">--</div>
		</div>
	</div>

	<h3 class="section-title">Recent Activity</h3>
	
	<div class="data-table panel">
		<div class="table-header">
			<div class="col col-name">Document</div>
			<div class="col col-status">Status</div>
			<div class="col col-risk">Risk Score</div>
			<div class="col col-date">Uploaded</div>
			<div class="col col-actions"></div>
		</div>
		
		{#if contracts.length === 0}
			<div class="table-row empty-row">
				No contracts analyzed yet.
			</div>
		{/if}

		{#each contracts as contract}
			<!-- svelte-ignore a11y_click_events_have_key_events -->
			<!-- svelte-ignore a11y_no_static_element_interactions -->
			<div class="table-row clickable-row" onclick={(e: MouseEvent) => {
				// Don't open drawer if they clicked the reprocess or delete button
				const target = e.target as HTMLElement | null;
				if (!target || !target.closest('.btn-icon')) {
					openDrawer(contract);
				}
			}}>
				<div class="col col-name">
					<svg class="file-icon" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/><line x1="16" y1="13" x2="8" y2="13"/><line x1="16" y1="17" x2="8" y2="17"/><polyline points="10 9 9 9 8 9"/></svg>
					{contract.filename}
				</div>
				<div class="col col-status" style="flex: 2; min-width: 0;">
					{#if contract.status === 'COMPLETED'}
						<span class="badge badge-success">Completed</span>
					{:else if contract.status === 'FAILED'}
						<span class="badge badge-danger">Failed</span>
					{:else}
						{@const phase = getProcessingPhase(contract.metadata_json?.processing_step)}
							<div class="thinking-indicator" title={contract.metadata_json?.processing_step || "Processing"}>
								<span class="spinner spinner-sm"></span>
								<span class="thinking-label">{phase}</span>
								<span class="thinking-step">{contract.metadata_json?.processing_step || "Processing..."}</span>
							</div>
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
				<div class="col col-actions" style="display: flex; gap: 8px; justify-content: flex-end;">
					{#if contract.status === 'FAILED' || contract.status === 'COMPLETED'}
						<button class="btn-icon" onclick={() => handleReprocess(contract.id)} aria-label="Reprocess" title="Reprocess">
							<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M3 12a9 9 0 1 0 9-9 9.75 9.75 0 0 0-6.74 2.74L3 8"/><path d="M3 3v5h5"/></svg>
						</button>
					{/if}
					<button class="btn-icon" onclick={(e) => { e.stopPropagation(); promptDelete(contract.id); }} aria-label="Delete" title="Delete Contract" style="color: var(--text-tertiary);">
						<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M3 6h18"></path><path d="M19 6v14c0 1-1 2-2 2H7c-1 0-2-1-2-2V6"></path><path d="M8 6V4c0-1 1-2 2-2h4c1 0 2 1 2 2v2"></path></svg>
					</button>
				</div>
			</div>
		{/each}
	</div>
</div>

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
						<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/><line x1="12" y1="13" x2="12" y2="17"/><line x1="12" y1="9" x2="12.01" y2="9"/></svg>
					</div>
					<h3>Analyze Pasted Contract Text</h3>
				</div>
				<div class="modal-body">
					<p class="text-tertiary modal-help">
						Paste the contract text below (emails, Google Docs, plaintext). We'll analyze it like a PDF.
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

	{#if drawerOpen}
		<button type="button" class="drawer-overlay" aria-label="Close" onclick={closeDrawer}></button>
		
		<div class="drawer {drawerOpen ? 'open' : ''}">
			<div class="drawer-header">
				<h2 class="drawer-title">{selectedContract?.filename}</h2>
				<button class="drawer-close" onclick={closeDrawer} aria-label="Close drawer">
					<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M18 6L6 18M6 6l12 12"/></svg>
				</button>
			</div>
			
			<div class="drawer-content">
				{#if isDrawerLoading}
					<div class="drawer-loading">
						<span class="spinner spinner-lg"></span>
						<p>Loading details...</p>
					</div>
				{:else}
				<div class="drawer-section">
					<h3>Overview</h3>
					<div class="drawer-meta">
						<div class="meta-item">
							<span class="meta-label">Status</span>
							{#if selectedContract?.status === 'COMPLETED'}
								<span class="badge badge-success">Completed</span>
							{:else if selectedContract?.status === 'FAILED'}
								<span class="badge badge-danger">Failed</span>
							{:else}
								{@const phase = getProcessingPhase(selectedContract?.metadata_json?.processing_step)}
								<div class="thinking-indicator thinking-indicator-compact" title={selectedContract?.metadata_json?.processing_step || "Processing"}>
									<span class="spinner spinner-sm"></span>
									<span class="thinking-label">{phase}</span>
									<span class="thinking-step">{selectedContract?.metadata_json?.processing_step || "Processing..."}</span>
								</div>
							{/if}
						</div>
						<div class="meta-item">
							<span class="meta-label">Uploaded</span>
							<span>{selectedContract ? timeAgo(selectedContract.created_at) : '--'}</span>
						</div>
					</div>
				</div>

				{#if selectedContract?.status === 'COMPLETED' && selectedContract?.metadata_json?.top_risks?.length}
					<div class="drawer-section">
						<h3>Top Risks</h3>
						<div class="clauses-list">
							{#each selectedContract.metadata_json.top_risks as r}
								<div class="clause-card risk-{(r.risk_level || 'LOW').toLowerCase()}">
									<div class="clause-header">
										<span class="clause-type">{r.clause_type || 'Clause'}</span>
										<span class="badge badge-{r.risk_level === 'CRITICAL' || r.risk_level === 'HIGH' ? 'danger' : r.risk_level === 'MEDIUM' ? 'warning' : 'success'}">{r.risk_level}</span>
									</div>
									{#if r.auto_renewal}
										<div class="text-tertiary" style="margin: 6px 0 2px;">
											<strong>Auto-renewal:</strong>
											{#if r.auto_renewal.opt_out_days_before_renewal}
												You must cancel at least {r.auto_renewal.opt_out_days_before_renewal} days before renewal to avoid auto-renewal.
											{:else}
												This clause appears to include auto-renewal language. Confirm the opt-out deadline.
											{/if}
										</div>
									{/if}
									<div class="clause-reasoning">
										<strong>Why it matters:</strong> {r.risk_reasoning || 'Flagged as risky.'}
									</div>
									{#if r.text_excerpt}
										<div class="clause-text" style="margin-top: 8px;">{r.text_excerpt}</div>
									{/if}
								</div>
							{/each}
						</div>
					</div>
				{/if}

				{#if selectedContract?.status === 'PROCESSING'}
					<div class="drawer-section">
						<h3>Live Processing Trace</h3>
						{#if processingStatus}
							<div class="processing-meta">
								<div class="pm-item">
									<span class="pm-label">Stage</span>
									<span class="pm-value">{processingStatus.stage?.label || 'Processing'} ({processingStatus.stage?.index || 0}/{processingStatus.stage?.count || 3})</span>
								</div>
								<div class="pm-item">
									<span class="pm-label">ETA</span>
									<span class="pm-value">{formatEta(processingStatus.eta_seconds)}</span>
								</div>
								{#if processingStatus.progress}
									<div class="pm-item">
										<span class="pm-label">Progress</span>
										<span class="pm-value">{processingStatus.progress.current}/{processingStatus.progress.total}</span>
									</div>
								{/if}
							</div>
						{/if}
						<div class="timeline">
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

					{#if selectedContract?.status === 'COMPLETED' || selectedContract?.status === 'FAILED'}
						<div class="drawer-section">
							<h3>Extracted Clauses ({drawerClauses.length})</h3>
							{#if drawerClauses.length === 0}
								<p class="text-tertiary">No clauses extracted.</p>
							{:else}
								<div class="clauses-list">
									{#each drawerClauses as clause}
										<div class="clause-card risk-{clause.risk_level.toLowerCase()}">
											<div class="clause-header">
												<span class="clause-type">{clause.clause_type}</span>
												<span
													class="badge badge-{clause.risk_level === 'CRITICAL' || clause.risk_level === 'HIGH'
														? 'danger'
														: clause.risk_level === 'MEDIUM'
															? 'warning'
															: 'success'}"
												>
													{clause.risk_level}
												</span>
											</div>
											<div class="clause-text">{clause.text_content}</div>
											<div class="clause-reasoning">
												<strong>Rationale:</strong> {clause.risk_reasoning}
											</div>
											{#if clause.redline_suggestion}
												<div class="clause-redline">
													<div class="clause-redline-head">
														<strong>Suggested Redline</strong>
														<button class="btn btn-secondary btn-compact" onclick={() => copyClauseRedline(clause)}>Copy</button>
													</div>
													<pre class="clause-redline-block">{clause.redline_suggestion}</pre>
												</div>
											{/if}

											{#if clause.risk_debug_json && Object.keys(clause.risk_debug_json).length}
												<details class="clause-tech">
													<summary>Technical details</summary>
													<div class="tech-grid">
														<div class="tech-row">
															<span class="tech-label">Model</span>
															<span class="tech-value">{clause.risk_debug_json.model || '--'}</span>
														</div>
														<div class="tech-row">
															<span class="tech-label">Latency</span>
															<span class="tech-value">{clause.risk_debug_json.latency_ms ?? '--'}ms</span>
														</div>
														<div class="tech-row">
															<span class="tech-label">Composite</span>
															<span class="tech-value">{clause.risk_debug_json.composite_score ?? '--'}</span>
														</div>
														<div class="tech-row">
															<span class="tech-label">Confidence</span>
															<span class="tech-value">{clause.risk_debug_json.confidence ?? '--'}</span>
														</div>
													</div>

													{#if clause.risk_debug_json.dimensions}
														{@const dims = clause.risk_debug_json.dimensions as Record<string, number>}
														<div class="tech-dims">
															{#each Object.entries(dims) as [k, v] (k)}
																{#if v > 0}
																	<div class="dim-row">
																		<span class="dim-key">{k}</span>
																		<span class="dim-val">{v}</span>
																	</div>
																{/if}
															{/each}
														</div>
													{/if}
												</details>
											{/if}
										</div>
									{/each}
								</div>
							{/if}
						</div>
					{/if}

				<div class="drawer-section">
					<h3>Raw OCR Text</h3>
					<div class="raw-text-container">
						{selectedContract?.metadata_json?.raw_text || "Raw text not available."}
					</div>
				</div>
			{/if}
		</div>
	</div>
{/if}

<style>
	.page-header {
		padding: 32px 40px 24px;
		border-bottom: 1px solid var(--border-subtle);
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

	.page-content {
		padding: 32px 40px;
		max-width: 1200px;
	}

	.metric-row {
		display: grid;
		grid-template-columns: repeat(4, 1fr);
		gap: 16px;
		margin-bottom: 40px;
	}

	.metric-card {
		background: var(--bg-glass-card);
		border: 1px solid var(--border-glass);
		border-radius: 12px;
		padding: 24px 20px;
		transition: transform 180ms var(--ease-out), 
					border-color 180ms var(--ease-out), 
					box-shadow 180ms var(--ease-out);
		cursor: pointer;
		position: relative;
		overflow: hidden;
	}

	.metric-card:hover {
		transform: translateY(-2px);
		border-color: var(--border-glass-hover);
		box-shadow: 0 8px 30px rgba(0, 0, 0, 0.35);
	}

	.metric-card:active {
		transform: scale(0.975);
	}

	.metric-card::before {
		content: '';
		position: absolute;
		top: 0; left: 0; right: 0; height: 1px;
		background: linear-gradient(90deg, transparent, rgba(255, 255, 255, 0.15), transparent);
	}

	.metric-label {
		font-size: 13px;
		color: var(--text-secondary);
		margin-bottom: 8px;
		font-weight: 500;
	}

	.metric-value {
		font-size: 24px;
		font-weight: 600;
		color: var(--text-primary);
	}

	.text-danger { color: #e5484d; }
	.text-warning { color: #f5a623; }
	.text-tertiary { color: var(--text-tertiary); }

	.section-title {
		font-size: 14px;
		margin-bottom: 16px;
		color: var(--text-primary);
	}

	/* Data Table */
	.data-table {
		display: flex;
		flex-direction: column;
	}

	.table-header {
		display: flex;
		padding: 12px 16px;
		border-bottom: 1px solid var(--border-subtle);
		font-size: 12px;
		font-weight: 500;
		color: var(--text-secondary);
	}

	.table-row {
		display: flex;
		align-items: center;
		padding: 14px 20px;
		border-bottom: 1px solid var(--border-subtle);
		font-size: 13px;
		transition: background-color 180ms var(--ease-out), 
					transform 180ms var(--ease-out);
	}

	.table-row:last-child {
		border-bottom: none;
	}

	.table-row.clickable-row {
		cursor: pointer;
	}

	.table-row.clickable-row:hover {
		background-color: var(--bg-hover);
	}

	.table-row.clickable-row:active {
		transform: scale(0.995);
	}

	.col { flex: 1; }
	.col-name { 
		flex: 3; 
		display: flex; 
		align-items: center; 
		gap: 10px; 
		font-weight: 500;
	}
	.col-status { flex: 2; }
	.col-risk { flex: 2; display: flex; align-items: center; gap: 8px; }
	.col-date { flex: 1; text-align: right; }
	.col-actions { flex: 0.5; display: flex; justify-content: flex-end; }

		.btn-icon {
		background: transparent;
		border: none;
		color: var(--text-tertiary);
		cursor: pointer;
		padding: 4px;
		border-radius: 4px;
		display: flex;
		align-items: center;
		justify-content: center;
			transition: background 150ms ease, color 150ms ease, transform 120ms var(--ease-out);
		}
		.btn-icon:active { transform: scale(0.97); }
	.btn-icon:hover {
		background: var(--bg-hover);
		color: var(--text-primary);
	}

	.file-icon {
		color: var(--text-tertiary);
	}

	.badge {
		display: inline-flex;
		align-items: center;
		padding: 2px 8px;
		border-radius: 100px;
		font-size: 11px;
		font-weight: 600;
	}

	.badge-success { background: rgba(46, 160, 67, 0.15); color: #3fb950; }
	.badge-warning { background: rgba(210, 153, 34, 0.15); color: #d29922; }
	.badge-blue { background: rgba(88, 166, 255, 0.15); color: #58a6ff; }

	.risk-indicator {
		width: 8px;
		height: 8px;
		border-radius: 50%;
	}

	.risk-low { background: #3fb950; }
	.risk-high { background: #f85149; }

	.drawer-overlay {
		position: fixed;
		top: 0; left: 0; right: 0; bottom: 0;
		background: rgba(0, 0, 0, 0.5);
		backdrop-filter: blur(8px);
		z-index: 100;
		animation: fadeIn 220ms cubic-bezier(0.16, 1, 0.3, 1) forwards;
	}

	.drawer {
		position: fixed;
		top: 0; right: 0; bottom: 0;
		width: 620px;
		max-width: 100vw;
		background: var(--bg-glass);
		backdrop-filter: blur(24px) saturate(190%);
		-webkit-backdrop-filter: blur(24px) saturate(190%);
		border-left: 1px solid var(--border-glass);
		box-shadow: var(--shadow-premium);
		z-index: 101;
		display: flex;
		flex-direction: column;
		transform: translateX(100%);
		transition: transform 280ms cubic-bezier(0.16, 1, 0.3, 1);
	}
	.drawer.open {
		transform: translateX(0);
	}

		.drawer-header {
			padding: 24px;
			border-bottom: 1px solid var(--border-subtle);
			display: flex;
		justify-content: space-between;
		align-items: center;
	}

	.drawer-title {
		font-size: 1.25rem;
		font-weight: 500;
		color: var(--text-primary);
		margin: 0;
	}

		.drawer-close {
		background: transparent;
		border: none;
		color: var(--text-tertiary);
		cursor: pointer;
		padding: 4px;
		border-radius: 4px;
		display: flex;
		align-items: center;
		justify-content: center;
			transition: background 150ms ease, color 150ms ease, transform 120ms var(--ease-out);
		}
		.drawer-close:active { transform: scale(0.97); }
	.drawer-close:hover {
		background: var(--bg-hover);
		color: var(--text-primary);
	}

	.drawer-content {
		padding: 24px;
		overflow-y: auto;
		flex: 1;
		display: flex;
		flex-direction: column;
		gap: 32px;
	}

	.drawer-loading {
		display: flex;
		flex-direction: column;
		align-items: center;
		justify-content: center;
		height: 200px;
		gap: 16px;
		color: var(--text-tertiary);
	}

	.drawer-section h3 {
		font-size: 0.875rem;
		text-transform: uppercase;
		letter-spacing: 0.05em;
		color: var(--text-tertiary);
		margin: 0 0 16px 0;
	}

		.drawer-meta {
			display: grid;
			grid-template-columns: 1fr 1fr;
			gap: 16px;
			background: rgba(255, 255, 255, 0.02);
			padding: 18px;
			border-radius: 10px;
			border: 1px solid rgba(255, 255, 255, 0.05);
		}

	.meta-item {
		display: flex;
		flex-direction: column;
		gap: 4px;
		font-size: 0.875rem;
	}

	.meta-label {
		color: var(--text-tertiary);
	}

	.clauses-list {
		display: flex;
		flex-direction: column;
		gap: 16px;
	}

	.clause-card {
		background: var(--bg-glass-card);
		border: 1px solid var(--border-glass);
		border-radius: 12px;
		padding: 18px;
		display: flex;
		flex-direction: column;
		gap: 12px;
		transition: transform 200ms var(--ease-out), 
					border-color 200ms var(--ease-out), 
					box-shadow 200ms var(--ease-out), 
					background-color 200ms var(--ease-out);
		position: relative;
		overflow: hidden;
	}

	.clause-card:hover {
		transform: translateY(-2px);
		border-color: var(--border-glass-hover);
		box-shadow: 0 8px 30px rgba(0, 0, 0, 0.35);
	}

	.clause-card:active {
		transform: scale(0.985);
	}

	.clause-card.risk-critical {
		background: var(--glow-critical);
		border-color: var(--glow-critical-border);
		box-shadow: 0 4px 20px rgba(255, 59, 48, 0.015);
	}
	.clause-card.risk-critical:hover {
		border-color: rgba(255, 59, 48, 0.4);
		box-shadow: 0 8px 30px rgba(255, 59, 48, 0.05), 0 0 1px rgba(255, 59, 48, 0.2);
	}

	.clause-card.risk-high {
		background: var(--glow-high);
		border-color: var(--glow-high-border);
		box-shadow: 0 4px 20px rgba(248, 81, 73, 0.015);
	}
	.clause-card.risk-high:hover {
		border-color: rgba(248, 81, 73, 0.4);
		box-shadow: 0 8px 30px rgba(248, 81, 73, 0.05), 0 0 1px rgba(248, 81, 73, 0.2);
	}

	.clause-card.risk-medium {
		background: var(--glow-medium);
		border-color: var(--glow-medium-border);
		box-shadow: 0 4px 20px rgba(210, 153, 34, 0.015);
	}
	.clause-card.risk-medium:hover {
		border-color: rgba(210, 153, 34, 0.4);
		box-shadow: 0 8px 30px rgba(210, 153, 34, 0.05), 0 0 1px rgba(210, 153, 34, 0.2);
	}

	.clause-card.risk-low {
		background: var(--glow-low);
		border-color: var(--glow-low-border);
		box-shadow: 0 4px 20px rgba(63, 185, 80, 0.015);
	}
	.clause-card.risk-low:hover {
		border-color: rgba(63, 185, 80, 0.4);
		box-shadow: 0 8px 30px rgba(63, 185, 80, 0.05), 0 0 1px rgba(63, 185, 80, 0.2);
	}

	.clause-header {
		display: flex;
		justify-content: space-between;
		align-items: center;
	}

	.clause-type {
		font-weight: 500;
		color: var(--text-primary);
	}

	.clause-text {
		font-size: 0.875rem;
		color: var(--text-secondary);
		line-height: 1.6;
		padding: 14px;
		background: rgba(0, 0, 0, 0.25);
		border-radius: 8px;
		border: 1px solid rgba(255, 255, 255, 0.04);
	}

	.clause-reasoning, .clause-redline {
		font-size: 0.875rem;
		color: var(--text-secondary);
		line-height: 1.4;
	}
	
	.clause-redline-head {
		display: flex;
		align-items: center;
		justify-content: space-between;
		gap: 12px;
	}

	.btn-compact {
		height: 28px;
		padding: 0 10px;
		font-size: 12px;
	}

	.clause-redline-block {
		margin: 8px 0 0 0;
		padding: 16px;
		border-radius: 10px;
		border: 1px solid rgba(255, 255, 255, 0.06);
		background: rgba(10, 10, 12, 0.65);
		color: #a7f3d0;
		text-shadow: 0 0 12px rgba(167, 243, 208, 0.08);
		white-space: pre-wrap;
		line-height: 1.55;
		font-family: 'JetBrains Mono', 'Fira Code', ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, "Liberation Mono", "Courier New", monospace;
		font-size: 13px;
	}

	.clause-tech {
		border-top: 1px solid var(--border-subtle);
		padding-top: 10px;
		margin-top: 2px;
	}

	.clause-tech > summary {
		cursor: pointer;
		color: var(--text-tertiary);
		font-size: 12px;
		user-select: none;
		list-style: none;
	}

	.clause-tech > summary::-webkit-details-marker {
		display: none;
	}

	.clause-tech > summary::before {
		content: "▸";
		display: inline-block;
		margin-right: 8px;
		transform: translateY(-1px);
		transition: transform 120ms var(--ease-out);
	}

	.clause-tech[open] > summary::before {
		transform: rotate(90deg) translateY(-1px);
	}

	.tech-grid {
		margin-top: 10px;
		display: grid;
		grid-template-columns: repeat(2, minmax(0, 1fr));
		gap: 8px 14px;
	}

	.tech-row {
		display: flex;
		align-items: baseline;
		justify-content: space-between;
		gap: 12px;
		padding: 10px 12px;
		background: rgba(255, 255, 255, 0.03);
		border: 1px solid var(--border-subtle);
		border-radius: 8px;
	}

	.tech-label {
		color: var(--text-tertiary);
		font-size: 11px;
		text-transform: uppercase;
		letter-spacing: 0.05em;
	}

	.tech-value {
		color: var(--text-secondary);
		font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, "Liberation Mono", "Courier New", monospace;
		font-size: 12px;
	}

	.tech-dims {
		margin-top: 10px;
		display: grid;
		grid-template-columns: repeat(2, minmax(0, 1fr));
		gap: 6px 12px;
	}

	.dim-row {
		display: flex;
		align-items: baseline;
		justify-content: space-between;
		gap: 10px;
		padding: 8px 10px;
		border: 1px solid var(--border-subtle);
		border-radius: 8px;
		background: rgba(255, 255, 255, 0.02);
	}

	.dim-key {
		color: var(--text-tertiary);
		font-size: 12px;
	}

	.dim-val {
		color: var(--text-secondary);
		font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, "Liberation Mono", "Courier New", monospace;
		font-size: 12px;
	}

	.raw-text-container {
		font-family: 'JetBrains Mono', 'Fira Code', ui-monospace, monospace;
		font-size: 12px;
		color: var(--text-secondary);
		line-height: 1.5;
		white-space: pre-wrap;
		padding: 16px;
		background: rgba(10, 10, 12, 0.45);
		border-radius: 10px;
		border: 1px solid rgba(255, 255, 255, 0.05);
		max-height: 300px;
		overflow-y: auto;
	}

	/* Timeline Styles */
	.timeline {
		display: flex;
		flex-direction: column;
		gap: 0;
		padding-left: 8px;
	}

	.processing-meta {
		display: grid;
		grid-template-columns: repeat(3, minmax(0, 1fr));
		gap: 10px;
		margin: 0 0 14px 0;
	}

	.pm-item {
		display: flex;
		align-items: baseline;
		justify-content: space-between;
		gap: 12px;
		padding: 10px 12px;
		border: 1px solid var(--border-subtle);
		border-radius: 8px;
		background: rgba(255, 255, 255, 0.03);
	}

	.pm-label {
		color: var(--text-tertiary);
		font-size: 11px;
		text-transform: uppercase;
		letter-spacing: 0.05em;
	}

	.pm-value {
		color: var(--text-secondary);
		font-size: 12px;
		font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, "Liberation Mono", "Courier New", monospace;
	}

	.timeline-step {
		display: flex;
		gap: 16px;
		position: relative;
		padding-bottom: 24px;
	}

	.timeline-step:last-child {
		padding-bottom: 0;
	}

	.timeline-step:not(:last-child)::before {
		content: '';
		position: absolute;
		top: 24px;
		bottom: 0;
		left: 11px;
		width: 2px;
		background: var(--border-subtle);
		border-radius: 2px;
	}

	.timeline-icon {
		width: 24px;
		height: 24px;
		border-radius: 50%;
		display: flex;
		align-items: center;
		justify-content: center;
		flex-shrink: 0;
		z-index: 1;
		background: var(--bg-panel);
		border: 2px solid var(--border-subtle);
	}

	.timeline-icon.done {
		border-color: #3fb950;
		background: rgba(63, 185, 80, 0.1);
		color: #3fb950;
	}

	.timeline-icon.active {
		border-color: #58a6ff;
		background: rgba(88, 166, 255, 0.1);
		color: #58a6ff;
		box-shadow: 0 0 0 4px rgba(88, 166, 255, 0.1);
	}

	.timeline-step:hover .timeline-icon.active {
		transform: scale(1.05);
	}

	.timeline-content {
		display: flex;
		flex-direction: column;
		gap: 4px;
		padding-top: 2px;
	}

	.timeline-text {
		font-size: 14px;
		color: var(--text-primary);
		font-weight: 500;
	}

	.timeline-time {
		font-size: 12px;
		font-variant-numeric: tabular-nums;
		font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
	}

	.time-active {
		color: #58a6ff;
		font-weight: 600;
	}

	@keyframes fadeIn {
		from { opacity: 0; }
		to { opacity: 1; }
	}

		.thinking-indicator {
			display: flex;
			align-items: center;
			gap: 8px;
			padding: 6px 10px;
			border-radius: 999px;
			background: rgba(255, 255, 255, 0.03);
			border: 1px solid rgba(255, 255, 255, 0.06);
			max-width: 100%;
			min-width: 0;
		}

		.thinking-indicator-compact {
			transform: scale(0.95);
			transform-origin: left;
		}

		.thinking-label {
			font-size: 11px;
			font-weight: 600;
			text-transform: uppercase;
			letter-spacing: 0.6px;
			color: var(--text-secondary);
			line-height: 1;
		}

		.thinking-step {
			font-size: 12px;
			color: var(--text-secondary);
			white-space: nowrap;
			overflow: hidden;
			text-overflow: ellipsis;
			line-height: 1.2;
			min-width: 0;
		}

	.truncate {
		white-space: nowrap;
		overflow: hidden;
		text-overflow: ellipsis;
	}

	.btn-danger {
		background: #e5484d;
		color: #fff;
		border: 1px solid #e5484d;
	}
	
	.btn-danger:hover {
		background: #c93c41;
	}

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
			box-shadow: 0 16px 40px rgba(0, 0, 0, 0.4);
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
		background: rgba(229, 72, 77, 0.15);
		color: #e5484d;
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

	.flex-end {
		display: flex;
		justify-content: flex-end;
	}

	.gap-12 {
		gap: 12px;
	}

	@keyframes modalIn {
		to {
			transform: scale(1);
			opacity: 1;
		}
	}
</style>
