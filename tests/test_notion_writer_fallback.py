"""
Notion Writer Worker-C 폴백 로직 테스트

Worker-C (Haiku 모델, 섹션 6-8 담당) 실패 시 재시도 및 레거시 폴백이
올바르게 동작하는지 검증합니다.
"""

import json
import os
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch, call

import pytest

# 테스트 대상 모듈
from scripts.notion_writer import (
    run_parallel_notion_writer,
    _notify_worker_failure,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def sample_market_json(tmp_path):
    """최소 구조의 시장 분석 JSON 파일을 생성합니다."""
    data = {
        "BTC/USDT": {"close": 65000, "change_pct": 1.2},
        "ETH/USDT": {"close": 3500, "change_pct": -0.5},
        "news": {"articles": []},
        "fear_greed_index": {"value": 55, "label": "Neutral"},
    }
    json_path = tmp_path / "2026-03-03.json"
    json_path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    return str(json_path)


def _make_worker_result(success: bool, output: str = "", cost: float = 0.01):
    """run_claude_worker 반환 형식의 튜플을 만듭니다."""
    return (success, output, cost)


WORKER_A_OUTPUT = "# 1. 시장 요약\n내용\n# 2. 종목별 분석\n내용"
WORKER_B_OUTPUT = "# 3. Top 3\n내용\n# 4. 공포/탐욕\n내용\n# 5. 뉴스\n내용"
WORKER_C_OUTPUT = "# 6. 전략 파라미터\n내용\n# 7. 전방 전망\n내용\n# 8. 리스크\n내용"
NOTION_WRITER_OUTPUT = "페이지 작성 완료\nNOTION_PAGE_URL: https://www.notion.so/test-page-12345"


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestWorkerCRetryOnTimeout:
    """Worker-C 타임아웃/실패 시 재시도 동작 검증"""

    @patch("scripts.notion_writer._notify_worker_failure")
    @patch("scripts.notion_writer.run_claude_worker")
    @patch("scripts.notion_writer.build_notion_writer_prompt", return_value="notion_prompt")
    @patch("scripts.notion_writer.get_notion_page_id", return_value="test-page-id")
    @patch("scripts.notion_writer.validate_assembly", return_value=True)
    @patch("scripts.notion_writer.assemble_sections", return_value="assembled_content")
    @patch("scripts.notion_writer.build_worker_c_prompt", return_value="prompt_c")
    @patch("scripts.notion_writer.build_worker_b_prompt", return_value=("prompt_b", ["AAPL", "MSFT", "NVDA"]))
    @patch("scripts.notion_writer.build_worker_a_prompt", return_value="prompt_a")
    @patch("scripts.notion_writer.precompute_session_metrics", return_value=None)
    def test_worker_c_retry_succeeds(
        self, mock_precompute, mock_prompt_a, mock_prompt_b, mock_prompt_c,
        mock_assemble, mock_validate, mock_page_id, mock_notion_prompt,
        mock_run_worker, mock_notify,
    ):
        """Worker-C 첫 시도 실패 → 재시도 성공 시 정상 완료"""
        # 호출 순서: Worker-A, Worker-C (병렬) → Worker-B → (Worker-C 재시도) → Notion-Writer
        call_count = {"n": 0}
        def side_effect(worker_name, prompt, tools, timeout=600, max_budget=0.50):
            call_count["n"] += 1
            if worker_name == "Worker-A":
                return _make_worker_result(True, WORKER_A_OUTPUT)
            elif worker_name == "Worker-B":
                return _make_worker_result(True, WORKER_B_OUTPUT)
            elif worker_name == "Worker-C":
                # 첫 번째 호출 (timeout=300) → 실패, 두 번째 (timeout=600) → 성공
                if timeout <= 300:
                    return _make_worker_result(False)
                return _make_worker_result(True, WORKER_C_OUTPUT)
            elif worker_name == "Notion-Writer":
                return _make_worker_result(True, NOTION_WRITER_OUTPUT)
            return _make_worker_result(False)

        mock_run_worker.side_effect = side_effect

        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump({"news": {}, "fear_greed_index": {}}, f)
            json_path = f.name

        try:
            result = run_parallel_notion_writer(json_path, session_reports_dir=None)
        finally:
            os.unlink(json_path)

        assert result is True
        # Worker-C 재시도가 timeout=600, budget=$0.60으로 호출되었는지 확인
        worker_c_calls = [
            c for c in mock_run_worker.call_args_list
            if len(c[0]) > 0 and c[0][0] == "Worker-C"
        ]
        assert len(worker_c_calls) >= 2, f"Worker-C는 최소 2번 호출되어야 합니다 (초기 + 재시도), got {len(worker_c_calls)}"

        # 재시도 시 timeout=600, budget=0.60 확인
        retry_call = worker_c_calls[-1]
        retry_args = retry_call[0]
        assert retry_args[3] == 600, f"재시도 timeout은 600이어야 합니다, got {retry_args[3]}"
        assert retry_args[4] == 0.60, f"재시도 budget은 0.60이어야 합니다, got {retry_args[4]}"

        # Slack 알림 전송 확인
        mock_notify.assert_called()

    @patch("scripts.notion_writer._notify_worker_failure")
    @patch("scripts.notion_writer._run_legacy_fallback", return_value=True)
    @patch("scripts.notion_writer.run_claude_worker")
    @patch("scripts.notion_writer.build_worker_c_prompt", return_value="prompt_c")
    @patch("scripts.notion_writer.build_worker_b_prompt", return_value=("prompt_b", ["AAPL", "MSFT", "NVDA"]))
    @patch("scripts.notion_writer.build_worker_a_prompt", return_value="prompt_a")
    @patch("scripts.notion_writer.precompute_session_metrics", return_value=None)
    def test_worker_c_retry_fails_triggers_legacy_fallback(
        self, mock_precompute, mock_prompt_a, mock_prompt_b, mock_prompt_c,
        mock_run_worker, mock_legacy, mock_notify,
    ):
        """Worker-C 첫 시도 + 재시도 모두 실패 → 레거시 폴백"""
        def side_effect(worker_name, prompt, tools, timeout=600, max_budget=0.50):
            if worker_name == "Worker-A":
                return _make_worker_result(True, WORKER_A_OUTPUT)
            elif worker_name == "Worker-B":
                return _make_worker_result(True, WORKER_B_OUTPUT)
            elif worker_name == "Worker-C":
                return _make_worker_result(False)  # 항상 실패
            return _make_worker_result(False)

        mock_run_worker.side_effect = side_effect

        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump({"news": {}, "fear_greed_index": {}}, f)
            json_path = f.name

        try:
            result = run_parallel_notion_writer(json_path, session_reports_dir=None)
        finally:
            os.unlink(json_path)

        # 레거시 폴백이 호출되었는지 확인
        mock_legacy.assert_called_once()
        assert result is True

        # Slack 알림이 2번 전송되었는지 확인 (첫 실패 + 재시도 실패)
        assert mock_notify.call_count == 2


class TestWorkerCValidationNotSkipped:
    """Worker-C 성공 시 유효성 검증이 건너뛰어지지 않는지 확인"""

    @patch("scripts.notion_writer._notify_worker_failure")
    @patch("scripts.notion_writer._run_legacy_fallback", return_value=True)
    @patch("scripts.notion_writer.run_claude_worker")
    @patch("scripts.notion_writer.build_notion_writer_prompt", return_value="notion_prompt")
    @patch("scripts.notion_writer.get_notion_page_id", return_value="test-page-id")
    @patch("scripts.notion_writer.validate_assembly", return_value=False)
    @patch("scripts.notion_writer.assemble_sections", return_value="bad_content")
    @patch("scripts.notion_writer.build_worker_c_prompt", return_value="prompt_c")
    @patch("scripts.notion_writer.build_worker_b_prompt", return_value=("prompt_b", ["AAPL", "MSFT", "NVDA"]))
    @patch("scripts.notion_writer.build_worker_a_prompt", return_value="prompt_a")
    @patch("scripts.notion_writer.precompute_session_metrics", return_value=None)
    def test_validation_runs_when_all_workers_succeed(
        self, mock_precompute, mock_prompt_a, mock_prompt_b, mock_prompt_c,
        mock_assemble, mock_validate, mock_page_id, mock_notion_prompt,
        mock_run_worker, mock_legacy, mock_notify,
    ):
        """3개 워커 모두 성공했지만 validate_assembly 실패 시 레거시 폴백"""
        def side_effect(worker_name, prompt, tools, timeout=600, max_budget=0.50):
            if worker_name == "Worker-A":
                return _make_worker_result(True, WORKER_A_OUTPUT)
            elif worker_name == "Worker-B":
                return _make_worker_result(True, WORKER_B_OUTPUT)
            elif worker_name == "Worker-C":
                return _make_worker_result(True, WORKER_C_OUTPUT)
            return _make_worker_result(False)

        mock_run_worker.side_effect = side_effect

        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump({"news": {}, "fear_greed_index": {}}, f)
            json_path = f.name

        try:
            result = run_parallel_notion_writer(json_path, session_reports_dir=None)
        finally:
            os.unlink(json_path)

        # validate_assembly가 호출되었는지 확인 (건너뛰지 않음)
        mock_validate.assert_called_once()
        # 검증 실패 → 레거시 폴백
        mock_legacy.assert_called_once()


class TestNotifyWorkerFailure:
    """Slack 알림 함수 단위 테스트"""

    @patch("trading_bot.notifications.NotificationService")
    def test_notify_sends_slack_message(self, mock_notifier_cls):
        """_notify_worker_failure가 NotificationService.notify_error를 호출"""
        mock_instance = MagicMock()
        mock_notifier_cls.return_value = mock_instance

        _notify_worker_failure("Worker-C", "타임아웃 발생")

        mock_instance.notify_error.assert_called_once_with(
            "Notion Writer Worker-C 실패",
            context="타임아웃 발생",
        )

    @patch("trading_bot.notifications.NotificationService", side_effect=Exception("no slack"))
    def test_notify_does_not_raise_on_error(self, mock_notifier_cls):
        """Slack 전송 실패 시 예외를 전파하지 않음"""
        # 예외가 발생하지 않아야 함
        _notify_worker_failure("Worker-C", "테스트")


class TestAllWorkersFailLegacyFallback:
    """모든 워커 실패 시 레거시 폴백 및 Slack 알림"""

    @patch("scripts.notion_writer._notify_worker_failure")
    @patch("scripts.notion_writer._run_legacy_fallback", return_value=True)
    @patch("scripts.notion_writer.run_claude_worker", return_value=_make_worker_result(False))
    @patch("scripts.notion_writer.build_worker_c_prompt", return_value="prompt_c")
    @patch("scripts.notion_writer.build_worker_b_prompt", return_value=("prompt_b", ["AAPL", "MSFT", "NVDA"]))
    @patch("scripts.notion_writer.build_worker_a_prompt", return_value="prompt_a")
    @patch("scripts.notion_writer.precompute_session_metrics", return_value=None)
    def test_all_workers_fail_notifies_and_falls_back(
        self, mock_precompute, mock_prompt_a, mock_prompt_b, mock_prompt_c,
        mock_run_worker, mock_legacy, mock_notify,
    ):
        """A/B/C 전부 실패 → Slack 알림 + 레거시 폴백"""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump({"news": {}, "fear_greed_index": {}}, f)
            json_path = f.name

        try:
            result = run_parallel_notion_writer(json_path, session_reports_dir=None)
        finally:
            os.unlink(json_path)

        mock_legacy.assert_called_once()
        mock_notify.assert_called_once()
        assert result is True
