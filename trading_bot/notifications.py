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
from typing import Dict, Optional
from datetime import datetime


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
        email_config: Optional[Dict] = None
    ):
        """
        Initialize notification service

        Args:
            slack_webhook_url: Slack incoming webhook URL
                Get from: https://api.slack.com/messaging/webhooks
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

        # Email configuration
        self.email_config = email_config or self._load_email_config()

        # Log configuration
        if self.slack_webhook_url:
            logger.info("✓ Slack notifications enabled")
        else:
            logger.info("⚪ Slack notifications disabled (no webhook URL)")

        if self.email_config:
            logger.info("✓ Email notifications enabled")
        else:
            logger.info("⚪ Email notifications disabled (no email config)")

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

        try:
            # Format as Slack attachment for better visibility
            payload = {
                'attachments': [{
                    'color': color,
                    'text': message,
                    'footer': 'Trading Bot',
                    'ts': int(datetime.now().timestamp())
                }]
            }

            response = requests.post(
                self.slack_webhook_url,
                json=payload,
                timeout=10
            )

            if response.status_code == 200:
                logger.debug("✓ Slack notification sent")
                return True
            else:
                logger.error(f"✗ Slack notification failed: {response.status_code} {response.text}")
                return False

        except Exception as e:
            logger.error(f"✗ Slack notification error: {e}")
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
        total_return = session_summary.get('total_return', 0.0)
        sharpe = session_summary.get('sharpe_ratio', 0.0)
        max_dd = session_summary.get('max_drawdown', 0.0)
        win_rate = session_summary.get('win_rate', 0.0)
        num_trades = session_summary.get('num_trades', 0)

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
        slack_msg = f"""
⚠️ *트레이딩 봇 오류*

{error_msg}
        """.strip()

        if context:
            slack_msg += f"\n\n상황: {context}"

        slack_msg += f"\n\n시간: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"

        email_subject = "트레이딩 봇 오류 알림"
        email_body = f"""
오류 알림

{error_msg}

상황: {context or '없음'}
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
