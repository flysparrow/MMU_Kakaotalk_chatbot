import os
import boto3
import json
from datetime import datetime, timedelta
import requests
from bs4 import BeautifulSoup as bs

def read_s3_file(bucket_name, file_key):
    s3 = boto3.client('s3')
    try:
        obj = s3.get_object(Bucket=bucket_name, Key=file_key)
        return obj['Body'].read().decode('utf-8')
    except s3.exceptions.NoSuchKey:
        raise ValueError(f"The file {file_key} does not exist in the bucket {bucket_name}.")

def scrape_and_upload_to_s3(bucket_name, file_key):
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/106.0.0.0 Safari/537.36"
    }
    url = "https://www.mmu.ac.kr/main/contents/todayMenu2"
    res = requests.get(url, headers=headers)
    res.raise_for_status()

    soup = bs(res.text, 'html.parser')
    rows = soup.find_all('tr')

    food_data = ""

    for row in rows:
        date_day_td = row.find('td', class_='text_center')
        if date_day_td:
            date_day = date_day_td.get_text(separator=' ', strip=True).split(' ')[0]
            menu_tds = row.find_all('td')[1:]
            meal_times = ['조식', '중식', '석식']
            for index, menu_td in enumerate(menu_tds):
                menu = menu_td.get_text(separator='\n', strip=True)
                meal_time = meal_times[index] if index < len(meal_times) else f"식사 {index+1}"
                food_data += f"{date_day} {meal_time}\n{menu}\n---\n"

    s3 = boto3.client('s3')
    try:
        s3.put_object(Bucket=bucket_name, Key=file_key, Body=food_data, ContentType='text/plain; charset=utf-8')
        print("File uploaded successfully.")
    except Exception as e:
        print(f"Error uploading file: {str(e)}")

def get_korean_day_of_week(weekday):
    days = ['월요일', '화요일', '수요일', '목요일', '금요일', '토요일', '일요일']
    return days[weekday]

def lambda_handler(event, context):
    # Log the event to CloudWatch
    print("Received event:", json.dumps(event, ensure_ascii=False))

    request_body = json.loads(event['body'])
    params = request_body['action']['params']
    
    if '내일' in params['time']:
        meal_type = params['time'].replace('내일 ', '')
        date_offset = 1
        show_all_today = '메뉴' in meal_type
        menu_day_label = "내일의 해사대학 학식 메뉴"
    elif '오늘 메뉴' in params['time']:
        meal_type = '오늘 메뉴'
        date_offset = 0
        show_all_today = True
        menu_day_label = "오늘의 해사대학 학식 메뉴"
    else:
        meal_type = params['time']
        date_offset = 0
        show_all_today = False
        menu_day_label = "해사대학 학식 메뉴"

    bucket_name = 'Private'
    file_key = 'Private'

    try:
        file_content = read_s3_file(bucket_name, file_key)
    except ValueError as e:
        return {
            'statusCode': 400,
            'body': json.dumps({'error': str(e)}),
            'headers': {
                'Access-Control-Allow-Origin': '*',
            }
        }

    lines = file_content.split('\n')
    current_date = datetime.now() + timedelta(hours=9)
    target_date = current_date + timedelta(days=date_offset)
    
    # 날짜를 'MM월 DD일 요일' 형식으로 변환
    date_info = target_date.strftime(f'%m월 %d일 {get_korean_day_of_week(target_date.weekday())}')
    simple_date_info = target_date.strftime('%-m/%-d')

    menus = {"조식": "", "중식": "", "석식": ""}
    menu_found = False
    current_meal_type = ""

    if show_all_today:
        for line in lines:
            if simple_date_info in line:
                for meal in menus.keys():
                    if meal in line:
                        current_meal_type = meal
                        menu_found = True
                        break
            elif menu_found and line.strip() == "---":
                current_meal_type = ""
            elif menu_found and current_meal_type:
                if simple_date_info in line or current_meal_type in line:
                    continue
                menus[current_meal_type] += line.strip() + "\n"

        menus = {meal: menu.strip() for meal, menu in menus.items() if menu.strip()}

    else:
        response_text = ""
        for line in lines:
            if simple_date_info in line and meal_type in line:
                menu_found = True
                response_text = f"{date_info} {meal_type}\n"
                continue
            if line.strip() == "---" and menu_found:
                break
            if menu_found:
                if simple_date_info in line or meal_type in line:
                    continue
                response_text += line.strip() + "\n"

    if not any(menus.values()):
        scrape_and_upload_to_s3(bucket_name, file_key)
        response_text = "해당하는 메뉴 정보를 찾을 수 없습니다.\n메뉴 자동 갱신 중입니다.\n3초 뒤 다시 시도해 주세요.\n방학 기간엔 교내 사이트에 메뉴 정보가 업로드 되지 않으므로 기다려도 메뉴 정보를 불러올 수 없어요."

    # 현재 시간을 가져오기
    now = datetime.now() + timedelta(hours=9)

    # 메뉴 타이틀과 시간 정보 생성
    menu_titles = "\n\n".join([
        f"🌅조식\n{menus.get('조식', '메뉴가 없습니다.')}",
        f"🖼️중식\n{menus.get('중식', '메뉴가 없습니다.')}",
        f"🌆석식\n{menus.get('석식', '메뉴가 없습니다.')}"
    ])

    # 주말인지 확인
    is_weekend = target_date.weekday() in [5, 6]  # Saturday (5) or Sunday (6)

    # 시간별로 아이콘을 변경 (오늘의 메뉴일 때만 적용)
    if date_offset == 0:  # 오늘의 메뉴일 경우만 체크
        if now.time() >= datetime.strptime("07:30", "%H:%M").time() and now.time() <= datetime.strptime("08:30", "%H:%M").time():
            breakfast_icon = "✅"
        else:
            breakfast_icon = "⏰"

        if now.time() >= datetime.strptime("11:50", "%H:%M").time() and now.time() <= datetime.strptime("13:30", "%H:%M").time():
            lunch_icon = "✅"
        else:
            lunch_icon = "⏰"

        if now.time() >= datetime.strptime("17:30", "%H:%M").time() and now.time() <= datetime.strptime("18:30", "%H:%M").time():
            dinner_icon = "✅"
        else:
            dinner_icon = "⏰"
    else:  # 내일의 메뉴일 경우
        breakfast_icon = "⏰"
        lunch_icon = "⏰"
        dinner_icon = "⏰"

    # 중식 시간 조정
    lunch_time_description = "11:40 ~ 13:00" if is_weekend else "11:40 ~ 13:30"

    result = {
        "version": "2.0",
        "template": {
            "outputs": [
                {
                    "itemCard": {
                        "imageTitle": {
                            "title": date_info,
                            "description": menu_day_label
                        },
                        "title": menu_titles,
                        "itemList": [
                            {
                                "title": f"조식 {breakfast_icon}",
                                "description": "07:20 ~ 08:30"
                            },
                            {
                                "title": f"중식 {lunch_icon}",
                                "description": lunch_time_description
                            },
                            {
                                "title": f"석식 {dinner_icon}",
                                "description": "17:20 ~ 18:30"
                            }
                        ],
                        "itemListAlignment": "right",
                        "buttons": [
                            {
                              "action": "webLink",
                              "label": "전체 메뉴 보러가기",
                              "webLinkUrl": "https://www.mmu.ac.kr/main/contents/todayMenu2"
                            }
                        ]
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
                    "messageText": "이번달",
                    "action": "message",
                    "label": "이번달 학사일정"
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
