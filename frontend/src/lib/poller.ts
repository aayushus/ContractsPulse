/**
 * Adaptive poller used for live-updating views (dashboard, contracts list).
 *
 * Instead of a fixed `setInterval`, it:
 *  - polls quickly (`activeMs`) only while there is work in progress (`isActive`)
 *  - backs off to a slow cadence (`idleMs`) when nothing is happening
 *  - pauses entirely while the tab is hidden, and refreshes immediately on return
 *
 * This avoids hammering the API forever and stops the list from flickering when
 * the user isn't even looking at the page.
 */
export type AdaptivePollerOptions = {
	/** The work to run on each tick (e.g. fetch contracts). */
	fn: () => void | Promise<void>;
	/** Returns true while fast polling is warranted (e.g. something is PROCESSING). */
	isActive: () => boolean;
	/** Delay between polls while active. Default 3000ms. */
	activeMs?: number;
	/** Delay between polls while idle. Default 30000ms. */
	idleMs?: number;
	/** Run `fn` immediately on start. Default true. */
	runImmediately?: boolean;
};

export type AdaptivePoller = {
	start: () => void;
	stop: () => void;
};

export function createAdaptivePoller(opts: AdaptivePollerOptions): AdaptivePoller {
	const activeMs = opts.activeMs ?? 3000;
	const idleMs = opts.idleMs ?? 30000;
	const runImmediately = opts.runImmediately ?? true;

	let timer: ReturnType<typeof setTimeout> | null = null;
	let stopped = true;
	let running = false;

	const isHidden = () => typeof document !== 'undefined' && document.hidden;

	function clearTimer() {
		if (timer !== null) {
			clearTimeout(timer);
			timer = null;
		}
	}

	function schedule() {
		clearTimer();
		if (stopped || isHidden()) return;
		const delay = opts.isActive() ? activeMs : idleMs;
		timer = setTimeout(tick, delay);
	}

	async function tick() {
		timer = null;
		if (stopped || isHidden() || running) return;
		running = true;
		try {
			await opts.fn();
		} finally {
			running = false;
			schedule();
		}
	}

	function onVisibility() {
		if (stopped) return;
		if (isHidden()) {
			clearTimer();
		} else {
			// Tab came back into focus: refresh now, then resume the cadence.
			void tick();
		}
	}

	function start() {
		if (!stopped) return;
		stopped = false;
		if (typeof document !== 'undefined') {
			document.addEventListener('visibilitychange', onVisibility);
		}
		if (runImmediately) {
			void tick();
		} else {
			schedule();
		}
	}

	function stop() {
		stopped = true;
		clearTimer();
		if (typeof document !== 'undefined') {
			document.removeEventListener('visibilitychange', onVisibility);
		}
	}

	return { start, stop };
}
