1. **Understand the Goal**: Identify a UX enhancement for the Contractspulse app, fix it, and verify it with the `pnpm check`/`npm run check` commands. Keep it under 50 lines.
2. **Identified Issue**: The `svelte-check` tool reported an accessibility error in `frontend/src/routes/contracts/[id]/+page.svelte` at line 1719:
   - A `<div>` element with an `onclick` handler lacks a `role` and `tabindex`, plus it requires keyboard event handlers like `onkeydown`.
3. **Proposed Fix**: Add `role="button" tabindex="0"` to the `.upload-dropzone` `<div>` element and implement `onkeydown` to trigger a click on the hidden `<input type="file">` when the user presses Enter or Space. This improves accessibility significantly for screen reader users and keyboard navigators.
4. **Implementation Steps**:
   - Update `frontend/src/routes/contracts/[id]/+page.svelte` at line 1719.
   - Replace `<div class="upload-dropzone" onclick={() => revisionFileInput?.click()}>` with `<div class="upload-dropzone" role="button" tabindex="0" onclick={() => revisionFileInput?.click()} onkeydown={(e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); revisionFileInput?.click(); } }}>`
5. **Pre Commit Steps**: Ensure proper testing, verifications, reviews and reflections are done. Run `npm run check` and ensure it doesn't fail.
6. **Submit**: Create a commit with a relevant message.
