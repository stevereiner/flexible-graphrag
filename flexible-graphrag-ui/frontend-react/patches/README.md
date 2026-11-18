# Patches to dependencies

Applied by `patch-package` on every `npm install` / `npm ci` (the `postinstall` script). A patch is tied to the
exact version in its file name, so that package is pinned in `package.json`; after upgrading it, re-make the patch
(edit the file in `node_modules`, then `npx patch-package <package>`) or drop it if the new version fixes the issue.

- `@cubone+react-file-manager+1.37.0.patch`: a double-click opens a folder only when the two clicks are less than
  300 ms apart (its own timing in the item click handler, not the browser's `dblclick`), too fast for most people
  (Windows' default is 500 ms). Raised to 500 ms.
