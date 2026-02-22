"""
Notification Service for Trading Bot

Sends alerts and reports via:
- Slack (Webhook)
- Slack (Bot Token - file uploads)
- Email (SMTP)

Architecture:
    NotificationChannel (ABC)
    +-- SlackWebhookChannel   (text messages via webhook)
    +-- SlackBotChannel       (file uploads via Bot Token)
    +-- EmailChannel          (email via SMTP)

    NotificationService
    +-- channels: List[NotificationChannel]
    +-- notify_trade(), notify_daily_report(), etc. (public API - unchanged)

Usage:
    from trading_bot.notifications import NotificationService

    # Initialize with Slack
    notifier = NotificationService(
        slack_webhook_url="https://hooks.slack.com/services/YOUR/WEBHOOK/URL"
    )

    # Send trade notification
    notifier.notify_trade({
        'type': 'BUY',
        'symbol': 'AAPL',
        'price': 150.25,
        'size': 10.0
    })

    # Send daily report
    notifier.notify_daily_report({
        'strategy_name': 'RSI_14_70_30',
        'total_return': 2.5,
        'win_rate': 65.0,
        'max_drawdown': -3.2
    })
"""

import os
import logging
import requests
import smtplib
import time
from abc import ABC, abstractmethod
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from typing import Dict, Optional, List
from datetime import datetime
from pathlib import Path


logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# NotificationChannel ABC
# ---------------------------------------------------------------------------

class NotificationChannel(ABC):
    """
    알림 채널 추상 기본 클래스

    모든 알림 채널은 이 클래스를 상속하여 send()와 is_configured()를 구현합니다.
    """

    @abstractmethod
    def send(self, message: str, **kwargs) -> bool:
        """
        메시지 전송

        Args:
            message: 전송할 메시지
            **kwargs: 채널별 추가 옵션 (color, subject, html 등)

        Returns:
            True if sent successfully, False otherwise
        """
        pass

    @abstractmethod
    def is_configured(self) -> bool:
        """
        채널이 올바르게 설정되었는지 확인

        Returns:
            True if the channel has all required configuration
        """
        pass


# ---------------------------------------------------------------------------
# SlackWebhookChannel
# ---------------------------------------------------------------------------

class SlackWebhookChannel(NotificationChannel):
    """
    Slack Incoming Webhook을 통한 텍스트 메시지 전송 채널

    Args:
        webhook_url: Slack incoming webhook URL
    """

    def __init__(self, webhook_url: Optional[str] = None):
        self.webhook_url = webhook_url

    def is_configured(self) -> bool:
        return bool(self.webhook_url)

    def send(self, message: str, **kwargs) -> bool:
        """
        Slack webhook으로 메시지 전송

        Args:
            message: 메시지 텍스트 (Slack markdown 지원)
            color: Attachment 색상 ('good', 'warning', 'danger', hex)

        Returns:
            True if sent successfully
        """
        if not self.is_configured():
            logger.debug("Slack webhook not configured, skipping notification")
            return False

        color = kwargs.get('color', 'good')

        payload = {
            'attachments': [{
                'color': color,
                'text': message,
                'footer': 'Trading Bot',
                'ts': int(datetime.now().timestamp())
            }]
        }

        delays = [5, 10, 20]
        last_error = None

        for attempt in range(3):
            try:
                response = requests.post(
                    self.webhook_url,
                    json=payload,
                    timeout=10
                )
                if response.status_code == 200:
                    logger.debug("Slack notification sent")
                    return True
                elif response.status_code in (400, 401, 403, 404):
                    logger.error(
                        f"Slack auth/request error (no retry): "
                        f"{response.status_code} {response.text}"
                    )
                    return False
                else:
                    last_error = f"{response.status_code} {response.text}"
                    logger.warning(
                        f"Slack send failed (attempt {attempt + 1}/3): {last_error}"
                    )
            except Exception as e:
                last_error = str(e)
                logger.warning(
                    f"Slack send error (attempt {attempt + 1}/3): {e}"
                )

            if attempt < 2:
                time.sleep(delays[attempt])

        logger.error(f"Slack notification failed after 3 attempts: {last_error}")
        return False


# ---------------------------------------------------------------------------
# SlackBotChannel
# ---------------------------------------------------------------------------

