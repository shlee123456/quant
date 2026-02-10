"""
Trading Report Generator

일일 트레이딩 리포트를 CSV, JSON 형식으로 생성합니다.

Usage:
    from trading_bot.reports import ReportGenerator
    from trading_bot.database import TradingDatabase

    db = TradingDatabase()
    generator = ReportGenerator(db)

    # CSV 리포트 생성
    generator.generate_session_report(session_id, output_dir='reports/')
"""

import os
import csv
import json
import logging
from pathlib import Path
from datetime import datetime
from typing import Optional, Dict, List

from trading_bot.database import TradingDatabase


logger = logging.getLogger(__name__)


class ReportGenerator:
    """
    트레이딩 세션 리포트 생성기

    세션 데이터를 CSV, JSON 형식으로 내보냅니다.
    """

    def __init__(self, db: TradingDatabase):
        """
        Initialize report generator

        Args:
            db: TradingDatabase instance
        """
        self.db = db

    def _sanitize_session_id(self, session_id: str) -> str:
        """
        세션 ID를 파일명에 안전한 형식으로 변환

        Args:
            session_id: Original session ID

        Returns:
            Sanitized session ID safe for filenames
        """
        return session_id.replace(':', '_').replace(' ', '_')

    def generate_session_report(
        self,
        session_id: str,
        output_dir: str = 'reports/',
        formats: Optional[List[str]] = None
    ) -> Dict[str, str]:
        """
        세션 리포트 생성

        Args:
            session_id: Session ID
            output_dir: Output directory for reports
            formats: List of formats to generate ['csv', 'json']
                     If None, generates both

        Returns:
            Dict mapping format to file path
            Example: {'csv': 'reports/2026-02-09/session_123.csv', 'json': 'reports/2026-02-09/session_123.json'}
        """
        if formats is None:
            formats = ['csv', 'json']

        # Get session data
        summary = self.db.get_session_summary(session_id)
        if not summary:
            logger.error(f"Session {session_id} not found")
            return {}

        trades = self.db.get_session_trades(session_id)
        snapshots = self.db.get_session_snapshots(session_id)

        # Extract date from session start_time and create date-based directory
        start_time = summary.get('start_time', '')
        if start_time:
            # Parse date from start_time (handles both ISO format and regular format)
            # ISO format: 2026-02-09T23:30:01.853558
            # Regular format: 2026-02-09 23:30:01
            try:
                if 'T' in start_time:
                    date_str = start_time.split('T')[0]  # ISO format
                else:
                    date_str = start_time.split()[0]  # Regular format
            except (IndexError, AttributeError):
                logger.warning(f"Failed to parse start_time: {start_time}, using current date")
                date_str = datetime.now().strftime('%Y-%m-%d')
        else:
            # Fallback to current date
            date_str = datetime.now().strftime('%Y-%m-%d')

        # Create date-based subdirectory
        date_output_dir = os.path.join(output_dir, date_str)
        Path(date_output_dir).mkdir(parents=True, exist_ok=True)

        # Generate reports
        output_files = {}

        if 'csv' in formats:
            csv_path = self._generate_csv_report(
                session_id, summary, trades, snapshots, date_output_dir
            )
            output_files['csv'] = csv_path

        if 'json' in formats:
            json_path = self._generate_json_report(
                session_id, summary, trades, snapshots, date_output_dir
            )
            output_files['json'] = json_path

        logger.info(f"✓ Reports generated for session {session_id}")
        for format_name, path in output_files.items():
            logger.info(f"  {format_name.upper()}: {path}")

        return output_files

    def _generate_csv_report(
        self,
        session_id: str,
        summary: Dict,
        trades: List[Dict],
        snapshots: List[Dict],
        output_dir: str
    ) -> str:
        """
        Generate CSV report

        Creates two CSV files:
        - {session_id}_trades.csv: Trade history
        - {session_id}_snapshots.csv: Portfolio snapshots
        """
        # Sanitize session_id for filename
        safe_session_id = self._sanitize_session_id(session_id)

        # 1. Generate trades CSV
        trades_file = os.path.join(output_dir, f'{safe_session_id}_trades.csv')

        if trades:
            with open(trades_file, 'w', newline='', encoding='utf-8') as f:
                # Define columns
                fieldnames = [
                    'timestamp', 'symbol', 'type', 'price', 'size',
                    'commission', 'pnl', 'portfolio_value'
                ]
                writer = csv.DictWriter(f, fieldnames=fieldnames)

                writer.writeheader()
                for trade in trades:
                    writer.writerow({
                        'timestamp': trade['timestamp'],
                        'symbol': trade['symbol'],
                        'type': trade['type'],
                        'price': trade['price'],
                        'size': trade['size'],
                        'commission': trade.get('commission', 0),
                        'pnl': trade.get('pnl', 0),
                        'portfolio_value': trade.get('portfolio_value', 0)
                    })

            logger.info(f"  Trades CSV: {trades_file}")

        # 2. Generate snapshots CSV
        snapshots_file = os.path.join(output_dir, f'{safe_session_id}_snapshots.csv')

        if snapshots:
            with open(snapshots_file, 'w', newline='', encoding='utf-8') as f:
                fieldnames = ['timestamp', 'total_value', 'cash', 'positions']
                writer = csv.DictWriter(f, fieldnames=fieldnames)

                writer.writeheader()
                for snapshot in snapshots:
                    writer.writerow({
                        'timestamp': snapshot['timestamp'],
                        'total_value': snapshot['total_value'],
                        'cash': snapshot['cash'],
                        'positions': snapshot['positions']  # JSON string
                    })

            logger.info(f"  Snapshots CSV: {snapshots_file}")

        # 3. Generate summary CSV
        summary_file = os.path.join(output_dir, f'{safe_session_id}_summary.csv')

        with open(summary_file, 'w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)

            # Write summary as key-value pairs
            # Handle None values from database (use 0.0 if None, but preserve 0 values)
            total_return = summary.get('total_return', 0.0) if summary.get('total_return') is not None else 0.0
            sharpe_ratio = summary.get('sharpe_ratio', 0.0) if summary.get('sharpe_ratio') is not None else 0.0
            max_drawdown = summary.get('max_drawdown', 0.0) if summary.get('max_drawdown') is not None else 0.0
            win_rate_value = summary.get('win_rate')
            win_rate = win_rate_value if win_rate_value is not None else 0.0

            writer.writerow(['Metric', 'Value'])
            writer.writerow(['Session ID', session_id])
            writer.writerow(['Strategy', summary.get('strategy_name', 'N/A')])
            writer.writerow(['Start Time', summary.get('start_time', 'N/A')])
            writer.writerow(['End Time', summary.get('end_time', 'N/A')])
            writer.writerow(['Initial Capital', f"${summary.get('initial_capital', 0):,.2f}"])
            writer.writerow(['Final Capital', f"${summary.get('final_capital', 0):,.2f}"])
            writer.writerow(['Total Return', f"{total_return:.2f}%"])
            writer.writerow(['Sharpe Ratio', f"{sharpe_ratio:.2f}"])
            writer.writerow(['Max Drawdown', f"{max_drawdown:.2f}%"])
            writer.writerow(['Win Rate', f"{win_rate:.2f}%"])
            writer.writerow(['Total Trades', len(trades)])

        logger.info(f"  Summary CSV: {summary_file}")

        return summary_file

    def _generate_json_report(
        self,
        session_id: str,
        summary: Dict,
        trades: List[Dict],
        snapshots: List[Dict],
        output_dir: str
    ) -> str:
        """
        Generate JSON report

        Creates a single JSON file with all session data
        """
        safe_session_id = self._sanitize_session_id(session_id)
        json_file = os.path.join(output_dir, f'{safe_session_id}_report.json')

        # Combine all data
        report_data = {
            'session_id': session_id,
            'summary': summary,
            'trades': trades,
            'snapshots': snapshots,
            'generated_at': datetime.now().isoformat()
        }

        with open(json_file, 'w', encoding='utf-8') as f:
            json.dump(report_data, f, indent=2, ensure_ascii=False)

        logger.info(f"  JSON Report: {json_file}")

        return json_file

    def generate_daily_summary(
        self,
        output_dir: str = 'reports/',
        date: Optional[str] = None
    ) -> str:
        """
        일일 전체 세션 요약 리포트 생성

        Args:
            output_dir: Output directory
            date: Date string (YYYY-MM-DD). If None, uses today

        Returns:
            Path to summary CSV file
        """
        if date is None:
            date = datetime.now().strftime('%Y-%m-%d')

        # Create date-based subdirectory
        date_output_dir = os.path.join(output_dir, date)
        Path(date_output_dir).mkdir(parents=True, exist_ok=True)

        # Get all sessions
        all_sessions = self.db.get_all_sessions()

        # Filter sessions by date
        daily_sessions = [
            s for s in all_sessions
            if s.get('start_time', '').startswith(date)
        ]

        if not daily_sessions:
            logger.warning(f"No sessions found for date {date}")
            return ''

        # Generate summary CSV
        summary_file = os.path.join(date_output_dir, f'daily_summary_{date}.csv')

        with open(summary_file, 'w', newline='', encoding='utf-8') as f:
            fieldnames = [
                'session_id', 'strategy_name', 'start_time', 'end_time',
                'initial_capital', 'final_capital', 'total_return',
                'sharpe_ratio', 'max_drawdown', 'win_rate', 'status'
            ]
            writer = csv.DictWriter(f, fieldnames=fieldnames)

            writer.writeheader()
            for session in daily_sessions:
                writer.writerow({
                    'session_id': session.get('session_id', ''),
                    'strategy_name': session.get('strategy_name', ''),
                    'start_time': session.get('start_time', ''),
                    'end_time': session.get('end_time', ''),
                    'initial_capital': session.get('initial_capital', 0),
                    'final_capital': session.get('final_capital', 0),
                    'total_return': session.get('total_return', 0),
                    'sharpe_ratio': session.get('sharpe_ratio', 0),
                    'max_drawdown': session.get('max_drawdown', 0),
                    'win_rate': session.get('win_rate', 0),
                    'status': session.get('status', '')
                })

        logger.info(f"✓ Daily summary generated: {summary_file}")
        logger.info(f"  Sessions: {len(daily_sessions)}")

        return summary_file
