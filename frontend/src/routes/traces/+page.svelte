<script lang="ts">
	import { onMount, onDestroy } from 'svelte';
	import { apiFetch } from '$lib/api';

	let events: any[] = $state([]);
	let pollInterval: any;
	let apiBase = $state('http://localhost:9432');

	async function fetchEvents() {
		try {
			const res = await apiFetch('/api/v1/events/recent');
			if (!res.ok) return;
			const json = await res.json();
			events = json.events || [];
		} catch (err) {
			console.error('Failed to fetch events:', err);
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
		const u = new URL(window.location.href);
		apiBase = `${u.protocol}//${u.hostname}:9432`;
		fetchEvents();
		pollInterval = setInterval(fetchEvents, 3000);
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
			<span class="crumb active">Agent Traces</span>
		</div>

		<div class="header-content flex-between">
			<div class="header-title-row">
				<span class="header-icon">
					<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M22 12h-4l-3 9L9 3l-3 9H2"/></svg>
				</span>
				<h1>Agent Traces</h1>
			</div>
		</div>
	</div>
</header>

<div class="page-content">
	<div class="data-table panel">
		<div class="table-header">
			<div class="col col-name">Message</div>
			<div class="col col-status">Type</div>
			<div class="col col-date">When</div>
		</div>

		{#if events.length === 0}
			<div class="table-row empty-row">No trace events yet.</div>
		{/if}

		{#each events as e}
			<div class="table-row">
				<div class="col col-name">
					<span class="truncate">{e.message}</span>
					<span class="text-tertiary" style="margin-left: 8px;">({e.contract_id.slice(0, 8)})</span>
				</div>
				<div class="col col-status">
					<span class="badge badge-blue">{e.event_type}</span>
				</div>
				<div class="col col-date text-tertiary">{timeAgo(e.created_at)}</div>
			</div>
		{/each}
	</div>
</div>
