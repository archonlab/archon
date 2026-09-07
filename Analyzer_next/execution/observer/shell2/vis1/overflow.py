"""OL2-VIS1 themed Observation overflow popover.

This deliberately avoids ``tk.Menu`` because native menus ignore the launcher's
semantic light/dark palette on several desktops.  The popover is presentation
only; commands remain owned by INTERACT1.
"""
from __future__ import annotations

import tkinter as tk
from dataclasses import dataclass
from typing import Callable, Iterable

from Analyzer_next.execution.observer.shell2.theme import ThemePalette


@dataclass(frozen=True, slots=True)
class OverflowAction:
    label: str
    command: Callable[[], None]
    danger: bool = False


class ObservationOverflowPopover:
    WIDTH = 220

    def __init__(self, root: tk.Misc) -> None:
        self.root = root
        self.window: tk.Toplevel | None = None

    def close(self) -> None:
        window = self.window
        self.window = None
        if window is None:
            return
        try:
            if window.winfo_exists():
                window.destroy()
        except tk.TclError:
            pass

    def show(
        self,
        anchor: tk.Misc,
        actions: Iterable[OverflowAction | None],
        palette: ThemePalette,
    ) -> None:
        self.close()
        popup = tk.Toplevel(self.root)
        self.window = popup
        popup.withdraw()
        popup.overrideredirect(True)
        try:
            popup.transient(self.root.winfo_toplevel())
        except (tk.TclError, AttributeError):
            pass
        popup.configure(background=palette["border.strong"])

        body = tk.Frame(
            popup,
            background=palette["surface.card"],
            borderwidth=0,
            highlightthickness=1,
            highlightbackground=palette["border.strong"],
            highlightcolor=palette["border.strong"],
        )
        body.pack(fill="both", expand=True)

        for action in actions:
            if action is None:
                tk.Frame(
                    body,
                    background=palette["border.default"],
                    height=1,
                    borderwidth=0,
                ).pack(fill="x", padx=8, pady=5)
                continue
            normal_bg = palette["surface.card"]
            active_bg = palette["action.danger"] if action.danger else palette["surface.selected"]
            active_fg = palette["text.inverse"] if action.danger else palette["text.primary"]
            button = tk.Button(
                body,
                text=action.label,
                command=self._wrapped(action.command),
                anchor="w",
                relief="flat",
                borderwidth=0,
                highlightthickness=0,
                padx=14,
                pady=8,
                background=normal_bg,
                foreground=palette["status.failed"] if action.danger else palette["text.primary"],
                activebackground=active_bg,
                activeforeground=active_fg,
                font=("TkDefaultFont", 9),
                cursor="hand2",
            )
            button.pack(fill="x", padx=2, pady=1)

        popup.update_idletasks()
        width = max(self.WIDTH, popup.winfo_reqwidth())
        height = popup.winfo_reqheight()
        try:
            anchor_right = anchor.winfo_rootx() + anchor.winfo_width()
            anchor_bottom = anchor.winfo_rooty() + anchor.winfo_height()
            screen_w = popup.winfo_screenwidth()
            screen_h = popup.winfo_screenheight()
            x = max(4, min(anchor_right - width, screen_w - width - 4))
            y = max(4, min(anchor_bottom + 4, screen_h - height - 4))
            popup.geometry(f"{width}x{height}+{x}+{y}")
        except tk.TclError:
            pass
        popup.deiconify()
        popup.lift()
        try:
            popup.focus_set()
        except tk.TclError:
            pass
        popup.bind("<Escape>", lambda _event: (self.close(), "break")[1])
        popup.bind("<FocusOut>", self._schedule_focus_check, add="+")

    def _wrapped(self, command: Callable[[], None]) -> Callable[[], None]:
        def invoke() -> None:
            self.close()
            command()
        return invoke

    def _schedule_focus_check(self, _event=None) -> None:
        try:
            self.root.after(60, self._close_if_focus_elsewhere)
        except tk.TclError:
            self.close()

    def _close_if_focus_elsewhere(self) -> None:
        popup = self.window
        if popup is None:
            return
        try:
            focus = popup.focus_get()
            if focus is None:
                self.close()
                return
            if str(focus).startswith(str(popup)):
                return
        except tk.TclError:
            pass
        self.close()
