"""Tiny headless Tk compatibility layer for the OL2 presentation bridge.

The legacy Observer owns scientific state and timing. This module only
provides the widget/event-loop surface it expects so the legacy WorldViewer
can run without creating a second desktop window.
"""
from __future__ import annotations

from dataclasses import dataclass, field
import heapq
import itertools
import time
from typing import Any, Callable


Callback = Callable[[], Any]


class _Widget:
    _ids = itertools.count(1)

    def __init__(self, master: Any = None, **kwargs: Any) -> None:
        self.master = master
        self.children: list[Any] = []
        self.options: dict[str, Any] = dict(kwargs)
        self._exists = True
        self._width = int(kwargs.get("width") or 640)
        self._height = int(kwargs.get("height") or 480)
        self._items: dict[int, dict[str, Any]] = {}
        if master is not None and hasattr(master, "children"):
            master.children.append(self)

    def pack(self, *args: Any, **kwargs: Any) -> None:
        return None

    def grid(self, *args: Any, **kwargs: Any) -> None:
        return None

    def place(self, *args: Any, **kwargs: Any) -> None:
        return None

    def pack_forget(self) -> None:
        return None

    def grid_remove(self) -> None:
        return None

    def place_forget(self) -> None:
        return None

    def pack_propagate(self, flag: bool) -> None:
        return None

    def grid_propagate(self, flag: bool) -> None:
        return None

    def grid_rowconfigure(self, *args: Any, **kwargs: Any) -> None:
        return None

    def grid_columnconfigure(self, *args: Any, **kwargs: Any) -> None:
        return None

    def configure(self, cnf: Any = None, **kwargs: Any) -> None:
        if isinstance(cnf, dict):
            self.options.update(cnf)
        self.options.update(kwargs)
        if "width" in kwargs:
            try:
                self._width = int(kwargs["width"])
            except Exception:
                pass
        if "height" in kwargs:
            try:
                self._height = int(kwargs["height"])
            except Exception:
                pass

    config = configure

    def cget(self, key: str) -> Any:
        return self.options.get(key, "")

    def bind(self, *args: Any, **kwargs: Any) -> None:
        return None

    def bind_all(self, *args: Any, **kwargs: Any) -> None:
        return None

    def unbind_all(self, *args: Any, **kwargs: Any) -> None:
        return None

    def destroy(self) -> None:
        self._exists = False

    def winfo_exists(self) -> int:
        return int(self._exists)

    def winfo_width(self) -> int:
        return max(1, self._width)

    def winfo_height(self) -> int:
        return max(1, self._height)

    def winfo_children(self) -> list[Any]:
        return list(self.children)

    def winfo_screenwidth(self) -> int:
        return 1920

    def winfo_screenheight(self) -> int:
        return 1080

    def update_idletasks(self) -> None:
        return None

    def lift(self) -> None:
        return None

    def tag_raise(self, *args: Any, **kwargs: Any) -> None:
        return None

    def focus_set(self) -> None:
        return None

    def yview(self, *args: Any, **kwargs: Any) -> tuple[float, float]:
        return (0.0, 1.0)

    def xview(self, *args: Any, **kwargs: Any) -> tuple[float, float]:
        return (0.0, 1.0)

    def yview_scroll(self, *args: Any, **kwargs: Any) -> None:
        return None

    def set(self, *args: Any, **kwargs: Any) -> None:
        return None

    def bbox(self, *args: Any, **kwargs: Any) -> tuple[int, int, int, int]:
        return (0, 0, self.winfo_width(), self.winfo_height())

    def create_rectangle(self, *coords: Any, **kwargs: Any) -> int:
        item = next(self._ids)
        self._items[item] = {"coords": tuple(coords), **kwargs}
        return item

    def create_text(self, *coords: Any, **kwargs: Any) -> int:
        item = next(self._ids)
        self._items[item] = {"coords": tuple(coords), **kwargs}
        return item

    def create_window(self, *coords: Any, **kwargs: Any) -> int:
        item = next(self._ids)
        self._items[item] = {"coords": tuple(coords), **kwargs}
        return item

    def coords(self, item: int, *coords: Any) -> tuple[Any, ...]:
        if item in self._items and coords:
            self._items[item]["coords"] = tuple(coords)
        return tuple(self._items.get(item, {}).get("coords", ()))

    def itemconfig(self, item: int, **kwargs: Any) -> None:
        self._items.setdefault(item, {}).update(kwargs)

    itemconfigure = itemconfig

    def delete(self, target: Any) -> None:
        if target == "all":
            self._items.clear()
            return
        if isinstance(target, int):
            self._items.pop(target, None)
            return
        doomed = [
            item for item, data in self._items.items()
            if target in tuple(data.get("tags") or ())
        ]
        for item in doomed:
            self._items.pop(item, None)

    def __getattr__(self, name: str):
        if name.startswith("_"):
            raise AttributeError(name)
        return lambda *args, **kwargs: None


