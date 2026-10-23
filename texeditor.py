#!/usr/bin/env python3
"""
QTeX — a small local LaTeX editor for whole projects, with live PDF preview.
Copyright (C) 2026 André Lopes

This program is free software: you can redistribute it and/or modify it under the
terms of the GNU General Public License as published by the Free Software Foundation,
either version 3 of the License, or (at your option) any later version.
This program is distributed in the hope that it will be useful, but WITHOUT ANY
WARRANTY; without even the implied warranty of MERCHANTABILITY or FITNESS FOR A
PARTICULAR PURPOSE. See the GNU General Public License (LICENSE file) for details.

Requires: Python 3.9+, PySide6 (python -m pip install PySide6), TeX Live or MiKTeX.
Run:      python texeditor.py                 (reopens the last project)
          python texeditor.py path/to/folder  (opens a project folder)
          python texeditor.py path/to/file.tex
"""
import hashlib
import os
import re
import shutil
import sys

from PySide6.QtCore import (QBuffer, QByteArray, QDir, QEvent, QFile,
                            QFileSystemWatcher, QIODevice, QPointF, QProcess,
                            QProcessEnvironment, QRect, QRectF,
                            QRegularExpression, QSettings, QSize,
                            QSortFilterProxyModel, Qt, QTimer, QUrl, Signal)
from PySide6.QtGui import (QAction, QActionGroup, QColor, QDesktopServices, QFont, QPalette, QShortcut,
                           QTextDocument,
                           QFontDatabase, QGuiApplication, QKeySequence,
                           QPainter, QPen,
                           QSyntaxHighlighter, QTextCharFormat, QTextCursor,
                           QTextFormat)
from PySide6.QtPdf import QPdfDocument
from PySide6.QtPdfWidgets import QPdfView
from PySide6.QtWidgets import (QAbstractItemView, QApplication, QCheckBox,
                               QComboBox, QDialog, QDialogButtonBox,
                               QFileDialog, QFileSystemModel, QHBoxLayout,
                               QHeaderView, QLineEdit, QStyleFactory, QToolButton,
                               QTreeWidget, QTreeWidgetItem,
                               QInputDialog, QLabel, QListWidget,
                               QListWidgetItem, QMainWindow, QMenu,
                               QMessageBox, QPlainTextEdit, QPushButton,
                               QSplitter, QStackedWidget, QStatusBar,
                               QTabWidget, QTextEdit, QToolBar, QTreeView,
                               QVBoxLayout, QWidget)

APP_NAME = "QTeX"

# Files opened in the editor; anything else opens in the system's default app.
TEXT_EXTS = {".tex", ".bib", ".sty", ".cls", ".bst", ".bbx", ".cbx", ".dtx", ".ins",
             ".txt", ".md", ".cfg", ".def", ".tikz", ".pgf", ".csv", ".dat", ".ltx",
             ".latexmkrc", ".py", ".json", ".yaml", ".yml", ".log"}
# Build by-products hidden from the project tree.
AUX_EXTS = (".aux", ".log", ".out", ".toc", ".fls", ".fdb_latexmk", ".synctex.gz",
            ".synctex", ".bbl", ".blg", ".bcf", ".run.xml", ".nav", ".snm", ".lof",
            ".lot", ".xdv", ".idx", ".ilg", ".ind", ".glo", ".gls", ".glg", ".ist",
            ".vrb", ".synctex(busy)", ".dvi")

NEW_DOC = r"""\documentclass[11pt]{article}
\usepackage[utf8]{inputenc}
\usepackage[T1]{fontenc}
\usepackage{amsmath, amssymb}
\usepackage{graphicx}
\usepackage{hyperref}

\title{Untitled}
\author{}
\date{\today}

\begin{document}
\maketitle

\section{Introduction}
Hello, \LaTeX! Here is an equation:
\begin{equation}
  e^{i\pi} + 1 = 0
\end{equation}

\end{document}
"""


def norm(p):
    """Canonical key for comparing paths (handles / vs \\ and case on Windows)."""
    return os.path.normcase(os.path.normpath(os.path.abspath(p)))


def is_text_file(path):
    name = os.path.basename(path).lower()
    return os.path.splitext(name)[1] in TEXT_EXTS or name in TEXT_EXTS


def read_text(path):
    with open(path, encoding="utf-8", errors="replace", newline="") as f:
        return f.read().replace("\r\n", "\n")


def looks_like_main(path):
    try:
        head = read_text(path)[:20000]
    except OSError:
        return False
    return "\\documentclass" in head and "\\begin{document}" in head


def tex_root_magic(path):
    """Return the main file named by a '% !TEX root = ...' comment, if any."""
    try:
        head = read_text(path)[:3000]
    except OSError:
        return None
    m = re.search(r"^\s*%\s*!\s*TEX\s+root\s*=\s*(.+?)\s*$", head, re.M | re.I)
    if m:
        target = os.path.normpath(os.path.join(os.path.dirname(path), m[1]))
        if os.path.isfile(target):
            return target
    return None


def settings_key(prefix, root):
    return f"{prefix}/{hashlib.md5(norm(root).encode()).hexdigest()}"


# --------------------------------------------------------------------------- #
#  Themes (View → Theme)
# --------------------------------------------------------------------------- #
THEMES = ("system", "light", "dark")
_SYSTEM_LOOK = {}   # style name and palette Qt chose at startup, to restore "System"

SYNTAX_COLORS = {
    #            environments  sectioning  input/include  commands   brackets   math       comments
    "light": dict(env="#a626a4", sect="#b06d00", incl="#d14d00", cmd="#1f62c4", brace="#8a8a8a",
                  math="#1d8a4a", comment="#8a8a8a"),
    "dark":  dict(env="#d19af0", sect="#f0c040", incl="#ff9a52", cmd="#6cb6ff", brace="#8f8f8f",
                  math="#62d38f", comment="#7f8a8f"),
}


def _palette(colors):
    pal = QPalette()
    roles = {
        QPalette.Window: "window", QPalette.WindowText: "text", QPalette.Base: "base",
        QPalette.AlternateBase: "alt", QPalette.Text: "text", QPalette.Button: "button",
        QPalette.ButtonText: "text", QPalette.BrightText: "bright", QPalette.Highlight: "highlight",
        QPalette.HighlightedText: "hl_text", QPalette.ToolTipBase: "tooltip", QPalette.ToolTipText: "text",
        QPalette.PlaceholderText: "placeholder", QPalette.Link: "link", QPalette.Light: "light",
        QPalette.Midlight: "midlight", QPalette.Mid: "mid", QPalette.Dark: "dark", QPalette.Shadow: "shadow",
    }
    for role, key in roles.items():
        pal.setColor(role, QColor(colors[key]))
    for role in (QPalette.WindowText, QPalette.Text, QPalette.ButtonText):
        pal.setColor(QPalette.Disabled, role, QColor(colors["disabled"]))
    pal.setColor(QPalette.Disabled, QPalette.Highlight, QColor(colors["mid"]))
    return pal


LIGHT_PALETTE = dict(window="#f3f3f3", text="#1f1f1f", base="#ffffff", alt="#f2f4f7", button="#f3f3f3",
                     bright="#ffffff", highlight="#2f6fd6", hl_text="#ffffff", tooltip="#ffffdc",
                     placeholder="#8a8a8a", link="#1f62c4", light="#ffffff", midlight="#e6e6e6",
                     mid="#b8b8b8", dark="#a0a0a0", shadow="#6e6e6e", disabled="#a0a0a0")
DARK_PALETTE = dict(window="#2b2d30", text="#e3e3e3", base="#1e1f22", alt="#25272b", button="#34363a",
                    bright="#ffffff", highlight="#3574f0", hl_text="#ffffff", tooltip="#3c3f41",
                    placeholder="#7f8389", link="#6cb6ff", light="#4a4d52", midlight="#3e4146",
                    mid="#2a2c2f", dark="#1b1c1e", shadow="#000000", disabled="#6f737a")


def _dark_checkbox_css():
    tick = resource_path("assets", "check-light.svg").replace("\\", "/")
    return ("QCheckBox::indicator { width: 13px; height: 13px; border: 1px solid #8a8f98; border-radius: 3px;"
            " background: #1e1f22; }"
            "QCheckBox::indicator:hover { border-color: #b4b9c2; }"
            "QCheckBox::indicator:checked { background: #3574f0; border-color: #3574f0;"
            f" image: url({tick}); }}"
            "QCheckBox::indicator:disabled { border-color: #4a4d52; background: #2b2d30; }")


def is_dark():
    return QApplication.palette().color(QPalette.Window).lightness() < 128


def apply_theme(mode):
    """mode: 'system' (follow Windows), 'light' or 'dark'. Safe to call while the app is running."""
    app = QApplication.instance()
    if not _SYSTEM_LOOK:
        _SYSTEM_LOOK["style"] = app.style().name() or "Fusion"
        _SYSTEM_LOOK["palette"] = QPalette(app.palette())
    hints = app.styleHints()
    if mode in ("light", "dark"):
        if app.style().name().lower() != "fusion":
            app.setStyle(QStyleFactory.create("Fusion"))
        app.setPalette(_palette(LIGHT_PALETTE if mode == "light" else DARK_PALETTE))
        # Fusion draws checkbox outlines darker than the window, which vanishes on a dark background
        app.setStyleSheet(_dark_checkbox_css() if mode == "dark" else "")
        try:  # also tells Windows, so the title bar matches
            hints.setColorScheme(Qt.ColorScheme.Light if mode == "light" else Qt.ColorScheme.Dark)
        except AttributeError:
            pass
    else:
        try:
            hints.setColorScheme(Qt.ColorScheme.Unknown)
        except AttributeError:
            pass
        app.setStyleSheet("")
        if app.style().name().lower() != _SYSTEM_LOOK["style"].lower():
            style = QStyleFactory.create(_SYSTEM_LOOK["style"])
            if style is not None:
                app.setStyle(style)
        app.setPalette(_SYSTEM_LOOK["palette"])


# --------------------------------------------------------------------------- #
#  Syntax highlighting
# --------------------------------------------------------------------------- #
class LatexHighlighter(QSyntaxHighlighter):
    def __init__(self, doc):
        super().__init__(doc)
        self.comment_re = QRegularExpression(r"(?<!\\)%.*$")
        self.update_colors(rehighlight=False)

    def update_colors(self, rehighlight=True):
        """Pick the syntax colors for the current (light or dark) theme."""
        c = SYNTAX_COLORS["dark" if is_dark() else "light"]

        def fmt(color, bold=False, italic=False):
            f = QTextCharFormat()
            f.setForeground(QColor(color))
            if bold:
                f.setFontWeight(QFont.Bold)
            if italic:
                f.setFontItalic(True)
            return f

        self.rules = [
            (QRegularExpression(r"\\(begin|end)\{[^}]*\}"), fmt(c["env"], bold=True)),
            (QRegularExpression(r"\\(part|chapter|section|subsection|subsubsection|paragraph)\*?"),
             fmt(c["sect"], bold=True)),
            (QRegularExpression(r"\\(input|include|includegraphics|bibliography|addbibresource)\b"),
             fmt(c["incl"], bold=True)),
            (QRegularExpression(r"\\[A-Za-z@]+\*?|\\."), fmt(c["cmd"])),
            (QRegularExpression(r"[{}\[\]]"), fmt(c["brace"])),
            (QRegularExpression(r"\$[^$\n]*\$|\\\([^\n]*?\\\)"), fmt(c["math"])),
        ]
        self.comment_fmt = fmt(c["comment"], italic=True)
        if rehighlight:
            self.rehighlight()

    def highlightBlock(self, text):
        for regex, f in self.rules:
            it = regex.globalMatch(text)
            while it.hasNext():
                m = it.next()
                self.setFormat(m.capturedStart(), m.capturedLength(), f)
        m = self.comment_re.match(text)
        if m.hasMatch():
            self.setFormat(m.capturedStart(), m.capturedLength(), self.comment_fmt)


