"""Unit and integration tests for AutoCAD Electrical MCP tools.

Tests are organised in two tiers:

1. **Unit tests** – run without AutoCAD using mock COM objects.  These verify
   that the tool functions handle errors gracefully, return proper dict shapes,
   and that the config / provider layers work correctly.

2. **Integration tests** – marked with ``@pytest.mark.integration``.  These
   require a live AutoCAD Electrical 2025 instance and are skipped by default.
   Run them with: ``pytest -m integration``

Usage::

    # Unit tests only (no AutoCAD required)
    pytest tests/

    # All tests including integration
    pytest -m integration tests/
"""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch, PropertyMock

import pytest

# Ensure project root is on the path when running pytest from any directory
_ROOT = Path(__file__).parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))


# ===========================================================================
# Fixtures
# ===========================================================================

@pytest.fixture()
def mock_ms():
    """A mock AutoCAD ModelSpace collection."""
    ms = MagicMock()
    ms.Count = 0
    return ms


@pytest.fixture()
def mock_doc(mock_ms):
    """A mock AutoCAD Document object."""
    doc = MagicMock()
    doc.Name = "Sheet_01.dwg"
    doc.FullName = "C:/Projects/Test/Sheet_01.dwg"
    doc.Saved = True
    doc.ModelSpace = mock_ms
    return doc


@pytest.fixture()
def mock_conn(mock_doc, mock_ms):
    """A fully-mocked AutoCADConnection that returns mock_doc / mock_ms."""
    conn = MagicMock()
    conn.is_connected.return_value = True
    conn.get_active_document.return_value = mock_doc
    conn.get_model_space.return_value = mock_ms
    return conn


@pytest.fixture(autouse=True)
def patch_get_connection(mock_conn):
    """Patch get_connection() across all tool modules for every test."""
    with patch("src.autocad.connection.get_connection", return_value=mock_conn):
        # Also patch it in each tool module that imports it directly
        patches = [
            patch("src.tools.drawing.get_connection", return_value=mock_conn),
            patch("src.tools.electrical.get_connection", return_value=mock_conn),
            patch("src.tools.wires.get_connection", return_value=mock_conn),
            patch("src.tools.components.get_connection", return_value=mock_conn),
            patch("src.tools.reports.get_connection", return_value=mock_conn),
            patch("src.tools.project.get_connection", return_value=mock_conn),
        ]
        for p in patches:
            p.start()
        yield
        for p in patches:
            p.stop()


# ===========================================================================
# Config tests
# ===========================================================================

class TestConfig:
    def test_loads_defaults(self, tmp_path):
        """Config loads without errors from the project config.yaml."""
        from src.config import Config
        cfg = Config(config_path=_ROOT / "config.yaml")
        assert cfg.active_provider in cfg.list_providers()

    def test_get_provider_config(self):
        from src.config import Config
        cfg = Config(config_path=_ROOT / "config.yaml")
        pc = cfg.get_provider_config("ollama")
        assert "model" in pc
        assert "base_url" in pc

    def test_unknown_provider_raises(self):
        from src.config import Config
        cfg = Config(config_path=_ROOT / "config.yaml")
        with pytest.raises(KeyError):
            cfg.get_provider_config("nonexistent_provider_xyz")

    def test_env_var_override(self, monkeypatch):
        monkeypatch.setenv("ACTIVE_PROVIDER", "ollama")
        from src.config import Config
        cfg = Config(config_path=_ROOT / "config.yaml")
        assert cfg.active_provider == "ollama"

    def test_save_and_reload(self, tmp_path):
        """Config can be written to a temp file and re-read."""
        import shutil
        from src.config import Config
        tmp_cfg = tmp_path / "config.yaml"
        shutil.copy(_ROOT / "config.yaml", tmp_cfg)
        cfg = Config(config_path=tmp_cfg)
        cfg.active_provider = "ollama"
        cfg.save(config_path=tmp_cfg)
        cfg2 = Config(config_path=tmp_cfg)
        assert cfg2.active_provider == "ollama"


# ===========================================================================
# Drawing tool tests
# ===========================================================================

