"""
Slack 채널 디버그 스크립트

Bot이 접근 가능한 채널 목록을 확인합니다.
"""

import os
import sys
from pathlib import Path
from dotenv import load_dotenv

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

# Load environment
load_dotenv()

def main():
    bot_token = os.getenv('SLACK_BOT_TOKEN')

    if not bot_token:
        print("❌ SLACK_BOT_TOKEN이 설정되지 않았습니다.")
        return

    print("🔍 Slack Bot 정보 확인 중...\n")

    try:
        from slack_sdk import WebClient
        from slack_sdk.errors import SlackApiError

        client = WebClient(token=bot_token)

        # 1. Bot 정보 확인
        print("=" * 60)
        print("1. Bot 정보")
        print("=" * 60)
        try:
            auth_test = client.auth_test()
            print(f"✓ Bot 이름: {auth_test['user']}")
            print(f"✓ Bot ID: {auth_test['user_id']}")
            print(f"✓ Team: {auth_test['team']}")
            print(f"✓ Team ID: {auth_test['team_id']}")
        except SlackApiError as e:
            print(f"❌ Bot 정보 조회 실패: {e.response['error']}")
            return

        # 2. Bot이 속한 채널 목록
        print("\n" + "=" * 60)
        print("2. Bot이 참여 중인 채널")
        print("=" * 60)
        try:
            conversations = client.conversations_list(
                types="public_channel,private_channel",
                limit=100
            )

            bot_channels = []
            for channel in conversations['channels']:
                if channel.get('is_member', False):
                    bot_channels.append(channel)
                    print(f"✓ {channel['name']} (ID: {channel['id']})")

            if not bot_channels:
                print("⚠️  Bot이 참여 중인 채널이 없습니다.")
                print("\n해결 방법:")
                print("1. Slack 채널로 이동")
                print("2. 채널에서 '/invite @Bot이름' 실행")
                print("   또는")
                print("3. 채널 설정 → Integrations → Add apps에서 Bot 추가")
        except SlackApiError as e:
            print(f"❌ 채널 목록 조회 실패: {e.response['error']}")

        # 3. 모든 public 채널 (참조용)
        print("\n" + "=" * 60)
        print("3. 모든 Public 채널 (참조용)")
        print("=" * 60)
        try:
            all_channels = client.conversations_list(
                types="public_channel",
                exclude_archived=True,
                limit=100
            )

            for channel in all_channels['channels']:
                is_member = "✓ 참여중" if channel.get('is_member', False) else "  미참여"
                print(f"{is_member} - #{channel['name']} (ID: {channel['id']})")
        except SlackApiError as e:
            print(f"❌ 채널 목록 조회 실패: {e.response['error']}")

        # 4. 현재 .env 설정
        print("\n" + "=" * 60)
        print("4. 현재 .env 설정")
        print("=" * 60)
        print(f"SLACK_CHANNEL: {os.getenv('SLACK_CHANNEL', '설정 안 됨')}")

        # 5. 권장 설정
        print("\n" + "=" * 60)
        print("5. 권장 설정")
        print("=" * 60)
        if bot_channels:
            recommended_channel = bot_channels[0]
            print(f"\n.env 파일에 다음과 같이 설정하세요:")
            print(f"SLACK_CHANNEL=#{recommended_channel['name']}")
            print(f"또는")
            print(f"SLACK_CHANNEL={recommended_channel['id']}")
        else:
            print("⚠️  먼저 Bot을 채널에 초대하세요.")

    except ImportError:
        print("❌ slack-sdk가 설치되지 않았습니다.")
        print("   pip install slack-sdk 실행 후 다시 시도하세요.")
    except Exception as e:
        print(f"❌ 오류 발생: {e}")


if __name__ == '__main__':
    main()
