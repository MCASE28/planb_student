from http.server import BaseHTTPRequestHandler
from urllib.parse import parse_qs, urlparse
import json
import requests
from bs4 import BeautifulSoup
import re

class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        # 1. 파라미터 파싱
        parsed_path = urlparse(self.path)
        params = parse_qs(parsed_path.query)
        bj_id = params.get('id', [None])[0]

        # 헤더 설정 (CORS 허용)
        self.send_response(200)
        self.send_header('Content-type', 'application/json')
        self.send_header('Access-Control-Allow-Origin', '*')
        self.end_headers()

        if not bj_id:
            response_data = {'success': False, 'message': 'ID parameter is missing'}
            self.wfile.write(json.dumps(response_data).encode('utf-8'))
            return

        try:
            # 2. 크롤링 대상 URL 설정
            # 모바일 페이지가 데이터 구조가 단순하여 크롤링에 유리한 경우가 많음
            # 메인 스테이션 (라이브 여부, 프로필)
            station_url = f"https://bj.afreecatv.com/{bj_id}"
            # 다시보기 목록 (PC 웹 페이지 활용)
            vod_url = f"https://bj.afreecatv.com/{bj_id}/vods"

            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
                'Referer': 'https://bj.afreecatv.com/'
            }

            # 3. 데이터 수집 (내부 API 사용)
            # 방송국 정보 (닉네임, 프사, 생방송 여부)
            api_station_url = f"https://bjapi.afreecatv.com/api/{bj_id}/station"
            res_station = requests.get(api_station_url, headers=headers, timeout=5)
            data_station = res_station.json()

            # 기본 정보 파싱
            station_info = data_station.get('station', {})
            nickname = station_info.get('user_nick', bj_id)
            
            profile_img = data_station.get('profile_image', '')
            if profile_img and profile_img.startswith('//'):
                profile_img = 'https:' + profile_img

            # 방송 중 여부 ('broad' 필드가 null이면 오프라인, 객체면 방송 중)
            is_live = data_station.get('broad') is not None

            # 4. 데이터 수집 (VOD API 사용)
            api_vod_url = f"https://bjapi.afreecatv.com/api/{bj_id}/vods"
            res_vod = requests.get(api_vod_url, headers=headers, timeout=5)
            data_vod = res_vod.json()
            
            vod_list = []
            if 'data' in data_vod:
                for item in data_vod['data'][:10]: # 최근 10개
                    try:
                        title_no = item.get('title_no')
                        if not title_no: continue

                        # 썸네일 처리
                        thumb = item.get('ucc', {}).get('thumb', '')
                        if thumb and thumb.startswith('//'):
                            thumb = 'https:' + thumb

                        # 시간 처리 (초 단위 -> HH:MM:SS)
                        duration_sec = item.get('ucc', {}).get('total_file_duration', 0)
                        # API가 주는 duration 단위가 초가 아닐 수 있음 (보통 밀리초거나 그냥 초)
                        # 테스트 결과: 12139600 -> 매우 큼. 밀리초일 가능성 높음? 아니면 그냥 초?
                        # 확인: 12139600 / 1000 = 12139초 = 약 3시간. (밀리초가 맞는 듯 보임)
                        # 하지만 31053400 같은 값도 있음. 일단 초 단위로 변환
                        # 아프리카 VOD duration은 보통 '초' 단위인데 값이 크다면 확인 필요.
                        # -> API 응답 예시: 12139600. 이건 3시간 방송이면 10800초여야 함.
                        # -> 따라서 12139600 은 밀리초(ms) 단위일 가능성이 매우 높음.
                        
                        seconds = int(duration_sec) // 1000
                        h = seconds // 3600
                        m = (seconds % 3600) // 60
                        s = seconds % 60
                        duration_str = f"{h:02}:{m:02}:{s:02}" if h > 0 else f"{m:02}:{s:02}"

                        vod_list.append({
                            'title': item.get('title_name', ''),
                            'link': f"https://vod.afreecatv.com/player/{title_no}",
                            'thumb': thumb,
                            'duration': duration_str,
                            'date': item.get('reg_date', '').split(' ')[0] # 2025-12-30 형식
                        })
                    except Exception:
                        continue

            # 5. 결과 반환
            result = {
                'success': True,
                'id': bj_id,
                'nickname': nickname,
                'profile_img': profile_img,
                'is_live': is_live,
                'vods': vod_list
            }
            self.wfile.write(json.dumps(result, ensure_ascii=False).encode('utf-8'))

        except Exception as e:
            error_response = {'success': False, 'message': str(e)}
            self.wfile.write(json.dumps(error_response).encode('utf-8'))
