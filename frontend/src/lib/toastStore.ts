import { writable } from 'svelte/store';

export type ToastType = 'info' | 'success' | 'error' | 'loading';

export interface Toast {
	id: string;
	message: string;
	type: ToastType;
}

const MAX_TOASTS = 5;

export const toasts = writable<Toast[]>([]);

// Track timeouts so they can be cleared on manual dismiss
const timeoutMap = new Map<string, ReturnType<typeof setTimeout>>();

export const toast = {
	show(message: string, type: ToastType = 'info', duration: number = 3000) {
		const id = Math.random().toString(36).substring(2, 11);
		
		toasts.update((all) => {
			const next = [...all, { id, message, type }];
			// Cap at MAX_TOASTS — remove oldest
			if (next.length > MAX_TOASTS) {
				const removed = next.shift();
				if (removed) {
					const timer = timeoutMap.get(removed.id);
					if (timer) { clearTimeout(timer); timeoutMap.delete(removed.id); }
				}
			}
			return next;
		});

		if (type !== 'loading') {
			const timer = setTimeout(() => {
				toast.dismiss(id);
			}, duration);
			timeoutMap.set(id, timer);
		}
		
		return id;
	},
	
	success(message: string, duration = 3000) {
		return this.show(message, 'success', duration);
	},
	
	error(message: string, duration = 5000) {
		return this.show(message, 'error', duration);
	},
	
	loading(message: string) {
		return this.show(message, 'loading', 0);
	},

	dismiss(id: string) {
		const timer = timeoutMap.get(id);
		if (timer) { clearTimeout(timer); timeoutMap.delete(id); }
		toasts.update((all) => all.filter((t) => t.id !== id));
	}
};
