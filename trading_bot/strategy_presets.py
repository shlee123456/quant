"""
Strategy Preset Manager

전략 설정을 저장하고 불러오는 기능 제공

Usage:
    from trading_bot.strategy_presets import StrategyPresetManager

    manager = StrategyPresetManager()

    # 프리셋 저장
    manager.save_preset(
        name="보수적 RSI 전략",
        strategy="RSI Strategy",
        strategy_params={"period": 14, "overbought": 70, "oversold": 30},
        initial_capital=10000.0,
        position_size=0.3,
        symbols=["AAPL", "MSFT"],
        stop_loss_pct=0.03,
        take_profit_pct=0.06,
        enable_stop_loss=True,
        enable_take_profit=True
    )

    # 프리셋 불러오기
    preset = manager.load_preset("보수적 RSI 전략")

    # 모든 프리셋 조회
    all_presets = manager.list_presets()
"""

import json
import os
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Optional, Any


class StrategyPresetManager:
    """
    전략 프리셋 관리 클래스

    JSON 파일로 전략 설정을 저장하고 불러옴
    """

    def __init__(self, presets_file: str = "data/strategy_presets.json"):
        """
        Initialize preset manager

        Args:
            presets_file: Path to presets JSON file
        """
        self.presets_file = presets_file

        # Create data directory if not exists
        data_dir = os.path.dirname(presets_file)
        if data_dir and not os.path.exists(data_dir):
            os.makedirs(data_dir)

        # Initialize presets file if not exists
        if not os.path.exists(presets_file):
            self._save_to_file({"presets": []})

    def _load_from_file(self) -> Dict:
        """Load presets from JSON file"""
        try:
            with open(self.presets_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            print(f"Error loading presets: {e}")
            return {"presets": []}

    def _save_to_file(self, data: Dict):
        """Save presets to JSON file"""
        try:
            with open(self.presets_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
        except Exception as e:
            print(f"Error saving presets: {e}")

    def save_preset(
        self,
        name: str,
        strategy: str,
        strategy_params: Dict[str, Any],
        initial_capital: float = 10000.0,
        position_size: float = 0.95,
        symbols: Optional[List[str]] = None,
        stop_loss_pct: float = 0.05,
        take_profit_pct: float = 0.10,
        enable_stop_loss: bool = True,
        enable_take_profit: bool = True,
        description: str = "",
        limit_orders: Optional[List[Dict[str, Any]]] = None
    ) -> bool:
        """
        Save strategy preset

        Args:
            name: Preset name (must be unique)
            strategy: Strategy name (e.g., "RSI Strategy")
            strategy_params: Strategy parameters (e.g., {"period": 14})
            initial_capital: Initial capital
            position_size: Position size fraction
            symbols: List of trading symbols
            stop_loss_pct: Stop loss percentage
            take_profit_pct: Take profit percentage
            enable_stop_loss: Enable stop loss
            enable_take_profit: Enable take profit
            description: Optional description
            limit_orders: Optional list of limit order configs
                Each dict: {"symbol": "NVDA", "side": "buy", "price": 172.0,
                            "trigger_order": {"side": "sell", "price": 190.0}}

        Returns:
            True if saved successfully, False otherwise
        """
        if not name or not name.strip():
            print("Preset name cannot be empty")
            return False

        data = self._load_from_file()

        # Check if preset with same name already exists
        existing_preset = next((p for p in data['presets'] if p['name'] == name), None)

        preset = {
            "name": name,
            "strategy": strategy,
            "strategy_params": strategy_params,
            "initial_capital": initial_capital,
            "position_size": position_size,
            "symbols": symbols or [],
            "stop_loss_pct": stop_loss_pct,
            "take_profit_pct": take_profit_pct,
            "enable_stop_loss": enable_stop_loss,
            "enable_take_profit": enable_take_profit,
            "description": description,
            "limit_orders": limit_orders or [],
            "created_at": existing_preset.get("created_at") if existing_preset else datetime.now().isoformat(),
            "updated_at": datetime.now().isoformat(),
            "last_used": existing_preset.get("last_used") if existing_preset else None
        }

        if existing_preset:
            # Update existing preset
            data['presets'] = [p if p['name'] != name else preset for p in data['presets']]
        else:
            # Add new preset
            data['presets'].append(preset)

        self._save_to_file(data)
        return True

    def load_preset(self, name: str) -> Optional[Dict[str, Any]]:
        """
        Load preset by name

        Args:
            name: Preset name

        Returns:
            Preset dict if found, None otherwise
        """
        data = self._load_from_file()
        preset = next((p for p in data['presets'] if p['name'] == name), None)

        if preset:
            # Update last_used timestamp
            preset['last_used'] = datetime.now().isoformat()
            self._save_to_file(data)

        return preset

    def list_presets(self) -> List[Dict[str, Any]]:
        """
        List all presets

        Returns:
            List of preset dicts
        """
        data = self._load_from_file()
        return data['presets']

    def delete_preset(self, name: str) -> bool:
        """
        Delete preset by name

        Args:
            name: Preset name

        Returns:
            True if deleted successfully, False if not found
        """
        data = self._load_from_file()
        original_count = len(data['presets'])

        data['presets'] = [p for p in data['presets'] if p['name'] != name]

        if len(data['presets']) < original_count:
            self._save_to_file(data)
            return True

        return False

    def rename_preset(self, old_name: str, new_name: str) -> bool:
        """
        Rename preset

        Args:
            old_name: Current preset name
            new_name: New preset name

        Returns:
            True if renamed successfully, False otherwise
        """
        if not new_name or not new_name.strip():
            print("New preset name cannot be empty")
            return False

        data = self._load_from_file()

        # Check if new name already exists
        if any(p['name'] == new_name for p in data['presets']):
            print(f"Preset with name '{new_name}' already exists")
            return False

        # Find and rename
        preset = next((p for p in data['presets'] if p['name'] == old_name), None)

        if preset:
            preset['name'] = new_name
            preset['updated_at'] = datetime.now().isoformat()
            self._save_to_file(data)
            return True

        return False

    def get_recent_presets(self, limit: int = 5) -> List[Dict[str, Any]]:
        """
        Get recently used presets

        Args:
            limit: Maximum number of presets to return

        Returns:
            List of preset dicts sorted by last_used (most recent first)
        """
        data = self._load_from_file()
        presets = [p for p in data['presets'] if p.get('last_used')]

        # Sort by last_used descending
        presets.sort(key=lambda x: x.get('last_used', ''), reverse=True)

        return presets[:limit]

    def export_preset(self, name: str, export_path: str) -> bool:
        """
        Export preset to separate JSON file

        Args:
            name: Preset name
            export_path: Path to export file

        Returns:
            True if exported successfully, False otherwise
        """
        preset = self.load_preset(name)

        if not preset:
            print(f"Preset '{name}' not found")
            return False

        try:
            with open(export_path, 'w', encoding='utf-8') as f:
                json.dump(preset, f, indent=2, ensure_ascii=False)
            return True
        except Exception as e:
            print(f"Error exporting preset: {e}")
            return False

    def import_preset(self, import_path: str) -> bool:
        """
        Import preset from JSON file

        Args:
            import_path: Path to import file

        Returns:
            True if imported successfully, False otherwise
        """
        try:
            with open(import_path, 'r', encoding='utf-8') as f:
                preset = json.load(f)

            # Validate preset structure
            required_fields = ['name', 'strategy', 'strategy_params']
            if not all(field in preset for field in required_fields):
                print("Invalid preset file format")
                return False

            # Save as new preset
            return self.save_preset(
                name=preset['name'],
                strategy=preset['strategy'],
                strategy_params=preset['strategy_params'],
                initial_capital=preset.get('initial_capital', 10000.0),
                position_size=preset.get('position_size', 0.95),
                symbols=preset.get('symbols', []),
                stop_loss_pct=preset.get('stop_loss_pct', 0.05),
                take_profit_pct=preset.get('take_profit_pct', 0.10),
                enable_stop_loss=preset.get('enable_stop_loss', True),
                enable_take_profit=preset.get('enable_take_profit', True),
                description=preset.get('description', ''),
                limit_orders=preset.get('limit_orders', [])
            )
        except Exception as e:
            print(f"Error importing preset: {e}")
            return False
