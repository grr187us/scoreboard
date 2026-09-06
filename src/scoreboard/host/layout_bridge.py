"""The host bridge for the presentation layout editor (spec section 6).

The presentation layout is a host concern, exactly like the display preference
and the data folder in :mod:`scoreboard.host.bridge`: reading, validating,
saving, selecting, renaming, duplicating, resetting, or previewing a layout
advances no revision,
submits no :class:`~scoreboard.domain.commands.Command`, writes nothing to
``scoreboard.db`` or its backup, and records no action-history row. The one
durable side effect anywhere in this module is a write to ``layouts.json``
through :mod:`scoreboard.infrastructure.layouts`, which is deliberately a
separate file from ``config.json`` and the game database (see that module's
docstring for why).

Two small classes carry that separation into the webview boundary:

* :class:`PresentationLayouts` is the host-side object that owns the layout
  library in memory, mirroring how :class:`~scoreboard.host.bridge.DisplayLink`
  and the data-folder functions are host actions rather than game state. It
  never receives, holds, or calls the
  :class:`~scoreboard.application.service.ScoreboardService`: nothing in this
  class can build a ``Command``.
* :class:`LayoutEditorBridge` is the ``js_api`` handed to the layout editor
  window. It reads a live, read-only spectator snapshot and forwards every
  other call to a :class:`PresentationLayouts`. There is deliberately no
  ``command`` method here, and no method whose name matches a
  :class:`~scoreboard.domain.commands.CommandType` value: the editor window
  has no path to a game mutation at all.

:class:`LayoutLink` mirrors :class:`~scoreboard.host.bridge.DisplayLink`: a
tiny seam the bridge can be tested against without a real window, replaced by
:class:`~scoreboard.host.app.WindowHost` at wiring time. On its own it opens
and publishes nothing, which is what lets every test in this module run
without a webview.

A layout ``publish`` failure must never fail a save or reach the game (R-002),
so :meth:`PresentationLayouts.save`/``select``/``delete``/``reset`` call the
link's ``publish`` inside a ``try/except`` that logs through
:class:`~scoreboard.infrastructure.diagnostics.Diagnostics` and never
propagates.
"""

from __future__ import annotations

from typing import Any, Callable

from scoreboard.infrastructure import layouts as layouts_infra
from scoreboard.infrastructure.diagnostics import Diagnostics, NullDiagnostics
from scoreboard.infrastructure.paths import ScoreboardPaths
from scoreboard.presentation import layout as layout_module


class LayoutLink:
    """Host hook, mirroring DisplayLink. On its own it opens and pushes nothing.

    :class:`~scoreboard.host.app.WindowHost` replaces ``open_editor`` and
    ``publish`` at wiring time. Left alone -- which is what every test below
    that does not care about the editor window uses -- opening the editor
    reports a plain-language "unavailable" message rather than raising, and a
    publish is a silent no-op.
    """

    def open_editor(self) -> dict[str, str]:
        """Overridden by the host. On its own this opens no editor window."""

        return {"message": "The layout editor is unavailable."}

    def publish(self, layout: dict[str, Any]) -> None:
        """Overridden by the host. On its own this pushes nothing anywhere."""

        return None


