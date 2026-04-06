import streamlit as st
import anthropic
import smtplib
import re
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from datetime import datetime, timedelta
import streamlit.components.v1 as components

# ── 기본 수신자 목록 ────────────────────────────────────
DEFAULT_RECIPIENTS = [
    "eunice@nextronkorea.com",
    "jack@nextronkorea.com",
    "jacob@nextronkorea.com",
    "josh@nextronkorea.com",
    "may@nextronkorea.com",
    "samyu@nextronkorea.com",
]
HIGHLIGHT_COMPANIES = ["CHAEVI", "EVAR", "EVSIS", "EVMODE", "KEFICO", "SKSIGNET", "TEXON"]

# ── 날짜 계산 ──────────────────────────────────────────
def get_dates():
    today = datetime.now()
    week_ago = today - timedelta(days=7)
    return today, week_ago

# ── 뉴스레터 생성 ──────────────────────────────────────
def generate_newsletter(api_key: str) -> str:
    today, week_ago = get_dates()
    today_str  = today.strftime("%Y.%m.%d")
    w_ago_str  = week_ago.strftime("%Y.%m.%d")
    today_kor  = today.strftime("%Y년 %m월 %d일")
    w_ago_kor  = week_ago.strftime("%Y년 %m월 %d일")

    system = f"""오늘 날짜: {today_kor} ({today.strftime('%Y-%m-%d')})
수집 허용 기간: {w_ago_kor} ({week_ago.strftime('%Y-%m-%d')}) ~ {today_kor} ({today.strftime('%Y-%m-%d')})

══════════════════════════════════════
⛔ 날짜 필터 — 가장 중요한 규칙
══════════════════════════════════════
- 반드시 각 기사의 발행일을 확인할 것
- {week_ago.strftime('%Y-%m-%d')} 이전에 발행된 기사는 단 1건도 포함 금지
- 발행일이 명시되지 않은 기사 포함 금지
- 날짜 확인 불가능한 기사 포함 금지
- 웹 검색 시 반드시 "after:{week_ago.strftime('%Y-%m-%d')}" 조건으로 검색할 것
- 기사를 목록에 추가하기 전 반드시 발행일을 재확인할 것
══════════════════════════════════════

【역할】
Nextron Korea 주간 EV 뉴스레터 생성 AI

【검색 방법】
각 주제를 검색할 때 반드시 최근 7일 필터 적용:
- "전기차 뉴스 {today.strftime('%Y년 %m월')}" 형태로 검색
- "EV news after:{week_ago.strftime('%Y-%m-%d')}" 형태로 검색
- 검색 결과에서 날짜 확인 후 {week_ago.strftime('%Y-%m-%d')} 이전 기사 즉시 제거

【검색 주제】
1. 전기차(EV) 시장동향, 신차출시, 판매실적
2. 전기차 충전케이블 / EV charging cable, 충전인프라, 충전표준(CCS/NACS/CHAdeMO/GB-T)
3. 휴머노이드 로봇 (humanoid)
4. 전기차·충전 관련 정책·규제 (한국 및 글로벌)

【하이라이트 기업 — 언급 시 <strong>볼드</strong>】
CHAEVI, EVAR, EVSIS, EVMODE, KEFICO, SKSIGNET, TEXON

【출력 형식】
Outlook 최적화 HTML 이메일.
- 테이블 기반 레이아웃 (flexbox·grid 금지)
- 모든 스타일 인라인 CSS
- 폰트: 14px 'Apple SD Gothic Neo', Malgun Gothic, Arial, sans-serif
- 최대폭 680px 중앙 정렬

【섹션 구조】
① 헤더: "⚡ 전기차 & 충전케이블 주간뉴스 다이제스트" | {w_ago_str}~{today_str} | Nextron Korea 내부용
   (헤더 배경 #0d1117, 텍스트 흰색)
② 주간 핵심요약: 3~5개 핵심 뉴스 불릿
③ 주간 핵심시그널 테이블: 시그널 | 내용 | 영향도(🔴고/🟡중/🟢저)
④ 기업 하이라이트: CHAEVI·EVAR 등 언급 기사 별도 정리 (없으면 섹션 생략)
⑤ 카테고리별 뉴스:
   ⚡ 전기차 시장동향 / 🔌 충전 인프라 & 케이블 / 📋 정책 & 규제 / 🔬 기술 & 혁신 / 🤖 휴머노이드
   각 기사: 제목(원문 링크) | 출처 | 발행날짜(YYYY-MM-DD) | 2~3문장 한국어 요약
   ※ 발행날짜가 {week_ago.strftime('%Y-%m-%d')} 이전이면 절대 포함하지 말 것
⑥ 푸터: © {today.year} Nextron Korea | Claude AI 자동 생성 | {w_ago_str}~{today_str}

<!DOCTYPE html> 로 시작하는 완전한 HTML 문서만 출력. 마크다운 코드펜스(```) 절대 금지."""

    client = anthropic.Anthropic(api_key=api_key)
    response = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=8000,
        system=system,
        tools=[{"type": "web_search_20250305", "name": "web_search"}],
        messages=[{
            "role": "user",
            "content": (
                f"오늘은 {today.strftime('%Y-%m-%d')}입니다. "
                f"반드시 {week_ago.strftime('%Y-%m-%d')} ~ {today.strftime('%Y-%m-%d')} 사이 발행된 기사만 포함해서 "
                f"전기차·EV·충전케이블·휴머노이드 주간 뉴스레터 HTML을 생성해주세요. "
                f"{week_ago.strftime('%Y-%m-%d')} 이전 기사는 절대 포함 금지."
            )
        }]
    )

    raw = "".join(b.text for b in response.content if b.type == "text")
    raw = re.sub(r"```html\s*", "", raw)
    raw = re.sub(r"```\s*", "", raw).strip()
    idx = raw.find("<!DOCTYPE")
    if idx == -1:
        idx = raw.find("<html")
    return raw[max(idx, 0):]