class SlackBotChannel(NotificationChannel):
    """
    Slack Bot Token을 통한 파일 업로드 채널

    Args:
        bot_token: Slack Bot User OAuth Token
        channel: Slack channel ID or name
    """

    def __init__(
        self,
        bot_token: Optional[str] = None,
        channel: Optional[str] = None
    ):
        self.bot_token = bot_token
        self.channel = channel or '#trading-alerts'

    def is_configured(self) -> bool:
        return bool(self.bot_token)

    def send(self, message: str, **kwargs) -> bool:
        """
        SlackBotChannel의 send()는 파일 업로드에 사용됩니다.
        텍스트 메시지 전송에는 SlackWebhookChannel을 사용하세요.

        이 메서드는 직접 호출하지 않고, upload_file()을 사용합니다.
        """
        logger.debug("SlackBotChannel.send() called - use upload_file() instead")
        return False

    def upload_file(
        self,
        file_path: str,
        initial_comment: Optional[str] = None,
        title: Optional[str] = None
    ) -> bool:
        """
        Slack에 파일 업로드

        Args:
            file_path: 업로드할 파일 경로
            initial_comment: 파일과 함께 전송할 메시지
            title: 파일 제목 (기본값: 파일명)

        Returns:
            True if uploaded successfully
        """
        if not self.is_configured():
            logger.debug("Slack bot token not configured, skipping file upload")
            return False

        file_path_obj = Path(file_path)
        if not file_path_obj.exists():
            logger.error(f"File not found: {file_path}")
            return False

        try:
            try:
                from slack_sdk import WebClient
            except ImportError:
                logger.error("slack-sdk not installed. Run: pip install slack-sdk")
                return False

            client = WebClient(token=self.bot_token)

            if title is None:
                title = file_path_obj.name

            response = client.files_upload_v2(
                channel=self.channel,
                file=str(file_path),
                title=title,
                initial_comment=initial_comment
            )

            if response['ok']:
                logger.debug(f"File uploaded to Slack: {file_path}")
                return True
            else:
                logger.error(f"Slack file upload failed: {response}")
                return False

        except Exception as e:
            logger.error(f"Slack file upload error: {e}")
            return False


# ---------------------------------------------------------------------------
# EmailChannel
# ---------------------------------------------------------------------------

class EmailChannel(NotificationChannel):
    """
    SMTP를 통한 이메일 전송 채널

    Args:
        config: Email SMTP 설정 딕셔너리
            - smtp_server: SMTP 서버 주소
            - smtp_port: SMTP 포트
            - username: 사용자명
            - password: 비밀번호
            - from_addr: 발신 이메일 주소
            - to_addrs: 수신 이메일 주소 리스트
    """

    def __init__(self, config: Optional[Dict] = None):
        self.config = config

    def is_configured(self) -> bool:
        return bool(self.config)

    def send(self, message: str, **kwargs) -> bool:
        """
        이메일 전송

        Args:
            message: 이메일 본문
            subject: 이메일 제목 (기본값: 'Trading Bot Notification')
            html: True이면 HTML 본문 (기본값: False)

        Returns:
            True if sent successfully
        """
        if not self.is_configured():
            logger.debug("Email not configured, skipping notification")
            return False

        subject = kwargs.get('subject', 'Trading Bot Notification')
        html = kwargs.get('html', False)

        try:
            if html:
                msg = MIMEMultipart('alternative')
                msg.attach(MIMEText(message, 'html'))
            else:
                msg = MIMEText(message, 'plain')

            msg['Subject'] = subject
            msg['From'] = self.config['from_addr']
            msg['To'] = ', '.join(self.config['to_addrs'])

            with smtplib.SMTP(
                self.config['smtp_server'],
                self.config['smtp_port']
            ) as server:
                server.starttls()
                server.login(
                    self.config['username'],
                    self.config['password']
                )
                server.sendmail(
                    self.config['from_addr'],
                    self.config['to_addrs'],
                    msg.as_string()
                )

            logger.debug("Email notification sent")
            return True

        except Exception as e:
            logger.error(f"Email notification error: {e}")
            return False


# ---------------------------------------------------------------------------
# NotificationService (public API preserved)
# ---------------------------------------------------------------------------

