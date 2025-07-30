# PLM_calculation.py (API 제거 + 주말 자동 제외 + 수동 제외 유지)

import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime, date, timedelta
import json
import os
from PIL import Image
import io
import base64
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import time

# ✅ 앱 설정
st.set_page_config(page_title="이퀄베리 신제품 일정 관리", layout="wide")

# ✅ 기본 단계 정의
DEFAULT_PHASES = [
    {"단계": "사전 시장조사", "리드타임": 20, "담당자": "", "Asana Task 코드": ""},
    {"단계": "부자재 서칭 및 샘플링", "리드타임": 27, "담당자": "", "Asana Task 코드": ""},
    {"단계": "CT 및 사전 품질 확보", "리드타임": 10, "담당자": "", "Asana Task 코드": ""},
    {"단계": "부자재 발주~입고", "리드타임": 30, "담당자": "", "Asana Task 코드": ""},
    {"단계": "완제품 발주~생산", "리드타임": 20, "담당자": "", "Asana Task 코드": ""},
    {"단계": "품질 초도 검사~입고", "리드타임": 5, "담당자": "", "Asana Task 코드": ""},
]

# ✅ 총 리드타임 계산 (세션 상태 초기화 후)
def calculate_total_lead_time():
    total_lead_time = 0
    if "phases" in st.session_state and not st.session_state.phases.empty:
        total_lead_time = st.session_state.phases["리드타임"].sum()
    return total_lead_time




def save_product_data(product_name, product_data, filename=None):
    """제품 데이터를 JSON 파일로 저장"""
    try:
        if filename is None:
            filename = f"{product_name}_product_data.json"
        
        # productPLM 폴더에 저장
        file_path = os.path.join("productPLM", filename)
        
        # DataFrame을 딕셔너리로 변환
        phases_dict = product_data["phases"].to_dict(orient="records") if not product_data["phases"].empty else []
        excludes_list = [d.isoformat() for d in product_data["custom_excludes"]] if product_data["custom_excludes"] else []
        
        save_data = {
            "product_name": product_name,
            "phases": phases_dict,
            "custom_excludes": excludes_list,
            "target_date": product_data["target_date"].isoformat() if product_data["target_date"] else None,
            "team_members": product_data.get("team_members", []),
            "saved_at": datetime.now().isoformat(),
            "description": "제품별 개발 일정 데이터"
        }
        
        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump(save_data, f, ensure_ascii=False, indent=2)
        return True
    except Exception as e:
        st.error(f"제품 데이터 저장 중 오류 발생: {e}")
        return False

