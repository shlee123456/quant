"""
NotificationService 단위 테스트

모든 외부 API 호출(Slack, Email)은 mock으로 처리합니다.
"""

import pytest
from unittest.mock import patch, MagicMock
from datetime import datetime

from trading_bot.notifications import NotificationService


class TestNotificationServiceInit:
    """NotificationService 초기화 테스트"""

    def test_init_no_config(self):
        """설정 없이 초기화"""
        env_clear = {
            'SLACK_WEBHOOK_URL': '',
            'SLACK_BOT_TOKEN': '',
            'SLACK_CHANNEL': '',
            'SMTP_SERVER': '',
            'SMTP_PORT': '',
            'SMTP_USERNAME': '',
            'SMTP_PASSWORD': '',
            'SMTP_FROM': '',
            'SMTP_TO': '',
        }
        with patch.dict('os.environ', env_clear, clear=True):
            notifier = NotificationService()
        # os.getenv returns '' which is falsy but not None
        assert not notifier.slack_webhook_url
        assert not notifier.slack_bot_token
        assert notifier.email_config is None

    def test_init_with_slack_webhook(self):
        """Slack webhook URL로 초기화"""
        notifier = NotificationService(slack_webhook_url="https://hooks.slack.com/test")
        assert notifier.slack_webhook_url == "https://hooks.slack.com/test"

    def test_init_with_slack_bot_token(self):
        """Slack bot token으로 초기화"""
        notifier = NotificationService(slack_bot_token="xoxb-test-token", slack_channel="#test")
        assert notifier.slack_bot_token == "xoxb-test-token"
        assert notifier.slack_channel == "#test"

    def test_init_with_email_config(self):
        """Email 설정으로 초기화"""
        email_cfg = {
            'smtp_server': 'smtp.test.com',
            'smtp_port': 587,
            'username': 'user',
            'password': 'pass',
            'from_addr': 'from@test.com',
            'to_addrs': ['to@test.com']
        }
        notifier = NotificationService(email_config=email_cfg)
        assert notifier.email_config == email_cfg

    def test_error_count_starts_at_zero(self):
        """에러 카운터 초기값"""
        notifier = NotificationService()
        assert notifier._error_count == 0


class TestSendSlack:
    """Slack 메시지 전송 테스트"""

    def test_send_slack_no_webhook(self):
        """webhook 미설정 시 False 반환"""
        with patch.dict('os.environ', {}, clear=True):
            notifier = NotificationService(slack_webhook_url=None)
        notifier.slack_webhook_url = None
        assert notifier.send_slack("test") is False

    @patch('trading_bot.notifications.requests.post')
    def test_send_slack_success(self, mock_post):
        """Slack 전송 성공"""
        mock_post.return_value.status_code = 200
        notifier = NotificationService(slack_webhook_url="https://hooks.slack.com/test")

        result = notifier.send_slack("test message")

        assert result is True
        mock_post.assert_called_once()

    @patch('trading_bot.notifications.requests.post')
    def test_send_slack_auth_error_no_retry(self, mock_post):
        """인증 에러(4xx)는 재시도하지 않음"""
        mock_post.return_value.status_code = 401
        mock_post.return_value.text = "invalid_token"
        notifier = NotificationService(slack_webhook_url="https://hooks.slack.com/test")

        result = notifier.send_slack("test")

        assert result is False
        assert mock_post.call_count == 1  # 1회만 호출

    @patch('time.sleep')
    @patch('trading_bot.notifications.requests.post')
    def test_send_slack_retry_on_server_error(self, mock_post, mock_sleep):
        """서버 에러(5xx)는 재시도"""
        mock_post.return_value.status_code = 500
        mock_post.return_value.text = "internal error"
        notifier = NotificationService(slack_webhook_url="https://hooks.slack.com/test")

        result = notifier.send_slack("test")

        assert result is False
        assert mock_post.call_count == 3  # 3회 시도


