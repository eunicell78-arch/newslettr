import streamlit as st
import anthropic
import smtplib
import re
import json
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from datetime import datetime, timedelta, timezone
import streamlit.components.v1 as components

from date_utils import extract_publish_date, is_within_cutoff

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

def _build_region_config(region: str, today: datetime, cutoff: str):
    """Return (region_label, search_topics, search_hints, translation_note)."""
    _TRANSLATION_NOTE = """══════════════════════════════════════
⚠️ 해외 기사 번역 규칙 (필수)
══════════════════════════════════════
- 모든 기사 요약(2~3문장)은 반드시 한국어로 작성할 것
- 원문이 영어·중국어·기타 언어여도 한국어로 번역하여 요약
- 기사 제목도 한국어 번역 제공 (원문 제목은 하이퍼링크에 유지)
- 전문 용어는 원어 병기 허용 (예: CCS(Combined Charging System))
- 주간 핵심요약·핵심시그널 테이블도 모두 한국어로 작성
══════════════════════════════════════
"""

    if region == "domestic":
        region_label = "국내(한국)"
        search_topics = """【검색 주제 — 국내(한국) 중심】
1. 국내 전기차(EV) 시장동향, 신차출시, 판매실적 (한국 완성차, 현대/기아 등)
2. 국내 전기차 충전케이블·충전인프라, 충전표준(CCS/NACS/CHAdeMO/GB-T)
3. 국내 휴머노이드 로봇 (한국 기업·연구기관)
4. 국내 전기차·충전 관련 정책·규제 (환경부, 산업부, 국토부 등)"""
        search_hints = f"""- "전기차 뉴스 {today.strftime('%Y년 %m월')}" 형태로 검색
- "한국 EV 충전 after:{cutoff}" 형태로 검색
- "국내 전기차 정책 after:{cutoff}" 형태로 검색
- 국내 주요 매체(전자신문, 연합뉴스, 헤럴드경제 등) 포함"""
        translation_note = ""

    elif region == "international":
        region_label = "해외(국제)"
        search_topics = """【검색 주제 — 해외(국제) 중심】
1. Global EV market trends, new models, sales performance (US, Europe, China)
2. EV charging cable / charging infrastructure, charging standards (CCS/NACS/CHAdeMO/GB-T) globally
3. Humanoid robots global (Tesla Optimus, Figure, Boston Dynamics, Agility, Unitree, etc.)
4. EV and charging policy & regulations (US, EU, China, global)"""
        search_hints = f"""- "EV news after:{cutoff}" 형태로 검색
- "electric vehicle market {today.strftime('%B %Y')}" 형태로 검색
- "EV charging infrastructure after:{cutoff}" 형태로 검색
- "humanoid robot after:{cutoff}" 형태로 검색
- Reuters, Bloomberg, Electrek, InsideEVs, TechCrunch 등 해외 주요 매체 포함"""
        translation_note = _TRANSLATION_NOTE

    else:  # "both"
        region_label = "국내+해외(전체)"
        search_topics = """【검색 주제 — 국내 + 해외 통합】
1. 전기차(EV) 시장동향, 신차출시, 판매실적 (국내 + 글로벌)
2. 전기차 충전케이블 / EV charging cable, 충전인프라, 충전표준(CCS/NACS/CHAdeMO/GB-T)
3. 휴머노이드 로봇 / Humanoid robots (국내 + 글로벌)
4. 전기차·충전 관련 정책·규제 (한국 및 글로벌)"""
        search_hints = f"""- "전기차 뉴스 {today.strftime('%Y년 %m월')}" 형태로 검색
- "EV news after:{cutoff}" 형태로 검색
- "electric vehicle {today.strftime('%B %Y')}" 형태로 검색
- "humanoid robot after:{cutoff}" 형태로 검색
- 국내외 주요 매체 모두 포함"""
        translation_note = _TRANSLATION_NOTE

    return region_label, search_topics, search_hints, translation_note


