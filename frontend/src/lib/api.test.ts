import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { getApiBase, apiFetch } from './api';
import { authState } from './auth.svelte';

describe('getApiBase', () => {
	const originalWindow = global.window;

	afterEach(() => {
		// Restore window after each test
		if (originalWindow === undefined) {
			// @ts-ignore
			delete global.window;
		} else {
			global.window = originalWindow;
		}
	});

	it('should return http://localhost:9432 when window is undefined (SSR context)', () => {
		// @ts-ignore
		delete global.window;
		expect(getApiBase()).toBe('http://localhost:9432');
	});

	it('should return protocol://hostname:9432 when window.location.href has port 5173 (local development)', () => {
		global.window = Object.create(window);
		Object.defineProperty(window, 'location', {
			value: {
				href: 'http://localhost:5173/some/path'
			},
			writable: true
		});

		expect(getApiBase()).toBe('http://localhost:9432');
	});

	it('should return protocol://host when window.location.href has port other than 5173 (e.g., 80 or 443 proxy)', () => {
		global.window = Object.create(window);
		Object.defineProperty(window, 'location', {
			value: {
				href: 'https://app.contractspulse.com/some/path'
			},
			writable: true
		});

		expect(getApiBase()).toBe('https://app.contractspulse.com');
	});

	it('should return protocol://host when window.location.href has an explicit custom port other than 5173', () => {
		global.window = Object.create(window);
		Object.defineProperty(window, 'location', {
			value: {
				href: 'http://192.168.1.10:8080/some/path'
			},
			writable: true
		});

		expect(getApiBase()).toBe('http://192.168.1.10:8080');
	});
});

describe('apiFetch', () => {
	const originalFetch = global.fetch;
	const originalWindow = global.window;

	beforeEach(() => {
		global.fetch = vi.fn();
		// Set up window to get a predictable getApiBase() result
		global.window = Object.create(window);
		Object.defineProperty(window, 'location', {
			value: { href: 'http://localhost:5173' },
			writable: true
		});
	});

	afterEach(() => {
		global.fetch = originalFetch;
		if (originalWindow === undefined) {
			// @ts-ignore
			delete global.window;
		} else {
			global.window = originalWindow;
		}
		vi.restoreAllMocks();
		authState.setToken(null);
	});

	it('should set Authorization header when token is present', async () => {
		authState.setToken('test-token');
		const mockResponse = new Response(null, { status: 200 });
		(global.fetch as ReturnType<typeof vi.fn>).mockResolvedValue(mockResponse);

		await apiFetch('/test-path');

		expect(global.fetch).toHaveBeenCalledWith('http://localhost:9432/test-path', expect.objectContaining({
			headers: expect.any(Headers)
		}));

		const callArgs = (global.fetch as ReturnType<typeof vi.fn>).mock.calls[0];
		const headers = callArgs[1].headers as Headers;
		expect(headers.get('Authorization')).toBe('Bearer test-token');
	});

	it('should call authState.logout() when response status is 401', async () => {
		const logoutSpy = vi.spyOn(authState, 'logout');
		const mockResponse = new Response(null, { status: 401 });
		(global.fetch as ReturnType<typeof vi.fn>).mockResolvedValue(mockResponse);

		await apiFetch('/test-path');

		expect(logoutSpy).toHaveBeenCalledTimes(1);
	});

	it('should not call authState.logout() when response status is not 401', async () => {
		const logoutSpy = vi.spyOn(authState, 'logout');
		const mockResponse = new Response(null, { status: 200 });
		(global.fetch as ReturnType<typeof vi.fn>).mockResolvedValue(mockResponse);

		await apiFetch('/test-path');

		expect(logoutSpy).not.toHaveBeenCalled();
	});
});