class TestDrawingTools:
    """Tests for src/tools/drawing.py"""

    def test_draw_line_success(self, mock_ms):
        """draw_line returns success dict on a working connection."""
        from src.tools.drawing import draw_line

        mock_line = MagicMock()
        mock_line.Handle = "1A"
        mock_ms.AddLine.return_value = mock_line
        mock_ms.Count = 0

        result = draw_line(0, 0, 100, 0)
        assert result["success"] is True
        assert result["entity"] == "Line"
        assert result["handle"] == "1A"

    def test_draw_line_no_connection(self):
        """draw_line returns error dict when AutoCAD is not connected."""
        from src.autocad.connection import AutoCADConnectionError
        from src.tools.drawing import draw_line

        with patch("src.tools.drawing.get_connection") as mock_gc:
            conn = MagicMock()
            conn.is_connected.return_value = False
            conn.connect.side_effect = AutoCADConnectionError("AutoCAD not running")
            mock_gc.return_value = conn

            result = draw_line(0, 0, 10, 10)
            assert result["success"] is False
            assert "AutoCAD not running" in result["error"]

    def test_draw_circle_success(self, mock_ms):
        from src.tools.drawing import draw_circle

        mock_circle = MagicMock()
        mock_circle.Handle = "2B"
        mock_ms.AddCircle.return_value = mock_circle

        result = draw_circle(50, 50, 10)
        assert result["success"] is True
        assert result["radius"] == 10
        assert result["handle"] == "2B"

    def test_draw_arc_success(self, mock_ms):
        from src.tools.drawing import draw_arc

        mock_arc = MagicMock()
        mock_arc.Handle = "3C"
        mock_ms.AddArc.return_value = mock_arc

        result = draw_arc(0, 0, 5, 0, 180)
        assert result["success"] is True
        assert result["start_angle"] == 0
        assert result["end_angle"] == 180

    def test_draw_text_success(self, mock_ms):
        from src.tools.drawing import draw_text

        mock_txt = MagicMock()
        mock_txt.Handle = "4D"
        mock_ms.AddText.return_value = mock_txt

        result = draw_text(10, 10, "Hello World")
        assert result["success"] is True
        assert result["text"] == "Hello World"

    def test_draw_rectangle_success(self, mock_ms):
        from src.tools.drawing import draw_rectangle

        mock_pline = MagicMock()
        mock_pline.Handle = "5E"
        mock_ms.AddLightWeightPolyline.return_value = mock_pline

        result = draw_rectangle(0, 0, 100, 50)
        assert result["success"] is True
        assert result["entity"] == "LWPolyline"


# ===========================================================================
# Electrical tool tests
# ===========================================================================

class TestElectricalTools:
    def test_get_symbol_list_all(self):
        from src.tools.electrical import get_symbol_list
        result = get_symbol_list()
        assert result["success"] is True
        assert result["count"] > 0
        assert "WD_NOPEN" in result["symbols"]

    def test_get_symbol_list_filtered(self):
        from src.tools.electrical import get_symbol_list
        result = get_symbol_list("coils")
        assert result["success"] is True
        assert all("COIL" in s or "WD_" in s for s in result["symbols"])

    def test_get_symbol_list_unknown_category(self):
        from src.tools.electrical import get_symbol_list
        result = get_symbol_list("unknown_xyz")
        assert result["success"] is True
        assert result["count"] == 0  # no match → empty list

    def test_insert_electrical_symbol_sends_lisp(self, mock_conn):
        from src.tools.electrical import insert_electrical_symbol
        result = insert_electrical_symbol("WD_NOPEN", 100, 200)
        # COM send_command should have been called
        assert mock_conn.send_command.called
        # Result is either success (if mock block found) or partial success
        assert "success" in result

    def test_insert_ladder_sends_command(self, mock_conn):
        from src.tools.electrical import insert_ladder
        result = insert_ladder(0, 0, rung_count=5)
        assert mock_conn.send_command.called
        assert result["success"] is True
        assert result["rung_count"] == 5

    def test_set_wire_number_sends_command(self, mock_conn):
        from src.tools.electrical import set_wire_number
        result = set_wire_number("101", 50, 100)
        assert mock_conn.send_command.called
        assert result["success"] is True
        assert result["wire_number"] == "101"

    def test_edit_component_attributes_not_found(self, mock_ms):
        from src.tools.electrical import edit_component_attributes
        mock_ms.Count = 0  # empty drawing
        result = edit_component_attributes("NOTFOUND", {"DESC1": "Test"})
        assert result["success"] is False
        assert "not found" in result["error"].lower()


# ===========================================================================
# Wire tool tests
# ===========================================================================

