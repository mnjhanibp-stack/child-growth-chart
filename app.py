import pandas as pd
import numpy as np
import streamlit as st
import matplotlib.pyplot as plt
from math import erf, sqrt, log

st.set_page_config(page_title="성장 백분위 그래프", layout="wide")

EXCEL_PATH = "엑셀.xlsx"
HEIGHT_SHEET = "연령별 신장"
BIRTH_WEIGHT_SHEET = "출생시 체중 백분위"

def norm_cdf(z: float) -> float:
    # Standard normal CDF via erf (no scipy dependency)
    return 0.5 * (1.0 + erf(z / sqrt(2.0)))

def lms_z(x: float, L: float, M: float, S: float) -> float:
    if abs(L) < 1e-12:
        return log(x / M) / S
    return ((x / M) ** L - 1.0) / (L * S)

@st.cache_data
def load_tables():
    xl = pd.ExcelFile(EXCEL_PATH)

    h = xl.parse(HEIGHT_SHEET)
    h = h[h["성별"].notna()].copy()
    h = h[["성별", "만나이(개월)", "L", "M", "S"]].dropna()
    h["성별"] = h["성별"].astype(int)
    h["만나이(개월)"] = h["만나이(개월)"].astype(int)
    for c in ["L","M","S"]:
        h[c] = pd.to_numeric(h[c], errors="coerce")
    h = h.dropna()

    bw = xl.parse(BIRTH_WEIGHT_SHEET)
    bw = bw[bw["성별"].notna()].copy()
    bw = bw[["성별", "만나이(개월)", "L", "M", "S"]].dropna()
    bw["성별"] = bw["성별"].astype(int)
    bw["만나이(개월)"] = bw["만나이(개월)"].astype(int)
    for c in ["L","M","S"]:
        bw[c] = pd.to_numeric(bw[c], errors="coerce")
    bw = bw.dropna()

    return h, bw

def get_lms_interpolated(df: pd.DataFrame, sex: int, months: float):
    """Linear interpolation of L/M/S across months for a given sex."""
    sub = df[df["성별"] == sex].sort_values("만나이(개월)")
    m_min, m_max = int(sub["만나이(개월)"].min()), int(sub["만나이(개월)"].max())
    months_clamped = min(max(months, m_min), m_max)

    m0 = int(np.floor(months_clamped))
    m1 = int(np.ceil(months_clamped))
    if m0 == m1:
        row = sub[sub["만나이(개월)"] == m0].iloc[0]
        return float(row["L"]), float(row["M"]), float(row["S"]), months_clamped

    r0 = sub[sub["만나이(개월)"] == m0].iloc[0]
    r1 = sub[sub["만나이(개월)"] == m1].iloc[0]
    t = (months_clamped - m0) / (m1 - m0)

    L = float(r0["L"]) + t * (float(r1["L"]) - float(r0["L"]))
    M = float(r0["M"]) + t * (float(r1["M"]) - float(r0["M"]))
    S = float(r0["S"]) + t * (float(r1["S"]) - float(r0["S"]))
    return L, M, S, months_clamped

def percentile_from_value(df: pd.DataFrame, sex: int, months: float, value: float) -> float:
    L, M, S, _ = get_lms_interpolated(df, sex, months)
    z = lms_z(value, L, M, S)
    return norm_cdf(z) * 100.0

def months_between(birth_date, measure_date) -> int:
    # "완료된 개월 수" 기준: DATEDIF(...,"m")과 동일한 방식
    y = measure_date.year - birth_date.year
    m = measure_date.month - birth_date.month
    total = y * 12 + m
    if measure_date.day < birth_date.day:
        total -= 1
    return max(total, 0)

def ym_label(total_months: int) -> str:
    return f"{total_months//12}년 {total_months%12}개월"

st.title("키 백분위 그래프 (엑셀 기준 데이터 기반)")
st.caption("※ 이 앱은 업로드된 엑셀 파일(연령별 신장 / 출생시 체중 백분위)의 LMS를 기준으로 계산합니다.")

height_df, bw_df = load_tables()

