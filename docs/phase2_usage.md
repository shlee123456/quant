# Phase 2: Automated Scheduler Usage Guide

## Overview

Phase 2 introduces automated scheduling and notification features to run paper trading sessions automatically during US market hours.

## Features

### 1. Automated Scheduling
- **Pre-market** (23:00 KST): Strategy parameter optimization
- **Market open** (23:30 KST): Start paper trading session
- **Market close** (06:00 KST): Stop trading and generate report

### 2. Notifications
- **Slack**: Real-time alerts via webhook
- **Email**: SMTP-based notifications
- **Events**:
  - Trade execution alerts
  - Session start/end notifications
  - Daily performance reports
  - Error alerts

## Setup

### 1. Install Dependencies

```bash
pip install -r requirements.txt
```

New dependencies in Phase 2:
- `APScheduler>=3.10.0` - Task scheduling
- `requests>=2.31.0` - HTTP requests for Slack
- `python-dotenv>=1.0.0` - Environment variables

### 2. Configure Notifications

Edit `.env` file:

#### Slack Notifications

```bash
# Get webhook URL from https://api.slack.com/messaging/webhooks
SLACK_WEBHOOK_URL=https://hooks.slack.com/services/YOUR/WEBHOOK/URL
```

#### Email Notifications

```bash
# Gmail example (use App Password, not regular password)
SMTP_SERVER=smtp.gmail.com
SMTP_PORT=587
SMTP_USERNAME=your_email@gmail.com
SMTP_PASSWORD=your_app_password
SMTP_FROM=your_email@gmail.com
SMTP_TO=recipient1@example.com,recipient2@example.com
```

**Gmail App Password Setup**:
1. Go to Google Account settings
2. Enable 2-factor authentication
3. Go to Security → App passwords
4. Generate new app password for "Mail"
5. Use this password in `SMTP_PASSWORD`

## Usage

### Run Scheduler

```bash
python scheduler.py
```

Output:
```
============================================================
AUTOMATED TRADING SCHEDULER
============================================================
Timezone: Asia/Seoul
Schedule:
  23:00 KST - Strategy optimization
  23:30 KST - Start paper trading
  06:00 KST - Stop trading & report
============================================================

✓ Scheduler started successfully
Press Ctrl+C to stop
```

### Stop Scheduler

Press `Ctrl+C` to gracefully stop:
- Active trading sessions will be stopped
- Final reports will be generated
- Session data will be saved to database

## Testing

### Test Notifications

```bash
python examples/test_notifications.py
```

Tests:
- Slack webhook (if configured)
- Email SMTP (if configured)
- Message formatting

### Test Scheduler Tasks

```bash
python examples/test_scheduler.py
```

Tests:
- Strategy optimization task
- Notification integration
- Error handling

## Notification Examples

### Trade Alert (Slack)

```
🟢 BUY AAPL
Price: $150.25
Size: 10.00 shares
Value: $1,502.50
Time: 2024-01-01 10:30:00
```

### Daily Report (Slack)

```
🚀 Daily Trading Report

Strategy: RSI_14_70_30
Total Return: +2.50%
Sharpe Ratio: 1.45
Max Drawdown: -3.20%
Win Rate: 65.0%
Total Trades: 12

Date: 2024-01-01
```

### Error Alert (Slack)

```
⚠️ Trading Bot Error

API rate limit exceeded

Context: Fetching OHLCV data
Time: 2024-01-01 10:30:00
```

## Logs

Scheduler logs are saved to `logs/scheduler.log`:

```bash
# View logs
tail -f logs/scheduler.log

# View last 50 lines
tail -50 logs/scheduler.log
```

## Production Deployment

### Using systemd (Linux)

Create `/etc/systemd/system/trading-scheduler.service`:

```ini
[Unit]
Description=Trading Bot Scheduler
After=network.target

[Service]
Type=simple
User=your_username
WorkingDirectory=/path/to/crypto-trading-bot
ExecStart=/usr/bin/python3 scheduler.py
Restart=on-failure
RestartSec=10

[Install]
WantedBy=multi-user.target
```

Enable and start:
```bash
sudo systemctl enable trading-scheduler
sudo systemctl start trading-scheduler
sudo systemctl status trading-scheduler
```

### Using Docker

```bash
# Build image
docker-compose build

# Run scheduler
docker-compose up -d

# View logs
docker-compose logs -f
```

## Troubleshooting

### Notifications Not Sending

1. **Check configuration**:
   ```bash
   python examples/test_notifications.py
   ```

2. **Verify environment variables**:
   ```bash
   grep -E "^SLACK|^SMTP" .env
   ```

3. **Check logs**:
   ```bash
   tail -50 logs/scheduler.log
   ```

### Scheduler Not Running Tasks

1. **Verify timezone**:
   ```bash
   python -c "import pytz; print(pytz.timezone('Asia/Seoul').localize(datetime.now()))"
   ```

2. **Check APScheduler logs** in `logs/scheduler.log`

3. **Test tasks manually**:
   ```bash
   python examples/test_scheduler.py
   ```

### KIS Broker Connection Issues

1. **Check API credentials** in `.env`
2. **Verify market hours** (US market: 23:30-06:00 KST)
3. **Check rate limits** (KIS API: ~1 call per minute)

## Advanced Configuration

### Custom Schedule

Edit `scheduler.py`:

```python
# Run optimization at different time
scheduler.add_job(
    optimize_strategy,
    CronTrigger(hour=22, minute=30),  # 22:30 instead of 23:00
    id='optimize_strategy'
)
```

### Custom Trading Hours

```python
# Extended hours trading
scheduler.add_job(
    start_paper_trading,
    CronTrigger(hour=19, minute=0),  # Start earlier
    id='start_trading'
)
```

### Multiple Strategies

Modify `start_paper_trading()` in `scheduler.py` to run multiple strategies in parallel.

## Next Steps

- **Phase 3**: Live trading with real money (use with caution!)
- **Phase 4**: Advanced features (LLM integration, ML strategies, portfolio optimization)

See `docs/roadmap.md` for details.
