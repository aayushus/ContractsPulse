## 2024-11-21 - Accessible Authentication Tabs
**Learning:** Native `<button>` elements used as a toggle group (like Login/Signup) need explicit WAI-ARIA `role="tab"` and `role="tablist"` attributes to be properly announced by screen readers, even when styled like tabs.
**Action:** Always ensure that visual tab interfaces use standard ARIA roles (`tablist`, `tab`, `tabpanel`) or `aria-pressed` for semantic accessibility.
