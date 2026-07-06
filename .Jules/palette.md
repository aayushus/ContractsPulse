## 2024-07-03 - [Accordion ARIA State]
**Learning:** In the Svelte frontend, when implementing accordion toggles using `<button>`, standard screen reader visibility of the expanded state (`aria-expanded`) must be manually included using `aria-expanded={!!stateVar}` to correctly output true/false boolean string values. This pattern is essential for any custom-built expansion panels.
**Action:** Always verify accordion-like buttons and disclosure widgets in custom Svelte components contain dynamically bound `aria-expanded` attributes connected to their collapse/expand state variables.

## 2026-07-06 - [Auto-submit Suggestion Pills]
**Learning:** For suggestion pills in chat interfaces or search inputs, requiring the user to click the pill to populate the input, and then requiring a second click to submit the form is a point of friction.
**Action:** When implementing suggestion pills or example prompts, configure their `onclick` handlers to both set the input value and automatically trigger the submission function to reduce user friction.
