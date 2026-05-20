/**
 * Svelte 5 Custom Action for Premium Radial Hover Glow Effects
 * Simulates directional light reflection on dark metallic/glass surfaces.
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
