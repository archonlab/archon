"""Theme-aware Tk modal presenter for OL2-DIALOGS1."""
from __future__ import annotations

from collections.abc import Callable
import tkinter as tk

from Analyzer_next.execution.observer.shell2.theme import ColorScheme, palette_for

from .model import DialogKind, DialogResult, DialogSpec


_KIND_TOKENS = {
    DialogKind.CONFIRM: "action.primary",
    DialogKind.INFO: "status.info",
    DialogKind.WARNING: "status.waiting",
    DialogKind.ERROR: "status.failed",
}


class ThemedDialogPresenter:
    """Render small blocking modals without delegating labels/theme to the OS."""

    def __init__(self, root: tk.Misc, scheme_provider: Callable[[], ColorScheme | str]) -> None:
        self.root = root
        self.scheme_provider = scheme_provider
        self.active_dialog: tk.Toplevel | None = None
        self.active_buttons: dict[str, tk.Button] = {}
        self._result = DialogResult.NO

    def show(self, spec: DialogSpec) -> DialogResult:
        if self.active_dialog is not None:
            try:
                if self.active_dialog.winfo_exists():
                    self.active_dialog.lift()
                    return DialogResult.NO
            except tk.TclError:
                pass
        palette = palette_for(self.scheme_provider())
        self._result = spec.secondary_result if spec.secondary_label is not None else spec.primary_result
        dialog = tk.Toplevel(self.root)
        self.active_dialog = dialog
        self.active_buttons = {}
        dialog.title(spec.title)
        dialog.transient(self.root)
        dialog.resizable(False, False)
        dialog.configure(background=palette["surface.app"])
        dialog.protocol("WM_DELETE_WINDOW", lambda: self._finish(self._default_cancel_result(spec)))

        outer = tk.Frame(
            dialog,
            background=palette["surface.card"],
            highlightbackground=palette["border.default"],
            highlightthickness=1,
            borderwidth=0,
        )
        outer.pack(fill="both", expand=True, padx=1, pady=1)

        accent = tk.Frame(outer, background=palette[_KIND_TOKENS[spec.kind]], width=5, borderwidth=0)
        accent.pack(side="left", fill="y")
        accent.pack_propagate(False)

        content = tk.Frame(outer, background=palette["surface.card"], borderwidth=0)
        content.pack(side="left", fill="both", expand=True)

        heading = tk.Label(
            content,
            text=spec.title,
            background=palette["surface.card"],
            foreground=palette["text.primary"],
            borderwidth=0,
            anchor="w",
            justify="left",
            font=("TkDefaultFont", 12, "bold"),
        )
        heading.pack(fill="x", padx=20, pady=(18, 8))

        message = tk.Label(
            content,
            text=spec.message,
            background=palette["surface.card"],
            foreground=palette["text.secondary"],
            borderwidth=0,
            anchor="w",
            justify="left",
            wraplength=590,
            font=("TkDefaultFont", 10),
        )
        message.pack(fill="x", padx=20, pady=(0, 18))

        actions = tk.Frame(content, background=palette["surface.elevated"], borderwidth=0)
        actions.pack(fill="x")
        inner = tk.Frame(actions, background=palette["surface.elevated"], borderwidth=0)
        inner.pack(fill="x", padx=14, pady=12)

        if spec.secondary_label is not None:
            secondary = self._button(
                inner,
                spec.secondary_label,
                lambda: self._finish(spec.secondary_result),
                background=palette["surface.control"],
                foreground=palette["text.primary"],
                active_background=palette["surface.card"],
                active_foreground=palette["text.primary"],
            )
            secondary.pack(side="right", padx=(6, 0))
            self.active_buttons[spec.secondary_label] = secondary

        if spec.destructive:
            primary_bg = palette["action.danger"]
            primary_hover = palette["action.danger_hover"]
        else:
            primary_bg = palette["action.primary"]
            primary_hover = palette["action.primary_hover"]
        primary = self._button(
            inner,
            spec.primary_label,
            lambda: self._finish(spec.primary_result),
            background=primary_bg,
            foreground=palette["text.inverse"],
            active_background=primary_hover,
            active_foreground=palette["text.inverse"],
        )
        primary.pack(side="right")
        self.active_buttons[spec.primary_label] = primary

        dialog.bind("<Return>", lambda _event: self._finish(spec.primary_result), add="+")
        dialog.bind("<KP_Enter>", lambda _event: self._finish(spec.primary_result), add="+")
        dialog.bind("<Escape>", lambda _event: self._finish(self._default_cancel_result(spec)), add="+")

        dialog.update_idletasks()
        self._center(dialog)
        try:
            dialog.grab_set()
        except tk.TclError:
            pass
        try:
            primary.focus_set()
        except tk.TclError:
            pass
        self.root.wait_window(dialog)
        return self._result

    def confirm(self, title: str, message: str, *, destructive: bool = False) -> bool:
        return self.show(DialogSpec.confirm(title, message, destructive=destructive)) is DialogResult.YES

    def info(self, title: str, message: str) -> None:
        self.show(DialogSpec.notice(title, message, kind=DialogKind.INFO))

    def warning(self, title: str, message: str) -> None:
        self.show(DialogSpec.notice(title, message, kind=DialogKind.WARNING))

    def error(self, title: str, message: str) -> None:
        self.show(DialogSpec.notice(title, message, kind=DialogKind.ERROR))

    def _button(
        self,
        parent: tk.Misc,
        text: str,
        command,
        *,
        background: str,
        foreground: str,
        active_background: str,
        active_foreground: str,
    ) -> tk.Button:
        return tk.Button(
            parent,
            text=text,
            command=command,
            borderwidth=0,
            relief="flat",
            cursor="hand2",
            padx=18,
            pady=8,
            background=background,
            foreground=foreground,
            activebackground=active_background,
            activeforeground=active_foreground,
            highlightthickness=0,
            font=("TkDefaultFont", 10, "bold"),
        )

    @staticmethod
    def _default_cancel_result(spec: DialogSpec) -> DialogResult:
        return spec.secondary_result if spec.secondary_label is not None else spec.primary_result

    def _finish(self, result: DialogResult) -> None:
        self._result = result
        dialog = self.active_dialog
        self.active_dialog = None
        self.active_buttons = {}
        if dialog is None:
            return
        try:
            dialog.grab_release()
        except tk.TclError:
            pass
        try:
            dialog.destroy()
        except tk.TclError:
            pass

    def _center(self, dialog: tk.Toplevel) -> None:
        try:
            root_x = self.root.winfo_rootx()
            root_y = self.root.winfo_rooty()
            root_w = self.root.winfo_width()
            root_h = self.root.winfo_height()
            width = dialog.winfo_reqwidth()
            height = dialog.winfo_reqheight()
            x = root_x + max(0, (root_w - width) // 2)
            y = root_y + max(0, (root_h - height) // 3)
            dialog.geometry(f"+{x}+{y}")
        except tk.TclError:
            return


__all__ = ["ThemedDialogPresenter"]
