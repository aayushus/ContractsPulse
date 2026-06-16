## 2024-06-05 - Added ARIA label to revision upload modal file removal button\n**Learning:** Icon-only buttons for clearing selected files in modals often miss accessibility labels, making them invisible to screen readers.\n**Action:** Always check `.btn-remove-file` or similar icon-only buttons for `aria-label` and `title` attributes.

## 2026-06-16 - [Fix dropzone accessibility]
**Learning:** `div` dropzones missing `role="button"` and `tabindex` trigger svelte a11y warnings.
**Action:** Ensure all interactive non-button elements have appropriate ARIA roles and keyboard event handlers.
