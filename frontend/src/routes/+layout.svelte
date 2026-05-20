<script lang="ts">
	import '../app.css';
	import { toasts, toast } from '$lib/toastStore';
	import { page } from '$app/stores';
	import { authState } from '$lib/auth.svelte';
	import { apiFetch } from '$lib/api';
	import { onMount } from 'svelte';

	let { children } = $props();

	let isLogin = $state(true);
	let email = $state('');
	let password = $state('');
	let loginError = $state('');
	let loading = $state(false);

	onMount(async () => {
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
			loginError = 'Connection error. Please try again.';
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
				<div class="workspace-avatar" style="margin: 0 auto 16px;">C</div>
				<h2>{isLogin ? 'Log in to ContractsPulse' : 'Create an Account'}</h2>
				<p>{isLogin ? 'Enter your credentials to access your workspace.' : 'Register a new account to get started.'}</p>
			</div>

			{#if !authState.signupDisabled}
				<div class="auth-tabs">
					<button 
						type="button" 
						class="auth-tab" 
						class:active={isLogin} 
						onclick={() => { isLogin = true; loginError = ''; }}
					>
						Log In
					</button>
					<button 
						type="button" 
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

			{#if authState.signupDisabled && isLogin}
				<div class="signup-disabled-banner">
					<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" class="banner-icon"><circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/></svg>
					<span>Signups are disabled for this instance</span>
				</div>
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
				<div class="workspace-avatar">C</div>
				<div class="workspace-name">ContractsPulse</div>
			</div>

			<nav class="sidebar-nav">
				<div class="nav-section">
					<div class="nav-label">Your Workspace</div>
					<a href="/" class="nav-item {$page.url.pathname === '/' ? 'active' : ''}">
						<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="3" y="3" width="18" height="18" rx="2"/><path d="M3 9h18M9 21V9"/></svg>
						Dashboard
					</a>
					<a href="/contracts" class="nav-item {$page.url.pathname === '/contracts' ? 'active' : ''}">
						<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/><line x1="16" y1="13" x2="8" y2="13"/><line x1="16" y1="17" x2="8" y2="17"/><polyline points="10 9 9 9 8 9"/></svg>
						All Contracts
					</a>
					<a href="/risk" class="nav-item {$page.url.pathname === '/risk' ? 'active' : ''}">
						<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"/><line x1="12" y1="9" x2="12" y2="13"/><line x1="12" y1="17" x2="12.01" y2="17"/></svg>
						Risk Inbox
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
		bottom: 24px;
		right: 24px;
		display: flex;
		flex-direction: column;
		gap: 8px;
		z-index: 100;
		pointer-events: none;
	}

	:global(.toast) {
		background: #1c1c1e;
		border: 1px solid var(--border-subtle);
		color: #fff;
		padding: 12px 16px;
		border-radius: 8px;
		font-size: 13px;
		font-weight: 500;
		box-shadow: 0 8px 24px rgba(0,0,0,0.4);
		pointer-events: auto;
		animation: slideIn 0.3s cubic-bezier(0.23, 1, 0.32, 1) forwards;
		transform-origin: bottom center;
	}

	:global(.toast-error) { border-color: rgba(248, 81, 73, 0.5); }
	:global(.toast-success) { border-color: rgba(63, 185, 80, 0.5); }

	:global(.toast-content) {
		display: flex;
		align-items: center;
		gap: 10px;
	}

	@keyframes slideIn {
		from { opacity: 0; transform: translateY(20px) scale(0.95); }
		to { opacity: 1; transform: translateY(0) scale(1); }
	}

	.app-layout {
		display: flex;
		height: 100vh;
		overflow: hidden;
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
		color: white;
		border-radius: 4px;
		display: flex;
		align-items: center;
		justify-content: center;
		font-size: 12px;
		font-weight: 600;
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
		transition: background 100ms ease, color 100ms ease;
	}

	.nav-item:hover {
		background: var(--bg-hover);
		color: var(--text-primary);
	}

	.nav-item.active {
		background: var(--bg-active);
		color: var(--text-primary);
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
		box-shadow: 0 1px 2px rgba(0,0,0,0.2);
	}

	.signup-disabled-banner {
		display: flex;
		align-items: center;
		gap: 8px;
		background: rgba(210, 153, 34, 0.08);
		border: 1px solid rgba(210, 153, 34, 0.2);
		border-radius: 6px;
		padding: 10px 12px;
		margin-bottom: 24px;
		color: #d29922;
		font-size: 12px;
		font-weight: 500;
	}

	.banner-icon {
		flex-shrink: 0;
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
		border-color: var(--text-secondary);
	}

	.btn-block {
		width: 100%;
	}

	.error-msg {
		color: #e5484d;
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
