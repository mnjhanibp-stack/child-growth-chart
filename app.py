import pandas as pd
import numpy as np
import streamlit as st
import matplotlib.pyplot as plt
from math import erf, sqrt, log

# =========================
# 설정
# =========================
st.set_page_config(page_title="키 백분위 성장 그래프", layout="wide")

EXCEL_PATH = "엑셀.xlsx"
HEIGHT_SHEET = "연령별 신장"
BIRTH_WEIGHT_SHEET = "출생시 체중 백분위"

END_AGE_YEARS = 18
END_MONTH = END_AGE_YEARS * 12


# =========================
# 수학/통계 유틸
# =========================
def norm_cdf(z: float) -> float:
    # 표준정규 CDF (scipy 없이 erf로 구현)
    return 0.5 * (1.0 + erf(z / sqrt(2.0)))


def lms_z(x: float, L: float, M: float, S: float) -> float:
    # LMS 기반 z-score
    if abs(L) < 1e-12:
        return log(x / M) / S
    return ((x / M) ** L - 1.0) / (L * S)


def ym_label(total_months: int) -> str:
    return f"{total_months//12}년 {total_months%12}개월"


def months_between(birth_date, measure_date) -> int:
    """
    '완료된 개월 수' 기준 (엑셀 DATEDIF(birth, measure, "m")와 동일한 방식)
    """
    y = measure_date.year - birth_date.year
    m = measure_date.month - birth_date.month
    total = y * 12 + m
    if measure_date.day < birth_date.day:
        total -= 1
    return max(total, 0)


# =========================
# 데이터 로딩/조회
# =========================
@st.cache_data
def load_tables():
    xl = pd.ExcelFile(EXCEL_PATH)

    height = xl.parse(HEIGHT_SHEET)
    height = height[height["성별"].notna()].copy()
    height = height[["성별", "만나이(개월)", "L", "M", "S"]].dropna()
    height["성별"] = height["성별"].astype(int)
    height["만나이(개월)"] = height["만나이(개월)"].astype(int)
    for c in ["L", "M", "S"]:
        height[c] = pd.to_numeric(height[c], errors="coerce")
    height = height.dropna()

    bw = xl.parse(BIRTH_WEIGHT_SHEET)
    bw = bw[bw["성별"].notna()].copy()
    bw = bw[["성별", "만나이(개월)", "L", "M", "S"]].dropna()
    bw["성별"] = bw["성별"].astype(int)
    bw["만나이(개월)"] = bw["만나이(개월)"].astype(int)
    for c in ["L", "M", "S"]:
        bw[c] = pd.to_numeric(bw[c], errors="coerce")
    bw = bw.dropna()

    return height, bw


def get_lms_interpolated(df: pd.DataFrame, sex: int, months: float):
    """
    df에서 성별/개월에 해당하는 LMS를 선형보간으로 반환
    """
    sub = df[df["성별"] == sex].sort_values("만나이(개월)")
    m_min = int(sub["만나이(개월)"].min())
    m_max = int(sub["만나이(개월)"].max())

    months = float(np.clip(months, m_min, m_max))
    m0 = int(np.floor(months))
    m1 = int(np.ceil(months))

    if m0 == m1:
        r = sub[sub["만나이(개월)"] == m0].iloc[0]
        return float(r["L"]), float(r["M"]), float(r["S"]), months

    r0 = sub[sub["만나이(개월)"] == m0].iloc[0]
    r1 = sub[sub["만나이(개월)"] == m1].iloc[0]
    t = (months - m0) / (m1 - m0)

    L = float(r0["L"]) + t * (float(r1["L"]) - float(r0["L"]))
    M = float(r0["M"]) + t * (float(r1["M"]) - float(r0["M"]))
    S = float(r0["S"]) + t * (float(r1["S"]) - float(r0["S"]))
    return L, M, S, months


def percentile_from_value(df: pd.DataFrame, sex: int, months: float, value: float) -> float:
    L, M, S, _ = get_lms_interpolated(df, sex, months)
    z = lms_z(value, L, M, S)
    return norm_cdf(z) * 100.0


# =========================
# UI
# =========================
st.title("키 백분위 성장 그래프 (엑셀 기준 데이터)")
st.caption("※ 기준 데이터는 업로드된 엑셀(연령별 신장 / 출생시 체중 백분위)의 LMS를 그대로 사용합니다.")

height_df, bw_df = load_tables()

col1, col2, col3 = st.columns([1.2, 1.2, 1.8], gap="large")

with col1:
    st.subheader("입력")
    sex_txt = st.radio("성별", ["남", "여"], horizontal=True)
    sex = 1 if sex_txt == "남" else 2

    birth_weight = st.number_input("출생체중 (kg)", min_value=0.5, max_value=8.0, value=3.20, step=0.01, format="%.2f")
    birth_date = st.date_input("생년월일", value=None)
    measure_date = st.date_input("측정일", value=None)

    current_height = st.number_input("현재 키 (cm)", min_value=30.0, max_value=220.0, value=100.0, step=0.1, format="%.1f")

with col2:
    st.subheader("부모 키")
    father_h = st.number_input("아빠 키 (cm)", min_value=120.0, max_value=220.0, value=170.0, step=0.1, format="%.1f")
    mother_h = st.number_input("엄마 키 (cm)", min_value=120.0, max_value=220.0, value=160.0, step=0.1, format="%.1f")

    st.subheader("설정")
    tick_step = st.selectbox("가로축 눈금 간격", ["12개월(1년)", "6개월"], index=0)
    tick_every = 12 if tick_step.startswith("12") else 6

    st.caption("원하는 형태(선 굵기/라벨 위치/예측 방식)는 완성본 보고 계속 조절 가능합니다.")

