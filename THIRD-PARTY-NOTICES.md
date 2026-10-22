# Third-party software

QTeX itself is licensed under the GNU General Public License v3 or later (see `LICENSE`).

The Windows builds (installer and portable zip) also include the following software:

## Qt 6 and PySide6 (Qt for Python)

- Copyright © The Qt Company Ltd. and other contributors.
- License: GNU Lesser General Public License v3 (LGPLv3). https://www.gnu.org/licenses/lgpl-3.0.html
- Source code: https://code.qt.io/ (Qt) and https://code.qt.io/cgit/pyside/pyside-setup.git/ (PySide6). Also available from https://download.qt.io/official_releases/.

The Qt and PySide6 libraries are shipped unmodified as separate files in the `_internal` folder. You may replace them with your own compatible builds.

## Python

- Copyright © Python Software Foundation.
- License: Python Software Foundation License. https://docs.python.org/3/license.html

## PyInstaller bootloader

- Copyright © PyInstaller Development Team.
- License: GPL v2 or later with a special exception that permits distributing programs built with it under any license. https://github.com/pyinstaller/pyinstaller/blob/develop/COPYING.txt

QTeX does not include a TeX distribution. It calls the TeX Live or MiKTeX programs already installed on your computer.
