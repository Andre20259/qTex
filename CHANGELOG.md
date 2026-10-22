# Changelog

Each release's notes on GitHub are taken from its section here.
Write upcoming changes under **Unreleased**; `release.ps1` turns that section into the new version.

## [Unreleased]

### Added
- **Highlight source** button on the PDF toolbar: point at the PDF and the matching line is highlighted in the editor (switching tabs if it's in another file).
- `Ctrl+click` on the PDF jumps to that line in the editor.
- *Sync PDF to Cursor* (`Ctrl+J`) now outlines the matching text in the PDF for a moment.
- `Shift` + mouse wheel scrolls the PDF sideways when zoomed in; `Ctrl` + mouse wheel zooms.

### Fixed
- Zooming in or out from *Fit width* / *Fit page* now continues from the current size instead of jumping to 100%.

## [1.0.1] - 2026-10-22

### Fixed
- The project tree hidden with `Ctrl+B` no longer reappears when you type, switch tabs or compile. It also stays hidden after restarting.

### Added
- Help → About, with version and license.

## [1.0.0] - 2026-10-22

First release.

- Opens whole LaTeX projects: file tree, tabs, automatic main-file detection, `% !TEX root` support.
- Live PDF preview that recompiles as you type.
- Built-in build pipeline (LaTeX, BibTeX/Biber, makeindex, reruns), so no Perl or latexmk is needed. latexmk is optional.
- Problems panel with errors and warnings per file; click one to jump to it.
- SyncTeX: jump from the cursor to the matching spot in the PDF (`Ctrl+J`).
- Windows installer and portable zip.
