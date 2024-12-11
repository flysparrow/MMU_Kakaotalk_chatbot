import boto3
import json
from datetime import datetime, timedelta
import requests
from bs4 import BeautifulSoup

def read_s3_file(bucket_name, file_key):
    s3 = boto3.client('s3')
    try:
        obj = s3.get_object(Bucket=bucket_name, Key=file_key)
        return obj['Body'].read().decode('utf-8')
    except s3.exceptions.NoSuchKey:
        raise ValueError(f"The file {file_key} does not exist in the bucket {bucket_name}.")

def split_text(text, max_length=1000):
    lines = text.split('\n')
    chunks = []
    current_chunk = ""

    for line in lines:
        if len(current_chunk) + len(line) + 1 > max_length:
            chunks.append(current_chunk)
            current_chunk = line + "\n"
        else:
            current_chunk += line + "\n"

    if current_chunk:
        chunks.append(current_chunk)

    return chunks

def scrape_menu_and_save_to_s3(bucket_name, file_key):
    url = 'https://www.mmu.ac.kr/main/contents/todayMenu1'
    response = requests.get(url)
    soup = BeautifulSoup(response.text, 'html.parser')
    
    menu_data = []
    current_date = ''
    
    for row in soup.find_all('tr')[1:]:
        columns = row.find_all('td')
        
        if len(columns) > 0:
            date_column = columns[0].get_text(strip=True).replace('\n', ' ')
            meal_columns = [col.get_text(separator='\n', strip=True).replace('&amp;', '&') for col in columns[1:4]]
            
            if "원산지" in date_column:
                continue
            
            if date_column:
                if len(date_column) > 0:
                    date_column = date_column.replace('월', ' 월').replace('화', ' 화').replace('수', ' 수').replace('목', ' 목').replace('금', ' 금')
                
                current_date = date_column
                menu_data.append(f'{current_date} 조식')
                
                if len(meal_columns) > 0 and meal_columns[0]:
                    menu_data.append(meal_columns[0])
                else:
                    menu_data.append('조식 없음')
                
                menu_data.append('---')
                menu_data.append(f'{current_date} 중식')
                
                if len(meal_columns) > 1 and meal_columns[1]:
                    menu_data.append(meal_columns[1])
                else:
                    menu_data.append('중식 없음')
                    
                menu_data.append('---')
                menu_data.append(f'{current_date} 석식')
                
                if len(meal_columns) > 2 and meal_columns[2]:
                    menu_data.append(meal_columns[2])
                else:
                    menu_data.append('석식 없음')
                    
                menu_data.append('---')
    
    formatted_data = '\n'.join([line for line in menu_data if line != '---\n---'])
    
    s3 = boto3.client('s3')
    s3.put_object(Bucket=bucket_name, Key=file_key, Body=formatted_data.encode('utf-8'))


def get_korean_day_of_week(weekday):
    days = ['월요일', '화요일', '수요일', '목요일', '금요일', '토요일', '일요일']
    return days[weekday]

def lambda_handler(event, context):
    request_body = json.loads(event['body'])
    params = request_body['action']['params']
    
    if '내일' in params['time2']:
        meal_type = params['time2'].replace('내일 ', '')
        date_offset = 1
        show_all_today = '메뉴' in meal_type
        menu_day_label = "내일의 학생회관 식당 메뉴"
    elif '오늘 메뉴' in params['time2']:
        meal_type = '오늘 메뉴'
        date_offset = 0
        show_all_today = True
        menu_day_label = "오늘의 학생회관 식당 메뉴"
    else:
        meal_type = params['time2']
        date_offset = 0
        show_all_today = False
        menu_day_label = "학생회관 식당 메뉴"

    bucket_name = 'Private'
    file_key = 'Private'

    try:
        file_content = read_s3_file(bucket_name, file_key)
    except ValueError:
        scrape_menu_and_save_to_s3(bucket_name, file_key)
        file_content = read_s3_file(bucket_name, file_key)

    lines = file_content.split('\n')
    
    current_date = datetime.now() + timedelta(hours=9)
    target_date = current_date + timedelta(days=date_offset)
    date_info = target_date.strftime('%m월 %d일') + " " + get_korean_day_of_week(target_date.weekday())
    simple_date_info = target_date.strftime('%-m/%-d')

    menus = {"조식": "", "중식": "", "석식": ""}
    response_text = ""  # response_text 변수를 초기화
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
        
        for meal, menu in menus.items():
            if menu:
                response_text += f"{date_info} {meal}\n{menu}\n"
    else:
        for line in lines:
            if simple_date_info in line and meal_type in line:
                menu_found = True
                response_text += f"{date_info} {meal_type}\n"
                continue
            if line.strip() == "---" and menu_found:
                break
            if menu_found:
                if simple_date_info in line or meal_type in line:
                    continue
                response_text += line.strip() + "\n"

    if not any(menus.values()):
        scrape_menu_and_save_to_s3(bucket_name, file_key)
        response_text = "해당하는 메뉴 정보를 찾을 수 없습니다.\n메뉴 자동 갱신 중입니다.\n3초 뒤 다시 시도해 주세요.\n방학 기간엔 교내 사이트에 메뉴 정보가 업로드 되지 않으므로 기다려도 메뉴 정보를 불러올 수 없어요."

    now = datetime.now() + timedelta(hours=9)

    menu_titles = "\n\n".join([
        f"🌅조식\n{menus.get('조식', '메뉴 정보 없음')}",
        f"🖼️중식\n{menus.get('중식', '메뉴 정보 없음')}",
        f"🌆석식\n{menus.get('석식', '메뉴 정보 없음')}"
    ])

    is_weekend = target_date.weekday() in [5, 6]  # Saturday (5) or Sunday (6)

    # 시간별로 아이콘을 변경 (오늘의 메뉴일 때만 적용)
    if date_offset == 0:  # 오늘의 메뉴일 경우만 체크
        if now.time() >= datetime.strptime("08:00", "%H:%M").time() and now.time() <= datetime.strptime("09:00", "%H:%M").time():
            breakfast_icon = "✅"
        else:
            breakfast_icon = "⏰"

        if is_weekend:
            if now.time() >= datetime.strptime("12:00", "%H:%M").time() and now.time() <= datetime.strptime("13:00", "%H:%M").time():
                lunch_icon = "✅"
            else:
                lunch_icon = "⏰"
        else:
            if now.time() >= datetime.strptime("11:30", "%H:%M").time() and now.time() <= datetime.strptime("13:30", "%H:%M").time():
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

    # 주말 여부에 따른 점심 시간 설명
    lunch_time_description = "12:00 ~ 13:00" if is_weekend else "11:30 ~ 13:30"

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
                            "description": "08:00 ~ 09:00"
                        },
                        {
                            "title": f"중식 {lunch_icon}",
                            "description": lunch_time_description
                        },
                        {
                            "title": f"석식 {dinner_icon}",
                            "description": "17:30 ~ 18:30"
                        }
                    ],
                    "buttons": [
                        {
                            "action": "webLink",
                            "label": "전체 메뉴 보러가기",
                            "webLinkUrl": "https://www.mmu.ac.kr/main/contents/todayMenu1"
                        }
                    ],
                    "itemListAlignment": "right"
                }
            }
        ],
        "quickReplies": [
            {
                "messageText": "해성게시판",
                "action": "message",
                "label": "해성게시판"
            },
            {
                "messageText": "해성공지",
                "action": "message",
                "label": "해성공지"
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
