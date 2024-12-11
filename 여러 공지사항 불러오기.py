import requests
from bs4 import BeautifulSoup
import json

def lambda_handler(event, context):
    try:
        # body를 파싱하여 board_type 추출
        body = json.loads(event['body'])
        board_type = body.get('action', {}).get('params', {}).get('board_type', "")
    except (json.JSONDecodeError, KeyError):
        return {
            'statusCode': 400,
            'body': json.dumps({"error": "Invalid request format"}, ensure_ascii=False)
        }

    # URL 및 게시판 이름 선택
    if board_type == "해성공지":
        url = "https://www.mmu.ac.kr/main/board/301"
        board_name = "해성공지"
    elif board_type == "학사공지":
        url = "https://www.mmu.ac.kr/main/board/302"
        board_name = "학사공지"
    elif board_type == "해성게시판":
        url = "https://www.mmu.ac.kr/main/board/282"
        board_name = "해성게시판"
    elif board_type == "인검전달사항":
        url = "https://www.mmu.ac.kr/main/board/262"
        board_name = "인검전달사항"
    else:
        return {
            'statusCode': 400,
            'body': json.dumps({"error": "Invalid board_type"}, ensure_ascii=False)
        }

    # 웹 페이지 요청
    try:
        response = requests.get(url)
        response.encoding = 'utf-8'
    except requests.exceptions.RequestException as e:
        return {
            'statusCode': 500,
            'body': json.dumps({"error": "Failed to retrieve page"}, ensure_ascii=False)
        }

    # 페이지 파싱
    soup = BeautifulSoup(response.text, 'html.parser')

    # 공지사항과 일반 글 리스트
    notices = []
    general_posts = []

    # 모든 게시물 가져오기
    rows = soup.find('table').find('tbody').find_all('tr')

    for row in rows:
        no_column = row.find("td", class_="no")
        title_column = row.find("td", class_="title")
        date_column = row.find("td", class_="date")

        title = title_column.get_text(strip=True) if title_column else "No title"
        date = date_column.get_text(strip=True) if date_column else "No date"

        # 연도를 제외하고 월과 일만 추출
        date_parts = date.split('-')
        if len(date_parts) == 3:
            date = f"{date_parts[1]}-{date_parts[2]}"  # 월-일로 구성

        post = f"{title} {date}"

        if no_column and no_column.find("span", class_="notice"):
            notices.append(post)
        else:
            general_posts.append(post)

    # 일반 게시물은 최대 7개만 표시
    general_posts = general_posts[:7]

    # 공지사항 리스트 생성
    notice_item_list = [{"title": "주요공지", "description": notice} for notice in notices]

    # 일반 게시물 리스트 생성
    general_item_list = [{"title": "일반공지", "description": post} for post in general_posts]

    # JSON 응답 구성
    result = {
        "version": "2.0",
        "template": {
            "outputs": [
                {
                    "itemCard": {
                        "imageTitle": {
                            "title": board_name,
                            "description": "일반공지는 최근 4~7개 내역만 불러옵니다."
                        },
                        "itemList": notice_item_list + general_item_list,  # 공지사항과 일반 공지 모두 포함
                        "itemListAlignment": "right",
                        "buttons": [
                            {
                                "label": f"{board_name} 바로가기",
                                "action": "webLink",
                                "webLinkUrl": url
                            }
                        ],
                        "buttonLayout": "vertical"
                    }
                }
            ],
            "quickReplies": [
                {
                    "messageText": "인검전달사항",
                    "action": "message",
                    "label": "인검전달사항"
                },
                {
                    "messageText": "해성공지",
                    "action": "message",
                    "label": "해성공지"
                },
                {
                    "messageText": "해성게시판",
                    "action": "message",
                    "label": "해성게시판"
                },
                {
                    "messageText": "학사공지",
                    "action": "message",
                    "label": "학사공지"
                }
            ]
        }
    }

    return {
        'statusCode': 200,
        'body': json.dumps(result, ensure_ascii=False),
        'headers': {
            'Access-Control-Allow-Origin': '*',
        }
    }
