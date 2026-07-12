<script lang="ts">
	import '../app.css';
	import { toasts, toast } from '$lib/toastStore';
	import { page } from '$app/stores';
	import { authState } from '$lib/auth.svelte';
	import { apiFetch, getApiBase } from '$lib/api';
	import { onMount } from 'svelte';
	import { navigating } from '$app/stores';

	let { children } = $props();

	let isLogin = $state(true);
	let email = $state('');
	let password = $state('');
	let loginError = $state('');
	let loading = $state(false);

	let theme = $state<'light' | 'dark'>('light');

	// Global assistant
	type AssistantRole = 'user' | 'assistant';
	type AssistantTurn = { role: AssistantRole; content: string; sources?: any[] };
	let assistantOpen = $state(false);
	let assistantMessages = $state<AssistantTurn[]>([]);
	let assistantInput = $state('');
	let assistantLoading = $state(false);

	async function sendAssistant() {
		const q = (assistantInput || '').trim();
		if (!q || assistantLoading) return;
		const history = assistantMessages.map((m) => ({ role: m.role, content: m.content }));
		assistantMessages = [...assistantMessages, { role: 'user', content: q }];
		assistantInput = '';
		assistantLoading = true;
		try {
			const res = await apiFetch('/api/v1/assistant/chat', {
				method: 'POST',
				headers: { 'Content-Type': 'application/json' },
				body: JSON.stringify({ question: q, history })
			});
			const json = await res.json().catch(() => ({}));
			if (!res.ok) throw new Error(json?.detail || 'Assistant failed');
			assistantMessages = [...assistantMessages, { role: 'assistant', content: json.answer || '', sources: json.sources || [] }];
		} catch (e: any) {
			toast.error(e?.message || 'Assistant failed');
		} finally {
			assistantLoading = false;
		}
	}

	function toggleTheme() {
		theme = theme === 'light' ? 'dark' : 'light';
		localStorage.setItem('cp_theme', theme);
		document.documentElement.setAttribute('data-theme', theme);
	}

	onMount(async () => {
		// Initialize theme preference (default to light)
		theme = (localStorage.getItem('cp_theme') as 'light' | 'dark') || 'light';
		document.documentElement.setAttribute('data-theme', theme);
		// Fetch signup status first
		try {
			const statusRes = await apiFetch('/api/v1/auth/signup-status');
			if (statusRes.ok) {
				const statusData = await statusRes.json();
				authState.signupDisabled = statusData.signup_disabled;
			}
		} catch (e) {
			console.error('Failed to fetch signup status', e);
		}

		// Verify existing token if present
		if (authState.token) {
			try {
				const meRes = await apiFetch('/api/v1/auth/me');
				if (meRes.ok) {
					const meData = await meRes.json();
					authState.setUser(meData);
				} else {
					authState.logout();
				}
			} catch (e) {
				console.error('Token validation failed', e);
				authState.logout();
			}
		}
		authState.initialized = true;
	});

	async function handleSubmit(e: Event) {
		e.preventDefault();
		if (loading) return;
		loading = true;
		loginError = '';

		const endpoint = isLogin ? '/api/v1/auth/login' : '/api/v1/auth/signup';
		try {
			const res = await apiFetch(endpoint, {
				method: 'POST',
				headers: { 'Content-Type': 'application/json' },
				body: JSON.stringify({ email, password })
			});

			const data = await res.json();
			if (res.ok) {
				authState.setToken(data.access_token);
				authState.setUser(data.user);
				toast.success(isLogin ? 'Logged in successfully' : 'Account created successfully');
				email = '';
				password = '';
			} else {
				loginError = data.detail || 'Authentication failed.';
				toast.error(loginError);
			}
		} catch (err: any) {
			loginError = `Connection error — API not reachable at ${getApiBase()}.`;
			toast.error(loginError);
		} finally {
			loading = false;
		}
	}
</script>

