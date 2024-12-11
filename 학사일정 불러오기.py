import json
import requests
from datetime import datetime
from dateutil.relativedelta import relativedelta  # relativedelta를 추가합니다.

def get_schedule(month_offset):
    # 요청할 URL
    url = 'https://www.mmu.ac.kr/main/scheduleList'

    # 현재 날짜를 기준으로 월을 가져오기
    current_date = datetime.now() + relativedelta(months=month_offset)  # 월 단위로 더함
    current_month = current_date.strftime("%Y-%m")  # "2024-11" 형식 (예: 다음달)

    # 요청 데이터 설정
    params = {
        "libType": "D",  # 기본값으로 설정
        "searchDt": current_month,  # 예: "2024-11"
        "hakgi": "0",  # 기본값으로 설정
        "recordCnt": 999,
        "year": current_date.year  # 요청할 연도
    }

    try:
        # GET 요청
        response = requests.get(url, params=params)
        response.raise_for_status()  # 오류가 있을 경우 예외 발생
    except requests.exceptions.RequestException as e:
        # 요청 실패 시 에러 메시지 반환
        return f"일정 데이터를 가져오는 중 오류가 발생했습니다: {e}"

    try:
        # JSON 데이터 로드
        schedule_data = response.json()
    except json.JSONDecodeError:
        return "일정 데이터를 파싱하는 중 오류가 발생했습니다."

    # 결과 출력 형식 준비
    result = {}
    if 'list' in schedule_data and schedule_data['list']:
        for item in schedule_data['list']:
            # 현재 날짜와 비교하여 월이 같은지 확인
            try:
                item_date = datetime.strptime(item['frdt'], "%Y-%m-%d")
            except (KeyError, ValueError):
                continue  # 날짜 형식이 맞지 않거나 키가 없을 경우 건너뜀

            if item_date.month == current_date.month and item_date.year == current_date.year:
                # 날짜가 이미 키로 존재하는지 확인
                if item['frdt'] in result:
                    result[item['frdt']].append(item['title'])  # 제목 추가
                else:
                    result[item['frdt']] = [item['title']]  # 새로운 날짜 키 추가

    # 최종 출력 형식 준비
    formatted_result = []
    if not result:
        formatted_result.append("등록된 일정이 없습니다.")
    else:
        for date, titles in sorted(result.items()):
            # 날짜와 제목을 포맷팅하여 문자열로 결합
            formatted_result.append(f"{date} : {', '.join(titles)}")

    # 최종 결과를 문자열으로 반환
    return "\n".join(formatted_result)

def lambda_handler(event, context):
    try:
        # 이벤트에서 cal_type 파라미터 추출
        body = json.loads(event['body'])
        cal_type = body['action']['params'].get('cal_type', '')

        # 월 오프셋 결정
        month_offset = 0  # 이번달
        if "다음달" in cal_type:
            month_offset = 1
        elif "저번달" in cal_type:
            month_offset = -1

        # 일정 가져오기
        schedule = get_schedule(month_offset)

        # 월과 년도 추출
        current_date = datetime.now() + relativedelta(months=month_offset)
        current_year = current_date.year
        current_month = current_date.month

        # 제목과 설명을 월에 따라 가변적으로 설정
        title = f"{current_year}년 {current_month}월 학사일정"
        description = f"{current_month}월의 학사일정을 불러옵니다."

        # result 출력 형식으로 변경 (simpleText 예시)
        result = {
            "version": "2.0",
            "template": {
                "outputs": [
                    {
                        "simpleText": {
                            "text": f"{title}\n{description}\n\n{schedule}"
                        }
                    }
                ]
            }
        }

        # JSON 응답 반환
        return {
            'statusCode': 200,
            'body': json.dumps(result, ensure_ascii=False),
            'headers': {
                'Content-Type': 'application/json; charset=utf-8',
                'Access-Control-Allow-Origin': '*',
            }
        }

    except Exception as e:
        # 에러 발생 시 적절한 응답 반환
        return {
            'statusCode': 500,
            'body': json.dumps({"message": f"서버 오류가 발생했습니다: {e}"}),
            'headers': {
                'Content-Type': 'application/json; charset=utf-8',
                'Access-Control-Allow-Origin': '*',
            }
        }
