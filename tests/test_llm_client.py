"""Tests for LLMClient"""

import pytest
import json
from unittest.mock import patch, MagicMock
from trading_bot.llm_client import LLMClient, LLMConfig, LLMSignalDecision, LLMRegimeJudgment


class TestLLMClient:
    """LLMClient unit tests"""

    @pytest.fixture
    def config(self):
        return LLMConfig(
            signal_filter_url="http://localhost:8000/v1/chat/completions",
            regime_judge_url="http://localhost:8001/v1/chat/completions",
            enabled=True,
            timeout=5.0
        )

    @pytest.fixture
    def client(self, config):
        return LLMClient(config)

    @pytest.fixture
    def signal_context(self):
        return {
            'signal': 1,
            'symbol': 'AAPL',
            'strategy': 'RSI Strategy',
            'indicators': {'rsi': 28.5, 'price': 150.25},
            'regime': {'regime': 'BULLISH', 'confidence': 0.82, 'adx': 32.1},
            'position_info': {'current_positions': 2, 'capital_pct_used': 0.6}
        }

    @pytest.fixture
    def regime_context(self):
        return {
            'statistical_regime': {'regime': 'SIDEWAYS', 'adx': 18.5, 'volatility_percentile': 45.0},
            'market_data': {'recent_returns': [0.01, -0.02, 0.005], 'volume_trend': 'declining'},
            'active_strategies': ['RSI Strategy', 'Bollinger Bands']
        }

    def _mock_response(self, json_content: dict, status_code=200):
        """Helper to create mock response"""
        mock_resp = MagicMock()
        mock_resp.status_code = status_code
        mock_resp.json.return_value = {
            'choices': [{
                'message': {
                    'content': json.dumps(json_content)
                }
            }]
        }
        mock_resp.raise_for_status = MagicMock()
        return mock_resp

    def _mock_response_text(self, text: str, status_code=200):
        """Helper to create mock response with raw text"""
        mock_resp = MagicMock()
        mock_resp.status_code = status_code
        mock_resp.json.return_value = {
            'choices': [{
                'message': {
                    'content': text
                }
            }]
        }
        mock_resp.raise_for_status = MagicMock()
        return mock_resp

    # --- filter_signal tests ---

    @patch('trading_bot.llm_client.requests.post')
    def test_filter_signal_execute(self, mock_post, client, signal_context):
        mock_post.return_value = self._mock_response({
            'action': 'execute',
            'confidence': 0.85,
            'position_size_adj': 1.0,
            'reasoning': 'RSI oversold in bullish regime'
        })

        result = client.filter_signal(signal_context)
        assert result is not None
        assert isinstance(result, LLMSignalDecision)
        assert result.action == 'execute'
        assert result.confidence == 0.85
        assert result.position_size_adj == 1.0
        assert 'RSI' in result.reasoning

    @patch('trading_bot.llm_client.requests.post')
    def test_filter_signal_reject(self, mock_post, client, signal_context):
        mock_post.return_value = self._mock_response({
            'action': 'reject',
            'confidence': 0.72,
            'position_size_adj': 0.0,
            'reasoning': 'Conflicting signals'
        })

        result = client.filter_signal(signal_context)
        assert result.action == 'reject'

    @patch('trading_bot.llm_client.requests.post')
    def test_filter_signal_hold(self, mock_post, client, signal_context):
        mock_post.return_value = self._mock_response({
            'action': 'hold',
            'confidence': 0.60,
            'position_size_adj': 1.0,
            'reasoning': 'Wait for confirmation'
        })

        result = client.filter_signal(signal_context)
        assert result.action == 'hold'

    @patch('trading_bot.llm_client.requests.post')
    def test_filter_signal_timeout(self, mock_post, client, signal_context):
        """Timeout should return None (fail-open)"""
        import requests as req
        mock_post.side_effect = req.exceptions.Timeout("timeout")

        result = client.filter_signal(signal_context)
        assert result is None

    @patch('trading_bot.llm_client.requests.post')
    def test_filter_signal_connection_error(self, mock_post, client, signal_context):
        """Connection error should return None (fail-open)"""
        import requests as req
        mock_post.side_effect = req.exceptions.ConnectionError("refused")

        result = client.filter_signal(signal_context)
        assert result is None

    @patch('trading_bot.llm_client.requests.post')
    def test_filter_signal_server_error(self, mock_post, client, signal_context):
        """Server error should return None (fail-open)"""
        mock_resp = MagicMock()
        mock_resp.raise_for_status.side_effect = Exception("500 Server Error")
        mock_post.return_value = mock_resp

        result = client.filter_signal(signal_context)
        assert result is None

    def test_filter_signal_disabled(self, signal_context):
        """Disabled client should return None without making request"""
        config = LLMConfig(enabled=False)
        client = LLMClient(config)
        result = client.filter_signal(signal_context)
        assert result is None

    @patch('trading_bot.llm_client.requests.post')
    def test_filter_signal_invalid_action(self, mock_post, client, signal_context):
        """Invalid action should default to 'execute'"""
        mock_post.return_value = self._mock_response({
            'action': 'invalid_action',
            'confidence': 0.5,
            'position_size_adj': 1.0,
            'reasoning': 'test'
        })

        result = client.filter_signal(signal_context)
        assert result.action == 'execute'

    # --- judge_regime tests ---

    @patch('trading_bot.llm_client.requests.post')
    def test_judge_regime_agree(self, mock_post, client, regime_context):
        mock_post.return_value = self._mock_response({
            'regime_override': None,
            'confidence': 0.78,
            'analysis': 'Statistical regime looks correct',
            'strategy_recommendation': ['RSI Strategy']
        })

        result = client.judge_regime(regime_context)
        assert result is not None
        assert isinstance(result, LLMRegimeJudgment)
        assert result.regime_override is None
        assert result.confidence == 0.78

    @patch('trading_bot.llm_client.requests.post')
    def test_judge_regime_override(self, mock_post, client, regime_context):
        mock_post.return_value = self._mock_response({
            'regime_override': 'BEARISH',
            'confidence': 0.65,
            'analysis': 'Market showing bearish divergence',
            'strategy_recommendation': ['RSI Strategy', 'Bollinger Bands']
        })

        result = client.judge_regime(regime_context)
        assert result.regime_override == 'BEARISH'

    @patch('trading_bot.llm_client.requests.post')
    def test_judge_regime_timeout(self, mock_post, client, regime_context):
        import requests as req
        mock_post.side_effect = req.exceptions.Timeout("timeout")

        result = client.judge_regime(regime_context)
        assert result is None

    def test_judge_regime_disabled(self, regime_context):
        config = LLMConfig(enabled=False)
        client = LLMClient(config)
        result = client.judge_regime(regime_context)
        assert result is None

    # --- _extract_json tests ---

    def test_extract_json_raw(self, client):
        text = '{"action": "execute", "confidence": 0.9}'
        result = client._extract_json(text)
        assert result == {"action": "execute", "confidence": 0.9}

    def test_extract_json_markdown_block(self, client):
        text = '```json\n{"action": "hold", "confidence": 0.6}\n```'
        result = client._extract_json(text)
        assert result == {"action": "hold", "confidence": 0.6}

    def test_extract_json_markdown_block_no_lang(self, client):
        text = '```\n{"action": "reject"}\n```'
        result = client._extract_json(text)
        assert result == {"action": "reject"}

    def test_extract_json_with_surrounding_text(self, client):
        text = 'Here is my analysis:\n{"action": "execute", "confidence": 0.8}\nThat is my answer.'
        result = client._extract_json(text)
        assert result['action'] == 'execute'

    def test_extract_json_empty(self, client):
        assert client._extract_json('') is None
        assert client._extract_json('   ') is None
        assert client._extract_json(None) is None

    def test_extract_json_invalid(self, client):
        assert client._extract_json('not json at all') is None

    # --- health_check tests ---

    @patch('trading_bot.llm_client.requests.get')
    def test_health_check_both_up(self, mock_get, client):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_get.return_value = mock_resp

        result = client.health_check()
        assert result['signal_filter'] is True
        assert result['regime_judge'] is True

    @patch('trading_bot.llm_client.requests.get')
    def test_health_check_one_down(self, mock_get, client):
        def side_effect(url, **kwargs):
            if '8001' in url:
                resp = MagicMock()
                resp.status_code = 200
                return resp
            raise ConnectionError("refused")

        mock_get.side_effect = side_effect

        result = client.health_check()
        # signal_filter is on port 8000 (refused), regime_judge is on port 8001 (up)
        assert result['signal_filter'] is False
        assert result['regime_judge'] is True

    @patch('trading_bot.llm_client.requests.get')
    def test_health_check_both_down(self, mock_get, client):
        mock_get.side_effect = ConnectionError("refused")

        result = client.health_check()
        assert result['signal_filter'] is False
        assert result['regime_judge'] is False

    # --- LLMConfig tests ---

    def test_config_defaults(self):
        config = LLMConfig()
        assert '192.168.45.222:8080' in config.base_url
        assert config.signal_filter_url == ''
        assert config.regime_judge_url == ''
        assert config.enabled is True
        assert config.signal_timeout == 5.0
        assert config.regime_timeout == 15.0
        assert config.temperature == 0.1

    @patch.dict('os.environ', {'LLM_ENABLED': 'false'})
    def test_config_env_override_disabled(self):
        client = LLMClient(LLMConfig())
        assert client.config.enabled is False

    @patch.dict('os.environ', {'LLM_SIGNAL_URL': 'http://custom:9000/v1/chat/completions'})
    def test_config_env_override_url(self):
        client = LLMClient(LLMConfig())
        assert client.config.signal_filter_url == 'http://custom:9000/v1/chat/completions'

    # --- Markdown code block response test ---

    @patch('trading_bot.llm_client.requests.post')
    def test_filter_signal_markdown_response(self, mock_post, client, signal_context):
        """Test handling of markdown-wrapped JSON response from LLM"""
        text = '```json\n{"action": "execute", "confidence": 0.9, "position_size_adj": 1.2, "reasoning": "Strong signal"}\n```'
        mock_post.return_value = self._mock_response_text(text)

        result = client.filter_signal(signal_context)
        assert result is not None
        assert result.action == 'execute'
        assert result.confidence == 0.9
