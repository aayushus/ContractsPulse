## 2024-07-03 - [Accordion ARIA State]
**Learning:** In the Svelte frontend, when implementing accordion toggles using `<button>`, standard screen reader visibility of the expanded state (`aria-expanded`) must be manually included using `aria-expanded={!!stateVar}` to correctly output true/false boolean string values. This pattern is essential for any custom-built expansion panels.
**Action:** Always verify accordion-like buttons and disclosure widgets in custom Svelte components contain dynamically bound `aria-expanded` attributes connected to their collapse/expand state variables.
## 2024-05-19 - Suggestion Pill Auto-Submit
**Learning:** In chat interfaces, users expect that clicking a "suggestion" or "example" prompt not only fills in the input box but also immediately triggers the submission. Previously, suggestion pills only filled the input, requiring an extra click on the "Send" button.
**Action:** Always bind auto-submit behaviors (`sendChat()`) along with setting the input state when implementing suggestion chips.
