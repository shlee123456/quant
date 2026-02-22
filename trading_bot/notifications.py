"""
Notification Service for Trading Bot

Sends alerts and reports via:
- Slack (Webhook)
- Email (SMTP)

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
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from typing import Dict, Optional, List
from datetime import datetime
from pathlib import Path


logger = logging.getLogger(__name__)


class NotificationService:
    """
    Multi-channel notification service for trading alerts

    Supports:
    - Slack Webhook notifications
    - Email (SMTP) notifications
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
                Get from: https://api.slack.com/messaging/webhooks
            slack_bot_token: Slack Bot User OAuth Token (for file uploads)
                Get from: https://api.slack.com/apps → OAuth & Permissions
                Required scopes: files:write, chat:write
            slack_channel: Slack channel to post to (e.g., '#trading-alerts')
            email_config: Email SMTP configuration dict with keys:
                - smtp_server: SMTP server address (e.g., 'smtp.gmail.com')
                - smtp_port: SMTP port (e.g., 587 for TLS)
                - username: Email username
                - password: Email password or app password
                - from_addr: Sender email address
                - to_addrs: List of recipient email addresses
        """
        # Slack configuration
        self.slack_webhook_url = slack_webhook_url or os.getenv('SLACK_WEBHOOK_URL')
        self.slack_bot_token = slack_bot_token or os.getenv('SLACK_BOT_TOKEN')
        self.slack_channel = slack_channel or os.getenv('SLACK_CHANNEL', '#trading-alerts')

        # Email configuration
        self.email_config = email_config or self._load_email_config()

        # Log configuration
        if self.slack_webhook_url:
            logger.info("✓ Slack webhook enabled (text messages)")
        else:
            logger.info("⚪ Slack webhook disabled (no webhook URL)")

        if self.slack_bot_token:
            logger.info("✓ Slack bot token enabled (file uploads)")
        else:
            logger.info("⚪ Slack bot token disabled (no bot token)")

        if self.email_config:
            logger.info("✓ Email notifications enabled")
        else:
            logger.info("⚪ Email notifications disabled (no email config)")

        # Error tracking
        self._error_count = 0

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

    def send_slack(self, message: str, color: str = 'good') -> bool:
        """
        Send message to Slack via webhook

        Args:
            message: Message text (supports Slack markdown)
            color: Attachment color ('good', 'warning', 'danger', or hex code)

        Returns:
            True if sent successfully, False otherwise
        """
        if not self.slack_webhook_url:
            logger.debug("Slack webhook not configured, skipping notification")
            return False

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
                    self.slack_webhook_url,
                    json=payload,
                    timeout=10
                )
                if response.status_code == 200:
                    logger.debug("✓ Slack notification sent")
                    self._error_count = 0
                    return True
                elif response.status_code in (400, 401, 403, 404):
                    logger.error(f"✗ Slack 인증/요청 오류 (재시도 불가): {response.status_code} {response.text}")
                    return False
                else:
                    last_error = f"{response.status_code} {response.text}"
                    logger.warning(f"⚠ Slack 전송 실패 (시도 {attempt + 1}/3): {last_error}")
            except Exception as e:
                last_error = str(e)
                logger.warning(f"⚠ Slack 전송 오류 (시도 {attempt + 1}/3): {e}")

            if attempt < 2:
                import time
                time.sleep(delays[attempt])

        logger.error(f"✗ Slack notification failed after 3 attempts: {last_error}")
        return False

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
        if not self.email_config:
            logger.debug("Email not configured, skipping notification")
            return False

        try:
            # Create message
            if html:
                msg = MIMEMultipart('alternative')
                msg.attach(MIMEText(body, 'html'))
            else:
                msg = MIMEText(body, 'plain')

            msg['Subject'] = subject
            msg['From'] = self.email_config['from_addr']
            msg['To'] = ', '.join(self.email_config['to_addrs'])

            # Send via SMTP
            with smtplib.SMTP(
                self.email_config['smtp_server'],
                self.email_config['smtp_port']
            ) as server:
                server.starttls()  # Enable TLS
                server.login(
                    self.email_config['username'],
                    self.email_config['password']
                )
                server.sendmail(
                    self.email_config['from_addr'],
                    self.email_config['to_addrs'],
                    msg.as_string()
                )

            logger.debug("✓ Email notification sent")
            return True

        except Exception as e:
            logger.error(f"✗ Email notification error: {e}")
            return False

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

        email_subject = f"{prefix}트레이딩 봇 오류 알림"
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

        Example:
            notifier.upload_file_to_slack(
                'reports/RSI_14_30_70_20260209_report.json',
                initial_comment='📊 일일 트레이딩 리포트',
                title='Daily Trading Report'
            )
        """
        if not self.slack_bot_token:
            logger.debug("Slack bot token not configured, skipping file upload")
            return False

        # Check if file exists
        file_path_obj = Path(file_path)
        if not file_path_obj.exists():
            logger.error(f"✗ File not found: {file_path}")
            return False

        try:
            # Import slack_sdk (lazy import to avoid dependency if not used)
            try:
                from slack_sdk import WebClient
                from slack_sdk.errors import SlackApiError
            except ImportError:
                logger.error("✗ slack-sdk not installed. Run: pip install slack-sdk")
                return False

            client = WebClient(token=self.slack_bot_token)

            # Use filename as title if not provided
            if title is None:
                title = file_path_obj.name

            # Upload file
            response = client.files_upload_v2(
                channel=self.slack_channel,
                file=str(file_path),
                title=title,
                initial_comment=initial_comment
            )

            if response['ok']:
                logger.debug(f"✓ File uploaded to Slack: {file_path}")
                return True
            else:
                logger.error(f"✗ Slack file upload failed: {response}")
                return False

        except Exception as e:
            logger.error(f"✗ Slack file upload error: {e}")
            return False

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

        Example:
            notifier.upload_reports_to_slack(
                report_files=[
                    'reports/RSI_14_30_70_summary.csv',
                    'reports/RSI_14_30_70_snapshots.csv',
                    'reports/RSI_14_30_70_report.json'
                ],
                session_summary={'total_return': 2.5, 'win_rate': 65.0}
            )
        """
        if not self.slack_bot_token:
            logger.debug("Slack bot token not configured, skipping file upload")
            return False

        # Format initial comment
        if session_summary:
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
            comment = f"📊 트레이딩 리포트 ({len(report_files)}개 파일)"

        # Upload each file
        success_count = 0
        for file_path in report_files:
            if self.upload_file_to_slack(
                file_path,
                initial_comment=comment if success_count == 0 else None,  # Only first file gets comment
                title=Path(file_path).name
            ):
                success_count += 1

        if success_count > 0:
            logger.info(f"✓ Uploaded {success_count}/{len(report_files)} files to Slack")
            return True
        else:
            logger.error(f"✗ Failed to upload any files to Slack")
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

        Example:
            notifier.notify_daily_report_with_files(
                session_summary={
                    'strategy_name': 'RSI_14_70_30',
                    'total_return': 2.5,
                    'win_rate': 65.0
                },
                report_files=[
                    'reports/RSI_14_30_70_summary.csv',
                    'reports/RSI_14_30_70_report.json'
                ]
            )
        """
        # Send text notification (webhook or email)
        text_sent = self.notify_daily_report(session_summary)

        # Upload files if provided
        files_sent = False
        if report_files:
            files_sent = self.upload_reports_to_slack(report_files, session_summary)

        return text_sent or files_sent