col1, col2, col3 = st.columns([1.2, 1.2, 1.6], gap="large")

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
    end_age_years = st.selectbox("그래프 종료 나이", [16, 17, 18], index=0)
    end_month = int(end_age_years * 12)

    tick_step = st.selectbox("가로축 눈금 간격", ["12개월(1년)", "6개월"], index=0)
    tick_every = 12 if tick_step.startswith("12") else 6

    st.caption("추가 커스터마이징(선 색/두께/문구)은 완성본 확인 후 조절해드릴게요.")

with col3:
    st.subheader("결과 요약")

    if (birth_date is None) or (measure_date is None):
        st.info("생년월일과 측정일을 입력하면 자동으로 만나이(개월) 계산 및 그래프가 생성됩니다.")
        st.stop()

    age_months = months_between(birth_date, measure_date)

    # Birth weight percentile (at 0 months in provided sheet)
    bw_pct = percentile_from_value(bw_df, sex, 0, float(birth_weight))

    # Height percentile at current age
    cur_pct = percentile_from_value(height_df, sex, age_months, float(current_height))

    # Start percentile mapping rule (currently identity)
    start_pct = bw_pct

    # Parent-based adult upper/lower height rules (as discussed)
    if sex == 1:  # boy
        upper_adult_h = mother_h + 13.0
        lower_adult_h = father_h - 13.0
    else:  # girl
        upper_adult_h = father_h - 13.0
        lower_adult_h = mother_h + 13.0

    upper_end_pct = percentile_from_value(height_df, sex, end_month, float(upper_adult_h))
    lower_end_pct = percentile_from_value(height_df, sex, end_month, float(lower_adult_h))

    st.write(f"- 자동 계산된 만나이: **{ym_label(age_months)}** (총 {age_months}개월)")
    st.write(f"- 출생체중 백분위(엑셀 기준): **{bw_pct:.1f}백분위** → (그래프 시작 백분위로 사용)")
    st.write(f"- 현재 키 백분위(엑셀 기준): **{cur_pct:.1f}백분위**")
    st.write(f"- 16세 기준 부모키 밴드(규칙 적용): 하한 키 **{lower_adult_h:.1f}cm**, 상한 키 **{upper_adult_h:.1f}cm**")
    st.write(f"  - 하한(16세) 백분위: **{lower_end_pct:.1f}백분위**, 상한(16세) 백분위: **{upper_end_pct:.1f}백분위**")

    st.divider()

    st.subheader("그래프")
    months = np.arange(0, end_month + 1)

    # Child percentile path: linear from start->current, then hold constant
    child_pct = np.empty_like(months, dtype=float)
    if age_months <= 0:
        child_pct[:] = start_pct
    else:
        for i, m in enumerate(months):
            if m <= age_months:
                t = m / age_months
                child_pct[i] = (1 - t) * start_pct + t * cur_pct
            else:
                child_pct[i] = cur_pct

    # Upper/lower bands: linear from start percentile to end percentile
    upper_pct = start_pct + (upper_end_pct - start_pct) * (months / end_month)
    lower_pct = start_pct + (lower_end_pct - start_pct) * (months / end_month)

    # Plot
    fig, ax = plt.subplots(figsize=(11, 5))
    ax.plot(months, upper_pct, linewidth=2, label="상한(빨간선)")
    ax.plot(months, lower_pct, linewidth=2, label="하한(파란선)")
    ax.plot(months, child_pct, linewidth=2, label="아이 경로")

    ax.set_ylim(0, 100)
    ax.set_xlim(0, end_month)
    ax.set_ylabel("키 백분위(%)")
    ax.set_xlabel("나이")

    ticks = np.arange(0, end_month + 1, tick_every)
    ax.set_xticks(ticks)
    ax.set_xticklabels([ym_label(int(t)) for t in ticks], rotation=0)
    ax.grid(True, linestyle="--", linewidth=0.7, alpha=0.5)
    ax.legend(loc="upper left")

    st.pyplot(fig, clear_figure=True)

    st.caption("가로축 표기는 내부 '개월'을 '년/개월'로 변환해 표시합니다. (예: 87개월 → 7년 3개월)")
