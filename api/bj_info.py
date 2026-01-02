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
            # 다시보기 목록 (모바일 웹 페이지 활용)
            vod_url = f"https://mw.afreecatv.com/station/{bj_id}/vod"

            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
            }

            # 3. 데이터 수집 (메인 페이지)
            res_station = requests.get(station_url, headers=headers, timeout=5)
            soup_station = BeautifulSoup(res_station.text, 'html.parser')

            # 닉네임
            nick_tag = soup_station.select_one('meta[property="og:title"]')
            nickname = nick_tag['content'] if nick_tag else bj_id
            
            # 프로필 이미지
            img_tag = soup_station.select_one('meta[property="og:image"]')
            profile_img = img_tag['content'] if img_tag else ""

            # 방송 중 여부 (on 클래스 확인)
            # PC 페이지 기준: <button type="button" class="btn_broadcast on">
            is_live = False
            if "class=\"btn_broadcast on\"" in res_station.text or "player_live" in res_station.text:
                is_live = True

            # 4. 데이터 수집 (VOD 페이지) - 모바일 페이지 파싱이 더 안정적일 수 있음
            # 모바일 페이지 요청
            res_vod = requests.get(vod_url, headers=headers, timeout=5)
            soup_vod = BeautifulSoup(res_vod.text, 'html.parser')
            
            vod_list = []
            # 모바일 VOD 리스트 파싱 로직 (mw.afreecatv.com 구조 기준)
            # 보통 ul.list_type1 > li 구조
            items = soup_vod.select('.list_type1 li')
            if not items:
                items = soup_vod.select('li[data-type="vod"]')

            for item in items[:10]: # 최근 10개만
                try:
                    title_tag = item.select_one('.title, .subject')
                    link_tag = item.select_one('a')
                    thumb_tag = item.select_one('img')
                    time_tag = item.select_one('.time, .running_time')
                    date_tag = item.select_one('.date, .reg_date')

                    if title_tag and link_tag:
                        link = link_tag['href']
                        if not link.startswith('http'):
                            link = f"https://mw.afreecatv.com{link}"
                            
                        vod_list.append({
                            'title': title_tag.get_text(strip=True),
                            'link': link,
                            'thumb': thumb_tag['src'] if thumb_tag else "",
                            'duration': time_tag.get_text(strip=True) if time_tag else "00:00",
                            'date': date_tag.get_text(strip=True) if date_tag else ""
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
