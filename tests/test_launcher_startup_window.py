from __future__ import annotations

from types import SimpleNamespace

import launcher_web


class FakeNativeEvent:
    def __init__(self) -> None:
        self.handlers = []

    def __iadd__(self, handler):
        self.handlers.append(handler)
        return self

    def fire(self, sender) -> None:
        for handler in list(self.handlers):
            handler(sender, object())


class FakeForm:
    def __init__(self) -> None:
        self.Shown = FakeNativeEvent()
        self._window_state = None
        self._top_most = False
        self.actions: list[tuple[str, object] | tuple[str]] = []

    @property
    def WindowState(self):
        return self._window_state

    @WindowState.setter
    def WindowState(self, value) -> None:
        self._window_state = value
        self.actions.append(("WindowState", value))

    @property
    def TopMost(self):
        return self._top_most

    @TopMost.setter
    def TopMost(self, value) -> None:
        self._top_most = bool(value)
        self.actions.append(("TopMost", bool(value)))

    def BringToFront(self) -> None:
        self.actions.append(("BringToFront",))

    def Activate(self) -> None:
        self.actions.append(("Activate",))


def test_bring_native_form_to_front_maximizes_and_releases_topmost() -> None:
    form = FakeForm()

    launcher_web._bring_native_form_to_front(form, "MAXIMIZED")

    assert form.WindowState == "MAXIMIZED"
    assert form.TopMost is False
    assert form.actions == [
        ("WindowState", "MAXIMIZED"),
        ("TopMost", True),
        ("BringToFront",),
        ("Activate",),
        ("TopMost", False),
        ("BringToFront",),
        ("Activate",),
    ]


def test_install_windows_startup_focus_is_noop_off_windows(monkeypatch) -> None:
    monkeypatch.setattr(launcher_web.sys, "platform", "linux")
    window = SimpleNamespace(native=FakeForm())

    assert launcher_web._install_windows_startup_focus(window) is False
    assert window.native.actions == []
    assert window.native.Shown.handlers == []


def test_install_windows_startup_focus_handles_missing_native(monkeypatch) -> None:
    monkeypatch.setattr(launcher_web.sys, "platform", "win32")
    window = SimpleNamespace(native=None)
    winforms = SimpleNamespace(FormWindowState=SimpleNamespace(Maximized="MAXIMIZED"))

    assert launcher_web._install_windows_startup_focus(window, winforms=winforms) is False


def test_install_windows_startup_focus_runs_once_on_native_shown(monkeypatch) -> None:
    monkeypatch.setattr(launcher_web.sys, "platform", "win32")
    form = FakeForm()
    window = SimpleNamespace(native=form)
    winforms = SimpleNamespace(FormWindowState=SimpleNamespace(Maximized="MAXIMIZED"))

    assert launcher_web._install_windows_startup_focus(window, winforms=winforms) is True
    assert form.WindowState == "MAXIMIZED"
    assert len(form.Shown.handlers) == 1

    form.actions.clear()
    form.Shown.fire(form)
    first_run = list(form.actions)
    form.Shown.fire(form)

    assert first_run == [
        ("WindowState", "MAXIMIZED"),
        ("TopMost", True),
        ("BringToFront",),
        ("Activate",),
        ("TopMost", False),
        ("BringToFront",),
        ("Activate",),
    ]
    assert form.actions == first_run


def test_install_windows_startup_focus_uses_selected_pywebview_backend(monkeypatch) -> None:
    monkeypatch.setattr(launcher_web.sys, "platform", "win32")
    form = FakeForm()
    winforms = SimpleNamespace(FormWindowState=SimpleNamespace(Maximized="MAXIMIZED"))
    window = SimpleNamespace(native=form, gui=SimpleNamespace(WinForms=winforms))

    assert launcher_web._install_windows_startup_focus(window) is True
    assert form.WindowState == "MAXIMIZED"
    assert len(form.Shown.handlers) == 1