class PresentationLayouts:
    """Reads, validates, stores, and publishes spectator layouts.

    A host concern, exactly like the display preference and the data folder:
    it advances no revision, writes nothing to the game database, and records
    no action history. It holds no reference to a
    :class:`~scoreboard.application.service.ScoreboardService` at all, so
    nothing here can build or submit a
    :class:`~scoreboard.domain.commands.Command`.
    """

    def __init__(
        self,
        paths: ScoreboardPaths,
        *,
        diagnostics: Diagnostics | None = None,
        link: LayoutLink | None = None,
    ) -> None:
        self._paths = paths
        self._diagnostics = NullDiagnostics() if diagnostics is None else diagnostics
        self._link = LayoutLink() if link is None else link
        self._library = layouts_infra.read_library(paths)
        self._saved = True
        if self._library.fell_back and self._library.issues:
            # Something was stored and could not be used. Say so, and say what
            # it did not affect.
            self._diagnostics.note("LAYOUT_FILE_FELL_BACK")
            self._message = (
                "The saved presentation layout could not be read, so the "
                "built-in default is being used. Nothing about the game was "
                "affected."
            )
        elif self._library.fell_back:
            # Nothing has ever been saved. That is the ordinary first run, not
            # a fault, and must not be reported to an operator as damage.
            self._message = "No presentation layout has been saved yet; using the built-in default."
        else:
            self._message = f"Using the {self._library.active!r} layout."

    # --- The JavaScript-facing API ------------------------------------------

    @property
    def link(self) -> LayoutLink:
        return self._link

    def current_layout(self) -> dict[str, Any]:
        """The active layout document. Always a valid, normalized layout."""

        return self._library.active_layout()

    def state(self) -> dict[str, Any]:
        """Everything the editor and the operator need to render the library."""

        library = self._library
        return {
            "schema_version": layouts_infra.LAYOUT_LIBRARY_SCHEMA_VERSION,
            "active": library.active,
            "names": library.names(),
            "layout": library.active_layout(),
            "widgets": layout_module.widget_descriptors(),
            "limits": layout_module.limits(),
            # Built-in starting points the editor offers as a gallery. Each is
            # a complete, validated layout document (spec section 1.7).
            "presets": layout_module.preset_descriptors(),
            "issues": [issue.to_dict() for issue in library.issues],
            "fell_back": library.fell_back,
            "saved": self._saved,
            "message": self._message,
        }

    def preview(self, payload: Any) -> dict[str, Any]:
        """Validate a draft without writing or publishing anything."""

        return layout_module.validate_layout(payload).to_dict()

    def clamp(self, payload: Any) -> dict[str, Any]:
        """Best-effort "Fit to safe area" repair. Returns a draft, writes nothing."""

        normalized, clamp_issues = layout_module.clamp_layout(payload)
        result = layout_module.validate_layout(normalized).to_dict()
        result["warnings"] = [issue.to_dict() for issue in clamp_issues] + result["warnings"]
        return result

    def reset_widget(self, widget_id: Any, payload: Any) -> dict[str, Any]:
        """Reset one widget of a draft to its default. Returns a draft, writes nothing.

        The rest of the draft is repaired with :func:`~scoreboard.presentation
        .layout.clamp_layout` first (coordinates only, never colours or
        overlaps) rather than strictly validated, so resetting one broken
        widget can never discard every other change already made in the same
        editing session.
        """

        normalized, _clamp_issues = layout_module.clamp_layout(payload)
        updated = layout_module.reset_widget(normalized, widget_id)
        return layout_module.validate_layout(updated).to_dict()

    def save(self, name: Any, payload: Any) -> dict[str, Any]:
        """Validate and store one named layout.

        On failure the previously stored library is returned unchanged and
        nothing is written -- the "preserve the last valid layout" guarantee.
        """

        library, validation = layouts_infra.save_layout(self._paths, name, payload)
        self._library = library
        if validation.ok:
            self._saved = True
            self._message = f"Saved the {library.active!r} layout."
            self._diagnostics.note(
                "LAYOUT_SAVED", name=library.active, widgets=len(layout_module.WIDGET_IDS)
            )
            self._publish()
        else:
            self._saved = False
            self._message = (
                "The layout could not be saved. Fix the highlighted issues and try again."
            )
            self._diagnostics.note("LAYOUT_INVALID", reason="save")
        return self._finished(validation)

    def select(self, name: Any) -> dict[str, Any]:
        """Make a stored layout active. Never edits any layout's own contents."""

        library, validation = layouts_infra.select_layout(self._paths, name)
        self._library = library
        if validation.ok:
            self._saved = True
            self._message = f"Now showing the {library.active!r} layout."
            self._publish()
        else:
            self._saved = False
            self._message = "That layout could not be selected."
            self._diagnostics.note("LAYOUT_INVALID", reason="select")
        return self._finished(validation)

    def delete(self, name: Any) -> dict[str, Any]:
        """Remove a stored layout. ``"Default"`` can never be removed."""

        library, validation = layouts_infra.delete_layout(self._paths, name)
        self._library = library
        if validation.ok:
            self._saved = True
            self._message = f"Deleted the {name!r} layout."
            self._publish()
        else:
            self._saved = False
            self._message = "That layout could not be deleted."
            self._diagnostics.note("LAYOUT_INVALID", reason="delete")
        return self._finished(validation)

    def rename(self, old: Any, new: Any) -> dict[str, Any]:
        """Rename a stored layout. ``"Default"`` can never be renamed.

        Renaming the active layout keeps it active under the new name.
        """

        library, validation = layouts_infra.rename_layout(self._paths, old, new)
        self._library = library
        if validation.ok:
            self._saved = True
            self._message = f"Renamed the layout to {new!r}."
            self._publish()
        else:
            self._saved = False
            self._message = "That layout could not be renamed."
            self._diagnostics.note("LAYOUT_INVALID", reason="rename")
        return self._finished(validation)

    def duplicate(self, name: Any, new_name: Any) -> dict[str, Any]:
        """Copy a stored layout under a new name. The copy becomes active."""

        library, validation = layouts_infra.duplicate_layout(self._paths, name, new_name)
        self._library = library
        if validation.ok:
            self._saved = True
            self._message = f"Duplicated the layout as {library.active!r}."
            self._publish()
        else:
            self._saved = False
            self._message = "That layout could not be duplicated."
            self._diagnostics.note("LAYOUT_INVALID", reason="duplicate")
        return self._finished(validation)

    def reset(self) -> dict[str, Any]:
        """Restore the built-in default layout library."""

        self._library = layouts_infra.reset_library(self._paths)
        self._saved = True
        self._message = "The presentation layout was reset to the built-in default."
        self._diagnostics.note("LAYOUT_RESET")
        self._publish()
        payload = self.state()
        payload["ok"] = True
        return payload

    # --- Internals ------------------------------------------------------

    def _finished(self, validation: layout_module.LayoutValidation) -> dict[str, Any]:
        payload = self.state()
        payload["ok"] = validation.ok
        if not validation.ok:
            payload["errors"] = [issue.to_dict() for issue in validation.errors]
            payload["warnings"] = [issue.to_dict() for issue in validation.warnings]
        return payload

    def _publish(self) -> None:
        try:
            self._link.publish(self.current_layout())
        except Exception as exc:  # noqa: BLE001 - a publish must never fail a save (R-002)
            self._diagnostics.unhandled_error(context="layout_publish", error=exc)


