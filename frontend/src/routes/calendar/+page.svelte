<script lang="ts">
	import { goto } from '$app/navigation';
	let { data } = $props();
	const initialItems = (data && (data as any).items) ? (data as any).items : [];

	type CalendarItem = {
		id: string;
		filename: string;
		status: string;
		contract_type: string | null;
		company: string | null;
		contract_date: string | null;
		expiry_date: string | null;
		days_until_expiry: number | null;
		renewal_notice_days: number | null;
		renewal_deadline: string | null;
		contract_term: string | null;
		urgency: string;
		overall_risk: string | null;
		created_at: string;
	};

	let items: CalendarItem[] = $state(initialItems || []);
	let isLoading = $state(false);

	let withExpiry = $derived(items.filter(i => i.expiry_date !== null));
	let withoutExpiry = $derived(items.filter(i => i.expiry_date === null));
	let expiredItems = $derived(withExpiry.filter(i => i.urgency === 'expired'));
	let criticalItems = $derived(withExpiry.filter(i => i.urgency === 'critical'));
	let warningItems = $derived(withExpiry.filter(i => i.urgency === 'warning'));
	let soonItems = $derived(withExpiry.filter(i => i.urgency === 'soon'));
	let safeItems = $derived(withExpiry.filter(i => i.urgency === 'safe'));

	let expiringThisMonth = $derived(withExpiry.filter(i => i.days_until_expiry !== null && i.days_until_expiry >= 0 && i.days_until_expiry <= 30).length);
	let renewalDue = $derived(withExpiry.filter(i => {
		if (!i.renewal_deadline) return false;
		const d = new Date(i.renewal_deadline);
		const now = new Date();
		const diff = (d.getTime() - now.getTime()) / (1000 * 60 * 60 * 24);
		return diff >= 0 && diff <= 30;
	}).length);

	function formatDocumentName(filename: string) {
		if (!filename) return '';
		let clean = filename.replace(/\.[a-zA-Z0-9]+$/, '');
		clean = clean.replace(/[_-]/g, ' ');
		return clean.replace(/\b\w/g, c => c.toUpperCase());
	}

	function formatDate(dateStr: string | null) {
		if (!dateStr) return '--';
		try {
			return new Date(dateStr).toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' });
		} catch { return dateStr; }
	}

	function daysLabel(days: number | null) {
		if (days === null) return '';
		if (days < 0) return `${Math.abs(days)}d overdue`;
		if (days === 0) return 'Expires today';
		return `${days}d remaining`;
	}
</script>

<svelte:head>
	<title>Contract Calendar — ContractsPulse</title>
	<meta name="description" content="Track contract expiry dates, renewal deadlines and upcoming obligations across your entire portfolio." />
</svelte:head>

<header class="page-header">
	<div class="page-header-inner">
		<div class="breadcrumbs">
			<span class="crumb">ContractsPulse</span>
			<span class="separator">›</span>
			<span class="crumb active">Contract Calendar</span>
		</div>
		<div class="header-content">
			<div class="header-title-row">
				<span class="header-icon">
					<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="3" y="4" width="18" height="18" rx="2"/><line x1="16" y1="2" x2="16" y2="6"/><line x1="8" y1="2" x2="8" y2="6"/><line x1="3" y1="10" x2="21" y2="10"/></svg>
				</span>
				<h1>Contract Calendar</h1>
			</div>
		</div>
	</div>
</header>

