import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { getApiBase, apiFetch } from './api';
import { authState } from './auth.svelte';

describe('apiFetch', () => {
	let fetchMock: any;
	let logoutSpy: any;

	beforeEach(() => {
		// Mock fetch globally
		fetchMock = vi.fn().mockResolvedValue({ status: 200 } as Response);
		vi.stubGlobal('fetch', fetchMock);

		// Spy on authState.logout
		logoutSpy = vi.spyOn(authState, 'logout');

		// Reset token state for tests
		authState.setToken(null);
	});

	afterEach(() => {
		vi.unstubAllGlobals();
		vi.restoreAllMocks();
	});

	it('should call fetch with correct URL and options', async () => {
		// Mock window for this test to ensure it hits getApiBase() as expected
		global.window = Object.create(window);
		Object.defineProperty(window, 'location', {
			value: { href: 'http://localhost:5173/some/path', port: '5173', protocol: 'http:', hostname: 'localhost' },
			writable: true
		});
		await apiFetch('/test-path', { method: 'POST' });

		expect(fetchMock).toHaveBeenCalledTimes(1);
		expect(fetchMock).toHaveBeenCalledWith('http://localhost:9432/test-path', expect.objectContaining({
			method: 'POST'
		}));
	});

	it('should add Authorization header if authState.token exists', async () => {
		authState.setToken('test-token');

		await apiFetch('/test-path');

		expect(fetchMock).toHaveBeenCalledTimes(1);
		const callArgs = fetchMock.mock.calls[0];
		const options = callArgs[1];
		expect(options.headers.get('Authorization')).toBe('Bearer test-token');
	});

	it('should not add Authorization header if authState.token is null', async () => {
		await apiFetch('/test-path');

		expect(fetchMock).toHaveBeenCalledTimes(1);
		const callArgs = fetchMock.mock.calls[0];
		const options = callArgs[1];
		expect(options.headers.has('Authorization')).toBe(false);
	});

	it('should call authState.logout() when response status is 401', async () => {
		fetchMock.mockResolvedValue({ status: 401 } as Response);

		await apiFetch('/test-path');

		expect(logoutSpy).toHaveBeenCalledTimes(1);
	});

	it('should not call authState.logout() when response status is 200', async () => {
		fetchMock.mockResolvedValue({ status: 200 } as Response);

		await apiFetch('/test-path');

		expect(logoutSpy).not.toHaveBeenCalled();
	});
});

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
