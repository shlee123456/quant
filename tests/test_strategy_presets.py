"""
Tests for StrategyPresetManager

Covers save, load, list, delete, rename, get_recent, export, import.
Uses temporary files to avoid polluting data/.
"""

import json
import os
import pytest

from trading_bot.strategy_presets import StrategyPresetManager


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def preset_file(tmp_path):
    """Temporary presets JSON file path."""
    return str(tmp_path / "presets.json")


@pytest.fixture
def manager(preset_file):
    """StrategyPresetManager backed by a temp file."""
    return StrategyPresetManager(presets_file=preset_file)


def _save_sample(mgr, name="Test RSI", strategy="RSI Strategy",
                 params=None, symbols=None):
    """Helper to save a preset with defaults."""
    return mgr.save_preset(
        name=name,
        strategy=strategy,
        strategy_params=params or {"period": 14, "overbought": 70, "oversold": 30},
        symbols=symbols or ["AAPL"],
        initial_capital=10000.0,
        position_size=0.3,
        description="test preset",
    )


# ---------------------------------------------------------------------------
# Initialization
# ---------------------------------------------------------------------------

class TestInit:

    def test_creates_file_on_init(self, preset_file):
        StrategyPresetManager(presets_file=preset_file)
        assert os.path.exists(preset_file)

    def test_creates_directory_if_needed(self, tmp_path):
        deep_path = str(tmp_path / "a" / "b" / "presets.json")
        StrategyPresetManager(presets_file=deep_path)
        assert os.path.exists(deep_path)

    def test_empty_presets_on_init(self, manager):
        presets = manager.list_presets()
        assert presets == []


# ---------------------------------------------------------------------------
# save_preset
# ---------------------------------------------------------------------------

class TestSavePreset:

    def test_save_new_preset(self, manager):
        result = _save_sample(manager)
        assert result is True
        presets = manager.list_presets()
        assert len(presets) == 1
        assert presets[0]["name"] == "Test RSI"

    def test_save_updates_existing(self, manager):
        _save_sample(manager, name="Dup")
        _save_sample(manager, name="Dup", params={"period": 20})
        presets = manager.list_presets()
        assert len(presets) == 1
        assert presets[0]["strategy_params"]["period"] == 20

    def test_save_preserves_created_at(self, manager):
        _save_sample(manager, name="Keep")
        first = manager.load_preset("Keep")
        created = first["created_at"]

        _save_sample(manager, name="Keep", params={"period": 21})
        second = manager.load_preset("Keep")
        assert second["created_at"] == created
        assert second["updated_at"] != created

    def test_save_empty_name_fails(self, manager):
        result = manager.save_preset(
            name="", strategy="RSI", strategy_params={}
        )
        assert result is False

    def test_save_whitespace_name_fails(self, manager):
        result = manager.save_preset(
            name="   ", strategy="RSI", strategy_params={}
        )
        assert result is False

    def test_save_multiple_presets(self, manager):
        _save_sample(manager, name="A")
        _save_sample(manager, name="B")
        _save_sample(manager, name="C")
        assert len(manager.list_presets()) == 3

    def test_save_with_all_fields(self, manager):
        result = manager.save_preset(
            name="Full",
            strategy="MACD Strategy",
            strategy_params={"fast": 12, "slow": 26},
            initial_capital=50000.0,
            position_size=0.5,
            symbols=["AAPL", "MSFT", "GOOGL"],
            stop_loss_pct=0.03,
            take_profit_pct=0.06,
            enable_stop_loss=True,
            enable_take_profit=True,
            description="full test",
        )
        assert result is True
        p = manager.load_preset("Full")
        assert p["initial_capital"] == 50000.0
        assert p["symbols"] == ["AAPL", "MSFT", "GOOGL"]
        assert p["stop_loss_pct"] == 0.03


# ---------------------------------------------------------------------------
# load_preset
# ---------------------------------------------------------------------------

class TestLoadPreset:

    def test_load_existing(self, manager):
        _save_sample(manager)
        preset = manager.load_preset("Test RSI")
        assert preset is not None
        assert preset["strategy"] == "RSI Strategy"

    def test_load_nonexistent(self, manager):
        preset = manager.load_preset("No Such Preset")
        assert preset is None

    def test_load_updates_last_used(self, manager):
        _save_sample(manager)
        preset = manager.load_preset("Test RSI")
        assert preset["last_used"] is not None


# ---------------------------------------------------------------------------
# list_presets
# ---------------------------------------------------------------------------

class TestListPresets:

    def test_list_empty(self, manager):
        assert manager.list_presets() == []

    def test_list_returns_all(self, manager):
        _save_sample(manager, name="A")
        _save_sample(manager, name="B")
        presets = manager.list_presets()
        names = [p["name"] for p in presets]
        assert "A" in names
        assert "B" in names