<div class="page-content">
	{#if isLoading}
		<div class="loading-state">
			<span class="spinner spinner-lg"></span>
			<p class="text-tertiary">Loading calendar...</p>
		</div>
	{:else}
		<!-- Stats Row -->
		<div class="stats-row">
			<div class="stat-card panel">
				<div class="stat-label">Tracked Contracts</div>
				<div class="stat-value">{items.length}</div>
				<p class="stat-desc">{withExpiry.length} with known expiry</p>
			</div>
			<div class="stat-card panel">
				<div class="stat-label">Expiring This Month</div>
				<div class="stat-value" class:text-danger={expiringThisMonth > 0} class:text-success={expiringThisMonth === 0}>{expiringThisMonth}</div>
				<p class="stat-desc">within 30 days</p>
			</div>
			<div class="stat-card panel">
				<div class="stat-label">Renewal Notices Due</div>
				<div class="stat-value" class:text-warning={renewalDue > 0} class:text-success={renewalDue === 0}>{renewalDue}</div>
				<p class="stat-desc">opt-out deadlines this month</p>
			</div>
			<div class="stat-card panel">
				<div class="stat-label">Missing Expiry</div>
				<div class="stat-value text-secondary">{withoutExpiry.length}</div>
				<p class="stat-desc">no date detected in text</p>
			</div>
		</div>

		{#if withExpiry.length === 0 && withoutExpiry.length === 0}
			<div class="empty-state panel">
				<svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" class="empty-icon">
					<rect x="3" y="4" width="18" height="18" rx="2"/>
					<line x1="16" y1="2" x2="16" y2="6"/>
					<line x1="8" y1="2" x2="8" y2="6"/>
					<line x1="3" y1="10" x2="21" y2="10"/>
				</svg>
				<h3>No contracts yet</h3>
				<p class="text-tertiary">Upload contracts to the Repository to track expiry and renewal deadlines here.</p>
				<button class="btn btn-primary" onclick={() => goto('/contracts')}>Go to Contract Repository</button>
			</div>
		{:else}
			<!-- Urgency Sections -->
			{#if expiredItems.length > 0}
				<div class="urgency-section">
					<div class="section-header">
						<span class="section-dot dot-expired"></span>
						<h2 class="section-title text-danger">Expired</h2>
						<span class="section-count">{expiredItems.length}</span>
					</div>
					<div class="cards-grid">
						{#each expiredItems as item}
							<button class="contract-card panel urgency-expired" onclick={() => goto(`/contracts/${item.id}`)}>
								{@render contractCardContent(item)}
							</button>
						{/each}
					</div>
				</div>
			{/if}

			{#if criticalItems.length > 0}
				<div class="urgency-section">
					<div class="section-header">
						<span class="section-dot dot-critical-urg"></span>
						<h2 class="section-title text-danger">Critical — Expiring within 30 days</h2>
						<span class="section-count">{criticalItems.length}</span>
					</div>
					<div class="cards-grid">
						{#each criticalItems as item}
							<button class="contract-card panel urgency-critical" onclick={() => goto(`/contracts/${item.id}`)}>
								{@render contractCardContent(item)}
							</button>
						{/each}
					</div>
				</div>
			{/if}

			{#if warningItems.length > 0}
				<div class="urgency-section">
					<div class="section-header">
						<span class="section-dot dot-warning-urg"></span>
						<h2 class="section-title text-warning">Watch — Expiring within 60 days</h2>
						<span class="section-count">{warningItems.length}</span>
					</div>
					<div class="cards-grid">
						{#each warningItems as item}
							<button class="contract-card panel urgency-warning" onclick={() => goto(`/contracts/${item.id}`)}>
								{@render contractCardContent(item)}
							</button>
						{/each}
					</div>
				</div>
			{/if}

			{#if soonItems.length > 0}
				<div class="urgency-section">
					<div class="section-header">
						<span class="section-dot dot-soon-urg"></span>
						<h2 class="section-title">Upcoming — Expiring within 90 days</h2>
						<span class="section-count">{soonItems.length}</span>
					</div>
					<div class="cards-grid">
						{#each soonItems as item}
							<button class="contract-card panel" onclick={() => goto(`/contracts/${item.id}`)}>
								{@render contractCardContent(item)}
							</button>
						{/each}
					</div>
				</div>
			{/if}

			{#if safeItems.length > 0}
				<div class="urgency-section">
					<div class="section-header">
						<span class="section-dot dot-safe-urg"></span>
						<h2 class="section-title text-success">Active — Expiry beyond 90 days</h2>
						<span class="section-count">{safeItems.length}</span>
					</div>
					<div class="cards-grid">
						{#each safeItems as item}
							<button class="contract-card panel" onclick={() => goto(`/contracts/${item.id}`)}>
								{@render contractCardContent(item)}
							</button>
						{/each}
					</div>
				</div>
			{/if}

			{#if withoutExpiry.length > 0}
				<div class="urgency-section">
					<div class="section-header">
						<span class="section-dot dot-unknown-urg"></span>
						<h2 class="section-title text-tertiary">No Expiry Detected</h2>
						<span class="section-count">{withoutExpiry.length}</span>
					</div>
					<div class="cards-grid">
						{#each withoutExpiry as item}
							<button class="contract-card panel card-muted" onclick={() => goto(`/contracts/${item.id}`)}>
								{@render contractCardContent(item)}
							</button>
						{/each}
					</div>
				</div>
			{/if}
		{/if}
	{/if}
</div>

{#snippet contractCardContent(item: CalendarItem)}
	<div class="card-top">
		<div class="card-title-row">
			<span class="card-name">{formatDocumentName(item.filename)}</span>
			{#if item.overall_risk}
				<span class="risk-chip risk-chip-{item.overall_risk.toLowerCase()}">{item.overall_risk}</span>
			{/if}
		</div>
		{#if item.company}
			<span class="card-vendor text-tertiary">{item.company}</span>
		{/if}
		{#if item.contract_type}
			<span class="card-type-badge">{item.contract_type}</span>
		{/if}
	</div>
	<div class="card-dates">
		{#if item.expiry_date}
			<div class="date-row">
				<span class="date-label">Expires</span>
				<span class="date-value">{formatDate(item.expiry_date)}</span>
				{#if item.days_until_expiry !== null}
					<span class="days-chip" class:chip-expired={item.urgency === 'expired'} class:chip-critical={item.urgency === 'critical'} class:chip-warning={item.urgency === 'warning'} class:chip-safe={item.urgency === 'safe' || item.urgency === 'soon'}>
						{daysLabel(item.days_until_expiry)}
					</span>
				{/if}
			</div>
		{/if}
		{#if item.renewal_deadline}
			<div class="date-row">
				<span class="date-label">Opt-out by</span>
				<span class="date-value">{formatDate(item.renewal_deadline)}</span>
				{#if item.renewal_notice_days}
					<span class="notice-chip">{item.renewal_notice_days}d notice</span>
				{/if}
			</div>
		{/if}
		{#if item.contract_term}
			<div class="date-row">
				<span class="date-label">Term</span>
				<span class="date-value text-secondary">{item.contract_term}</span>
			</div>
		{/if}
		{#if !item.expiry_date}
			<div class="date-row">
				<span class="date-label text-tertiary">No expiry date found in contract text</span>
			</div>
		{/if}
	</div>
	<div class="card-footer">
		<span class="status-dot status-{item.status.toLowerCase()}"></span>
		<span class="status-text text-tertiary">{item.status}</span>
		<svg class="card-arrow" width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5">
			<line x1="5" y1="12" x2="19" y2="12"/>
			<polyline points="12 5 19 12 12 19"/>
		</svg>
	</div>
{/snippet}

<style>
	.page-content {
		padding: 32px 40px;
		max-width: 1200px;
		width: 100%;
		box-sizing: border-box;
	}

	.loading-state {
		display: flex;
		flex-direction: column;
		align-items: center;
		justify-content: center;
		gap: 16px;
		padding: 80px;
		color: var(--text-tertiary);
	}

	.stats-row {
		display: grid;
		grid-template-columns: repeat(4, 1fr);
		gap: 16px;
		margin-bottom: 32px;
	}

	.stat-card {
		padding: 20px;
		border-radius: 8px;
	}

	.stat-label {
		font-size: 11px;
		text-transform: uppercase;
		letter-spacing: 0.8px;
		color: var(--text-secondary);
		font-weight: 600;
		margin-bottom: 8px;
	}

	.stat-value {
		font-size: 28px;
		font-weight: 700;
		color: var(--text-primary);
		line-height: 1.1;
		margin-bottom: 4px;
		font-variant-numeric: tabular-nums;
	}

	.stat-desc {
		font-size: 12px;
		color: var(--text-tertiary);
		margin: 0;
	}

	.empty-state {
		display: flex;
		flex-direction: column;
		align-items: center;
		justify-content: center;
		gap: 16px;
		padding: 80px 40px;
		text-align: center;
		border-radius: 8px;
	}

	.empty-icon {
		color: var(--text-tertiary);
	}

	.empty-state h3 {
		margin: 0;
		font-size: 18px;
		font-weight: 600;
		color: var(--text-primary);
	}

	.urgency-section {
		margin-bottom: 40px;
	}

	.section-header {
		display: flex;
		align-items: center;
		gap: 10px;
		margin-bottom: 16px;
	}

	.section-dot {
		width: 10px;
		height: 10px;
		border-radius: 50%;
		flex-shrink: 0;
	}

	.dot-expired { background: var(--color-critical); }
	.dot-critical-urg { background: var(--color-high); }
	.dot-warning-urg { background: var(--color-medium); }
	.dot-soon-urg { background: var(--accent-primary); }
	.dot-safe-urg { background: var(--color-low); }
	.dot-unknown-urg { background: var(--text-tertiary); }

	.section-title {
		margin: 0;
		font-size: 14px;
		font-weight: 600;
		color: var(--text-primary);
	}

	.section-count {
		font-size: 11px;
		font-weight: 600;
		padding: 2px 7px;
		border-radius: 6px;
		background: var(--bg-hover);
		color: var(--text-secondary);
		border: 1px solid var(--border-subtle);
	}

	.cards-grid {
		display: grid;
		grid-template-columns: repeat(auto-fill, minmax(320px, 1fr));
		gap: 12px;
	}

	.contract-card {
		display: flex;
		flex-direction: column;
		gap: 12px;
		padding: 16px 20px;
		border-radius: 8px;
		background: var(--bg-panel);
		border: 1px solid var(--border-subtle);
		cursor: pointer;
		text-align: left;
		transition: border-color 150ms ease, box-shadow 150ms ease, transform 120ms ease;
	}

	.contract-card:hover {
		border-color: var(--border-glass-hover);
		box-shadow: var(--shadow-md);
	}

	.contract-card:active {
		transform: scale(0.98);
	}

	.urgency-expired {
		border-left: 3px solid var(--color-critical);
	}

	.urgency-critical {
		border-left: 3px solid var(--color-high);
	}

	.urgency-warning {
		border-left: 3px solid var(--color-medium);
	}

	.card-muted {
		opacity: 0.75;
	}

	.card-top {
		display: flex;
		flex-direction: column;
		gap: 4px;
	}

	.card-title-row {
		display: flex;
		align-items: flex-start;
		justify-content: space-between;
		gap: 8px;
	}

	.card-name {
		font-size: 13px;
		font-weight: 600;
		color: var(--text-primary);
		line-height: 1.3;
		max-width: 220px;
	}

	.card-vendor {
		font-size: 12px;
		margin-top: 2px;
	}

	.card-type-badge {
		font-size: 10px;
		font-weight: 600;
		text-transform: uppercase;
		letter-spacing: 0.5px;
		padding: 2px 6px;
		border-radius: 4px;
		background: var(--bg-hover);
		color: var(--text-secondary);
		border: 1px solid var(--border-subtle);
		width: fit-content;
		margin-top: 4px;
	}

	.risk-chip {
		font-size: 9px;
		font-weight: 700;
		padding: 2px 5px;
		border-radius: 4px;
		text-transform: uppercase;
		flex-shrink: 0;
	}

	.risk-chip-critical { background: rgba(var(--color-critical-rgb), 0.12); color: var(--color-critical); border: 1px solid rgba(var(--color-critical-rgb), 0.2); }
	.risk-chip-high { background: rgba(var(--color-high-rgb), 0.12); color: var(--color-high); border: 1px solid rgba(var(--color-high-rgb), 0.2); }
	.risk-chip-medium { background: rgba(var(--color-medium-rgb), 0.12); color: var(--color-medium); border: 1px solid rgba(var(--color-medium-rgb), 0.2); }
	.risk-chip-low { background: rgba(var(--color-low-rgb), 0.12); color: var(--color-low); border: 1px solid rgba(var(--color-low-rgb), 0.2); }

	.card-dates {
		display: flex;
		flex-direction: column;
		gap: 6px;
	}

	.date-row {
		display: flex;
		align-items: center;
		gap: 8px;
		font-size: 12px;
	}

	.date-label {
		color: var(--text-tertiary);
		min-width: 60px;
		font-size: 11px;
	}

	.date-value {
		color: var(--text-primary);
		font-weight: 500;
	}

	.days-chip {
		font-size: 10px;
		font-weight: 600;
		padding: 2px 6px;
		border-radius: 4px;
	}

	.chip-expired { background: rgba(var(--color-critical-rgb), 0.1); color: var(--color-critical); }
	.chip-critical { background: rgba(var(--color-high-rgb), 0.1); color: var(--color-high); }
	.chip-warning { background: rgba(var(--color-medium-rgb), 0.1); color: var(--color-medium); }
	.chip-safe { background: rgba(var(--color-low-rgb), 0.1); color: var(--color-low); }

	.notice-chip {
		font-size: 10px;
		padding: 2px 6px;
		border-radius: 4px;
		background: var(--bg-hover);
		color: var(--text-secondary);
		border: 1px solid var(--border-subtle);
		font-weight: 600;
	}

	.card-footer {
		display: flex;
		align-items: center;
		gap: 6px;
		font-size: 11px;
		padding-top: 8px;
		border-top: 1px solid var(--border-subtle);
		justify-content: space-between;
	}

	.status-dot {
		width: 6px;
		height: 6px;
		border-radius: 50%;
	}

	.status-dot.status-completed { background: var(--color-low); }
	.status-dot.status-processing { background: var(--color-medium); }
	.status-dot.status-failed { background: var(--color-critical); }
	.status-dot.status-pending { background: var(--text-tertiary); }

	.status-text {
		text-transform: capitalize;
		flex: 1;
	}

	.card-arrow {
		color: var(--text-tertiary);
		margin-left: auto;
		transition: transform 150ms ease;
	}

	.contract-card:hover .card-arrow {
		transform: translateX(3px);
	}

	@media (max-width: 900px) {
		.stats-row { grid-template-columns: repeat(2, 1fr); }
		.cards-grid { grid-template-columns: 1fr; }
	}
</style>
