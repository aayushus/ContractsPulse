## 2024-05-24 - Hiding decorative icons inside descriptive buttons
**Learning:** Decorative SVG icons that sit inside a button alongside descriptive text should be hidden from screen readers using `aria-hidden="true"`. Otherwise, screen readers may announce them as unlabelled graphics, which is confusing and redundant since the button already has text.
**Action:** When adding icons inside text buttons, always apply `aria-hidden="true"` to the `<svg>` element.
