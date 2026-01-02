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

            # 4. 데이터 수집 (VOD 페이지) - PC 페이지 활용 (모바일 mw 도메인 접속 불가 대응)
            res_vod = requests.get(vod_url, headers=headers, timeout=5)
            soup_vod = BeautifulSoup(res_vod.text, 'html.parser')
            
            vod_list = []
            
            # PC 페이지 구조가 다양할 수 있으므로 범용적인 탐색 시도
            # VOD 리스트는 보통 li 태그로 구성됨
            items = soup_vod.select('li')

            for item in items:
                try:
                    # 제목: .tit, .title, .subject 클래스 또는 dt 태그 내부
                    title_tag = item.select_one('.tit, .title, .subject, dt a')
                    # 링크: 썸네일 링크(.thumb) 또는 일반 링크
                    link_tag = item.select_one('a.thumb, a.box_link')
                    if not link_tag:
                        link_tag = item.select_one('a')
                    # 썸네일 이미지
                    thumb_tag = item.select_one('img')
                    # 시간 및 날짜
                    time_tag = item.select_one('.time, .runtime, .running_time')
                    date_tag = item.select_one('.date, .reg_date, .day')

                    # 필수 요소(제목, 링크, 이미지)가 모두 있어야 VOD 항목으로 인정
                    if title_tag and link_tag and thumb_tag:
                        link = link_tag.get('href', '')
                        # 자바스크립트 링크나 앵커 링크 제외
                        if not link or 'javascript' in link or link == '#':
                            continue
                            
                        if not link.startswith('http'):
                            link = f"https://bj.afreecatv.com{link}"

                        # 이미지 소스 (src 또는 data-original 등)
                        thumb_src = thumb_tag.get('src', '')
                        
                        # 이미지가 없거나 아이콘인 경우 스킵 (선택사항)
                        if not thumb_src: continue

                        vod_list.append({
                            'title': title_tag.get_text(strip=True),
                            'link': link,
                            'thumb': thumb_src,
                            'duration': time_tag.get_text(strip=True) if time_tag else "",
                            'date': date_tag.get_text(strip=True) if date_tag else ""
                        })
                        
                        if len(vod_list) >= 8: # 최대 8개까지만
                            break
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