class TestSendEmail:
    """Email 전송 테스트"""

    def test_send_email_no_config(self):
        """email 미설정 시 False 반환"""
        notifier = NotificationService()
        assert notifier.send_email("Subject", "Body") is False

    @patch('trading_bot.notifications.smtplib.SMTP')
    def test_send_email_success(self, mock_smtp):
        """Email 전송 성공"""
        mock_server = MagicMock()
        mock_smtp.return_value.__enter__ = MagicMock(return_value=mock_server)
        mock_smtp.return_value.__exit__ = MagicMock(return_value=False)

        email_cfg = {
            'smtp_server': 'smtp.test.com',
            'smtp_port': 587,
            'username': 'user',
            'password': 'pass',
            'from_addr': 'from@test.com',
            'to_addrs': ['to@test.com']
        }
        notifier = NotificationService(email_config=email_cfg)

        result = notifier.send_email("Test Subject", "Test Body")

        assert result is True
        mock_server.starttls.assert_called_once()
        mock_server.login.assert_called_once_with('user', 'pass')

    @patch('trading_bot.notifications.smtplib.SMTP')
    def test_send_email_html(self, mock_smtp):
        """HTML 이메일 전송"""
        mock_server = MagicMock()
        mock_smtp.return_value.__enter__ = MagicMock(return_value=mock_server)
        mock_smtp.return_value.__exit__ = MagicMock(return_value=False)

        email_cfg = {
            'smtp_server': 'smtp.test.com',
            'smtp_port': 587,
            'username': 'user',
            'password': 'pass',
            'from_addr': 'from@test.com',
            'to_addrs': ['to@test.com']
        }
        notifier = NotificationService(email_config=email_cfg)

        result = notifier.send_email("Subject", "<h1>HTML</h1>", html=True)
        assert result is True

    @patch('trading_bot.notifications.smtplib.SMTP', side_effect=ConnectionError("refused"))
    def test_send_email_connection_error(self, mock_smtp):
        """Email 연결 에러"""
        email_cfg = {
            'smtp_server': 'smtp.test.com',
            'smtp_port': 587,
            'username': 'user',
            'password': 'pass',
            'from_addr': 'from@test.com',
            'to_addrs': ['to@test.com']
        }
        notifier = NotificationService(email_config=email_cfg)

        result = notifier.send_email("Subject", "Body")
        assert result is False


class TestNotifyTrade:
    """거래 알림 테스트"""

    @patch('trading_bot.notifications.requests.post')
    def test_notify_trade_buy(self, mock_post):
        """매수 알림"""
        mock_post.return_value.status_code = 200
        notifier = NotificationService(slack_webhook_url="https://hooks.slack.com/test")

        trade = {
            'type': 'BUY',
            'symbol': 'AAPL',
            'price': 150.0,
            'size': 10.0,
            'timestamp': datetime(2026, 2, 22, 10, 30)
        }
        result = notifier.notify_trade(trade)
        assert result is True

    @patch('trading_bot.notifications.requests.post')
    def test_notify_trade_sell(self, mock_post):
        """매도 알림"""
        mock_post.return_value.status_code = 200
        notifier = NotificationService(slack_webhook_url="https://hooks.slack.com/test")

        trade = {
            'type': 'SELL',
            'symbol': 'MSFT',
            'price': 400.0,
            'size': 5.0,
            'timestamp': datetime(2026, 2, 22, 10, 30)
        }
        result = notifier.notify_trade(trade)
        assert result is True

    def test_notify_trade_no_channels(self):
        """채널 미설정 시 False"""
        with patch.dict('os.environ', {}, clear=True):
            notifier = NotificationService()
        notifier.slack_webhook_url = None
        notifier.email_config = None
        trade = {'type': 'BUY', 'symbol': 'AAPL', 'price': 150.0, 'timestamp': datetime(2026, 2, 22)}
        result = notifier.notify_trade(trade)
        assert result is False