class LayoutEditorBridge:
    """``js_api`` for the editor window. Presentation only.

    There is deliberately no ``command`` method here, and no method whose name
    matches a :class:`~scoreboard.domain.commands.CommandType` value: nothing
    exposed to this window can change the game. ``get_snapshot`` is the one
    read of live state, and it is read-only.
    """

    def __init__(
        self,
        layouts: PresentationLayouts,
        read_snapshot: Callable[[], dict[str, Any]],
    ) -> None:
        self._layouts = layouts
        self._read_snapshot = read_snapshot

    def get_snapshot(self) -> dict[str, Any]:
        """The live, read-only spectator view model the preview renders."""

        return self._read_snapshot()

    def layout_state(self) -> dict[str, Any]:
        return self._layouts.state()

    def preview_layout(self, payload: Any) -> dict[str, Any]:
        return self._layouts.preview(payload)

    def clamp_layout(self, payload: Any) -> dict[str, Any]:
        return self._layouts.clamp(payload)

    def reset_widget(self, widget_id: Any, payload: Any) -> dict[str, Any]:
        return self._layouts.reset_widget(widget_id, payload)

    def save_layout(self, name: Any, payload: Any) -> dict[str, Any]:
        return self._layouts.save(name, payload)

    def select_layout(self, name: Any) -> dict[str, Any]:
        return self._layouts.select(name)

    def delete_layout(self, name: Any) -> dict[str, Any]:
        return self._layouts.delete(name)

    def rename_layout(self, old: Any, new: Any) -> dict[str, Any]:
        return self._layouts.rename(old, new)

    def duplicate_layout(self, name: Any, new_name: Any) -> dict[str, Any]:
        return self._layouts.duplicate(name, new_name)

    def reset_layout(self) -> dict[str, Any]:
        return self._layouts.reset()


__all__ = [
    "LayoutEditorBridge",
    "LayoutLink",
    "PresentationLayouts",
]