def load_product_data(filename):
    """제품 데이터를 JSON 파일에서 불러오기"""
    try:
        # productPLM 폴더에서 로드
        file_path = os.path.join("productPLM", filename)
        if os.path.exists(file_path):
            with open(file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            # 딕셔너리를 DataFrame으로 변환
            phases_df = pd.DataFrame(data.get("phases", []))
            excludes_set = {datetime.fromisoformat(d).date() for d in data.get("custom_excludes", [])}
            target_date = datetime.fromisoformat(data["target_date"]).date() if data.get("target_date") else None
            
            return {
                "phases": phases_df,
                "custom_excludes": excludes_set,
                "target_date": target_date,
                "team_members": data.get("team_members", [])
            }
        return None
    except Exception as e:
        st.error(f"제품 데이터 불러오기 중 오류 발생: {e}")
        return None


# ✅ 일정 역산
def backward_schedule(target_date, phases, excluded_days):
    schedule = []
    current_date = target_date
    
    for phase in reversed(phases):
        name, lead_time = phase['단계'], phase['리드타임']
        담당자, asana_code = phase.get("담당자", ""), phase.get("Asana Task 코드", "")
        workdays, date_cursor = 0, current_date
        
        # 리드타임만큼 평일을 역산
        while workdays < lead_time:
            date_cursor -= timedelta(days=1)
            if date_cursor.weekday() < 5 and date_cursor not in excluded_days:
                workdays += 1
        
        # 시작일이 주말이거나 제외일인 경우 평일로 조정
        start_date = date_cursor + timedelta(days=1)
        while start_date.weekday() >= 5 or start_date in excluded_days:
            start_date -= timedelta(days=1)
        
        schedule.append({
            "단계": name,
            "시작일": start_date,
            "종료일": current_date,
            "담당자": 담당자,
            "Asana Task 코드": asana_code
        })
        current_date = start_date
    
    return list(reversed(schedule))

# ✅ 시각화 옵션들
def show_timeline_view(df):
    """타임라인 뷰 - 각 단계별 진행 상황을 시간순으로 표시"""
    df_chart = df.copy()
    df_chart["시작일"] = pd.to_datetime(df_chart["시작일"])
    df_chart["종료일"] = pd.to_datetime(df_chart["종료일"])
    df_chart["기간"] = (df_chart["종료일"] - df_chart["시작일"]).dt.days + 1
    
    # 연도 정보 추가
    start_year = df_chart["시작일"].min().year
    end_year = df_chart["종료일"].max().year
    year_range = f"{start_year}년" if start_year == end_year else f"{start_year}년~{end_year}년"
    
    # 타임라인 차트
    fig = px.timeline(df_chart, x_start="시작일", x_end="종료일", y="단계", 
                      color="단계", hover_data=["담당자", "Asana Task 코드", "기간"])
    
    # 세로축 개선 - 가로 구분선 추가
    fig.update_yaxes(
        title="개발 단계",
        autorange="reversed",
        showgrid=True,
        gridwidth=1,
        gridcolor='lightgray',
        zeroline=False
    )
    
    # 가로축 개선
    fig.update_xaxes(
        title="날짜",
        showgrid=False,
        zeroline=False
    )
    
    # 레이아웃 개선
    fig.update_layout(
        title=f"📅 개발 일정 타임라인 ({year_range})", 
        height=400,
        showlegend=True,
        legend=dict(
            orientation="h",
            yanchor="bottom",
            y=1.02,
            xanchor="right",
            x=1
        ),
        margin=dict(l=50, r=50, t=80, b=50)
    )
    
    # 타임라인 바에 텍스트 추가
    for i, row in df_chart.iterrows():
        # 중간 지점 계산
        mid_date = row["시작일"] + (row["종료일"] - row["시작일"]) / 2
        
        # 텍스트 추가
        fig.add_annotation(
            x=mid_date,
            y=row["단계"],
            text=row["단계"],
            showarrow=False,
            font=dict(size=10, color="white"),
            bgcolor="rgba(0,0,0,0.7)",
            bordercolor="white",
            borderwidth=1
        )
        
        # 담당자 정보도 추가 (있는 경우)
        if row["담당자"]:
            fig.add_annotation(
                x=mid_date,
                y=row["단계"],
                text=f"👤 {row['담당자']}",
                showarrow=False,
                font=dict(size=8, color="white"),
                bgcolor="rgba(0,0,0,0.5)",
                bordercolor="white",
                borderwidth=1,
                yshift=-20
            )
    
    st.plotly_chart(fig, use_container_width=True)

def show_progress_cards(df):
    """진행 카드 뷰 - 각 단계를 카드 형태로 표시"""
    # 연도 정보 계산
    df_temp = df.copy()
    df_temp["시작일"] = pd.to_datetime(df_temp["시작일"])
    df_temp["종료일"] = pd.to_datetime(df_temp["종료일"])
    start_year = df_temp["시작일"].min().year
    end_year = df_temp["종료일"].max().year
    year_range = f"{start_year}년" if start_year == end_year else f"{start_year}년~{end_year}년"
    
    st.subheader(f"📋 단계별 진행 상황 ({year_range})")
    
    # 단계명 길이에 따른 폰트 크기 자동 조정
    max_phase_length = max(len(row['단계']) for _, row in df.iterrows())
    
    # 폰트 크기 자동 계산 (최소 12px, 최대 18px)
    if max_phase_length <= 10:
        title_font_size = "18px"
        content_font_size = "14px"
        small_font_size = "12px"
    elif max_phase_length <= 15:
        title_font_size = "16px"
        content_font_size = "13px"
        small_font_size = "11px"
    else:
        title_font_size = "14px"
        content_font_size = "12px"
        small_font_size = "10px"
    
    cols = st.columns(len(df))
    for i, (_, row) in enumerate(df.iterrows()):
        with cols[i]:
            start_date = pd.to_datetime(row["시작일"])
            end_date = pd.to_datetime(row["종료일"])
            duration = (end_date - start_date).days + 1
            
            st.markdown(f"""
            <div style="border: 2px solid #e0e0e0; border-radius: 10px; padding: 15px; margin: 5px; background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: white; height: 200px; display: flex; flex-direction: column; justify-content: space-between;">
                <h3 style="margin: 0; color: white; font-size: {title_font_size}; line-height: 1.2; word-wrap: break-word;">{row['단계']}</h3>
                <div style="flex-grow: 1;">
                    <p style="margin: 5px 0; font-size: {content_font_size};">📅 {start_date.strftime('%Y/%m/%d')} ~ {end_date.strftime('%Y/%m/%d')}</p>
                    <p style="margin: 5px 0; font-size: {small_font_size};">⏱️ {duration}일</p>
                    <p style="margin: 5px 0; font-size: {small_font_size};">👤 {row['담당자'] if row['담당자'] else '미정'}</p>
                    <p style="margin: 5px 0; font-size: {small_font_size};">📝 {row['Asana Task 코드'] if row['Asana Task 코드'] else '-'}</p>
                </div>
            </div>
            """, unsafe_allow_html=True)

def show_calendar_grid(df, excluded_days=None):
    """캘린더 그리드 뷰 - 월별 캘린더 안에 주별 단계 표시"""
    st.subheader("📅 월별 캘린더 뷰")
    
    # excluded_days가 None이면 빈 set으로 초기화
    if excluded_days is None:
        excluded_days = set()
    
    # 색상별 단계 설명을 상단에 한 번만 표시
    st.markdown("### 🎨 단계별 색상 설명")
    phase_colors = {
        "사전 시장조사": "#E3F2FD",
        "부자재 서칭 및 샘플링": "#F3E5F5",
        "CT 및 사전 품질 확보": "#E8F5E8",
        "부자재 발주~입고": "#FFF3E0",
        "완제품 발주~생산": "#FCE4EC",
        "품질 초도 검사~입고": "#E0F2F1"
    }
    
    # 색상 설명을 2열로 배치
    legend_cols = st.columns(2)
    for i, (phase, color) in enumerate(phase_colors.items()):
        with legend_cols[i % 2]:
            st.markdown(f"""
            <div style="display: flex; align-items: center; margin: 8px 0;">
                <div style="width: 25px; height: 25px; background: {color}; border: 1px solid #ddd; border-radius: 4px; margin-right: 12px;"></div>
                <span style="font-size: 14px; font-weight: 500;">{phase}</span>
            </div>
            """, unsafe_allow_html=True)
    
    st.markdown("<br>", unsafe_allow_html=True)
    
    # 모든 날짜 범위 계산
    all_dates = []
    for _, row in df.iterrows():
        start = pd.to_datetime(row["시작일"])
        end = pd.to_datetime(row["종료일"])
        date_range = pd.date_range(start, end, freq='D')
        all_dates.extend([(d, row["단계"], row["담당자"], row["Asana Task 코드"]) for d in date_range])
    
    if all_dates:
        # 월별로 그룹화
        df_dates = pd.DataFrame(all_dates, columns=['날짜', '단계', '담당자', 'Asana Task 코드'])
        df_dates['월'] = df_dates['날짜'].dt.to_period('M')
        
        # 연도별로 그룹화하여 표시
        df_dates['연도'] = df_dates['날짜'].dt.year
        years = sorted(df_dates['연도'].unique())
        
        # 캘린더 HTML 생성
        calendar_html = generate_calendar_html(df_dates, years, phase_colors, excluded_days)
        
        # 캘린더 표시
        st.markdown(calendar_html, unsafe_allow_html=True)
        
        # 이미지 저장 기능
        st.markdown("---")
        st.subheader("📸 캘린더 이미지 저장")
        
        col1, col2 = st.columns([1, 1])
        
        with col1:
            if st.button("🖼️ 캘린더 이미지 생성", key="generate_calendar_image_btn"):
                with st.spinner("이미지를 생성하고 있습니다..."):
                    try:
                        # 이미지 생성
                        image_data = generate_calendar_image(calendar_html)
                        if image_data:
                            st.session_state.calendar_image = image_data
                            st.success("✅ 캘린더 이미지가 생성되었습니다!")
                        else:
                            st.error("❌ 이미지 생성에 실패했습니다.")
                    except Exception as e:
                        st.error(f"❌ 이미지 생성 중 오류 발생: {e}")
        
        with col2:
            if "calendar_image" in st.session_state and st.session_state.calendar_image:
                # 이미지 다운로드 버튼
                filename = f"캘린더_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png"
                st.download_button(
                    "📥 이미지 다운로드",
                    data=st.session_state.calendar_image,
                    file_name=filename,
                    mime="image/png",
                    key="download_calendar_image_btn"
                )
            else:
                st.info("이미지를 먼저 생성해주세요.")
        
        # HTML 다운로드 대안 제공
        st.markdown("### 📄 HTML 다운로드 (대안)")
        st.info("이미지 생성이 실패하는 경우 HTML 파일을 다운로드하여 브라우저에서 열어보세요.")
        
        # HTML 파일 생성
        html_filename = f"캘린더_{datetime.now().strftime('%Y%m%d_%H%M%S')}.html"
        html_content_full = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="utf-8">
            <title>개발 일정 캘린더</title>
            <style>
                body {{ 
                    font-family: Arial, sans-serif; 
                    margin: 0; 
                    padding: 20px 200px 20px 20px;
                    background: white;
                    width: 1200px;
                    overflow: hidden;
                }}
                .calendar-container {{
                    background: white;
                    padding: 20px;
                    border-radius: 10px;
                    box-shadow: 0 2px 10px rgba(0,0,0,0.1);
                    overflow: hidden;
                    margin-left: 0;
                }}
                /* 스크롤바 숨기기 */
                ::-webkit-scrollbar {{
                    display: none;
                }}
                html {{
                    scrollbar-width: none;
                }}
                body {{
                    -ms-overflow-style: none;
                }}
            </style>
        </head>
        <body>
            <div class="calendar-container">
                {calendar_html}
            </div>
        </body>
        </html>
        """
        
        st.download_button(
            "📥 HTML 다운로드",
            data=html_content_full.encode('utf-8'),
            file_name=html_filename,
            mime="text/html",
            key="download_calendar_html_btn"
        )
    else:
        st.info("표시할 일정이 없습니다.")

def generate_calendar_html(df_dates, years, phase_colors, excluded_days):
    """캘린더 HTML 생성"""
    html_parts = []
    
    for year in years:
        year_data = df_dates[df_dates['연도'] == year]
        months = sorted(year_data['월'].unique())
        
        # 월별로 가로 배치 (최대 3개월씩)
        for i in range(0, len(months), 3):
            month_group = months[i:i+3]
            
            html_parts.append('<div style="display: flex; gap: 20px; margin-bottom: 30px;">')
            
            for j in range(3):  # 항상 3개 컬럼 사용
                if j < len(month_group):
                    month = month_group[j]
                    month_data = year_data[year_data['월'] == month]
                    
                    html_parts.append(f'''
                    <div style="border: 2px solid #e0e0e0; border-radius: 8px; padding: 15px; background: #fafafa; flex: 1; min-width: 200px;">
                        <h4 style="margin: 0 0 15px 0; text-align: center; color: #333;">{month.strftime('%Y년 %m월')}</h4>
                    ''')
                    
                    # 요일 헤더
                    weekdays = ['월', '화', '수', '목', '금', '토', '일']
                    header_html = '<div style="display: grid; grid-template-columns: repeat(7, 1fr); gap: 2px; margin-bottom: 10px;">'
                    for day in weekdays:
                        header_html += f'<div style="text-align: center; font-weight: bold; font-size: 12px; padding: 5px;">{day}</div>'
                    header_html += '</div>'
                    html_parts.append(header_html)
                    
                    # 월의 첫 주 시작일과 마지막 주 종료일 계산
                    month_start = month_data['날짜'].min()
                    month_end = month_data['날짜'].max()
                    first_week_start = month_start - timedelta(days=month_start.weekday())
                    last_week_end = month_end + timedelta(days=6-month_end.weekday())
                    
                    # 주별로 캘린더 표시
                    current_date = first_week_start
                    while current_date <= last_week_end:
                        week_html = '<div style="display: grid; grid-template-columns: repeat(7, 1fr); gap: 2px; margin-bottom: 5px;">'
                        
                        for k in range(7):  # 한 주의 7일
                            check_date = current_date + timedelta(days=k)
                            
                            # 해당 날짜의 단계 정보 확인
                            date_data = month_data[month_data['날짜'] == check_date]
                            
                            # 날짜 스타일 결정
                            date_style = "text-align: center; padding: 8px; font-size: 12px; border-radius: 4px;"
                            
                            if check_date.weekday() >= 5 or check_date.date() in excluded_days:
                                # 주말 또는 제외일
                                date_style += "color: #ff4444; background: #f8f8f8;"
                                date_text = f'<div style="{date_style}">{check_date.day}</div>'
                            elif not date_data.empty:
                                # 단계가 있는 날짜
                                phase = date_data.iloc[0]['단계']
                                color = phase_colors.get(phase, "#E0E0E0")
                                date_style += f"background: {color}; border: 1px solid #ddd;"
                                date_text = f'<div style="{date_style}">{check_date.day}</div>'
                            else:
                                # 일반 날짜
                                date_style += "background: white; border: 1px solid #eee;"
                                date_text = f'<div style="{date_style}">{check_date.day}</div>'
                            
                            week_html += date_text
                        
                        week_html += '</div>'
                        html_parts.append(week_html)
                        
                        current_date += timedelta(days=7)
                    
                    html_parts.append('</div>')
                else:
                    # 빈 컬럼
                    html_parts.append('<div style="flex: 1;"></div>')
            
            html_parts.append('</div>')
    
    return ''.join(html_parts)

def generate_calendar_image(html_content):
    """HTML을 이미지로 변환"""
    try:
        # 임시 HTML 파일 생성
        temp_html = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="utf-8">
            <style>
                body {{ 
                    font-family: Arial, sans-serif; 
                    margin: 0; 
                    padding: 20px 200px 20px 20px;
                    background: white;
                    width: 1200px;
                    overflow: hidden;
                }}
                .calendar-container {{
                    background: white;
                    padding: 20px;
                    border-radius: 10px;
                    box-shadow: 0 2px 10px rgba(0,0,0,0.1);
                    overflow: hidden;
                    margin-left: 0;
                }}
                /* 스크롤바 숨기기 */
                ::-webkit-scrollbar {{
                    display: none;
                }}
                /* Firefox 스크롤바 숨기기 */
                html {{
                    scrollbar-width: none;
                }}
                /* IE/Edge 스크롤바 숨기기 */
                body {{
                    -ms-overflow-style: none;
                }}
            </style>
        </head>
        <body>
            <div class="calendar-container">
                {html_content}
            </div>
        </body>
        </html>
        """
        
        # 임시 파일 저장
        temp_file = f"temp_calendar_{int(time.time())}.html"
        with open(temp_file, 'w', encoding='utf-8') as f:
            f.write(temp_html)
        
        # Chrome 옵션 설정 (Streamlit Cloud 환경에 최적화)
        chrome_options = Options()
        chrome_options.add_argument("--headless")
        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument("--disable-dev-shm-usage")
        chrome_options.add_argument("--hide-scrollbars")
        chrome_options.add_argument("--disable-scrollbars")
        chrome_options.add_argument("--disable-gpu")
        chrome_options.add_argument("--remote-debugging-port=9222")
        chrome_options.add_argument("--disable-extensions")
        chrome_options.add_argument("--disable-plugins")
        chrome_options.add_argument("--disable-images")
        chrome_options.add_argument("--disable-javascript")
        chrome_options.add_argument("--disable-web-security")
        chrome_options.add_argument("--allow-running-insecure-content")
        chrome_options.add_argument("--disable-background-timer-throttling")
        chrome_options.add_argument("--disable-backgrounding-occluded-windows")
        chrome_options.add_argument("--disable-renderer-backgrounding")
        chrome_options.add_argument("--disable-features=TranslateUI")
        chrome_options.add_argument("--disable-ipc-flooding-protection")
        
        # Streamlit Cloud 환경 감지
        import os
        if os.environ.get('STREAMLIT_SERVER_RUN_ON_IP') or os.environ.get('STREAMLIT_SERVER_PORT'):
            # Streamlit Cloud 환경에서는 webdriver-manager 사용
            try:
                from webdriver_manager.chrome import ChromeDriverManager
                from selenium.webdriver.chrome.service import Service
                
                service = Service(ChromeDriverManager().install())
                driver = webdriver.Chrome(service=service, options=chrome_options)
            except Exception as e:
                st.error(f"Chrome 드라이버 설치 실패: {e}")
                return None
        else:
            # 로컬 환경에서는 기본 Chrome 드라이버 사용
            try:
                driver = webdriver.Chrome(options=chrome_options)
            except Exception as e:
                st.error(f"Chrome 드라이버 실행 실패: {e}")
                return None
        
        try:
            driver.get(f"file://{os.path.abspath(temp_file)}")
            
            # 페이지 로딩 대기
            WebDriverWait(driver, 10).until(
                EC.presence_of_element_located((By.TAG_NAME, "body"))
            )
            
            # JavaScript로 스크롤바 숨기기
            driver.execute_script("""
                document.body.style.overflow = 'hidden';
                document.documentElement.style.overflow = 'hidden';
                document.body.style.scrollbarWidth = 'none';
                document.body.style.msOverflowStyle = 'none';
            """)
            
            # 캘린더 컨테이너의 실제 높이 계산
            calendar_height = driver.execute_script("""
                var container = document.querySelector('.calendar-container');
                return container.scrollHeight;
            """)
            
            # 여백을 포함한 전체 높이 계산 (상하 패딩 40px + 여유 120px)
            total_height = calendar_height + 160
            
            # 브라우저 창 크기를 동적으로 조정
            driver.set_window_size(1200, total_height)
            
            # 페이지가 다시 렌더링될 때까지 잠시 대기
            time.sleep(1)
            
            # 스크린샷 촬영
            screenshot = driver.get_screenshot_as_png()
            
            # 임시 파일 삭제
            os.remove(temp_file)
            
            return screenshot
            
        finally:
            driver.quit()
            
    except Exception as e:
        st.error(f"이미지 생성 중 오류: {e}")
        # 임시 파일 정리
        try:
            if os.path.exists(temp_file):
                os.remove(temp_file)
        except:
            pass
        return None

def show_kanban_board(df):
    """칸반 보드 뷰 - 진행 상태별로 단계를 분류"""
    # 연도 정보 계산
    df_temp = df.copy()
    df_temp["시작일"] = pd.to_datetime(df_temp["시작일"])
    df_temp["종료일"] = pd.to_datetime(df_temp["종료일"])
    start_year = df_temp["시작일"].min().year
    end_year = df_temp["종료일"].max().year
    year_range = f"{start_year}년" if start_year == end_year else f"{start_year}년~{end_year}년"
    
    st.subheader(f"📊 칸반 보드 ({year_range})")
    
    # 오늘 날짜 기준으로 진행 상태 자동 판단
    today = datetime.today().date()
    
    def determine_status(row):
        start_date = pd.to_datetime(row["시작일"]).date()
        end_date = pd.to_datetime(row["종료일"]).date()
        
        if start_date <= today <= end_date:
            return "진행중"
        elif start_date > today and end_date > today:
            return "준비중"
        elif start_date < today and end_date < today:
            return "완료"
        else:
            return "진행중"  # 기본값
    
    df_kanban = df.copy()
    df_kanban["상태"] = df_kanban.apply(determine_status, axis=1)
    
    # 상태별 컬럼 생성
    statuses = ["준비중", "진행중", "완료"]
    cols = st.columns(len(statuses))
    
    for i, status in enumerate(statuses):
        with cols[i]:
            # 상태별 색상 설정
            if status == "준비중":
                status_color = "#FFE6B3"  # 연한 주황
                border_color = "#FFA500"
            elif status == "진행중":
                status_color = "#E6F3FF"  # 연한 파랑
                border_color = "#0066CC"
            else:  # 완료
                status_color = "#E6FFE6"  # 연한 초록
                border_color = "#00CC00"
            
            st.markdown(f"### {status}")
            status_data = df_kanban[df_kanban["상태"] == status]
            
            if status_data.empty:
                st.info(f"📝 {status} 상태의 작업이 없습니다.")
            else:
                for _, row in status_data.iterrows():
                    start_date = pd.to_datetime(row["시작일"])
                    end_date = pd.to_datetime(row["종료일"])
                    duration = (end_date - start_date).days + 1
                    
                    # 단계명 길이에 따른 폰트 크기 자동 조정
                    phase_length = len(row['단계'])
                    if phase_length <= 10:
                        title_font_size = "16px"
                        content_font_size = "12px"
                    elif phase_length <= 15:
                        title_font_size = "14px"
                        content_font_size = "11px"
                    else:
                        title_font_size = "12px"
                        content_font_size = "10px"
                    
                    st.markdown(f"""
                    <div style="border: 2px solid {border_color}; border-radius: 8px; padding: 10px; margin: 5px 0; background: {status_color}; height: 120px; display: flex; flex-direction: column; justify-content: space-between;">
                        <strong style="font-size: {title_font_size}; line-height: 1.2; word-wrap: break-word;">{row['단계']}</strong>
                        <div>
                            <small style="font-size: {content_font_size};">📅 {start_date.strftime('%Y/%m/%d')} ~ {end_date.strftime('%Y/%m/%d')}</small><br>
                            <small style="font-size: {content_font_size};">⏱️ {duration}일</small><br>
                            <small style="font-size: {content_font_size};">👤 {row['담당자'] if row['담당자'] else '미정'}</small>
                        </div>
                    </div>
                    """, unsafe_allow_html=True)

# ✅ 세션 초기화
if "products" not in st.session_state:
    st.session_state.products = {}
if "current_product" not in st.session_state:
    st.session_state.current_product = "새 제품"
if "phases" not in st.session_state:
    st.session_state.phases = pd.DataFrame(DEFAULT_PHASES).copy()
    # Asana Task 코드 컬럼이 없으면 추가
    if "Asana Task 코드" not in st.session_state.phases.columns:
        st.session_state.phases["Asana Task 코드"] = ""
if "custom_excludes" not in st.session_state:
    st.session_state.custom_excludes = set()

if "team_members" not in st.session_state:
    st.session_state.team_members = []

if "target_date" not in st.session_state:
    st.session_state.target_date = datetime.today().date()

if "new_product_input" not in st.session_state:
    st.session_state.new_product_input = ""

if "new_member_input" not in st.session_state:
    st.session_state.new_member_input = ""

if "exclude_date_input" not in st.session_state:
    st.session_state.exclude_date_input = datetime.today().date()

# 기존 데이터를 새로운 용어로 업데이트 (필요한 경우)
if "phases" in st.session_state and not st.session_state.phases.empty:
    # 기존 용어를 새로운 용어로 매핑
    old_to_new = {
        "시장조사": "사전 시장조사",
        "샘플링": "부자재 서칭 및 샘플링", 
        "완제품 발주~입고": "완제품 발주~생산",
        "품질 입고 검사": "품질 초도 검사~입고"
    }
    
    # 단계명 업데이트
    st.session_state.phases["단계"] = st.session_state.phases["단계"].replace(old_to_new)
    
    # 비고 컬럼을 Asana Task 코드로 변경
    if "비고" in st.session_state.phases.columns:
        st.session_state.phases = st.session_state.phases.rename(columns={"비고": "Asana Task 코드"})
    elif "Asana Task 코드" not in st.session_state.phases.columns:
        # Asana Task 코드 컬럼이 없으면 빈 컬럼 추가
        st.session_state.phases["Asana Task 코드"] = ""

# ✅ 제목과 총 리드타임 표시
total_lead_time = calculate_total_lead_time()
col1, col2 = st.columns([3, 1])
with col1:
    st.title("🛠️ 이퀄베리 신제품 일정은 이렇답니다")
with col2:
    st.metric("📊 총 리드타임", f"{total_lead_time}일")

st.markdown("---")

# ✅ 제품 관리
st.subheader("📦 제품 관리")

def add_product():
    if st.session_state.new_product_input and st.session_state.new_product_input.strip():
        product_name = st.session_state.new_product_input.strip()
        if product_name not in st.session_state.products:
            st.session_state.products[product_name] = {
                "phases": pd.DataFrame(DEFAULT_PHASES),
                "custom_excludes": set(),
                "target_date": datetime.today().date(),
                "team_members": st.session_state.team_members.copy() if st.session_state.team_members else []
            }
            st.session_state.current_product = product_name
            st.session_state.new_product_input = ""  # 입력 필드 초기화
            st.success(f"✅ '{product_name}' 제품이 추가되었습니다.")
            st.rerun()
        else:
            st.warning("이미 존재하는 제품명입니다.")

col1, col2 = st.columns([3, 1])

with col1:
    # 제품명 입력
    new_product = st.text_input(
        "새 제품명 입력 (엔터키로 바로 추가)",
        placeholder="예: 신제품A, 화장품B 등",
        value=st.session_state.new_product_input,
        on_change=add_product,
        key="new_product_input"
    )

with col2:
    # 제품 추가/삭제 버튼을 나란히 배치
    col_add, col_del = st.columns(2)
    
    with col_add:
        if st.button("➕ 제품 추가", key="add_product_btn"):
            if new_product and new_product.strip():
                if new_product.strip() not in st.session_state.products:
                    st.session_state.products[new_product.strip()] = {
                        "phases": pd.DataFrame(DEFAULT_PHASES),
                        "custom_excludes": set(),
                        "target_date": datetime.today().date(),
                        "team_members": st.session_state.team_members.copy() if st.session_state.team_members else []
                    }
                    st.session_state.current_product = new_product.strip()
                    st.success(f"✅ '{new_product.strip()}' 제품이 추가되었습니다.")
                    st.rerun()
                else:
                    st.warning("이미 존재하는 제품명입니다.")

    with col_del:
        if st.button("🗑️ 삭제", key="delete_product_btn"):
            if st.session_state.current_product in st.session_state.products:
                del st.session_state.products[st.session_state.current_product]
                st.session_state.current_product = "새 제품"
                st.success("✅ 제품이 삭제되었습니다.")
                st.rerun()

# 제품 선택 드롭다운
product_options = ["새 제품"] + list(st.session_state.products.keys())
selected_product = st.selectbox("📋 제품 선택", product_options, index=product_options.index(st.session_state.current_product))

if selected_product != st.session_state.current_product:
    st.session_state.current_product = selected_product
    st.rerun()

# 현재 제품 정보 표시
if st.session_state.current_product != "새 제품":
    st.info(f"📋 현재 선택된 제품: **{st.session_state.current_product}**")
    
    # 제품별 저장 상태 표시
    if st.session_state.current_product in st.session_state.products:
        product_data = st.session_state.products[st.session_state.current_product]
        saved_info = []
        if not product_data["phases"].empty:
            phase_names = [phase for phase in product_data["phases"]["단계"] if phase]
            if phase_names:
                saved_info.append(f"단계 {len(phase_names)}개: {', '.join(phase_names[:3])}{'...' if len(phase_names) > 3 else ''}")
            else:
                saved_info.append("단계 0개")
        if product_data["custom_excludes"]:
            saved_info.append(f"제외일 {len(product_data['custom_excludes'])}개")
        if "team_members" in product_data and product_data["team_members"]:
            saved_info.append(f"담당자 {len(product_data['team_members'])}명")
        if "target_date" in product_data:
            saved_info.append(f"목표일 {product_data['target_date']}")
        
        if saved_info:
            st.success(f"💾 저장된 정보: {', '.join(saved_info)}")
        else:
            st.warning("⚠️ 아직 저장된 정보가 없습니다.")

# ✅ 제품별 데이터 불러오기
if st.session_state.current_product != "새 제품":
    if st.session_state.current_product in st.session_state.products:
        product_data = st.session_state.products[st.session_state.current_product]
        
        # 단계 정보 불러오기
        if "phases" in product_data:
            st.session_state.phases = product_data["phases"].copy()
        
        # 제외일 정보 불러오기
        if "custom_excludes" in product_data:
            st.session_state.custom_excludes = product_data["custom_excludes"].copy()
        
        # 담당자 정보 불러오기
        if "team_members" in product_data:
            st.session_state.team_members = product_data["team_members"].copy()
        
        if "target_date" in product_data:
            target_date_default = product_data["target_date"]
        else:
            target_date_default = datetime.today().date()
    else:
        target_date_default = datetime.today().date()
else:
    target_date_default = datetime.today().date()

# 기본값 설정 (안전장치)
if 'target_date_default' not in locals():
    target_date_default = datetime.today().date()

# ✅ 설정 관리 섹션
st.markdown("## ⚙️ 설정 관리")
settings_expander = st.expander("설정 관리", expanded=False)

with settings_expander:
    col1, col2 = st.columns(2)
    
    with col1:
        st.markdown("### 👥 담당자 관리")
        
        # 기본 담당자 파일 자동 불러오기
        try:
            with open("Eqqualberry_PLM_members.json", "r", encoding="utf-8") as f:
                default_members_data = json.load(f)
                default_members = default_members_data.get("team_members", [])
                if default_members:
                    st.session_state.team_members = default_members
                    st.success(f"✅ 기본 담당자 목록을 불러왔습니다. ({len(default_members)}명)")
                else:
                    st.warning("기본 담당자 파일이 비어있습니다.")
        except FileNotFoundError:
            st.error("❌ 기본 담당자 파일을 찾을 수 없습니다.")
        except Exception as e:
            st.error(f"❌ 기본 담당자 파일 불러오기 실패: {e}")
        
        # 새 담당자 추가
        new_member = st.text_input("새 담당자 추가", key="new_member_input", 
                                  on_change=lambda: add_new_member())
        
        # 담당자 목록 표시 및 삭제
        if st.session_state.team_members:
            st.write("**현재 담당자 목록:**")
            for i, member in enumerate(st.session_state.team_members):
                col_a, col_b = st.columns([3, 1])
                with col_a:
                    st.write(f"• {member}")
                with col_b:
                    if st.button("🗑️", key=f"delete_member_{i}"):
                        st.session_state.team_members.remove(member)
                        st.rerun()
        else:
            st.info("등록된 담당자가 없습니다.")
    
    with col2:
        st.markdown("### 📅 제외일 설정")
        
        # 기본 제외일 파일 자동 불러오기
        try:
            with open("공휴일_2025_Second_exclude_settings.json", "r", encoding="utf-8") as f:
                default_exclude_data = json.load(f)
                default_exclude_dates = default_exclude_data.get("exclude_dates", [])
                if default_exclude_dates:
                    # ISO 형식의 날짜 문자열을 date 객체로 변환
                    exclude_dates = {datetime.fromisoformat(date_str).date() for date_str in default_exclude_dates}
                    st.session_state.custom_excludes.update(exclude_dates)
                    st.success(f"✅ 기본 제외일 설정을 불러왔습니다. ({len(exclude_dates)}개)")
                else:
                    st.warning("기본 제외일 파일이 비어있습니다.")
        except FileNotFoundError:
            st.error("❌ 기본 제외일 파일을 찾을 수 없습니다.")
        except Exception as e:
            st.error(f"❌ 기본 제외일 파일 불러오기 실패: {e}")
        
        # 제외일 추가
        exclude_date = st.date_input("제외할 날짜 선택", key="exclude_date_input")
        if st.button("➕ 제외일 추가", key="add_exclude_btn"):
            if exclude_date not in st.session_state.custom_excludes:
                st.session_state.custom_excludes.add(exclude_date)
                st.success(f"✅ {exclude_date.strftime('%Y-%m-%d')} 제외일로 추가되었습니다!")
                st.rerun()
            else:
                st.warning("이미 제외일로 설정된 날짜입니다.")
        
        # 제외일 목록 표시 및 삭제
        if st.session_state.custom_excludes:
            st.write("**현재 제외일 목록:**")
            for exclude_date in sorted(st.session_state.custom_excludes):
                col_c, col_d = st.columns([3, 1])
                with col_c:
                    st.write(f"• {exclude_date.strftime('%Y-%m-%d')}")
                with col_d:
                    if st.button("🗑️", key=f"delete_exclude_{exclude_date}"):
                        st.session_state.custom_excludes.remove(exclude_date)
                        st.rerun()
        else:
            st.info("등록된 제외일이 없습니다.")
        
        # 초기화 기능
        col_clear1, col_clear2 = st.columns(2)
        
        with col_clear1:
            if st.button("🗑️ 제외일 전체 초기화", key="clear_all_excludes_btn"):
                st.session_state.custom_excludes.clear()
                st.success("✅ 모든 제외일이 초기화되었습니다.")
        
        with col_clear2:
            if st.button("🗑️ 담당자 전체 초기화", key="clear_all_members_btn"):
                st.session_state.team_members.clear()
                st.success("✅ 모든 담당자가 초기화되었습니다.")

# ✅ 담당자 추가 함수
def add_new_member():
    if st.session_state.new_member_input and st.session_state.new_member_input not in st.session_state.team_members:
        st.session_state.team_members.append(st.session_state.new_member_input)
        st.session_state.new_member_input = ""
        st.rerun()

st.markdown("---")

# ✅ 리드타임 입력
st.subheader("📋 단계별 리드타임 / 담당자 / Asana Task 코드 입력")

# 담당자 연동 상태 표시
if "team_members" in st.session_state and st.session_state.team_members:
    st.info(f"✅ 담당자 관리와 연동됨 - {len(st.session_state.team_members)}명의 담당자 중 선택 가능")
else:
    st.warning("⚠️ 설정 관리에서 담당자를 먼저 등록해주세요")

# 담당자 드롭다운 옵션 생성
if "team_members" in st.session_state and st.session_state.team_members:
    member_options = [""] + st.session_state.team_members
else:
    member_options = [""]

# 데이터 타입 명시적 설정
if not st.session_state.phases.empty:
    st.session_state.phases["단계"] = st.session_state.phases["단계"].astype(str)
    st.session_state.phases["담당자"] = st.session_state.phases["담당자"].astype(str)
    
    # Asana Task 코드 컬럼 강제 생성
    if "Asana Task 코드" not in st.session_state.phases.columns:
        st.session_state.phases["Asana Task 코드"] = ""
    st.session_state.phases["Asana Task 코드"] = st.session_state.phases["Asana Task 코드"].astype(str)

# 데이터 에디터에 담당자 드롭다운 적용
edited_df = st.data_editor(
    st.session_state.phases,
    num_rows="dynamic",
    use_container_width=True,
    key="phases_editor",
    column_order=("단계", "리드타임", "담당자", "Asana Task 코드"),
    column_config={
        "단계": st.column_config.TextColumn(
            "단계",
            help="개발 단계명",
            max_chars=50,
            validate="^.+$"
        ),
        "리드타임": st.column_config.NumberColumn(
            "리드타임 (일)",
            min_value=1,
            max_value=365,
            help="작업 소요 일수"
        ),
        "담당자": st.column_config.SelectboxColumn(
            "담당자",
            options=member_options,
            required=False,
            help="설정 관리에서 등록한 담당자 중 선택하세요"
        ),
        "Asana Task 코드": st.column_config.TextColumn(
            "Asana Task 코드",
            help="Asana 작업 코드 (자동화용)",
            max_chars=50
        )
    }
)

# 데이터 에디터의 변경사항을 즉시 세션 상태에 반영
if edited_df is not None:
    st.session_state.phases = edited_df.copy()

# ✅ 목표일 입력
st.session_state.target_date = st.date_input("✅ 목표 완료일", value=st.session_state.target_date)

# ✅ 주말 제외일 자동 설정
def get_weekends_between(start: date, end: date) -> set:
    weekends = set()
    current = start
    while current <= end:
        if current.weekday() >= 5:
            weekends.add(current)
        current += timedelta(days=1)
    return weekends

earliest_possible_start = st.session_state.target_date - timedelta(days=300)
weekend_excludes = get_weekends_between(earliest_possible_start, st.session_state.target_date)

# ✅ 제품별 데이터 자동 저장
if st.session_state.current_product != "새 제품":
    st.session_state.products[st.session_state.current_product] = {
        "phases": st.session_state.phases,
        "custom_excludes": st.session_state.custom_excludes,
        "target_date": st.session_state.target_date,
        "team_members": st.session_state.team_members.copy() if st.session_state.team_members else []
    }
    
    # 저장 상태 표시
    saved_count = 0
    saved_details = []
    
    if not st.session_state.phases.empty:
        phase_count = len([phase for phase in st.session_state.phases["단계"] if phase])
        if phase_count > 0:
            saved_count += 1
            saved_details.append(f"단계 {phase_count}개")
    
    if st.session_state.custom_excludes:
        saved_count += 1
        saved_details.append(f"제외일 {len(st.session_state.custom_excludes)}개")
    
    if st.session_state.team_members:
        saved_count += 1
        saved_details.append(f"담당자 {len(st.session_state.team_members)}명")
    
    if st.session_state.target_date:
        saved_count += 1
        saved_details.append(f"목표일")
    
    if saved_count > 0:
        st.info(f"💾 **{st.session_state.current_product}** 제품 데이터가 자동 저장되었습니다. ({', '.join(saved_details)})")

st.markdown("---")

# ✅ 일정 계산
phases_data = st.session_state.phases.to_dict(orient="records")
excluded = weekend_excludes | st.session_state.custom_excludes
result_df = pd.DataFrame(backward_schedule(st.session_state.target_date, phases_data, excluded))



st.success("✅ 주요 단계별 시작/종료일 산출")
st.dataframe(result_df)

# ✅ 다운로드
csv = result_df.to_csv(index=False).encode("utf-8-sig")
if st.session_state.current_product != "새 제품":
    filename = f"{st.session_state.current_product}_개발일정표.csv"
else:
    filename = "개발일정표.csv"
st.download_button("📥 엑셀 다운로드", data=csv, file_name=filename, mime="text/csv")

st.markdown("---")

# ✅ 시각화
st.subheader("📊 시각화 옵션")
visualization_option = st.selectbox(
    "시각화 방식 선택",
    ["타임라인 뷰", "진행 카드 뷰", "캘린더 그리드 뷰", "칸반 보드 뷰"],
    index=0
)

if visualization_option == "타임라인 뷰":
    show_timeline_view(result_df)
elif visualization_option == "진행 카드 뷰":
    show_progress_cards(result_df)
elif visualization_option == "캘린더 그리드 뷰":
    show_calendar_grid(result_df, excluded)
elif visualization_option == "칸반 보드 뷰":
    show_kanban_board(result_df)

# ✅ 제품 데이터 관리
st.markdown("---")
st.subheader("💾 제품 데이터 관리")
product_data_expander = st.expander("제품 데이터 저장/불러오기", expanded=False)

with product_data_expander:
    col_save, col_load = st.columns(2)
    
    with col_save:
        st.markdown("### 💾 제품 데이터 저장")
        save_filename = st.text_input("저장할 파일명 (확장자 제외)", 
                                    value=f"{st.session_state.current_product}_product_data" if st.session_state.current_product != "새 제품" else "product_data",
                                    key="save_filename_input")
        
        if st.button("💾 제품 데이터 저장", key="save_product_data_btn"):
            product_data = {
                "phases": st.session_state.phases,
                "custom_excludes": st.session_state.custom_excludes,
                "target_date": st.session_state.target_date,
                "team_members": st.session_state.team_members
            }
            
            if save_product_data(st.session_state.current_product, product_data, f"{save_filename}.json"):
                st.success(f"✅ **{st.session_state.current_product}** 제품 데이터가 저장되었습니다!")
    
    with col_load:
        st.markdown("### 📂 제품 데이터 불러오기")
        # 저장된 제품 파일 목록
        try:
            # productPLM 폴더에서 검색
            folder_path = "productPLM"
            if os.path.exists(folder_path):
                product_files = [f for f in os.listdir(folder_path) if f.endswith('_product_data.json')]
                if product_files:
                    selected_file = st.selectbox("저장된 제품 파일 선택", ["선택하세요"] + product_files, key="load_product_select")
                    
                    if st.button("📂 제품 데이터 불러오기", key="load_product_data_btn") and selected_file != "선택하세요":
                        loaded_data = load_product_data(selected_file)
                        if loaded_data:
                            st.session_state.phases = loaded_data["phases"]
                            st.session_state.custom_excludes = loaded_data["custom_excludes"]
                            if loaded_data["target_date"]:
                                st.session_state.target_date = loaded_data["target_date"]
                            if loaded_data["team_members"]:
                                st.session_state.team_members = loaded_data["team_members"]
                            st.success(f"✅ **{selected_file}** 제품 데이터를 불러왔습니다!")
                            st.rerun()
                    
                    # 파일 삭제 기능
                    if st.button("🗑️ 선택된 파일 삭제", key="delete_product_file_btn") and selected_file != "선택하세요":
                        try:
                            file_path = os.path.join(folder_path, selected_file)
                            os.remove(file_path)
                            st.success(f"✅ **{selected_file}** 파일이 삭제되었습니다!")
                            st.rerun()
                        except Exception as e:
                            st.error(f"❌ 파일 삭제 중 오류 발생: {e}")
                else:
                    st.info("저장된 제품 데이터 파일이 없습니다.")
            else:
                st.info("productPLM 폴더가 존재하지 않습니다.")
        except Exception as e:
            st.error(f"파일 목록 조회 중 오류 발생: {e}")
