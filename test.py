import streamlit as st
import pandas as pd
from io import BytesIO
import requests
import json
from bs4 import BeautifulSoup

# JSON 파일에서 법정동 코드 가져오기
def get_dong_codes_for_city(city_name, sigungu_name=None, json_path='district.json'):
    try:
        with open(json_path, 'r', encoding='utf-8') as file:
            data = json.load(file)
    except FileNotFoundError:
        st.error(f"Error: The file at {json_path} was not found.")
        return None, None

    for si_do in data:
        if si_do['si_do_name'] == city_name:
            if sigungu_name and sigungu_name != '전체':
                for sigungu in si_do['sigungu']:
                    if sigungu['sigungu_name'] == sigungu_name:
                        return [sigungu['sigungu_code']], [
                            {'code': dong['code'], 'name': dong['name']} for dong in sigungu['eup_myeon_dong']
                        ]
            else:
                sigungu_codes = [sigungu['sigungu_code'] for sigungu in si_do['sigungu']]
                dong_codes = [
                    {'code': dong['code'], 'name': dong['name']}
                    for sigungu in si_do['sigungu']
                    for dong in sigungu['eup_myeon_dong']
                ]
                return sigungu_codes, dong_codes
    return None, None

# 아파트 코드 리스트 가져오기
def get_apt_list(dong_code):
    down_url = f'https://new.land.naver.com/api/regions/complexes?cortarNo={dong_code}&realEstateType=APT&order='
    header = {
        "Accept-Encoding": "gzip",
        "Host": "new.land.naver.com",
        "Referer": "https://new.land.naver.com/complexes/102378",
        "Sec-Fetch-Dest": "empty",
        "Sec-Fetch-Mode": "cors",
        "Sec-Fetch-Site": "same-origin",
        "User-Agent": "Mozilla/5.0"
    }

    try:
        r = requests.get(down_url, headers=header)
        r.encoding = "utf-8-sig"
        data = r.json()

        if 'complexList' in data and isinstance(data['complexList'], list):
            df = pd.DataFrame(data['complexList'])
            required_columns = ['complexNo', 'complexName', 'buildYear', 'totalHouseholdCount', 'areaSize', 'price', 'address', 'floor']

            for col in required_columns:
                if col not in df.columns:
                    df[col] = None

            return df[required_columns]
        else:
            st.warning(f"No data found for {dong_code}.")
            return pd.DataFrame(columns=required_columns)

    except Exception as e:
        st.error(f"Error fetching data for {dong_code}: {e}")
        return pd.DataFrame(columns=required_columns)
    
def get_apt_details(apt_code):
    URL = "https://m.land.naver.com/complex/getComplexArticleList"

    parameter = {
        'hscpNo': apt_code,
        'tradTpCd': 'A1:B1:B2',  # 거래방식 3가지
        'order': 'spc_',  # 면적별 정렬
    }

    header = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
        'Referer': 'https://m.land.naver.com/'
    }

    page = 0
    lands = []

    try:
        while True:
            page += 1
            parameter['page'] = page

            response = requests.get(URL, params=parameter, headers=header)
            
            if response.status_code != 200:
                print('invalid status: %d' % response.status_code)
                break

            data = json.loads(response.text)
            result = data['result']
            
            if result is None:
                print('no result')
                break

            for item in result['list']:
                lands.append([
                    item['atclNm'],
                    item['tradTpNm'],  # 거래 타입 이름
                    item['bildNm'],    # 건물 이름
                    item['flrInfo'],   # 층 정보
                    item['prcInfo'],   # 가격 정보
                    item['spc1']       # 면적 정보
                ])

            if result['moreDataYn'] == 'N':
                break

    except Exception as e:
        st.error(f"Error fetching data: {e}")
        return pd.DataFrame()

import pdb
# 아파트 정보를 수집하는 함수
def collect_apt_info_for_city(city_name, sigungu_name, dong_name=None, json_path='district.json'):
    sigungu_codes, dong_list = get_dong_codes_for_city(city_name, sigungu_name, json_path)

    if dong_list is None:
        st.error(f"Error: {city_name} not found in JSON.")
        return None

    all_apt_data = []
    dong_code_name_map = {dong['code']: dong['name'] for dong in dong_list}
    
    # 수집 중 표시를 위한 placeholder
    placeholder = st.empty()

    if dong_name and dong_name != '전체':
        dong_code_name_map = {k: v for k, v in dong_code_name_map.items() if v == dong_name}

    for dong_code, dong_name in dong_code_name_map.items():
        placeholder.write(f"{dong_name} ({dong_code}) - 수집중입니다.")
        apt_codes = get_apt_list(dong_code)

        if not apt_codes.empty:
            for _, apt_info in apt_codes.iterrows():
                apt_code = apt_info['complexNo']
                apt_name = apt_info['complexName']
                placeholder.write(f"{apt_name} ({apt_code}) - 수집중입니다.")
                listings = get_apt_details(apt_code)
                
                if listings:
                    for listing in listings:
                        listing['dong_code'] = dong_code
                        listing['dong_name'] = dong_name
                        all_apt_data.append(listing)
        else:
            st.warning(f"No apartment codes found for {dong_code}")

    # 수집이 완료된 후, 수집 중 메시지를 지우기
    placeholder.empty()

    if all_apt_data:
        final_df = pd.DataFrame(all_apt_data)
        final_df['si_do_name'] = city_name
        final_df['sigungu_name'] = sigungu_name
        final_df['dong_name'] = dong_name if dong_name else '전체'
        
        # 데이터프레임 결과 출력
        st.write("아파트 정보 수집 완료:")
        st.dataframe(final_df)

        # 엑셀 파일로 저장
        output = BytesIO()
        with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
            final_df.to_excel(writer, index=False)
        output.seek(0)

        # 엑셀 파일 다운로드 버튼
        st.download_button(
            label="Download Excel",
            data=output,
            file_name=f"{city_name}_{sigungu_name}_apartments.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )

        # CSV 파일 다운로드 버튼
        csv = final_df.to_csv(index=False).encode('utf-8')
        st.download_button(
            label="Download CSV",
            data=csv,
            file_name=f"{city_name}_{sigungu_name}_apartments.csv",
            mime="text/csv"
        )
    else:
        st.write("No data to save.")

# Streamlit 앱 실행
st.title("아파트 정보 수집기")

# 사용자 입력 받기
city_name = st.text_input("시/도 이름 입력", "서울특별시")
sigungu_name = st.text_input("구/군/구 이름 입력", "강남구")
dong_name = st.text_input("동 이름 입력 (선택사항)", "전체")

if st.button("정보 수집 시작"):
    collect_apt_info_for_city(city_name, sigungu_name, dong_name)


    