import { writable } from 'svelte/store';

export type ToastType = 'info' | 'success' | 'error' | 'loading';

export interface Toast {
	id: string;
	message: string;
	type: ToastType;
}

export const toasts = writable<Toast[]>([]);

export const toast = {
	show(message: string, type: ToastType = 'info', duration: number = 3000) {
		const id = Math.random().toString(36).substr(2, 9);
		toasts.update((all) => [...all, { id, message, type }]);

		if (type !== 'loading') {
			setTimeout(() => {
				toast.dismiss(id);
			}, duration);
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
		return this.show(message, 'loading', 0); // Requires manual dismissal
	},

	dismiss(id: string) {
		toasts.update((all) => all.filter((t) => t.id !== id));
	}
};
