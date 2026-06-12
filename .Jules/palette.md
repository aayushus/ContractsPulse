## 2023-10-27 - [Add accessibility keyboard handler to upload dropzone]
**Learning:** Svelte enforces strict a11y checks; adding `role="button"`, `tabindex="0"`, and `onkeydown` correctly prevents the generic div element from being a purely static component.
**Action:** Next time looking to add accessibility for clickable generic components like `div` in Svelte, always remember to pair `onclick` with `role="button"`, `tabindex="0"`, and `onkeydown` to make it keyboard navigatable.
