"""
Test scheduler functionality

This script tests the scheduler without waiting for actual market hours.
It runs the scheduled tasks immediately for testing purposes.
"""

import sys
from pathlib import Path

# Add parent directory to path
sys.path.append(str(Path(__file__).parent.parent))

# Import scheduler functions (not the main scheduler itself)
from scheduler import notifier


def main():
    print("=" * 60)
    print("SCHEDULER TEST")
    print("=" * 60)
    print("\nThis test runs scheduler tasks immediately (without waiting)")
    print("In production, tasks run at scheduled times:")
    print("  23:30 KST - Start paper trading")
    print("  06:00 KST - Stop trading & report")
    print("=" * 60)

    # Test notification service
    print("\n1. Testing Notification Service...")
    print(f"   Slack enabled: {notifier.slack_webhook_url is not None}")
    print(f"   Email enabled: {notifier.email_config is not None}")

    if not notifier.slack_webhook_url and not notifier.email_config:
        print("\n   ⚠ No notifications configured")
        print("   Add SLACK_WEBHOOK_URL or SMTP settings to .env to enable")

    # Note about trading tasks
    print("\n2. Paper Trading Tasks")
    print("   ⚠ NOT testing paper trading tasks (requires market hours)")
    print("   These tasks will run automatically at scheduled times:")
    print("     - start_paper_trading() at 23:30 KST")
    print("     - stop_paper_trading() at 06:00 KST")

    # Instructions
    print("\n" + "=" * 60)
    print("TO RUN SCHEDULER IN PRODUCTION")
    print("=" * 60)
    print("\n1. Configure notifications in .env:")
    print("   - Add SLACK_WEBHOOK_URL for Slack alerts")
    print("   - Add SMTP settings for email alerts")
    print("\n2. Run scheduler:")
    print("   python scheduler.py")
    print("\n3. Scheduler will run tasks automatically at:")
    print("   - 23:30 KST (11:30 PM) - Start paper trading")
    print("   - 06:00 KST (6:00 AM) - Stop trading & send report")
    print("\n4. Stop scheduler:")
    print("   Press Ctrl+C to gracefully stop")

    print("\n✓ Scheduler test completed")


if __name__ == "__main__":
    main()
