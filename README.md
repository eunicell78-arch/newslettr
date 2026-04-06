# ⚡ EV 뉴스레터 자동 발행 시스템

전기차 & 충전케이블 주간뉴스를 자동 수집해 HTML 리포트를 생성하고 이메일로 발송합니다.

---

## 🚀 배포 방법 (3단계)

### 1단계 — GitHub에 올리기

```
GitHub에서 새 레포지토리 생성 (예: ev-newsletter)
아래 3개 파일 업로드:
  - app.py
  - requirements.txt
  - README.md
```

### 2단계 — Streamlit Cloud 배포

1. **share.streamlit.io** 접속 → GitHub 계정으로 로그인
2. **New app** 클릭
3. Repository: `본인계정/ev-newsletter` 선택
4. Branch: `main`
5. Main file path: `app.py`
6. **Deploy** 클릭 → 고정 URL 발급됨

### 3단계 — Secrets 설정 (API 키 등록)

배포 완료 후 앱 대시보드에서:

**Settings → Secrets** 에 아래 내용 붙여넣기:

```toml
ANTHROPIC_API_KEY = "sk-ant-api03-여기에_본인_키_입력"
GMAIL_ADDRESS = "발송할Gmail주소@gmail.com"
GMAIL_APP_PASSWORD = "xxxx xxxx xxxx xxxx"
```

> Secrets를 등록하면 앱 화면에서 키를 입력하지 않아도 자동 연결됩니다.

---

## 🔑 API 키 발급 방법

### Anthropic API Key
1. **console.anthropic.com** 접속
2. API Keys → Create Key
3. 생성된 키 복사 (`sk-ant-api03-...`)

### Gmail 앱 비밀번호
> 일반 Gmail 비밀번호가 아닌 **앱 전용 비밀번호**가 필요합니다.

1. **myaccount.google.com** → 보안
2. 2단계 인증 활성화 (미설정 시 먼저 설정)
3. 검색창에 **"앱 비밀번호"** 검색
4. 앱 선택: **기타(직접 입력)** → 이름: `EV Newsletter`
5. 생성된 16자리 비밀번호 복사 (`xxxx xxxx xxxx xxxx`)

---

## 📋 사용 방법

1. 배포된 앱 URL 북마크
2. 매일 아침 앱 접속
3. **🔍 뉴스 수집 & 리포트 생성** 클릭 (1~2분 소요)
4. 미리보기 확인
5. **📧 이메일 발송** 클릭

---

## 📬 수신자 변경 방법

`app.py` 파일 상단 `RECIPIENTS` 리스트 수정:

```python
RECIPIENTS = [
    "eunice@nextronkorea.com",
    "jack@nextronkorea.com",
    # 추가/삭제
]
```

---

## 🏢 하이라이트 기업 변경 방법

`app.py` 파일 상단 `HIGHLIGHT_COMPANIES` 리스트 수정:

```python
HIGHLIGHT_COMPANIES = ["CHAEVI", "EVAR", "EVSIS", ...]
```

---

## ⚙️ 기술 스택

- **Streamlit** — 웹 앱 프레임워크
- **Anthropic Claude API** — 뉴스 수집 (web_search) + HTML 생성
- **Python smtplib** — Gmail 직접 발송 (초안 저장 없이 바로 발송)
