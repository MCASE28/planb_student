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
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
                'Accept-Language': 'ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7',
                'Referer': 'https://www.afreecatv.com/'
            }

            # 3. 데이터 수집 (메인 페이지)
            res_station = requests.get(station_url, headers=headers, timeout=5)
            # 인코딩 강제 설정 (한글 깨짐 방지)
            res_station.encoding = 'utf-8'
            
            soup_station = BeautifulSoup(res_station.text, 'html.parser')
            html_text = res_station.text

            # 닉네임 파싱 (우선순위: og:title -> title 태그 -> 정규식)
            nick_tag = soup_station.select_one('meta[property="og:title"]')
            if nick_tag and nick_tag.get('content'):
                nickname = nick_tag['content']
            else:
                # 백업: title 태그 사용 ("닉네임 - SOOP" 형식 제거)
                title_tag = soup_station.select_one('title')
                if title_tag:
                    nickname = title_tag.get_text().split(' |')[0].split(' -')[0].strip()
                else:
                    nickname = bj_id

            # 프로필 이미지 파싱 (우선순위: og:image -> 본문 내 프로필 이미지 -> 정규식)
            img_tag = soup_station.select_one('meta[property="og:image"]')
            if img_tag and img_tag.get('content'):
                profile_img = img_tag['content']
            else:
                # 백업: 본문 내 프로필 이미지 클래스 시도
                profile_elem = soup_station.select_one('.st_profile img')
                if profile_elem:
                    profile_img = profile_elem.get('src')
                else:
                    # 백업: 정규식으로 thumb 패턴 찾기
                    match = re.search(r'http[s]?://profile\.img\.afreecatv\.com/[^"\']+', html_text)
                    profile_img = match.group(0) if match else ""

            # 방송 중 여부 파싱
            # 1. HTML 클래스로 확인
            is_live = False
            if "class=\"btn_broadcast on\"" in html_text or "player_live" in html_text:
                is_live = True
            
            # 2. 백업: 자바스크립트 변수 확인 (아프리카TV는 스크립트 변수로 상태를 가짐)
            # broad_no(방송번호)가 0이 아니거나, is_broad 등이 true인 경우
            if not is_live:
                if re.search(r'"broad_no"\s*:\s*"?[1-9]', html_text): # broad_no가 0이 아님
                    is_live = True
                elif re.search(r"broad_no\s*=\s*['\"]?[1-9]", html_text):
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
