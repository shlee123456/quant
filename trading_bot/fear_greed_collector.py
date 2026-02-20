"""
Fear & Greed Index Collector - CNN Fear & Greed Index 수집기

CNN Fear & Greed Index API에서 데이터를 수집하고
matplotlib 차트를 생성합니다.

Usage:
    from trading_bot.fear_greed_collector import FearGreedCollector

    collector = FearGreedCollector()
    data = collector.collect(limit=30)
    # data['current']['value'] → 현재 F&G 값
    # data['chart_path'] → 생성된 차트 PNG 경로
"""

import logging
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

import requests

logger = logging.getLogger(__name__)

# CNN Fear & Greed API 엔드포인트
CNN_FEAR_GREED_API = "https://production.dataviz.cnn.io/index/fearandgreed/graphdata"


def _classify_value(value: float) -> str:
    """F&G 값을 분류 문자열로 변환"""
    if value < 25:
        return "Extreme Fear"
    elif value < 45:
        return "Fear"
    elif value < 55:
        return "Neutral"
    elif value < 75:
        return "Greed"
    else:
        return "Extreme Greed"


class FearGreedCollector:
    """CNN Fear & Greed Index API에서 데이터를 수집하고 차트를 생성하는 클래스"""

    def __init__(self, timeout: float = 10.0):
        """
        Args:
            timeout: API 요청 타임아웃(초)
        """
        self.timeout = timeout

    def collect(self, limit: int = 30) -> Optional[Dict]:
        """
        CNN Fear & Greed Index 현재값 + 히스토리 수집

        Args:
            limit: 히스토리 일수 (기본 30)

        Returns:
            수집된 데이터 딕셔너리 또는 None (실패 시)
        """
        try:
            response = requests.get(
                CNN_FEAR_GREED_API,
                headers={
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                                  "AppleWebKit/537.36 (KHTML, like Gecko) "
                                  "Chrome/120.0.0.0 Safari/537.36",
                    "Accept": "application/json",
                },
                timeout=self.timeout,
            )
            response.raise_for_status()
            raw = response.json()
        except requests.RequestException as e:
            logger.warning(f"CNN Fear & Greed API 호출 실패: {e}")
            return None
        except ValueError as e:
            logger.warning(f"CNN Fear & Greed API JSON 파싱 실패: {e}")
            return None

        return self._parse_response(raw, limit)

    def _parse_response(self, raw: Dict, limit: int) -> Optional[Dict]:
        """API 응답을 구조화된 딕셔너리로 파싱"""
        try:
            # 현재 값 추출
            fear_greed = raw.get("fear_and_greed", {})
            current_score = float(fear_greed.get("score", 0))
            current_rating = fear_greed.get("rating", "")
            timestamp = fear_greed.get("timestamp", "")

            # 타임스탬프 파싱
            if timestamp:
                try:
                    ts_dt = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
                    timestamp_str = ts_dt.strftime("%Y-%m-%dT%H:%M:%S")
                except (ValueError, AttributeError):
                    timestamp_str = timestamp
            else:
                timestamp_str = datetime.now().strftime("%Y-%m-%dT%H:%M:%S")

            current = {
                "value": round(current_score, 1),
                "classification": current_rating or _classify_value(current_score),
                "timestamp": timestamp_str,
            }

            # 히스토리 추출 (fear_and_greed_historical.data)
            historical = raw.get("fear_and_greed_historical", {})
            history_data = historical.get("data", [])

            history = []
            for item in history_data:
                try:
                    x_val = item.get("x", 0)
                    y_val = float(item.get("y", 0))
                    # x는 밀리초 타임스탬프
                    dt = datetime.fromtimestamp(x_val / 1000)
                    history.append({
                        "date": dt.strftime("%Y-%m-%d"),
                        "value": round(y_val, 1),
                        "classification": item.get("rating", _classify_value(y_val)),
                    })
                except (ValueError, TypeError, OSError):
                    continue

            # 최신순 정렬 후 limit 적용
            history.sort(key=lambda h: h["date"], reverse=True)
            history = history[:limit]

            logger.info(
                f"Fear & Greed Index 수집 완료: 현재 {current['value']} ({current['classification']}), "
                f"히스토리 {len(history)}건"
            )

            return {
                "current": current,
                "history": history,
            }

        except Exception as e:
            logger.warning(f"Fear & Greed 데이터 파싱 실패: {e}")
            return None

    def generate_chart(self, data: Dict, output_dir: str = "data/market_analysis/charts") -> Optional[str]:
        """
        Fear & Greed Index matplotlib 차트 생성

        Args:
            data: collect() 반환 데이터
            output_dir: 차트 저장 디렉토리

        Returns:
            생성된 PNG 파일 경로 또는 None (실패 시)
        """
        try:
            import matplotlib
            matplotlib.use("Agg")
            import matplotlib.pyplot as plt
            import matplotlib.patches as mpatches
            import numpy as np
        except ImportError:
            logger.warning("matplotlib 미설치 - 차트 생성 건너뜀")
            return None

        try:
            current = data["current"]
            history = data.get("history", [])

            fig, axes = plt.subplots(2, 1, figsize=(12, 8), gridspec_kw={"height_ratios": [1, 1.2]})
            fig.suptitle("CNN Fear & Greed Index", fontsize=16, fontweight="bold", y=0.98)

            # ── 상단: 게이지 차트 ──
            ax_gauge = axes[0]
            self._draw_gauge(ax_gauge, current["value"], current["classification"])

            # ── 하단: 히스토리 라인 차트 ──
            ax_hist = axes[1]
            self._draw_history(ax_hist, history)

            plt.tight_layout(rect=[0, 0, 1, 0.95])

            # 저장
            out_path = Path(output_dir)
            out_path.mkdir(parents=True, exist_ok=True)

            today = datetime.now().strftime("%Y-%m-%d")
            file_path = out_path / f"fear_greed_{today}.png"
            fig.savefig(str(file_path), dpi=150, bbox_inches="tight", facecolor="white")
            plt.close(fig)

            logger.info(f"Fear & Greed 차트 저장: {file_path}")
            return str(file_path)

        except Exception as e:
            logger.warning(f"Fear & Greed 차트 생성 실패: {e}")
            plt.close("all")
            return None

    def _draw_gauge(self, ax, value: float, classification: str):
        """게이지 차트 그리기 (0-100 스펙트럼)"""
        import matplotlib.pyplot as plt
        import matplotlib.patches as mpatches
        import numpy as np

        ax.set_xlim(0, 100)
        ax.set_ylim(0, 1)
        ax.set_aspect("auto")
        ax.axis("off")

        # 색상 구간 배경
        zones = [
            (0, 25, "#d32f2f", "Extreme Fear"),
            (25, 45, "#ff9800", "Fear"),
            (45, 55, "#fdd835", "Neutral"),
            (55, 75, "#8bc34a", "Greed"),
            (75, 100, "#2e7d32", "Extreme Greed"),
        ]

        bar_y = 0.35
        bar_height = 0.2

        for start, end, color, label in zones:
            rect = mpatches.FancyBboxPatch(
                (start, bar_y), end - start, bar_height,
                boxstyle="round,pad=0.01",
                facecolor=color, alpha=0.7, edgecolor="none",
            )
            ax.add_patch(rect)
            # 구간 라벨
            mid = (start + end) / 2
            ax.text(mid, bar_y - 0.08, label, ha="center", va="top", fontsize=7, color="#555555")

        # 현재 값 마커 (삼각형)
        ax.plot(value, bar_y + bar_height + 0.05, marker="v", markersize=14,
                color="#333333", zorder=5)

        # 현재 값 텍스트
        ax.text(50, 0.85, f"{value:.0f}", ha="center", va="center",
                fontsize=36, fontweight="bold", color="#333333")
        ax.text(50, 0.68, classification, ha="center", va="center",
                fontsize=14, color="#666666")

    def _draw_history(self, ax, history: List[Dict]):
        """히스토리 라인 차트 그리기"""
        import matplotlib.pyplot as plt
        import matplotlib.dates as mdates
        import numpy as np

        if not history:
            ax.text(0.5, 0.5, "No historical data", ha="center", va="center",
                    transform=ax.transAxes, fontsize=12, color="#999999")
            ax.set_xlim(0, 1)
            ax.set_ylim(0, 100)
            return

        # 날짜순 정렬 (오래된→최신)
        sorted_hist = sorted(history, key=lambda h: h["date"])
        dates = [datetime.strptime(h["date"], "%Y-%m-%d") for h in sorted_hist]
        values = [h["value"] for h in sorted_hist]

        # 배경 영역 색칠
        ax.axhspan(0, 25, facecolor="#d32f2f", alpha=0.08)
        ax.axhspan(25, 45, facecolor="#ff9800", alpha=0.08)
        ax.axhspan(45, 55, facecolor="#fdd835", alpha=0.08)
        ax.axhspan(55, 75, facecolor="#8bc34a", alpha=0.08)
        ax.axhspan(75, 100, facecolor="#2e7d32", alpha=0.08)

        # 수평 구분선
        for level in [25, 45, 55, 75]:
            ax.axhline(y=level, color="#cccccc", linewidth=0.5, linestyle="--")

        # 라인 차트
        ax.plot(dates, values, color="#1565c0", linewidth=2, marker="o",
                markersize=3, markerfacecolor="#1565c0", zorder=3)

        # 영역 라벨 (우측)
        labels = [
            (12.5, "Extreme\nFear", "#d32f2f"),
            (35, "Fear", "#ff9800"),
            (50, "Neutral", "#999999"),
            (65, "Greed", "#8bc34a"),
            (87.5, "Extreme\nGreed", "#2e7d32"),
        ]
        for y_pos, label, color in labels:
            ax.text(1.02, y_pos / 100, label, ha="left", va="center",
                    transform=ax.get_yaxis_transform(), fontsize=7, color=color)

        ax.set_ylim(0, 100)
        ax.set_ylabel("Fear & Greed Index", fontsize=10)
        ax.set_title("30-Day History", fontsize=11, pad=8)

        # X축 날짜 포맷
        ax.xaxis.set_major_formatter(mdates.DateFormatter("%m/%d"))
        ax.xaxis.set_major_locator(mdates.AutoDateLocator(minticks=5, maxticks=12))
        plt.setp(ax.xaxis.get_majorticklabels(), rotation=45, ha="right")

        ax.grid(axis="y", alpha=0.3)
        ax.spines["top"].set_visible(False)
        ax.spines["right"].set_visible(False)