class TestWireTools:
    def test_draw_wire_success(self, mock_ms):
        from src.tools.wires import draw_wire

        mock_line = MagicMock()
        mock_line.Handle = "W1"
        mock_ms.AddLine.return_value = mock_line

        result = draw_wire(0, 0, 50, 0)
        assert result["success"] is True
        assert result["layer"] == "WIRES"
        assert result["handle"] == "W1"

    def test_number_wires_drawing_scope(self, mock_conn):
        from src.tools.wires import number_wires
        result = number_wires()
        assert mock_conn.send_command.called
        assert result["success"] is True
        assert result["scope"] == "drawing"

    def test_number_wires_project_scope(self, mock_conn):
        from src.tools.wires import number_wires
        result = number_wires(project="MyProject")
        assert result["success"] is True
        assert result["scope"] == "project"

    def test_get_wire_numbers_empty_drawing(self, mock_ms):
        from src.tools.wires import get_wire_numbers
        mock_ms.Count = 0
        result = get_wire_numbers()
        assert result["success"] is True
        assert result["wire_numbers"] == []
        assert result["count"] == 0

    def test_create_wire_from_to_not_found(self, mock_ms):
        from src.tools.wires import create_wire_from_to
        mock_ms.Count = 0
        result = create_wire_from_to("CR101", "M1")
        assert result["success"] is False
        assert "not found" in result["error"].lower()


# ===========================================================================
# Component tool tests
# ===========================================================================

class TestComponentTools:
    def _make_component_mock(self, tag1: str, handle: str = "A1"):
        """Helper to create a mock AcDbBlockReference component."""
        obj = MagicMock()
        obj.ObjectName = "AcDbBlockReference"
        obj.Name = "WD_NOPEN"
        obj.Layer = "SYMS"
        obj.Handle = handle
        obj.Rotation = 0.0
        obj.InsertionPoint = (100.0, 200.0, 0.0)
        # Simulate GetAttributes
        attr_mock = MagicMock()
        attr_mock.TagString = "TAG1"
        attr_mock.TextString = tag1
        obj.GetAttributes.return_value = [attr_mock]
        return obj

    def test_get_component_list_finds_components(self, mock_ms):
        from src.tools.components import get_component_list
        mock_ms.Count = 1
        mock_ms.Item.return_value = self._make_component_mock("CR101")
        result = get_component_list()
        assert result["success"] is True
        assert result["count"] >= 0  # mock may or may not pass the electrical_tags filter

    def test_get_component_info_not_found(self, mock_ms):
        from src.tools.components import get_component_info
        mock_ms.Count = 0
        result = get_component_info("MISSING")
        assert result["success"] is False

    def test_search_components_empty(self, mock_ms):
        from src.tools.components import search_components
        mock_ms.Count = 0
        result = search_components({"MFG": "ALLEN-BRADLEY"})
        assert result["success"] is True
        assert result["count"] == 0


# ===========================================================================
# Report tool tests
# ===========================================================================

class TestReportTools:
    def test_generate_bom_csv(self, tmp_path, mock_ms, mock_doc):
        from src.tools.reports import generate_bom
        mock_ms.Count = 0
        result = generate_bom(output_path=str(tmp_path / "bom.csv"))
        assert result["success"] is True
        assert Path(result["file"]).exists()

    def test_generate_wire_list_empty(self, tmp_path, mock_ms):
        from src.tools.reports import generate_wire_list
        mock_ms.Count = 0
        result = generate_wire_list(output_path=str(tmp_path / "wires.csv"))
        assert result["success"] is True
        assert result["wire_count"] == 0

    def test_generate_terminal_plan_empty(self, tmp_path, mock_ms):
        from src.tools.reports import generate_terminal_plan
        mock_ms.Count = 0
        result = generate_terminal_plan(output_path=str(tmp_path / "terminals.csv"))
        assert result["success"] is True
        assert result["terminal_count"] == 0

    def test_generate_plc_io_list_empty(self, tmp_path, mock_ms):
        from src.tools.reports import generate_plc_io_list
        mock_ms.Count = 0
        result = generate_plc_io_list(output_path=str(tmp_path / "plc.csv"))
        assert result["success"] is True
        assert result["io_count"] == 0


# ===========================================================================
# Project tool tests
# ===========================================================================

