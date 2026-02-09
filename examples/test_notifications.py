"""
Test notification service

Tests Slack and Email notifications without actually sending them.
"""

import sys
from pathlib import Path
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Add parent directory to path
sys.path.append(str(Path(__file__).parent.parent))

from trading_bot.notifications import NotificationService


def main():
    print("=" * 60)
    print("NOTIFICATION SERVICE TEST")
    print("=" * 60)

    # Initialize notification service (without credentials, just for testing)
    notifier = NotificationService()

    print("\nService initialized:")
    print(f"  Slack enabled: {notifier.slack_webhook_url is not None}")
    print(f"  Email enabled: {notifier.email_config is not None}")

    # Test 1: Trade notification
    print("\n" + "=" * 60)
    print("TEST 1: Trade Notification")
    print("=" * 60)

    trade = {
        'type': 'BUY',
        'symbol': 'AAPL',
        'price': 150.25,
        'size': 10.0
    }

    print("\nTrade data:")
    print(f"  Type: {trade['type']}")
    print(f"  Symbol: {trade['symbol']}")
    print(f"  Price: ${trade['price']:.2f}")
    print(f"  Size: {trade['size']:.2f} shares")

    result = notifier.notify_trade(trade)
    print(f"\nNotification sent: {result}")
    print("(No actual notification sent - credentials not configured)")

    # Test 2: Daily report
    print("\n" + "=" * 60)
    print("TEST 2: Daily Report")
    print("=" * 60)

    session_summary = {
        'strategy_name': 'RSI_14_70_30',
        'total_return': 2.5,
        'sharpe_ratio': 1.45,
        'max_drawdown': -3.2,
        'win_rate': 65.0,
        'num_trades': 12
    }

    print("\nSession summary:")
    print(f"  Strategy: {session_summary['strategy_name']}")
    print(f"  Return: {session_summary['total_return']:+.2f}%")
    print(f"  Sharpe: {session_summary['sharpe_ratio']:.2f}")
    print(f"  Max DD: {session_summary['max_drawdown']:.2f}%")
    print(f"  Win Rate: {session_summary['win_rate']:.1f}%")

    result = notifier.notify_daily_report(session_summary)
    print(f"\nNotification sent: {result}")
    print("(No actual notification sent - credentials not configured)")

    # Test 3: Error notification
    print("\n" + "=" * 60)
    print("TEST 3: Error Notification")
    print("=" * 60)

    error_msg = "API rate limit exceeded"
    context = "Fetching OHLCV data"

    print(f"\nError: {error_msg}")
    print(f"Context: {context}")

    result = notifier.notify_error(error_msg, context)
    print(f"\nNotification sent: {result}")
    print("(No actual notification sent - credentials not configured)")

    # Instructions
    print("\n" + "=" * 60)
    print("TO ENABLE NOTIFICATIONS")
    print("=" * 60)
    print("\n1. Slack Notifications:")
    print("   - Get webhook URL from https://api.slack.com/messaging/webhooks")
    print("   - Add to .env: SLACK_WEBHOOK_URL=https://hooks.slack.com/...")
    print("\n2. Email Notifications:")
    print("   - Add SMTP settings to .env:")
    print("     SMTP_SERVER=smtp.gmail.com")
    print("     SMTP_PORT=587")
    print("     SMTP_USERNAME=your_email@gmail.com")
    print("     SMTP_PASSWORD=your_app_password")
    print("     SMTP_FROM=your_email@gmail.com")
    print("     SMTP_TO=recipient@example.com")
    print("\n✓ Test completed successfully")


if __name__ == "__main__":
    main()
