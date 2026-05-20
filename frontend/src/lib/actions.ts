/**
 * Svelte 5 Custom Actions for Bleeding-Edge 2026-Era UI Aesthetics
 * Simulates real 3D glass perspective reflections, micro-tilts, and ambient glows.
 */

export function glow(node: HTMLElement, options?: { color?: string }) {
	const handlePointerMove = (e: PointerEvent) => {
		const rect = node.getBoundingClientRect();
		const x = e.clientX - rect.left;
		const y = e.clientY - rect.top;
		node.style.setProperty('--mouse-x', `${x}px`);
		node.style.setProperty('--mouse-y', `${y}px`);
	};

	node.classList.add('premium-glow-card');
	if (options?.color) {
		node.style.setProperty('--glow-color', options.color);
	}

	node.addEventListener('pointermove', handlePointerMove);

	return {
		update(newOptions?: { color?: string }) {
			if (newOptions?.color) {
				node.style.setProperty('--glow-color', newOptions.color);
			} else {
				node.style.removeProperty('--glow-color');
			}
		},
		destroy() {
			node.removeEventListener('pointermove', handlePointerMove);
		}
	};
}

/**
 * 3D Perspective Card Tilt Action
 * Physically tilts the card towards the mouse cursor on hover.
 */
export function tilt(node: HTMLElement, options?: { max?: number }) {
	const max = options?.max || 4; // Subtlety is key in premium design. Keep degrees small.
	
	const handlePointerMove = (e: PointerEvent) => {
		const rect = node.getBoundingClientRect();
		const x = e.clientX - rect.left;
		const y = e.clientY - rect.top;
		const w = rect.width;
		const h = rect.height;
		
		const normX = (x / w) - 0.5;
		const normY = (y / h) - 0.5;
		
		const rotX = -(normY * max).toFixed(2);
		const rotY = (normX * max).toFixed(2);
		
		node.style.transform = `perspective(1000px) rotateX(${rotX}deg) rotateY(${rotY}deg) translateY(-3px)`;
	};

	const handlePointerLeave = () => {
		node.style.transform = `perspective(1000px) rotateX(0deg) rotateY(0deg) translateY(0px)`;
	};

	node.style.transformStyle = 'preserve-3d';
	node.style.transition = 'transform 300ms cubic-bezier(0.25, 1, 0.5, 1), box-shadow 300ms ease, border-color 300ms ease';

	node.addEventListener('pointermove', handlePointerMove);
	node.addEventListener('pointerleave', handlePointerLeave);

	return {
		destroy() {
			node.removeEventListener('pointermove', handlePointerMove);
			node.removeEventListener('pointerleave', handlePointerLeave);
		}
	};
}

/**
 * Combined Premium 2026 Interactive Card action
 * Integrates 3D Perspective Tilt with Pointer-Tracking Ambient Glow in a single high-performance loop.
 */
export function premiumCard(node: HTMLElement, options?: { color?: string; maxTilt?: number }) {
	const max = options?.maxTilt || 5;
	
	const handlePointerMove = (e: PointerEvent) => {
		const rect = node.getBoundingClientRect();
		const x = e.clientX - rect.left;
		const y = e.clientY - rect.top;
		const w = rect.width;
		const h = rect.height;
		
		node.style.setProperty('--mouse-x', `${x}px`);
		node.style.setProperty('--mouse-y', `${y}px`);
		
		const normX = (x / w) - 0.5;
		const normY = (y / h) - 0.5;
		
		const rotX = -(normY * max).toFixed(2);
		const rotY = (normX * max).toFixed(2);
		
		node.style.transform = `perspective(1000px) rotateX(${rotX}deg) rotateY(${rotY}deg) translateY(-4px)`;
		node.style.boxShadow = '0 16px 40px rgba(0, 0, 0, 0.45), 0 1px 2px rgba(255, 255, 255, 0.05)';
	};

	const handlePointerLeave = () => {
		node.style.transform = `perspective(1000px) rotateX(0deg) rotateY(0deg) translateY(0px)`;
		node.style.boxShadow = '';
	};

	node.classList.add('premium-glow-card');
	if (options?.color) {
		node.style.setProperty('--glow-color', options.color);
	}

	node.style.transformStyle = 'preserve-3d';
	node.style.transition = 'transform 350ms cubic-bezier(0.16, 1, 0.3, 1), box-shadow 350ms cubic-bezier(0.16, 1, 0.3, 1), border-color 350ms ease';

	node.addEventListener('pointermove', handlePointerMove);
	node.addEventListener('pointerleave', handlePointerLeave);

	return {
		update(newOptions?: { color?: string; maxTilt?: number }) {
			if (newOptions?.color) {
				node.style.setProperty('--glow-color', newOptions.color);
			} else {
				node.style.removeProperty('--glow-color');
			}
		},
		destroy() {
			node.removeEventListener('pointermove', handlePointerMove);
			node.removeEventListener('pointerleave', handlePointerLeave);
		}
	};
}
