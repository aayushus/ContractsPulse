class AuthState {
	token = $state<string | null>(null);
	user = $state<{ id: string; email: string } | null>(null);
	signupDisabled = $state<boolean>(false);
	initialized = $state<boolean>(false);

	get isAuthenticated(): boolean {
		return !!this.token && !!this.user;
	}

	constructor() {
		if (typeof window !== 'undefined') {
			this.token = localStorage.getItem('cp_token');
			const savedUser = localStorage.getItem('cp_user');
			if (savedUser) {
				try {
					this.user = JSON.parse(savedUser);
				} catch (e) {
					this.user = null;
				}
			}
		}
	}

	setToken(token: string | null) {
		this.token = token;
		if (typeof window !== 'undefined') {
			if (token) {
				localStorage.setItem('cp_token', token);
			} else {
				localStorage.removeItem('cp_token');
				localStorage.removeItem('cp_user');
				this.user = null;
			}
		}
	}

	setUser(user: { id: string; email: string } | null) {
		this.user = user;
		if (typeof window !== 'undefined') {
			if (user) {
				localStorage.setItem('cp_user', JSON.stringify(user));
			} else {
				localStorage.removeItem('cp_user');
			}
		}
	}

	logout() {
		this.setToken(null);
		this.setUser(null);
	}
}

export const authState = new AuthState();
