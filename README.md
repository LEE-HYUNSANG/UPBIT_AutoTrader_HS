# UPBIT AutoTrading Example

This repository contains a minimal Flask + SocketIO demo for an automated
trading dashboard. All HTML templates use Jinja2 variables so tables and forms
are filled with server side data.

## Quick Start
1. 파이썬 3.11 이상 설치 후 저장소를 클론합니다.
2. 의존 패키지 설치:
   ```bash
   pip install wheel
   pip install -r requirements.txt
   ```
3. 봇 실행:
   ```bash
   python app.py
   ```
4. 웹 브라우저에서 `http://localhost:5000` 에 접속하면 대시보드를 확인할 수 있습니다.
## 사용법
1. 서버 실행 후 웹 브라우저로 접속하면 메인 대시보드가 표시됩니다.
2. "전략" 메뉴에서 원하는 전략과 파라미터를 설정합니다.
3. "봇 시작" 버튼을 누르면 자동매매가 진행됩니다.
4. 각 메뉴에서 자금 한도와 위험 관리 값을 조정할 수 있습니다.
5. 실제 API 키와 텔레그램 토큰은 `config/secrets.json`에 입력합니다. 먼저
   `config/secrets.json.example`을 복사해 파일을 만든 뒤 값을 수정하세요.


