\# BusOnlineTicket — QA Automation Framework



A structured, industry-style test automation project for \[BusOnlineTicket.com](https://www.busonlineticket.com)  

using \*\*pytest\*\* · \*\*Selenium\*\* (UI) · \*\*requests\*\* (API).



\---



\## Project Structure



```

bot\_qa/

├── config/

│   ├── \_\_init\_\_.py

│   └── settings.py          # Browser settings, timeouts, paths

│

├── data/

│   └── test\_data.json       # ← All test credentials live here

│

├── tests/

│   ├── ui/

│   │   ├── test\_ui\_login.py    # TC-UI-01: Login via phone number

│   │   └── test\_ui\_signup.py   # TC-UI-02: Signup → OTP screen

│   └── api/

│       ├── test\_api\_login.py   # TC-API-01/02: Login valid + invalid

│       └── test\_api\_signup.py  # TC-API-03/04: Signup valid + duplicate

│

├── utils/

│   ├── data\_loader.py       # Loads test\_data.json

│   ├── driver\_factory.py    # Creates Selenium WebDriver instances

│   └── logger.py            # Colour-coded terminal output

│

├── reports/                 # (auto-created) test reports

├── conftest.py              # Fixtures + custom summary reporter

├── pytest.ini               # pytest settings \& marker registration

└── requirements.txt

```



\---



\## Setup



\### 1. Create a virtual environment

```bash

python -m venv venv

\# Windows

venv\\Scripts\\activate

\# macOS / Linux

source venv/bin/activate

```



\### 2. Install dependencies

```bash

pip install -r requirements.txt

```



\### 3. Update test data

Edit `data/test\_data.json` with valid credentials:

```json

{

&#x20; "login": {

&#x20;   "phone": "163553613",

&#x20;   "password": "111111"

&#x20; },

&#x20; "signup": {

&#x20;   "phone": "1XXXXXXXXX",    ← use a FRESH, unregistered number

&#x20;   "password": "Test@1234",

&#x20;   "confirm\_password": "Test@1234"

&#x20; }

}

```



\---



\## Running Tests



| Command | What it runs |

|---|---|

| `pytest` | All tests |

| `pytest -m ui` | UI tests only |

| `pytest -m api` | API tests only |

| `pytest tests/ui/test\_ui\_login.py` | Single test file |

| `pytest -m ui -v` | UI tests with verbose output |



\### Expected terminal output

```

================================================================

QA AUTOMATION SUMMARY

================================================================

&#x20; ✔  UI:     2/2 passed

&#x20; ✔  API:    4/4 passed

================================================================

```



\---



\## Test Cases



\### UI Tests (Selenium — browser is always visible)



| ID | File | Description |

|---|---|---|

| TC-UI-01 | test\_ui\_login.py | Login via phone number and password |

| TC-UI-02 | test\_ui\_signup.py | Fill signup form → assert OTP screen appears |



\### API Tests (requests library)



| ID | File | Description |

|---|---|---|

| TC-API-01 | test\_api\_login.py | POST login with valid credentials → HTTP 200 |

| TC-API-02 | test\_api\_login.py | POST login with invalid credentials → rejected |

| TC-API-03 | test\_api\_signup.py | POST signup with valid data → OTP triggered |

| TC-API-04 | test\_api\_signup.py | POST signup with duplicate phone → error returned |



\---



\## ⚠️  OTP / Signup Limitation



Phone-based signup requires a real SMS OTP. Automated tests \*\*cannot\*\* intercept SMS.



\*\*Current approach (industry standard):\*\*

\- The test fills the form and verifies the \*\*OTP screen appears\*\* — this proves the signup request was accepted.

\- OTP submission is left for manual verification.



\*\*To fully automate signup in the future:\*\*

1\. Use a \*\*virtual number service\*\* (Twilio, TextMagic, etc.) and read OTPs via their API.

2\. Ask the dev team for a \*\*test bypass endpoint\*\* that accepts a fixed OTP code (e.g. `123456`) in a staging environment.



\---



\## Configuration



Environment variables (optional — override `config/settings.py`):



| Variable | Default | Options |

|---|---|---|

| `BROWSER` | `chrome` | `chrome`, `firefox`, `edge` |

| `HEADLESS` | `false` | `true` to run without UI |



Example:

```bash

BROWSER=firefox pytest -m ui

HEADLESS=true pytest -m api

```



\---



\## Troubleshooting



\*\*Selector errors (element not found)\*\*  

The website may have updated its HTML. Open the page in DevTools, find the new element ID/class, and update the selector in the relevant test file.



\*\*API endpoint 404\*\*  

The API path may have changed. Use your browser's Network tab to capture the correct endpoint during a manual login/signup, then update `API\_LOGIN\_ENDPOINT` or `API\_SIGNUP\_ENDPOINT`.



\*\*ChromeDriver version mismatch\*\*  

`webdriver-manager` handles this automatically. If you see driver errors, run:

```bash

pip install --upgrade webdriver-manager

```