# ── Gmail 발송 ─────────────────────────────────────────
def send_email(html: str, gmail_address: str, app_password: str, recipients: list):
    today, week_ago = get_dates()
    subject = (
        f"⚡ 전기차 & 충전케이블 주간뉴스 다이제스트 "
        f"[{week_ago.strftime('%m.%d')}~{today.strftime('%m.%d')}]"
    )
    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"]    = gmail_address
    msg["To"]      = ", ".join(recipients)
    msg.attach(MIMEText(html, "html", "utf-8"))

    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
        server.login(gmail_address, app_password)
        server.sendmail(gmail_address, recipients, msg.as_string())

# ── Streamlit UI ───────────────────────────────────────
def main():
    st.set_page_config(
        page_title="⚡ EV 뉴스레터 자동 발행",
        page_icon="⚡",
        layout="wide",
    )

    # 세션 초기화
    if "recipients" not in st.session_state:
        st.session_state.recipients = DEFAULT_RECIPIENTS.copy()

    # ── 사이드바 ──
    with st.sidebar:
        st.markdown("### ⚙️ API 설정")

        try:
            api_key = st.secrets["ANTHROPIC_API_KEY"]
            st.success("✅ Anthropic API Key 연결됨")
        except Exception:
            api_key = st.text_input("Anthropic API Key", type="password",
                                    placeholder="sk-ant-api03-...")

        st.markdown("---")

        try:
            gmail_address  = st.secrets["GMAIL_ADDRESS"]
            gmail_password = st.secrets["GMAIL_APP_PASSWORD"]
            st.success("✅ Gmail 연결됨")
        except Exception:
            gmail_address  = st.text_input("Gmail 주소", placeholder="your@gmail.com")
            gmail_password = st.text_input("Gmail 앱 비밀번호", type="password",
                                           placeholder="xxxx xxxx xxxx xxxx")

        st.markdown("---")

        # ── 수신자 관리 ──
        st.markdown("### 📬 수신자 관리")

        # 수신자 추가
        with st.expander("➕ 수신자 추가"):
            new_email = st.text_input("이메일 주소 입력",
                                      placeholder="name@example.com",
                                      key="new_email_input",
                                      label_visibility="collapsed")
            if st.button("추가하기", use_container_width=True):
                new_email = new_email.strip()
                if new_email and "@" in new_email and "." in new_email:
                    if new_email not in st.session_state.recipients:
                        st.session_state.recipients.append(new_email)
                        st.rerun()
                    else:
                        st.warning("이미 등록된 이메일입니다.")
                else:
                    st.error("올바른 이메일 형식을 입력해주세요.")

        # 수신자 선택 체크박스
        st.caption("✉️ 발송할 수신자 선택:")
        selected_recipients = []
        for r in st.session_state.recipients:
            col_chk, col_del = st.columns([6, 1])
            with col_chk:
                if st.checkbox(r, value=True, key=f"chk_{r}"):
                    selected_recipients.append(r)
            with col_del:
                if st.button("✕", key=f"del_{r}", help="삭제"):
                    st.session_state.recipients.remove(r)
                    st.rerun()

        if selected_recipients:
            st.caption(f"선택: {len(selected_recipients)}명 / 전체: {len(st.session_state.recipients)}명")
        else:
            st.warning("수신자를 1명 이상 선택해주세요.")

        st.markdown("---")
        st.markdown("### 🏢 하이라이트 기업")
        st.caption("  ·  ".join(HIGHLIGHT_COMPANIES))

        today, week_ago = get_dates()
        st.markdown("---")
        st.markdown("### 📅 검색 기간")
        st.caption(f"{week_ago.strftime('%Y.%m.%d')} ~ {today.strftime('%Y.%m.%d')}")
        st.caption("*(오늘 기준 자동 계산)*")

    # ── 메인 헤더 ──
    st.title("⚡ EV 뉴스레터 자동 발행")
    st.caption("전기차 & 충전케이블 주간뉴스 다이제스트  ·  Nextron Korea 내부용")
    st.divider()

    # ── 버튼 영역 ──
    today, week_ago = get_dates()
    col1, col2, col3 = st.columns(3)

    with col1:
        gen_btn = st.button("🔍 뉴스 수집 & 리포트 생성",
                            use_container_width=True, type="primary")
    with col2:
        send_btn = st.button("📧 이메일 발송",
                             use_container_width=True,
                             disabled="html_content" not in st.session_state)
    with col3:
        if "html_content" in st.session_state:
            st.download_button(
                "💾 HTML 다운로드",
                data=st.session_state.html_content,
                file_name=f"ev_newsletter_{today.strftime('%Y%m%d')}.html",
                mime="text/html",
                use_container_width=True,
            )

    # ── 뉴스레터 생성 ──
    if gen_btn:
        if not api_key:
            st.error("❌ 사이드바에서 Anthropic API Key를 입력해주세요.")
        else:
            with st.status("🔍 최신 뉴스 수집 & 리포트 생성 중...", expanded=True) as status:
                try:
                    st.write("🌐 웹에서 최신 뉴스 검색 중...")
                    html = generate_newsletter(api_key)
                    st.write("✍️ HTML 리포트 생성 완료")
                    st.session_state.html_content = html
                    status.update(label="✅ 뉴스레터 생성 완료!", state="complete")
                    st.rerun()
                except Exception as e:
                    status.update(label="❌ 오류 발생", state="error")
                    st.error(f"오류: {e}")

    # ── 이메일 발송 ──
    if send_btn:
        if not gmail_address or not gmail_password:
            st.error("❌ 사이드바에서 Gmail 주소와 앱 비밀번호를 입력해주세요.")
        elif not selected_recipients:
            st.warning("⚠️ 사이드바에서 수신자를 1명 이상 선택해주세요.")
        elif "html_content" not in st.session_state:
            st.warning("⚠️ 먼저 뉴스레터를 생성해주세요.")
        else:
            with st.spinner(f"📧 {len(selected_recipients)}명에게 발송 중..."):
                try:
                    send_email(st.session_state.html_content,
                               gmail_address, gmail_password,
                               selected_recipients)
                    names = ", ".join(r.split("@")[0] for r in selected_recipients)
                    st.success(f"✅ 발송 완료! {len(selected_recipients)}명 ({names})")
                    st.balloons()
                except Exception as e:
                    st.error(f"❌ 발송 실패: {e}")
                    st.info("💡 Gmail 앱 비밀번호를 확인해주세요. 일반 비밀번호가 아닌 앱 전용 비밀번호가 필요합니다.")

    # ── 미리보기 ──
    if "html_content" in st.session_state:
        st.divider()
        st.subheader("📄 뉴스레터 미리보기")
        components.html(st.session_state.html_content, height=700, scrolling=True)

if __name__ == "__main__":
    main()
