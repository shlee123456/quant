"""
LLM Client for Trading Signal Filtering and Regime Judgment

Connects to llm-server FastAPI gateway (인터페이스 정의서 참조):
- POST /v1/signal-filter: 시그널 필터 (Qwen2.5-7B-AWQ)
- POST /v1/regime-judgment: 레짐 판단 (Qwen2.5-14B-AWQ)
- GET /v1/health: 서비스 상태 확인

하위 호환: LLM_SIGNAL_URL / LLM_REGIME_URL 설정 시 vLLM 직접 호출 (마이그레이션 전)

Design principles:
- Fail-open: LLM errors → original signal passes through unchanged
- No openai SDK: uses requests directly (minimal dependencies)
- JSON-only responses from LLM, with fallback parsing
"""

import os
import json
import re
import logging
import time
from dataclasses import dataclass, field
from typing import Dict, Optional, Any, List
import requests

logger = logging.getLogger(__name__)


@dataclass
class LLMConfig:
    # FastAPI 게이트웨이 (인터페이스 정의서 기준)
    base_url: str = "http://192.168.45.222:8080"
    # 하위 호환: vLLM 직접 호출 URL (마이그레이션 완료 후 제거)
    signal_filter_url: str = ""
    regime_judge_url: str = ""
    signal_model_name: str = "Qwen/Qwen2.5-7B-Instruct-AWQ"
    regime_model_name: str = "Qwen/Qwen2.5-14B-Instruct-AWQ"
    signal_timeout: float = 5.0
    regime_timeout: float = 15.0
    timeout: float = 10.0  # 하위 호환 (레거시)
    temperature: float = 0.1
    max_tokens: int = 500
    enabled: bool = True


@dataclass
class LLMSignalDecision:
    action: str  # "execute", "hold", "reject"
    confidence: float  # 0.0 ~ 1.0
    position_size_adj: float  # multiplier, 0.5~1.0 (축소만 허용, 의사결정 Issue 1)
    reasoning: str


@dataclass
class LLMRegimeJudgment:
    regime_override: Optional[str]  # None = agree with statistical, or "BULLISH"/"BEARISH"/etc
    confidence: float
    analysis: str
    strategy_recommendation: List[str]