{#if !authState.initialized}
	<div class="auth-container">
		<span class="spinner spinner-lg"></span>
	</div>
{:else if !authState.isAuthenticated}
	<div class="auth-container">
		<div class="auth-card panel">
			<div class="auth-header">
				<div class="workspace-avatar brand-mark brand-mark-lg" style="margin: 0 auto 16px;" aria-label="ContractsPulse logo">
					<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
						<path d="M14 3H7a1 1 0 0 0-1 1v16a1 1 0 0 0 1 1h10a1 1 0 0 0 1-1V7z"/>
						<path d="M14 3v4h4"/>
						<path d="M8 13h2l1.5-3 2 6 1.5-3H16"/>
					</svg>
				</div>
				<h2>{isLogin ? 'Log in to ContractsPulse' : 'Create an Account'}</h2>
				<p>{isLogin ? 'Enter your credentials to access your workspace.' : 'Register a new account to get started.'}</p>
			</div>

			{#if !authState.signupDisabled}
				<div class="auth-tabs" role="tablist" aria-label="Authentication Mode">
					<button 
						type="button" 
						role="tab"
						aria-selected={isLogin}
						class="auth-tab" 
						class:active={isLogin} 
						onclick={() => { isLogin = true; loginError = ''; }}
					>
						Log In
					</button>
					<button 
						type="button" 
						role="tab"
						aria-selected={!isLogin}
						class="auth-tab" 
						class:active={!isLogin} 
						onclick={() => { isLogin = false; loginError = ''; }}
					>
						Sign Up
					</button>
				</div>
			{:else if !isLogin}
				<!-- Fallback if user somehow got to signup page when disabled -->
				{ (isLogin = true, '') }
			{/if}

			<form onsubmit={handleSubmit} class="auth-form">
				<div class="form-group">
					<label for="email">Email</label>
					<input 
						type="email" 
						id="email" 
						bind:value={email} 
						placeholder="you@domain.com" 
						class="input-field" 
						required 
					/>
				</div>
				<div class="form-group">
					<label for="password">Password</label>
					<input 
						type="password" 
						id="password" 
						bind:value={password} 
						placeholder="••••••••" 
						class="input-field" 
						required 
						minlength={isLogin ? undefined : 8}
					/>
				</div>
				
				{#if loginError}
					<div class="error-msg">{loginError}</div>
				{/if}

				<button type="submit" class="btn btn-primary btn-block" style="margin-top: 8px;" disabled={loading}>
					{#if loading}
						<span class="spinner spinner-sm"></span>
					{:else}
						Continue
					{/if}
				</button>
			</form>
		</div>
	</div>
{:else}
	<div class="app-layout">
		<aside class="sidebar">
			<div class="workspace-switcher flex-row">
				<div class="workspace-avatar brand-mark" aria-label="ContractsPulse logo">
					<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
						<path d="M14 3H7a1 1 0 0 0-1 1v16a1 1 0 0 0 1 1h10a1 1 0 0 0 1-1V7z"/>
						<path d="M14 3v4h4"/>
						<path d="M8 13h2l1.5-3 2 6 1.5-3H16"/>
					</svg>
				</div>
				<div class="workspace-name">ContractsPulse</div>
			</div>

			<nav class="sidebar-nav">
				<div class="nav-section">
					<div class="nav-label">Workspace</div>
					<a href="/" class="nav-item {$page.url.pathname === '/' ? 'active' : ''}">
						<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="3" y="3" width="18" height="18" rx="2"/><path d="M3 9h18M9 21V9"/></svg>
						Dashboard
					</a>
					<a href="/contracts" class="nav-item {$page.url.pathname === '/contracts' ? 'active' : ''}">
						<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/><line x1="16" y1="13" x2="8" y2="13"/><line x1="16" y1="17" x2="8" y2="17"/><polyline points="10 9 9 9 8 9"/></svg>
						Contract Repository
					</a>
					<a href="/risk" class="nav-item {$page.url.pathname === '/risk' ? 'active' : ''}">
						<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"/><line x1="12" y1="9" x2="12" y2="13"/><line x1="12" y1="17" x2="12.01" y2="17"/></svg>
						Risk Inbox
					</a>
					<a href="/calendar" class="nav-item {$page.url.pathname === '/calendar' ? 'active' : ''}">
						<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="3" y="4" width="18" height="18" rx="2"/><line x1="16" y1="2" x2="16" y2="6"/><line x1="8" y1="2" x2="8" y2="6"/><line x1="3" y1="10" x2="21" y2="10"/></svg>
						Calendar
					</a>
					<a href="/vendors" class="nav-item {$page.url.pathname === '/vendors' ? 'active' : ''}">
						<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M3 7l9-4 9 4-9 4-9-4z"/><path d="M3 17l9 4 9-4"/><path d="M3 12l9 4 9-4"/></svg>
						Vendors
					</a>
				</div>
				
				<div class="nav-section">
					<div class="nav-label">System</div>
					<a href="/traces" class="nav-item {$page.url.pathname === '/traces' ? 'active' : ''}">
						<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M22 12h-4l-3 9L9 3l-3 9H2"/></svg>
						Agent Traces
					</a>
				</div>
			</nav>
			
			<div class="sidebar-footer">
				{#if authState.user}
					<div class="user-info flex-row">
						<div class="user-avatar">{authState.user.email[0].toUpperCase()}</div>
						<div class="user-email" title={authState.user.email}>{authState.user.email}</div>
					</div>
				{/if}
				<button type="button" class="nav-item nav-item-button" onclick={toggleTheme} aria-label={theme === 'light' ? 'Switch to Dark Mode' : 'Switch to Light Mode'}>
					{#if theme === 'light'}
						<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true"><circle cx="12" cy="12" r="5"/><line x1="12" y1="1" x2="12" y2="3"/><line x1="12" y1="21" x2="12" y2="23"/><line x1="4.22" y1="4.22" x2="5.64" y2="5.64"/><line x1="18.36" y1="18.36" x2="19.78" y2="19.78"/><line x1="1" y1="12" x2="3" y2="12"/><line x1="21" y1="12" x2="23" y2="12"/><line x1="4.22" y1="19.78" x2="5.64" y2="18.36"/><line x1="18.36" y1="5.64" x2="19.78" y2="4.22"/></svg>
						Dark Mode
					{:else}
						<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true"><path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z"/></svg>
						Light Mode
					{/if}
				</button>
				<button type="button" class="nav-item nav-item-button" onclick={() => authState.logout()}>
					<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4"/><polyline points="16 17 21 12 16 7"/><line x1="21" y1="12" x2="9" y2="12"/></svg>
					Sign Out
				</button>
			</div>
		</aside>

		<main class="main-content">
			{@render children()}
		</main>
	</div>

	{#if $navigating}
		<div class="nav-loading-bar"></div>
	{/if}

	<!-- Bottom-left assistant -->
	<button class="assistant-fab" type="button" onclick={() => (assistantOpen = !assistantOpen)} aria-label="Open assistant">
		<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 15a4 4 0 0 1-4 4H7l-4 4V7a4 4 0 0 1 4-4h10a4 4 0 0 1 4 4z"/></svg>
	</button>

	{#if assistantOpen}
		<div class="assistant-panel panel">
			<div class="assistant-head flex-between">
				<div>
					<div class="flex-row gap-8">
						<div class="assistant-title">Sage</div>
						<span class="ai-badge" title="Generated by AI. Verify against contract text.">
							<svg class="ai-icon" width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 2l1.2 4.3L18 8l-4.8 1.7L12 14l-1.2-4.3L6 8l4.8-1.7L12 2z"/></svg>
							AI
						</span>
					</div>
					<div class="text-tertiary" style="font-size: 12px;">Search clauses + get answers</div>
				</div>
				<button class="btn btn-secondary btn-compact" type="button" onclick={() => (assistantOpen = false)}>Close</button>
			</div>

			<div class="assistant-body">
				{#if assistantMessages.length === 0}
					<div class="assistant-empty text-tertiary">
						Try: “Find MFN clauses” or “What are our termination notice obligations across vendors?”
					</div>
				{:else}
					{#each assistantMessages as m, idx (idx)}
						<div class="assistant-msg {m.role}">
							<div class="assistant-bubble">
								<div class="assistant-role">{m.role === 'user' ? 'You' : 'Sage'}</div>
								{#if m.role === 'assistant'}
									<div class="ai-chip" style="margin-bottom: 8px;" title="This response was generated by AI.">
										<svg class="ai-icon" width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 2l1.2 4.3L18 8l-4.8 1.7L12 14l-1.2-4.3L6 8l4.8-1.7L12 2z"/></svg>
										AI answer
									</div>
								{/if}
								<div class="assistant-content">{m.content}</div>
							</div>
						</div>
					{/each}
				{/if}
			</div>

			<div class="assistant-compose">
				<textarea
					class="assistant-textarea"
					rows="1"
					placeholder="Ask Sage…"
					bind:value={assistantInput}
					disabled={assistantLoading}
					aria-label="Ask Sage assistant"
					onkeydown={(e) => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); sendAssistant(); } }}
				></textarea>
				<button class="btn btn-primary assistant-send" type="button" onclick={sendAssistant} disabled={assistantLoading || !assistantInput.trim()} aria-label="Send">
					{#if assistantLoading}
						<span class="spinner spinner-sm"></span>
					{:else}
						<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M22 2L11 13"/><path d="M22 2l-7 20-4-9-9-4z"/></svg>
					{/if}
				</button>
			</div>
		</div>
	{/if}

	<!-- Toast Container -->
	<div class="toast-viewport">
		{#each $toasts as toast (toast.id)}
			<div class="toast" class:toast-error={toast.type === 'error'} class:toast-success={toast.type === 'success'}>
				<div class="toast-content">
					{#if toast.type === 'success'}
						<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M22 11.08V12a10 10 0 1 1-5.93-9.14"/><polyline points="22 4 12 14.01 9 11.01"/></svg>
					{:else if toast.type === 'error'}
						<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/></svg>
					{:else}
						<span class="spinner spinner-md"></span>
					{/if}
					<span>{toast.message}</span>
				</div>
			</div>
		{/each}
	</div>
{/if}

<style>
	:global(.toast-viewport) {
		position: fixed;
		top: 24px;
		right: 24px;
		display: flex;
		flex-direction: column;
		gap: 8px;
		z-index: 200;
		pointer-events: none;
	}

	:global(.toast) {
		background: var(--bg-panel);
		border: 1px solid var(--border-subtle);
		color: var(--text-primary);
		padding: 12px 16px;
		border-radius: 8px;
		font-size: 13px;
		font-weight: 500;
		box-shadow: var(--shadow-premium);
		pointer-events: auto;
		animation: slideIn 220ms var(--ease-out) forwards;
		transform-origin: top center;
	}

	:global(.toast-error) {
		border-color: var(--glow-critical-border);
		box-shadow: 0 8px 30px var(--glow-critical);
		color: var(--color-critical);
	}
	
	:global(.toast-success) {
		border-color: var(--glow-low-border);
		box-shadow: 0 8px 30px var(--glow-low);
		color: var(--color-low);
	}

	:global(.toast-content) {
		display: flex;
		align-items: center;
		gap: 10px;
	}

	@keyframes slideIn {
		from { opacity: 0; transform: translateY(-12px) scale(0.95); }
		to { opacity: 1; transform: translateY(0) scale(1); }
	}

	.app-layout {
		display: flex;
		height: 100vh;
		overflow: hidden;
	}

	.nav-loading-bar {
		position: fixed;
		left: 240px;
		right: 0;
		top: 0;
		height: 2px;
		background: linear-gradient(90deg, rgba(88,166,255,0.0), rgba(88,166,255,0.9), rgba(88,166,255,0.0));
		animation: shimmer 800ms linear infinite;
		z-index: 120;
	}
	@keyframes shimmer {
		0% { transform: translateX(-30%); }
		100% { transform: translateX(30%); }
	}

	.assistant-fab {
		position: fixed;
		right: 16px;
		bottom: 18px;
		width: 44px;
		height: 44px;
		border-radius: 999px;
		border: 1px solid var(--border-subtle);
		background: var(--bg-panel);
		color: var(--text-primary);
		box-shadow: var(--shadow-premium);
		display: inline-flex;
		align-items: center;
		justify-content: center;
		cursor: pointer;
		z-index: 150;
	}
	.assistant-fab:hover {
		background: var(--bg-active);
		border-color: var(--border-strong);
	}
	.assistant-panel {
		position: fixed;
		right: 16px;
		bottom: 70px;
		width: 380px;
		max-width: calc(100vw - 32px);
		height: 520px;
		max-height: calc(100vh - 120px);
		display: flex;
		flex-direction: column;
		padding: 0;
		overflow: hidden;
		z-index: 160;
	}
	.assistant-head {
		padding: 12px 12px;
		border-bottom: 1px solid var(--border-subtle);
	}
	.assistant-title {
		font-weight: 700;
	}
	.assistant-body {
		flex: 1;
		overflow: auto;
		padding: 12px;
		background: var(--bg-app);
	}
	.assistant-empty {
		padding: 18px 10px;
		font-size: 12px;
	}
	.assistant-msg {
		display: flex;
		margin-bottom: 10px;
	}
	.assistant-msg.user {
		justify-content: flex-end;
	}
	.assistant-bubble {
		max-width: 92%;
		padding: 10px 12px;
		border: 1px solid var(--border-subtle);
		border-radius: 12px;
		background: var(--bg-panel);
	}
	.assistant-msg.user .assistant-bubble {
		background: rgba(88, 166, 255, 0.06);
		border-color: rgba(88, 166, 255, 0.22);
	}
	.assistant-role {
		font-size: 11px;
		color: var(--text-tertiary);
		margin-bottom: 6px;
	}
	.assistant-content {
		white-space: pre-wrap;
		line-height: 1.35;
	}
	.assistant-compose {
		display: grid;
		grid-template-columns: 1fr auto;
		gap: 10px;
		padding: 10px 12px;
		border-top: 1px solid var(--border-subtle);
		background: var(--bg-panel);
		align-items: end;
	}
	.assistant-textarea {
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
	.assistant-textarea:focus {
		border-color: var(--text-secondary);
	}
	.assistant-send {
		height: 40px;
		width: 42px;
		display: inline-flex;
		align-items: center;
		justify-content: center;
		padding: 0;
		border-radius: 10px;
	}

	.sidebar {
		width: 240px;
		background: var(--bg-sidebar);
		border-right: 1px solid var(--border-subtle);
		display: flex;
		flex-direction: column;
		flex-shrink: 0;
	}

	.workspace-switcher {
		padding: 16px;
		gap: 12px;
		border-bottom: 1px solid var(--border-subtle);
		cursor: pointer;
		transition: background 100ms ease;
	}

	.workspace-switcher:hover {
		background: var(--bg-hover);
	}

	.workspace-avatar {
		width: 24px;
		height: 24px;
		background: var(--accent-primary);
		color: var(--text-on-accent);
		border-radius: 4px;
		display: flex;
		align-items: center;
		justify-content: center;
		font-size: 12px;
		font-weight: 600;
	}

	.brand-mark {
		background: linear-gradient(135deg, #6e79e0 0%, #7c3aed 100%);
		color: #fff;
	}

	.brand-mark svg {
		width: 15px;
		height: 15px;
	}

	.brand-mark-lg {
		width: 48px;
		height: 48px;
		border-radius: 12px;
		box-shadow: 0 6px 20px rgba(var(--ai-rgb), 0.28);
	}

	.brand-mark-lg svg {
		width: 28px;
		height: 28px;
	}

	.workspace-name {
		font-size: 14px;
		font-weight: 500;
		color: var(--text-primary);
	}

	.sidebar-nav {
		padding: 16px 8px;
		flex: 1;
	}

	.nav-section {
		margin-bottom: 24px;
	}

	.nav-label {
		font-size: 11px;
		font-weight: 600;
		color: var(--text-secondary);
		text-transform: uppercase;
		letter-spacing: 0.5px;
		padding: 0 8px;
		margin-bottom: 8px;
	}

	.nav-item {
		display: flex;
		align-items: center;
		gap: 10px;
		padding: 6px 8px;
		color: var(--text-secondary);
		text-decoration: none;
		font-size: 13px;
		font-weight: 500;
		border-radius: 6px;
		margin-bottom: 2px;
		position: relative;
		transition: background 160ms var(--ease-out), color 160ms var(--ease-out), transform 120ms var(--ease-out);
	}

	.nav-item:hover {
		background: var(--bg-hover);
		color: var(--text-primary);
	}

	.nav-item:active {
		transform: scale(0.98);
	}

	.nav-item.active {
		background: var(--bg-active);
		color: var(--text-primary);
	}

	.nav-item.active::before {
		content: '';
		position: absolute;
		left: 0;
		top: 6px;
		bottom: 6px;
		width: 3px;
		background-color: var(--accent-primary);
		border-radius: 99px;
	}

	.main-content {
		flex: 1;
		background: var(--bg-app);
		overflow-y: auto;
		display: flex;
		flex-direction: column;
	}

	.sidebar-footer {
		padding: 16px 8px;
		border-top: 1px solid var(--border-subtle);
		display: flex;
		flex-direction: column;
		gap: 12px;
	}

	.nav-item-button {
		width: 100%;
		background: transparent;
		border: none;
		text-align: left;
		cursor: pointer;
		font: inherit;
	}

	/* Auth Screen Styles */
	.auth-container {
		display: flex;
		align-items: center;
		justify-content: center;
		height: 100vh;
		background: var(--bg-app);
	}

	.auth-card {
		width: 100%;
		max-width: 360px;
		padding: 32px;
	}

	.auth-header {
		text-align: center;
		margin-bottom: 24px;
	}

	.auth-header h2 {
		font-size: 18px;
		margin-bottom: 8px;
	}

	.auth-header p {
		color: var(--text-secondary);
		font-size: 13px;
	}

	.auth-tabs {
		display: flex;
		background: var(--bg-app);
		border: 1px solid var(--border-subtle);
		border-radius: 6px;
		padding: 3px;
		margin-bottom: 24px;
	}

	.auth-tab {
		flex: 1;
		background: transparent;
		border: none;
		color: var(--text-secondary);
		font-size: 13px;
		font-weight: 500;
		padding: 6px 0;
		border-radius: 4px;
		cursor: pointer;
		transition: background 150ms var(--ease-out), color 150ms var(--ease-out), transform 100ms ease;
		user-select: none;
	}

	.auth-tab:active {
		transform: scale(0.97);
	}

	.auth-tab.active {
		background: var(--bg-hover);
		color: var(--text-primary);
		box-shadow: var(--shadow-sm);
	}

	.form-group {
		margin-bottom: 16px;
	}

	.form-group label {
		display: block;
		font-size: 12px;
		font-weight: 500;
		color: var(--text-secondary);
		margin-bottom: 6px;
	}

	.input-field {
		width: 100%;
		padding: 8px 12px;
		background: var(--bg-app);
		border: 1px solid var(--border-subtle);
		border-radius: 6px;
		color: var(--text-primary);
		font-size: 13px;
		transition: border-color 150ms var(--ease-out);
		outline: none;
	}

	.input-field:focus {
		border-color: var(--accent-primary);
		box-shadow: 0 0 0 3px rgba(var(--accent-primary-rgb), 0.12);
	}

	.btn-block {
		width: 100%;
	}

	.error-msg {
		color: var(--color-critical);
		font-size: 12px;
		margin-top: 8px;
		text-align: center;
	}

	/* User info in sidebar footer */
	.user-info {
		padding: 0 8px;
		gap: 10px;
	}

	.user-avatar {
		width: 22px;
		height: 22px;
		background: var(--bg-hover);
		border: 1px solid var(--border-strong);
		color: var(--text-primary);
		border-radius: 50%;
		display: flex;
		align-items: center;
		justify-content: center;
		font-size: 11px;
		font-weight: 600;
	}

	.user-email {
		font-size: 12px;
		font-weight: 500;
		color: var(--text-secondary);
		white-space: nowrap;
		overflow: hidden;
		text-overflow: ellipsis;
	}
</style>