def _collect_article_candidates(
    client: anthropic.Anthropic,
    region_label: str,
    search_topics: str,
    search_hints: str,
    today_iso: str,
    cutoff: str,
) -> list:
    """Step 1: Ask the LLM to collect article candidates and return them as JSON.

    Returns a list of dicts with keys: title, url, source, category, summary_ko.
    """
    system = f"""오늘 날짜: {today_iso}
수집 허용 기간: {cutoff} ~ {today_iso}
수집 지역: {region_label}

【역할】
Nextron Korea 주간 EV 뉴스 수집 AI.
웹 검색으로 최근 7일 내 기사를 수집하고, 결과를 JSON 배열로만 반환합니다.

【검색 방법】
{search_hints}
- 검색 결과에서 {cutoff} 이전 기사는 제거하고 URL만 포함

{search_topics}

【출력 형식 — 엄격히 준수】
아래 형식의 JSON 배열만 출력. 다른 텍스트·마크다운 금지.
[
  {{
    "title": "기사 원문 제목",
    "url": "https://...",
    "source": "출처 매체명",
    "category": "EV시장동향|충전인프라|정책규제|기술혁신|휴머노이드",
    "summary_ko": "2~3문장 한국어 요약"
  }},
  ...
]
- 최소 10개, 최대 25개 기사
- {cutoff} 이후 발행된 기사만 포함
- URL은 반드시 실제 기사 URL (홈페이지 URL 금지)"""

    response = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=4000,
        system=system,
        tools=[{"type": "web_search_20250305", "name": "web_search"}],
        messages=[{
            "role": "user",
            "content": (
                f"오늘은 {today_iso}입니다. 수집 지역: {region_label}. "
                f"{cutoff} ~ {today_iso} 사이 발행된 전기차·EV·충전케이블·휴머노이드 "
                f"기사를 검색해서 JSON 배열로만 반환해주세요."
            )
        }]
    )

    raw = "".join(b.text for b in response.content if b.type == "text").strip()
    # Strip markdown fences if present
    raw = re.sub(r"^```(?:json)?\s*", "", raw)
    raw = re.sub(r"\s*```$", "", raw).strip()

    try:
        articles = json.loads(raw)
        if not isinstance(articles, list):
            articles = []
    except (json.JSONDecodeError, ValueError):
        # Try to extract a JSON array from the raw text
        m = re.search(r"\[.*\]", raw, re.DOTALL)
        if m:
            try:
                articles = json.loads(m.group(0))
            except (json.JSONDecodeError, ValueError):
                articles = []
        else:
            articles = []

    return articles


def _filter_by_date(articles: list, cutoff_dt: datetime, status_writer=None) -> list:
    """Step 2: Fetch each article URL and verify publish date is within cutoff.

    Articles whose date cannot be determined are excluded for safety
    (conservative approach: when in doubt, leave it out).
    Returns list of dicts with an added 'published_date' key (YYYY-MM-DD).
    """
    filtered = []
    for art in articles:
        url = art.get("url", "")
        if not url:
            continue
        if status_writer:
            status_writer(f"🔍 날짜 확인 중: {url[:80]}…")
        dt = extract_publish_date(url)
        if dt is None or not is_within_cutoff(dt, cutoff_dt):
            continue
        art["published_date"] = dt.strftime("%Y-%m-%d")
        filtered.append(art)
    return filtered


