"""The native folder picker for choosing where the game and its logs are saved.

By default the scoreboard writes its database, backup, and logs to the standard
per-user location for the laptop it runs on. That is the right default, but it
is buried several folders deep, and an operator who wants the game data on a
USB stick, on a shared drive, or simply somewhere they can find after a game
should not have to edit an environment variable to get it.

This module opens a real Windows folder dialog and remembers the answer. It
holds no game state and never touches a database: it validates a folder,
records the choice, and reports what happened. The choice takes effect at the
**next launch**, because the database connection, the instance lock, and the
log handler are all open on the current folder while a game is running.

Two dialog paths, tried in order, because the picker is reachable from two
different places:

* the window's own dialog, when the operator clicks the control inside the
  running application;
* a WinForms dialog on a dedicated STA thread, when there is no window at all
  --- the ``--choose-data-folder`` command a technician runs before a season.

Both are already available: the window dialog comes from pywebview and the
WinForms one from pythonnet, and both are pinned dependencies that already ship
in the package. Nothing new is added to the build for this.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from scoreboard.infrastructure.paths import (
    PathResolutionError,
    clear_chosen_root,
    describe_resolution,
    resolve_paths,
    write_chosen_root,
)


@dataclass(frozen=True, slots=True)
class FolderChoice:
    """What came back from the picker, in terms the operator view can render."""

    #: ``chosen``, ``cancelled``, ``rejected``, or ``unavailable``.
    outcome: str
    message: str
    root: str | None = None

    @property
    def changed(self) -> bool:
        return self.outcome == "chosen"

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "outcome": self.outcome,
            "changed": self.changed,
            "message": self.message,
            "root": self.root,
        }
        payload["location"] = describe_resolution()
        return payload


def _from_window(window: Any, initial: str) -> str | None:
    """Ask the running window for a folder, or raise if it cannot."""

    import webview

    # `FileDialog.FOLDER` is the current spelling; `FOLDER_DIALOG` is the
    # deprecated alias kept by pywebview. Prefer the new one and fall back, so
    # this keeps working across a dependency bump in either direction.
    dialog_type = getattr(getattr(webview, "FileDialog", None), "FOLDER", None)
    if dialog_type is None:
        dialog_type = webview.FOLDER_DIALOG
    selection = window.create_file_dialog(dialog_type, directory=initial)
    if not selection:
        return None
    first = selection[0] if isinstance(selection, (list, tuple)) else selection
    return str(first)


def _from_winforms(initial: str) -> str | None:
    """Ask Windows directly, with no application window in play.

    WinForms dialogs must run on a single-threaded-apartment thread, and the
    interpreter's main thread is not one, so the dialog gets a thread of its
    own and this call waits for it.
    """

    import clr

    clr.AddReference("System.Windows.Forms")
    from System.Threading import ApartmentState, Thread, ThreadStart
    from System.Windows.Forms import DialogResult, FolderBrowserDialog

    picked: list[str] = []

    def show() -> None:
        dialog = FolderBrowserDialog()
        dialog.Description = "Choose where the scoreboard saves its game and logs"
        dialog.UseDescriptionForTitle = True
        dialog.ShowNewFolderButton = True
        if initial:
            dialog.SelectedPath = initial
        if dialog.ShowDialog() == DialogResult.OK:
            picked.append(str(dialog.SelectedPath))

    thread = Thread(ThreadStart(show))
    thread.SetApartmentState(ApartmentState.STA)
    thread.Start()
    thread.Join()
    return picked[0] if picked else None


def open_folder_dialog(window: Any = None, initial: str | None = None) -> str | None:
    """Show a folder dialog and return the selected path, or ``None``.

    ``None`` means the operator cancelled, which is not an error and must leave
    the saved choice exactly as it was.
    """

    start = initial if initial is not None else str(resolve_paths().root)
    if window is not None:
        try:
            return _from_window(window, start)
        except Exception:  # noqa: BLE001 - fall through to the windowless path
            pass
    return _from_winforms(start)


def choose_data_folder(window: Any = None) -> FolderChoice:
    """Open the picker, validate the answer, and remember it for next launch.

    Every failure is reported rather than raised. This is called from a button
    an operator may press during a game: a dialog that will not open, or a
    folder that cannot be written to, must leave the running game completely
    untouched and say so.
    """

    try:
        selection = open_folder_dialog(window)
    except Exception as exc:  # noqa: BLE001 - a picker must not end a game
        return FolderChoice(
            outcome="unavailable",
            message=(
                "The folder picker could not be opened on this computer "
                f"({exc}). The scoreboard is still saving to its current "
                "folder. You can also set the SCOREBOARD_DATA_DIR environment "
                "variable instead."
            ),
        )

    if selection is None:
        return FolderChoice(
            outcome="cancelled",
            message="No change. The scoreboard is still saving where it was.",
        )

    try:
        saved = write_chosen_root(selection)
    except PathResolutionError as exc:
        return FolderChoice(
            outcome="rejected",
            message=(
                f"That folder cannot be used: {exc}. Nothing was changed; the "
                "scoreboard is still saving where it was."
            ),
        )

    return FolderChoice(
        outcome="chosen",
        root=str(saved),
        message=(
            f"Saved. The scoreboard will use {saved} the next time it starts. "
            "The game running now keeps saving to its current folder, so "
            "finish this game before restarting."
        ),
    )


def use_default_folder() -> FolderChoice:
    """Forget a chosen folder and go back to the standard per-user location."""

    clear_chosen_root()
    location = describe_resolution()
    return FolderChoice(
        outcome="chosen",
        root=location["default_root"],
        message=(
            f"Saved. The scoreboard will use its standard folder, "
            f"{location['default_root']}, the next time it starts."
        ),
    )


__all__ = [
    "FolderChoice",
    "choose_data_folder",
    "open_folder_dialog",
    "use_default_folder",
]
