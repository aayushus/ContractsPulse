import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { getApiBase } from './api';

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