# ---------------------------------------------------------------------------
# delete_preset
# ---------------------------------------------------------------------------

class TestDeletePreset:

    def test_delete_existing(self, manager):
        _save_sample(manager, name="Del")
        result = manager.delete_preset("Del")
        assert result is True
        assert len(manager.list_presets()) == 0

    def test_delete_nonexistent(self, manager):
        result = manager.delete_preset("Nope")
        assert result is False

    def test_delete_preserves_others(self, manager):
        _save_sample(manager, name="Keep")
        _save_sample(manager, name="Delete")
        manager.delete_preset("Delete")
        presets = manager.list_presets()
        assert len(presets) == 1
        assert presets[0]["name"] == "Keep"


# ---------------------------------------------------------------------------
# rename_preset
# ---------------------------------------------------------------------------

class TestRenamePreset:

    def test_rename_success(self, manager):
        _save_sample(manager, name="Old")
        result = manager.rename_preset("Old", "New")
        assert result is True
        assert manager.load_preset("Old") is None
        assert manager.load_preset("New") is not None

    def test_rename_nonexistent(self, manager):
        result = manager.rename_preset("X", "Y")
        assert result is False

    def test_rename_to_existing_fails(self, manager):
        _save_sample(manager, name="A")
        _save_sample(manager, name="B")
        result = manager.rename_preset("A", "B")
        assert result is False

    def test_rename_empty_name_fails(self, manager):
        _save_sample(manager, name="A")
        result = manager.rename_preset("A", "")
        assert result is False

    def test_rename_whitespace_name_fails(self, manager):
        _save_sample(manager, name="A")
        result = manager.rename_preset("A", "   ")
        assert result is False


# ---------------------------------------------------------------------------
# get_recent_presets
# ---------------------------------------------------------------------------

class TestGetRecentPresets:

    def test_no_recent(self, manager):
        _save_sample(manager, name="NotUsed")
        # Not loaded yet, so no last_used
        assert manager.get_recent_presets() == []

    def test_recent_after_load(self, manager):
        _save_sample(manager, name="Used")
        manager.load_preset("Used")
        recent = manager.get_recent_presets()
        assert len(recent) == 1
        assert recent[0]["name"] == "Used"

    def test_limit_parameter(self, manager):
        for i in range(10):
            _save_sample(manager, name=f"P{i}")
            manager.load_preset(f"P{i}")
        recent = manager.get_recent_presets(limit=3)
        assert len(recent) == 3


# ---------------------------------------------------------------------------
# export_preset / import_preset
# ---------------------------------------------------------------------------

class TestExportImport:

    def test_export_success(self, manager, tmp_path):
        _save_sample(manager, name="Export")
        export_path = str(tmp_path / "exported.json")
        result = manager.export_preset("Export", export_path)
        assert result is True
        assert os.path.exists(export_path)

        with open(export_path, "r") as f:
            data = json.load(f)
        assert data["name"] == "Export"

    def test_export_nonexistent(self, manager, tmp_path):
        result = manager.export_preset("Nope", str(tmp_path / "x.json"))
        assert result is False

    def test_import_success(self, manager, tmp_path):
        # Create a preset file to import
        preset_data = {
            "name": "Imported",
            "strategy": "MACD Strategy",
            "strategy_params": {"fast": 12, "slow": 26, "signal": 9},
            "symbols": ["TSLA"],
        }
        import_path = str(tmp_path / "import.json")
        with open(import_path, "w") as f:
            json.dump(preset_data, f)

        result = manager.import_preset(import_path)
        assert result is True
        p = manager.load_preset("Imported")
        assert p is not None
        assert p["strategy"] == "MACD Strategy"

    def test_import_invalid_format(self, manager, tmp_path):
        bad_path = str(tmp_path / "bad.json")
        with open(bad_path, "w") as f:
            json.dump({"invalid": True}, f)
        result = manager.import_preset(bad_path)
        assert result is False

    def test_import_nonexistent_file(self, manager):
        result = manager.import_preset("/nonexistent/file.json")
        assert result is False

    def test_roundtrip_export_import(self, manager, tmp_path):
        """Export then import preserves data."""
        _save_sample(manager, name="RT", params={"period": 21})
        export_path = str(tmp_path / "rt.json")
        manager.export_preset("RT", export_path)

        # Create a new manager to import into
        mgr2 = StrategyPresetManager(str(tmp_path / "presets2.json"))
        mgr2.import_preset(export_path)
        p = mgr2.load_preset("RT")
        assert p is not None
        assert p["strategy_params"]["period"] == 21
