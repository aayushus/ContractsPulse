## 2024-07-03 - [Accordion ARIA State]
**Learning:** In the Svelte frontend, when implementing accordion toggles using `<button>`, standard screen reader visibility of the expanded state (`aria-expanded`) must be manually included using `aria-expanded={!!stateVar}` to correctly output true/false boolean string values. This pattern is essential for any custom-built expansion panels.
**Action:** Always verify accordion-like buttons and disclosure widgets in custom Svelte components contain dynamically bound `aria-expanded` attributes connected to their collapse/expand state variables.

## 2024-07-04 - Loading States for Destructive Actions
**Learning:** Destructive actions like deleting contracts were missing loading indicators on the confirmation buttons, causing the modal to disappear instantly before the network request finished, which leaves the user uncertain of the system state.
**Action:** Always add an `isDeleting` or similar loading state to destructive action confirmation buttons, disable the button, show a spinner, and ensure the modal stays open until the request actually succeeds or fails.
