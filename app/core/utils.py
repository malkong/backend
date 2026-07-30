"""DB·HTTP와 무관한 순수 유틸.

기존 services/storage.py의 _normalize_image_url을 옮긴 것이다. DB 접근과 아무 관련이
없는데 리포지토리 계층에 private 함수로 있었고, card_generator.py가 언더스코어 붙은
private 함수를 모듈 밖에서 import해 쓰고 있었다. 여기로 옮기면서 public으로 바꿨다.
"""
import re

_DRIVE_FILE_ID_RE = re.compile(r"drive\.google\.com/file/d/([^/]+)/")


def normalize_image_url(url):
    """구글드라이브 '보기' 페이지 링크(.../file/d/{id}/view)를 <img>에 바로 넣을 수 있는
    썸네일 리소스 URL로 변환한다. 패턴이 없으면(다른 호스트 등) 원본을 그대로 반환한다.
    """
    if not url:
        return url
    m = _DRIVE_FILE_ID_RE.search(url)
    if not m:
        return url
    file_id = m.group(1)
    return f"https://drive.google.com/thumbnail?id={file_id}&sz=w400"