with col3:
    st.subheader("결과 요약")

    if (birth_date is None) or (measure_date is None):
        st.info("생년월일과 측정일을 입력하면 자동으로 만나이(개월) 계산 및 그래프가 생성됩니다.")
        st.stop()

    age_months = months_between(birth_date, measure_date)
    age_months = min(age_months, END_MONTH)

    # 출생체중 백분위(0개월 기준)
    bw_pct = percentile_from_value(bw_df, sex, 0, float(birth_weight))

    # 현재 키 백분위(현재 월령 기준)
    cur_pct = percentile_from_value(height_df, sex, age_months, float(current_height))

    # 그래프 시작 백분위: 출생체중 백분위 그대로 사용(원하면 나중에 매핑 규칙 추가 가능)
    start_pct = bw_pct

    # =========================
    # ✅ 부모키 밴드 규칙 (원장님 규칙 반영)
    # - 성별에 상/하한을 고정하지 않음
    # - "두 후보 키"를 만든 뒤, 큰 값=빨간선, 작은 값=파란선
    # =========================
    if sex == 1:  # 남아: 후보 = (아빠 그대로) vs (엄마+13)
        cand1 = float(father_h)
        cand2 = float(mother_h) + 13.0
    else:         # 여아: 후보 = (엄마 그대로) vs (아빠-13)
        cand1 = float(mother_h)
        cand2 = float(father_h) - 13.0

    upper_adult_h = max(cand1, cand2)  # 빨간선 끝(키 cm)
    lower_adult_h = min(cand1, cand2)  # 파란선 끝(키 cm)

    # ✅ 만 18세(END_MONTH)에서의 백분위로 변환
    upper_end_pct = percentile_from_value(height_df, sex, END_MONTH, upper_adult_h)
    lower_end_pct = percentile_from_value(height_df, sex, END_MONTH, lower_adult_h)

    st.write(f"- 자동 계산된 만나이: **{ym_label(age_months)}** (총 {age_months}개월)")
    st.write(f"- 출생체중 백분위(엑셀 기준): **{bw_pct:.1f}백분위** → (그래프 시작 백분위로 사용)")
    st.write(f"- 현재 키 백분위(엑셀 기준): **{cur_pct:.1f}백분위**")
    st.write(f"- 18세 밴드 후보 키: **{cand1:.1f}cm** / **{cand2:.1f}cm**")
    st.write(f"  - 파란선(하한): **{lower_adult_h:.1f}cm → {lower_end_pct:.1f}백분위**")
    st.write(f"  - 빨간선(상한): **{upper_adult_h:.1f}cm → {upper_end_pct:.1f}백분위**")

    st.divider()
    st.subheader("그래프")

    # x축: 0~18세(개월)
    months = np.arange(0, END_MONTH + 1)

    # =========================
    # ✅ 초록선(아이 경로): 현재까지 '만' 표시
    # 출생(start_pct) -> 현재(cur_pct) 직선 보간
    # =========================
    if age_months <= 0:
        child_months = np.array([0])
        child_pct = np.array([start_pct], dtype=float)
    else:
        child_months = np.arange(0, age_months + 1)
        t = child_months / age_months
        child_pct = (1 - t) * start_pct + t * cur_pct

    # =========================
    # ✅ 밴드: 시작 백분위 -> 18세 끝 백분위 직선
    # =========================
    upper_pct = start_pct + (upper_end_pct - start_pct) * (months / END_MONTH)
    lower_pct = start_pct + (lower_end_pct - start_pct) * (months / END_MONTH)

    # =========================
    # Plot
    # =========================
    fig, ax = plt.subplots(figsize=(11, 5))

    # 밴드
    ax.plot(months, upper_pct, linewidth=2, label="상한(빨간선)")
    ax.plot(months, lower_pct, linewidth=2, label="하한(파란선)")

    # 아이 경로(현재까지)
    ax.plot(child_months, child_pct, linewidth=2, label="아이 경로(현재까지)")

    # 현재 지점 별표(★)
    ax.scatter([age_months], [cur_pct], marker="*", s=220, zorder=5, label="현재 지점")

    # 18세 밴드 끝점 마커 + 라벨(키/백분위)
    ax.scatter([END_MONTH], [upper_end_pct], s=70, zorder=5)
    ax.scatter([END_MONTH], [lower_end_pct], s=70, zorder=5)
    ax.text(END_MONTH, upper_end_pct, f"  {upper_adult_h:.0f}cm / {upper_end_pct:.1f}%", va="center")
    ax.text(END_MONTH, lower_end_pct, f"  {lower_adult_h:.0f}cm / {lower_end_pct:.1f}%", va="center")

    # 축/눈금
    ax.set_ylim(0, 100)
    ax.set_xlim(0, END_MONTH)
    ax.set_ylabel("키 백분위(%)")
    ax.set_xlabel("나이")

    ticks = np.arange(0, END_MONTH + 1, tick_every)
    ax.set_xticks(ticks)
    ax.set_xticklabels([ym_label(int(t)) for t in ticks], rotation=0)

    ax.grid(True, linestyle="--", linewidth=0.7, alpha=0.5)
    ax.legend(loc="upper left")

    st.pyplot(fig, clear_figure=True)
    st.caption("가로축 표기는 내부 '개월'을 '년/개월'로 변환해 표시합니다.")