class TestNotifyDailyReport:
    """일일 리포트 알림 테스트"""

    @patch('trading_bot.notifications.requests.post')
    def test_notify_daily_report_positive(self, mock_post):
        """양수 수익률 리포트"""
        mock_post.return_value.status_code = 200
        notifier = NotificationService(slack_webhook_url="https://hooks.slack.com/test")

        summary = {
            'strategy_name': 'RSI_14',
            'total_return': 5.0,
            'sharpe_ratio': 1.5,
            'max_drawdown': -3.0,
            'win_rate': 60.0,
            'num_trades': 10
        }
        result = notifier.notify_daily_report(summary)
        assert result is True

    @patch('trading_bot.notifications.requests.post')
    def test_notify_daily_report_handles_none_values(self, mock_post):
        """None 값 처리"""
        mock_post.return_value.status_code = 200
        notifier = NotificationService(slack_webhook_url="https://hooks.slack.com/test")

        summary = {
            'strategy_name': 'RSI_14',
            'total_return': None,
            'sharpe_ratio': None,
            'max_drawdown': None,
            'win_rate': None,
            'num_trades': None
        }
        result = notifier.notify_daily_report(summary)
        assert result is True


class TestNotifyError:
    """에러 알림 테스트"""

    def test_notify_error(self):
        """에러 알림 시 에러 카운트 증가"""
        with patch.dict('os.environ', {}, clear=True):
            notifier = NotificationService()
        notifier.slack_webhook_url = None
        notifier.email_config = None

        notifier.notify_error("API 실패", "rate limit exceeded")
        assert notifier._error_count == 1

    def test_notify_error_critical_escalation(self):
        """3회 연속 에러 시 CRITICAL 에스컬레이션"""
        with patch.dict('os.environ', {}, clear=True):
            notifier = NotificationService()
        notifier.slack_webhook_url = None
        notifier.email_config = None

        notifier.notify_error("err1")
        notifier.notify_error("err2")
        notifier.notify_error("err3")

        assert notifier._error_count == 3

    def test_reset_error_count(self):
        """에러 카운터 리셋"""
        notifier = NotificationService()
        notifier._error_count = 5
        notifier.reset_error_count()
        assert notifier._error_count == 0


class TestUploadFileToSlack:
    """Slack 파일 업로드 테스트"""

    def test_upload_no_bot_token(self):
        """bot token 미설정 시 False"""
        notifier = NotificationService()
        assert notifier.upload_file_to_slack("test.txt") is False

    def test_upload_file_not_found(self):
        """존재하지 않는 파일"""
        notifier = NotificationService(slack_bot_token="xoxb-test")
        assert notifier.upload_file_to_slack("/nonexistent/file.txt") is False

    def test_upload_reports_no_bot_token(self):
        """bot token 미설정 시 upload_reports_to_slack False"""
        notifier = NotificationService()
        assert notifier.upload_reports_to_slack(["file1.txt"]) is False


class TestNotifySessionStart:
    """세션 시작 알림 테스트"""

    @patch('trading_bot.notifications.requests.post')
    def test_notify_session_start(self, mock_post):
        """세션 시작 알림"""
        mock_post.return_value.status_code = 200
        notifier = NotificationService(slack_webhook_url="https://hooks.slack.com/test")

        config = {
            'strategy_name': 'RSI_14',
            'symbols': ['AAPL', 'MSFT'],
            'initial_capital': 10000.0
        }
        result = notifier.notify_session_start(config)
        assert result is True


class TestNotifyDailyReportWithFiles:
    """일일 리포트 + 파일 통합 전송 테스트"""

    @patch('trading_bot.notifications.requests.post')
    def test_text_only_no_files(self, mock_post):
        """파일 없이 텍스트만 전송"""
        mock_post.return_value.status_code = 200
        notifier = NotificationService(slack_webhook_url="https://hooks.slack.com/test")

        summary = {'strategy_name': 'RSI', 'total_return': 1.0}
        result = notifier.notify_daily_report_with_files(summary)
        assert result is True
