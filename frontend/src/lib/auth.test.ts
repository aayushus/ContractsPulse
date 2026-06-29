import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { AuthState } from './auth.svelte';

describe('AuthState', () => {
	const originalWindow = global.window;

	let getItemMock: ReturnType<typeof vi.fn>;
	let setItemMock: ReturnType<typeof vi.fn>;
	let removeItemMock: ReturnType<typeof vi.fn>;

	beforeEach(() => {
		getItemMock = vi.fn();
		setItemMock = vi.fn();
		removeItemMock = vi.fn();

		// Mock localStorage
		Object.defineProperty(global, 'localStorage', {
			value: {
				getItem: getItemMock,
				setItem: setItemMock,
				removeItem: removeItemMock
			},
			writable: true
		});
	});

	afterEach(() => {
		if (originalWindow === undefined) {
			// @ts-ignore
			delete global.window;
		} else {
			global.window = originalWindow;
		}
		vi.restoreAllMocks();
	});

	describe('Constructor', () => {
		it('should handle SSR environments gracefully (window is undefined)', () => {
			// @ts-ignore
			delete global.window;
			const auth = new AuthState();
			expect(auth.token).toBeNull();
			expect(auth.user).toBeNull();
			expect(getItemMock).not.toHaveBeenCalled();
		});

		it('should correctly initialize token and user from localStorage on load', () => {
			getItemMock.mockImplementation((key) => {
				if (key === 'cp_token') return 'test_token';
				if (key === 'cp_user') return JSON.stringify({ id: '1', email: 'test@example.com' });
				return null;
			});

			const auth = new AuthState();
			expect(auth.token).toBe('test_token');
			expect(auth.user).toEqual({ id: '1', email: 'test@example.com' });
		});

		it('should handle invalid JSON in localStorage for cp_user safely', () => {
			getItemMock.mockImplementation((key) => {
				if (key === 'cp_token') return 'test_token';
				if (key === 'cp_user') return 'invalid_json';
				return null;
			});

			const auth = new AuthState();
			expect(auth.token).toBe('test_token');
			expect(auth.user).toBeNull();
		});
	});

	describe('Authentication Status', () => {
		it('should return false if neither token nor user exist', () => {
			const auth = new AuthState();
			expect(auth.isAuthenticated).toBe(false);
		});

		it('should return false if only token exists', () => {
			getItemMock.mockImplementation((key) => key === 'cp_token' ? 'test_token' : null);
			const auth = new AuthState();
			expect(auth.isAuthenticated).toBe(false);
		});

		it('should return false if only user exists', () => {
			getItemMock.mockImplementation((key) => key === 'cp_user' ? JSON.stringify({ id: '1', email: 't@t.com' }) : null);
			const auth = new AuthState();
			expect(auth.isAuthenticated).toBe(false);
		});

		it('should return true when both token and user exist', () => {
			getItemMock.mockImplementation((key) => {
				if (key === 'cp_token') return 'test_token';
				if (key === 'cp_user') return JSON.stringify({ id: '1', email: 't@t.com' });
				return null;
			});
			const auth = new AuthState();
			expect(auth.isAuthenticated).toBe(true);
		});
	});

	describe('Setters', () => {
		it('setToken(token) should set state and update localStorage', () => {
			const auth = new AuthState();
			auth.setToken('new_token');
			expect(auth.token).toBe('new_token');
			expect(setItemMock).toHaveBeenCalledWith('cp_token', 'new_token');
		});

		it('setToken(null) should clear cp_token and cp_user from localStorage and nullify user state', () => {
			getItemMock.mockImplementation((key) => {
				if (key === 'cp_token') return 'test_token';
				if (key === 'cp_user') return JSON.stringify({ id: '1', email: 't@t.com' });
				return null;
			});
			const auth = new AuthState();
			auth.setToken(null);

			expect(auth.token).toBeNull();
			expect(auth.user).toBeNull();
			expect(removeItemMock).toHaveBeenCalledWith('cp_token');
			expect(removeItemMock).toHaveBeenCalledWith('cp_user');
		});

		it('setUser(user) should set state and correctly stringify to localStorage', () => {
			const auth = new AuthState();
			const user = { id: '2', email: 'test2@example.com' };
			auth.setUser(user);

			expect(auth.user).toEqual(user);
			expect(setItemMock).toHaveBeenCalledWith('cp_user', JSON.stringify(user));
		});

		it('setUser(null) should clear state and cp_user from localStorage', () => {
			const auth = new AuthState();
			auth.setUser(null);

			expect(auth.user).toBeNull();
			expect(removeItemMock).toHaveBeenCalledWith('cp_user');
		});
	});

	describe('Logout', () => {
		it('should delegate to clearing token and user, ensuring complete cleanup', () => {
			getItemMock.mockImplementation((key) => {
				if (key === 'cp_token') return 'test_token';
				if (key === 'cp_user') return JSON.stringify({ id: '1', email: 't@t.com' });
				return null;
			});
			const auth = new AuthState();

			// Spy on the methods
			const setTokenSpy = vi.spyOn(auth, 'setToken');
			const setUserSpy = vi.spyOn(auth, 'setUser');

			auth.logout();

			expect(setTokenSpy).toHaveBeenCalledWith(null);
			expect(setUserSpy).toHaveBeenCalledWith(null);

			expect(auth.token).toBeNull();
			expect(auth.user).toBeNull();

			// setToken(null) does the removing from local storage. Let's make sure it was called.
			expect(removeItemMock).toHaveBeenCalledWith('cp_token');
			expect(removeItemMock).toHaveBeenCalledWith('cp_user');
		});
	});
});
