<script lang="ts">
	import { onMount, onDestroy } from 'svelte';
	import { page } from '$app/stores';
	import { goto } from '$app/navigation';
	import { apiFetch } from '$lib/api';
	import { toast } from '$lib/toastStore';

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
	let traceEvents = $state<any[]>([]);
	let isTraceLoading = $state(false);

	// Vendor email draft (AI)
	let emailModalOpen = $state(false);
	let emailTone = $state<'professional' | 'firm' | 'friendly'>('professional');
	let emailInclude = $state<'unresolved' | 'all'>('unresolved');
	let isEmailLoading = $state(false);
	let emailDraft = $state<{ subject: string; body: string } | null>(null);
	let isCopied = $state(false);

	// Tabs state
	let activeTab = $state('overview'); // 'overview' | 'risks' | 'clauses' | 'chat' | 'obligations' | 'trace'

	// Chat state
	type ChatRole = 'user' | 'assistant';
	type ChatTurn = { role: ChatRole; content: string; sources?: { clause_type: string; text_excerpt: string; risk_level: string }[] };
	let chatMessages = $state<ChatTurn[]>([]);
	let chatInput = $state('');
	let isChatLoading = $state(false);

	// Obligations state
	type ObligationItem = {
		title: string;
		description: string;
		party_responsible: string;
		due_trigger: string;
		category: string;
	};
	let obligations = $state<ObligationItem[] | null>(null);
	let obligationsGenerated = $state(false);
	let isObligationsLoading = $state(false);

	// Filters for clauses
	let clauseSearchQuery = $state('');
	let clauseRiskFilter = $state('ALL'); // 'ALL' | 'CRITICAL' | 'HIGH' | 'MEDIUM' | 'LOW'
	let expandedClauses = $state<Record<string, boolean>>({});

	// Modals
	let deleteModalOpen = $state(false);

	// Version history and revision upload states
	let allContracts = $state<ContractDetail[]>([]);
	let versionDropdownOpen = $state(false);
	let uploadRevisionModalOpen = $state(false);
	let revisionInputType = $state<'file' | 'text'>('file');
	let revisionText = $state('');
	let isRevisionUploading = $state(false);
	let revisionFileInput = $state<HTMLInputElement | null>(null);
	let revisionFile = $state<File | null>(null);

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

	function formatDocumentName(filename: string) {
		if (!filename) return '';
		let clean = filename.replace(/\.[a-zA-Z0-9]+$/, '');
		clean = clean.replace(/[_-]/g, ' ');
		return clean.replace(/\b\w/g, c => c.toUpperCase());
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

	type ClauseMarker = { clauseId: string; risk: string; topPct: number };
	let clauseMarkers = $derived.by(() => {
		const rawText = contract?.metadata_json?.raw_text || '';
		if (!rawText || clauses.length === 0) return [] as ClauseMarker[];
		const total = Math.max(1, rawText.length);
		const markers: ClauseMarker[] = [];
		for (const clause of clauses) {
			const t = (clause.text_content || '').trim();
			if (!t) continue;
			const idx = rawText.indexOf(t);
			if (idx < 0) continue;
			const topPct = Math.max(0, Math.min(1, idx / total));
			markers.push({ clauseId: clause.id, risk: clause.risk_level, topPct });
		}
		return markers;
	});

	function jumpToClause(clauseId: string) {
		selectedClauseId = clauseId;
		const highlightEl = document.getElementById(`highlight-${clauseId}`);
		if (highlightEl) highlightEl.scrollIntoView({ behavior: 'smooth', block: 'center' });
	}

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

	async function sendChat() {
		const q = (chatInput || '').trim();
		if (!q || isChatLoading || !contract) return;

		const history = chatMessages.map((m) => ({ role: m.role, content: m.content }));
		chatMessages = [...chatMessages, { role: 'user', content: q }];
		chatInput = '';
		isChatLoading = true;

		try {
			const res = await apiFetch(`/api/v1/contracts/${contract.id}/chat`, {
				method: 'POST',
				headers: { 'Content-Type': 'application/json' },
				body: JSON.stringify({ question: q, history })
			});
			const json = await res.json().catch(() => ({}));
			if (!res.ok) throw new Error(json?.detail || 'Chat failed');

			chatMessages = [
				...chatMessages,
				{ role: 'assistant', content: json.answer || 'No answer returned.', sources: json.sources || [] }
			];
		} catch (e: any) {
			toast.error(e?.message || 'Chat failed');
			chatMessages = [...chatMessages, { role: 'assistant', content: 'Chat failed. Please try again.' }];
		} finally {
			isChatLoading = false;
		}
	}

	async function fetchObligations() {
		if (!contract || contract.status !== 'COMPLETED') return;
		isObligationsLoading = true;
		try {
			const res = await apiFetch(`/api/v1/contracts/${contract.id}/obligations`);
			const json = await res.json().catch(() => ({}));
			if (!res.ok) throw new Error(json?.detail || 'Failed to load obligations');
			obligations = json.obligations ?? null;
			obligationsGenerated = Boolean(json.generated);
		} catch (e: any) {
			toast.error(e?.message || 'Failed to load obligations');
		} finally {
			isObligationsLoading = false;
		}
	}

	async function generateObligations() {
		if (!contract || contract.status !== 'COMPLETED') return;
		isObligationsLoading = true;
		try {
			const res = await apiFetch(`/api/v1/contracts/${contract.id}/obligations/generate`, { method: 'POST' });
			const json = await res.json().catch(() => ({}));
			if (!res.ok) throw new Error(json?.detail || 'Failed to generate obligations');
			toast.success('Generating obligations…');
			// Poll until generated
			const startedAt = Date.now();
			while (Date.now() - startedAt < 30000) {
				await new Promise((r) => setTimeout(r, 1500));
				const check = await apiFetch(`/api/v1/contracts/${contract.id}/obligations`);
				const cj = await check.json().catch(() => ({}));
				if (check.ok && cj.generated) {
					obligations = cj.obligations ?? [];
					obligationsGenerated = true;
					break;
				}
			}
		} catch (e: any) {
			toast.error(e?.message || 'Failed to generate obligations');
		} finally {
			isObligationsLoading = false;
		}
	}

	async function generateVendorEmail() {
		if (!contract) return;
		const hadDraft = !!emailDraft;
		// Open the modal immediately so the user sees the loading state while we draft.
		emailModalOpen = true;
		isEmailLoading = true;
		try {
			const res = await apiFetch(`/api/v1/contracts/${contract.id}/redlines/email`, {
				method: 'POST',
				headers: { 'Content-Type': 'application/json' },
				body: JSON.stringify({ tone: emailTone, include: emailInclude })
			});
			const json = await res.json().catch(() => ({}));
			if (!res.ok) throw new Error(json?.detail || 'Failed to generate email');
			emailDraft = json.email || null;
		} catch (e: any) {
			toast.error(e?.message || 'Failed to generate email');
			// If this was the first attempt (no existing draft), don't strand the user on a skeleton.
			if (!hadDraft) emailModalOpen = false;
		} finally {
			isEmailLoading = false;
		}
	}

	async function copyEmailDraft() {
		if (!emailDraft) return;
		const text = `Subject: ${emailDraft.subject}\n\n${emailDraft.body}`;
		try {
			await navigator.clipboard.writeText(text);
			toast.success('Email copied to clipboard.');
			isCopied = true;
			setTimeout(() => {
				isCopied = false;
			}, 2000);
		} catch {
			toast.error('Failed to copy email.');
		}
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

	async function fetchContractEvents() {
		if (!contractId) return;
		isTraceLoading = true;
		try {
			const res = await apiFetch(`/api/v1/contracts/${contractId}/events`);
			if (!res.ok) return;
			const json = await res.json();
			traceEvents = json.events || [];
		} catch {
			// non-fatal
		} finally {
			isTraceLoading = false;
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
					}
					// Auto-select 'verification' tab if there are redline resolutions and it's a version and no tab has been selected yet.
					if (contract.metadata_json?.parent_contract_id && contract.metadata_json?.redline_resolutions?.length > 0 && activeTab === 'overview' && !new URL(window.location.href).searchParams.get('tab')) {
						activeTab = 'verification';
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

	async function loadVersionChain() {
		try {
			const res = await apiFetch('/api/v1/contracts');
			if (res.ok) {
				const data = await res.json();
				allContracts = data.contracts || [];
			}
		} catch (err) {
			console.error('Failed to load version chain:', err);
		}
	}

	let versionChain = $derived.by(() => {
		if (!contract || allContracts.length === 0) return [];

		// Precompute maps for O(1) lookups
		const idToContract = new Map<string, ContractDetail>();
		const parentIdToChild = new Map<string, ContractDetail>();

		for (const c of allContracts) {
			idToContract.set(c.id, c);
			if (c.metadata_json?.parent_contract_id) {
				if (!parentIdToChild.has(c.metadata_json.parent_contract_id)) {
					parentIdToChild.set(c.metadata_json.parent_contract_id, c);
				}
			}
		}
		
		// Trace back to the root parent
		let root: ContractDetail = contract;
		let visited = new Set<string>();
		
		while (root.metadata_json?.parent_contract_id && !visited.has(root.id)) {
			visited.add(root.id);
			const parent = idToContract.get(root.metadata_json.parent_contract_id);
			if (parent) {
				root = parent;
			} else {
				break;
			}
		}
		
		// Build linear chain from root downwards
		const chain: ContractDetail[] = [root];
		let currentId = root.id;
		visited.clear();
		visited.add(root.id);
		
		let nextContract = parentIdToChild.get(currentId);
		while (nextContract && !visited.has(nextContract.id)) {
			visited.add(nextContract.id);
			chain.push(nextContract);
			currentId = nextContract.id;
			nextContract = parentIdToChild.get(currentId);
		}
		
		return chain.map((c, index) => {
			const versionNum = c.metadata_json?.version_number || (index + 1);
			return {
				id: c.id,
				filename: c.filename,
				versionNumber: versionNum,
				label: versionNum === 1 ? `v1 (Original)` : `v${versionNum} (Revised)`,
				status: c.status,
				created_at: c.created_at
			};
		});
	});

	async function handleRevisionSuccess(response: any, loadingToastId: string, successMessage: string, isText: boolean) {
		toast.dismiss(loadingToastId);
		toast.success(successMessage);
		uploadRevisionModalOpen = false;
		if (isText) {
			revisionText = '';
		} else {
			revisionFile = null;
		}
		const data = await response.json();
		if (data.contract_id) {
			goto(`/contracts/${data.contract_id}`);
		} else {
			fetchContractDetails();
			loadVersionChain();
		}
	}

	async function handleRevisionFileUpload() {
		if (!revisionFile) {
			toast.error('Please select a file first.');
			return;
		}
		isRevisionUploading = true;
		const formData = new FormData();
		formData.append('file', revisionFile);

		const loadingToastId = toast.loading(`Uploading revision ${revisionFile.name}...`);
		try {
			const response = await apiFetch(`/api/v1/contracts/upload?parent_id=${contractId}`, {
				method: 'POST',
				body: formData
			});
			if (response.ok) {
				await handleRevisionSuccess(response, loadingToastId, 'Revision uploaded successfully. AI processing started.', false);
			} else {
				throw new Error('Revision upload failed');
			}
		} catch (error) {
			console.error('Revision upload error:', error);
			toast.dismiss(loadingToastId);
			toast.error('Failed to upload revision.');
		} finally {
			isRevisionUploading = false;
		}
	}

	async function handleRevisionTextUpload() {
		const text = revisionText.trim();
		if (!text) {
			toast.error('Please paste contract text first.');
			return;
		}
		isRevisionUploading = true;
		const loadingToastId = toast.loading('Submitting revision text for analysis...');
		try {
			const response = await apiFetch(`/api/v1/contracts/text?parent_id=${contractId}`, {
				method: 'POST',
				headers: { 'Content-Type': 'application/json' },
				body: JSON.stringify({ text })
			});
			if (response.ok) {
				await handleRevisionSuccess(response, loadingToastId, 'Revision text submitted. AI processing started.', true);
			} else {
				throw new Error('Revision text submit failed');
			}
		} catch (error) {
			console.error('Revision text submit error:', error);
			toast.dismiss(loadingToastId);
			toast.error('Failed to submit revision text.');
		} finally {
			isRevisionUploading = false;
		}
	}

	async function handleRevisionUpload() {
		if (revisionInputType === 'file') {
			await handleRevisionFileUpload();
		} else {
			await handleRevisionTextUpload();
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

	function isAiEventType(t: string) {
		const s = (t || '').toLowerCase();
		return s === 'llm' || s === 'embedding' || s === 'agent' || s === 'ai';
	}

	// React to contractId changes (parameter transitions)
	$effect(() => {
		if (contractId) {
			clauses = [];
			fetchContractDetails();
			loadVersionChain();
		}
	});

	onMount(() => {
		loadVersionChain();
		
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
	});

	$effect(() => {
		if (activeTab === 'obligations' && contract?.status === 'COMPLETED' && !isObligationsLoading) {
			if (obligations === null || !obligationsGenerated) fetchObligations();
		}
	});

	$effect(() => {
		if (activeTab === 'clauses' && contract?.status === 'COMPLETED' && clauses.length === 0 && !isClausesLoading) {
			fetchClauses();
		}
	});

	$effect(() => {
		if (activeTab === 'trace' && contract?.status === 'PROCESSING') {
			fetchContractEvents();
		}
	});

	// Reactively start/stop the stopwatch based on processing status
	$effect(() => {
		if (contract?.status === 'PROCESSING') {
			if (!stopwatchInterval) {
				stopwatchInterval = setInterval(() => {
					now = Date.now();
				}, 100);
			}
		} else {
			if (stopwatchInterval) {
				clearInterval(stopwatchInterval);
				stopwatchInterval = null;
			}
		}
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
			<a href="/contracts" class="crumb crumb-link">Contract Repository</a>
			<span class="separator">›</span>
			<div class="version-select-container">
				<button class="crumb active version-dropdown-trigger" onclick={() => versionDropdownOpen = !versionDropdownOpen} aria-expanded={versionDropdownOpen}>
					<span>{formatDocumentName(contract.filename)}</span>
					{#if versionChain.length > 1}
						<span class="version-badge">v{contract.metadata_json?.version_number || 1}</span>
						<svg class="dropdown-chevron" class:open={versionDropdownOpen} width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><polyline points="6 9 12 15 18 9"/></svg>
					{/if}
				</button>
				{#if versionDropdownOpen && versionChain.length > 1}
					<div class="version-dropdown-menu">
						<div class="dropdown-header">Version History</div>
						{#each versionChain as ver}
							<a href="/contracts/{ver.id}" class="version-item" class:active={ver.id === contract.id} onclick={() => versionDropdownOpen = false}>
								<div class="version-item-left">
									<span class="version-item-badge">{ver.label}</span>
									<span class="version-item-date">{timeAgo(ver.created_at)}</span>
								</div>
								{#if ver.id === contract.id}
									<svg class="check-icon" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><polyline points="20 6 9 17 4 12"/></svg>
								{/if}
							</a>
						{/each}
					</div>
				{/if}
			</div>
		</div>
		<div class="cockpit-actions">
			{#if contract.status === 'COMPLETED'}
				<button class="btn btn-secondary btn-compact btn-ai" onclick={generateVendorEmail} disabled={isEmailLoading} title="Generate a vendor email summarizing requested redlines (AI)">
					{#if isEmailLoading}
						<span class="spinner spinner-sm"></span>
						Drafting…
					{:else}
						<svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><path d="M21.75 6.75v10.5a2.25 2.25 0 0 1-2.25 2.25h-15a2.25 2.25 0 0 1-2.25-2.25V6.75m19.5 0A2.25 2.25 0 0 0 19.5 4.5h-15a2.25 2.25 0 0 0-2.25 2.25m19.5 0v.243a2.25 2.25 0 0 1-1.07 1.916l-7.5 4.615a2.25 2.25 0 0 1-2.36 0L3.32 8.91a2.25 2.25 0 0 1-1.07-1.916V6.75"/></svg>
						Email Vendor
					{/if}
				</button>
				<button class="btn btn-primary btn-compact" onclick={() => uploadRevisionModalOpen = true} title="Upload Revision / Next Version">
					<svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="17 8 12 3 7 8"/><line x1="12" y1="3" x2="12" y2="15"/></svg>
					Upload Revision
				</button>
			{/if}
			{#if contract.status === 'FAILED' || contract.status === 'COMPLETED'}
				<button class="btn btn-secondary btn-compact" onclick={handleReprocess} title="Reprocess Contract">
					<svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><path d="M3 12a9 9 0 1 0 9-9 9.75 9.75 0 0 0-6.74 2.74L3 8"/><path d="M3 3v5h5"/></svg>
					Reprocess
				</button>
			{/if}
			<button class="btn btn-secondary btn-danger-action btn-compact" onclick={() => deleteModalOpen = true} title="Delete Contract">
				<svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><path d="M3 6h18"></path><path d="M19 6v14c0 1-1 2-2 2H7c-1 0-2-1-2-2V6"></path><path d="M8 6V4c0-1 1-2 2-2h4c1 0 2 1 2 2v2"></path></svg>
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
				{#if clauseMarkers.length > 0}
					<div class="clause-minimap" aria-hidden="true">
						{#each clauseMarkers as m (m.clauseId)}
							<button
								type="button"
								class="minimap-dot risk-{m.risk.toLowerCase()} {selectedClauseId === m.clauseId ? 'active' : ''}"
								style="top: {m.topPct * 100}%;"
								onclick={() => jumpToClause(m.clauseId)}
								title={m.risk}
							></button>
						{/each}
					</div>
				{/if}
				<!-- svelte-ignore a11y_click_events_have_key_events -->
				<!-- svelte-ignore a11y_no_static_element_interactions -->
				<!-- svelte-ignore a11y_mouse_events_have_key_events -->
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
			<div class="analysis-tabs" role="tablist" aria-label="Contract Analysis Tabs">
				<button role="tab" aria-selected={activeTab === 'overview'} class="tab-btn" class:active={activeTab === 'overview'} onclick={() => activeTab = 'overview'}>
					<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="3" y="3" width="18" height="18" rx="2"/><path d="M3 9h18M9 21V9"/></svg>
					Overview
				</button>
				{#if contract.status === 'COMPLETED'}
					<button role="tab" aria-selected={activeTab === 'risks'} class="tab-btn" class:active={activeTab === 'risks'} onclick={() => activeTab = 'risks'}>
						<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"/><line x1="12" y1="9" x2="12" y2="13"/><line x1="12" y1="17" x2="12.01" y2="17"/></svg>
						Key Risks
					</button>
					<button role="tab" aria-selected={activeTab === 'clauses'} class="tab-btn" class:active={activeTab === 'clauses'} onclick={() => activeTab = 'clauses'}>
						<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="8" y1="6" x2="21" y2="6"/><line x1="8" y1="12" x2="21" y2="12"/><line x1="8" y1="18" x2="21" y2="18"/><line x1="3" y1="6" x2="3.01" y2="6"/><line x1="3" y1="12" x2="3.01" y2="12"/><line x1="3" y1="18" x2="3.01" y2="18"/></svg>
						Smart Clauses ({clauses.length})
					</button>
					<button role="tab" aria-selected={activeTab === 'chat'} class="tab-btn" class:active={activeTab === 'chat'} onclick={() => activeTab = 'chat'}>
						<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 15a4 4 0 0 1-4 4H7l-4 4V7a4 4 0 0 1 4-4h10a4 4 0 0 1 4 4z"/></svg>
						Ask
					</button>
					<button role="tab" aria-selected={activeTab === 'obligations'} class="tab-btn" class:active={activeTab === 'obligations'} onclick={() => activeTab = 'obligations'}>
						<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M9 11l3 3L22 4"/><path d="M21 12v7a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11"/></svg>
						Obligations
					</button>
					{#if contract.metadata_json?.parent_contract_id}
						<button role="tab" aria-selected={activeTab === 'verification'} class="tab-btn" class:active={activeTab === 'verification'} onclick={() => activeTab = 'verification'}>
							<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M22 11.08V12a10 10 0 1 1-5.93-9.14"/><polyline points="22 4 12 14.01 9 11.01"/></svg>
							Redline Verification
						</button>
					{/if}
				{/if}
				{#if contract.status === 'PROCESSING'}
					<button role="tab" aria-selected={activeTab === 'trace'} class="tab-btn" class:active={activeTab === 'trace'} onclick={() => activeTab = 'trace'}>
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
								<div class="meta-card bg-panel-glow">
									<span class="mc-label">Filename</span>
									<span class="mc-value truncate" title={contract.filename}>{formatDocumentName(contract.filename)}</span>
								</div>
								<div class="meta-card bg-panel-glow">
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
								<div class="meta-card bg-panel-glow">
									<span class="mc-label">Uploaded</span>
									<span class="mc-value">{timeAgo(contract.created_at)}</span>
								</div>
								<div class="meta-card bg-panel-glow">
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
									<div class="matrix-item bg-critical-glow">
										<span class="matrix-count text-critical">{contract.metadata_json?.risk_counts?.CRITICAL || 0}</span>
										<span class="matrix-label">Critical</span>
									</div>
									<div class="matrix-item bg-high-glow">
										<span class="matrix-count text-high">{contract.metadata_json?.risk_counts?.HIGH || 0}</span>
										<span class="matrix-label">High</span>
									</div>
									<div class="matrix-item bg-medium-glow">
										<span class="matrix-count text-medium">{contract.metadata_json?.risk_counts?.MEDIUM || 0}</span>
										<span class="matrix-label">Medium</span>
									</div>
									<div class="matrix-item bg-low-glow">
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
									<div class="risk-glow-card risk-{(r.risk_level || 'LOW').toLowerCase()}">
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
									aria-label="Search clauses by keyword"
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
									<div 
										id="clause-card-{clause.id}"
										class="clause-interactive-card risk-{clause.risk_level.toLowerCase()} {isExpanded ? 'expanded' : ''} {selectedClauseId === clause.id || hoveredClauseId === clause.id ? 'active-card' : ''}" 
										role="button"
										tabindex="0"
										onmouseenter={() => { hoveredClauseId = clause.id; }}
										onmouseleave={() => { if (hoveredClauseId === clause.id) hoveredClauseId = null; }}
										onclick={() => handleClauseCardClick(clause.id)}
										onkeydown={(e: KeyboardEvent) => {
											if (e.key === 'Enter' || e.key === ' ') {
												const target = e.target as HTMLElement | null;
												if (!target || !target.closest('button')) {
													e.preventDefault();
													handleClauseCardClick(clause.id);
												}
											}
										}}
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
											<div class="clause-expanded-section" role="presentation" onclick={(e) => e.stopPropagation()} onkeydown={(e) => e.stopPropagation()}>
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
													<!-- svelte-ignore a11y_no_noninteractive_element_interactions -->
													<details class="clause-tech" onclick={(e) => e.stopPropagation()} onkeydown={(e) => e.stopPropagation()}>
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

				<!-- ASK (CHAT) TAB -->
				{#if activeTab === 'chat' && contract.status === 'COMPLETED'}
					<div class="tab-content flex-col chat-tab">
						<div class="chat-panel bg-panel-glow">
							<div class="chat-panel-header">
								<div>
									<div class="flex-row gap-8" style="margin-bottom: 2px;">
										<div class="subsection-title" style="margin: 0;">Ask this contract</div>
										<span class="ai-badge" title="Generated by AI. Verify against contract text.">
											<svg class="ai-icon" width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 2l1.2 4.3L18 8l-4.8 1.7L12 14l-1.2-4.3L6 8l4.8-1.7L12 2z"/><path d="M19 13l.8 2.8L22 17l-2.2.8L19 20l-.8-2.2L16 17l2.2-1.2L19 13z"/></svg>
											AI
										</span>
									</div>
									<div class="text-tertiary text-xs margin-top-6">Answers are grounded in the most relevant clauses.</div>
								</div>
								<button class="btn btn-secondary btn-compact" onclick={() => (chatMessages = [])} disabled={chatMessages.length === 0 || isChatLoading}>
									Clear
								</button>
							</div>

							<div class="chat-history">
							{#if chatMessages.length === 0}
								<div class="chat-empty">
									<div class="chat-empty-title">Ask anything about terms, deadlines, and risk.</div>
									<div class="chat-empty-sub text-tertiary">Examples:</div>
									<div class="chat-suggestions">
										<button class="suggestion-pill" onclick={() => (chatInput = 'What are the termination notice requirements?')}>Termination notice</button>
										<button class="suggestion-pill" onclick={() => (chatInput = 'Are there any auto-renewal terms or opt-out deadlines?')}>Auto-renewal</button>
										<button class="suggestion-pill" onclick={() => (chatInput = 'Summarize key vendor obligations and our obligations.')}>Obligations summary</button>
										<button class="suggestion-pill" onclick={() => (chatInput = 'What is the limitation of liability and are there any carve-outs?')}>Liability caps</button>
									</div>
								</div>
							{:else}
								{#each chatMessages as m, idx (idx)}
									<div class="chat-message {m.role}">
										<div class="chat-bubble">
											<div class="chat-role">{m.role === 'user' ? 'You' : 'ContractsPulse'}</div>
											{#if m.role === 'assistant'}
												<div class="ai-chip" style="margin-bottom: 8px;" title="This response was generated by AI.">
													<svg class="ai-icon" width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 2l1.2 4.3L18 8l-4.8 1.7L12 14l-1.2-4.3L6 8l4.8-1.7L12 2z"/></svg>
													AI answer
												</div>
											{/if}
											<div class="chat-content">{m.content}</div>
											{#if m.role === 'assistant' && m.sources && m.sources.length}
												<div class="chat-sources">
													{#each m.sources as s (s.clause_type + s.text_excerpt)}
														<button class="source-pill" type="button" title={s.text_excerpt}>
															<span class="badge badge-{s.risk_level === 'CRITICAL' || s.risk_level === 'HIGH' ? 'danger' : s.risk_level === 'MEDIUM' ? 'warning' : 'success'}" style="height: 18px; padding: 0 8px;">
																{s.risk_level}
															</span>
															<span class="source-pill-text">{s.clause_type}</span>
														</button>
													{/each}
												</div>
											{/if}
										</div>
									</div>
								{/each}
							{/if}
						</div>
						</div>

						<div class="chat-composer">
							<textarea
								class="chat-textarea"
								rows="1"
								placeholder="Ask a question…"
								bind:value={chatInput}
								disabled={isChatLoading}
								aria-label="Ask a question"
								onkeydown={(e) => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); sendChat(); } }}
							></textarea>
							<button class="btn btn-primary chat-send" onclick={sendChat} disabled={isChatLoading || !chatInput.trim()} aria-label="Send question">
								{#if isChatLoading}
									<span class="spinner spinner-sm"></span>
								{:else}
									<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M22 2L11 13"/><path d="M22 2l-7 20-4-9-9-4z"/></svg>
								{/if}
							</button>
						</div>
					</div>
				{/if}

				<!-- OBLIGATIONS TAB -->
				{#if activeTab === 'obligations' && contract.status === 'COMPLETED'}
					<div class="tab-content flex-col scroll-container">
						<div class="overview-section">
							<div class="flex-row gap-8" style="margin-bottom: 8px;">
								<h3 class="subsection-title" style="margin: 0;">Actionable Obligations</h3>
								<span class="ai-badge" title="Generated by AI. Verify against contract text.">
									<svg class="ai-icon" width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 2l1.2 4.3L18 8l-4.8 1.7L12 14l-1.2-4.3L6 8l4.8-1.7L12 2z"/></svg>
									AI
								</span>
							</div>

							{#if isObligationsLoading}
								<div class="clauses-loading">
									<span class="spinner spinner-md"></span>
									<p>Loading obligations...</p>
								</div>
							{:else if obligationsGenerated && obligations && obligations.length === 0}
								<div class="empty-tab-state">
									<p class="text-tertiary">No actionable obligations were extracted.</p>
								</div>
							{:else if obligationsGenerated && obligations}
								<div class="obligations-list">
									{#each obligations as o (o.title + o.category + o.due_trigger)}
										<div class="obligation-card bg-panel-glow">
											<div class="obligation-head flex-between">
												<span class="font-semibold">{o.title}</span>
												<span class="badge badge-secondary">{o.category}</span>
											</div>
											<div class="ai-chip" style="margin-top: 10px;" title="Extracted by AI">
												<svg class="ai-icon" width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M19 13l.8 2.8L22 17l-2.2.8L19 20l-.8-2.2L16 17l2.2-1.2L19 13z"/></svg>
												AI extracted
											</div>
											{#if o.description}<div class="text-secondary text-sm margin-top-8">{o.description}</div>{/if}
											<div class="obligation-meta margin-top-10">
												<div><span class="text-tertiary">Party:</span> {o.party_responsible || '--'}</div>
												<div><span class="text-tertiary">Trigger:</span> {o.due_trigger || '--'}</div>
											</div>
										</div>
									{/each}
								</div>
							{:else}
								<div class="empty-tab-state">
									<p class="text-tertiary">Obligations have not been generated for this contract yet.</p>
									<button class="btn btn-primary margin-top-12" onclick={generateObligations} disabled={isObligationsLoading}>
										{#if isObligationsLoading}
											<span class="spinner spinner-sm"></span> Generating...
										{:else}
											Generate Obligations
										{/if}
									</button>
								</div>
							{/if}
						</div>
					</div>
				{/if}

				<!-- SYSTEM TRACE TAB (only for PROCESSING status) -->
				{#if activeTab === 'trace' && contract.status === 'PROCESSING'}
					<div class="tab-content flex-col">
						<div class="overview-section">
							<div class="flex-between" style="align-items: flex-end;">
								<div>
									<h3 class="subsection-title" style="margin-bottom: 4px;">System Trace</h3>
									<div class="text-tertiary text-xs">API-level events and pipeline steps as they happen.</div>
								</div>
								<button class="btn btn-secondary btn-compact" onclick={fetchContractEvents} disabled={isTraceLoading}>
									Refresh
								</button>
							</div>

							{#if isTraceLoading && traceEvents.length === 0}
								<div class="clauses-loading">
									<span class="spinner spinner-md"></span>
									<p>Loading events…</p>
								</div>
							{:else if traceEvents.length === 0}
								<div class="empty-tab-state">
									<p class="text-tertiary">No events yet.</p>
								</div>
							{:else}
								<div class="events-list bg-panel-glow">
									{#each traceEvents as e (e.id)}
										<details class="event-row">
											<summary class="event-summary">
												{#if isAiEventType(e.event_type)}
													<span class="ai-chip" title="AI request/response">
														<svg class="ai-icon" width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 2l1.2 4.3L18 8l-4.8 1.7L12 14l-1.2-4.3L6 8l4.8-1.7L12 2z"/></svg>
														AI
													</span>
												{:else}
													<span class="badge badge-secondary">{e.event_type}</span>
												{/if}
												<span class="event-message">{e.message}</span>
												<span class="event-time text-tertiary font-mono">{timeAgo(e.created_at)}</span>
											</summary>
											{#if e.payload_json && Object.keys(e.payload_json).length}
												<pre class="event-payload">{JSON.stringify(e.payload_json, null, 2)}</pre>
											{/if}
										</details>
									{/each}
								</div>
							{/if}
						</div>
					</div>
				{/if}

				<!-- REDLINE VERIFICATION TAB -->
				{#if activeTab === 'verification' && contract.status === 'COMPLETED'}
					{@const resolutions = contract.metadata_json?.redline_resolutions || []}
					{@const resolvedCount = resolutions.filter((r: any) => r.status === 'RESOLVED').length}
					{@const partialCount = resolutions.filter((r: any) => r.status === 'PARTIALLY_RESOLVED').length}
					{@const unresolvedCount = resolutions.filter((r: any) => r.status === 'UNRESOLVED').length}
					<div class="tab-content flex-col gap-24">
						<div class="verification-header bg-panel-glow">
							<div class="vh-left">
								<svg class="verify-icon" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M22 11.08V12a10 10 0 1 1-5.93-9.14"/><polyline points="22 4 12 14.01 9 11.01"/></svg>
								<div>
									<h3 class="subsection-title margin-bottom-4" style="margin: 0;">Redline Verification Cockpit</h3>
									<p class="text-tertiary font-size-12" style="margin: 4px 0 0 0;">AI Senior Counsel audit of counterparty edits compared to v1 recommended redlines.</p>
								</div>
							</div>
							<div class="vh-right">
								<div class="vh-stats">
									<div class="vstat-badge success">
										<span class="vstat-num">{resolvedCount}</span>
										<span class="vstat-label">Resolved</span>
									</div>
									<div class="vstat-badge warning">
										<span class="vstat-num">{partialCount}</span>
										<span class="vstat-label">Partial</span>
									</div>
									<div class="vstat-badge danger">
										<span class="vstat-num">{unresolvedCount}</span>
										<span class="vstat-label">Remaining</span>
									</div>
								</div>
							</div>
						</div>

						<div class="resolutions-list flex-col gap-16">
							{#each contract.metadata_json?.redline_resolutions || [] as resolution}
								<div class="resolution-card bg-panel-glow">
									<div class="rc-header">
										<div class="rc-header-left">
											<span class="clause-type-tag">{resolution.clause_type}</span>
											<span class="risk-pill risk-{resolution.parent_risk_level?.toLowerCase()}" title="Original risk level">
												<span class="rp-label">Originally</span>
												<span class="rp-level">{(resolution.parent_risk_level || '').toLowerCase()}</span>
											</span>
										</div>
										<span class="badge {resolution.status === 'RESOLVED' ? 'badge-success' : resolution.status === 'PARTIALLY_RESOLVED' ? 'badge-warning' : 'badge-danger'}">
											{resolution.status === 'RESOLVED' ? 'Resolved' : resolution.status === 'PARTIALLY_RESOLVED' ? 'Partially Resolved' : 'Unresolved'}
										</span>
									</div>

									<div class="rc-comparison-grid">
										<div class="pane pane-original">
											<div class="pane-label">Original Text (v1)</div>
											<div class="pane-content text-strikethrough">{resolution.parent_text}</div>
											{#if resolution.parent_redline_suggestion}
												<div class="redline-rec bg-hover">
													<div class="rr-label">Our Proposed Redline:</div>
													<div class="rr-text">{resolution.parent_redline_suggestion}</div>
												</div>
											{/if}
										</div>
										<div class="pane pane-revised">
											<div class="pane-label">Revised Text (v{contract.metadata_json?.version_number || 2})</div>
											<div class="pane-content highlight-revised">{resolution.new_text}</div>
										</div>
									</div>

									<div class="rc-explanation bg-active">
										<div class="ex-header">
											<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/></svg>
											<span>AI Senior Counsel Verdict:</span>
										</div>
										<p class="ex-body">{resolution.verification_details}</p>
									</div>
								</div>
							{:else}
								<div class="empty-state bg-panel-glow">
									<svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/></svg>
									<p class="text-secondary" style="margin-top: 8px;">No redline resolutions were processed for this revision.</p>
								</div>
							{/each}
						</div>
					</div>
				{/if}
			</div>
		</div>
	</div>
{/if}

{#if emailModalOpen}
	<div class="modal-root">
		<button type="button" class="modal-backdrop" aria-label="Close" onclick={() => (emailModalOpen = false)}></button>
		<div class="modal-content modal-content-wide email-composer" role="dialog" aria-modal="true">
			<!-- macOS Window Controls Decoration -->
			<div class="email-mac-buttons">
				<button class="mac-dot mac-close" onclick={() => (emailModalOpen = false)} aria-label="Close"></button>
				<div class="mac-dot mac-minimize"></div>
				<div class="mac-dot mac-maximize"></div>
			</div>
			
			<div class="modal-header email-composer-header">
				<div class="modal-icon warning" style="background: rgba(var(--ai-rgb), 0.12); color: var(--ai); border: none;">
					<svg class="ai-icon animate-pulse" width="18" height="18" viewBox="0 0 24 24" fill="currentColor" stroke="none"><path d="M12 6l1.2 4.3L18 12l-4.8 1.7L12 18l-1.2-4.3L6 12l4.8-1.7L12 6z"/></svg>
				</div>
				<div>
					<h3 class="font-semibold" style="margin: 0; font-size: 16px;">AI Negotiation Counsel</h3>
					<div class="text-tertiary" style="font-size: 11px; margin-top: 2px;">Drafts polished supplier communications explaining recommended contract changes.</div>
				</div>
			</div>
			
			<div class="modal-body email-composer-body">
				<!-- Settings controls -->
				<div class="email-composer-controls">
					<div class="control-group">
						<label for="email-tone-select">Tone</label>
						<div class="custom-select-wrapper">
							<select id="email-tone-select" class="custom-select" bind:value={emailTone}>
								<option value="professional">Professional</option>
								<option value="friendly">Friendly</option>
								<option value="firm">Firm</option>
							</select>
						</div>
					</div>
					<div class="control-group">
						<label for="email-include-select">Include</label>
						<div class="custom-select-wrapper">
							<select id="email-include-select" class="custom-select" bind:value={emailInclude}>
								<option value="unresolved">Unresolved only</option>
								<option value="all">All items</option>
							</select>
						</div>
					</div>
					
					<div class="control-spacer"></div>
					
					<button class="btn btn-secondary btn-compact btn-ai btn-regenerate" onclick={generateVendorEmail} disabled={isEmailLoading}>
						<svg class="icon-spin {isEmailLoading ? 'spin' : ''}" width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21.5 2v6h-6M21.34 15.57a10 10 0 1 1-.57-8.38l5.67-5.67"/></svg>
						Regenerate
					</button>
				</div>

				{#if !emailDraft || isEmailLoading}
					<div class="email-loading-pane bg-panel-glow">
						<div class="email-loading-status">
							<span class="spinner spinner-sm"></span>
							<span class="email-loading-text">AI Counsel is drafting your vendor email…</span>
						</div>
						<div class="loading-envelope-headers">
							<div class="loading-row">
								<div class="loading-label skeleton"></div>
								<div class="loading-value skeleton"></div>
							</div>
							<div class="loading-row">
								<div class="loading-label skeleton"></div>
								<div class="loading-value skeleton"></div>
							</div>
							<div class="loading-row">
								<div class="loading-label skeleton"></div>
								<div class="loading-value skeleton"></div>
							</div>
						</div>
						<div class="loading-body">
							<div class="loading-line skeleton width-70"></div>
							<div class="loading-line skeleton width-90"></div>
							<div class="loading-line skeleton width-80"></div>
							<div class="loading-line skeleton width-50"></div>
						</div>
					</div>
				{:else}
					<!-- CRM Email Workspace -->
					<div class="email-workspace bg-panel-glow">
						<!-- Mail Header Info -->
						<div class="email-envelope-headers">
							<div class="envelope-row">
								<span class="env-label">From:</span>
								<div class="env-value">
									<span class="env-tag env-tag-ai">AI Procurement Agent</span>
									<span class="env-address">&lt;assistant@contractspulse.ai&gt;</span>
								</div>
							</div>
							<div class="envelope-row">
								<span class="env-label">To:</span>
								<div class="env-value">
									<span class="env-tag">{contract?.metadata_json?.company || 'Vendor Representative'}</span>
									{#if contract?.metadata_json?.company}
										<span class="env-address">&lt;contracts@{(contract?.metadata_json?.company || '').toLowerCase().replace(/[^a-z0-9]/g, '') || 'vendor'}.com&gt;</span>
									{/if}
								</div>
							</div>
							<div class="envelope-row">
								<span class="env-label">Subject:</span>
								<div class="env-value subject-value font-semibold">{emailDraft.subject}</div>
							</div>
						</div>
						
						<!-- Mail Message Body Pane -->
						<div class="email-body-pane">
							<pre class="email-body-text">{emailDraft.body}</pre>
						</div>
					</div>
				{/if}
			</div>
			
			<div class="modal-footer email-composer-footer">
				<button class="btn btn-secondary" onclick={() => (emailModalOpen = false)}>Close</button>
				<button class="btn btn-primary btn-copy-draft {isCopied ? 'copied' : ''}" onclick={copyEmailDraft} disabled={!emailDraft || isEmailLoading}>
					<div class="copy-state-wrapper">
						<span class="copy-state copy-state-default {isCopied ? 'state-hidden' : ''}">
							<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
								<rect x="9" y="9" width="13" height="13" rx="2" ry="2"/><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"/>
							</svg>
							<span>Copy Email Draft</span>
						</span>
						<span class="copy-state copy-state-success {isCopied ? 'state-visible' : ''}">
							<svg class="copy-icon-success" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><polyline points="20 6 9 17 4 12"/></svg>
							<span>Copied!</span>
						</span>
					</div>
				</button>
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

<!-- Upload Revision Modal -->
{#if uploadRevisionModalOpen}
	<div class="modal-root">
		<button type="button" class="modal-backdrop" aria-label="Close" onclick={() => { uploadRevisionModalOpen = false; revisionFile = null; }}></button>
		<div class="modal-content" role="dialog" aria-modal="true">
			<div class="modal-header">
				<div class="modal-icon">
					<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="17 8 12 3 7 8"/><line x1="12" y1="3" x2="12" y2="15"/></svg>
				</div>
				<h3>Upload Revised Version</h3>
			</div>
			<div class="modal-body">
				<div class="tabs-nav-modal" role="tablist" aria-label="Upload Method">
					<button class="tab-nav-modal-btn" role="tab" aria-selected={revisionInputType === 'file'} class:active={revisionInputType === 'file'} onclick={() => { revisionInputType = 'file'; revisionFile = null; }}>
						Upload Document
					</button>
					<button class="tab-nav-modal-btn" role="tab" aria-selected={revisionInputType === 'text'} class:active={revisionInputType === 'text'} onclick={() => { revisionInputType = 'text'; revisionText = ''; }}>
						Paste contract text
					</button>
				</div>

				{#if revisionInputType === 'file'}
					<div class="upload-dropzone" role="button" tabindex="0" onclick={() => revisionFileInput?.click()} onkeydown={(e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); revisionFileInput?.click(); } }}>
						<input type="file" bind:this={revisionFileInput} onchange={(e) => {
							const target = e.target as HTMLInputElement;
							if (target.files && target.files.length > 0) {
								revisionFile = target.files[0];
							}
						}} style="display: none;" accept=".pdf,.docx,.txt" />
						<div class="dropzone-label">
							<svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="17 8 12 3 7 8"/><line x1="12" y1="3" x2="12" y2="15"/></svg>
							<span>Click to select contract document</span>
							<span class="dropzone-subtitle">PDF, DOCX, or TXT up to 10MB</span>
						</div>
					</div>
					{#if revisionFile}
						<div class="selected-file-banner">
							<div class="flex-row gap-8 align-center">
								<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/></svg>
								<span>{revisionFile.name} ({(revisionFile.size / 1024).toFixed(0)} KB)</span>
							</div>
							<button class="btn-remove-file" onclick={() => revisionFile = null} aria-label="Remove selected file" title="Remove file">
								<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>
							</button>
						</div>
					{/if}
				{:else}
					<div class="textarea-container flex-col gap-6">
						<label for="revision-paste-text" class="text-secondary font-size-12 font-weight-500">Paste contract text</label>
						<textarea id="revision-paste-text" bind:value={revisionText} placeholder="Paste the updated agreement text here..." rows="8" class="input-field" style="resize: vertical; font-family: monospace; font-size: 12px;"></textarea>
					</div>
				{/if}
			</div>
			<div class="modal-footer flex-end gap-12">
				<button class="btn btn-secondary" onclick={() => { uploadRevisionModalOpen = false; revisionFile = null; revisionText = ''; }} disabled={isRevisionUploading}>Cancel</button>
				<button class="btn btn-primary" onclick={handleRevisionUpload} disabled={isRevisionUploading || (revisionInputType === 'file' && !revisionFile) || (revisionInputType === 'text' && !revisionText.trim())}>
					{#if isRevisionUploading}
						<span class="spinner spinner-sm"></span> Processing...
					{:else}
						Start Version Analysis
					{/if}
				</button>
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

	.cockpit-header .breadcrumbs {
		margin-bottom: 0;
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
		color: var(--color-high);
	}

	.btn-danger-action:hover {
		background: rgba(248, 81, 73, 0.15);
		border-color: rgba(248, 81, 73, 0.35);
	}

	/* Main Split Screen Wrapper */
	.cockpit-wrapper {
		display: grid;
		grid-template-columns: minmax(520px, 58%) minmax(420px, 42%);
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
		position: relative;
		flex: 1;
		overflow-y: auto;
		padding: 24px;
		display: flex;
		justify-content: center;
		background: var(--bg-app);
	}

	.clause-minimap {
		position: absolute;
		right: 10px;
		top: 12px;
		bottom: 12px;
		width: 12px;
		border-radius: 999px;
		background: rgba(0, 0, 0, 0.03);
		border: 1px solid var(--border-subtle);
		overflow: hidden;
		z-index: 5;
	}
	:global([data-theme="dark"]) .clause-minimap {
		background: rgba(255, 255, 255, 0.04);
	}
	.minimap-dot {
		position: absolute;
		left: 50%;
		transform: translate(-50%, -50%);
		width: 8px;
		height: 8px;
		border-radius: 999px;
		border: 1px solid rgba(255, 255, 255, 0.65);
		opacity: 0.85;
		cursor: pointer;
		padding: 0;
	}
	.minimap-dot:hover {
		opacity: 1;
		transform: translate(-50%, -50%) scale(1.15);
	}
	.minimap-dot.active {
		box-shadow: var(--ring-strong);
		opacity: 1;
	}
	.minimap-dot.risk-low { background: var(--color-low); }
	.minimap-dot.risk-medium { background: var(--color-medium); }
	.minimap-dot.risk-high { background: var(--color-high); }
	.minimap-dot.risk-critical { background: var(--color-critical); }

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
		overflow-wrap: break-word;
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
		transition: color 120ms var(--ease-out), background 120ms var(--ease-out), border-color 120ms var(--ease-out), transform 120ms var(--ease-out);
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

	.text-critical { color: var(--color-critical); }
	.text-high { color: var(--color-high); }
	.text-medium { color: var(--color-medium); }
	.text-low { color: var(--color-low); }

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
		transition: border-color 200ms var(--ease-out), box-shadow 200ms var(--ease-out), background 200ms var(--ease-out);
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
		color: var(--color-medium);
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
		border-radius: 6px;
		cursor: pointer;
		transition: color 120ms ease, background 120ms ease, border-color 120ms ease;
		user-select: none;
	}

	.filter-pill:hover {
		color: var(--text-primary);
		border-color: var(--border-strong);
	}

	.filter-pill.active {
		color: var(--text-on-accent);
		border-color: var(--border-strong);
		background: var(--bg-hover);
	}

	.filter-pill-critical.active {
		background: rgba(255, 59, 48, 0.15);
		color: var(--color-critical);
		border-color: rgba(255, 59, 48, 0.4);
	}

	.filter-pill-high.active {
		background: rgba(248, 81, 73, 0.15);
		color: var(--color-high);
		border-color: rgba(248, 81, 73, 0.4);
	}

	.filter-pill-medium.active {
		background: rgba(210, 153, 34, 0.12);
		color: var(--color-medium);
		border-color: rgba(210, 153, 34, 0.35);
	}

	.filter-pill-low.active {
		background: rgba(63, 185, 80, 0.12);
		color: var(--color-low);
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
		transition: border-color 200ms var(--ease-out), background 200ms var(--ease-out), box-shadow 200ms var(--ease-out), transform 200ms var(--ease-out);
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
		overflow-wrap: break-word;
		margin: 0;
	}

	.clause-tech {
		border: 1px solid var(--border-subtle);
		border-radius: 6px;
		padding: 8px 12px;
		background: var(--bg-hover);
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
		background: var(--bg-hover);
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
		color: var(--color-low);
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
		color: var(--color-high);
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

	/* Version select and dropdown */
	.version-select-container {
		position: relative;
		display: inline-block;
	}
	.version-dropdown-trigger {
		background: transparent;
		border: none;
		display: inline-flex;
		align-items: center;
		gap: 6px;
		cursor: pointer;
		font-size: 13px;
		font-weight: 500;
		color: var(--text-primary);
		padding: 2px 6px;
		border-radius: 6px;
		transition: background-color 150ms var(--ease-out);
	}
	.version-dropdown-trigger:hover {
		background-color: var(--bg-hover);
	}
	.version-dropdown-trigger:active {
		transform: scale(0.97);
	}
	.version-badge {
		background: var(--bg-active);
		color: var(--text-secondary);
		font-size: 10px;
		padding: 1px 5px;
		border-radius: 4px;
		font-weight: 600;
	}
	.dropdown-chevron {
		transition: transform 150ms var(--ease-out);
		color: var(--text-tertiary);
	}
	.dropdown-chevron.open {
		transform: rotate(180deg);
	}
	.version-dropdown-menu {
		position: absolute;
		top: calc(100% + 4px);
		left: 0;
		z-index: 1000;
		min-width: 220px;
		background: var(--bg-sidebar);
		border: 1px solid var(--border-subtle);
		border-radius: 6px;
		box-shadow: var(--shadow-lg);
		padding: 4px;
		display: flex;
		flex-direction: column;
	}
	.dropdown-header {
		font-size: 11px;
		text-transform: uppercase;
		font-weight: 600;
		color: var(--text-tertiary);
		padding: 6px 12px;
		letter-spacing: 0.05em;
	}
	.version-item {
		display: flex;
		align-items: center;
		justify-content: space-between;
		padding: 8px 12px;
		border-radius: 6px;
		text-decoration: none;
		color: var(--text-secondary);
		transition: background-color 120ms var(--ease-out), color 120ms var(--ease-out);
	}
	.version-item:hover {
		background-color: var(--bg-hover);
		color: var(--text-primary);
	}
	.version-item.active {
		background-color: var(--bg-active);
		color: var(--text-primary);
		font-weight: 500;
	}
	.version-item-left {
		display: flex;
		flex-direction: column;
		gap: 2px;
	}
	.version-item-badge {
		font-size: 12px;
	}
	.version-item-date {
		font-size: 10px;
		color: var(--text-tertiary);
	}
	.check-icon {
		color: var(--accent-primary);
	}

	/* Verification tab styles */
	.verification-header {
		display: flex;
		justify-content: space-between;
		align-items: center;
		padding: 16px 20px;
		border-radius: 8px;
		border: 1px solid var(--border-subtle);
		gap: 16px;
	}
	.vh-left {
		display: flex;
		align-items: center;
		gap: 12px;
	}
	.verify-icon {
		color: #3fb950;
	}
	.vh-stats {
		display: flex;
		gap: 8px;
	}
	.vstat-badge {
		display: flex;
		flex-direction: column;
		align-items: center;
		justify-content: center;
		padding: 6px 12px;
		border-radius: 6px;
		min-width: 68px;
		border: 1px solid transparent;
	}
	.vstat-badge.success {
		background: rgba(46, 160, 67, 0.08);
		border-color: rgba(46, 160, 67, 0.15);
		color: #3fb950;
	}
	.vstat-badge.warning {
		background: rgba(210, 153, 34, 0.08);
		border-color: rgba(210, 153, 34, 0.15);
		color: #d29922;
	}
	.vstat-badge.danger {
		background: rgba(248, 81, 73, 0.08);
		border-color: rgba(248, 81, 73, 0.15);
		color: #f85149;
	}
	.vstat-num {
		font-size: 16px;
		font-weight: 700;
		line-height: 1;
	}
	.vstat-label {
		font-size: 9px;
		text-transform: uppercase;
		font-weight: 600;
		opacity: 0.8;
		margin-top: 2px;
	}

	.resolution-card {
		border: 1px solid var(--border-subtle);
		border-radius: 8px;
		overflow: hidden;
		display: flex;
		flex-direction: column;
		transition: transform 180ms var(--ease-out), box-shadow 180ms var(--ease-out);
	}
	.resolution-card:hover {
		transform: translateY(-1px);
		box-shadow: var(--shadow-md);
	}
	.rc-header {
		display: flex;
		justify-content: space-between;
		align-items: center;
		padding: 12px 16px;
		background: var(--bg-hover);
		border-bottom: 1px solid var(--border-subtle);
	}
	.rc-header-left {
		display: flex;
		align-items: center;
		gap: 10px;
	}
	.clause-type-tag {
		font-weight: 600;
		font-size: 12px;
		color: var(--text-primary);
		text-transform: uppercase;
		letter-spacing: 0.02em;
	}
	.risk-pill {
		display: inline-flex;
		align-items: center;
		gap: 6px;
		padding: 4px 8px;
		border-radius: 999px;
		border: 1px solid var(--border-subtle);
		background: var(--bg-panel);
		white-space: nowrap;
	}
	.rp-label {
		font-size: 11px;
		color: var(--text-tertiary);
		font-weight: 650;
	}
	.rp-level {
		font-size: 11px;
		font-weight: 750;
		text-transform: uppercase;
	}
	.risk-pill.risk-critical .rp-level { color: var(--color-critical); }
	.risk-pill.risk-high .rp-level { color: var(--color-high); }
	.risk-pill.risk-medium .rp-level { color: var(--color-medium); }
	.risk-pill.risk-low .rp-level { color: var(--color-low); }

	.rc-comparison-grid {
		display: grid;
		grid-template-columns: 1fr 1fr;
		border-bottom: 1px solid var(--border-subtle);
		background: var(--bg-panel);
	}
	.rc-comparison-grid .pane {
		padding: 16px;
		display: flex;
		flex-direction: column;
		gap: 12px;
	}
	.rc-comparison-grid .pane-original {
		border-right: 1px solid var(--border-subtle);
		background: rgba(248, 81, 73, 0.01);
	}
	.rc-comparison-grid .pane-revised {
		background: rgba(46, 160, 67, 0.01);
	}
	.pane-label {
		font-size: 10px;
		font-weight: 600;
		color: var(--text-tertiary);
		text-transform: uppercase;
		letter-spacing: 0.05em;
	}
	.pane-content {
		font-size: 13px;
		line-height: 1.6;
		color: var(--text-secondary);
	}
	.text-strikethrough {
		text-decoration: line-through;
		opacity: 0.75;
	}
	.highlight-revised {
		color: var(--text-primary);
	}
	.redline-rec {
		margin-top: 10px;
		padding: 10px 12px;
		border-radius: 6px;
		border-left: 3px solid var(--accent-primary);
	}
	.rr-label {
		font-size: 10px;
		font-weight: 600;
		color: var(--accent-primary);
		margin-bottom: 4px;
	}
	.rr-text {
		font-size: 12px;
		line-height: 1.5;
		color: var(--text-secondary);
	}

	.rc-explanation {
		padding: 12px 16px;
		display: flex;
		flex-direction: column;
		gap: 4px;
		border-top: 1px dashed var(--border-subtle);
	}
	.ex-header {
		display: flex;
		align-items: center;
		gap: 6px;
		font-size: 11px;
		font-weight: 600;
		color: var(--text-primary);
	}
	.ex-body {
		font-size: 12px;
		line-height: 1.5;
		color: var(--text-secondary);
		margin: 0;
	}

	/* Revision upload modal specific styles */
	.tabs-nav-modal {
		display: flex;
		border-bottom: 1px solid var(--border-subtle);
		margin-bottom: 20px;
	}
	.tab-nav-modal-btn {
		background: transparent;
		border: none;
		border-bottom: 2px solid transparent;
		padding: 8px 16px;
		font-size: 13px;
		font-weight: 500;
		color: var(--text-secondary);
		cursor: pointer;
		transition: all 120ms var(--ease-out);
	}
	.tab-nav-modal-btn:hover {
		color: var(--text-primary);
	}
	.tab-nav-modal-btn.active {
		color: var(--accent-primary);
		border-bottom-color: var(--accent-primary);
	}
	.tab-nav-modal-btn:active {
		transform: scale(0.97);
	}
	.upload-dropzone {
		border: 2px dashed var(--border-subtle);
		border-radius: 8px;
		padding: 32px 20px;
		text-align: center;
		cursor: pointer;
		background: var(--bg-hover);
		transition: border-color 150ms var(--ease-out), background-color 150ms var(--ease-out);
	}
	.upload-dropzone:hover {
		border-color: var(--accent-primary);
		background: var(--bg-active);
	}
	.dropzone-label {
		display: flex;
		flex-direction: column;
		align-items: center;
		gap: 10px;
		color: var(--text-secondary);
		font-size: 13px;
	}
	.dropzone-subtitle {
		font-size: 11px;
		color: var(--text-tertiary);
	}
	.selected-file-banner {
		display: flex;
		align-items: center;
		justify-content: space-between;
		padding: 10px 14px;
		background: var(--bg-active);
		border: 1px solid var(--border-subtle);
		border-radius: 6px;
		margin-top: 12px;
		font-size: 13px;
		color: var(--text-primary);
	}
	.btn-remove-file {
		background: transparent;
		border: none;
		color: var(--text-tertiary);
		cursor: pointer;
	}
	.btn-remove-file:hover {
		color: var(--color-high);
	}
	.btn-remove-file:active {
		transform: scale(0.97);
	}

	/* Chat */
	.chat-tab {
		gap: 12px;
		height: 100%;
	}
	.chat-panel {
		display: flex;
		flex-direction: column;
		border-radius: 12px;
		border: 1px solid var(--border-subtle);
		overflow: hidden;
		min-height: 440px;
	}
	.chat-panel-header {
		display: flex;
		align-items: flex-start;
		justify-content: space-between;
		gap: 12px;
		padding: 12px 12px;
		border-bottom: 1px solid var(--border-subtle);
		background: var(--bg-panel);
	}
	.chat-history {
		flex: 1;
		overflow: auto;
		padding: 14px 12px;
		background: linear-gradient(180deg, rgba(0,0,0,0.00), rgba(0,0,0,0.02));
	}
	:global([data-theme="dark"]) .chat-history {
		background: linear-gradient(180deg, rgba(255,255,255,0.00), rgba(255,255,255,0.02));
	}
	.chat-message {
		display: flex;
		margin-bottom: 10px;
	}
	.chat-message.user {
		justify-content: flex-end;
	}
	.chat-bubble {
		max-width: 92%;
		padding: 10px 12px;
		border: 1px solid var(--border-subtle);
		border-radius: 12px;
		background: var(--bg-panel);
	}
	.chat-message.user .chat-bubble {
		background: rgba(88, 166, 255, 0.06);
		border-color: rgba(88, 166, 255, 0.22);
	}
	.chat-role {
		font-size: 11px;
		color: var(--text-tertiary);
		margin-bottom: 6px;
	}
	.chat-content {
		white-space: pre-wrap;
		line-height: 1.35;
	}
	.chat-sources {
		display: flex;
		flex-wrap: wrap;
		gap: 6px;
		margin-top: 10px;
	}
	.source-pill {
		display: inline-flex;
		align-items: center;
		gap: 8px;
		padding: 6px 8px;
		border-radius: 10px;
		border: 1px solid var(--border-subtle);
		background: var(--bg-active);
		font-size: 11px;
		color: var(--text-secondary);
		cursor: pointer;
	}
	.source-pill:hover {
		border-color: var(--border-strong);
	}
	.source-pill-text {
		font-weight: 550;
		color: var(--text-secondary);
	}
	.chat-composer {
		display: grid;
		grid-template-columns: 1fr auto;
		gap: 10px;
		align-items: end;
		padding: 10px 12px;
		border: 1px solid var(--border-subtle);
		border-radius: 12px;
		background: var(--bg-panel);
	}
	.chat-textarea {
		width: 100%;
		resize: none;
		min-height: 40px;
		max-height: 140px;
		padding: 10px 12px;
		background: var(--bg-app);
		border: 1px solid var(--border-subtle);
		border-radius: 10px;
		color: var(--text-primary);
		font-size: 13px;
		line-height: 1.35;
		outline: none;
	}
	.chat-textarea:focus {
		border-color: var(--text-secondary);
	}
	.chat-send {
		height: 40px;
		width: 42px;
		display: inline-flex;
		align-items: center;
		justify-content: center;
		padding: 0;
		border-radius: 10px;
	}

	.chat-empty {
		display: flex;
		flex-direction: column;
		align-items: center;
		justify-content: center;
		gap: 10px;
		padding: 34px 16px;
		min-height: 220px;
	}
	.chat-empty-title {
		font-weight: 650;
		color: var(--text-secondary);
	}
	.chat-empty-sub {
		font-size: 12px;
	}
	.chat-suggestions {
		display: flex;
		flex-wrap: wrap;
		justify-content: center;
		gap: 8px;
		margin-top: 6px;
	}
	.suggestion-pill {
		border: 1px solid var(--border-subtle);
		background: var(--bg-panel);
		color: var(--text-secondary);
		padding: 6px 10px;
		border-radius: 999px;
		font-size: 12px;
		cursor: pointer;
		transition: border-color 150ms ease, background 150ms ease;
	}
	.suggestion-pill:hover {
		background: var(--bg-active);
		border-color: var(--border-strong);
		color: var(--text-primary);
	}

	/* Obligations */
	.obligations-list {
		display: flex;
		flex-direction: column;
		gap: 10px;
	}
	.obligation-card {
		padding: 12px;
		border-radius: 12px;
		border: 1px solid var(--border-subtle);
	}
	.obligation-meta {
		display: grid;
		gap: 6px;
		font-size: 12px;
		color: var(--text-secondary);
	}

	/* Trace events */
	.events-list {
		margin-top: 14px;
		padding: 10px;
		border-radius: 12px;
		border: 1px solid var(--border-subtle);
		max-height: 520px;
		overflow: auto;
	}
	.event-row {
		border: 1px solid var(--border-subtle);
		border-radius: 12px;
		background: var(--bg-panel);
		margin-bottom: 8px;
		overflow: hidden;
	}
	.event-summary {
		display: grid;
		grid-template-columns: auto 1fr auto;
		align-items: center;
		gap: 10px;
		padding: 10px 10px;
		cursor: pointer;
	}
	.event-message {
		color: var(--text-primary);
		font-size: 13px;
		white-space: nowrap;
		overflow: hidden;
		text-overflow: ellipsis;
	}
	.event-payload {
		margin: 0;
		padding: 10px 12px;
		border-top: 1px solid var(--border-subtle);
		background: var(--bg-app);
		font-size: 12px;
		white-space: pre-wrap;
	}

	/* Redline Cockpit Layout Tweaks */
	.vh-right {
		display: flex;
		align-items: center;
		gap: 16px;
	}
	.vh-divider {
		width: 1px;
		height: 28px;
		background: var(--border-subtle);
	}
	/* Premium Email Composer Modal override */
	.modal-backdrop {
		transition: background-color 280ms var(--ease-drawer), backdrop-filter 280ms var(--ease-drawer);
	}
	@starting-style {
		.modal-backdrop {
			background-color: rgba(0, 0, 0, 0) !important;
			backdrop-filter: blur(0px) !important;
		}
	}

	.modal-content-wide.email-composer {
		max-width: 760px;
		background: rgba(15, 18, 25, 0.82); /* Glass dark obsidian styling */
		backdrop-filter: blur(24px) saturate(190%);
		-webkit-backdrop-filter: blur(24px) saturate(190%);
		border: 1px solid rgba(255, 255, 255, 0.08);
		border-radius: var(--radius-md);
		position: relative;
		overflow: hidden;
		gap: 0;
		padding: 0;
		box-shadow: 0 30px 70px rgba(0, 0, 0, 0.6), inset 0 1px 0 rgba(255, 255, 255, 0.05);
		opacity: 1;
		transform: scale(1) translateY(0);
		transition: opacity 280ms var(--ease-drawer), transform 280ms var(--ease-drawer);
	}
	@starting-style {
		.modal-content-wide.email-composer {
			opacity: 0;
			transform: scale(0.96) translateY(16px);
		}
	}

	.email-mac-buttons {
		position: absolute;
		top: 22px;
		left: 20px;
		display: flex;
		gap: 8px;
		z-index: 210;
	}
	.mac-dot {
		width: 12px;
		height: 12px;
		border-radius: 50%;
		border: none;
		cursor: pointer;
		position: relative;
		padding: 0;
		transition: transform 120ms var(--ease-out), filter 120ms var(--ease-out), opacity 120ms var(--ease-out);
		box-shadow: inset 0 0.5px 1px rgba(255, 255, 255, 0.15);
	}
	.mac-dot:active {
		transform: scale(0.9);
	}
	.mac-close {
		background: #ff5f56;
	}
	.mac-close:hover {
		background: #e0443e;
	}
	.mac-minimize {
		background: #ffbd2e;
	}
	.mac-maximize {
		background: #27c93f;
	}
	.email-mac-buttons:hover .mac-dot {
		filter: brightness(0.85);
	}

	.email-composer-header {
		padding: 22px 24px 18px 24px;
		border-bottom: 1px solid rgba(255, 255, 255, 0.06);
		display: flex;
		align-items: center;
		gap: 12px;
		margin-left: 68px; /* push to the right of mac buttons */
	}

	.email-composer-body {
		padding: 16px 24px 20px 24px;
		display: flex;
		flex-direction: column;
		gap: 16px;
	}

	.email-composer-controls {
		display: flex;
		align-items: center;
		gap: 16px;
		background: rgba(22, 27, 34, 0.45);
		padding: 10px 16px;
		border-radius: var(--radius-sm);
		border: 1px solid rgba(255, 255, 255, 0.05);
		backdrop-filter: blur(10px);
	}

	.control-group {
		display: flex;
		align-items: center;
		gap: 8px;
	}
	.control-group label {
		font-size: 11px;
		color: #8b949e;
		font-weight: 600;
		text-transform: uppercase;
		letter-spacing: 0.03em;
	}

	.custom-select-wrapper {
		position: relative;
		display: inline-flex;
		align-items: center;
	}
	.custom-select {
		background: rgba(13, 17, 23, 0.65);
		border: 1px solid rgba(255, 255, 255, 0.08);
		border-radius: 6px;
		color: #e6edf3;
		font-size: 12px;
		font-weight: 550;
		height: 32px;
		padding: 0 28px 0 12px;
		outline: none;
		cursor: pointer;
		appearance: none;
		-webkit-appearance: none;
		min-width: 140px;
		transition: border-color 150ms var(--ease-out), box-shadow 150ms var(--ease-out), background-color 150ms var(--ease-out);
	}
	.custom-select:hover {
		border-color: rgba(255, 255, 255, 0.18);
		background-color: rgba(13, 17, 23, 0.85);
	}
	.custom-select:focus {
		border-color: var(--ai);
		box-shadow: 0 0 0 3px rgba(var(--ai-rgb), 0.25);
	}
	.custom-select-wrapper::after {
		content: "";
		position: absolute;
		right: 12px;
		top: 50%;
		transform: translateY(-50%);
		width: 8px;
		height: 8px;
		background: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='none' stroke='%238b949e' stroke-width='3' stroke-linecap='round' stroke-linejoin='round'%3E%3Cpolyline points='6 9 12 15 18 9'/%3E%3C/svg%3E") no-repeat center center;
		background-size: contain;
		pointer-events: none;
		transition: transform 180ms var(--ease-out);
	}
	.custom-select-wrapper:focus-within::after {
		transform: translateY(-50%) rotate(180deg);
	}

	.control-spacer {
		flex: 1;
	}

	.btn-regenerate {
		height: 32px;
		font-size: 12px;
		font-weight: 600;
		padding: 0 14px;
		border-radius: 6px;
		cursor: pointer;
		display: inline-flex;
		align-items: center;
		gap: 6px;
		transition: transform 160ms var(--ease-out), background-color 200ms var(--ease-out), border-color 200ms var(--ease-out), box-shadow 200ms var(--ease-out);
	}
	.btn-regenerate:active {
		transform: scale(0.97);
	}
	.btn-regenerate:hover .icon-spin {
		transform: rotate(45deg);
	}

	.email-loading-pane {
		min-height: 380px;
		background: rgba(22, 27, 34, 0.45);
		border-radius: 10px;
		border: 1px solid rgba(255, 255, 255, 0.05);
		display: flex;
		flex-direction: column;
		overflow: hidden;
		box-shadow: inset 0 2px 12px rgba(0, 0, 0, 0.2);
	}

	.email-loading-status {
		display: flex;
		align-items: center;
		gap: 10px;
		padding: 14px 20px;
		border-bottom: 1px solid rgba(255, 255, 255, 0.05);
		background: rgba(var(--ai-rgb), 0.06);
	}
	.email-loading-text {
		font-size: 12.5px;
		font-weight: 600;
		color: var(--ai);
		letter-spacing: 0.01em;
	}

	.loading-envelope-headers {
		padding: 18px 20px;
		border-bottom: 1px solid rgba(255, 255, 255, 0.05);
		display: flex;
		flex-direction: column;
		gap: 12px;
	}
	.loading-row {
		display: flex;
		align-items: center;
		gap: 16px;
	}
	.loading-label {
		width: 48px;
		height: 10px;
		border-radius: 4px;
		background: rgba(255, 255, 255, 0.04);
	}
	.loading-value {
		width: 180px;
		height: 10px;
		border-radius: 4px;
	}
	.loading-body {
		padding: 24px 20px;
		display: flex;
		flex-direction: column;
		gap: 14px;
	}
	.loading-line {
		height: 10px;
		border-radius: 4px;
	}
	.width-70 { width: 70%; }
	.width-80 { width: 80%; }
	.width-90 { width: 90%; }
	.width-50 { width: 50%; }

	.skeleton {
		background: linear-gradient(90deg, rgba(255, 255, 255, 0.02) 25%, rgba(255, 255, 255, 0.07) 50%, rgba(255, 255, 255, 0.02) 75%);
		background-size: 200% 100%;
		animation: shimmer 1.6s infinite var(--ease-in-out);
	}
	@keyframes shimmer {
		0% { background-position: 200% 0; }
		100% { background-position: -200% 0; }
	}

	.email-workspace {
		background: rgba(22, 27, 34, 0.45);
		border: 1px solid rgba(255, 255, 255, 0.05);
		border-radius: 10px;
		display: flex;
		flex-direction: column;
		box-shadow: inset 0 2px 12px rgba(0, 0, 0, 0.3), 0 4px 24px rgba(0, 0, 0, 0.2);
		overflow: hidden;
	}

	.email-envelope-headers {
		padding: 16px 20px;
		background: rgba(13, 17, 23, 0.25);
		border-bottom: 1px solid rgba(255, 255, 255, 0.05);
		display: flex;
		flex-direction: column;
		gap: 10px;
	}

	.envelope-row {
		display: flex;
		align-items: center;
		font-size: 13px;
	}
	.env-label {
		width: 72px;
		color: #8b949e;
		font-weight: 600;
		font-size: 12px;
		text-transform: uppercase;
		letter-spacing: 0.03em;
	}
	.env-value {
		display: flex;
		align-items: center;
		gap: 8px;
		flex: 1;
		color: #c9d1d9;
	}
	.subject-value {
		color: #f0f6fc !important;
		font-size: 14px;
	}
	.env-tag {
		font-size: 11px;
		padding: 3px 10px;
		border-radius: 6px;
		background: rgba(255, 255, 255, 0.04);
		border: 1px solid rgba(255, 255, 255, 0.08);
		color: #c9d1d9;
		font-weight: 500;
		box-shadow: 0 1px 2px rgba(0,0,0,0.05);
	}
	.env-tag-ai {
		background: rgba(var(--ai-rgb), 0.12) !important;
		border-color: rgba(var(--ai-rgb), 0.25) !important;
		color: var(--ai) !important;
		font-weight: 600;
	}
	.env-address {
		font-family: var(--font-mono);
		font-size: 11px;
		color: #57606a;
	}

	.email-body-pane {
		background: rgba(13, 17, 23, 0.2);
		padding: 24px 20px;
		min-height: 240px;
		max-height: 340px;
		overflow-y: auto;
		border-top: none;
		box-shadow: inset 0 2px 8px rgba(0, 0, 0, 0.15);
	}
	.email-body-pane::-webkit-scrollbar {
		width: 6px;
	}
	.email-body-pane::-webkit-scrollbar-track {
		background: transparent;
	}
	.email-body-pane::-webkit-scrollbar-thumb {
		background-color: rgba(255, 255, 255, 0.08);
		border-radius: 99px;
	}
	:global([data-theme="light"]) .email-body-pane::-webkit-scrollbar-thumb {
		background-color: rgba(0, 0, 0, 0.12);
	}
	.email-body-pane::-webkit-scrollbar-thumb:hover {
		background-color: rgba(255, 255, 255, 0.16);
	}
	:global([data-theme="light"]) .email-body-pane::-webkit-scrollbar-thumb:hover {
		background-color: rgba(0, 0, 0, 0.2);
	}

	.email-body-text {
		margin: 0;
		white-space: pre-wrap;
		font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
		font-size: 14px;
		line-height: 1.6;
		color: #e6edf3;
		letter-spacing: -0.010em;
		selection-background-color: rgba(var(--ai-rgb), 0.3);
	}

	.email-composer-footer {
		padding: 16px 24px 20px 24px;
		border-top: 1px solid rgba(255, 255, 255, 0.05);
		display: flex;
		justify-content: flex-end;
		gap: 12px;
		background: rgba(13, 17, 23, 0.15);
	}

	/* ---- Light theme adaptation for the email composer ---- */
	:global([data-theme="light"]) .modal-content-wide.email-composer {
		background: rgba(255, 255, 255, 0.94);
		border: 1px solid var(--border-subtle);
		box-shadow: 0 30px 70px rgba(0, 0, 0, 0.18), inset 0 1px 0 rgba(255, 255, 255, 0.7);
	}
	:global([data-theme="light"]) .email-composer-header {
		border-bottom: 1px solid var(--border-subtle);
	}
	:global([data-theme="light"]) .email-composer-controls {
		background: var(--bg-hover);
		border: 1px solid var(--border-subtle);
	}
	:global([data-theme="light"]) .control-group label {
		color: var(--text-secondary);
	}
	:global([data-theme="light"]) .custom-select {
		background: #ffffff;
		border: 1px solid var(--border-subtle);
		color: var(--text-primary);
	}
	:global([data-theme="light"]) .custom-select:hover {
		background-color: var(--bg-hover);
		border-color: var(--border-strong);
	}
	:global([data-theme="light"]) .email-loading-pane {
		background: var(--bg-hover);
		border: 1px solid var(--border-subtle);
		box-shadow: inset 0 2px 12px rgba(0, 0, 0, 0.05);
	}
	:global([data-theme="light"]) .email-loading-status,
	:global([data-theme="light"]) .loading-envelope-headers {
		border-bottom: 1px solid var(--border-subtle);
	}
	:global([data-theme="light"]) .loading-label {
		background: rgba(0, 0, 0, 0.05);
	}
	:global([data-theme="light"]) .skeleton {
		background: linear-gradient(90deg, rgba(0, 0, 0, 0.04) 25%, rgba(0, 0, 0, 0.08) 50%, rgba(0, 0, 0, 0.04) 75%);
		background-size: 200% 100%;
	}
	:global([data-theme="light"]) .email-workspace {
		background: #ffffff;
		border: 1px solid var(--border-subtle);
		box-shadow: inset 0 1px 4px rgba(0, 0, 0, 0.04), 0 4px 24px rgba(0, 0, 0, 0.06);
	}
	:global([data-theme="light"]) .email-envelope-headers {
		background: var(--bg-app);
		border-bottom: 1px solid var(--border-subtle);
	}
	:global([data-theme="light"]) .env-label {
		color: var(--text-secondary);
	}
	:global([data-theme="light"]) .env-value {
		color: var(--text-primary);
	}
	:global([data-theme="light"]) .subject-value {
		color: var(--text-primary) !important;
	}
	:global([data-theme="light"]) .env-tag {
		background: var(--bg-hover);
		border: 1px solid var(--border-subtle);
		color: var(--text-secondary);
	}
	:global([data-theme="light"]) .env-address {
		color: var(--text-tertiary);
	}
	:global([data-theme="light"]) .email-body-pane {
		background: #ffffff;
		box-shadow: inset 0 1px 4px rgba(0, 0, 0, 0.03);
	}
	:global([data-theme="light"]) .email-body-text {
		color: var(--text-primary);
	}
	:global([data-theme="light"]) .email-composer-footer {
		border-top: 1px solid var(--border-subtle);
		background: var(--bg-app);
	}

	.btn-copy-draft {
		position: relative;
		min-width: 170px;
		height: 34px;
		padding: 0 16px;
		cursor: pointer;
		background: var(--accent-primary);
		border: 1px solid rgba(255, 255, 255, 0.1);
		transition: transform 160ms var(--ease-out), background-color 200ms var(--ease-out), border-color 200ms var(--ease-out), box-shadow 200ms var(--ease-out);
		overflow: hidden;
	}
	.btn-copy-draft:active {
		transform: scale(0.97);
	}
	.btn-copy-draft.copied {
		background: #1a7f37 !important;
		border-color: rgba(255, 255, 255, 0.15) !important;
		color: #ffffff !important;
		box-shadow: 0 0 16px rgba(46, 160, 67, 0.35) !important;
	}

	.copy-state-wrapper {
		position: relative;
		display: flex;
		align-items: center;
		justify-content: center;
		width: 100%;
		height: 100%;
	}
	.copy-state {
		display: inline-flex;
		align-items: center;
		justify-content: center;
		gap: 8px;
		transition: opacity 180ms var(--ease-out), transform 180ms var(--ease-spring-gentle), filter 180ms var(--ease-out);
		white-space: nowrap;
	}
	.copy-state-default {
		opacity: 1;
		transform: scale(1);
		filter: blur(0px);
	}
	.copy-state-default.state-hidden {
		opacity: 0;
		transform: scale(0.94);
		filter: blur(2px);
		pointer-events: none;
		position: absolute;
	}
	.copy-state-success {
		opacity: 0;
		transform: scale(0.94);
		filter: blur(2px);
		pointer-events: none;
		position: absolute;
	}
	.copy-state-success.state-visible {
		opacity: 1;
		transform: scale(1);
		filter: blur(0px);
		position: relative;
		pointer-events: auto;
	}
	.copy-icon-success {
		stroke: #ffffff;
		animation: scaleIn 220ms var(--ease-spring);
	}
	@keyframes scaleIn {
		from { transform: scale(0.5); opacity: 0; }
		to { transform: scale(1); opacity: 1; }
	}
	
	.icon-spin.spin {
		animation: spin 1.2s linear infinite;
	}
	@keyframes spin {
		from { transform: rotate(0deg); }
		to { transform: rotate(360deg); }
	}
</style>
