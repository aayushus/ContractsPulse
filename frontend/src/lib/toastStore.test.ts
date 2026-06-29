import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { get } from 'svelte/store';
import { toast, toasts } from './toastStore';

describe('toastStore', () => {
	beforeEach(() => {
		// Reset the store before each test
		toasts.set([]);
		vi.useFakeTimers();
	});

	afterEach(() => {
		// Clean up any remaining toasts to clear timeouts
		const currentToasts = get(toasts);
		currentToasts.forEach((t) => toast.dismiss(t.id));
		vi.restoreAllMocks();
	});

	it('should have an empty initial state', () => {
		expect(get(toasts)).toEqual([]);
	});

	it('should show a default info toast', () => {
		const id = toast.show('Hello World');
		const currentToasts = get(toasts);
		expect(currentToasts).toHaveLength(1);
		expect(currentToasts[0]).toEqual({
			id,
			message: 'Hello World',
			type: 'info'
		});
	});

	it('should show success, error, and loading toasts', () => {
		const successId = toast.success('Success');
		const errorId = toast.error('Error');
		const loadingId = toast.loading('Loading');

		const currentToasts = get(toasts);
		expect(currentToasts).toHaveLength(3);
		expect(currentToasts[0]).toMatchObject({ id: successId, message: 'Success', type: 'success' });
		expect(currentToasts[1]).toMatchObject({ id: errorId, message: 'Error', type: 'error' });
		expect(currentToasts[2]).toMatchObject({ id: loadingId, message: 'Loading', type: 'loading' });
	});

	it('should cap at MAX_TOASTS (5) and remove the oldest', () => {
		const ids = [];
		for (let i = 0; i < 6; i++) {
			ids.push(toast.show(`Message ${i}`));
		}

		const currentToasts = get(toasts);
		expect(currentToasts).toHaveLength(5);
		// The first toast (ids[0]) should be removed
		expect(currentToasts[0].id).toBe(ids[1]);
		expect(currentToasts[4].id).toBe(ids[5]);
	});

	it('should auto-dismiss toast after duration', () => {
		toast.show('Auto dismiss', 'info', 3000);
		expect(get(toasts)).toHaveLength(1);

		// Advance time by 2999ms, toast should still be there
		vi.advanceTimersByTime(2999);
		expect(get(toasts)).toHaveLength(1);

		// Advance time to 3000ms, toast should be dismissed
		vi.advanceTimersByTime(1);
		expect(get(toasts)).toHaveLength(0);
	});

	it('should not auto-dismiss loading toasts', () => {
		toast.loading('Loading...');
		expect(get(toasts)).toHaveLength(1);

		// Advance time by a large amount
		vi.advanceTimersByTime(10000);
		expect(get(toasts)).toHaveLength(1);
	});

	it('should allow manual dismissal', () => {
		const id = toast.show('Manual dismiss');
		expect(get(toasts)).toHaveLength(1);

		toast.dismiss(id);
		expect(get(toasts)).toHaveLength(0);
	});

	it('should clear timeout when manually dismissed early', () => {
		const id = toast.show('Dismiss early', 'info', 3000);
		expect(get(toasts)).toHaveLength(1);

		toast.dismiss(id);
		expect(get(toasts)).toHaveLength(0);

		// Advance time past the original duration to ensure no errors occur
		vi.advanceTimersByTime(3000);
		expect(get(toasts)).toHaveLength(0);
	});
});
