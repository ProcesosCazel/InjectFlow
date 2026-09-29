from __future__ import annotations

from pathlib import Path

import preview_renderer
from preview_renderer import ExcelPdfPreviewRenderer, PreviewDocument
from web_api import InjectFlowAPI


def _dummy_workbook(tmp_path: Path) -> Path:
    path = tmp_path / "HojaDeParametros.xlsx"
    path.write_bytes(b"dummy")
    return path


def test_preview_renderer_retries_after_failed_attempt(monkeypatch, tmp_path: Path) -> None:
    workbook = _dummy_workbook(tmp_path)
    monkeypatch.setattr(preview_renderer.sys, "platform", "win32")

    calls: list[Path] = []

    def fake_render(self, workbook_path: Path) -> PreviewDocument:
        calls.append(workbook_path)
        if len(calls) == 1:
            raise TimeoutError("simulated timeout")
        return PreviewDocument(content=b"%PDF-test", sheet_name="11092026")

    monkeypatch.setattr(ExcelPdfPreviewRenderer, "_render_isolated", fake_render)

    renderer = ExcelPdfPreviewRenderer(max_attempts=3, retry_delay_seconds=0)
    result = renderer.render(workbook)

    assert result.content == b"%PDF-test"
    assert result.sheet_name == "11092026"
    assert calls == [workbook.resolve(), workbook.resolve()]


def test_preview_renderer_stops_after_configured_attempts(monkeypatch, tmp_path: Path) -> None:
    workbook = _dummy_workbook(tmp_path)
    monkeypatch.setattr(preview_renderer.sys, "platform", "win32")

    calls = 0

    def always_fail(self, workbook_path: Path) -> PreviewDocument:
        nonlocal calls
        calls += 1
        raise RuntimeError("simulated Excel failure")

    monkeypatch.setattr(ExcelPdfPreviewRenderer, "_render_isolated", always_fail)

    renderer = ExcelPdfPreviewRenderer(max_attempts=3, retry_delay_seconds=0)

    try:
        renderer.render(workbook)
    except RuntimeError as exc:
        assert "3 intentos" in str(exc)
    else:
        raise AssertionError("Se esperaba RuntimeError despues de agotar los reintentos")

    assert calls == 3


def test_preview_api_rejects_parallel_preview_without_starting_another(tmp_path: Path) -> None:
    api = InjectFlowAPI(
        project_root=tmp_path,
        mapping_path=tmp_path / "data" / "Mapeo.xlsx",
    )
    api._preview_running = True

    result = api.get_current_preview()

    assert result["ok"] is False
    assert result["retryable"] is True
    assert result["error"]["code"] == "preview_busy"


def test_preview_ui_has_manual_refresh_and_no_preview_error_popup() -> None:
    root = Path(__file__).resolve().parents[1]
    html = (root / "web" / "index.html").read_text(encoding="utf-8")
    js = (root / "web" / "js" / "main.js").read_text(encoding="utf-8")
    css = (root / "web" / "css" / "styles.css").read_text(encoding="utf-8")

    assert 'id="refresh-preview-button"' in html
    assert "↻ Refresh" in html
    assert ".preview-refresh-button" in css
    assert 'byId("refresh-preview-button")' in js
    assert 'loadCurrentPreview({ manual: true })' in js

    preview_start = js.index("async function loadCurrentPreview")
    preview_end = js.index("async function openOutputFolder", preview_start)
    preview_function = js[preview_start:preview_end]
    assert "showErrorPopup" not in preview_function