class NotificationService:
    """
    Multi-channel notification service for trading alerts

    Supports:
    - Slack Webhook notifications
    - Slack Bot Token file uploads
    - Email (SMTP) notifications

    Internally delegates to NotificationChannel implementations.
    Public API (notify_trade, notify_daily_report, etc.) is unchanged.
    """

    def __init__(
        self,
        slack_webhook_url: Optional[str] = None,
        slack_bot_token: Optional[str] = None,
        slack_channel: Optional[str] = None,
        email_config: Optional[Dict] = None
    ):
        """
        Initialize notification service

        Args:
            slack_webhook_url: Slack incoming webhook URL (for text messages)
            slack_bot_token: Slack Bot User OAuth Token (for file uploads)
            slack_channel: Slack channel to post to (e.g., '#trading-alerts')
            email_config: Email SMTP configuration dict
        """
        # Resolve from env if not provided
        resolved_webhook = slack_webhook_url or os.getenv('SLACK_WEBHOOK_URL')
        resolved_bot_token = slack_bot_token or os.getenv('SLACK_BOT_TOKEN')
        resolved_channel = slack_channel or os.getenv('SLACK_CHANNEL', '#trading-alerts')
        resolved_email = email_config or self._load_email_config()

        # Build channels
        self._slack_webhook = SlackWebhookChannel(webhook_url=resolved_webhook)
        self._slack_bot = SlackBotChannel(
            bot_token=resolved_bot_token,
            channel=resolved_channel
        )
        self._email = EmailChannel(config=resolved_email)

        # Backward-compatible attributes
        self.slack_webhook_url = resolved_webhook
        self.slack_bot_token = resolved_bot_token
        self.slack_channel = resolved_channel
        self.email_config = resolved_email

        # Log configuration
        if self._slack_webhook.is_configured():
            logger.info("Slack webhook enabled (text messages)")
        else:
            logger.info("Slack webhook disabled (no webhook URL)")

        if self._slack_bot.is_configured():
            logger.info("Slack bot token enabled (file uploads)")
        else:
            logger.info("Slack bot token disabled (no bot token)")

        if self._email.is_configured():
            logger.info("Email notifications enabled")
        else:
            logger.info("Email notifications disabled (no email config)")

        # Error tracking
        self._error_count = 0

    @property
    def channels(self) -> List[NotificationChannel]:
        """설정된 모든 채널 반환 (SlackBot 제외 - 파일 업로드 전용)"""
        result = []
        if self._slack_webhook.is_configured():
            result.append(self._slack_webhook)
        if self._email.is_configured():
            result.append(self._email)
        return result

    def reset_error_count(self):
        """에러 카운터 리셋 (정상 동작 복귀 시 호출)"""
        self._error_count = 0

    def _load_email_config(self) -> Optional[Dict]:
        """Load email configuration from environment variables"""
        smtp_server = os.getenv('SMTP_SERVER')
        smtp_port = os.getenv('SMTP_PORT')
        username = os.getenv('SMTP_USERNAME')
        password = os.getenv('SMTP_PASSWORD')
        from_addr = os.getenv('SMTP_FROM')
        to_addrs = os.getenv('SMTP_TO')

        if all([smtp_server, smtp_port, username, password, from_addr, to_addrs]):
            return {
                'smtp_server': smtp_server,
                'smtp_port': int(smtp_port),
                'username': username,
                'password': password,
                'from_addr': from_addr,
                'to_addrs': [addr.strip() for addr in to_addrs.split(',')]
            }

        return None

    # ------------------------------------------------------------------
    # Low-level send methods (backward-compatible)
    # ------------------------------------------------------------------

    def send_slack(self, message: str, color: str = 'good') -> bool:
        """
        Send message to Slack via webhook

        Args:
            message: Message text (supports Slack markdown)
            color: Attachment color ('good', 'warning', 'danger', or hex code)

        Returns:
            True if sent successfully, False otherwise
        """
        result = self._slack_webhook.send(message, color=color)
        if result:
            self._error_count = 0
        return result

    def send_email(self, subject: str, body: str, html: bool = False) -> bool:
        """
        Send email via SMTP

        Args:
            subject: Email subject
            body: Email body (plain text or HTML)
            html: If True, body is HTML, otherwise plain text

        Returns:
            True if sent successfully, False otherwise
        """
        return self._email.send(body, subject=subject, html=html)

    # ------------------------------------------------------------------
    # High-level notification methods (public API - unchanged)
    # ------------------------------------------------------------------

    def notify_trade(self, trade: Dict) -> bool:
        """
        Send notification when a trade is executed

        Args:
            trade: Trade dict with keys:
                - type: 'BUY' or 'SELL'
                - symbol: Stock symbol
                - price: Execution price
                - size: Number of shares
                - timestamp: Trade timestamp (optional)

        Returns:
            True if at least one notification sent successfully
        """
        trade_type = trade['type']
        symbol = trade['symbol']
        price = trade['price']
        size = trade.get('size', 0)

        # Format message
        emoji = '🟢' if trade_type == 'BUY' else '🔴'
        type_kr = '매수' if trade_type == 'BUY' else '매도'
        timestamp = trade.get('timestamp', datetime.now()).strftime('%Y-%m-%d %H:%M:%S')

        slack_msg = f"""
{emoji} *{type_kr}* {symbol}
가격: ${price:.2f}
수량: {size:.2f}주
금액: ${price * size:,.2f}
시간: {timestamp}
        """.strip()

        email_subject = f"거래 알림: {type_kr} {symbol}"
        email_body = f"""
거래 체결 알림

종류: {type_kr}
종목: {symbol}
가격: ${price:.2f}
수량: {size:.2f}주
총 금액: ${price * size:,.2f}
시간: {timestamp}

---
자동매매 트레이딩 봇
        """.strip()

        # Send notifications
        slack_sent = self.send_slack(slack_msg, color='good' if trade_type == 'BUY' else 'danger')
        email_sent = self.send_email(email_subject, email_body)

        return slack_sent or email_sent

    def notify_daily_report(self, session_summary: Dict) -> bool:
        """
        Send daily performance report

        Args:
            session_summary: Session summary dict with keys:
                - strategy_name: Strategy name
                - total_return: Total return percentage
                - sharpe_ratio: Sharpe ratio
                - max_drawdown: Maximum drawdown percentage
                - win_rate: Win rate percentage
                - num_trades: Total number of trades

        Returns:
            True if at least one notification sent successfully
        """
        strategy = session_summary.get('strategy_name', 'Unknown')
        # Handle None values explicitly (get() returns None if value is None)
        total_return = session_summary.get('total_return') or 0.0
        sharpe = session_summary.get('sharpe_ratio') or 0.0
        max_dd = session_summary.get('max_drawdown') or 0.0
        win_rate = session_summary.get('win_rate') or 0.0
        num_trades = session_summary.get('num_trades') or 0

        # Determine performance emoji
        if total_return > 2:
            emoji = '🚀'
            color = 'good'
        elif total_return > 0:
            emoji = '📈'
            color = 'good'
        elif total_return > -2:
            emoji = '📊'
            color = 'warning'
        else:
            emoji = '📉'
            color = 'danger'

        # Format Slack message
        slack_msg = f"""
{emoji} *일일 트레이딩 리포트*

전략: {strategy}
총 수익률: {total_return:+.2f}%
샤프 비율: {sharpe:.2f}
최대 낙폭: {max_dd:.2f}%
승률: {win_rate:.1f}%
총 거래: {num_trades}회

날짜: {datetime.now().strftime('%Y-%m-%d')}
        """.strip()

        # Format email
        email_subject = f"일일 리포트: {total_return:+.2f}% ({strategy})"
        email_body = f"""
일일 모의투자 리포트
{datetime.now().strftime('%Y-%m-%d')}

성과 요약
-------------------
전략: {strategy}
총 수익률: {total_return:+.2f}%
샤프 비율: {sharpe:.2f}
최대 낙폭: {max_dd:.2f}%
승률: {win_rate:.1f}%

거래 활동
----------------
총 거래: {num_trades}회

---
자동매매 트레이딩 봇
        """.strip()

        # Send notifications
        slack_sent = self.send_slack(slack_msg, color=color)
        email_sent = self.send_email(email_subject, email_body)

        return slack_sent or email_sent

    def notify_error(self, error_msg: str, context: Optional[str] = None) -> bool:
        """
        Send error notification

        Args:
            error_msg: Error message
            context: Additional context (optional)

        Returns:
            True if at least one notification sent successfully
        """
        self._error_count += 1

        # 3회 연속 에러 시 CRITICAL 에스컬레이션
        prefix = "[CRITICAL] " if self._error_count >= 3 else ""

        slack_msg = f"""
⚠️ *{prefix}트레이딩 봇 오류*

{error_msg}
        """.strip()

        if context:
            slack_msg += f"\n\n상황: {context}"

        if self._error_count >= 3:
            slack_msg += f"\n\n⚠️ 연속 에러 {self._error_count}회 발생"

        slack_msg += f"\n\n시간: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"

        email_subject = f"{prefix}트레이딩 봇 오류 \uc54c\ub9bc"
        email_body = f"""
{prefix}오류 알림

{error_msg}

상황: {context or '없음'}
연속 에러: {self._error_count}회
시간: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

---
자동매매 트레이딩 봇
        """.strip()

        # Send notifications
        slack_sent = self.send_slack(slack_msg, color='danger')
        email_sent = self.send_email(email_subject, email_body)

        return slack_sent or email_sent

    def notify_session_start(self, config: Dict) -> bool:
        """
        Send notification when trading session starts

        Args:
            config: Session configuration dict

        Returns:
            True if at least one notification sent successfully
        """
        strategy = config.get('strategy_name', 'Unknown')
        symbols = config.get('symbols', [])
        capital = config.get('initial_capital', 0)

        slack_msg = f"""
🟢 *트레이딩 세션 시작*

전략: {strategy}
종목: {', '.join(symbols)}
초기 자본: ${capital:,.2f}
시간: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
        """.strip()

        email_subject = "트레이딩 세션 시작"
        email_body = f"""
모의투자 세션 시작

전략: {strategy}
종목: {', '.join(symbols)}
초기 자본: ${capital:,.2f}
시간: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

---
자동매매 트레이딩 봇
        """.strip()

        slack_sent = self.send_slack(slack_msg, color='good')
        email_sent = self.send_email(email_subject, email_body)

        return slack_sent or email_sent

    def notify_session_end(self, session_summary: Dict) -> bool:
        """
        Send notification when trading session ends

        Args:
            session_summary: Session summary dict

        Returns:
            True if at least one notification sent successfully
        """
        return self.notify_daily_report(session_summary)

    # ------------------------------------------------------------------
    # File upload methods (delegate to SlackBotChannel)
    # ------------------------------------------------------------------

    def upload_file_to_slack(
        self,
        file_path: str,
        initial_comment: Optional[str] = None,
        title: Optional[str] = None
    ) -> bool:
        """
        Upload a file to Slack using Bot Token

        Args:
            file_path: Path to the file to upload
            initial_comment: Optional message to include with the file
            title: Optional title for the file (defaults to filename)

        Returns:
            True if uploaded successfully, False otherwise
        """
        return self._slack_bot.upload_file(
            file_path,
            initial_comment=initial_comment,
            title=title
        )

    def upload_reports_to_slack(
        self,
        report_files: List[str],
        session_summary: Optional[Dict] = None
    ) -> bool:
        """
        Upload multiple report files to Slack with a summary message

        Args:
            report_files: List of file paths to upload
            session_summary: Optional session summary dict for message formatting

        Returns:
            True if at least one file uploaded successfully
        """
        if not self._slack_bot.is_configured():
            logger.debug("Slack bot token not configured, skipping file upload")
            return False

        # Format initial comment
        if session_summary:
            strategy = session_summary.get('strategy_name', 'Unknown')
            total_return = session_summary.get('total_return') or 0.0
            sharpe = session_summary.get('sharpe_ratio') or 0.0
            max_dd = session_summary.get('max_drawdown') or 0.0
            win_rate = session_summary.get('win_rate') or 0.0
            num_trades = session_summary.get('num_trades') or 0

            if total_return > 2:
                emoji = '🚀'
            elif total_return > 0:
                emoji = '📈'
            elif total_return > -2:
                emoji = '📊'
            else:
                emoji = '📉'

            comment = f"""
{emoji} *일일 트레이딩 리포트*

전략: {strategy}
총 수익률: {total_return:+.2f}%
샤프 비율: {sharpe:.2f}
최대 낙폭: {max_dd:.2f}%
승률: {win_rate:.1f}%
총 거래: {num_trades}회

날짜: {datetime.now().strftime('%Y-%m-%d')}
파일 수: {len(report_files)}개
            """.strip()
        else:
            comment = f"📊 트레이딩 리포트 ({len(report_files)}개 \ud30c\uc77c)"

        # Upload each file
        success_count = 0
        for file_path in report_files:
            if self._slack_bot.upload_file(
                file_path,
                initial_comment=comment if success_count == 0 else None,
                title=Path(file_path).name
            ):
                success_count += 1

        if success_count > 0:
            logger.info(f"Uploaded {success_count}/{len(report_files)} files to Slack")
            return True
        else:
            logger.error("Failed to upload any files to Slack")
            return False

    def notify_daily_report_with_files(
        self,
        session_summary: Dict,
        report_files: Optional[List[str]] = None
    ) -> bool:
        """
        Send daily report notification with file attachments

        Combines text notification (Webhook/Email) with file uploads (Bot Token)

        Args:
            session_summary: Session summary dict
            report_files: Optional list of report file paths to upload

        Returns:
            True if at least one notification sent successfully
        """
        # Send text notification (webhook or email)
        text_sent = self.notify_daily_report(session_summary)

        # Upload files if provided
        files_sent = False
        if report_files:
            files_sent = self.upload_reports_to_slack(report_files, session_summary)

        return text_sent or files_sent
