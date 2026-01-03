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
            
            # 통계 정보 파싱
            upd = station_info.get('upd', {})
            fan_cnt = upd.get('fan_cnt', 0)
            total_visit_cnt = upd.get('total_visit_cnt', 0)
            today_visit_cnt = upd.get('today1_visit_cnt', 0)
            
            profile_img = data_station.get('profile_image', '')
            if profile_img and profile_img.startswith('//'):
                profile_img = 'https:' + profile_img

            # 방송 중 여부 ('broad' 필드가 null이면 오프라인, 객체면 방송 중)
            is_live = data_station.get('broad') is not None

            # 4. 데이터 수집 (VOD API 사용)
            vod_list = []
            for page in range(1, 6): # 1~5페이지까지 수집
                api_vod_url = f"https://bjapi.afreecatv.com/api/{bj_id}/vods?page={page}"
                res_vod = requests.get(api_vod_url, headers=headers, timeout=5)
                data_vod = res_vod.json()
                
                if 'data' in data_vod and data_vod['data']:
                    for item in data_vod['data']: 
                        try:
                            title_no = item.get('title_no')
                            if not title_no: continue

                            # 썸네일 처리
                            thumb = item.get('ucc', {}).get('thumb', '')
                            if thumb and thumb.startswith('//'):
                                thumb = 'https:' + thumb

                            # 시간 처리 (초 단위 -> HH:MM:SS)
                            duration_sec = item.get('ucc', {}).get('total_file_duration', 0)
                            # API duration은 밀리초(ms) 단위임
                            seconds = int(duration_sec) // 1000
                            
                            h = seconds // 3600
                            m = (seconds % 3600) // 60
                            s = seconds % 60
                            duration_str = f"{h:02}:{m:02}:{s:02}" if h > 0 else f"{m:02}:{s:02}"

                            # 조회수 (그래프용)
                            read_cnt = item.get('count', {}).get('read_cnt', 0)

                            vod_list.append({
                                'title': item.get('title_name', ''),
                                'link': f"https://vod.afreecatv.com/player/{title_no}",
                                'thumb': thumb,
                                'duration': duration_str,
                                'duration_sec': seconds, # 계산용 원본 초
                                'read_cnt': read_cnt,
                                'date': item.get('reg_date', '').split(' ')[0] # 2025-12-30 형식
                            })
                        except Exception:
                            continue
                else:
                    break # 데이터가 없으면 루프 종료

            # 5. 결과 반환
            result = {
                'success': True,
                'id': bj_id,
                'nickname': nickname,
                'profile_img': profile_img,
                'is_live': is_live,
                'fan_cnt': fan_cnt,
                'total_visit_cnt': total_visit_cnt,
                'today_visit_cnt': today_visit_cnt,
                'vods': vod_list
            }
            self.wfile.write(json.dumps(result, ensure_ascii=False).encode('utf-8'))

        except Exception as e:
            error_response = {'success': False, 'message': str(e)}
            self.wfile.write(json.dumps(error_response).encode('utf-8'))
