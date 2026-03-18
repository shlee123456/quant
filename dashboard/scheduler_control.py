"""
Scheduler Container Control Module

Docker 컨테이너로 실행 중인 스케줄러를 제어하는 모듈

Features:
- 컨테이너 상태 확인 (실행 중/중지)
- 컨테이너 시작/중지
- 컨테이너 로그 조회 (tail)
- 스케줄 정보 표시

Usage:
    from dashboard.scheduler_control import SchedulerController

    controller = SchedulerController()
    status = controller.get_status()
    controller.start()
    controller.stop()
    logs = controller.get_logs(lines=100)
"""

import docker
from docker.errors import NotFound, APIError
from typing import Dict, Optional, List
import logging

logger = logging.getLogger(__name__)


class SchedulerController:
    """
    Docker 컨테이너 스케줄러 제어 클래스
    """

    # docker-compose.yml의 컨테이너 이름
    CONTAINER_NAME = "trading-bot-scheduler"

    def __init__(self):
        """
        Initialize Docker client

        Raises:
            docker.errors.DockerException: Docker 데몬 연결 실패
        """
        try:
            self.client = docker.from_env()
            # Docker 연결 테스트
            self.client.ping()
        except Exception as e:
            logger.error(f"Docker 클라이언트 초기화 실패: {e}")
            raise

    def get_status(self) -> Dict[str, any]:
        """
        스케줄러 컨테이너 상태 조회

        Returns:
            Dict with:
            - exists: 컨테이너 존재 여부 (bool)
            - running: 실행 중 여부 (bool)
            - status: 컨테이너 상태 문자열 (running/exited/created/...)
            - created: 생성 시간 (ISO format)
            - started: 시작 시간 (ISO format, 실행 중일 때만)
            - error: 에러 메시지 (오류 시)
        """
        try:
            container = self.client.containers.get(self.CONTAINER_NAME)

            # 컨테이너 정보 조회
            container.reload()  # 최신 상태 갱신

            status = container.status  # running, exited, created, etc.
            running = (status == 'running')

            result = {
                'exists': True,
                'running': running,
                'status': status,
                'created': container.attrs['Created'],
                'started': container.attrs['State'].get('StartedAt'),
                'finished': container.attrs['State'].get('FinishedAt'),
                'exit_code': container.attrs['State'].get('ExitCode'),
                'error': None
            }

            return result

        except NotFound:
            return {
                'exists': False,
                'running': False,
                'status': 'not_found',
                'created': None,
                'started': None,
                'error': f"컨테이너 '{self.CONTAINER_NAME}'를 찾을 수 없습니다."
            }
        except APIError as e:
            logger.error(f"Docker API 오류: {e}")
            return {
                'exists': False,
                'running': False,
                'status': 'error',
                'created': None,
                'started': None,
                'error': f"Docker API 오류: {str(e)}"
            }
        except Exception as e:
            logger.error(f"상태 조회 실패: {e}")
            return {
                'exists': False,
                'running': False,
                'status': 'error',
                'created': None,
                'started': None,
                'error': f"알 수 없는 오류: {str(e)}"
            }

    def start(self) -> Dict[str, any]:
        """
        스케줄러 컨테이너 시작

        Returns:
            Dict with:
            - success: 성공 여부 (bool)
            - message: 결과 메시지
            - error: 에러 메시지 (실패 시)
        """
        try:
            container = self.client.containers.get(self.CONTAINER_NAME)

            # 이미 실행 중인지 확인
            container.reload()
            if container.status == 'running':
                return {
                    'success': False,
                    'message': '스케줄러가 이미 실행 중입니다.',
                    'error': None
                }

            # 컨테이너 시작
            container.start()
            logger.info(f"스케줄러 컨테이너 시작: {self.CONTAINER_NAME}")

            return {
                'success': True,
                'message': '스케줄러가 성공적으로 시작되었습니다.',
                'error': None
            }

        except NotFound:
            # 컨테이너가 없으면 docker-compose up 필요
            return {
                'success': False,
                'message': f"컨테이너 '{self.CONTAINER_NAME}'를 찾을 수 없습니다.",
                'error': "docker-compose up -d 명령어로 컨테이너를 먼저 생성하세요."
            }
        except APIError as e:
            logger.error(f"컨테이너 시작 실패: {e}")
            return {
                'success': False,
                'message': '스케줄러 시작 실패',
                'error': str(e)
            }
        except Exception as e:
            logger.error(f"알 수 없는 오류: {e}")
            return {
                'success': False,
                'message': '스케줄러 시작 실패',
                'error': str(e)
            }

    def stop(self) -> Dict[str, any]:
        """
        스케줄러 컨테이너 중지

        Returns:
            Dict with:
            - success: 성공 여부 (bool)
            - message: 결과 메시지
            - error: 에러 메시지 (실패 시)
        """
        try:
            container = self.client.containers.get(self.CONTAINER_NAME)

            # 이미 중지되었는지 확인
            container.reload()
            if container.status != 'running':
                return {
                    'success': False,
                    'message': '스케줄러가 이미 중지되어 있습니다.',
                    'error': None
                }

            # 컨테이너 중지 (graceful shutdown, 10초 타임아웃)
            container.stop(timeout=10)
            logger.info(f"스케줄러 컨테이너 중지: {self.CONTAINER_NAME}")

            return {
                'success': True,
                'message': '스케줄러가 성공적으로 중지되었습니다.',
                'error': None
            }

        except NotFound:
            return {
                'success': False,
                'message': f"컨테이너 '{self.CONTAINER_NAME}'를 찾을 수 없습니다.",
                'error': None
            }
        except APIError as e:
            logger.error(f"컨테이너 중지 실패: {e}")
            return {
                'success': False,
                'message': '스케줄러 중지 실패',
                'error': str(e)
            }
        except Exception as e:
            logger.error(f"알 수 없는 오류: {e}")
            return {
                'success': False,
                'message': '스케줄러 중지 실패',
                'error': str(e)
            }

    def restart(self) -> Dict[str, any]:
        """
        스케줄러 컨테이너 재시작

        Returns:
            Dict with:
            - success: 성공 여부 (bool)
            - message: 결과 메시지
            - error: 에러 메시지 (실패 시)
        """
        try:
            container = self.client.containers.get(self.CONTAINER_NAME)

            # 컨테이너 재시작 (graceful restart, 10초 타임아웃)
            container.restart(timeout=10)
            logger.info(f"스케줄러 컨테이너 재시작: {self.CONTAINER_NAME}")

            return {
                'success': True,
                'message': '스케줄러가 성공적으로 재시작되었습니다.',
                'error': None
            }

        except NotFound:
            return {
                'success': False,
                'message': f"컨테이너 '{self.CONTAINER_NAME}'를 찾을 수 없습니다.",
                'error': None
            }
        except APIError as e:
            logger.error(f"컨테이너 재시작 실패: {e}")
            return {
                'success': False,
                'message': '스케줄러 재시작 실패',
                'error': str(e)
            }
        except Exception as e:
            logger.error(f"알 수 없는 오류: {e}")
            return {
                'success': False,
                'message': '스케줄러 재시작 실패',
                'error': str(e)
            }

    def get_logs(self, lines: int = 100, tail: bool = True) -> List[str]:
        """
        스케줄러 컨테이너 로그 조회

        Args:
            lines: 조회할 로그 라인 수
            tail: True면 최근 로그, False면 전체 로그

        Returns:
            로그 라인 리스트 (문자열)
        """
        try:
            container = self.client.containers.get(self.CONTAINER_NAME)

            # 로그 조회
            if tail:
                logs = container.logs(tail=lines, timestamps=True)
            else:
                logs = container.logs(timestamps=True)

            # bytes를 문자열로 변환
            log_lines = logs.decode('utf-8').split('\n')

            # 빈 라인 제거
            log_lines = [line for line in log_lines if line.strip()]

            return log_lines

        except NotFound:
            return [f"ERROR: 컨테이너 '{self.CONTAINER_NAME}'를 찾을 수 없습니다."]
        except APIError as e:
            logger.error(f"로그 조회 실패: {e}")
            return [f"ERROR: 로그 조회 실패 - {str(e)}"]
        except Exception as e:
            logger.error(f"알 수 없는 오류: {e}")
            return [f"ERROR: 알 수 없는 오류 - {str(e)}"]

    def get_schedule_info(self) -> Dict[str, any]:
        """Get current schedule information with DST auto-detection."""
        try:
            from trading_bot.us_market_hours import get_market_hours_kst
            hours = get_market_hours_kst()
            label = hours['et_label']
            dst_mode = '서머타임' if hours['is_dst'] else '윈터타임'
            open_str = f"{hours['open']['hour']:02d}:{hours['open']['minute']:02d}"
            close_str = f"{hours['close']['hour']:02d}:{hours['close']['minute']:02d}"
        except ImportError:
            label = 'ET'
            dst_mode = '알 수 없음'
            open_str = '??:??'
            close_str = '??:??'

        return {
            'timezone': f'Asia/Seoul (KST) — {dst_mode} ({label})',
            'schedules': [
                {
                    'time': f'{open_str} KST',
                    'job': '페이퍼 트레이딩 시작',
                    'description': f'미국 시장 개장 (정규장 {open_str}-{close_str})'
                },
                {
                    'time': f'{close_str} KST',
                    'job': '페이퍼 트레이딩 중지',
                    'description': '미국 시장 마감, 리포트 생성 및 Slack 전송'
                }
            ],
            'market_hours': {
                'name': 'US Stock Market',
                'open': f'{open_str} KST (09:30 {label})',
                'close': f'{close_str} KST (16:00 {label})',
                'timezone': 'US/Eastern'
            }
        }

    def check_docker_available(self) -> Dict[str, any]:
        """
        Docker 데몬 연결 가능 여부 확인

        Returns:
            Dict with:
            - available: Docker 사용 가능 여부 (bool)
            - version: Docker 버전 정보 (사용 가능 시)
            - error: 에러 메시지 (사용 불가 시)
        """
        try:
            # Docker 버전 정보 조회
            version_info = self.client.version()

            return {
                'available': True,
                'version': version_info.get('Version', 'Unknown'),
                'api_version': version_info.get('ApiVersion', 'Unknown'),
                'error': None
            }

        except Exception as e:
            logger.error(f"Docker 연결 실패: {e}")
            return {
                'available': False,
                'version': None,
                'api_version': None,
                'error': str(e)
            }