# --------------------------------------------------------------------------- #
#  Code editor with line numbers
# --------------------------------------------------------------------------- #
class LineNumberArea(QWidget):
    def __init__(self, editor):
        super().__init__(editor)
        self.editor = editor

    def sizeHint(self):
        return QSize(self.editor.line_number_width(), 0)

    def paintEvent(self, event):
        self.editor.paint_line_numbers(event)


class CodeEditor(QPlainTextEdit):
    def __init__(self, path):
        super().__init__()
        self.path = path
        font = QFontDatabase.systemFont(QFontDatabase.FixedFont)
        font.setPointSize(11)
        self.setFont(font)
        self.setTabStopDistance(self.fontMetrics().horizontalAdvance(" ") * 2)
        self.setLineWrapMode(QPlainTextEdit.WidgetWidth)
        self.error_lines = set()
        self.search_matches = []         # QTextCursors of find-bar matches (highlighted)
        self.sync_line = None            # line highlighted from the PDF (1-based)
        self._sync_timer = QTimer(self, singleShot=True)
        self._sync_timer.timeout.connect(self.clear_sync_line)

        self.number_area = LineNumberArea(self)
        self.blockCountChanged.connect(self._update_margin)
        self.updateRequest.connect(self._update_number_area)
        self.cursorPositionChanged.connect(self._highlight_current_line)
        self._update_margin()
        self._highlight_current_line()
        if os.path.splitext(path)[1].lower() in (".tex", ".sty", ".cls", ".bib", ".ltx", ".tikz", ".dtx"):
            self.highlighter = LatexHighlighter(self.document())

    def line_number_width(self):
        digits = len(str(max(1, self.blockCount())))
        return 14 + self.fontMetrics().horizontalAdvance("9") * digits

    def _update_margin(self, *_):
        self.setViewportMargins(self.line_number_width(), 0, 0, 0)

    def _update_number_area(self, rect, dy):
        if dy:
            self.number_area.scroll(0, dy)
        else:
            self.number_area.update(0, rect.y(), self.number_area.width(), rect.height())
        if rect.contains(self.viewport().rect()):
            self._update_margin()

    def resizeEvent(self, e):
        super().resizeEvent(e)
        cr = self.contentsRect()
        self.number_area.setGeometry(QRect(cr.left(), cr.top(), self.line_number_width(), cr.height()))

    def paint_line_numbers(self, event):
        painter = QPainter(self.number_area)
        pal = self.palette()
        painter.fillRect(event.rect(), pal.alternateBase())
        block = self.firstVisibleBlock()
        num = block.blockNumber()
        top = round(self.blockBoundingGeometry(block).translated(self.contentOffset()).top())
        bottom = top + round(self.blockBoundingRect(block).height())
        current = self.textCursor().blockNumber()
        while block.isValid() and top <= event.rect().bottom():
            if block.isVisible() and bottom >= event.rect().top():
                line = num + 1
                if line in self.error_lines:
                    painter.fillRect(0, top, self.number_area.width(), bottom - top, QColor(224, 27, 36, 70))
                painter.setPen(pal.text().color() if num == current else QColor("#888"))
                painter.drawText(0, top, self.number_area.width() - 6, self.fontMetrics().height(),
                                 Qt.AlignRight, str(line))
            block = block.next()
            top = bottom
            bottom = top + round(self.blockBoundingRect(block).height())
            num += 1

    def _highlight_current_line(self):
        sels = []
        sel = QTextEdit.ExtraSelection()
        c = self.palette().highlight().color()
        c.setAlpha(35)
        sel.format.setBackground(c)
        sel.format.setProperty(QTextFormat.FullWidthSelection, True)
        sel.cursor = self.textCursor()
        sel.cursor.clearSelection()
        sels.append(sel)
        for m in self.search_matches:
            if m.hasSelection():
                hit = QTextEdit.ExtraSelection()
                hit.format.setBackground(QColor(255, 150, 0, 85))
                hit.cursor = m
                sels.append(hit)
        if self.sync_line:
            block = self.document().findBlockByNumber(self.sync_line - 1)
            if block.isValid():
                hl = QTextEdit.ExtraSelection()
                hl.format.setBackground(QColor(255, 196, 0, 110))
                hl.format.setProperty(QTextFormat.FullWidthSelection, True)
                hl.cursor = QTextCursor(block)
                hl.cursor.movePosition(QTextCursor.EndOfBlock, QTextCursor.KeepAnchor)  # cover wrapped lines too
                sels.append(hl)
        self.setExtraSelections(sels)

    def show_sync_line(self, line, flash_ms=0):
        """Highlight a source line (from the PDF) and scroll it into view without moving the cursor."""
        self.sync_line = max(1, line)
        self._sync_timer.stop()
        if flash_ms:
            self._sync_timer.start(flash_ms)
        self._highlight_current_line()
        block = self.document().findBlockByNumber(self.sync_line - 1)
        if not block.isValid():
            return
        geo = self.blockBoundingGeometry(block).translated(self.contentOffset())
        vp = self.viewport().rect()
        if geo.top() >= vp.top() and geo.bottom() <= vp.bottom():
            return  # already visible
        # QPlainTextEdit scrolls in layout lines: count the lines above the block, then centre it.
        lines_above = 0
        b = self.document().firstBlock()
        while b.isValid() and b.blockNumber() < block.blockNumber():
            lines_above += max(1, b.lineCount()) if b.isVisible() else 0
            b = b.next()
        visible_lines = max(1, int(vp.height() / max(1, self.fontMetrics().lineSpacing())))
        self.verticalScrollBar().setValue(max(0, lines_above - visible_lines // 2))

    def clear_sync_line(self):
        if self.sync_line is not None:
            self.sync_line = None
            self._highlight_current_line()

    def set_error_lines(self, lines):
        self.error_lines = set(lines)
        self.number_area.update()

    def goto_line(self, line):
        block = self.document().findBlockByNumber(max(0, line - 1))  # logical line, not wrapped line
        self.setTextCursor(QTextCursor(block))
        self.centerCursor()
        self.setFocus()

    def keyPressEvent(self, e):
        if e.key() in (Qt.Key_Return, Qt.Key_Enter) and not e.modifiers() & Qt.ControlModifier:
            if e.modifiers() & Qt.ShiftModifier:
                # Qt's default Shift+Enter inserts a Unicode line separator (U+2028): the editor counts it
                # as the same line while the saved file gets a real newline, so line numbers drift.
                self.textCursor().insertBlock()
                self.ensureCursorVisible()
                return
            indent = re.match(r"\s*", self.textCursor().block().text()).group(0)
            super().keyPressEvent(e)
            self.insertPlainText(indent)
            return
        if e.key() == Qt.Key_Slash and e.modifiers() & Qt.ControlModifier:
            self.toggle_comment()
            return
        super().keyPressEvent(e)

    def toggle_comment(self):
        cur = self.textCursor()
        start, end = sorted((cur.selectionStart(), cur.selectionEnd()))
        doc = self.document()
        first = doc.findBlock(start).blockNumber()
        last = doc.findBlock(end).blockNumber()
        blocks = [doc.findBlockByNumber(i) for i in range(first, last + 1)]
        all_commented = all(b.text().lstrip().startswith("%") or not b.text().strip() for b in blocks)
        cur.beginEditBlock()
        for b in blocks:
            c = QTextCursor(b)
            text = b.text()
            if all_commented:
                i = text.find("%")
                if i >= 0:
                    c.setPosition(b.position() + i)
                    c.setPosition(b.position() + i + (2 if text[i + 1:i + 2] == " " else 1),
                                  QTextCursor.KeepAnchor)
                    c.removeSelectedText()
            elif text.strip():
                c.insertText("% ")
        cur.endEditBlock()


# --------------------------------------------------------------------------- #
#  Find bar (Ctrl+F)
# --------------------------------------------------------------------------- #
class FindBar(QWidget):
    """Search in the current editor tab: highlights all matches, Enter/Shift+Enter to step through."""
    MAX_HIGHLIGHTS = 5000

    def __init__(self, window):
        super().__init__()
        self.main_window = window
        self.setVisible(False)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(6, 3, 6, 3)
        lay.setSpacing(4)

        self.field = QLineEdit()
        self.field.setPlaceholderText("Find")
        self.field.setClearButtonEnabled(True)
        self.field.setMinimumWidth(220)
        self.field.textChanged.connect(lambda _t: self.search(from_start_of_selection=True))
        self.field.installEventFilter(self)

        def tbtn(text, tip, slot, checkable=False):
            b = QToolButton()
            b.setText(text)
            b.setToolTip(tip)
            b.setCheckable(checkable)
            b.setAutoRaise(True)
            (b.toggled if checkable else b.clicked).connect(slot)
            return b

        self.case_btn = tbtn("Aa", "Match case", lambda _c: self.search(from_start_of_selection=True), True)
        self.word_btn = tbtn("W", "Whole words only", lambda _c: self.search(from_start_of_selection=True), True)
        self.count = QLabel()
        self.count.setMinimumWidth(90)
        prev_btn = tbtn("▲", "Previous match (Shift+Enter, Shift+F3)", self.find_prev)
        next_btn = tbtn("▼", "Next match (Enter, F3)", self.find_next)
        close_btn = tbtn("✕", "Close (Esc)", self.close_bar)

        lay.addWidget(QLabel("Find:"))
        lay.addWidget(self.field, 1)
        lay.addWidget(self.case_btn)
        lay.addWidget(self.word_btn)
        lay.addWidget(self.count)
        lay.addWidget(prev_btn)
        lay.addWidget(next_btn)
        lay.addStretch(0)
        lay.addWidget(close_btn)

        # refresh highlights/count when the text changes (debounced)
        self._refresh = QTimer(self, singleShot=True, interval=250)
        self._refresh.timeout.connect(lambda: self.search(move=False))
        self._watched = None

    # ---- helpers
    def editor(self):
        return self.main_window.current_editor()

    def _flags(self, backward=False):
        f = QTextDocument.FindFlag(0)
        if self.case_btn.isChecked():
            f |= QTextDocument.FindCaseSensitively
        if self.word_btn.isChecked():
            f |= QTextDocument.FindWholeWords
        if backward:
            f |= QTextDocument.FindBackward
        return f

    def _watch(self, ed):
        if self._watched is ed:
            return
        if self._watched is not None:
            try:
                self._watched.textChanged.disconnect(self._refresh.start)
            except (RuntimeError, TypeError):
                pass
        self._watched = ed
        if ed is not None:
            ed.textChanged.connect(self._refresh.start)

    def _all_matches(self, ed, text):
        doc = ed.document()
        out = []
        c = QTextCursor(doc)
        flags = self._flags()
        while len(out) < self.MAX_HIGHLIGHTS:
            c = doc.find(text, c, flags)
            if c.isNull():
                break
            out.append(QTextCursor(c))
        return out

    def _update_count(self, ed):
        n = len(ed.search_matches) if ed else 0
        text = self.field.text()
        if not text:
            self.count.setText("")
            self.field.setStyleSheet("")
            return
        if n == 0:
            self.count.setText("No results")
            self.field.setStyleSheet("QLineEdit { background: #5c2b2e; color: #ffffff; }" if is_dark()
                                     else "QLineEdit { background: #f8d7d7; color: #222222; }")
            return
        self.field.setStyleSheet("")
        cur = ed.textCursor()
        idx = next((i for i, m in enumerate(ed.search_matches)
                    if m.selectionStart() == cur.selectionStart() and m.selectionEnd() == cur.selectionEnd()), None)
        more = "+" if n >= self.MAX_HIGHLIGHTS else ""
        self.count.setText(f"{idx + 1} of {n}{more}" if idx is not None else f"{n}{more} matches")

    # ---- actions
    def open_bar(self):
        ed = self.editor()
        if ed:
            sel = ed.textCursor().selectedText()
            if sel and "\u2029" not in sel and len(sel) < 200:  # use a single-line selection as the search text
                self.field.blockSignals(True)
                self.field.setText(sel)
                self.field.blockSignals(False)
        self.setVisible(True)
        self.field.setFocus()
        self.field.selectAll()
        self.search(move=False)

    def close_bar(self):
        self.setVisible(False)
        for i in range(self.main_window.tabs.count()):
            ed = self.main_window.tabs.widget(i)
            if ed.search_matches:
                ed.search_matches = []
                ed._highlight_current_line()
        self._watch(None)
        ed = self.editor()
        if ed:
            ed.setFocus()

    def tab_changed(self):
        if self.isVisible():
            self.search(move=False)

    def search(self, move=True, from_start_of_selection=False):
        """Re-highlight all matches. With move, select the first match at/after the cursor."""
        ed = self.editor()
        self._watch(ed if self.isVisible() else None)
        if ed is None:
            self.count.setText("")
            return
        if not self.isVisible():  # never leave highlights behind while the bar is closed
            if ed.search_matches:
                ed.search_matches = []
                ed._highlight_current_line()
            return
        text = self.field.text()
        ed.search_matches = self._all_matches(ed, text) if text else []
        if move and text and ed.search_matches:
            cur = ed.textCursor()
            start = cur.selectionStart() if from_start_of_selection else cur.position()
            nxt = next((m for m in ed.search_matches if m.selectionStart() >= start), ed.search_matches[0])
            ed.setTextCursor(QTextCursor(nxt))
            ed.centerCursor() if not self._visible(ed) else None
        ed._highlight_current_line()
        self._update_count(ed)

    def _visible(self, ed):
        r = ed.cursorRect()
        return ed.viewport().rect().contains(r)

    def _step(self, backward):
        ed = self.editor()
        text = self.field.text()
        if not ed or not text:
            if not self.isVisible():
                self.open_bar()
            return
        if not self.isVisible():
            self.setVisible(True)
        doc = ed.document()
        cur = ed.textCursor()
        found = doc.find(text, cur, self._flags(backward))
        if found.isNull():  # wrap around
            c = QTextCursor(doc)
            if backward:
                c.movePosition(QTextCursor.End)
            found = doc.find(text, c, self._flags(backward))
            if not found.isNull():
                self.main_window.status.showMessage("Search wrapped around", 1500)
        if found.isNull():
            self.search(move=False)
            return
        ed.setTextCursor(found)
        if not self._visible(ed):
            ed.centerCursor()
        self.search(move=False)

    def find_next(self):
        self._step(False)

    def find_prev(self):
        self._step(True)

    def eventFilter(self, obj, e):
        if obj is self.field and e.type() == QEvent.KeyPress:
            if e.key() in (Qt.Key_Return, Qt.Key_Enter):
                self.find_prev() if e.modifiers() & Qt.ShiftModifier else self.find_next()
                return True
            if e.key() == Qt.Key_Escape:
                self.close_bar()
                return True
        return super().eventFilter(obj, e)


# --------------------------------------------------------------------------- #
#  Project tree
# --------------------------------------------------------------------------- #
class ProjectModel(QFileSystemModel):
    """File system model that shows the main file in bold."""
    main_key = None

    def data(self, index, role=Qt.DisplayRole):
        if role == Qt.FontRole and index.column() == 0 and self.main_key \
                and norm(self.filePath(index)) == self.main_key:
            f = QFont()
            f.setBold(True)
            return f
        return super().data(index, role)


class HideAuxProxy(QSortFilterProxyModel):
    def filterAcceptsRow(self, row, parent):
        src = self.sourceModel()
        idx = src.index(row, 0, parent)
        if src.isDir(idx):
            return True
        return not src.fileName(idx).lower().endswith(AUX_EXTS)


# --------------------------------------------------------------------------- #
#  PDF preview
# --------------------------------------------------------------------------- #
class PdfOverlay(QWidget):
    """Transparent layer over the PDF that draws SyncTeX highlight boxes."""

    def __init__(self, preview):
        super().__init__(preview.view.viewport())
        self.preview = preview
        self.box = None            # (page, QRectF in PDF points)
        self.setAttribute(Qt.WA_TransparentForMouseEvents)
        self.setAttribute(Qt.WA_NoSystemBackground)
        self._timer = QTimer(self, singleShot=True)
        self._timer.timeout.connect(self.clear)

    def flash(self, page, rect, ms=2500):
        self.box = (page, rect)
        self._timer.start(ms)
        self.raise_()
        self.update()

    def clear(self):
        self.box = None
        self.update()

    def paintEvent(self, _e):
        if not self.box:
            return
        r = self.preview.points_to_viewport(*self.box)
        if r is None:
            return
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.setPen(QPen(QColor(230, 150, 0), 2))
        p.setBrush(QColor(255, 196, 0, 70))
        p.drawRoundedRect(r.adjusted(-3, -3, 3, 3), 3, 3)


class PdfPreview(QWidget):
    # page (0-based), x, y in PDF points from the top-left, jump (True = Ctrl+click, False = hover)
    sourceRequested = Signal(int, float, float, bool)
    hoverLeft = Signal()

    def __init__(self):
        super().__init__()
        self.doc = QPdfDocument(self)
        self.view = QPdfView(self)
        self.view.setDocument(self.doc)
        self.view.setPageMode(QPdfView.PageMode.MultiPage)
        self.view.setZoomMode(QPdfView.ZoomMode.FitToWidth)
        self.view.setPageSpacing(12)
        self._buffer = None

        bar = QToolBar()
        self.page_label = QLabel(" – ")
        for text, slot in (("−", self.zoom_out), ("+", self.zoom_in),
                           ("Fit width", self.fit_width), ("Fit page", self.fit_page)):
            a = QAction(text, self)
            a.triggered.connect(slot)
            bar.addAction(a)
        bar.addSeparator()
        self.track_action = QAction("Highlight source", self)
        self.track_action.setCheckable(True)
        self.track_action.setToolTip("Highlight source: point at the PDF to highlight the matching line "
                                     "in the editor.\nCtrl+click on the PDF jumps to that line (always available).")
        bar.addAction(self.track_action)
        bar.addSeparator()
        bar.addWidget(self.page_label)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)
        lay.addWidget(bar)
        lay.addWidget(self.view)

        self.overlay = PdfOverlay(self)
        vp = self.view.viewport()
        vp.setMouseTracking(True)
        vp.installEventFilter(self)
        self.view.verticalScrollBar().valueChanged.connect(self.overlay.update)
        self.view.horizontalScrollBar().valueChanged.connect(self.overlay.update)

        self._hover_pos = None
        self._hover_timer = QTimer(self, singleShot=True, interval=120)
        self._hover_timer.timeout.connect(self._emit_hover)

        self.view.pageNavigator().currentPageChanged.connect(self._update_label)
        self.doc.pageCountChanged.connect(self._update_label)

    # ---- page geometry (mirrors QPdfView's own layout code, which it doesn't expose)
    def _page_rects(self):
        """List of (QRect in document pixels, QSizeF page size in points) per page."""
        v, doc = self.view, self.doc
        n = doc.pageCount()
        if n <= 0:
            return []
        res = QGuiApplication.primaryScreen().logicalDotsPerInch() / 72.0
        m = v.documentMargins()
        vp = v.viewport().size()
        mode = v.zoomMode()
        sizes = []
        for i in range(n):
            pts = doc.pagePointSize(i)
            w, h = int(pts.width() * res + 0.5), int(pts.height() * res + 0.5)
            if mode == QPdfView.ZoomMode.FitToWidth:
                f = (vp.width() - m.left() - m.right()) / max(1, w)
                w, h = int(w * f + 0.5), int(h * f + 0.5)
            elif mode == QPdfView.ZoomMode.FitInView:
                s = QSize(w, h).scaled(QSize(vp.width() - m.left() - m.right(), vp.height() - v.pageSpacing()),
                                       Qt.KeepAspectRatio)
                w, h = s.width(), s.height()
            else:
                z = v.zoomFactor()
                w, h = int(pts.width() * res * z + 0.5), int(pts.height() * res * z + 0.5)
            sizes.append((w, h, pts))
        total_w = max(w for w, _h, _p in sizes) + m.left() + m.right()
        y = m.top()
        rects = []
        for w, h, pts in sizes:
            x = (max(total_w, vp.width()) - w) // 2
            rects.append((QRect(x, y, w, h), pts))
            y += h + v.pageSpacing()
        return rects

    def viewport_to_points(self, pos):
        """Viewport position -> (page, x_pt, y_pt), or None if not over a page."""
        dx = pos.x() + self.view.horizontalScrollBar().value()
        dy = pos.y() + self.view.verticalScrollBar().value()
        for page, (r, pts) in enumerate(self._page_rects()):
            if r.top() <= dy <= r.bottom() + 1 and r.left() <= dx <= r.right() + 1:
                return (page, (dx - r.left()) * pts.width() / r.width(),
                        (dy - r.top()) * pts.height() / r.height())
        return None

    def points_to_viewport(self, page, rect):
        """QRectF in PDF points on a page -> QRectF in viewport pixels."""
        rects = self._page_rects()
        if not 0 <= page < len(rects):
            return None
        r, pts = rects[page]
        sx, sy = r.width() / pts.width(), r.height() / pts.height()
        ox = r.left() - self.view.horizontalScrollBar().value()
        oy = r.top() - self.view.verticalScrollBar().value()
        return QRectF(ox + rect.x() * sx, oy + rect.y() * sy, rect.width() * sx, rect.height() * sy)

    # ---- mouse handling on the PDF
    def eventFilter(self, obj, e):
        t = e.type()
        if t == QEvent.Wheel:
            mods = e.modifiers()
            if mods & Qt.ControlModifier:                       # Ctrl+wheel: zoom
                d = e.angleDelta().y()
                if d:
                    self.zoom_in() if d > 0 else self.zoom_out()
                return True
            if mods & Qt.ShiftModifier:                          # Shift+wheel: scroll sideways
                hbar = self.view.horizontalScrollBar()
                px = e.pixelDelta()
                if not px.isNull():
                    d = px.y() or px.x()
                else:
                    a = e.angleDelta()
                    d = (a.y() or a.x()) / 120 * QApplication.wheelScrollLines() * 20
                hbar.setValue(int(hbar.value() - d))
                return True
        elif t == QEvent.MouseButtonPress and e.button() == Qt.LeftButton and e.modifiers() & Qt.ControlModifier:
            hit = self.viewport_to_points(e.position().toPoint())
            if hit:
                self.sourceRequested.emit(hit[0], hit[1], hit[2], True)
            return True
        elif t == QEvent.MouseMove and self.track_action.isChecked():
            self._hover_pos = e.position().toPoint()
            self._hover_timer.start()
        elif t == QEvent.Leave:
            self._hover_timer.stop()
            if self.track_action.isChecked():
                self.hoverLeft.emit()
        elif t == QEvent.Resize:
            self.overlay.setGeometry(obj.rect())
        return super().eventFilter(obj, e)

    def _emit_hover(self):
        if self._hover_pos is None or not self.track_action.isChecked():
            return
        hit = self.viewport_to_points(self._hover_pos)
        if hit:
            self.sourceRequested.emit(hit[0], hit[1], hit[2], False)

    def _update_label(self, *_):
        n = self.doc.pageCount()
        p = self.view.pageNavigator().currentPage() + 1 if n else 0
        self.page_label.setText(f"  Page {p} / {n}  ")

    def clear(self):
        self.doc.close()
        self.overlay.clear()
        self._update_label()

    def load(self, path):
        """Load from memory so the file isn't locked while LaTeX rewrites it (matters on Windows)."""
        try:
            with open(path, "rb") as f:
                data = f.read()
        except OSError:
            return False
        vbar, hbar = self.view.verticalScrollBar(), self.view.horizontalScrollBar()
        v, h = vbar.value(), hbar.value()
        buf = QBuffer(self)
        buf.setData(QByteArray(data))
        buf.open(QIODevice.ReadOnly)
        self.doc.close()
        self.doc.load(buf)
        if self._buffer is not None:
            self._buffer.deleteLater()
        self._buffer = buf
        QTimer.singleShot(0, lambda: (vbar.setValue(v), hbar.setValue(h)))
        return True

    def jump_to(self, page, x, y):
        self.view.pageNavigator().jump(page, QPointF(x, max(0.0, y - 40)), self.view.zoomFactor())

    def _effective_zoom(self):
        """The zoom level actually on screen (in Fit modes QPdfView's zoomFactor isn't updated)."""
        rects = self._page_rects()
        if not rects:
            return self.view.zoomFactor()
        r, pts = rects[0]
        res = QGuiApplication.primaryScreen().logicalDotsPerInch() / 72.0
        return r.width() / (pts.width() * res)

    def _set_zoom(self, z):
        self.view.setZoomFactor(min(8.0, max(0.1, z)))
        self.view.setZoomMode(QPdfView.ZoomMode.Custom)
        self.overlay.update()

    def zoom_in(self):
        self._set_zoom(self._effective_zoom() * 1.2)

    def zoom_out(self):
        self._set_zoom(self._effective_zoom() / 1.2)

    def fit_width(self):
        self.view.setZoomMode(QPdfView.ZoomMode.FitToWidth)

    def fit_page(self):
        self.view.setZoomMode(QPdfView.ZoomMode.FitInView)


# --------------------------------------------------------------------------- #
#  LaTeX log parsing
# --------------------------------------------------------------------------- #
ERROR_RE = re.compile(r"^(?P<file>(?:[A-Za-z]:)?[^:\n]*?\.(?:tex|sty|cls|bib|ltx|tikz|def|cfg)):(?P<line>\d+):\s*(?P<msg>.*)$")
WARN_RE = re.compile(r"(?:LaTeX|Package [\w-]+|Class [\w-]+) Warning:\s*(?P<msg>.*?)(?: on input line (?P<line>\d+))?\.?\s*$")
BOX_RE = re.compile(r"^(?P<msg>(?:Over|Under)full \\[hv]box .*?) (?:in paragraph |detected )?at lines? (?P<line>\d+)")
FILE_TOKEN_RE = re.compile(r'\((?:"([^"]+)"|([^\s()"]+))|\)')


def parse_log(text, base_dir):
    """Return a list of (kind, path|None, line|None, message).

    Warnings don't name their file, so the files LaTeX opens/closes are tracked
    through the '(./chapter.tex ... )' parentheses in the log.
    """
    issues = []
    stack = []

    def resolve(p):
        p = p.strip('"')
        full = p if os.path.isabs(p) else os.path.join(base_dir, p)
        return os.path.normpath(full)

    def feed(segment):
        for t in FILE_TOKEN_RE.finditer(segment):
            if t.group(0) == ")":
                if stack:
                    stack.pop()
            else:
                name = t.group(1) or t.group(2)
                stack.append(resolve(name) if os.path.splitext(name)[1] else None)

    def current_tex():
        for p in reversed(stack):
            if p and p.lower().endswith(".tex") and os.path.isfile(p):
                return p
        return None

    lines = text.splitlines()
    for i, ln in enumerate(lines):
        m = ERROR_RE.match(ln)
        if m:
            if not m["msg"].startswith("==> Fatal error"):
                ctx = next((l.strip() for l in lines[i + 1:i + 4] if l.startswith("l.")), "")
                issues.append(("error", resolve(m["file"]), int(m["line"]), f"{m['msg']}  {ctx}".strip()))
            continue
        if ln.startswith("! "):  # error without -file-line-error info
            issues.append(("error", current_tex(), None, ln[2:]))
            continue
        w = WARN_RE.search(ln) or BOX_RE.search(ln)
        if w:
            feed(ln[:w.start()])
            line = w["line"]
            kind = "box" if ln.lstrip().startswith(("Overfull", "Underfull")) else "warning"
            issues.append((kind, current_tex(), int(line) if line else None, w["msg"]))
            feed(ln[w.start():])
            continue
        feed(ln)
    return issues


# --------------------------------------------------------------------------- #
#  Main window
# --------------------------------------------------------------------------- #
class MainWindow(QMainWindow):
    def __init__(self, target=None):
        super().__init__()
        self.settings = QSettings(APP_NAME, APP_NAME)
        self.root = None
        self.main = None
        self.proc = None
        self.recompile_pending = False
        self.error_map = {}          # norm(path) -> set(lines)
        self._saving = set()         # paths we're writing ourselves (ignore watcher)
        self._build = {}
        self._step = None
        self.tree_hidden = self.settings.value("treeHidden", "false") == "true"  # user hid it with Ctrl+B
        self._cite_hashes = {}       # main file -> hash of \citation lines when bibtex last ran
        self._idx_hashes = {}

        # ---- project tree
        self.model = ProjectModel(self)
        self.model.setFilter(QDir.AllDirs | QDir.Files | QDir.NoDotAndDotDot)
        self.proxy = HideAuxProxy(self)
        self.proxy.setSourceModel(self.model)
        self.tree = QTreeView()
        self.tree.setModel(self.proxy)
        for c in (1, 2, 3):
            self.tree.hideColumn(c)
        self.tree.setHeaderHidden(True)
        self.tree.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.tree.setContextMenuPolicy(Qt.CustomContextMenu)
        self.tree.customContextMenuRequested.connect(self._tree_menu)
        self.tree.activated.connect(self._tree_activated)
        self.tree.doubleClicked.connect(self._tree_activated)

        # ---- editor tabs + welcome screen
        self.tabs = QTabWidget()
        self.tabs.setTabsClosable(True)
        self.tabs.setMovable(True)
        self.tabs.setDocumentMode(True)
        self.tabs.tabCloseRequested.connect(self.close_tab)
        self.tabs.currentChanged.connect(lambda _i: self._refresh_ui())
        self.welcome = self._build_welcome()
        self.center = QStackedWidget()
        self.center.addWidget(self.welcome)
        self.center.addWidget(self.tabs)

        self.watcher = QFileSystemWatcher(self)
        self.watcher.fileChanged.connect(self._file_changed_on_disk)

        # ---- preview, problems, log
        self.preview = PdfPreview()
        self.preview.sourceRequested.connect(self.inverse_search)
        self.preview.hoverLeft.connect(self._hover_left)
        self.preview.track_action.setChecked(self.settings.value("trackSource", "false") == "true")
        self.preview.track_action.toggled.connect(self._track_toggled)
        self._inv_proc = None
        self._inv_pending = None
        self._hover_clear_timer = QTimer(self, singleShot=True, interval=1500)
        self._hover_clear_timer.timeout.connect(self._clear_sync_highlights)
        self.log = QPlainTextEdit(readOnly=True)
        self.log.setFont(QFontDatabase.systemFont(QFontDatabase.FixedFont))
        self.issues = QListWidget()
        self.issues.itemActivated.connect(self._goto_issue)
        self.issues.itemClicked.connect(self._goto_issue)
        self.bottom = QTabWidget()
        self.bottom.addTab(self.issues, "Problems")
        self.bottom.addTab(self.log, "Log")
        hide_btn = QToolButton()
        hide_btn.setText("✕")
        hide_btn.setAutoRaise(True)
        hide_btn.setToolTip("Hide the Problems/Log panel (Ctrl+Shift+M)")
        hide_btn.clicked.connect(self.toggle_bottom)
        self.bottom.setCornerWidget(hide_btn, Qt.TopRightCorner)
        self.bottom_hidden = self.settings.value("bottomHidden", "false") == "true"
        self.bottom.setVisible(not self.bottom_hidden)

        self.find_bar = FindBar(self)
        self.tabs.currentChanged.connect(lambda _i: self.find_bar.tab_changed())
        editor_area = QWidget()
        ea = QVBoxLayout(editor_area)
        ea.setContentsMargins(0, 0, 0, 0)
        ea.setSpacing(0)
        ea.addWidget(self.center)
        ea.addWidget(self.find_bar)
        esc = QShortcut(QKeySequence(Qt.Key_Escape), editor_area, context=Qt.WidgetWithChildrenShortcut)
        esc.activated.connect(lambda: self.find_bar.isVisible() and self.find_bar.close_bar())

        mid = QSplitter(Qt.Vertical)
        mid.addWidget(editor_area)
        mid.addWidget(self.bottom)
        mid.setSizes([700, 160])
        mid.setCollapsible(0, False)

        self.split = QSplitter(Qt.Horizontal)
        self.split.addWidget(self.tree)
        self.split.addWidget(mid)
        self.split.addWidget(self.preview)
        self.split.setSizes([220, 600, 600])
        self.split.setCollapsible(1, False)
        self.setCentralWidget(self.split)

        self.status = QStatusBar()
        self.setStatusBar(self.status)
        self.main_label = QLabel()
        self.status.addPermanentWidget(self.main_label)

        self.typing_timer = QTimer(self, singleShot=True, interval=1500)
        self.typing_timer.timeout.connect(self._auto_compile)

        self._build_actions()
        self.resize(1500, 880)
        geo = self.settings.value("geometry")
        if geo:
            self.restoreGeometry(geo)

        if target and os.path.isdir(target):
            self.open_project(target)
        elif target and os.path.isfile(target):
            self.open_single_file(target)
        else:
            last = self.settings.value("lastProject")
            if last and os.path.isdir(last):
                self.open_project(last)
        self._refresh_ui()

    # ------------------------------------------------------------------ UI
    def _build_welcome(self):
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.addStretch()
        title = QLabel(f"<h2>{APP_NAME}</h2><p>Open a LaTeX project folder to get started.</p>")
        title.setAlignment(Qt.AlignCenter)
        lay.addWidget(title)
        for text, slot in (("Open Project Folder…", self.open_folder_dialog),
                           ("New Project…", self.new_project),
                           ("Open File…", self.open_file_dialog)):
            b = QPushButton(text)
            b.setFixedWidth(240)
            b.clicked.connect(slot)
            lay.addWidget(b, alignment=Qt.AlignCenter)
        lay.addStretch()
        return w

    def _build_actions(self):
        tb = QToolBar("Main")
        tb.setMovable(False)
        self.addToolBar(tb)
        m_file = self.menuBar().addMenu("&File")
        m_edit = self.menuBar().addMenu("&Edit")
        m_build = self.menuBar().addMenu("&Build")
        m_view = self.menuBar().addMenu("&View")
        m_help = self.menuBar().addMenu("&Help")

        def act(text, slot, shortcut=None, menu=None, toolbar=False):
            a = QAction(text, self)
            a.triggered.connect(slot)
            if shortcut:
                a.setShortcut(QKeySequence(shortcut))
            if menu is not None:
                menu.addAction(a)
            if toolbar:
                tb.addAction(a)
            return a

        act("Open Folder…", self.open_folder_dialog, "Ctrl+Shift+O", m_file, True)
        act("Open File…", self.open_file_dialog, QKeySequence.Open, m_file)
        act("New Project…", self.new_project, None, m_file)
        act("New File…", self.new_file, QKeySequence.New, m_file, True)
        m_file.addSeparator()
        act("Save", self.save_current, QKeySequence.Save, m_file, True)
        act("Save All", self.save_all, "Ctrl+Alt+S", m_file)
        act("Close Tab", lambda: self.close_tab(self.tabs.currentIndex()), "Ctrl+W", m_file)
        self.recent_menu = m_file.addMenu("Recent Projects")
        self._fill_recent_menu()
        m_file.addSeparator()
        act("Quit", self.close, QKeySequence.Quit, m_file)

        act("Find…", lambda: self.find_bar.open_bar(), QKeySequence.Find, m_edit)
        act("Find Next", lambda: self.find_bar.find_next(), QKeySequence.FindNext, m_edit)
        act("Find Previous", lambda: self.find_bar.find_prev(), QKeySequence.FindPrevious, m_edit)
        m_edit.addSeparator()
        act("Toggle Comment", lambda: self.current_editor() and self.current_editor().toggle_comment(), "Ctrl+/", m_edit)

        tb.addSeparator()
        act("▶ Compile", self.compile, "Ctrl+Return", m_build, True)
        act("Stop", self.stop_compile, None, m_build)
        act("Set Current File as Main", lambda: self.current_editor() and self.set_main(self.current_editor().path),
            None, m_build)
        act("Clean Aux Files", self.clean, None, m_build)
        act("Sync PDF to Cursor", self.forward_search, "Ctrl+J", m_view, True)
        act("Next Tab", lambda: self.tabs.setCurrentIndex((self.tabs.currentIndex() + 1) % max(1, self.tabs.count())),
            "Ctrl+PgDown", m_view)
        act("Previous Tab", lambda: self.tabs.setCurrentIndex((self.tabs.currentIndex() - 1) % max(1, self.tabs.count())),
            "Ctrl+PgUp", m_view)
        act("Show/Hide Project Tree", self.toggle_tree, "Ctrl+B", m_view)
        act("Show/Hide Problems Panel", self.toggle_bottom, "Ctrl+Shift+M", m_view)
        m_view.addSeparator()
        m_theme = m_view.addMenu("Theme")
        group = QActionGroup(self)
        group.setExclusive(True)
        current = self.settings.value("theme", "system")
        for key, label in (("light", "Light"), ("dark", "Dark"), ("system", "System (follow Windows)")):
            a = QAction(label, self, checkable=True)
            a.setChecked(key == current)
            a.triggered.connect(lambda _c=False, k=key: self.set_theme(k))
            group.addAction(a)
            m_theme.addAction(a)
        act("Keyboard Shortcuts", self.show_shortcuts, "F1", m_help)
        m_help.addSeparator()
        act(f"About {APP_NAME}", self.show_about, None, m_help)

        tb.addSeparator()
        tb.addWidget(QLabel(" Engine: "))
        self.engine = QComboBox()
        self.engine.addItems(["pdflatex", "xelatex", "lualatex"])
        tb.addWidget(self.engine)

        self.use_latexmk = QCheckBox("latexmk")
        self.use_latexmk.setToolTip("Build with latexmk instead of QTeX's built-in build.\n"
                                    "Both run bibtex/biber/makeindex and rerun LaTeX as needed;\n"
                                    "latexmk needs Perl (not bundled with MiKTeX).")
        has_mk = shutil.which("latexmk") is not None
        self.use_latexmk.setEnabled(has_mk)
        self.use_latexmk.setChecked(has_mk and self.settings.value("useLatexmk", "false") == "true")
        tb.addWidget(self.use_latexmk)

        self.auto = QCheckBox("Live")
        self.auto.setToolTip("Recompile automatically shortly after you stop typing")
        self.auto.setChecked(self.settings.value("live", "true") == "true")
        tb.addWidget(self.auto)

        self.show_boxes = QCheckBox("Box warnings")
        self.show_boxes.setToolTip("List overfull/underfull box warnings in Problems")
        self.show_boxes.setChecked(self.settings.value("boxes", "false") == "true")
        self.show_boxes.toggled.connect(lambda: self.main and self._parse_log())
        tb.addWidget(self.show_boxes)

    def _shortcut_sections(self):
        """(section, [(action, keys)]) built from the menus, so the list never goes out of date."""
        native = QKeySequence.NativeText
        sections = []
        for menu_action in self.menuBar().actions():
            menu = menu_action.menu()
            if not menu:
                continue
            rows = []
            for a in menu.actions():
                if a.isSeparator() or a.menu() or a.shortcut().isEmpty():
                    continue
                name = a.text().replace("&", "").replace("▶", "").replace("…", "").strip()
                rows.append((name, a.shortcut().toString(native)))
            if rows:
                sections.append((menu_action.text().replace("&", ""), rows))

        def std(key):
            return QKeySequence(key).toString(native)
        sections.append(("Editor", [
            ("Undo / Redo", f"{std(QKeySequence.Undo)} / {std(QKeySequence.Redo)}"),
            ("Cut / Copy / Paste", f"{std(QKeySequence.Cut)} / {std(QKeySequence.Copy)} / {std(QKeySequence.Paste)}"),
            ("Select all", std(QKeySequence.SelectAll)),
            ("New line keeping indentation", "Enter"),
            ("New line without indentation", "Shift+Enter"),
        ]))
        sections.append(("PDF preview", [
            ("Jump to the source line", "Ctrl+Click"),
            ("Highlight the source line under the mouse", "“Highlight source” button"),
            ("Scroll sideways (when zoomed in)", "Shift+Wheel"),
            ("Zoom in / out", "Ctrl+Wheel"),
        ]))
        return sections

    def show_shortcuts(self):
        dlg = getattr(self, "_shortcuts_dlg", None)
        if dlg is None:
            dlg = QDialog(self)
            dlg.setWindowTitle("Keyboard Shortcuts")
            dlg.resize(520, 600)
            lay = QVBoxLayout(dlg)
            search = QLineEdit()
            search.setPlaceholderText("Search shortcuts…")
            search.setClearButtonEnabled(True)
            tree = QTreeWidget()
            tree.setColumnCount(2)
            tree.setHeaderLabels(["Action", "Shortcut"])
            tree.setRootIsDecorated(False)
            tree.setAlternatingRowColors(True)
            tree.setSelectionMode(QAbstractItemView.NoSelection)
            tree.setFocusPolicy(Qt.NoFocus)
            tree.header().setSectionResizeMode(0, QHeaderView.Stretch)
            tree.header().setSectionResizeMode(1, QHeaderView.ResizeToContents)
            tree.header().setStretchLastSection(False)
            bold = QFont()
            bold.setBold(True)
            mono = QFontDatabase.systemFont(QFontDatabase.FixedFont)
            for title, rows in self._shortcut_sections():
                sec = QTreeWidgetItem(tree, [title])
                sec.setFont(0, bold)
                sec.setFirstColumnSpanned(True)
                for name, keys in rows:
                    it = QTreeWidgetItem(sec, [name, keys])
                    it.setFont(1, mono)
            tree.expandAll()

            def apply_filter(text):
                t = text.strip().lower()
                for i in range(tree.topLevelItemCount()):
                    sec = tree.topLevelItem(i)
                    any_shown = False
                    for j in range(sec.childCount()):
                        ch = sec.child(j)
                        show = not t or t in ch.text(0).lower() or t in ch.text(1).lower() or t in sec.text(0).lower()
                        ch.setHidden(not show)
                        any_shown |= show
                    sec.setHidden(not any_shown)
            search.textChanged.connect(apply_filter)
            buttons = QDialogButtonBox(QDialogButtonBox.Close)
            buttons.rejected.connect(dlg.close)
            lay.addWidget(search)
            lay.addWidget(tree)
            lay.addWidget(buttons)
            self._shortcuts_dlg = dlg
            dlg._search = search
        dlg._search.clear()
        dlg.show()
        dlg.raise_()
        dlg.activateWindow()
        dlg._search.setFocus()

    def show_about(self):
        QMessageBox.about(
            self, f"About {APP_NAME}",
            f"<h3>{APP_NAME} {APP_VERSION}</h3>"
            "<p>A LaTeX project editor with live PDF preview.</p>"
            "<p>Copyright © 2026 André Lopes</p>"
            "<p>This program is free software, licensed under the "
            "<a href='https://www.gnu.org/licenses/gpl-3.0.html'>GNU General Public License v3</a> "
            "or later. It comes with ABSOLUTELY NO WARRANTY.</p>"
            "<p>Built with Qt and PySide6 (LGPLv3).</p>")

    def set_theme(self, mode):
        self.settings.setValue("theme", mode)
        apply_theme(mode)
        for i in range(self.tabs.count()):
            ed = self.tabs.widget(i)
            if getattr(ed, "highlighter", None):
                ed.highlighter.update_colors()
            ed._highlight_current_line()
            ed.number_area.update()
        self.find_bar._update_count(self.current_editor())
        self.status.showMessage(f"Theme: {mode.capitalize()}", 2000)

    def toggle_bottom(self):
        self.bottom_hidden = not self.bottom_hidden
        self.settings.setValue("bottomHidden", "true" if self.bottom_hidden else "false")
        self.bottom.setVisible(not self.bottom_hidden)

    def toggle_tree(self):
        self.tree_hidden = not self.tree_hidden
        self.settings.setValue("treeHidden", "true" if self.tree_hidden else "false")
        self._refresh_ui()

    def _fill_recent_menu(self):
        self.recent_menu.clear()
        for p in self._recent():
            a = self.recent_menu.addAction(p)
            a.triggered.connect(lambda _=False, p=p: self.open_project(p))
        if not self.recent_menu.actions():
            self.recent_menu.addAction("(none)").setEnabled(False)

    def _recent(self):
        r = self.settings.value("recent", [])
        r = [r] if isinstance(r, str) else list(r or [])
        return [p for p in r if os.path.isdir(p)]

    def _refresh_ui(self):
        has_tabs = self.tabs.count() > 0
        self.center.setCurrentWidget(self.tabs if has_tabs else self.welcome)
        self.tree.setVisible(self.root is not None and not self.tree_hidden)
        proj = os.path.basename(self.root) if self.root else ""
        ed = self.current_editor()
        cur = ""
        if ed:
            cur = (os.path.relpath(ed.path, self.root) if self.root else os.path.basename(ed.path))
            if ed.document().isModified():
                cur = "• " + cur
        self.setWindowTitle(" — ".join(x for x in (cur, proj, APP_NAME) if x))
        if self.main:
            rel = os.path.relpath(self.main, self.root) if self.root else os.path.basename(self.main)
            self.main_label.setText(f"Main file: {rel}  ")
        else:
            self.main_label.setText("No main file — right-click a .tex file → Set as Main  " if self.root else "")

    # ------------------------------------------------------------------ project
    def open_folder_dialog(self):
        start = self.root or self.settings.value("lastdir", os.path.expanduser("~"))
        d = QFileDialog.getExistingDirectory(self, "Open Project Folder", start)
        if d:
            self.open_project(d)

    def open_file_dialog(self):
        start = self.root or self.settings.value("lastdir", os.path.expanduser("~"))
        p, _ = QFileDialog.getOpenFileName(self, "Open File", start,
                                           "TeX files (*.tex *.bib *.sty *.cls);;All files (*)")
        if p:
            if self.root and norm(p).startswith(norm(self.root) + os.sep):
                self.open_in_editor(p)
            else:
                self.open_single_file(p)

    def new_project(self):
        d = QFileDialog.getExistingDirectory(self, "Choose an (empty) folder for the new project",
                                             self.settings.value("lastdir", os.path.expanduser("~")))
        if not d:
            return
        main = os.path.join(d, "main.tex")
        if not os.path.exists(main):
            with open(main, "w", encoding="utf-8") as f:
                f.write(NEW_DOC)
        self.open_project(d, main)

    def open_single_file(self, path):
        """Open a file, treating its folder (or its '% !TEX root' main file's folder) as the project."""
        path = os.path.abspath(path)
        main = tex_root_magic(path)
        if main:
            root = os.path.dirname(main)
        else:
            root = os.path.dirname(path)
            main = path if looks_like_main(path) else None
        self.open_project(root, main, open_files=[path])

    def open_project(self, root, main=None, open_files=None):
        root = os.path.abspath(root)
        if self.root and norm(root) != norm(self.root):
            if not self._maybe_save_all():
                return
            self._save_session()
            while self.tabs.count():
                self._remove_tab(0)
            self.preview.clear()
            self.issues.clear()
            self.log.clear()
            self.error_map.clear()

        self.root = root
        self.settings.setValue("lastProject", root)
        self.settings.setValue("lastdir", os.path.dirname(root))
        recent = [root] + [p for p in self._recent() if norm(p) != norm(root)]
        self.settings.setValue("recent", recent[:10])
        self._fill_recent_menu()

        src_root = self.model.setRootPath(root)
        self.tree.setRootIndex(self.proxy.mapFromSource(src_root))

        engine = self.settings.value(settings_key("engine", root))
        if engine:
            self.engine.setCurrentText(engine)

        if not main:
            saved = self.settings.value(settings_key("main", root))
            main = saved if saved and os.path.isfile(saved) else self._detect_main(root)
        self.set_main(main, compile_if_needed=False)

        files = open_files
        if files is None:
            saved = self.settings.value(settings_key("tabs", root), [])
            files = [saved] if isinstance(saved, str) else list(saved or [])
            files = [f for f in files if os.path.isfile(f)]
            if not files and self.main:
                files = [self.main]
        for f in files:
            self.open_in_editor(f)

        pdf = self._pdf_path()
        if pdf and os.path.exists(pdf):
            self.preview.load(pdf)
        elif self.main:
            QTimer.singleShot(0, self.compile)
        self._refresh_ui()

    def _detect_main(self, root):
        cand = os.path.join(root, "main.tex")
        if os.path.isfile(cand) and looks_like_main(cand):
            return cand
        found = []
        for dirpath, dirnames, filenames in os.walk(root):
            dirnames[:] = [d for d in dirnames if not d.startswith(".")]
            depth = os.path.relpath(dirpath, root).count(os.sep) + (dirpath != root)
            if depth > 2:
                dirnames[:] = []
                continue
            for fn in filenames:
                if fn.lower().endswith(".tex"):
                    p = os.path.join(dirpath, fn)
                    if looks_like_main(p):
                        found.append((depth, fn.lower() not in ("main.tex", "thesis.tex", "paper.tex"), p))
        return sorted(found)[0][2] if found else None

    def set_main(self, path, compile_if_needed=True):
        self.main = os.path.abspath(path) if path else None
        self.model.main_key = norm(self.main) if self.main else None
        self.tree.viewport().update()
        if self.root and self.main:
            self.settings.setValue(settings_key("main", self.root), self.main)
        self._refresh_ui()
        if compile_if_needed and self.main:
            pdf = self._pdf_path()
            if pdf and os.path.exists(pdf):
                self.preview.load(pdf)
            else:
                self.compile()

    def _save_session(self):
        if not self.root:
            return
        tabs = [self.tabs.widget(i).path for i in range(self.tabs.count())]
        self.settings.setValue(settings_key("tabs", self.root), tabs)
        self.settings.setValue(settings_key("engine", self.root), self.engine.currentText())

    # ------------------------------------------------------------------ tree actions
    def _tree_path(self, proxy_index):
        return self.model.filePath(self.proxy.mapToSource(proxy_index))

    def _tree_activated(self, index):
        path = self._tree_path(index)
        if os.path.isdir(path):
            return
        if is_text_file(path):
            self.open_in_editor(path)
        elif path.lower().endswith(".pdf") and self.main and norm(path) == norm(self._pdf_path()):
            self.preview.load(path)
        else:
            QDesktopServices.openUrl(QUrl.fromLocalFile(path))

    def _tree_menu(self, pos):
        index = self.tree.indexAt(pos)
        path = self._tree_path(index) if index.isValid() else self.root
        if not path:
            return
        is_dir = os.path.isdir(path)
        folder = path if is_dir else os.path.dirname(path)
        menu = QMenu(self)
        if not is_dir:
            menu.addAction("Open", lambda: self._tree_activated(index))
            if path.lower().endswith(".tex"):
                menu.addAction("Set as Main File", lambda: self.set_main(path))
            menu.addSeparator()
        menu.addAction("New File…", lambda: self.new_file(folder))
        menu.addAction("New Folder…", lambda: self.new_folder(folder))
        if index.isValid():
            menu.addAction("Rename…", lambda: self.rename_path(path))
            menu.addAction("Delete", lambda: self.delete_path(path))
            menu.addSeparator()
            rel = os.path.relpath(path, os.path.dirname(self.main) if self.main else self.root).replace(os.sep, "/")
            menu.addAction("Copy Relative Path", lambda: QApplication.clipboard().setText(rel))
        menu.addAction("Show in File Manager", lambda: QDesktopServices.openUrl(QUrl.fromLocalFile(folder)))
        menu.exec(self.tree.viewport().mapToGlobal(pos))

    def new_file(self, folder=None):
        if not self.root:
            p, _ = QFileDialog.getSaveFileName(self, "New File", self.settings.value("lastdir", os.path.expanduser("~")),
                                               "TeX files (*.tex);;All files (*)")
            if not p:
                return
            if not os.path.splitext(p)[1]:
                p += ".tex"
            with open(p, "w", encoding="utf-8") as f:
                f.write(NEW_DOC)
            self.open_single_file(p)
            return
        folder = folder if isinstance(folder, str) else self.root
        base = os.path.relpath(folder, self.root)
        default = "" if base == "." else base.replace(os.sep, "/") + "/"
        name, ok = QInputDialog.getText(self, "New File", "File name (relative to the project, e.g. chapters/intro.tex):",
                                        text=default + "untitled.tex")
        if not ok or not name.strip():
            return
        p = os.path.normpath(os.path.join(self.root, name.strip()))
        if not os.path.splitext(p)[1]:
            p += ".tex"
        if os.path.exists(p):
            QMessageBox.warning(self, APP_NAME, "A file with that name already exists.")
            return
        os.makedirs(os.path.dirname(p), exist_ok=True)
        content = ""
        if p.lower().endswith(".tex") and self.main:
            rel_main = os.path.relpath(self.main, os.path.dirname(p)).replace(os.sep, "/")
            content = f"% !TEX root = {rel_main}\n\n"
        with open(p, "w", encoding="utf-8") as f:
            f.write(content)
        self.open_in_editor(p)
        if self.main and p.lower().endswith(".tex"):
            rel = os.path.relpath(os.path.splitext(p)[0], os.path.dirname(self.main)).replace(os.sep, "/")
            self.status.showMessage(f"Created. Include it in the main file with \\input{{{rel}}}", 8000)

    def new_folder(self, folder):
        name, ok = QInputDialog.getText(self, "New Folder", "Folder name:")
        if ok and name.strip():
            os.makedirs(os.path.join(folder, name.strip()), exist_ok=True)

    def rename_path(self, path):
        new, ok = QInputDialog.getText(self, "Rename", "New name:", text=os.path.basename(path))
        if not ok or not new.strip() or new == os.path.basename(path):
            return
        dest = os.path.join(os.path.dirname(path), new.strip())
        if os.path.exists(dest):
            QMessageBox.warning(self, APP_NAME, "Something with that name already exists.")
            return
        os.rename(path, dest)
        # update open editors and main file that lived at/under the old path
        old_key = norm(path)
        for i in range(self.tabs.count()):
            ed = self.tabs.widget(i)
            k = norm(ed.path)
            if k == old_key or k.startswith(old_key + os.sep):
                self.watcher.removePath(ed.path)
                ed.path = os.path.join(dest, os.path.relpath(ed.path, path)) if k != old_key else dest
                self.watcher.addPath(ed.path)
                self._update_tab(ed)
        if self.main and (norm(self.main) == old_key or norm(self.main).startswith(old_key + os.sep)):
            self.set_main(os.path.join(dest, os.path.relpath(self.main, path)) if norm(self.main) != old_key else dest,
                          compile_if_needed=False)
        self._refresh_ui()

    def delete_path(self, path):
        what = "folder" if os.path.isdir(path) else "file"
        r = QMessageBox.question(self, APP_NAME, f"Move the {what} '{os.path.basename(path)}' to the trash?")
        if r != QMessageBox.Yes:
            return
        key = norm(path)
        for i in reversed(range(self.tabs.count())):
            k = norm(self.tabs.widget(i).path)
            if k == key or k.startswith(key + os.sep):
                self._remove_tab(i)
        if not QFile.moveToTrash(path):
            QMessageBox.warning(self, APP_NAME, "Couldn't move it to the trash.")
            return
        if self.main and (norm(self.main) == key or norm(self.main).startswith(key + os.sep)):
            self.set_main(None, compile_if_needed=False)
        self._refresh_ui()

    # ------------------------------------------------------------------ tabs
    def current_editor(self):
        return self.tabs.currentWidget()

    def find_editor(self, path):
        key = norm(path)
        for i in range(self.tabs.count()):
            if norm(self.tabs.widget(i).path) == key:
                return self.tabs.widget(i)
        return None

    def open_in_editor(self, path, line=None):
        path = os.path.abspath(path)
        ed = self.find_editor(path)
        if ed is None:
            if not os.path.isfile(path):
                return None
            ed = CodeEditor(path)
            ed.setPlainText(read_text(path))
            ed.document().setModified(False)
            ed.set_error_lines(self.error_map.get(norm(path), ()))
            ed.document().modificationChanged.connect(lambda _m, e=ed: self._update_tab(e))
            ed.textChanged.connect(self._on_text_changed)
            self.tabs.addTab(ed, os.path.basename(path))
            self.watcher.addPath(path)
            self._update_tab(ed)
        self.tabs.setCurrentWidget(ed)
        if line:
            ed.goto_line(line)
        self._refresh_ui()
        return ed

    def _update_tab(self, ed):
        i = self.tabs.indexOf(ed)
        if i < 0:
            return
        name = os.path.basename(ed.path)
        self.tabs.setTabText(i, ("• " if ed.document().isModified() else "") + name)
        self.tabs.setTabToolTip(i, ed.path)
        self._refresh_ui()

    def close_tab(self, i):
        if i < 0:
            return
        ed = self.tabs.widget(i)
        if ed.document().isModified():
            r = QMessageBox.question(self, APP_NAME, f"Save changes to {os.path.basename(ed.path)}?",
                                     QMessageBox.Save | QMessageBox.Discard | QMessageBox.Cancel)
            if r == QMessageBox.Cancel:
                return
            if r == QMessageBox.Save:
                self._save_editor(ed)
        self._remove_tab(i)
        self._refresh_ui()

    def _remove_tab(self, i):
        ed = self.tabs.widget(i)
        self.watcher.removePath(ed.path)
        self.tabs.removeTab(i)
        ed.deleteLater()

    def _file_changed_on_disk(self, path):
        ed = self.find_editor(path)
        if ed is None:
            return
        if not os.path.exists(path):
            return
        # editors often save by replacing the file, which drops the watch
        if path not in self.watcher.files():
            self.watcher.addPath(path)
        if norm(path) in self._saving or ed.document().isModified():
            return
        text = read_text(path)
        if text != ed.toPlainText():
            pos = ed.textCursor().position()
            scroll = ed.verticalScrollBar().value()
            ed.blockSignals(True)
            ed.setPlainText(text)
            ed.blockSignals(False)
            ed.document().setModified(False)
            c = ed.textCursor()
            c.setPosition(min(pos, len(text)))
            ed.setTextCursor(c)
            ed.verticalScrollBar().setValue(scroll)
            self.status.showMessage(f"Reloaded {os.path.basename(path)} (changed on disk)", 3000)

    # ------------------------------------------------------------------ saving
    def _save_editor(self, ed):
        key = norm(ed.path)
        self._saving.add(key)
        try:
            with open(ed.path, "w", encoding="utf-8", newline="") as f:
                f.write(ed.toPlainText())
        finally:
            QTimer.singleShot(500, lambda: self._saving.discard(key))
        ed.document().setModified(False)

    def save_current(self):
        ed = self.current_editor()
        if ed:
            self._save_editor(ed)
            self.status.showMessage("Saved", 2000)

    def save_all(self):
        n = 0
        for i in range(self.tabs.count()):
            ed = self.tabs.widget(i)
            if ed.document().isModified():
                self._save_editor(ed)
                n += 1
        return n

    def _maybe_save_all(self):
        dirty = [self.tabs.widget(i) for i in range(self.tabs.count()) if self.tabs.widget(i).document().isModified()]
        if not dirty:
            return True
        names = "\n".join(os.path.basename(e.path) for e in dirty)
        r = QMessageBox.question(self, APP_NAME, f"Save changes to these files?\n\n{names}",
                                 QMessageBox.Save | QMessageBox.Discard | QMessageBox.Cancel)
        if r == QMessageBox.Save:
            self.save_all()
            return True
        return r == QMessageBox.Discard

    # ------------------------------------------------------------------ compile
    def _pdf_path(self):
        return os.path.splitext(self.main)[0] + ".pdf" if self.main else None

    def _on_text_changed(self):
        if self.auto.isChecked() and self.main:
            self.typing_timer.start()

    def _auto_compile(self):
        if self.main and self.auto.isChecked():
            self.compile()

    # The build runs as a chain of steps. With latexmk ticked it's a single latexmk
    # call; otherwise QTeX does latexmk's job itself (no Perl needed):
    #   engine → (bibtex|biber) → (makeindex) → engine again while the .aux/.toc
    #   files keep changing or LaTeX asks for a rerun, up to MAX_RUNS runs.
    MAX_RUNS = 5
    RERUN_RE = re.compile(r"Rerun to get|Label\(s\) may have changed|Please rerun LaTeX|"
                          r"\(rerunfilecheck\).*Rerun|Rerun LaTeX|Table widths have changed")

    def _engine_args(self):
        name = os.path.basename(self.main)
        return ["-interaction=nonstopmode", "-synctex=1", "-file-line-error", "-halt-on-error", name]

    def compile(self):
        if not self.main:
            ed = self.current_editor()
            if ed and ed.path.lower().endswith(".tex") and looks_like_main(ed.path):
                self.set_main(ed.path, compile_if_needed=False)
            else:
                QMessageBox.information(self, APP_NAME, "This project has no main file yet.\n\n"
                                        "Right-click the main .tex file in the project tree and choose "
                                        "“Set as Main File”.")
                return
        self.save_all()

        if self.proc and self.proc.state() != QProcess.NotRunning:
            self.recompile_pending = True
            return

        eng = self.engine.currentText()
        if not shutil.which(eng):
            QMessageBox.warning(self, APP_NAME, f"'{eng}' was not found on PATH. Is your TeX distribution "
                                "(TeX Live or MiKTeX) installed and on PATH?")
            return

        self.log.clear()
        self._build = {"runs": 0, "bib_done": False, "index_done": False, "notes": []}
        if self.use_latexmk.isChecked() and shutil.which("latexmk"):
            flag = {"pdflatex": "-pdf", "xelatex": "-xelatex", "lualatex": "-lualatex"}[eng]
            self.status.showMessage(f"Compiling {os.path.basename(self.main)} with latexmk…")
            self._run_step("latexmk", "latexmk", [flag, *self._engine_args()])
        else:
            self._run_engine()

    def _run_engine(self):
        self._build["runs"] += 1
        self._build["snapshot"] = self._aux_snapshot()
        eng = self.engine.currentText()
        n = self._build["runs"]
        self.status.showMessage(f"Compiling {os.path.basename(self.main)} with {eng}" + (f" (run {n})…" if n > 1 else "…"))
        self._run_step("engine", eng, self._engine_args())

    def _run_step(self, kind, prog, args):
        self._step = kind
        if self.log.toPlainText():
            self.log.appendPlainText("")
        self.log.appendPlainText(f"$ {prog} {' '.join(args)}")
        self.log.moveCursor(QTextCursor.End)
        self.log.insertPlainText("\n")
        self.proc = QProcess(self)
        env = QProcessEnvironment.systemEnvironment()
        env.insert("max_print_line", "10000")  # stop TeX wrapping log lines, so file names parse cleanly
        self.proc.setProcessEnvironment(env)
        self.proc.setWorkingDirectory(os.path.dirname(self.main))
        self.proc.setProcessChannelMode(QProcess.MergedChannels)
        self.proc.readyReadStandardOutput.connect(self._read_output)
        self.proc.finished.connect(self._step_done)
        self.proc.errorOccurred.connect(self._step_error)
        self.proc.start(prog, args)

    def _step_error(self, err):
        if err == QProcess.FailedToStart:
            self.log.appendPlainText(f"Could not start the program for step '{self._step}'.")
            self._finish(-1)

    def _read_output(self):
        data = bytes(self.proc.readAllStandardOutput()).decode("utf-8", errors="replace")
        self.log.moveCursor(QTextCursor.End)
        self.log.insertPlainText(data)
        self.log.moveCursor(QTextCursor.End)

    def _base(self):
        return os.path.splitext(self.main)[0]

    def _aux_snapshot(self):
        snap = {}
        for ext in (".aux", ".toc", ".lof", ".lot", ".out", ".nav", ".snm"):
            try:
                with open(self._base() + ext, "rb") as f:
                    snap[ext] = hashlib.md5(f.read()).hexdigest()
            except OSError:
                snap[ext] = None
        return snap

    def _project_bibs_newer_than(self, path):
        try:
            ref = os.path.getmtime(path)
        except OSError:
            return True
        for dirpath, dirnames, files in os.walk(os.path.dirname(self.main)):
            dirnames[:] = [d for d in dirnames if not d.startswith(".")]
            for fn in files:
                if fn.lower().endswith(".bib") and os.path.getmtime(os.path.join(dirpath, fn)) > ref:
                    return True
        return False

    def _bib_tool_needed(self, log):
        """Return 'biber', 'bibtex' or None."""
        base = self._base()
        bbl = base + ".bbl"
        if os.path.exists(base + ".bcf"):  # biblatex with biber backend
            if not os.path.exists(bbl) or re.search(r"Please \(?re\)?run Biber", log) \
                    or self._project_bibs_newer_than(bbl):
                return "biber"
            return None
        try:
            aux = read_text(base + ".aux")
        except OSError:
            return None
        if "\\bibdata" not in aux:
            return None
        cites = hashlib.md5("\n".join(l for l in aux.splitlines()
                                      if l.startswith(("\\citation", "\\bibdata", "\\bibstyle"))).encode()).hexdigest()
        key = norm(self.main)
        if not os.path.exists(bbl) or self._project_bibs_newer_than(bbl) or self._cite_hashes.get(key) != cites:
            self._cite_hashes[key] = cites
            return "bibtex"
        return None

    def _index_needed(self):
        idx = self._base() + ".idx"
        if not os.path.exists(idx):
            return False
        with open(idx, "rb") as f:
            h = hashlib.md5(f.read()).hexdigest()
        key = norm(self.main)
        if self._idx_hashes.get(key) == h and os.path.exists(self._base() + ".ind"):
            return False
        self._idx_hashes[key] = h
        return True

    def _step_done(self, code, _status=None):
        step = self._step
        name = os.path.basename(self._base())

        if step == "latexmk":
            out = self.log.toPlainText()
            if code != 0 and re.search(r"script engine 'perl'|perl.*not (found|recognized)", out, re.I):
                # MiKTeX's latexmk needs Perl; fall back to the built-in pipeline.
                self.use_latexmk.setChecked(False)
                self.log.appendPlainText("\nlatexmk needs Perl, which isn't installed. "
                                         "Switching to QTeX's built-in build (latexmk box unticked).")
                self._build["runs"] = 0
                self._run_engine()
                return
            self._finish(code)
            return

        if step == "engine":
            if code != 0:
                self._finish(code)
                return
            try:
                log = read_text(self._base() + ".log")
            except OSError:
                log = ""
            if not self._build["bib_done"]:
                tool = self._bib_tool_needed(log)
                if tool:
                    self._build["bib_done"] = True
                    if shutil.which(tool):
                        self.status.showMessage(f"Running {tool}…")
                        self._run_step("bib", tool, [name])
                        return
                    self._build["notes"].append(f"{tool} is needed for the bibliography but wasn't found on PATH.")
            if not self._build["index_done"] and self._index_needed():
                self._build["index_done"] = True
                if shutil.which("makeindex"):
                    self.status.showMessage("Running makeindex…")
                    self._run_step("index", "makeindex", [name])
                    return
            changed = self._aux_snapshot() != self._build["snapshot"]
            if (changed or self.RERUN_RE.search(log)) and self._build["runs"] < self.MAX_RUNS:
                self._run_engine()
                return
            self._finish(0)
            return

        # bib / index step finished — a non-zero exit is reported but we still rerun LaTeX
        if code != 0:
            self._build["notes"].append(f"{'Bibliography' if step == 'bib' else 'Index'} tool exited with code {code}; "
                                        "see the Log tab.")
        self._run_engine()

    def _finish(self, code):
        n_err = self._parse_log()
        for note in self._build.get("notes", []):
            item = QListWidgetItem(f"⚠  {note}")
            item.setForeground(QColor("#c88800"))
            self.issues.insertItem(0, item)
        if code == 0:
            runs = self._build.get("runs", 0)
            self.status.showMessage("Compiled successfully" + (f" ({runs} runs)" if runs > 1 else ""), 3000)
        else:
            msg = f"Compilation failed — {n_err} error(s)" if n_err else f"Compilation failed (exit {code})"
            if self.bottom_hidden:
                msg += "  ·  Ctrl+Shift+M shows the Problems panel"
            self.status.showMessage(msg)
            self.bottom.setCurrentWidget(self.issues if self.issues.count() else self.log)
        pdf = self._pdf_path()
        if pdf and os.path.exists(pdf):
            self.preview.load(pdf)
        if self.recompile_pending:
            self.recompile_pending = False
            QTimer.singleShot(0, self.compile)

    def stop_compile(self):
        if self.proc and self.proc.state() != QProcess.NotRunning:
            self.proc.finished.disconnect()
            self.proc.kill()
            self.proc.waitForFinished(2000)
            self.recompile_pending = False
            self.status.showMessage("Compilation stopped", 3000)

    def _parse_log(self):
        self.issues.clear()
        text = self.log.toPlainText()
        logf = os.path.splitext(self.main)[0] + ".log"
        if os.path.exists(logf):
            text = read_text(logf)
        base = os.path.dirname(self.main)
        self.error_map = {}
        n_err = 0
        seen = set()
        colors = {"error": "#e01b24", "warning": "#c88800", "box": "#888888"}
        icons = {"error": "✖", "warning": "⚠", "box": "▭"}
        for kind, path, line, msg in parse_log(text, base):
            if kind == "box" and not self.show_boxes.isChecked():
                continue
            if (kind, path, line, msg) in seen:
                continue
            seen.add((kind, path, line, msg))
            if kind == "error":
                n_err += 1
                if path and line:
                    self.error_map.setdefault(norm(path), set()).add(line)
            where = ""
            if path:
                try:
                    where = os.path.relpath(path, self.root or base)
                except ValueError:  # different drive on Windows
                    where = path
                if where.startswith(".."):
                    where = os.path.basename(path)
                where += f":{line}" if line else ""
            item = QListWidgetItem(f"{icons[kind]}  {where}  {msg}" if where else f"{icons[kind]}  {msg}")
            item.setForeground(QColor(colors[kind]))
            item.setToolTip(msg)
            item.setData(Qt.UserRole, (path, line))
            self.issues.addItem(item)
        for i in range(self.tabs.count()):
            ed = self.tabs.widget(i)
            ed.set_error_lines(self.error_map.get(norm(ed.path), ()))
        n = self.issues.count()
        self.bottom.setTabText(0, f"Problems ({n})" if n else "Problems")
        return n_err

    def _goto_issue(self, item):
        path, line = item.data(Qt.UserRole) or (None, None)
        if path and os.path.isfile(path):
            self.open_in_editor(path, line)

    def clean(self):
        if not self.main:
            return
        base = os.path.splitext(self.main)[0]
        removed = 0
        for ext in AUX_EXTS:
            try:
                os.remove(base + ext)
                removed += 1
            except (FileNotFoundError, IsADirectoryError):
                pass
        # \include'd chapters leave their own .aux files
        for dirpath, _dirs, files in os.walk(os.path.dirname(self.main)):
            for fn in files:
                if fn.endswith(".aux"):
                    try:
                        os.remove(os.path.join(dirpath, fn))
                        removed += 1
                    except OSError:
                        pass
        self.status.showMessage(f"Removed {removed} auxiliary files", 3000)

    # ------------------------------------------------------------------ SyncTeX
    def forward_search(self):
        ed = self.current_editor()
        if not ed or not self.main or not shutil.which("synctex"):
            self.status.showMessage("SyncTeX unavailable (compile the project first)", 3000)
            return
        line = ed.textCursor().blockNumber() + 1
        col = ed.textCursor().positionInBlock() + 1
        pdf = self._pdf_path()
        main_dir = os.path.dirname(self.main)
        rel = os.path.relpath(ed.path, main_dir)
        # SyncTeX stores names as TeX saw them ("./chapters/a.tex"); try a few spellings.
        for name in ("./" + rel.replace(os.sep, "/"), rel, ed.path):
            p = QProcess(self)
            p.setWorkingDirectory(main_dir)
            p.start("synctex", ["view", "-i", f"{line}:{col}:{name}", "-o", pdf])
            if not p.waitForFinished(3000):
                continue
            out = bytes(p.readAllStandardOutput()).decode(errors="replace")
            page = re.search(r"^Page:(\d+)", out, re.M)
            x = re.search(r"^x:([\d.]+)", out, re.M)
            y = re.search(r"^y:([\d.]+)", out, re.M)
            if page and y:
                pg = int(page[1]) - 1
                self.preview.jump_to(pg, float(x[1]) if x else 0.0, float(y[1]))
                box = [re.search(rf"^{k}:(-?[\d.]+)", out, re.M) for k in ("h", "v", "W", "H")]
                if all(box):
                    h, v, bw, bh = (float(b[1]) for b in box)
                    if bw > 0 and bh > 0:
                        # (h, v) is the left end of the baseline; the box extends up by H
                        QTimer.singleShot(50, lambda: self.preview.overlay.flash(pg, QRectF(h, v - bh, bw, bh)))
                return
        self.status.showMessage("No SyncTeX match for this line (is this file part of the main document?)", 4000)

    def _track_toggled(self, on):
        self.settings.setValue("trackSource", "true" if on else "false")
        if not on:
            self._clear_sync_highlights()

    def _hover_left(self):
        self._inv_pending = None
        self._hover_clear_timer.start()

    def _clear_sync_highlights(self):
        for i in range(self.tabs.count()):
            self.tabs.widget(i).clear_sync_line()

    def inverse_search(self, page, x, y, jump):
        """PDF position -> source line (SyncTeX). Runs in the background; the latest request wins."""
        if not self.main or not shutil.which("synctex"):
            if jump:
                self.status.showMessage("SyncTeX unavailable (compile the project first)", 3000)
            return
        self._hover_clear_timer.stop()
        req = (page, x, y, jump)
        if self._inv_proc and self._inv_proc.state() != QProcess.NotRunning:
            self._inv_pending = req
            return
        pdf = self._pdf_path()
        p = QProcess(self)
        p.setWorkingDirectory(os.path.dirname(self.main))
        p.finished.connect(lambda *_a, p=p, req=req: self._inverse_done(p, req))
        self._inv_proc = p
        p.start("synctex", ["edit", "-o", f"{page + 1}:{x:.2f}:{y:.2f}:{pdf}"])

    def _inverse_done(self, p, req):
        out = bytes(p.readAllStandardOutput()).decode(errors="replace")
        if self._inv_proc is p:
            self._inv_proc = None
        p.deleteLater()
        pending, self._inv_pending = self._inv_pending, None
        if pending:  # the mouse moved on while synctex ran; answer the newest position instead
            self.inverse_search(*pending)
            return
        _page, _x, _y, jump = req
        inp = re.search(r"^Input:(.+)$", out, re.M)
        line = re.search(r"^Line:(-?\d+)", out, re.M)
        if not inp or not line:
            if jump:
                self.status.showMessage("No source found for that spot in the PDF", 3000)
            return
        path = os.path.normpath(os.path.join(os.path.dirname(self.main), inp[1].strip()))
        if not os.path.isfile(path):
            return
        ln = max(1, int(line[1]))
        if jump:
            ed = self.open_in_editor(path, ln)
            if ed:
                ed.show_sync_line(ln, flash_ms=1500)
        else:
            ed = self.find_editor(path)
            if ed is None or self.tabs.currentWidget() is not ed:
                ed = self.open_in_editor(path)
            if ed:
                ed.show_sync_line(ln)
                for i in range(self.tabs.count()):
                    if self.tabs.widget(i) is not ed:
                        self.tabs.widget(i).clear_sync_line()
            rel = os.path.relpath(path, self.root) if self.root else os.path.basename(path)
            self.status.showMessage(f"PDF ↔ {rel}:{ln}", 2000)

    # ------------------------------------------------------------------ close
    def closeEvent(self, e):
        if not self._maybe_save_all():
            e.ignore()
            return
        self._save_session()
        self.settings.setValue("geometry", self.saveGeometry())
        self.settings.setValue("useLatexmk", "true" if self.use_latexmk.isChecked() else "false")
        self.settings.setValue("live", "true" if self.auto.isChecked() else "false")
        self.settings.setValue("boxes", "true" if self.show_boxes.isChecked() else "false")
        self.stop_compile()
        e.accept()


APP_VERSION = "1.0.4"


def resource_path(*parts):
    """Path to a bundled file, both when run as a script and as a PyInstaller build."""
    base = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base, *parts)


def windows_setup():
    """Windows-only fixes for running as a windowed .exe."""
    if sys.platform != "win32":
        return
    import ctypes
    try:
        # Own taskbar group/icon instead of being grouped with python.exe
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("QTeX.Editor")
    except Exception:
        pass
    try:
        # A windowed .exe has no console, so every pdflatex/bibtex/synctex run would pop up
        # its own console window. Give the app one hidden console that the children inherit.
        k32, u32 = ctypes.windll.kernel32, ctypes.windll.user32
        if not k32.GetConsoleWindow() and k32.AllocConsole():
            hwnd = k32.GetConsoleWindow()
            if hwnd:
                u32.ShowWindow(hwnd, 0)  # SW_HIDE
    except Exception:
        pass


def main():
    windows_setup()
    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setApplicationVersion(APP_VERSION)
    icon = resource_path("assets", "qtex.png")
    if os.path.exists(icon):
        from PySide6.QtGui import QIcon
        app.setWindowIcon(QIcon(icon))
    apply_theme(QSettings(APP_NAME, APP_NAME).value("theme", "system"))
    w = MainWindow(sys.argv[1] if len(sys.argv) > 1 else None)
    w.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