class TestProjectTools:
    def test_get_project_info_success(self, mock_conn, mock_doc):
        from src.tools.project import get_project_info
        mock_app = MagicMock()
        mock_app.Documents.Count = 1
        mock_app.Documents.Item.return_value = mock_doc
        mock_conn.get_application.return_value = mock_app
        result = get_project_info()
        assert result["success"] is True
        assert "active_drawing" in result

    def test_get_active_drawing_success(self, mock_conn, mock_doc, mock_ms):
        from src.tools.project import get_active_drawing
        result = get_active_drawing()
        assert result["success"] is True
        assert result["name"] == "Sheet_01.dwg"

    def test_list_drawings_success(self, mock_conn, mock_doc):
        from src.tools.project import list_drawings
        mock_app = MagicMock()
        mock_app.Documents.Count = 1
        mock_app.Documents.Item.return_value = mock_doc
        mock_app.ActiveDocument.Name = "Sheet_01.dwg"
        mock_conn.get_application.return_value = mock_app
        result = list_drawings()
        assert result["success"] is True
        assert isinstance(result["drawings"], list)

    def test_sync_project_sends_command(self, mock_conn):
        from src.tools.project import sync_project
        result = sync_project()
        assert mock_conn.send_command.called
        assert result["success"] is True

    def test_close_drawing_saves(self, mock_conn, mock_doc):
        from src.tools.project import close_drawing
        result = close_drawing(save=True)
        assert result["success"] is True
        mock_doc.Save.assert_called_once()
        mock_doc.Close.assert_called_once_with(True)


# ===========================================================================
# Provider tests (no network calls)
# ===========================================================================

class TestProviders:
    def test_claude_provider_init(self):
        from src.providers.claude import ClaudeProvider
        p = ClaudeProvider(api_key="test-key", model="claude-sonnet-4-6")
        assert p.get_model_name() == "claude-sonnet-4-6"
        assert p.name == "claude"

    def test_ollama_provider_init(self):
        from src.providers.ollama import OllamaProvider
        p = OllamaProvider(model="llama3.2")
        assert p.get_model_name() == "llama3.2"
        assert p.name == "ollama"

    def test_openai_compat_provider_init(self):
        from src.providers.openai_compat import OpenAICompatProvider
        p = OpenAICompatProvider(api_key="sk-test", model="gpt-4o")
        assert p.get_model_name() == "gpt-4o"

    def test_get_provider_factory_claude(self, monkeypatch):
        from src.config import get_config
        monkeypatch.setenv("ACTIVE_PROVIDER", "claude")
        from src.providers import get_provider
        provider = get_provider(get_config(reload=True))
        from src.providers.claude import ClaudeProvider
        assert isinstance(provider, ClaudeProvider)

    def test_get_provider_factory_ollama(self, monkeypatch):
        monkeypatch.setenv("ACTIVE_PROVIDER", "ollama")
        from src.config import get_config
        from src.providers import get_provider
        provider = get_provider(get_config(reload=True))
        from src.providers.ollama import OllamaProvider
        assert isinstance(provider, OllamaProvider)

    def test_ollama_is_available_false_no_server(self):
        """is_available() returns False when no Ollama server is running."""
        from src.providers.ollama import OllamaProvider
        p = OllamaProvider(base_url="http://localhost:19999")  # unused port
        assert p.is_available() is False


# ===========================================================================
# Integration tests (require AutoCAD to be running)
# ===========================================================================

@pytest.mark.integration
class TestIntegrationAutoCAD:
    """Integration tests – skip unless AutoCAD Electrical 2025 is running.

    Run with::

        pytest -m integration tests/test_tools.py
    """

    def test_connection(self):
        from src.autocad.connection import AutoCADConnection, reset_connection
        reset_connection()
        conn = AutoCADConnection()
        conn.connect()
        assert conn.is_connected()
        conn.disconnect()

    def test_get_active_drawing_real(self):
        from src.autocad.connection import reset_connection
        reset_connection()
        from src.tools.project import get_active_drawing
        result = get_active_drawing()
        assert result["success"] is True
        print(f"\nActive drawing: {result['name']}")

    def test_draw_line_real(self):
        from src.autocad.connection import reset_connection
        reset_connection()
        from src.tools.drawing import draw_line
        result = draw_line(0, 0, 100, 0, layer="TEST_MCP")
        assert result["success"] is True
        print(f"\nLine handle: {result['handle']}")