## Structure
- **app.py** – Flask application providing HTML pages and API routes. SocketIO is used to push live notifications.
- **templates/** – Jinja2 templates extending `base.html`. Pages include
  `Home.html`, `strategy.html`, `fund-risk.html`, `notifications.html`,
  `pSettings.html` and `aiAnalysis.html`.
  Each template gets variables like `positions`, `strategies`, `alerts` or `settings` directly from Flask.
- **static/js/main.js** – Common JavaScript handling API calls, SocketIO events,
  draggable layout and real time table updates.
- **static/css/custom.css** – Consolidated styles for all pages with no inline styles left in templates.
- **config/market.json** – Sample market data loaded for monitoring filters.
- **config/active_positions.json** – Persisted open trades restored on startup.
  Missing strategy information results in a strategy code of `INIT`, meaning the trade's origin is unknown.
- **notify()** – Helper in `app.py` that sends messages to SocketIO and Telegram.

## Example variables passed to templates
```python
return render_template(
    "Home.html",
    running=settings["running"],
    positions=positions,
    alerts=alerts,
    signals=signals,
)
```

## API usage
Buttons with a `data-api` attribute automatically send the nearest form data via `fetch`:
```html
<button data-api="/api/start-bot">봇 시작</button>
```
The JavaScript in `main.js` will call `/api/start-bot` and show any returned message via a modal.
SocketIO events `notification`, `positions` and `alerts` push real time updates to the browser.

### Manual buy and sell
Two buttons on the Home page allow direct trading:

* **Manual Buy** – POST `/api/manual-buy` with the selected coin. The bot uses
  the "회당 매수금(₩)" value from the fund settings and places a market order.
* **Manual Sell** – POST `/api/manual-sell` and sell the entire position of that
  coin at market price.

## Market data
`app.py` retrieves current prices and 24‑hour traded value from Upbit whenever a new
five‑minute candle closes.
Coins are filtered by the values in `config/filter.json` (`min_price`, `max_price`, `rank`).
The resulting list is written to `config/monitor_list.json` only when settings are saved,
so the same coins are reused until you update the filter.

### Buy signal levels
Buy signals are split into six categories:

1. 매수 적극 추천
2. 매수 추천
3. 관망
4. 매수 회피
5. 매수 금지
6. 데이터 대기

The `calc_buy_signal()` function returns these labels along with
`signal_class` values like `buy-strong`, `buy`, `wait`, `avoid`, `ban`
and `nodata`. See `docs/BUY_MONITOR_SPEC_KR.md` for detailed rules.

## Running
Install requirements and start the server:
```bash
pip install wheel
pip install -r requirements.txt
python app.py
```
The app runs with `socketio.run` so WebSocket notifications work by default.
Real time events are pushed to the browser via SocketIO and displayed with `showAlert()` in `main.js`.

The server checks the latest 5‑minute candle every 10 seconds. When the candle
time changes it refreshes KRW market data using `pyupbit`. Coins are ordered by
buy signal level first and then by 24‑hour traded value. They are filtered according to the
dashboard settings (`min_price`, `max_price`, `rank`). The resulting ticker list
is used for both monitoring and trading.

## Logging and refresh timers
Each log level is written to a separate file under the `logs/` directory
(e.g. `logs/debug.log`, `logs/cal.log`). Set `LOG_LEVEL=DEBUG` to record each
indicator value calculated for buy signals. The dashboard headers display the
remaining time until the next account and signal refresh, updated when a new
5‑minute candle closes.

When the countdown reaches `0:00` it now resets to `5:00` on the browser and
continues decreasing every second. Once the server finishes processing and
`/api/status` returns a new `next_refresh` value, the timer is synchronised with
the actual remaining time until the next five‑minute candle closes.

Account information and sell monitoring data are fetched every 10 seconds so
the dashboard always shows recent positions.

Both monitoring tables are refreshed right after each calculation. The
background loops emit a `refresh_data` SocketIO event, which triggers the
browser to call `/api/balances` and `/api/signals` three times at one‑second
intervals to avoid missing any update.
calc_buy_signal_retry() tries up to three times for each coin. If data is still
missing, the row shows "⛔" and "데이터 대기". Such rows are recalculated every
10 seconds until ten seconds before the next five‑minute candle. When data is
filled in, the browser receives a `refresh_data` event immediately.

Running the app with `python app.py` uses Flask's development server. It prints
a single access log line for every HTTP request. Example:
```
127.0.0.1 - - [21/May/2025 10:50:29] "GET /api/status HTTP/1.1" 200 236 0.002
```
The fields show the client IP, method and path, HTTP status, response size and
processing time. Because the dashboard polls `/api/status` every five seconds,
these lines appear repeatedly during development.

## Running tests
Install `pytest` and execute the suite:
```bash
pip install pytest
pytest
```

## Secrets configuration
Copy `config/secrets.json.example` to `config/secrets.json` and fill in your keys
before starting the server. This path is included in `.gitignore` so your real keys
stay private:

```json
{
  "UPBIT_KEY": "YOUR-UPBIT-KEY",
  "UPBIT_SECRET": "YOUR-UPBIT-SECRET",
  "TELEGRAM_TOKEN": "BOT-TOKEN",
  "TELEGRAM_CHAT_ID": "123456789"
  // "EMAIL_HOST": "smtp.example.com",
  // "EMAIL_PORT": 587,
  // "EMAIL_USER": "bot@example.com",
  // "EMAIL_PASSWORD": "pass",
  // "EMAIL_TO": "notify@example.com"  // 이메일 알림은 비활성화 상태

}
```

`utils.load_secrets()` reads this file when the app starts. If the file is missing,
unreadable or any required value is empty the application prints an error,
logs it and exits immediately. When Telegram credentials are available (in the
file or via `TELEGRAM_TOKEN` and `TELEGRAM_CHAT_ID` environment variables) the
same message is also sent there.
Example error:
```
[ERROR] Missing required secrets: UPBIT_KEY, UPBIT_SECRET
```

`config/market.json` stores fallback market data when live fetching from Upbit fails.
Tests load this file to avoid network access.
`config/active_positions.json` keeps track of open positions so strategies are restored on startup.

The bot tracks price lookup errors per coin. When a coin fails more than
`failure_limit` times (default `3`), a warning is raised but the ticker remains
monitored. The failure count is then reset so additional alerts may trigger if
the problem continues.

## Documentation
- `docs/OVERVIEW_KR.md` – 프로젝트 전체 흐름을 한국어로 정리한 문서
- `docs/BUY_MONITOR_SPEC_KR.md` – 매수 모니터링 표 각 컬럼의 계산 방식
- `AGENTS.md` – 개발 규칙과 코드 구조 요약

## Windows 설치 가이드
Windows 10/11 + Visual Studio C++ 빌드툴 환경에서 다음 순서로 준비합니다.

1. [Python 3.11](https://www.python.org/) 설치 시 "Add python to PATH" 를 선택합니다.
2. [Visual Studio Build Tools](https://visualstudio.microsoft.com/visual-cpp-build-tools/) 을 설치해 C++ 컴파일 도구를 준비합니다.
3. 저장소를 클론한 후 `cmd` 또는 PowerShell 에서 아래 명령을 실행합니다.

```cmd
pip install --upgrade pip
pip install wheel
pip install -r requirements.txt
```

`requirements.txt` 는 Windows 환경에서는 `TA-Lib`(미리 컴파일된 whl), 그
외 환경에서는 `talib-binary` 가 자동 선택되도록 환경 마커를 사용합니다.
따라서 별도 빌드 과정 없이 설치가 완료됩니다. 만약 TA-Lib 설치가 실패
한다면 [공식 배포 페이지](https://www.lfd.uci.edu/~gohlke/pythonlibs/#ta-lib)
에서 파이썬 버전에 맞는 whl 파일을 받아 직접 설치할 수 있습니다.

서버는 아래와 같이 실행합니다.

```cmd
python app.py
```

웹 브라우저에서 `http://localhost:5000` 접속 후 대시보드를 확인합니다.

## 운영 예시 (Gunicorn & Docker)

Gunicorn + eventlet 로 배포할 수 있습니다.

```bash
./scripts/run_gunicorn.sh
```

도커 사용 시:

```bash
docker build -t upbit-bot .
docker run -p 8000:8000 upbit-bot
```

`scripts/run_gunicorn.sh` 는 간단한 운영 자동화 스크립트 예시입니다.

## 문제 해결 로그
아래는 VSCode CSS 진단에서 보고된 예시 오류입니다. `templates/Home.html` 134번째 줄의 인라인 스타일에서 발생하였습니다.

```json
[
  {
    "resource": "/c:/Users/twtko/Desktop/UPBIT_AutoTrader_HS/templates/Home.html",
    "owner": "_generated_diagnostic_collection_name_#0",
    "code": "css-identifierexpected",
    "severity": 8,
    "message": "식별자 필요",
    "source": "css",
    "startLineNumber": 134,
    "startColumn": 53,
    "endLineNumber": 134,
    "endColumn": 54
  }
]

[
  {
    "resource": "/c:/Users/twtko/Desktop/UPBIT_AutoTrader_HS/templates/Home.html",
    "owner": "_generated_diagnostic_collection_name_#0",
    "code": "css-rcurlyexpected",
    "severity": 8,
    "message": "} 필요",
    "source": "css",
    "startLineNumber": 134,
    "startColumn": 54,
    "endLineNumber": 134,
    "endColumn": 55
  }
]

[
  {
    "resource": "/c:/Users/twtko/Desktop/UPBIT_AutoTrader_HS/templates/Home.html",
    "owner": "_generated_diagnostic_collection_name_#0",
    "code": "css-ruleorselectorexpected",
    "severity": 8,
    "message": "at-rule 또는 선택기가 필요함",
    "source": "css",
    "startLineNumber": 134,
    "startColumn": 68,
    "endLineNumber": 134,
    "endColumn": 69
  }
]

[
  {
    "resource": "/c:/Users/twtko/Desktop/UPBIT_AutoTrader_HS/templates/Home.html",
    "owner": "_generated_diagnostic_collection_name_#0",
    "code": "emptyRules",
    "severity": 4,
    "message": "빈 규칙 집합을 사용하지 마세요.",
    "source": "css",
    "startLineNumber": 134,
    "startColumn": 48,
    "endLineNumber": 134,
    "endColumn": 53
  }
]
```

해당 오류는 템플릿 변수를 직접 스타일 속성에 사용해 CSS 파서가 값을 인식하지 못해 발생했습니다. `data-pos` 속성으로 위치 값을 전달하고 스크립트에서 스타일을 적용하도록 변경하면 경고가 사라집니다.

```html
<span class="pin" data-pos="{{ p.pin_pct }}"></span>
```