def _generate_html(
    client: anthropic.Anthropic,
    articles: list,
    region_label: str,
    translation_note: str,
    today: datetime,
    week_ago: datetime,
    today_iso: str,
    cutoff: str,
) -> str:
    """Step 3: Generate the HTML newsletter from the verified article list."""
    today_str = today.strftime("%Y.%m.%d")
    w_ago_str = week_ago.strftime("%Y.%m.%d")
    today_kor = today.strftime("%Y년 %m월 %d일")
    w_ago_kor = week_ago.strftime("%Y년 %m월 %d일")

    articles_json = json.dumps(articles, ensure_ascii=False, indent=2)

    system = f"""오늘 날짜: {today_kor} ({today_iso})
수집 허용 기간: {w_ago_kor} ({cutoff}) ~ {today_kor} ({today_iso})
수집 지역: {region_label}

{translation_note}
【역할】
Nextron Korea 주간 EV 뉴스레터 HTML 생성 AI.
아래에 주어진 기사 목록(날짜 검증 완료)을 바탕으로 HTML 뉴스레터를 생성합니다.

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
② 주간 핵심요약: 3~5개 핵심 뉴스 불릿 (반드시 한국어)
③ 주간 핵심시그널 테이블: 시그널 | 내용 | 영향도(🔴고/🟡중/🟢저) (반드시 한국어)
④ 기업 하이라이트: CHAEVI·EVAR 등 언급 기사 별도 정리 (없으면 섹션 생략)
⑤ 카테고리별 뉴스:
   ⚡ 전기차 시장동향 / 🔌 충전 인프라 & 케이블 / 📋 정책 & 규제 / 🔬 기술 & 혁신 / 🤖 휴머노이드
   각 기사: 제목(원문 링크) | 출처 | 발행날짜(published_date 필드 값 사용) | 2~3문장 한국어 요약
⑥ 푸터: © {today.year} Nextron Korea | Claude AI 자동 생성 | {w_ago_str}~{today_str}

<!DOCTYPE html> 로 시작하는 완전한 HTML 문서만 출력. 마크다운 코드펜스(```) 절대 금지."""

    response = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=8000,
        system=system,
        messages=[{
            "role": "user",
            "content": (
                f"아래 날짜 검증이 완료된 기사 목록으로 HTML 뉴스레터를 생성해주세요.\n\n"
                f"기사 목록:\n{articles_json}"
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


def generate_newsletter(
    api_key: str,
    region: str = "both",
    status_writer=None,
) -> str:
    """Two-step newsletter generation with deterministic date filtering.

    Step 1: LLM collects article candidates (title, url, source, category, summary_ko).
    Step 2: Code fetches each URL and verifies publish date is within 7-day cutoff.
    Step 3: LLM generates HTML newsletter from the verified article list.
    """
    today, week_ago = get_dates()
    today_iso = today.strftime('%Y-%m-%d')
    cutoff = week_ago.strftime('%Y-%m-%d')
    cutoff_dt = week_ago.replace(
        hour=0, minute=0, second=0, microsecond=0, tzinfo=timezone.utc
    )

    region_label, search_topics, search_hints, translation_note = _build_region_config(
        region, today, cutoff
    )

    client = anthropic.Anthropic(api_key=api_key)

    # ── Step 1: collect candidates ──
    if status_writer:
        status_writer("📡 기사 후보 수집 중 (웹 검색)…")
    articles = _collect_article_candidates(
        client, region_label, search_topics, search_hints, today_iso, cutoff
    )

    # ── Step 2: deterministic date filter ──
    if status_writer:
        status_writer(f"🗓️ {len(articles)}개 기사 날짜 검증 중…")
    articles = _filter_by_date(articles, cutoff_dt, status_writer=status_writer)

    if status_writer:
        status_writer(f"✅ 날짜 검증 완료: {len(articles)}개 기사가 7일 필터 통과")

    if not articles:
        # Return a minimal HTML page explaining no recent articles were found
        today_str = today.strftime("%Y.%m.%d")
        w_ago_str = week_ago.strftime("%Y.%m.%d")
        return (
            f"<!DOCTYPE html><html><body>"
            f"<p>⚠️ {cutoff} ~ {today_iso} 기간에 해당하는 기사를 찾을 수 없습니다.</p>"
            f"</body></html>"
        )

    # ── Step 3: generate HTML ──
    if status_writer:
        status_writer("✍️ HTML 뉴스레터 생성 중…")
    return _generate_html(
        client, articles, region_label, translation_note,
        today, week_ago, today_iso, cutoff
    )

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
        st.markdown("### 🌏 수집 지역")
        region_option = st.radio(
            "수집 지역 선택",
            options=["both", "domestic", "international"],
            format_func=lambda x: {
                "both": "🌏 국내+해외 (전체)",
                "domestic": "🇰🇷 국내(한국)",
                "international": "🌐 해외(국제)",
            }[x],
            index=0,
            label_visibility="collapsed",
        )

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
                    html = generate_newsletter(
                        api_key,
                        region=region_option,
                        status_writer=st.write,
                    )
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
