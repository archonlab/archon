"""Toolkit-independent dialog contracts for OL2-DIALOGS1."""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class DialogKind(str, Enum):
    CONFIRM = "confirm"
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"


class DialogResult(str, Enum):
    YES = "yes"
    NO = "no"
    OK = "ok"


@dataclass(frozen=True, slots=True)
class DialogSpec:
    title: str
    message: str
    kind: DialogKind = DialogKind.CONFIRM
    primary_label: str = "Yes"
    secondary_label: str | None = "No"
    primary_result: DialogResult = DialogResult.YES
    secondary_result: DialogResult = DialogResult.NO
    destructive: bool = False

    def __post_init__(self) -> None:
        if not self.title.strip():
            raise ValueError("dialog title is required")
        if not self.message.strip():
            raise ValueError("dialog message is required")
        if not self.primary_label.strip():
            raise ValueError("primary dialog label is required")
        if self.secondary_label is not None and not self.secondary_label.strip():
            raise ValueError("secondary dialog label cannot be blank")

    @classmethod
    def confirm(
        cls,
        title: str,
        message: str,
        *,
        yes: str = "Yes",
        no: str = "No",
        destructive: bool = False,
    ) -> "DialogSpec":
        return cls(
            title=title,
            message=message,
            kind=DialogKind.CONFIRM,
            primary_label=yes,
            secondary_label=no,
            primary_result=DialogResult.YES,
            secondary_result=DialogResult.NO,
            destructive=destructive,
        )

    @classmethod
    def notice(cls, title: str, message: str, *, kind: DialogKind) -> "DialogSpec":
        if kind is DialogKind.CONFIRM:
            raise ValueError("notice kind cannot be confirm")
        return cls(
            title=title,
            message=message,
            kind=kind,
            primary_label="OK",
            secondary_label=None,
            primary_result=DialogResult.OK,
            secondary_result=DialogResult.OK,
        )


__all__ = ["DialogKind", "DialogResult", "DialogSpec"]
