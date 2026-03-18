"""
Korean Stock Symbol Database and Search Utilities

한국 KOSPI/KOSDAQ 주요 종목 데이터베이스.
대시보드에서 한국 주식 종목 선택 및 프리셋 제공.
"""

from typing import List, Dict, Optional


# 한국 주요 종목 프리셋
KR_PRESETS: Dict[str, List[str]] = {
    '대형주 TOP10': [
        '005930', '000660', '005380', '035420', '035720',
        '006400', '373220', '005490', '105560', '207940',
    ],
    '반도체': ['005930', '000660', '042700', '058470'],
    '2차전지': ['373220', '006400', '051910', '003670'],
    '바이오': ['207940', '068270', '326030', '091990'],
    '금융': ['105560', '055550', '086790', '316140'],
    '배당주': ['017670', '032830', '000810', '015760'],
    '인터넷/플랫폼': ['035420', '035720', '263750'],
}


class KRStockSymbolDB:
    """한국 KOSPI/KOSDAQ 주요 종목 데이터베이스"""

    def __init__(self) -> None:
        """종목 데이터베이스 초기화"""
        self.stocks: List[Dict[str, str]] = [
            # ===== KOSPI - 대형주 =====
            # 반도체
            {'code': '005930', 'name': '삼성전자', 'english_name': 'Samsung Electronics', 'market': 'KOSPI', 'sector': '반도체'},
            {'code': '000660', 'name': 'SK하이닉스', 'english_name': 'SK Hynix', 'market': 'KOSPI', 'sector': '반도체'},

            # 자동차
            {'code': '005380', 'name': '현대차', 'english_name': 'Hyundai Motor', 'market': 'KOSPI', 'sector': '자동차'},
            {'code': '000270', 'name': '기아', 'english_name': 'Kia Corporation', 'market': 'KOSPI', 'sector': '자동차'},
            {'code': '012330', 'name': '현대모비스', 'english_name': 'Hyundai Mobis', 'market': 'KOSPI', 'sector': '자동차'},

            # 2차전지/화학
            {'code': '373220', 'name': 'LG에너지솔루션', 'english_name': 'LG Energy Solution', 'market': 'KOSPI', 'sector': '2차전지'},
            {'code': '006400', 'name': '삼성SDI', 'english_name': 'Samsung SDI', 'market': 'KOSPI', 'sector': '2차전지'},
            {'code': '051910', 'name': 'LG화학', 'english_name': 'LG Chem', 'market': 'KOSPI', 'sector': '화학'},
            {'code': '003670', 'name': '포스코퓨처엠', 'english_name': 'POSCO Future M', 'market': 'KOSPI', 'sector': '2차전지'},
            {'code': '247540', 'name': '에코프로비엠', 'english_name': 'EcoPro BM', 'market': 'KOSPI', 'sector': '2차전지'},

            # 금융
            {'code': '105560', 'name': 'KB금융', 'english_name': 'KB Financial Group', 'market': 'KOSPI', 'sector': '금융'},
            {'code': '055550', 'name': '신한지주', 'english_name': 'Shinhan Financial Group', 'market': 'KOSPI', 'sector': '금융'},
            {'code': '086790', 'name': '하나금융지주', 'english_name': 'Hana Financial Group', 'market': 'KOSPI', 'sector': '금융'},
            {'code': '316140', 'name': '우리금융지주', 'english_name': 'Woori Financial Group', 'market': 'KOSPI', 'sector': '금융'},
            {'code': '138930', 'name': 'BNK금융지주', 'english_name': 'BNK Financial Group', 'market': 'KOSPI', 'sector': '금융'},

            # 철강/소재
            {'code': '005490', 'name': 'POSCO홀딩스', 'english_name': 'POSCO Holdings', 'market': 'KOSPI', 'sector': '철강'},
            {'code': '000810', 'name': '삼성화재', 'english_name': 'Samsung Fire & Marine', 'market': 'KOSPI', 'sector': '보험'},

            # 통신
            {'code': '017670', 'name': 'SK텔레콤', 'english_name': 'SK Telecom', 'market': 'KOSPI', 'sector': '통신'},
            {'code': '030200', 'name': 'KT', 'english_name': 'KT Corporation', 'market': 'KOSPI', 'sector': '통신'},
            {'code': '032830', 'name': '삼성생명', 'english_name': 'Samsung Life Insurance', 'market': 'KOSPI', 'sector': '보험'},

            # 유통/소비재
            {'code': '015760', 'name': '한국전력', 'english_name': 'KEPCO', 'market': 'KOSPI', 'sector': '전력'},
            {'code': '034730', 'name': 'SK', 'english_name': 'SK Inc.', 'market': 'KOSPI', 'sector': '지주'},
            {'code': '066570', 'name': 'LG전자', 'english_name': 'LG Electronics', 'market': 'KOSPI', 'sector': '전자'},
            {'code': '018260', 'name': '삼성에스디에스', 'english_name': 'Samsung SDS', 'market': 'KOSPI', 'sector': 'IT서비스'},
            {'code': '003550', 'name': 'LG', 'english_name': 'LG Corp', 'market': 'KOSPI', 'sector': '지주'},

            # 조선/중공업
            {'code': '009540', 'name': '한국조선해양', 'english_name': 'HD Korea Shipbuilding', 'market': 'KOSPI', 'sector': '조선'},
            {'code': '329180', 'name': 'HD현대중공업', 'english_name': 'HD Hyundai Heavy Industries', 'market': 'KOSPI', 'sector': '조선'},

            # 건설
            {'code': '000720', 'name': '현대건설', 'english_name': 'Hyundai E&C', 'market': 'KOSPI', 'sector': '건설'},
            {'code': '047050', 'name': '포스코인터내셔널', 'english_name': 'POSCO International', 'market': 'KOSPI', 'sector': '무역'},

            # 항공
            {'code': '003490', 'name': '대한항공', 'english_name': 'Korean Air', 'market': 'KOSPI', 'sector': '항공'},

            # 바이오 (KOSPI)
            {'code': '207940', 'name': '삼성바이오로직스', 'english_name': 'Samsung Biologics', 'market': 'KOSPI', 'sector': '바이오'},
            {'code': '068270', 'name': '셀트리온', 'english_name': 'Celltrion', 'market': 'KOSPI', 'sector': '바이오'},

            # 식품
            {'code': '097950', 'name': 'CJ제일제당', 'english_name': 'CJ CheilJedang', 'market': 'KOSPI', 'sector': '식품'},
            {'code': '004990', 'name': '롯데지주', 'english_name': 'Lotte Corp', 'market': 'KOSPI', 'sector': '지주'},

            # ===== KOSDAQ - 주요 종목 =====
            # 인터넷/플랫폼
            {'code': '035420', 'name': 'NAVER', 'english_name': 'NAVER Corporation', 'market': 'KOSPI', 'sector': '인터넷'},
            {'code': '035720', 'name': '카카오', 'english_name': 'Kakao Corp', 'market': 'KOSPI', 'sector': '인터넷'},
            {'code': '263750', 'name': '펄어비스', 'english_name': 'Pearl Abyss', 'market': 'KOSDAQ', 'sector': '게임'},

            # 반도체 (KOSDAQ)
            {'code': '042700', 'name': '한미반도체', 'english_name': 'Hanmi Semiconductor', 'market': 'KOSDAQ', 'sector': '반도체'},
            {'code': '058470', 'name': '리노공업', 'english_name': 'Leeno Industrial', 'market': 'KOSDAQ', 'sector': '반도체'},
            {'code': '403870', 'name': 'HPSP', 'english_name': 'HPSP', 'market': 'KOSDAQ', 'sector': '반도체장비'},
            {'code': '340570', 'name': '티앤엘', 'english_name': 'T&L', 'market': 'KOSDAQ', 'sector': '의료기기'},

            # 바이오 (KOSDAQ)
            {'code': '326030', 'name': 'SK바이오팜', 'english_name': 'SK Biopharmaceuticals', 'market': 'KOSDAQ', 'sector': '바이오'},
            {'code': '091990', 'name': '셀트리온헬스케어', 'english_name': 'Celltrion Healthcare', 'market': 'KOSDAQ', 'sector': '바이오'},
            {'code': '196170', 'name': '알테오젠', 'english_name': 'Alteogen', 'market': 'KOSDAQ', 'sector': '바이오'},
            {'code': '145020', 'name': '휴젤', 'english_name': 'Hugel', 'market': 'KOSDAQ', 'sector': '바이오'},

            # 엔터테인먼트
            {'code': '352820', 'name': '하이브', 'english_name': 'HYBE', 'market': 'KOSPI', 'sector': '엔터'},
            {'code': '041510', 'name': 'SM', 'english_name': 'SM Entertainment', 'market': 'KOSDAQ', 'sector': '엔터'},
            {'code': '122870', 'name': 'YG엔터테인먼트', 'english_name': 'YG Entertainment', 'market': 'KOSDAQ', 'sector': '엔터'},
            {'code': '259960', 'name': '크래프톤', 'english_name': 'Krafton', 'market': 'KOSPI', 'sector': '게임'},

            # IT/소프트웨어
            {'code': '036570', 'name': '엔씨소프트', 'english_name': 'NCSoft', 'market': 'KOSPI', 'sector': '게임'},
            {'code': '251270', 'name': '넷마블', 'english_name': 'Netmarble', 'market': 'KOSPI', 'sector': '게임'},

            # 2차전지 소재 (KOSDAQ)
            {'code': '086520', 'name': '에코프로', 'english_name': 'EcoPro', 'market': 'KOSDAQ', 'sector': '2차전지'},
            {'code': '112040', 'name': '위메이드', 'english_name': 'Wemade', 'market': 'KOSDAQ', 'sector': '게임'},
        ]

        # code -> stock dict 빠른 조회용 인덱스
        self._index: Dict[str, Dict[str, str]] = {
            s['code']: s for s in self.stocks
        }

    def get_symbol_info(self, code: str) -> Optional[Dict[str, str]]:
        """종목 코드로 종목 정보를 조회합니다.

        Args:
            code: 종목 코드 (예: '005930')

        Returns:
            종목 정보 dict 또는 None
        """
        code = code.strip()
        return self._index.get(code)

    def get_preset(self, name: str) -> List[str]:
        """프리셋 이름으로 종목 코드 리스트를 반환합니다.

        Args:
            name: 프리셋 이름 (예: '대형주 TOP10')

        Returns:
            종목 코드 리스트 (프리셋이 없으면 빈 리스트)
        """
        return KR_PRESETS.get(name, [])

    def get_all_presets(self) -> Dict[str, List[str]]:
        """모든 프리셋을 반환합니다.

        Returns:
            프리셋 딕셔너리
        """
        return KR_PRESETS.copy()

    def get_preset_names(self) -> List[str]:
        """프리셋 이름 목록을 반환합니다.

        Returns:
            프리셋 이름 리스트
        """
        return list(KR_PRESETS.keys())

    def search(self, query: str) -> List[Dict[str, str]]:
        """종목 코드 또는 이름으로 검색합니다.

        Args:
            query: 검색 키워드 (종목 코드, 한글 이름, 영문 이름)

        Returns:
            매칭된 종목 정보 리스트
        """
        if not query:
            return []

        query = query.strip()
        query_upper = query.upper()

        results: List[Dict[str, str]] = []
        seen_codes: set = set()

        for stock in self.stocks:
            if stock['code'] in seen_codes:
                continue

            # 코드 매칭 (prefix)
            if stock['code'].startswith(query):
                results.append(stock)
                seen_codes.add(stock['code'])
                continue

            # 한글 이름 매칭 (contains)
            if query in stock['name']:
                results.append(stock)
                seen_codes.add(stock['code'])
                continue

            # 영문 이름 매칭 (case-insensitive contains)
            if query_upper in stock['english_name'].upper():
                results.append(stock)
                seen_codes.add(stock['code'])
                continue

        return results

    def get_by_market(self, market: str) -> List[Dict[str, str]]:
        """마켓(KOSPI/KOSDAQ)으로 종목을 필터링합니다.

        Args:
            market: 'KOSPI' 또는 'KOSDAQ'

        Returns:
            해당 마켓 종목 리스트
        """
        market = market.upper().strip()
        return [s for s in self.stocks if s['market'] == market]

    def get_by_sector(self, sector: str) -> List[Dict[str, str]]:
        """섹터로 종목을 필터링합니다.

        Args:
            sector: 섹터 이름 (예: '반도체', '바이오')

        Returns:
            해당 섹터 종목 리스트
        """
        return [s for s in self.stocks if s['sector'] == sector]

    def get_all_sectors(self) -> List[str]:
        """모든 섹터 목록을 반환합니다.

        Returns:
            섹터 이름 리스트 (정렬됨)
        """
        sectors: set = set()
        for stock in self.stocks:
            sectors.add(stock['sector'])
        return sorted(sectors)

    def get_all_codes(self) -> List[str]:
        """모든 종목 코드를 반환합니다.

        Returns:
            종목 코드 리스트 (정렬됨)
        """
        return sorted(self._index.keys())

    def get_preset_with_info(self, name: str) -> List[Dict[str, str]]:
        """프리셋의 종목 코드에 대한 상세 정보를 반환합니다.

        Args:
            name: 프리셋 이름

        Returns:
            종목 정보 리스트 (프리셋이 없으면 빈 리스트)
        """
        codes = self.get_preset(name)
        results: List[Dict[str, str]] = []
        for code in codes:
            info = self.get_symbol_info(code)
            if info:
                results.append(info)
        return results
