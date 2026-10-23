# Changelog

Each release's notes on GitHub are taken from its section here.
Write upcoming changes under **Unreleased**; `release.ps1` turns that section into the new version.

## [Unreleased]

## [1.0.6] - 2026-10-23

### Added
- **Export PDF** (*File → Export PDF…*, `Ctrl+E`, or the toolbar button): save the PDF under any name and folder, with its **title, authors, subject and keywords** set. These are the properties Windows Explorer, Acrobat and browsers show. Title and authors are filled in from the document's `\title{}` and `\author{}`, accents included. Choices are remembered per project, and the document is compiled first if it has unsaved or newer changes.

## [1.0.5] - 2026-10-23

### Added
- **Automatic updates.** When QTeX opens, it checks GitHub for a newer release. If there is one, it shows what's new and offers *Update now*, *Later* or *Skip this version*. *Update now* downloads the installer, verifies its SHA-256 checksum, closes QTeX (asking to save unsaved work first), installs the update and reopens QTeX. Portable copies offer to open the download page instead.
- *Help → Check for Updates…*, and *Help → Check for Updates at Startup* to turn the automatic check off.

## [1.0.4] - 2026-10-23

### Added
- **Light and dark themes**: *View → Theme* offers Light, Dark, or System (follow Windows). It switches instantly and is remembered. Syntax colors are tuned for each, and the Windows title bar follows the theme.

## [1.0.3] - 2026-10-23

### Added
- **Search** (`Ctrl+F`): a find bar under the editor highlights every match and shows "3 of 12". `Enter`/`Shift+Enter` or `F3`/`Shift+F3` move between matches, with *Match case* and *Whole words* options. `Esc` closes it.
- **Hide the Problems/Log panel** with `Ctrl+Shift+M` (View menu) or the ✕ on the panel. It stays hidden, even after a failed compile, until you show it again; the status bar then reminds you of the shortcut.
- New **Edit** menu with Find, Find Next/Previous and Toggle Comment.

## [1.0.2] - 2026-10-22

### Added
- **Highlight source** button on the PDF toolbar: point at the PDF and the matching line is highlighted in the editor (switching tabs if it's in another file).
- `Ctrl+click` on the PDF jumps to that line in the editor.
- *Sync PDF to Cursor* (`Ctrl+J`) now outlines the matching text in the PDF for a moment.
- `Shift` + mouse wheel scrolls the PDF sideways when zoomed in; `Ctrl` + mouse wheel zooms.
- **Help → Keyboard Shortcuts** (`F1`): searchable list of every shortcut.
- *Toggle Comment* now shows its `Ctrl+/` shortcut in the View menu.

### Fixed
- Zooming in or out from *Fit width* / *Fit page* now continues from the current size instead of jumping to 100%.
- `Shift+Enter` now starts a real new line (without indentation). Before, it inserted a special line break that made line numbers in the editor drift from the file, so error markers and PDF sync could land on the wrong line.

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