@dataclass(order=True)
class _Scheduled:
    due: float
    sequence: int
    callback: Callback = field(compare=False)


class HeadlessRoot(_Widget):
    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(None, width=1536, height=864)
        self._destroyed = False
        self._queue: list[_Scheduled] = []
        self._sequence = itertools.count()
        self._title = ""

    def title(self, text: str | None = None) -> str:
        if text is not None:
            self._title = str(text)
        return self._title

    def geometry(self, value: str) -> None:
        try:
            size = value.split("+", 1)[0]
            width, height = size.split("x", 1)
            self._width = int(width)
            self._height = int(height)
        except Exception:
            pass

    def minsize(self, width: int, height: int) -> None:
        self._width = max(self._width, int(width))
        self._height = max(self._height, int(height))

    def protocol(self, *args: Any, **kwargs: Any) -> None:
        return None

    def resizable(self, *args: Any, **kwargs: Any) -> None:
        return None

    def transient(self, *args: Any, **kwargs: Any) -> None:
        return None

    def grab_set(self) -> None:
        return None

    def wait_window(self, *args: Any, **kwargs: Any) -> None:
        return None

    def after(
        self,
        milliseconds: int,
        callback: Callback | None = None,
        *args: Any,
    ) -> int:
        if callback is None:
            return 0
        delay = max(0, int(milliseconds)) / 1000.0
        sequence = next(self._sequence)
        scheduled_callback = (lambda: callback(*args)) if args else callback
        heapq.heappush(
            self._queue,
            _Scheduled(time.monotonic() + delay, sequence, scheduled_callback),
        )
        return sequence

    def after_idle(self, callback: Callback, *args: Any) -> int:
        return self.after(0, callback, *args)

    def mainloop(self) -> None:
        while not self._destroyed:
            if not self._queue:
                time.sleep(0.001)
                continue
            scheduled = heapq.heappop(self._queue)
            now = time.monotonic()
            if scheduled.due > now:
                time.sleep(min(scheduled.due - now, 0.05))
                heapq.heappush(self._queue, scheduled)
                continue
            scheduled.callback()

    def destroy(self) -> None:
        self._destroyed = True
        self._exists = False
        self._queue.clear()

    quit = destroy


class HeadlessToplevel(HeadlessRoot):
    def __init__(self, master: Any = None, *args: Any, **kwargs: Any) -> None:
        _Widget.__init__(self, master, width=640, height=480)
        self._destroyed = False
        self._queue = []
        self._sequence = itertools.count()
        self._title = ""


class _Variable:
    def __init__(self, master: Any = None, value: Any = None, **kwargs: Any) -> None:
        self._value = value

    def get(self) -> Any:
        return self._value

    def set(self, value: Any) -> None:
        self._value = value


class HeadlessTkModule:
    Tk = HeadlessRoot
    Toplevel = HeadlessToplevel
    Frame = _Widget
    Canvas = _Widget
    Label = _Widget
    Button = _Widget
    Scrollbar = _Widget
    Checkbutton = _Widget
    Entry = _Widget
    Scale = _Widget
    Listbox = _Widget
    Menu = _Widget
    StringVar = _Variable
    BooleanVar = _Variable
    IntVar = _Variable
    DoubleVar = _Variable
    END = "end"
    HORIZONTAL = "horizontal"
    VERTICAL = "vertical"
    TclError = RuntimeError

    def __getattr__(self, name: str):
        # Compatibility for presentation-only Tk additions in newer legacy
        # revisions. Widget-like class names become no-op widgets; constants
        # keep a stable lower-case token.
        if name.isupper():
            return name.lower()
        if name and name[0].isupper():
            return _Widget
        raise AttributeError(name)


__all__ = ["HeadlessRoot", "HeadlessTkModule"]
