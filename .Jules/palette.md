## 2024-07-03 - [Accordion ARIA State]
**Learning:** In the Svelte frontend, when implementing accordion toggles using `<button>`, standard screen reader visibility of the expanded state (`aria-expanded`) must be manually included using `aria-expanded={!!stateVar}` to correctly output true/false boolean string values. This pattern is essential for any custom-built expansion panels.
**Action:** Always verify accordion-like buttons and disclosure widgets in custom Svelte components contain dynamically bound `aria-expanded` attributes connected to their collapse/expand state variables.
