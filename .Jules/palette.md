## 2024-07-03 - [Accordion ARIA State]
**Learning:** In the Svelte frontend, when implementing accordion toggles using `<button>`, standard screen reader visibility of the expanded state (`aria-expanded`) must be manually included using `aria-expanded={!!stateVar}` to correctly output true/false boolean string values. This pattern is essential for any custom-built expansion panels.
**Action:** Always verify accordion-like buttons and disclosure widgets in custom Svelte components contain dynamically bound `aria-expanded` attributes connected to their collapse/expand state variables.
## 2024-05-19 - Suggestion Pill Auto-Submit
**Learning:** In chat interfaces, users expect that clicking a "suggestion" or "example" prompt not only fills in the input box but also immediately triggers the submission. Previously, suggestion pills only filled the input, requiring an extra click on the "Send" button.
**Action:** Always bind auto-submit behaviors (`sendChat()`) along with setting the input state when implementing suggestion chips.
## 2026-07-11 - Added ARIA attributes to custom dropdown menus
**Learning:** Custom dropdown triggers (like ) require  and a dynamic  state to properly communicate their function and state to screen readers.
**Action:** Always include these ARIA attributes when building or modifying custom combobox or select button elements.
## 2024-05-24 - Added ARIA attributes to custom dropdown menus
**Learning:** Custom dropdown triggers (like `custom-select-trigger`) require `aria-haspopup="listbox"` and a dynamic `aria-expanded` state to properly communicate their function and state to screen readers.
**Action:** Always include these ARIA attributes when building or modifying custom combobox or select button elements.
## 2024-07-28 - [ARIA Pressed on Filter Pills]
**Learning:** Custom UI filter groups (like `filter-pill`s) acting as mutually exclusive toggles or tabs must include `aria-pressed={state === 'VALUE'}` attributes. Relying solely on CSS `.active` classes leaves screen reader users completely unaware of which filter is currently active.
**Action:** Always verify that custom segment controls and filter pills contain dynamically bound ARIA attributes (e.g. `aria-pressed` or `aria-selected`) mirroring their visual active state.
## 2026-07-16 - Custom Dropdown Popup
**Learning:** Screen readers require knowledge of what type of popup an element spawns. When making a custom dropdown trigger button, simply having `aria-expanded` is not enough; it must explicitly state `aria-haspopup="listbox"`.
**Action:** Always include `aria-haspopup="listbox"` (or appropriate role) on elements functioning as custom select triggers to satisfy accessibility standards.