class LLMClient:
    """Client for llm-server FastAPI gateway (or direct vLLM for backward compat)"""

    def __init__(self, config: Optional[LLMConfig] = None):
        if config is None:
            config = LLMConfig()
        self.config = config

        # Allow env var overrides
        self.config.base_url = os.getenv('LLM_BASE_URL', self.config.base_url)

        # 하위 호환: LLM_SIGNAL_URL / LLM_REGIME_URL이 설정되면 vLLM 직접 호출 모드
        self.config.signal_filter_url = os.getenv('LLM_SIGNAL_URL', self.config.signal_filter_url)
        self.config.regime_judge_url = os.getenv('LLM_REGIME_URL', self.config.regime_judge_url)

        # 개별 타임아웃
        signal_timeout = os.getenv('LLM_SIGNAL_TIMEOUT')
        if signal_timeout:
            self.config.signal_timeout = float(signal_timeout)
        regime_timeout = os.getenv('LLM_REGIME_TIMEOUT')
        if regime_timeout:
            self.config.regime_timeout = float(regime_timeout)

        enabled_env = os.getenv('LLM_ENABLED')
        if enabled_env is not None:
            self.config.enabled = enabled_env.lower() in ('true', '1', 'yes')

        # 모드 결정: vLLM 직접 호출 vs FastAPI 게이트웨이
        self._use_direct_vllm = bool(self.config.signal_filter_url or self.config.regime_judge_url)
        if self._use_direct_vllm:
            logger.info(f"LLM Client: vLLM 직접 호출 모드 (signal={self.config.signal_filter_url}, regime={self.config.regime_judge_url})")
        else:
            logger.info(f"LLM Client: FastAPI 게이트웨이 모드 ({self.config.base_url})")

    def filter_signal(self, signal_context: Dict) -> Optional[LLMSignalDecision]:
        """
        Ask 7B model to filter/validate a trading signal

        Args:
            signal_context: Dict with keys:
                - signal: int (1=BUY, -1=SELL)
                - symbol: str
                - strategy: str
                - indicators: dict
                - regime: dict (from RegimeDetector)
                - position_info: dict

        Returns:
            LLMSignalDecision or None on error (fail-open)
        """
        if not self.config.enabled:
            return None

        signal_word = "BUY" if signal_context.get('signal', 0) == 1 else "SELL"

        try:
            if self._use_direct_vllm:
                response = self._filter_signal_direct(signal_context, signal_word)
            else:
                response = self._filter_signal_gateway(signal_context, signal_word)

            if response is None:
                return None

            # Validate and parse response
            action = response.get('action', 'execute')
            if action not in ('execute', 'hold', 'reject'):
                action = 'execute'

            # 의사결정 Issue 1: position_size_adj 0.5~1.0 (축소만 허용)
            raw_adj = float(response.get('position_size_adj', 1.0))
            clamped_adj = max(0.5, min(1.0, raw_adj))

            return LLMSignalDecision(
                action=action,
                confidence=float(response.get('confidence', 0.5)),
                position_size_adj=clamped_adj,
                reasoning=str(response.get('reasoning', ''))
            )

        except Exception as e:
            logger.warning(f"LLM signal filter error (fail-open): {e}")
            return None

    def _filter_signal_gateway(self, signal_context: Dict, signal_word: str) -> Optional[Dict]:
        """FastAPI 게이트웨이 경유 시그널 필터 (인터페이스 정의서 POST /v1/signal-filter)"""
        url = f"{self.config.base_url}/v1/signal-filter"
        payload = {
            'signal': signal_word,
            'symbol': signal_context.get('symbol', ''),
            'strategy': signal_context.get('strategy', ''),
            'indicators': signal_context.get('indicators', {}),
            'regime': signal_context.get('regime', {}),
            'position_info': signal_context.get('position_info', {}),
        }
        return self._call_gateway(url, payload, self.config.signal_timeout)

    def _filter_signal_direct(self, signal_context: Dict, signal_word: str) -> Optional[Dict]:
        """vLLM 직접 호출 시그널 필터 (하위 호환, 마이그레이션 후 제거)"""
        system_msg = (
            "You are a trading signal filter. Analyze the given signal context and decide whether to "
            "execute, hold, or reject the signal. Respond ONLY with a JSON object, no other text.\n"
            "Format: {\"action\": \"execute|hold|reject\", \"confidence\": 0.0-1.0, "
            "\"position_size_adj\": 0.5-1.0, \"reasoning\": \"brief explanation\"}"
        )

        user_msg = json.dumps({
            'signal': signal_word,
            'symbol': signal_context.get('symbol', ''),
            'strategy': signal_context.get('strategy', ''),
            'indicators': signal_context.get('indicators', {}),
            'regime': signal_context.get('regime', {}),
            'position_info': signal_context.get('position_info', {}),
        }, ensure_ascii=False, default=str)

        messages = [
            {"role": "system", "content": system_msg},
            {"role": "user", "content": user_msg}
        ]

        return self._call_llm(
            self.config.signal_filter_url,
            messages,
            self.config.signal_model_name
        )

    def judge_regime(self, regime_context: Dict) -> Optional[LLMRegimeJudgment]:
        """
        Ask 14B model to judge/enhance statistical regime detection

        Args:
            regime_context: Dict with keys:
                - statistical_regime: dict (from RegimeDetector)
                - market_data: dict (recent returns, volume trend, etc)
                - active_strategies: list of strategy names

        Returns:
            LLMRegimeJudgment or None on error
        """
        if not self.config.enabled:
            return None

        try:
            if self._use_direct_vllm:
                response = self._judge_regime_direct(regime_context)
            else:
                response = self._judge_regime_gateway(regime_context)

            if response is None:
                return None

            return LLMRegimeJudgment(
                regime_override=response.get('regime_override'),
                confidence=float(response.get('confidence', 0.5)),
                analysis=str(response.get('analysis', '')),
                strategy_recommendation=list(response.get('strategy_recommendation', []))
            )

        except Exception as e:
            logger.warning(f"LLM regime judge error: {e}")
            return None

    def _judge_regime_gateway(self, regime_context: Dict) -> Optional[Dict]:
        """FastAPI 게이트웨이 경유 레짐 판단 (인터페이스 정의서 POST /v1/regime-judgment)"""
        url = f"{self.config.base_url}/v1/regime-judgment"
        return self._call_gateway(url, regime_context, self.config.regime_timeout)

    def _judge_regime_direct(self, regime_context: Dict) -> Optional[Dict]:
        """vLLM 직접 호출 레짐 판단 (하위 호환, 마이그레이션 후 제거)"""
        system_msg = (
            "You are a market regime analyst. Analyze the statistical regime detection and market data, "
            "then provide your judgment. Respond ONLY with a JSON object, no other text.\n"
            "Format: {\"regime_override\": null or \"BULLISH\"|\"BEARISH\"|\"SIDEWAYS\"|\"VOLATILE\", "
            "\"confidence\": 0.0-1.0, \"analysis\": \"detailed analysis\", "
            "\"strategy_recommendation\": [\"strategy1\", \"strategy2\"]}"
        )

        user_msg = json.dumps(regime_context, ensure_ascii=False, default=str)

        messages = [
            {"role": "system", "content": system_msg},
            {"role": "user", "content": user_msg}
        ]

        return self._call_llm(
            self.config.regime_judge_url,
            messages,
            self.config.regime_model_name
        )

    def _call_gateway(self, url: str, payload: Dict, timeout: float) -> Optional[Dict]:
        """
        Call llm-server FastAPI gateway endpoint

        Returns parsed JSON dict or None on error.
        Gateway returns structured JSON directly (no prompt/parsing needed).
        """
        try:
            start_time = time.time()
            resp = requests.post(
                url,
                json=payload,
                timeout=timeout
            )
            latency_ms = (time.time() - start_time) * 1000

            resp.raise_for_status()

            data = resp.json()
            logger.debug(f"Gateway response ({latency_ms:.0f}ms) from {url}")

            # Gateway already returns structured JSON
            if '_latency_ms' not in data:
                data['_latency_ms'] = latency_ms
            return data

        except requests.exceptions.Timeout:
            logger.warning(f"Gateway request timed out ({timeout}s): {url}")
            return None
        except requests.exceptions.ConnectionError:
            logger.warning(f"Gateway server unreachable: {url}")
            return None
        except Exception as e:
            logger.warning(f"Gateway request failed: {e}")
            return None

    def _call_llm(self, url: str, messages: list, model_name: str) -> Optional[Dict]:
        """
        Call vLLM OpenAI-compatible chat completions API (하위 호환)

        Returns parsed JSON dict or None on error
        """
        payload = {
            "model": model_name,
            "messages": messages,
            "temperature": self.config.temperature,
            "max_tokens": self.config.max_tokens,
        }

        try:
            start_time = time.time()
            resp = requests.post(
                url,
                json=payload,
                timeout=self.config.timeout
            )
            latency_ms = (time.time() - start_time) * 1000

            resp.raise_for_status()

            data = resp.json()
            content = data['choices'][0]['message']['content']

            logger.debug(f"LLM response ({latency_ms:.0f}ms): {content[:200]}")

            parsed = self._extract_json(content)
            if parsed is not None:
                parsed['_latency_ms'] = latency_ms
            return parsed

        except requests.exceptions.Timeout:
            logger.warning(f"LLM request timed out ({self.config.timeout}s): {url}")
            return None
        except requests.exceptions.ConnectionError:
            logger.warning(f"LLM server unreachable: {url}")
            return None
        except Exception as e:
            logger.warning(f"LLM request failed: {e}")
            return None

    def _extract_json(self, text: str) -> Optional[Dict]:
        """
        Extract JSON from LLM response text

        Handles:
        - Raw JSON: {"key": "value"}
        - Markdown code block: ```json\\n{...}\\n```
        - Markdown code block without language: ```\\n{...}\\n```
        """
        if not text or not text.strip():
            return None

        text = text.strip()

        # Try 1: Direct JSON parse
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass

        # Try 2: Extract from markdown code block
        code_block_pattern = r'```(?:json)?\s*\n?(.*?)\n?\s*```'
        match = re.search(code_block_pattern, text, re.DOTALL)
        if match:
            try:
                return json.loads(match.group(1).strip())
            except json.JSONDecodeError:
                pass

        # Try 3: Find first { ... } in text
        brace_start = text.find('{')
        brace_end = text.rfind('}')
        if brace_start != -1 and brace_end != -1 and brace_end > brace_start:
            try:
                return json.loads(text[brace_start:brace_end + 1])
            except json.JSONDecodeError:
                pass

        logger.warning(f"Failed to extract JSON from LLM response: {text[:200]}")
        return None

    def health_check(self) -> Dict[str, bool]:
        """
        Check health of LLM servers

        Returns dict like: {"signal_filter": True, "regime_judge": False}
        """
        if not self._use_direct_vllm:
            return self._health_check_gateway()
        return self._health_check_direct()

    def _health_check_gateway(self) -> Dict[str, bool]:
        """FastAPI 게이트웨이 헬스체크 (GET /v1/health)"""
        try:
            resp = requests.get(f"{self.config.base_url}/v1/health", timeout=3)
            if resp.status_code != 200:
                return {"signal_filter": False, "regime_judge": False}
            data = resp.json()
            models = data.get('models', {})
            # 인터페이스 정의서 v1.1: 키 이름 signal_7b / regime_14b
            return {
                "signal_filter": models.get('signal_7b', {}).get('status') == 'healthy',
                "regime_judge": models.get('regime_14b', {}).get('status') == 'healthy',
            }
        except Exception:
            return {"signal_filter": False, "regime_judge": False}

    def _health_check_direct(self) -> Dict[str, bool]:
        """vLLM 직접 헬스체크 (하위 호환)"""
        results = {}

        for name, url in [
            ("signal_filter", self.config.signal_filter_url),
            ("regime_judge", self.config.regime_judge_url)
        ]:
            try:
                base_url = url.rsplit('/v1/', 1)[0]
                resp = requests.get(f"{base_url}/v1/models", timeout=3)
                results[name] = resp.status_code == 200
            except Exception:
                results[name] = False

        return results
