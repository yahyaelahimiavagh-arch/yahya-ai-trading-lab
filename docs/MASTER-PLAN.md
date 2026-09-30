# YATL — نقشه مرجع اجرا و وضعیت پروژه

نسخه بازیابی و supersede‌شده: 2026-09-09
وضعیت جاری: **P0 تا P10 ENGINEERING / OPERATIONS ACCEPTED — REAL FORWARD EVIDENCE COLLECTING — P11 LOCKED**
قدم جاری: **دو مسیر موازی: P10 جمع‌آوری شواهد آینده‌نگر + MCF-PROD-001 بستن جهان ماهانه قبل از اجرای عملکرد — P11 LOCKED**
مسیر تحقیقاتی موازی از **2026-09-23**: **CRISIS & REGIME STRESS LAB — RESEARCH ONLY — P10 UNTOUCHED**

## منشأ و حدود سند

این سند از متن کامل قابل‌دسترسی گفت‌وگوی «برنامه پروژه ربات معامله»
(6a9c78d3-c024-83eb-9cf9-b86bf860f2bb) و پیام ثبت Master Plan v1.0 در
«معرفی مدل جدید OpenAI» (6a9b31eb-46cc-83eb-8404-6ce4a8b17ebf) بازیابی شده است.
فایل اصلی MD/ZIP در خروجی بازیابی به صورت content-reference بود و متن فایل در دسترس نبود.
بنابراین این سند کپی لفظ‌به‌لفظ فایل اصلی نیست؛ فازها و شناسه‌های P0 از پیام‌ها نقل شده‌اند.
معیارهای تحویل زیر برای منظم‌کردن اجرا روشن شده‌اند؛ نباید به عنوان نقل مستقیم فایل اصلی معرفی شوند.
اگر فایل اصلی بازیابی شد، اختلاف‌ها ثبت و تطبیق داده می‌شوند، نه اینکه وضعیت‌های PASS حذف شوند.

## تعریف پروژه و پایان آن

Yahya AI Trading Lab یک سامانه پژوهش، آزمون و اجرای کنترل‌شده معاملات است.
نسخه اول فقط Crypto Spot روی BTC/USDT و ETH/USDT است؛ بدون Short، Margin، Futures و اهرم.
ساختار تصمیم: داده → تحلیل/استراتژی → کنترل ریسک مستقل → اجرای Paper/Testnet → ثبت و ارزیابی.
AI پیشنهاد می‌دهد و حق اجرای مستقیم ندارد. کنترل ریسک می‌تواند هر پیشنهاد را رد کند.

تحویل نرم‌افزاری نسخه آزمایشی: تکمیل و آزمون زنجیره P0 تا P9.
پذیرش عملکرد: تکمیل P10 روی داده جدید با شواهد و معیارهای از پیش مشخص‌شده.
P11 فقط نامزد اجرای واقعی بسیار محدود است، نه نتیجه خودکار تکمیل نرم‌افزار یا وعده سود.

قفل‌های فعلی: PAPER ONLY | LIVE_MASTER_LOCK=OFF | NO FUTURES | NO LEVERAGE |
NO WITHDRAWAL API | NO AI DIRECT EXECUTION. کلید فعلی USER_DATA only باقی می‌ماند.


## اصل حاکم اقتصادی — Profitability over Complexity

هدف نهایی YATL **تولید خروجی اقتصادی مثبت و قابل‌تکرار پس از هزینه‌ها، با ریسک
کنترل‌شده، روی داده‌ای است که سیستم قبلاً ندیده است**. تکمیل فازها، تعداد
اندیکاتورها، تعداد تحلیل‌ها، استفاده از AI، تعداد خطوط کد، تعداد تست‌ها یا زیبایی
Dashboard به‌تنهایی معیار موفقیت اقتصادی نیستند.

قواعد حاکم:

- **Profitability > Complexity**: اگر یک روش ساده روی داده جدید و پس از fee و
  slippage بهتر و پایدارتر از ترکیب روش‌های پیچیده عمل کند، روش ساده ترجیح دارد.
- **Evidence > Number of analyses**: اضافه‌کردن technical indicator، candlestick
  pattern، price action، order flow، derivatives، on-chain، macro، fundamental،
  news/sentiment یا AI فقط وقتی توجیه دارد که به‌صورت point-in-time و بدون leakage
  قابل ارزیابی باشد و ارزش افزوده اقتصادی آن در مقایسه با baseline سنجیده شود.
- **Out-of-sample / forward evidence > attractive backtest**: نتیجه خوب روی
  داده‌ای که برای طراحی/تنظیم دیده شده است، به‌تنهایی edge را اثبات نمی‌کند.
- **Risk-adjusted persistence > raw profit**: سود خالص باید همراه drawdown،
  هزینه، sample size، stability across regimes، failure behavior و exposure بررسی
  شود. سود خامی که با ریسک غیرقابل‌قبول یا شکنندگی بالا ساخته شود Gate را پاس
  نمی‌کند.
- **One profitable edge > many unproven signals**: هزار تحلیل بدون اثر مثبت
  پایدار روی نتیجه اقتصادی ارزش محصولی ندارد. هیچ feature یا مدل صرفاً به‌خاطر
  رایج‌بودن در ترید به سیستم اضافه نمی‌شود.
- هر قابلیت تحلیلی جدید باید baseline روشن داشته باشد و در صورت امکان با
  ablation/comparison نشان دهد که حذف/اضافه‌شدن آن چه اثری بر نتایج خارج از نمونه
  دارد. افزایش complexity بدون evidence کافی مجاز نیست.
- معیار اقتصادی اصلی در P10 شامل **Net PnL بعد از fee/slippage روی داده جدید**
  است، اما پذیرش فقط با سود مثبت خام انجام نمی‌شود؛ drawdown، تعداد معاملات،
  پایداری، consistency، failure/recovery و معیارهای از پیش‌ثبت‌شده نیز Gate هستند.
- اگر P10 نشان دهد استراتژی‌های فعلی edge قابل‌قبول ندارند، پروژه **موفق یا Live
  ready اعلام نمی‌شود**. مسیر به research/strategy iteration برمی‌گردد؛
  candidateها دوباره با همان اصول point-in-time، no leakage و pre-registered gates
  ارزیابی می‌شوند و P11 بسته می‌ماند.
- P11 فقط پس از پذیرش P10 و gateهای امنیت/حساب/ریسک باز می‌شود و حتی آن زمان نیز
  Tiny Live یک validation محدود است، نه تضمین سود.

این اصل، ترتیب ایمنی فازها را تغییر نمی‌دهد؛ بلکه معیار تصمیم‌گیری درباره ارزش هر
قابلیت و موفقیت نهایی سیستم را روشن می‌کند.

## ترتیب ثابت فازها

| فاز | خروجی مورد انتظار | وضعیت امروز |
|---|---|---|
| P0 Foundation | محیط، Git، امنیت، Testnet، آموزش و تمرین دستی Paper | **RUNTIME ACCEPTED — 2026-09-09** |
| P1 Market Data Layer | REST، دانلود تاریخی، WebSocket، نرمال‌سازی، SQLite، حذف تکرار، تشخیص شکاف، گزارش سلامت BTC/ETH | **RUNTIME ACCEPTED — checkpoint `4e77e34`** |
| P2 Backtesting Engine | آزمون تاریخی تکرارپذیر با کارمزد، لغزش و جلوگیری از استفاده از آینده | **RUNTIME ACCEPTED — checkpoint `9cbc197`** |
| P3 Strategy Framework | چارچوب مشترک استراتژی و قواعد روشن سیگنال/عدم معامله | **RUNTIME ACCEPTED — final audit run `34699232936`** |
| P4 Risk Manager | اندازه موقعیت، محدودیت ریسک و Kill Switch مستقل | **RUNTIME ACCEPTED — checkpoint `f3a5575`** |
| P5 Paper/Testnet Execution | اجرای آزمایشی زیر نظر Risk Manager و ثبت وضعیت سفارش | **RUNTIME ACCEPTED — checkpoint `cd5ff565`** |
| P6 AI Analyst | تحلیل ساختاریافته و NO_TRADE بدون دسترسی مستقیم به اجرا | **RUNTIME ACCEPTED — checkpoint `f07f220`** |
| P7 Journal / Analytics | دفتر معاملات و گزارش عملکرد قابل ممیزی | **RUNTIME ACCEPTED — checkpoint `93b9d87`** |
| P8 Dashboard | نمایش وضعیت، معاملات، عملکرد و خطاها | **RUNTIME ACCEPTED — checkpoint `fe973e8`** |
| P9 Telegram | هشدار و notification محدود طبق قواعد امنیتی | **RUNTIME ACCEPTED — checkpoint `60d7e267`** |
| P10 Forward/Paper Validation | ارزیابی روی داده جدید، هزینه‌ها، افت سرمایه و تست خطا/توقف | **ENGINEERING + COLLECTOR + MONITORING ACCEPTED / REAL FORWARD EVIDENCE IN PROGRESS** |
| P11 Tiny Live Candidate | فقط پس از پذیرش P10، ممیزی امنیت، الزامات حساب و تأیید صریح | LOCKED |


## وضعیت authoritative فعلی — 2026-09-22

این بخش وضعیت جاری را supersede می‌کند؛ بخش «نمای پیشرفت فعلی — 2026-09-20»
در ادامه برای سابقه تاریخی نگه داشته شده است.

- P0 تا P9 runtime accepted و merge شده‌اند.
- P10-001 تا P10-010 engineering runtime accepted و merge شده‌اند.
- P10 production forward collector با PR #78، Final HEAD
  `6b11a363d117e81a69db5a3929cb871072e46145` و Actions
  `35645158177` پذیرفته شد؛ full suite **1514/1514** و focused collector
  **12/12** PASS بود.
- PR #78 در checkpoint
  `eab1599d633b019a3d10f7af277bb5b5011a0753` merge شد و PR #79
  اصلاح CWD runbook را در
  `73815feb71947cf49f6d6ddace50b6ad49a4088b` بست.
- اولین real forward `COLLECTED` در VPS:
  **2026-09-22 04:05 UTC / 07:05 Istanbul**.
- real forward collection به‌صورت hourly ادامه دارد و در observed checkpoint
  شش dataset BTCUSDT/ETHUSDT × 15m/1h/4h با `store_count=72` و quality PASS
  ثبت شده بود.
- قبل از 51×4h warm-up، وضعیت درست
  `NOT_READY/FORWARD_WARMUP_NOT_COMPLETE` است؛ اولین decision قانونی زودتر از
  **2026-09-30 12:00 UTC / 15:00 Istanbul** نیست.
- لایه read-only Dashboard + outbound-only Telegram با PR #80، exact Final HEAD
  `d27d2d06db2717a9be4bfd36a3f7c2a1a55b5651` و Actions
  `35702529008` پذیرفته شد؛ هر دو job PASS و full suite **1529/1529** بود.
- focused monitor **8/8**، monitor-notifier **4/4** و notification projection
  regression **18/18** PASS شدند؛ safety scan و deterministic mocked monitoring
  runtime نیز PASS شدند.
- PR #80 در checkpoint
  `a6f032f1ac00a67fe70d8748924f5bbd05104782` squash-merge شد.
- docs closeout پیش از deployment در
  `51a266ea2c2ebe37bee8fc8072c06117406aabf1` ثبت شد و PR #81 persistence سرویس
  loopback HTTP را در checkpoint `2c244e38c29d938b824400882151cb1bcb4ea05f`
  بست.
- VPS Dashboard در 2026-09-22 runtime-verified شد: builder موفق بود، HTTP service
  enabled/active و فقط روی `127.0.0.1:8765` بود و تست محلی `HTTP 200` گرفت. صفحه
  واقعی وضعیت `NOT_READY/FORWARD_WARMUP_NOT_COMPLETE`,
  `INSUFFICIENT_EVIDENCE` و `P11 LOCKED` را نشان داد.
- outbound-only Telegram نیز runtime-verified شد: در 09:16 UTC هر دو پیام
  BTCUSDT/ETHUSDT با `DELIVERED` و overall `DELIVERY_COMPLETE` ارسال شدند؛ replay
  فوری در 09:18 UTC برای هر دو `DUPLICATE_SUPPRESSED=true` ثبت کرد.
- timer Telegram enabled/active است و روزانه در `05:10 UTC / 08:10 Istanbul`
  اجرا می‌شود؛ monitoring credentialها خارج از Git باقی می‌مانند.
- Monitoring هیچ candidate/gate/window/evidence را تغییر نمی‌دهد؛ Dashboard فقط
  local/read-only است و Telegram فقط outbound-only از transport پذیرفته‌شده P9
  استفاده می‌کند.
- قدم عملی بعدی: فقط ادامه real forward observation بدون تغییر candidate/gates؛
  deploy/verification monitoring بسته شده و هیچ کدنویسی P11 مجاز نیست.
- P11 همچنان **LOCKED** است. حتی engineering completion یا monitoring acceptance
  به معنی economic acceptance، Live authorization یا سوددهی اثبات‌شده نیست.

## مسیر تحقیقاتی موازی — Crisis & Regime Stress Lab — شروع 2026-09-23

هدف این مسیر، **شکنجه‌کردن پژوهشی Strategy و Risk Stack در دوره‌های تاریخی بحرانی
و شوک‌های مصنوعی** است؛ نه جایگزین‌کردن P10 و نه تولید مجوز Live. این مسیر از
**2026-09-23** با research، ساخت Event Catalog و جمع‌آوری داده شروع می‌شود و می‌تواند
همزمان با real-forward P10 ادامه پیدا کند.

### ساختار رسمی Research Track

مرجع اجرایی جزئی Crisis Lab از این پس در
[`docs/research/crisis-lab/`](research/crisis-lab/README.md) نگه‌داری می‌شود.
Master Plan فقط ترتیب Gateها و رابطه این مسیر با P10/P11 را نگه می‌دارد تا جزئیات
پژوهش در یک پوشه مستقل، قابل‌ممیزی و قابل‌گسترش باقی بمانند.

ترتیب رسمی checkpointها:

| Checkpoint | هدف | شرط عبور |
|---|---|---|
| CRL-000 | Charter / isolation | مرز RESEARCH_ONLY و عدم تغییر P10 فریز شود |
| CRL-001 | Event Catalog | schema، timestamps، sources و holdout designation ثبت شود |
| CRL-002 | Data Acquisition | acquisition/provenance reproducible و P10 read-only باشد |
| CRL-003 | Data Quality / Manifest | هر dataset دارای health PASS و SHA canonical باشد |
| CRL-004 | Historical Replay | point-in-time deterministic replay روی crisis data اجرا شود |
| CRL-005 | Controls / Baselines | pre/event/aftermath/calm + CASH + Buy-and-Hold مقایسه شوند |
| CRL-006 | Synthetic Stress | ماتریس shockهای مصنوعی ثابت و قابل‌تکرار اجرا شود |
| CRL-007 | Severity / Random Windows | S1–S5 و random-window registry بدون outcome tuning فریز شود |
| CRL-008 | Shadow Challenger | protocol challenger/ablation بدون آلودگی P10 پذیرفته شود |
| CRL-009 | Survival Certificate | artifact فنی immutable و reconstructable تعریف شود |
| CRL-010 | Independent Audit | کل evidence chain مستقل recompute و audit شود |

پوشه‌بندی استاندارد research:

- documentation/specs: `docs/research/crisis-lab/`;
- future research-only code/scripts: `research/crisis_lab/`;
- bulk runtime data: `data/research/crisis-lab/` و خارج از Git؛
- generated research artifacts: `artifacts/research/crisis-lab/` با انتشار فقط
  subsetهای bounded/canonical.

هیچ checkpoint بعدی پیش از بستن Gate قبلی «accepted» تلقی نمی‌شود. برای سرعت،
desk research می‌تواند موازی انجام شود، اما evidence نهایی باید همین ترتیب و مرزهای
داده را رعایت کند.

### قانون جداسازی از P10

- P10 Track A بدون هیچ تغییر ادامه می‌یابد: candidate، configuration، gate registry،
  sealed window، fee/slippage، risk limits و evidence فعلی **نباید** تحت تأثیر نتایج
  Crisis Lab تغییر کنند.
- Crisis Lab Track B کاملاً **RESEARCH_ONLY** است و نتیجه آن حق upgrade کردن
  `INSUFFICIENT_EVIDENCE`، بازکردن P11، ایجاد RiskAuthorization، quantity authority،
  TRADE permission، order endpoint یا AI direct execution را ندارد.
- هر weakness یا ایده‌ای که در Crisis Lab کشف شود فقط برای **نسل بعدی candidate /
  policy / research iteration** ثبت می‌شود؛ P10 جاری retune نمی‌شود.
- اگر نتیجه Crisis Lab ناخوشایند باشد، آن نتیجه پنهان یا cherry-pick نمی‌شود؛
  evidence منفی نیز دارایی پژوهشی پروژه است.

### فاز اول — Research و Data Acquisition

از 2026-09-23:

1. ساخت یک **Versioned Crisis Event Catalog** با timestamp دقیق و بازه
   pre-event / event / aftermath، بدون استفاده از headline یا برچسبی که در لحظه
   تصمیم هنوز در دسترس نبوده است.
2. جمع‌آوری و manifest کردن داده تاریخی BTCUSDT و ETHUSDT با همان semantics
   point-in-time پذیرفته‌شده YATL؛ شروع با 15m / 1h / 4h و در صورت نیاز پژوهشی
   resolution دقیق‌تر در یک مسیر جدا.
3. ثبت provenance، source، timezone، range، completeness، gaps و SHA-256 برای هر
   dataset؛ هیچ فایل بحران بدون data-quality gate وارد evidence نمی‌شود.
4. پوشش چند نوع regime و crisis، نه فقط یک جنگ یا crash خاص: volatility shock،
   liquidity stress، trend reversal، gap-like move، prolonged drawdown، exchange/data
   outage و recovery.
5. دوره‌های تاریخی باید به research/development و **blind holdout** تقسیم شوند تا
   خود Crisis Lab به منبع overfitting تبدیل نشود.

### Crisis Museum اولیه

Catalog اولیه می‌تواند شامل دوره‌های بزرگی مانند COVID crash 2020، Terra/LUNA،
FTX، جنگ روسیه–اوکراین، بحران‌های بانکی، شوک‌های ژئوپولیتیکی خاورمیانه و دوره‌های
شدید انرژی/نفت باشد. تاریخ و window هر event فقط بعد از research منبع‌محور قطعی
می‌شود؛ نام یک رویداد به‌تنهایی evidence نیست.

### دو نوع آزمون

**A. Historical point-in-time replay**
- Strategy دقیقاً مانند زمان واقعی candle به candle جلو می‌رود.
- candle آینده، نتیجه بعدی event و label نهایی بحران برای decision engine نامرئی است.
- fee/slippage و risk controls حذف نمی‌شوند.

**B. Synthetic adversarial stress**
- gap / jump stress؛
- چندبرابرشدن slippage و spread؛
- liquidity degradation؛
- missing/stale data؛
- latency/disconnect/restart؛
- price shock در حالت open position؛
- برای open-position shock، state واقعی از یک Development entry مجاز گرفته می‌شود
  و سپس ماتریس ثابت -5% / -10% / -20% gap با normal / 2x / 5x slippage اجرا می‌شود؛
- repeated shock / whipsaw؛
- delayed regime recognition.

Synthetic stress برای سنجش robustness است و نباید به‌عنوان historical PnL واقعی
معرفی شود.

### خروجی اجباری هر Crisis Run

حداقل این metrics/evidence باید تولید شود:
- Net PnL after costs؛
- maximum drawdown و worst equity excursion؛
- capital survival / ruin flag؛
- peak exposure؛
- entryهای انجام‌شده در شرایط shock؛
- Kill Switch trigger و time-to-protection؛
- time-to-zero-exposure در صورت نیاز؛
- slippage sensitivity؛
- regime-classification lag / unknown duration؛
- false re-entry count پس از shock؛
- recovery time؛
- deterministic replay identity و canonical evidence digest.

### اصل Survival before Profit

در Crisis Lab موفقیت فقط «سودکردن در بحران» نیست. ترتیب اولویت:

1. **Survive** — نابودی سرمایه یا breach ایمنی رخ ندهد.
2. **Preserve Capital** — drawdown و exposure در محدوده قابل‌قبول باقی بماند.
3. **Recover Safely** — سیستم بدون حدس، state corruption یا ورود عجولانه بازیابی شود.
4. **Exploit Opportunity** — فقط پس از سه مورد بالا، سودآوری بحران ارزش ارزیابی دارد.

### Backlog پژوهشی وابسته به evidence

موارد زیر از پیش production requirement محسوب نمی‌شوند و فقط در صورت اثبات نیاز
در Crisis Lab بررسی می‌شوند:
- Market Shock Detector مستقل از Strategy با stateهای
  `NORMAL / ELEVATED / SHOCK / DISLOCATION`؛
- volatility/liquidity anomaly detection؛
- strategy-health / edge-decay monitoring؛
- capacity / market-impact model؛
- order-book / spread-aware stress data؛
- event-aware یا news/macro context فقط اگر point-in-time، قابل‌ممیزی و دارای
  incremental OOS value نسبت به baseline باشد.

**قانون:** هیچ feature بالا صرفاً به‌خاطر جذاب‌بودن یا یک failure منفرد وارد
production path نمی‌شود. ابتدا باید baseline comparison / ablation / holdout
evidence نشان دهد ارزش افزوده دارد.

### طراحی پژوهش تکمیلی و Anti-Overfitting Rules

#### Control Windows

هر Crisis Event باید همراه با windowهای کنترل ارزیابی شود؛ خود بحران به‌تنهایی
کافی نیست. حداقل مجموعه مقایسه:

- pre-event window؛
- crisis/event window؛
- aftermath/recovery window؛
- ordinary/unlabelled control windowهای از پیش ثبت‌شده؛
- strategy-active ordinary diagnostic برای دیدن رفتار واقعی ورود/خروج؛
- در صورت امکان random windows هم‌طول از همان market era.

برای این کار یک Development corpus پیوسته و جدا از holdout ثبت می‌شود:
BTCUSDT/ETHUSDT × 15m/1h/4h از **2019-12-18 تا 2023-01-01 UTC**؛ بازه
تحلیلی unbiased از 2020-01-01 شروع می‌شود و 14 روز اول فقط warm-up است.
این corpus شامل داده‌ی پیوسته بازار است، نه فقط بحران‌ها. انتخاب ordinary window
با تقویم و exclusion rule انجام می‌شود و حق استفاده از return، volatility،
trade count، PnL یا drawdown برای انتخاب window ندارد.

پروتکل canonical:
`docs/research/crisis-lab/CONTROL-WINDOW-PROTOCOL-v0.1.0.json`.

هشت control window سی‌روزه با قانون first-Monday quarterly و guard هفت‌روزه
اطراف تمام crisisهای ثبت‌شده، قبل از مشاهده outcome فریز می‌شوند. هیچ window به
خاطر no-trade یا نتیجه بد حذف نمی‌شود.

علاوه بر cohort unbiased، یک **strategy-active diagnostic** برای ساخت source
stateهای CRL-006 وجود دارد. V1 با state کاملاً پیوسته سه‌ساله اجرا شد و پیش از
مشاهده هر outcome مربوط به synthetic shock فقط 2 episode انتخاب کرد؛ این نتیجه
به‌عنوان feasibility evidence حفظ می‌شود و بازنویسی نمی‌شود. علت ساختاری مهم این
است که Kill Switch پذیرفته‌شده P4 عمداً latch می‌شود و در یک scan تاریخی طولانی
می‌تواند entryهای بعدی را برای مدت نامحدود veto کند.

برای sample-feasibility، V2 پیش از اجرای synthetic-shock outcomeها جداگانه
pre-register می‌شود: market history همچنان point-in-time و پیوسته است، اما
Paper/Risk/portfolio/active-setup در epochهای ثابت 30روزه که از شروع analysis pool
anchor شده‌اند reset می‌شوند. در هر epoch حداکثر یک episode قابل انتخاب است؛
حداقل فاصله 7 روز، ترتیب chronological + lexical و ممنوعیت استفاده از آینده/PnL/
exit quality حفظ می‌شود. این cohort فقط diagnostic/source-state harvesting است و
evidence بازده unbiased یا تغییر P4/P10 محسوب نمی‌شود.

همچنین historical replay از pre-event به crisis anchor بدون reset ادامه می‌یابد.
اگر position قبل از بحران باز شده باشد، همان position باید داخل shock حمل شود و
`position_at_event_anchor`، time-to-protection، time-to-zero-exposure،
Kill Switch، false re-entry و recovery ثبت شوند. اگر position باز نباشد، historical
entry جعل نمی‌شود؛ سناریوی کنترل‌شده‌ی «position باز سپس shock ناگهانی» در CRL-006
به‌صورت SYNTHETIC جداگانه اجرا می‌شود.

هدف این است که مشخص شود ضعف یا قوت مشاهده‌شده واقعاً به crisis/regime مربوط است
یا رفتار عمومی Strategy است. Control windowها قبل از دیدن نتیجه run نهایی انتخاب
و ثبت می‌شوند تا cherry-picking کاهش یابد.


##### گزارش پیوسته چندساله — Continuous Long-Horizon Replay

برای اینکه Strategy به‌خاطر کوتاه‌بودن control windowها یا resetهای مصنوعی
از فرصت‌های واقعی ورود/خروج محروم نشود، یک run مستقل و از پیش‌ثبت‌شده روی کل
Development corpus اجرا می‌شود:

`docs/research/crisis-lab/LONG-HORIZON-REPLAY-PROTOCOL-v0.1.0.json`.

بازه اصلی این run از **2020-01-01 00:00 UTC تا 2023-01-01 00:00 UTC** است و
داده 2019-12-18 تا شروع بازه فقط warm-up محسوب می‌شود.

قواعد:
- Strategy، Risk، Paper portfolio و active setup در تمام سه سال state پیوسته دارند؛
- در مرز روز/ماه/فصل/control window/crisis anchor reset انجام نمی‌شود؛
- سقف «اولین 10 entry» فقط برای diagnostic جداگانه است و روی گزارش سه‌ساله اعمال
  نمی‌شود؛ در long-horizon هر `ENTER_LONG` قانونی پردازش می‌شود؛
- هیچ threshold استراتژی یا Risk برای زیادکردن تعداد معامله شل نمی‌شود؛
- stop/target/EXIT_LONG، fee و slippage دقیقاً فعال باقی می‌مانند؛
- position می‌تواند طبیعی از بازار عادی وارد crisis شود و تا خروج واقعی ادامه یابد؛
- chunking فقط برای performance است و حق تغییر نتیجه ندارد؛
- گزارش علاوه بر PnL باید funnel فرصت را نشان دهد: decision → signal → risk allow/
  veto → fill → exit → completed trade، به‌همراه time-in-market، holding time،
  exit reason، drawdown و هزینه‌ها.

اگر نتیجه سه‌ساله نشان دهد frozen candidate بیش از حد کم‌معامله است، این موضوع
به‌عنوان evidence «trade starvation» ثبت می‌شود؛ خود همین run بعد از مشاهده
نتیجه retune نمی‌شود. هر candidate بازتر باید در CRL-008 به‌عنوان challenger
نسل بعدی جداگانه ثبت و روی evidence مستقل ارزیابی شود.

#### Baseline comparison

هر Crisis Run باید دست‌کم با دو baseline مقایسه شود:

1. **NO-TRADE / CASH baseline** — اگر هیچ معامله‌ای انجام نمی‌شد چه می‌شد؛
2. **BUY-AND-HOLD research baseline** — برای context، نه به‌عنوان target اجباری.

در صورت نیاز baselineهای ساده دیگر فقط با preregistration اضافه می‌شوند. سودکردن
YATL به‌تنهایی کافی نیست؛ باید معلوم باشد آیا همان سود با ریسک کمتر، drawdown کمتر
یا رفتار ایمن‌تر نسبت به baseline به دست آمده است. در بعضی crisisها نتیجه مطلوب
ممکن است عمداً **NO_TRADE / capital preservation** باشد.

#### Shock Severity Model

Crisisها فقط با نام خبری دسته‌بندی نمی‌شوند. یک severity model پژوهشی باید بر
اساس داده بازار تعریف شود تا شدت stress قابل مقایسه باشد. نسخه اولیه می‌تواند
سطوح `S1..S5` را از ترکیبی از معیارهای از پیش تعریف‌شده بسازد، مانند:

- magnitude و سرعت return shock؛
- realized volatility؛
- gap/jump behavior؛
- volume anomaly؛
- spread/liquidity degradation در صورت وجود داده معتبر؛
- cross-asset/correlation dislocation در صورت اضافه‌شدن داده پژوهشی.

Thresholdهای severity باید نسخه‌دار و قبل از استفاده تحلیلی فریز شوند. label خبری
به‌تنهایی severity evidence محسوب نمی‌شود.

#### Random Stress / Random Historical Windows

برای جلوگیری از selection bias، فقط crisisهای مشهور انتخاب نمی‌شوند. تعداد معناداری
random historical windows نیز با seed/selection rule ثبت‌شده replay می‌شوند.

هدف:
- مقایسه Crisis performance با توزیع رفتار عادی Strategy؛
- کشف failureهایی که به eventهای معروف وابسته نیستند؛
- جلوگیری از ساختن نتیجه دلخواه با انتخاب دستی چند بازه خاص.

Random-window selection، seed و window length باید canonical evidence داشته باشند.

#### Market Shock Detector — research gate before implementation

Market Shock Detector در شروع Crisis Lab **ساخته نمی‌شود**. ابتدا باید replayها
نشان دهند که baseline فعلی در shockها failure یا reaction lag معنادار دارد.

فقط در صورت وجود evidence روشن، یک detector مستقل از Strategy برای research باز
می‌شود، با stateهای پیشنهادی:

`NORMAL / ELEVATED / SHOCK / DISLOCATION`

این detector در نسخه پژوهشی اول حق BUY/SELL، quantity، RiskAuthorization یا
execution ندارد. حداکثر نقش قابل بررسی آن یک risk veto / new-entry block است و
ارزش افزوده‌اش باید با ablation و blind holdout ثابت شود.

#### News / Macro / AI deferral

نسخه اول Crisis Lab از price/volume/volatility و داده بازار معتبر شروع می‌کند.
News، geopolitical labels، macro feeds یا AI به‌طور پیش‌فرض وارد decision path
نمی‌شوند.

اضافه‌شدن آن‌ها فقط وقتی مجاز به research است که:
- timestamp point-in-time معتبر داشته باشند؛
- publication/availability lag معلوم باشد؛
- leakage از نتیجه نهایی event نداشته باشند؛
- baseline بدون آن‌ها موجود باشد؛
- incremental OOS/holdout value قابل اندازه‌گیری باشد.

AI همچنان analysis-only است و قانون `NO AI DIRECT EXECUTION` تغییر نمی‌کند.

#### Historical Strategy Lab — Historical Mastery + Forward Validation

از این checkpoint به بعد، داده تاریخی فقط برای «اثبات زنده‌ماندن» استفاده نمی‌شود.
YATL یک مسیر پژوهشی مستقل با نام **Historical Strategy Lab (HSL)** خواهد داشت که
هدفش یادگیری نظام‌مند از بازار گذشته و ساخت challengerهای سودآورتر است، بدون اینکه
P10 جاری یا Live gate را دور بزند.

اصل پژوهشی HSL:
- گذشته یک dataset آموزشی/آزمایشگاهی اصلی است؛ الگوهای رفتاری بازار می‌توانند در
  شکل‌های متفاوت تکرار شوند، بنابراین failureها و successهای تاریخی باید استخراج،
  طبقه‌بندی و دوباره‌آزمایی شوند.
- بهترشدن روی گذشته مطلوب است، اما نتیجه تاریخی به‌تنهایی مجوز آینده نیست؛ هر
  challenger بعد از Historical Mastery باید از walk-forward و سپس real-forward
  مستقل عبور کند.
- failure تاریخی حذف، پنهان یا cherry-pick نمی‌شود. هر failure باید به علت احتمالی
  مشخص مثل entry quality، regime mismatch، exit logic، risk veto، cost drag،
  volatility condition یا execution assumption متصل شود.
- هدف HSL فقط بیشینه‌کردن total return نیست؛ robustness، sample size، expectancy،
  profit factor، win rate، maximum drawdown، year-by-year stability، symbol
  stability، regime stability و dependence on a few outlier trades همزمان سنجیده
  می‌شوند.
- یک strategy که سودش فقط از چند معامله استثنایی آمده، حتی با total return بالا،
  از یک strategy پایدارتر با expectancy مثبت در تعداد بیشتری از معاملات متمایز
  گزارش می‌شود.

خانواده‌های اولیه challenger که می‌توانند مستقل و سبک آزمایش شوند:
- Trend Pullback؛
- Breakout / Trend Continuation؛
- Momentum continuation؛
- Volatility contraction → expansion؛
- Mean Reversion فقط در regime مناسب؛
- Support / Resistance reaction؛
- Trend + volume confirmation؛
- Multi-timeframe confirmation؛
- Adaptive stop / trailing stop؛
- Time-based exit.

قانون معماری: این تکنیک‌ها داخل یک Strategy واحد و شلوغ ادغام نمی‌شوند. ابتدا هر
کدام یک challenger مستقل با config/version/identity جدا است؛ فقط تکنیک‌هایی که
ارزش افزوده تکرارپذیر نشان دهند می‌توانند بعداً وارد ensemble یا regime router شوند.

##### Market Regime Library

HSL باید بازار را علاوه بر تاریخ، بر اساس regime نیز طبقه‌بندی کند. taxonomy اولیه:
`TREND_UP / TREND_DOWN / SIDEWAYS / HIGH_VOL / LOW_VOL / SHOCK / RECOVERY`.

برای هر challenger باید مشخص شود:
- در کدام regime edge مثبت دارد؛
- در کدام regime باید entry محدود یا صفر شود؛
- آیا تغییر regime باعث degradation ناگهانی می‌شود؛
- آیا exit/risk logic در shock و recovery همان رفتار مطلوب را دارد.

هدف نهایی regime library این است که YATL مجبور نباشد یک setup را در همه محیط‌ها
استفاده کند. در صورت وجود evidence کافی، یک research-only regime router می‌تواند
بین challengerهای از قبل پذیرفته‌شده انتخاب کند؛ این router حق bypass کردن Risk،
P10 یا Live gate را ندارد.

##### Walk-forward discipline

سه‌سال Historical Development باید به چند segment زمانی ترتیبی تقسیم شود.
پارامتر/منطق هر challenger فقط با segmentهای گذشته ساخته یا انتخاب می‌شود و segment
بعدی برای همان iteration نقش out-of-sample دارد. پس از هر fold، فقط evidence ثبت
می‌شود؛ outcome segment آینده نباید برای انتخاب همان fold استفاده شود.

نتیجه نهایی HSL سه سطح دارد:
1. **Historical Mastery** — تکنیک روی گذشته متنوع، هزینه‌دار و regime-aware مفید است؛
2. **Walk-Forward Proven** — edge فقط حاصل fit کردن کل تاریخ نیست؛
3. **Forward Candidate** — فقط challengerهایی که دو سطح قبلی را می‌گذرانند حق ورود
   به یک registration جدید real-forward را دارند.

P10 baseline جاری تغییر نمی‌کند. Historical Strategy Lab برای ساخت نسل بعدی
candidate است، نه برای بازنویسی evidence جاری یا بازکردن P11.

Checkpointهای اجرایی اولیه HSL:
- **HSL-001 — Walk-Forward Baseline Matrix:** مقایسه frozen `TREND_PULLBACK 1.0.0`
  و frozen `RANGE_BREAKOUT 1.0.0` روی پنج fold شش‌ماهه OOS از 2020-07 تا 2023-01،
  با BTCUSDT/ETHUSDT، quantity/fee/slippage یکسان و بدون P4 risk veto تا edge خود
  Strategy جداگانه اندازه‌گیری شود. state در مرز هر fold مستقل reset می‌شود ولی
  market history فقط point-in-time قابل مشاهده است.
- **HSL-002 — Risk Overlay Challenger:** فقط بعد از HSL-001، اثر P4 latched risk
  در برابر یک recovery/cooldown policy research-only بررسی می‌شود؛ P4/P10 واقعی
  تغییر نمی‌کند.
- **HSL-003 — Entry Quality / Regime Ablation:** filterهای volatility، confirmation
  و regime به‌صورت تک‌به‌تک ablation می‌شوند، نه با ترکیب post-hoc.
- **HSL-004+ — Technique Library:** Momentum، volatility expansion، mean reversion،
  support/resistance و تکنیک‌های استخراج‌شده از منابع خارجی هرکدام candidate
  مستقل می‌شوند.

پروتکل HSL-001 قبل از outcome run در
`docs/research/historical-strategy-lab/HSL-001-WALK-FORWARD-PROTOCOL-v0.1.0.json`
فریز می‌شود. gate اولیه آن شامل minimum trade count، net PnL و expectancy مثبت،
profit factor، پایداری foldها، وابستگی به outlier و maximum drawdown است.
PASS در HSL فقط research qualification است و هیچ مجوز P10/P11/Live ایجاد نمی‌کند.

##### External Research Intake — Video / Article / Transcript

منابع بیرونی مثل ویدیو، مقاله، کتاب و transcript می‌توانند وارد HSL شوند، اما
فقط به‌عنوان **idea source** و نه evidence اثبات‌شده. هر منبع باید به یک
research note قابل‌آزمون تبدیل شود که حداقل شامل نام تکنیک، منطق entry/exit،
timeframe، regime فرض‌شده، risk/stop/target، هزینه‌های لازم، assumptions و موارد
نامشخص باشد.

برای ویدیوها، subtitle/transcript با timestamp ترجیح داده می‌شود تا ادعاهای
مهم به بخش دقیق منبع متصل شوند. هیچ تکنیکی صرفاً به‌دلیل اعتبار گوینده یا نتیجه
نمایش‌داده‌شده وارد candidate نمی‌شود؛ ابتدا باید به rule قابل‌کدنویسی تبدیل،
سپس روی historical development، walk-forward و در صورت موفقیت real-forward
آزمایش شود. ایده‌های تکراری باید deduplicate شوند و نتیجه منفی نیز حفظ شود.

#### Shadow Challenger Track

Crisis Lab می‌تواند یک **Shadow Challenger Track** برای نسل‌های آینده Strategy
داشته باشد. challengerها فقط در research اجرا می‌شوند و هیچ اثر روی P10 جاری ندارند.

برای هر challenger:
- strategy/version/config قبل از evaluation فریز می‌شود؛
- historical development، holdout، crisis و random-window evidence جدا می‌ماند؛
- نتیجه با baseline فعلی و NO-TRADE/BUY-AND-HOLD مقایسه می‌شود؛
- هزینه، drawdown، sample size، crisis survival و robustness گزارش می‌شوند؛
- فقط candidateهایی که به‌صورت تکرارپذیر و خارج از نمونه ارزش افزوده نشان دهند
  می‌توانند وارد یک **future forward-validation registration** شوند.

هیچ challenger با نتیجه تاریخی خوب حق ورود مستقیم به P10 جاری یا P11 ندارد.

#### YATL Survival Certificate — internal technical artifact

پس از تثبیت Crisis Lab، برای هر نسخه واجد شرایط یک artifact داخلی و قابل‌ممیزی
با عنوان موقت **YATL Survival Certificate** تولید می‌شود. این گواهی تبلیغاتی یا
تضمین سود نیست؛ خلاصه فنی شواهد همان نسخه است.

حداقل محتوای certificate:
- YATL version / strategy version / risk-policy version؛
- dataset/event-catalog identities و SHA-256؛
- تعداد crisis windows، control windows و random windows؛
- تعداد synthetic stress scenarios؛
- severity coverage؛
- worst maximum drawdown؛
- worst equity excursion؛
- capital-ruin/survival result؛
- Kill Switch trigger count و reaction latency؛
- worst slippage stress survived؛
- false re-entry / out-of-regime violations؛
- recovery-time distribution یا summary؛
- baseline comparisons؛
- exact evidence index / canonical digest؛
- limitations و untested regimes.

Certificate فقط زمانی `PASS` یا مشابه آن می‌گیرد که معیارهایش قبل از run نهایی
ثبت شده باشند. هیچ certificate نباید profitability guarantee، Live authorization
یا investment claim تلقی شود.

### معیارهای پژوهشی برای نتیجه‌گیری

برای جلوگیری از اینکه Crisis Lab به مجموعه‌ای از نمودارهای جذاب تبدیل شود:

- هر claim باید به event/window/scenario evidence مشخص متصل باشد.
- نتیجه منفی حذف نمی‌شود.
- historical و synthetic evidence با هم مخلوط نمی‌شوند.
- development و blind holdout از هم جدا می‌مانند.
- تعداد crisisهای پاس‌شده به‌تنهایی معیار قدرت نیست؛ severity، drawdown، exposure،
  failure behavior و baseline comparison نیز لازم‌اند.
- یک Strategy که در crisis سود نمی‌کند اما سرمایه را حفظ می‌کند ممکن است بهتر از
  Strategy سودده با tail-risk شدید باشد.
- تغییر Strategy/Risk بعد از مشاهده failure باید نسخه جدید بسازد؛ نتیجه نسخه قدیم
  بازنویسی نمی‌شود.
- Crisis Lab برای **research acceleration** است، نه shortcut برای forward/live proof.

### رابطه با مسیر اصلی

`P10 Real Forward` پاسخ می‌دهد: **آیا baseline روی آینده‌ای که هنگام طراحی وجود
نداشت edge دارد؟**

`Crisis & Regime Stress Lab` پاسخ می‌دهد: **وقتی بازار از شرایط معمول خارج می‌شود،
آیا سیستم زنده می‌ماند و رفتار fail-safe دارد؟**

`P11 Tiny Live` در صورت بازشدن جداگانه پاسخ می‌دهد: **آیا assumptions اجرا با
fill، latency، reconciliation و پول واقعی برقرار می‌مانند؟**

هیچ‌کدام جای دیگری را نمی‌گیرد.

## نمای پیشرفت فعلی — 2026-09-20

جای فعلی پروژه: هشت فاز اول توسعه، یعنی P0 تا P7، در runtime پذیرفته و روی
`main` بسته شده‌اند. P7-001 تا P7-010 قرارداد analytics، ingestion read-only،
timeline، trade reconstruction، metrics، segmentation، quality gate، CLI/export،
adversarial matrix و independent final audit را تکمیل کردند. checkpoint نهایی P7
`93b9d87cf23fe8a52470c4a01b480b0935be87c3` است. Final-head Actions run
`35516951238` هر دو job را با **842/842** تست کامل و **17/17** تست متمرکز
P7-010 پذیرفت. chain-set پذیرفته‌شده BTCUSDT+ETHUSDT برابر
`76face2aa41fbea1dc0ae718964eb77b5990d258beb41312c74132c8bb5c1209` است.
P6-001 تا P6-010 قراردادهای analysis-only، evidence
point-in-time، baseline قطعی، request boundary، response schema، grounding،
journal trace، CLI محافظت‌شده، adversarial matrix و independent final audit را
تکمیل کردند. checkpoint نهایی P6
`f07f2209cac5b46be8f9d74da2d162925ed8ab65` است. P5-001 تا P5-010 Local Paper execution، journal،
state machine، fill/cost integration، atomic portfolio projection، startup
reconciliation، snapshot recovery، guarded operator CLI، adversarial matrix و
independent final audit را تکمیل کردند. checkpoint نهایی P5
`cd5ff5651e2d1df509dba6de8bc717a3ba7bf34f` است. P4-001 در checkpoint `be3c042` روی `main`
merge شده است. P4-002 محاسبه دقیق اندازه موقعیت را روی شاخه مستقل پیاده‌سازی و در
GitHub Actions تأیید و در checkpoint `bc2bd30` merge کرده است. P4-003 کنترل cash،
notional و exposure را روی PR #5 پیاده‌سازی کرد و در checkpoint `27dfd86` merge
شد. P4-004 مدیریت point-in-time وضعیت portfolio/session را روی PR #6 پیاده‌سازی
کرد و در checkpoint `99cd8d5` merge شد. P4-005 protective/cost gate را روی PR #7
پیاده‌سازی کرد و پس از قبولی runtime در checkpoint `41411ef` merge شد. P4-006
مدارشکن‌های زیان session، drawdown و باخت متوالی را پیاده‌سازی کرد و در checkpoint
`98320df` merge شد. P4-007 state machine قفل‌شونده Kill Switch را پیاده‌سازی کرد،
در final HEAD run `34754437777` پذیرفته شد و از PR #9 در checkpoint `e09dc0e`
merge شد. P4-008 adapter محافظت‌شده P3→P4→P2 را پیاده‌سازی کرد، final HEAD run
`34764434584` را گذراند و از PR #10 در checkpoint `b268fa7` merge شد. P4-009
ماتریس adversarial را پیاده‌سازی کرد، final HEAD run `34770395981` را گذراند و
از PR #11 در checkpoint `23b2f5b`
merge شد. P4-010 ممیزی مستقل نهایی را پیاده‌سازی کرده و GitHub Actions run
`34771596172` را با 401 تست و همه gateها گذراند. Final HEAD run `34771969717`
نیز هر دو job را پذیرفت و PR #12 در checkpoint `f3a5575` merge شد. P4 بسته شد و
در همان checkpoint، P5 هنوز باز نشده بود.

| معیار | انجام‌شده | باقی‌مانده | تفسیر صحیح |
|---|---:|---:|---|
| فازهای تحویل نرم‌افزاری P0 تا P9 | 9 از 10 | 1 فاز | **90% بر مبنای شمارش ساده فازها**؛ تخمین زمان یا حجم کار نیست |
| checkpointهای P8 | 10 از 10 | صفر | P8-001 تا P8-010 پذیرفته و روی `main` بسته شده‌اند |
| فازهای پیش از Forward Validation | P0 تا P8 | P9 | پس از آن P10 باید روی داده جدید اجرا و پذیرفته شود |
| مسیر Live | هیچ | P5 تا P10 و ممیزی‌های P11 | P11 همچنان LOCKED و مشروط به تأیید صریح است |

### کار باقی‌مانده تا نسخه آزمایشی نرم‌افزار

1. P9: Telegram minimum-sufficient و ایمن روی status/alertهای پذیرفته‌شده upstream.

### کار باقی‌مانده تا ارزیابی عملکرد

- **هدف اقتصادی P10:** مشخص شود آیا candidateهای YATL روی داده جدید و بعد از
  fee/slippage، با drawdown و ریسک کنترل‌شده، evidence کافی برای یک edge مثبت و
  قابل‌تکرار دارند یا نه.
- P10 باید روی داده جدید و بازه کافی انجام شود؛ بک‌تست ۲۰روزه فعلی برای اثبات edge
  کافی نیست. هر دو candidate فعلاً `INSUFFICIENT_EVIDENCE` هستند.
- معیار ثبت‌شده P3 حداقل ۱۸۰ روز ارزیابی، ۳۰ معامله برای هر نماد و ۶۰ معامله pooled
  است. رسیدن به این حجم نمونه تضمین قبولی یا سوددهی نیست؛ فقط اجازه ارزیابی معتبرتر می‌دهد.
- Net PnL پس از هزینه معیار اصلی اقتصادی است، اما به‌تنهایی کافی نیست؛ drawdown،
  stability across regimes، consistency، failure/recovery و risk controls نیز
  باید Gateهای از پیش‌ثبت‌شده را پاس کنند.
- اگر P10 edge قابل‌قبول را تأیید نکند، P11 باز نمی‌شود؛ پروژه به
  research/strategy iteration برمی‌گردد. در آن iteration، candlestick/price
  action، volume/order flow، derivatives، on-chain، macro/fundamental،
  news/sentiment یا AI فقط در صورتی اضافه می‌شوند که ارزش افزوده‌شان نسبت به
  baseline با شواهد خارج از نمونه قابل‌اندازه‌گیری باشد.
- Live بخشی از درصد تحویل نرم‌افزاری نیست. P11 تنها در صورت پذیرش P10، ممیزی امنیتی،
  آماده‌بودن حساب و تأیید صریح جداگانه بررسی می‌شود.

بنابراین گزارش کوتاه این است: **90% فازهای نرم‌افزاری P0 تا P9 بسته شده‌اند؛
P8-001 تا P8-010 runtime accepted و merge شده‌اند و P9 مرحله جاری است.** این عدد
پیشرفت مهندسی است، نه درصد آمادگی برای سود یا Live.

در گفت‌وگوی قبلی برای P10 بازه ۳۰–۶۰ روز واقعی بازار مطرح شده است؛ این تخمین است،
نه تضمین کافی‌بودن نمونه. تاریخ‌های قبلی پایان توسعه و شروع Live، تعهد اجرایی نیستند.
درصد وزنیِ زمان/حجم کار نداریم؛ درصد 90% بالا فقط شمارش ساده فازهای بسته‌شده است.
پیشرفت authoritative بر اساس تحویل و پذیرش runtime ثبت می‌شود.
تایم‌فریم‌های 4h/1h/15m و 5m برای اجرای دقیق‌تر، پیشنهاد قبلی‌اند؛ تصمیم نهایی داده/استراتژی در P1/P3 ثبت می‌شود.

## P0 — شواهد و موارد باقی‌مانده

| شناسه اصلی | موضوع | ارزیابی فعلی |
|---|---|---|
| YATL-P0-001 | Master Plan | PASS؛ این سند نسخه مرجع supersede‌شده است و محدودیت منبع را حفظ می‌کند |
| YATL-P0-002 | Project scaffold | PASS؛ مخزن محلی، package، tests، docs و fixture برای محدوده P0 اجرا شدند |
| YATL-P0-003 | Python environment | PASS؛ uv و اجرای تست‌ها تأیید شده |
| YATL-P0-004 | .gitignore | PASS؛ .env نادیده گرفته می‌شود |
| YATL-P0-005 | .env.example | PASS؛ نمونه بدون Secret در Git |
| YATL-P0-006 | Config architecture | PASS؛ testnet/OFF و میزبان/روش/endpoint دقیق fail-closed هستند |
| YATL-P0-007 | Trading basics onboarding | PASS؛ Entry/Stop/Target/Position Size/Risk/R:R در fixture و README تعریف و محاسبه شدند |
| YATL-P0-008 | Paper environment | PASS؛ fixture محلی قابل‌تکرار جای وابستگی UI به TradingView را برای Gate P0 گرفت |
| YATL-P0-009 | Binance Spot Testnet | اتصال عمومی و خواندن احرازهویت‌شده PASS |
| YATL-P0-010 | Manual BTC/ETH paper workflow | PASS؛ دو سناریوی آموزشی ثابت validate شدند؛ هیچ سفارش یا ادعای معامله بازار ثبت نشد |

شواهد فنی نهایی در `STATUS.md` ثبت شده‌اند: 28/28 تست، اجرای fixture محلی، ping زنده
Testnet و خواندن احرازهویت‌شده حساب SPOT در 2026-09-09. اجرای مستقل فرمان حساب توسط
کاربر نیز ثبت شده است. این اعداد معیار سود یا تکمیل ربات نیستند.

## P0 Closure — accepted 2026-09-09

P0 با workflow محلی و deterministic بسته شد. TradingView Paper از Gate اجباری P0
به ابزار اختیاری آموزشی supersede شد، زیرا fixture داخل مخزن قابل نسخه‌بندی، تست و تکرار است.
این تغییر به معنی اجرای معامله نیست: قیمت‌ها فرضی‌اند، وضعیت هر سناریو
`MANUAL_PAPER_FIXTURE` است و `exchange_order_submission=false` باید باقی بماند.

Gate مخزن محلی به عنوان PASS پذیرفته شد؛ remote خصوصی و CI به P1 engineering backlog
منتقل شدند و شرط ایمنی یا اجرای P0 نبودند. فایل Master Plan/ZIP اولیه قابل بازیابی نبود؛
این محدودیت منشأ حفظ شده و نسخه حاضر مرجع authoritative ادامه پروژه است.

هیچ endpoint سفارش یا مجوز TRADE اضافه نشد. موتور اجرای خودکار متعلق به P5 است.
برنامه و شواهد P1 و P2 در implementation planهای همان فاز و `STATUS.md` ثبت شده‌اند.
P3 تا checkpoint نهایی P2 باز نمی‌شود.

## روش ادامه کار

- همین مخزن محل واحد کد و این فایل مرجع ترتیب اجراست؛ STATUS.md شواهد واقعی اجرا را نگه می‌دارد.
- ابتدای هر بسته: فاز، شناسه کار و معیار پایان اعلام شود.
- انتهای هر بسته: تغییر، آزمون/شواهد، وضعیت پذیرش و فقط یک قدم بعدی ثبت شود.
- پیش از پذیرش یک فاز، فاز بعدی شروع رسمی نمی‌شود؛ نمونه‌های اولیه به معنای تکمیل فاز نیستند.
- پیشنهاد خارج از فاز در backlog ثبت می‌شود و جای کار جاری را نمی‌گیرد.
- تغییر دامنه یا ترتیب باید همراه دلیل در همین سند ثبت شود.
- برای هر قابلیت تحلیلی/استراتژیک جدید، سؤال اول «آیا احتمالاً performance
  out-of-sample را بعد از هزینه بهتر می‌کند؟» است، نه «آیا این تکنیک در بازار
  مشهور است؟». قابلیت بدون روش ارزیابی روشن وارد production path نمی‌شود.
- P8 Dashboard و P9 Telegram باید **minimum sufficient** باقی بمانند: فقط آن‌قدر
  ساخته شوند که مشاهده، audit، alert و کنترل ایمن برای P10 فراهم شود. featureهای
  تزئینی یا پیچیدگی‌ای که رسیدن به P10 را به تأخیر بیندازد در backlog می‌ماند.
- تکمیل P0 تا P9 «software delivery» است؛ موفقیت نهایی سیستم فقط با evidence
  اقتصادی P10 و سپس validation محدود P11 سنجیده می‌شود.

## اصلاح مسیر — 2026-09-07

پیشنهاد مستقیم «کنترل کیفیت کندل‌ها» در چت اجرای حساب، مربوط به P1 و زودهنگام بود.
قدم بعدی اصلاح شد: P0 manual Paper workflow → P0 final audit → P1.
هیچ فاز جدیدی در این نوبت اجرا یا پذیرفته نشده است.

## Supersession record — 2026-09-09

- `P0 IN PROGRESS` با شواهد runtime جدید به `P0 RUNTIME ACCEPTED` supersede شد.
- TradingView Paper برای Gate P0 با fixture محلی قابل‌تکرار جایگزین شد؛ TradingView حذف نشده و اختیاری است.
- workflowها تمرین محاسباتی هستند؛ معامله واقعی، Testnet order یا نتیجه سود/زیان ادعا نمی‌شود.
- سیاست بازار تثبیت شد: BTCUSDT + ETHUSDT، Spot، 1h اصلی، 4h regime، 15m context؛ 5m غیرفعال.
- P1-001 تا P1-008 به‌ترتیب در `38f4e78`، `bff4d24`، `c5d6f0e`، `0982f21`، `a02acb4`، `c63d88e`، `ab1fa24` و `fd7eb63` checkpoint شدند.
- P1-009 شش dataset واقعی ۳۰روزه با مجموع ۷۵۶۰ کندل بسته و health gate کامل را تأیید و در `fa4de2d` checkpoint کرد.
- P1-010 بازسازی تمیز و اجرای دوم idempotent، REST، WebSocket، health، manifest، SQLite و مرزهای امنیتی را تأیید کرد؛ P1 در runtime پذیرفته شد.
- P1 در checkpoint نهایی `4e77e34` بسته شد.
- P2 طبق `P2-IMPLEMENTATION-PLAN.md` باز شد؛ P2-001 قرارداد point-in-time و سیاست
  paper-only را پیاده‌سازی کرد. P3 باز نشده است.

## P2 closure record — 2026-09-10

- P2-001 تا P2-009 به‌ترتیب و با checkpoint تمیز اجرا شدند؛ آخرین checkpoint ورودی
  ممیزی نهایی `de63601` است.
- مجموعه نهایی **190 تست** را بدون خطا گذراند. loader و clock روی BTCUSDT و ETHUSDT،
  شش سناریوی واقعی، هزینه‌ها، حسابداری، معیارها و artifactها در runtime تأیید شدند.
- ممیزی مستقل ۲ نماد، ۶ سناریو، ۶ artifact و ۸ معامله را بازسازی کرد و digest ورودی
  و نتیجه را تطبیق داد.
- P2 در runtime پذیرفته شد. این پذیرش سوددهی استراتژی را ادعا نمی‌کند؛ P3 هنوز باز نشده است.

## P3 planning record — 2026-09-10

برنامه ترتیبی P3 در `P3-IMPLEMENTATION-PLAN.md` ثبت شد. این فاز دو candidate شفاف و
نسخه‌بندی‌شده را پس از ساخت قرارداد، featureها، regime و registry ارزیابی می‌کند. کیفیت
چارچوب از قدرت شواهد عملکرد جدا می‌ماند؛ داده ۳۰روزه فقط smoke/integration است و نتیجه
ناکافی بدون دست‌کاری پارامترها `INSUFFICIENT_EVIDENCE` ثبت می‌شود. P3-001 اکنون قرارداد
research-only سیگنال را پیاده‌سازی کرده و checkpoint آن در انتظار ثبت است.

## P3 closure record — 2026-09-12

- ممیزی نهایی مستقل، ماتریس هر دو candidate و هر دو نماد را برای چهار run بازسازی کرد و
  ۲۱ فایل شواهد، ۱۶ artifact موتور P2 و ۳۵ معامله بسته را byte-for-byte تطبیق داد.
- مجموعه کامل **283 تست** را بدون خطا گذراند. GitHub Actions run `34699232936`
  بازسازی dataset، دو اجرای مستقل candidate matrix، diff بازگشتی، ممیزی سوم و انتشار
  شواهد را با موفقیت تکمیل کرد.
- SHA-256 شاخص شواهد در هر سه اجرا
  `59f0af64843baeb2ecf593142e3247be190bb24c8768de80dd971bc677d8e92a`
  باقی ماند.
- هر دو candidate با دلایل از پیش منجمدشده `EVALUATION_WINDOW_TOO_SHORT` و
  `MINIMUM_TRADES_NOT_MET` در وضعیت **`INSUFFICIENT_EVIDENCE`** ماندند؛ هیچ پارامتر
  یا بازه‌ای پس از مشاهده نتیجه تغییر نکرد.
- پذیرش P3 فقط پذیرش runtime چارچوب است و ادعای سوددهی یا مجوز معامله نیست.
  P4 پس از merge نهایی P3 در checkpoint `90d5847` باز شد.

## P4 planning record — 2026-09-12

برنامه ترتیبی P4 در `P4-IMPLEMENTATION-PLAN.md` ثبت شد. P4 یک Risk Manager مستقل،
قطعی و fail-closed میان خروجی P3 و اجرای Paper آینده می‌سازد. سیاست اولیه
`P4_RISK_V1` ریسک هر معامله، exposure، زیان session، drawdown، تعداد باخت متوالی و
Kill Switch را از پیش محدود می‌کند. candidateهای فعلی با برچسب
`INSUFFICIENT_EVIDENCE` اجازه ورود نمی‌گیرند. P4-001 قرارداد و مرز ایمنی را بدون
network، credential، broker یا order endpoint پیاده‌سازی می‌کند.

P4-001 در GitHub Actions run `34701891824` با **293 تست** پذیرفته و در checkpoint
`be3c042` merge شد. candidateهای فعلی برای ورود رد شدند و خروج کاهنده ریسک زیر
Kill Switch مجاز ماند. P4-002 اکنون روی شاخه مستقل در حال اجراست.

P4-002 در GitHub Actions run `34702613220` با **305 تست** پذیرفته شد. sizing
هزینه‌محور و رو‌به‌پایین است؛ candidateهای ناکافی پیش از محاسبه مسدود می‌شوند.
P4-002 در checkpoint `bc2bd30` merge شد. P4-003 در GitHub Actions run
`34714934702` با **314 تست**، اسکن‌های ایمنی و بازپخش/ممیزی بدون تغییر داده‌های
پذیرفته‌شده قبول شد. runtime نتیجه عادی را `PASS/WITHIN_LIMITS` و کمبود cash را
`REJECT/CASH_INSUFFICIENT` ثبت کرد. PR #5 در checkpoint `27dfd86` merge شد.
P4-004 در GitHub Actions run `34717094100` با **326 تست**، runtime هش‌زنجیره‌ای
state، اسکن‌های ایمنی و بازپخش/ممیزی بدون تغییر داده‌های پذیرفته‌شده قبول و در
checkpoint `99cd8d5` merge شد. P4-005 در GitHub Actions run `34747781858` با
**338 تست**، protective runtime، اسکن‌های ایمنی و بازپخش/ممیزی بدون تغییر داده‌های
پذیرفته‌شده قبول و از PR #7 در checkpoint `41411ef` merge شد. P4-006 مدارشکن‌های
دقیق session loss، drawdown و loss streak را پیاده‌سازی کرد. GitHub Actions run
`34749628926` هر دو job، کل **352/352** تست، اسکن‌های ایمنی، runtime مدارشکن و
بازسازی/بازپخش/ممیزی بدون تغییر داده عمومی را پذیرفت. PR #8 در checkpoint
`98320df` merge شد. P4-007 Kill Switch با startup فعال، latch بدون reset خودکار و
reset دستی همراه شواهد clear جدید پیاده‌سازی شد. Final HEAD GitHub Actions run
`34754437777` هر دو job، کل **365/365** تست، اسکن‌های ایمنی، runtime state machine
و بازسازی/بازپخش/ممیزی بدون تغییر داده عمومی را پذیرفت. PR #9 در checkpoint
`e09dc0e` merge شد. P4-008 adapter محافظت‌شده P3→P4→P2 را پیاده‌سازی کرده است:
16 تست adapter، 98 تست متمرکز P4 و کل **381/381** تست سبز شدند. GitHub Actions run
`34764015703` هر دو job، اسکن‌های ایمنی، runtime adapter، بازسازی 6 dataset و 7,560
ردیف بسته، دو اجرای byte-identical و ممیزی مستقل P3 با 35 معامله را پذیرفت. هر دو
candidate همچنان `INSUFFICIENT_EVIDENCE` هستند. Final HEAD run `34764434584` نیز
سبز شد و PR #10 در checkpoint `b268fa7` merge شد. P4-009 اکنون 8 سناریوی
adversarial را برای هر دو نماد، مجموع 16 run، به‌صورت canonical و دو بار قابل
byte-compare پیاده‌سازی کرده است. Final HEAD run `34770395981` کل **392/392**
تست، همه gateهای ایمنی، دو اجرای byte-identical P4 و artifact هفده‌فایلی را پذیرفت.
index سناریوها
`56c945c38571af294bb44bfd7e788f314d9ee3e9fc76457c6bedb018daae0783` است. ممیزی
P3 بدون تغییر ماند و هر دو candidate همچنان `INSUFFICIENT_EVIDENCE` هستند. Final
HEAD run `34770395981` نیز سبز شد و PR #11 در checkpoint `23b2f5b` merge شد.
P4-010 ممیزی مستقل policy digest، بسته 17 فایلی، تصمیم‌های دقیق و بازسازی
byte-for-byte را پیاده‌سازی کرده است. GitHub Actions run `34771596172` کل
**401/401** تست، 118 تست متمرکز P4، بازسازی 6 dataset و 7,560 ردیف، دو ماتریس
byte-identical و ممیزی نهایی 16 run/17 file را پذیرفت. Policy SHA-256 برابر
`cb72fffad317e05638e60ad4a93b96bb78e356b52677330ecd6149095b65e2c7` است.
هر 10 checkpoint در runtime پذیرفته‌اند. Final HEAD run `34771969717` هر دو job
را گذراند و PR #12 در checkpoint `f3a5575` merge شد. بنابراین P4 بسته شد؛ در آن
checkpoint P5 باز نشده بود و هیچ مجوز TRADE یا Live ایجاد نشد.

## P5 planning and P5-001 accepted record — 2026-09-13/14

برنامه ترتیبی P5 در `docs/P5-IMPLEMENTATION-PLAN.md` پیش از کد ثبت شد. منابع
NautilusTrader، Jesse، Freqtrade، Hummingbot و CCXT با repository رسمی، license و
commit ثابت در `docs/OPEN-SOURCE-DESIGN-REFERENCES.md` فقط به‌عنوان ورودی طراحی
ثبت شدند؛ هیچ کد یا dependency از آن‌ها وارد پروژه نشد.

P5-001 قرارداد immutable اجرای Local Paper، policy ثابت و recovery readiness
fail-closed را پیاده‌سازی می‌کند. فقط `RiskAuthorization` کامل P4 قابل ارزیابی است.
startup پیش‌فرض exposure را می‌بندد، candidateهای فعلی با
`INSUFFICIENT_EVIDENCE` حتی در حالت ready بسته می‌مانند و مقدار fixture واجد شرایط
بدون تغییر از P4 عبور می‌کند. 13 تست متمرکز و کل **414/414** تست محلی پاس شدند؛
runtime decision SHA-256 برابر
`4de1cda05b4dd3778e5dd18e1b8f633b76e77e8ba0572e6d1e4ce2e819c51f05` است.
Compile، whitespace، lock و restricted-source scan پاس شدند؛ `uv.lock` بدون تغییر
است. Final-HEAD GitHub Actions run `34782981428` هر دو job را با **414/414** تست
کامل و **13/13** تست متمرکز گذراند. PR #14 با squash-merge در checkpoint
`557747194fe8cdda75704d1bc3d067901f184450` بسته شد؛ بنابراین P5-001 runtime
accepted and merged است؛ P5-002 پس از آن به‌صورت candidate باز شد. هیچ TRADE
permission، order endpoint، credential یا external transport ایجاد نشده است.

P5-002 یک journal تراکنشی SQLite فقط برای intentهای Local Paper پذیرفته‌شده اضافه
می‌کند. authorization SHA-256 هویت یگانه effect محلی است؛ retry همسان همان رکورد
تأییدشده را برمی‌گرداند و evidence متفاوت با authorization یکسان بدون mutation رد
می‌شود. JSON canonical سطح evidence است و byteهای فایل SQLite evidence قطعی محسوب
نمی‌شوند. 12 تست متمرکز و کل **426/426** تست محلی، rollback، uniqueness، reopen،
چهار تلاش هم‌زمان، schema drift و tamper detection را گذراندند. runtime یک effect
با quantity دقیق `18.894653`، intent SHA-256
`206920d659e27113762959457eb88e7124582eb365963694fbd70c56af4e620a` و evidence
SHA-256 `fd7aa4412b9c2fd6b10a5167465aae27bee0d515cf02cf8e7112ea435b881cb6`
ثبت کرد. Final-HEAD GitHub Actions run `34899971951` هر دو job را روی commit
`b498759` با **426/426** تست و runtime/safety gateها گذراند. PR #16 در checkpoint
`ab9d38a55688f772c2c7ca166584e0978fd6163d` squash-merge شد؛ بنابراین P5-002
runtime accepted and merged است و P5-003 پس از آن باز و تکمیل شد. درصد
کل همچنان 50% است و هیچ endpoint، credential یا TRADE permission اضافه نشده است.

P5-003 یک state machine صریح و فقط محلی برای intent پذیرفته‌شده P5-002 اضافه
می‌کند: `PENDING_LOCAL` → `ACTIVE_LOCAL` → `CANCELLED_LOCAL`. sequence/time هر
event صعودی، reasonها ثابت و eventها با SHA-256 زنجیره شده‌اند؛ event و projection
در یک transaction نوشته می‌شوند. transition ناممکن، skipped، duplicate، stale،
out-of-order یا tampered بدون mutation رد می‌شود. 14 تست متمرکز و کل **440/440**
تست محلی پاس شدند. runtime نهایی state SHA-256 برابر
`a5d3bbee2a561b5a195ef92e3c6c5a08f3442a2e91bc0fe2c25d54bbdbdb9796` و evidence
SHA-256 برابر
`6364285fae61a03cacde2f20bf5e42a0c6f4f7e674b387c76a68973dee8f25fe` ثبت کرد.
Implementation-head GitHub Actions run `35029425081` هر دو job را روی commit
`fbca913` گذراند. Final-HEAD run `35029938678` نیز هر دو job را روی commit
`f52b0ff` با **440/440** تست و runtime/safety/replay/audit gateها گذراند. PR #18
در checkpoint `c96293f038436258a30c9030cbce778750180c1f` squash-merge شد؛ بنابراین
P5-003 runtime accepted and merged است. Documentation closeout run `35031254350`
هر دو job را گذراند و PR #19 در checkpoint
`3d48ef42e0c97361b14c232fd3419ac550bede41` merge شد. P5-004 پس از آن به‌صورت
candidate باز شد.

P5-004 فقط intent بازسازی‌پذیر P5، رکورد durable متناظر و order state فعال را به
قراردادهای پذیرفته‌شده `PaperFillEngine` و `apply_costs` در P2 می‌دهد. P2 روی یک
engine موقت اجرا می‌شود و تنها پس از موفقیت کامل fill و cost commit می‌گردد؛ candle
یا cost policy نامعتبر state نیمه‌کاره باقی نمی‌گذارد. 15 تست متمرکز P5-004، کل
**54/54** regression متمرکز P5 و **455/455** تست کامل محلی پاس شدند. runtime دو
step و دو fill با quantity دقیق `18.894653` و total cost quote دقیق
`5.6967284321735` را replay کرد و evidence SHA-256 برابر
`504156f0bdd29bc276e404021deabd63518f5404c315ea13a3a281c23a9a3d79` ثبت شد.
Implementation-head GitHub Actions run `35056541281` هر دو job را روی commit
`f0e4f0f` گذراند. Final-HEAD run `35056981878` نیز هر دو job را روی commit
`b8f113e` با **455/455** تست و runtime/safety/replay/audit gateها گذراند. PR #20
در checkpoint `ce655d0535ce9b8bac22c6525e68e115ea8626f2` squash-merge شد؛ بنابراین
P5-004 runtime accepted and merged است و P5-005 unopened باقی می‌ماند. درصد کل
همچنان 50% است. هیچ persistence fill/portfolio، endpoint، credential، external
transport یا TRADE permission اضافه نشده است.

P5-005 هر fill هزینه‌گذاری‌شده P5-004 را به intent پایدار و digest وضعیت فعال سفارش
محلی متصل می‌کند و fill eventها همراه با projection کامل cash، asset، position و
realized PnL را در یک transaction ثبت می‌کند. پیش از هر write، تاریخچه کامل با
`PortfolioLedger` پذیرفته‌شده P2 بازپخش می‌شود؛ بنابراین arithmetic موازی ایجاد
نشده است. 16 تست متمرکز P5-005، کل **70/70** regression متمرکز P5 و **471/471**
تست کامل محلی پاس شدند. runtime دو fill را ثبت و duplicate را رد کرد، پس از reopen
به `FLAT` با cash دقیق `10013.1979245678265` و realized PnL دقیق
`13.1979245678265` رسید. projection SHA-256 برابر
`11af7bcf91cd47e1809562f1b04f28c714676643f81e99fbfcfd0546ba93df09` و evidence
SHA-256 برابر `03a52caa7914d711a4c8634dcf7f29b366cd1af9b98f0058cb9458f9252bd921`
است. Implementation-head GitHub Actions run `35142189459` هر دو job را روی commit
`f5f2392` با **471/471** تست و runtime/safety/replay/audit gateها گذراند. Final-HEAD
run `35142873676` نیز هر دو job را روی commit `919d331` گذراند. PR #22 در
checkpoint `39e83aedae4ec3b29345bb23ee121bb77e4bd8f8` squash-merge شد؛ بنابراین
P5-005 runtime accepted and merged است و P5-006 unopened باقی می‌ماند. درصد کل
همچنان 50% است. هیچ endpoint، credential، external transport یا TRADE permission
اضافه نشده است.


## P6 closure record — 2026-09-20

- P6-001 تا P6-010 به‌ترتیب روی شاخه/PR مستقل پیاده‌سازی، با matching final-head
  GitHub Actions پذیرفته و روی `main` squash-merge شدند.
- P6 analysis-only باقی ماند و هیچ executor import، RiskAuthorization mutation،
  quantity authority، credential، provider/network transport، trade permission یا
  order endpoint اضافه نکرد.
- P6-009 هشت سناریوی adversarial را برای BTCUSDT و ETHUSDT اجرا کرد؛ 16 run و
  17 فایل canonical evidence دو بار byte-identical بازتولید شدند. index SHA-256:
  `a5a09bdde1600c706bdc3665b46f334ae04fd5fc4fe364613cc9ed7913018524`.
- P6-010 ممیزی مستقل نهایی را روی همان evidence اجرا کرد و policy SHA-256
  `355ad5a2ed274878db4c9a56e15b14548ee6ba0c16016c7cc3b04b02120bbe44`
  و evidence manifest SHA-256
  `93dd09b73d439ed60b781f38783f2fb716689210ad66fb7ed5a395ed7b5b5f0f`
  را بازسازی و تأیید کرد.
- Final-head GitHub Actions run `35504753305` هر دو job را با **703/703** تست
  کامل و **13/13** تست متمرکز P6-010، source safety، exact outcomes و replay
  equality پذیرفت.
- PR #39 در checkpoint نهایی
  `f07f2209cac5b46be8f9d74da2d162925ed8ab65` squash-merge شد؛ P6 بسته است.
- هر دو candidate فعلی P3 همچنان `INSUFFICIENT_EVIDENCE` هستند. پذیرش P6
  ادعای سوددهی یا اجازه Live نیست.
- PAPER ONLY; ANALYSIS ONLY برای خروجی AI؛ LIVE_MASTER_LOCK=OFF; NO FUTURES;
  NO LEVERAGE; NO WITHDRAWAL API; NO TRADE PERMISSION; NO ORDER ENDPOINTS;
  NO AI DIRECT EXECUTION.

## P7 planning record — 2026-09-20

برنامه ترتیبی P7 در `P7-IMPLEMENTATION-PLAN.md` ثبت شد. P7 یک لایه
Journal / Analytics read-only و قابل ممیزی روی شواهد پذیرفته‌شده P5 و P6
می‌سازد. این فاز upstream journalها را تغییر نمی‌دهد، اجرای جدیدی ایجاد نمی‌کند و
نتیجه analytics را به‌عنوان مجوز معامله یا اثبات edge تفسیر نمی‌کند. P7-001
قراردادهای immutable analytics و policy مرزی را بدون network، credential،
provider یا execution capability تعریف می‌کند.


## P7 closure record — 2026-09-20

- P7-001 تا P7-010 به‌ترتیب روی شاخه/PR مستقل پیاده‌سازی، با matching final-head
  GitHub Actions پذیرفته و روی `main` squash-merge شدند.
- P7 فقط read-only analytics روی شواهد پذیرفته‌شده P5/P6 باقی ماند و هیچ
  execution/backtest/account/risk import، credential، network/provider transport،
  RiskAuthorization mutation، quantity authority، trade permission یا order
  endpoint اضافه نکرد.
- P7-008 export canonical و guarded CLI را برای مصرف downstream ساخت؛ export
  پذیرفته‌شده BTC fixture SHA-256
  `8e11935814a57389399eea4046beed2f98b7bb448b25465740ef868f7e4dc456`
  بود و source path/private input وارد خروجی نشد.
- P7-009 نه سناریوی adversarial را برای BTCUSDT و ETHUSDT اجرا کرد؛ 18 run و
  19 فایل canonical evidence دو بار byte-identical بازتولید شدند. index SHA-256:
  `f13a322e7071b48a8b05182fceee8024ee6d22d6b08a7b223d337e5f7850e60b`.
- P7-010 ممیزی مستقل نهایی را روی policy، evidence، هر دو analytics chain،
  metrics/segmentation/quality/export identity و source safety اجرا کرد. policy
  SHA-256:
  `534fb28e630a8bca4ccffd4c8ef572f4aac440d4a3d05de190cf70264ac9f4d9`.
  chain-set SHA-256 پذیرفته‌شده BTCUSDT+ETHUSDT:
  `76face2aa41fbea1dc0ae718964eb77b5990d258beb41312c74132c8bb5c1209`.
- Final-head GitHub Actions run `35516951238` هر دو job را با **842/842** تست
  کامل و **17/17** تست متمرکز P7-010، exact outcomes، replay equality، no-write
  و source safety پذیرفت.
- PR #50 در checkpoint نهایی
  `93b9d87cf23fe8a52470c4a01b480b0935be87c3` squash-merge شد؛ P7 بسته است.
- هر دو candidate فعلی P3 همچنان `INSUFFICIENT_EVIDENCE` هستند. پذیرش P7
  ادعای سوددهی، پیش‌بینی عملکرد یا اجازه Live نیست.
- PAPER ONLY; READ_ONLY_ANALYTICS; LIVE_MASTER_LOCK=OFF; NO FUTURES; NO MARGIN;
  NO LEVERAGE; NO SHORT; NO WITHDRAWAL API; NO TRADE PERMISSION;
  NO ORDER ENDPOINTS; NO AI DIRECT EXECUTION.

## P8 planning record — 2026-09-20

برنامه ترتیبی P8 در `P8-IMPLEMENTATION-PLAN.md` ثبت شد. P8 یک Dashboard
local/read-only روی **accepted/sanitized P7 export only** می‌سازد. Dashboard منبع
حقیقت جدید نیست و به P5/P6 journalها مستقیم وصل نمی‌شود. P8-001 قراردادهای
immutable view و policy مرزی را تعریف می‌کند؛ سپس export loader، overview،
trade table، performance/segmentation، quality diagnostics، renderer self-contained،
CLI guarded، adversarial matrix و independent final audit به‌ترتیب اجرا می‌شوند.
Dashboard هیچ credential، remote asset، provider/network transport، execution
capability، RiskAuthorization/quantity authority، trade permission یا order
endpoint ندارد و `INSUFFICIENT_EVIDENCE` را تغییر نمی‌دهد. P8 و سپس P9 عمداً
minimum-sufficient نگه داشته می‌شوند تا observability/alerting لازم را بدون
gold-plating فراهم کنند و مسیر ورود به P10 Forward/Paper Validation را بی‌دلیل
طولانی نکنند.

### P8-001 implementation candidate — 2026-09-20

روی branch `p8-001-dashboard-policy-contracts` از baseline
`9344d0d6a45ac77b5ea676a119b8cd7e782f00da`، policy ثابت
`P8_DASHBOARD_V1` و قراردادهای immutable/display-only برای source identity،
safety banner، overview، completed Paper trade rows، metrics، segmentation و
diagnostics پیاده‌سازی شدند. قراردادها canonical serialization/SHA-256 و
reconstruction سخت‌گیرانه دارند، schema smuggling را fail-closed رد می‌کنند و
`INSUFFICIENT_EVIDENCE` را قابل ارتقا نمی‌کنند. focused suite شامل 21 تست است.
این checkpoint هیچ P7 loader واقعی، renderer، network/provider transport،
execution/account/risk capability، credential، RiskAuthorization/quantity
authority، TRADE permission یا order endpoint اضافه نمی‌کند. P8-001 فقط پس از
matching exact Final-HEAD Actions و merge مستقل پذیرفته می‌شود؛ P8-002 قبل از آن
باز نیست.


## P8-001 acceptance / P8-002 candidate — 2026-09-20

P8-001 با PR #52، Actions `35522537152`، **863/863** تست کامل و **21/21**
تست focused پذیرفته و در checkpoint
`e675fd06461e9bbd168404eda3b42dd53d3ef2b8` روی `main` merge شد. policy
`P8_DASHBOARD_V1` local/read-only/display-only باقی ماند.

P8-002 روی branch `p8-002-p7-export-loader` فقط loader و provenance binding
برای **accepted/sanitized P7 export** را می‌سازد. ورودی به expected export digest
صریح bind می‌شود؛ canonical JSON، quality PASS، safety fields و segmentation
identity دوباره بررسی می‌شوند و symlink/oversize/tamper/schema-smuggling/secret
material fail-closed رد می‌شوند. این checkpoint هیچ overview projection، UI،
renderer، network/provider، credential، execution/account/risk capability،
RiskAuthorization/quantity authority، TRADE permission یا order endpoint اضافه
نمی‌کند. P8-003 تا پذیرش و merge مستقل P8-002 بسته می‌ماند.


## P8-002 acceptance / P8-003 candidate — 2026-09-20

P8-002 با PR #53، Actions `35523493929`، **886/886** تست کامل و **23/23**
تست focused پذیرفته و در checkpoint
`a9112a525e07de0e4b5cc8a02433f636246b683f` روی `main` merge شد. loader فقط
accepted/sanitized P7 export را با canonical/digest/provenance binding و بدون write
یا دسترسی مستقیم P5/P6 مصرف می‌کند.

P8-003 روی branch `p8-003-overview-projection` فقط overview ثابت
system/safety/quality را از همان boundary می‌سازد. source fields بدون تفسیر
اقتصادی جدید حفظ می‌شوند؛ `open_trade_count` و `snapshot_freshness` به دلیل
نبودن source کافی صریحاً `UNKNOWN` می‌مانند. هیچ health/readiness/profitability
یا live/trade permission جدیدی استنباط نمی‌شود. P8-004 تا پذیرش و merge مستقل
P8-003 بسته می‌ماند.


## P8-003 acceptance / P8-004 candidate — 2026-09-20

P8-003 با PR #54، Actions `35524331648`، **910/910** تست کامل و **24/24**
تست focused پذیرفته و در checkpoint
`2a74006dd42ba3755c4f0382847a165d7ef485ce` روی `main` merge شد. overview
ثابت 15-card فقط source fields پذیرفته‌شده P7 را نمایش می‌دهد و unknownها را
صریح نگه می‌دارد.

P8-004 روی branch `p8-004-completed-trade-table` فقط completed-trade table را
از accepted P7 `trade_metrics` می‌سازد. تمام numeric values به شکل exact source
strings حفظ می‌شوند؛ filter/sort/page bounded و deterministic است؛ open/incomplete
material وارد completed rows نمی‌شود. چون accepted P7 export فیلدهای execution-level
لازم برای `DashboardTradeRow` قدیمی (entry/exit time، quantity، price) را ندارد،
آن قرارداد frozen تغییر نمی‌کند و هیچ داده‌ای جعل نمی‌شود؛ یک metric-row contract
جدا برای داده‌های واقعاً موجود استفاده می‌شود. P8-005 تا پذیرش و merge مستقل
P8-004 بسته می‌ماند.


## P8-004 acceptance / P8-005 candidate — 2026-09-20

P8-004 با PR #55، Actions `35525173631`، **936/936** تست کامل و **26/26**
تست focused پذیرفته و در checkpoint
`6388eaab83bd756f26ed09a57ac3cc2015d48782` روی `main` merge شد. completed
trade table فقط exact accepted P7 metrics را با pagination/filter/sort محدود و
deterministic نمایش می‌دهد و open/incomplete را جدا نگه می‌دارد.

P8-005 روی branch `p8-005-performance-segmentation-views` performance aggregate
و segmentation views را از accepted P7 می‌سازد. aggregate با فرمول canonical P7
و Decimal precision دقیق **256** بازسازی و با SYMBOL segment روی
count/PnL/cost/outcomes reconcile می‌شود. returnهای high-precision بدون rounding
در `DashboardExactMetricValue` جدا نگه‌داری می‌شوند و قرارداد frozen P8-001
تغییر نمی‌کند. هر segmentation dimension باید memberهای خودش را دقیقاً یک‌بار
partition کند؛ هیچ cross-dimension sum، causality، extrapolation یا evidence
upgrade مجاز نیست. nullهای واقعی `UNAVAILABLE` می‌مانند. P8-006 تا پذیرش و
merge مستقل P8-005 بسته می‌ماند.


## P8-005 acceptance / P8-006 candidate — 2026-09-20

P8-005 با PR #56، Actions `35527548960`، **962/962** تست کامل و **26/26**
تست focused پذیرفته و در checkpoint
`23307f18588447e82f494d7c8ff461b3055eee05` روی `main` merge شد. performance
و segmentation view مقادیر exact P7 با precision 256 را حفظ می‌کند و بدون
cross-dimension double counting با SYMBOL segment reconcile می‌شود.

P8-006 روی branch `p8-006-quality-diagnostic-view` سه state صریح
`PASS/FAIL/ABSENT` دارد. فقط PASS از `LoadedP7Export` معتبر اجازه‌ی نمایش
analytics می‌دهد. FAIL فقط sanitized P7 quality report با `accepted_chain=null`
را می‌پذیرد و ABSENT نیز analytics را مسدود می‌کند. unknown diagnostic/check،
free-text اضافی، مسیر محلی، SQL/traceback، partial publication، safety weakening
یا evidence upgrade fail-closed است. P8-007 تا پذیرش و merge مستقل P8-006 بسته
می‌ماند.


## P8-006 acceptance / P8-007 candidate — 2026-09-20

P8-006 با PR #57، Actions `35529109856`، **992/992** تست کامل و **30/30**
تست focused پذیرفته و در checkpoint
`4ac351c384bebf5abd47ea1d6baee84f08a9bfc5` روی `main` merge شد. سه حالت
PASS/FAIL/ABSENT quality به‌صورت fail-closed بسته شدند و FAIL/ABSENT هیچ analytics
جزئی منتشر نمی‌کنند.

P8-007 روی branch `p8-007-deterministic-dashboard-renderer` فقط renderer محلی
in-memory را می‌سازد. PASS باید تمام projectionهای P8-003 تا P8-005 را به همان
export معتبر bind کند؛ FAIL/ABSENT هر analytics تزریقی را رد می‌کنند. HTML/CSS
کاملاً self-contained و deterministic است، dynamic text همیشه escape می‌شود،
CSP شبکه/script/font/image را می‌بندد، artifact حداکثر 4 MiB است و SHA-256 روی
view model و exact rendered bytes ثبت می‌شود. هیچ write/CLI/publication در P8-007
وجود ندارد؛ P8-008 تا پذیرش و merge مستقل P8-007 بسته می‌ماند.


## P8-007 acceptance / P8-008 candidate — 2026-09-20

P8-007 با PR #58، Actions `35529802550`، **1026/1026** تست کامل و **34/34**
تست focused پذیرفته و در checkpoint
`ce1d7f5d5a8ea150e2ec92d9011765cdc4d79487` روی `main` merge شد. renderer
کاملاً static/self-contained است، dynamic content را escape می‌کند، remote/script
capability ندارد و exact rendered bytes را hash می‌کند.

P8-008 روی branch `p8-008-guarded-dashboard-cli` سه command محلی
`validate/summary/build` را با expected export SHA اجباری می‌سازد. build به‌طور
پیش‌فرض overwrite را رد می‌کند و فقط با flag صریح می‌تواند فایل regular موجود را
جایگزین کند. انتشار از temp همان directory و به‌صورت atomic انجام می‌شود؛ خروجی
دوباره read-back و با length/SHA renderer تطبیق داده می‌شود. source قبل از publish
دوباره verify می‌شود و هیچ path/rejected input/traceback در JSON خطا بازتاب پیدا
نمی‌کند. P8-009 تا پذیرش و merge مستقل P8-008 بسته می‌ماند.


## P8-008 acceptance / P8-009 candidate — 2026-09-20

P8-008 با PR #59، Actions `35532396801`، **1070/1070** تست کامل و **44/44**
تست focused پذیرفته و در checkpoint
`20df93ead290d918ce55c93c5f3beab090a14f62` روی `main` merge شد. CLI محلی
validate/summary/build با expected export SHA اجباری، overwrite guard، atomic
same-directory publication، read-back verification، source immutability و خطاهای
redacted بسته شد.

P8-009 روی branch `p8-009-adversarial-dashboard-matrix` ماتریس ثابت **9×2**
را برای BTCUSDT و ETHUSDT اجرا می‌کند: export tampering، fabricated quality PASS،
evidence upgrade، cross-symbol row، duplicate trade، oversized input/output،
HTML/script injection، path/private smuggling و artifact mutation. هر scenario دو
بار replay می‌شود، evidence canonical/redacted تولید می‌کند و accepted P7 source
identity باید byte-for-byte و hash-for-hash ثابت بماند. workflow یک artifact مستقل
`p8-009-evidence` با 19 فایل منتشر می‌کند. P8-010 تا پذیرش و merge مستقل P8-009
بسته می‌ماند.


## P8-009 acceptance / P8-010 final audit candidate — 2026-09-20

P8-009 با PR #60، Actions `35533242415`، **1107/1107** تست کامل و **37/37**
تست focused پذیرفته و در checkpoint
`503e78dd6fb741f33dce838b70ff4c2c4fea3452` روی `main` merge شد. ماتریس
9×2 با 18 run و 19 evidence file پذیرفته شد و index SHA-256 روی
`38bc0e1eafedd44b1776ecec1a65fc48352a3155341dfca323641686739a8608`
فریز شد.

P8-010 روی branch `p8-010-independent-final-audit` ممیزی مستقل نهایی P8 بود.
Exact final candidate HEAD
`05038f9955425ddc05f552e84d71b5625663a43d` با GitHub Actions
`35534981625` هر دو job، **1139/1139** تست کامل و **32/32** تست focused را
گذراند. PR #61 Ready و سپس با expected-head دقیق squash-merge شد؛ checkpoint نهایی
P8 روی `main` برابر
`fe973e8f55f0fb1d7a76015a0e3d0d043e278f2e` است.

ممیزی مستقل 2 symbol، 9 scenario، 18 run، 19 evidence file و 2 HTML artifact را
با exact outcomes، replay equality، projection/renderer recomputation،
artifact verification، no-write و source safety پذیرفت. policy SHA برابر
`b4534112975f519714592ad7468c950eb6aa112f49b9aee80b1d15bf51804c2e`،
P8-009 index SHA برابر
`38bc0e1eafedd44b1776ecec1a65fc48352a3155341dfca323641686739a8608`،
combined accepted P7 export-set SHA برابر
`6f884ea930cd929292f000e8ada2da370b4428d7173a1f3d2423deacc6523439`
و renderer-set SHA برابر
`17f8526ba74ea73a7915b8978d098ab567fe1e19a145f03c625246916e22ff0c`
فریز شده‌اند. **P8 RUNTIME ACCEPTED / CLOSED** است.


## Economic objective clarification — 2026-09-20

هدف محصول به‌صورت صریح supersede/clarify شد: **YATL برای «داشتن تحلیل بیشتر» ساخته
نمی‌شود؛ برای یافتن و اعتبارسنجی edge اقتصادی قابل‌تکرار با ریسک کنترل‌شده ساخته
می‌شود.** تعداد تکنیک‌ها معیار موفقیت نیست. Technical/candlestick/price-action،
order-flow، derivatives، on-chain، fundamental/macro، news/sentiment و AI همگی
candidate input هستند، نه checklist اجباری.

P8/P9 scope باید minimum-sufficient بماند تا P10 سریع‌تر آغاز شود. در P10 معیار
اصلی اقتصادی Net PnL پس از fee/slippage روی داده جدید است، همراه با drawdown،
sample size، stability و سایر gateهای از پیش‌ثبت‌شده. اگر P10 edge قابل‌قبول را
تأیید نکند، P11 باز نمی‌شود و چرخه research/strategy iteration ادامه می‌یابد.


## P9 planning record — 2026-09-20

P8 در checkpoint
`fe973e8f55f0fb1d7a76015a0e3d0d043e278f2e` بسته شد و P9 طبق
`P9-IMPLEMENTATION-PLAN.md` باز شد. P9 عمداً minimum-sufficient است تا ورود به
P10 Forward/Paper Validation بی‌دلیل عقب نیفتد.

P9-001 روی branch `p9-001-notification-policy-contracts` فقط policy ثابت
`P9_NOTIFICATION_V1` و قراردادهای immutable/read-only برای accepted/sanitized
status/alert material را می‌سازد. این checkpoint کاملاً offline است:
`transport_mode=NONE`. هیچ Telegram API call، Bot token، Chat ID، inbound
command، callback، webhook/polling receiver، execution/live control،
RiskAuthorization/quantity authority، credential، TRADE permission یا order
endpoint اضافه نمی‌شود.

دسته‌های future-facing قرارداد شامل system status، data-quality alert، Paper
trade lifecycle، Paper signal/candidate، risk/drawdown alert، periodic summary و
P10 validation status هستند. همه notificationها `INFORMATION_ONLY`، Paper و
`INSUFFICIENT_EVIDENCE` باقی می‌مانند.

ترتیب P9 در شش checkpoint حداقلی ثبت شده است: policy/contracts، projection/
formatter، outbound-only Telegram transport، delivery guard/dedupe/retry،
guarded notifier + adversarial matrix و independent final audit.

## AI decision-support direction — 2026-09-20

اتصال آینده YATL به مدل‌های AI/OpenAI می‌تواند برای technical analysis،
candle/price-action interpretation، volume/order-flow، news/sentiment،
macro/fundamental context، regime analysis و proposalهایی مانند ENTER / SKIP /
WAIT / EXIT CANDIDATE بررسی شود؛ اما این قابلیت بخشی از بزرگ‌کردن P9 نیست.

قانون دائمی **NO AI DIRECT EXECUTION** است: AI هیچ order endpoint، trade
permission، RiskAuthorization mutation یا quantity authority دریافت نمی‌کند.
ابتدا baseline بدون AI در P10 روی new/forward data سنجیده می‌شود. ورود AI به
decision pipeline بعدی فقط زمانی توجیه دارد که incremental value آن نسبت به
baseline با evidence، ترجیحاً OOS/forward، تحت همان fee/slippage/risk controls
اثبات شود.

اصول اقتصادی حاکم بدون تغییرند: Profitability > Complexity؛ Evidence > Number
of analyses؛ OOS/Forward evidence > attractive backtest؛ Risk-adjusted
persistence > raw profit؛ One profitable edge > many unproven signals.


## P9-001 acceptance / P9-002 candidate — 2026-09-20

P9-001 با PR #62 و matching Actions `35536327437`، **1160/1160** تست کامل و
**21/21** تست focused پذیرفته و در checkpoint
`fa77126d22b8091eff5d355c8bd7cbd816901874` روی `main` squash-merge شد.
policy SHA-256 ثابت P9 برابر
`e5274de931300114fccffc772c971c99b5ba140a2632d98f897687e591be0a35` است.

P9-002 روی branch `p9-002-upstream-projection-formatter` فقط accepted/sanitized
upstream projection و deterministic formatter آفلاین را می‌سازد. scope عمداً به
sourceهای واقعاً موجود محدود است: P8 overview برای system status و P8 sanitized
quality FAIL برای data-quality alert. مقادیر ناموجود مانند open trade count و
snapshot freshness جعل نمی‌شوند و `UNKNOWN` باقی می‌مانند. PASS به alert تبدیل
نمی‌شود و ABSENT source ساخته نمی‌شود.

Formatter فقط plain text bounded با `PLAIN_TEXT_NO_PARSE_MODE` می‌سازد و هیچ
Telegram API call، token/chat ID، network transport یا command surface ندارد.
P9-003 تا پذیرش و merge مستقل P9-002 بسته می‌ماند.


## P9-002 acceptance / P9-003 candidate — 2026-09-21

P9-002 با PR #63 و matching Actions `35536906561`، **1175/1175** تست کامل و
**15/15** تست focused پذیرفته و در checkpoint
`7158fbc84287b9327116581d6877f17a68a294a4` روی `main` squash-merge شد.
projection/formatter همچنان بدون network و credential باقی ماند.

P9-003 روی branch `p9-003-outbound-telegram-transport` اولین network boundary
Telegram را اضافه می‌کند، اما فقط به‌صورت outbound/send-only. transport policy
مستقل `P9_TELEGRAM_SEND_MESSAGE_V1` فقط HTTPS POST به
`api.telegram.org:443/bot<token>/sendMessage` را اجازه می‌دهد. P9-001 contract
policy دست‌نخورده می‌ماند و خودش هیچ transport authority نمی‌دهد.

credentialها فقط در transport boundary از
`YATL_TELEGRAM_BOT_TOKEN` و `YATL_TELEGRAM_CHAT_ID` خوانده می‌شوند و در
repr/error/receipt ظاهر نمی‌شوند. redirect دنبال نمی‌شود، proxy path وجود ندارد،
TLS verification، timeout و response/request bound اجباری است و provider error
text به exception منتقل نمی‌شود.

CI P9-003 فقط mocked transport را اجرا می‌کند؛ real Telegram send بخشی از
acceptance evidence این checkpoint نیست. inbound command/update/webhook/polling
و هر execution/live/trade authority همچنان ممنوع است. P9-004 تا merge مستقل این
checkpoint بسته می‌ماند.


## P9-003 acceptance / P9-004 candidate — 2026-09-21

P9-003 با PR #64 و matching Actions `35553060397`، **1194/1194** تست کامل و
**19/19** تست focused پذیرفته و در checkpoint
`0d29710f320cec2dde6b7f585b8f62e496daae1e` روی `main` squash-merge شد.
transport policy SHA-256 برابر
`26428411750db1d2290e9d54fc60b831f5497077822e3e26be63a60acf9cc9d4`
فریز است. acceptance آن فقط با mock انجام شد و هیچ credential یا network call
واقعی وارد evidence نشد.

P9-004 روی branch `p9-004-delivery-guard` delivery identity، duplicate
suppression و retry محدود را اضافه می‌کند. حداکثر سه attempt وجود دارد؛ فقط
connection failure پیش از صدور request با backoff ثابت 1 و 2 ثانیه retry می‌شود.
خطای network در request/response به `TELEGRAM_NETWORK_AMBIGUOUS` تبدیل می‌شود و
برای جلوگیری از duplicate احتمالی هرگز retry نمی‌شود. 429 فقط با
`retry_after` عددی معتبر و در bound پذیرفته می‌شود. HTTP/provider/schema/config
failureهای دیگر نیز retry نمی‌شوند.

state تحویل immutable، canonical و strict-reconstructable است؛ duplicate با state
قبلی قبل از network متوقف می‌شود. persistence فایل/دیتابیس در این checkpoint
عمداً وجود ندارد و snapshot به caller واگذار می‌شود تا P9-005 مالک runner/
persistence boundary را مشخص کند. هیچ upstream mutation یا control loop ساخته
نمی‌شود و محدودیت‌های PAPER ONLY، LIVE lock، no trade/order و no AI direct
execution بدون تغییرند.


## P9-004 acceptance / P9-005 candidate — 2026-09-21

P9-004 با PR #65 و matching Actions `35553839765`، **1218/1218** تست کامل،
**23/23** focused P9-004 و **20/20** regression حمل‌ونقل P9-003 پذیرفته و در
checkpoint `1e3cba7a0aeb820c9d0a006cc38e053d12f83085` روی `main`
squash-merge شد. guard policy SHA-256 برابر
`6d180d548e5294cb7974ce4023ddff2f83bbbe2b707beb25cfdb76f81bb87533`
فریز است.

P9-005 روی branch `p9-005-guarded-runner-adversarial-matrix` یک runner
one-shot و noninteractive اضافه می‌کند. runner فقط یک notification canonical
با expected batch hash و symbol مشخص می‌پذیرد، source را read-only نگه می‌دارد و
فقط delivery-state خودش را atomically ذخیره می‌کند. duplicate قبل از credential
loading و قبل از network متوقف می‌شود و خروجی/exit codeها bounded و redacted
هستند.

adversarial matrix ثابت شامل ۸ سناریو برای هر یک از BTCUSDT و ETHUSDT است:
source tampering، evidence upgrade، command/authority injection، secret leakage،
URL/markup injection، duplicate delivery، cross-symbol material و
transport-response corruption. جمعاً ۱۶ run و ۱۷ evidence file canonical تولید
می‌شود و replay دقیقاً مقایسه می‌شود.

هیچ command ورودی Telegram، callback/webhook/polling، execution/live control،
RiskAuthorization mutation، quantity authority، trade permission، order endpoint
یا AI direct execution اضافه نمی‌شود. P9-006 تا merge مستقل این checkpoint
بسته می‌ماند.


## P9-005 acceptance / P9-006 candidate — 2026-09-21

P9-005 با PR #66، Final HEAD
`da9d347b50d09d823b3b1bed9791ebc8ba7ec5f2` و matching Actions
`35555391256` پذیرفته شد: **1241/1241** full suite، **13/13** focused runner
و **10/10** focused adversarial matrix. ماتریس ثابت ۸ سناریو × ۲ symbol =
۱۶ run / ۱۷ evidence file با SHA
`30a2c7ff705e9ecc3e83d5fa6b7ec38f9e432a6f6cd9a7f9ae531ca8b040c063`
byte-identical replay شد. PR #66 squash-merge و checkpoint accepted جدید روی
`main` برابر
`8614758fa8229c12ed297d75cf79adc86353c8e7` است.

P9-006 روی branch `p9-006-independent-final-audit` فقط ممیزی مستقل نهایی است.
این checkpoint سه policy digest، هویت source/message/batch/formatter/delivery
برای BTCUSDT و ETHUSDT، identity-set SHA، ماتریس P9-005 و source-safety را
مستقل recompute می‌کند. delivery برای هر دو symbol با sender mock دوباره اجرا
می‌شود و باید `DELIVERED -> DUPLICATE_SUPPRESSED` با دقیقاً یک send و receipt/
state identity ثابت بدهد. authority شبکه/environment باید فقط در
`transport.py` باقی بماند.

P9-006 هیچ capability جدید Telegram، command surface، state authority،
execution/live control، RiskAuthorization mutation، quantity authority،
trade permission، order endpoint یا AI direct execution اضافه نمی‌کند. P10 فقط
پس از PASS شدن exact Final HEAD و merge صریح این ممیزی می‌تواند باز شود.


## P9 final acceptance / P10-001 candidate — 2026-09-21

P9-006 با PR #67، Final HEAD
`f7ff546d7310876fd969f03c4f2d153137889de1` و matching Actions
`35566103007` پذیرفته شد: **1275/1275** full suite و **34/34** focused
independent-audit tests. delivery-replay-set نهایی برابر
`b0fe40c76b57034eb84568f9ee95bdd36558f8eae665c4f71fee14fd0a12ba30`
است. PR #67 squash-merge شد و P9 در checkpoint
`60d7e267fdd878f513afb2a8febb30d509b61314` بسته شد.

P10 اکنون economic-validation gate فعال پروژه است. برنامه ثابت آن در
`docs/P10-IMPLEMENTATION-PLAN.md` ثبت شده است.

P10-001 روی branch `p10-001-validation-policy-contracts` فقط preregistration
policy/contracts را فریز می‌کند. هفت بعد ارزیابی از قبل مشخص می‌شوند:
Net PnL after costs، drawdown، sample size، consistency، regime stability،
failure/recovery و risk controls. P4 limits بدون شل‌شدن به P10 منتقل می‌شوند.

این checkpoint عمداً هنوز candidate، thresholdهای عددی P10، forward window یا
new data را باز نمی‌کند. P10-002 باید candidate و gateهای اقتصادی عددی را قبل از
شروع window فریز کند. بنابراین نتیجه‌ای از P10-001 نمی‌تواند به‌عنوان edge،
profitability، Live readiness یا اجازه ورود به P11 تفسیر شود.


## P10-001 acceptance / P10-002 candidate — 2026-09-21

P10-001 با PR #68، Final HEAD
`ea6532c617b7c78137fc3c396055bc314e70e464` و matching Actions
`35573516304` پذیرفته شد: **1296/1296** full suite و **21/21** focused.
policy SHA برابر
`a85981d7ec835b584907bc89f3cff62b662a11d46c163900101ad46a213aa2c2`
و charter SHA برابر
`9d44d28de13445fcacbf5dad85ec0257ae65d198cf75ec26fb95c81fb1dffa71`
است. PR #68 squash-merge و checkpoint جدید `main` برابر
`326bc85b0c7cf2b456f4a51ad648330b8a9845a0` شد.

P10-002 baseline واحد را `TREND_PULLBACK/1.0.0` فریز می‌کند. انتخاب صرفاً به
خاطر feasibility جمع‌آوری sample است (31 معامله پذیرفته‌شده در P3 در برابر 4)
و نه return تاریخی؛ هر دو candidate قبلی همچنان `INSUFFICIENT_EVIDENCE` هستند.

Gateها قبل از بازشدن forward window ثبت می‌شوند: حداقل 90 روز، 60 معامله pooled،
20 معامله برای هر symbol، net return after costs حداقل +2%، profit factor حداقل
1.10، drawdown حداکثر 8%، حداقل 2 segment مثبت از 3، هیچ segment بدتر از -4%،
PnL خالص مثبت روی هر دو symbol، حداقل دو regime مشاهده‌شده و صفر entry خارج از
TREND_UP. failure/recovery و risk/safety violationها zero-tolerance هستند.

P10-003 تنها بعد از پذیرش مستقل P10-002 اجازه seal کردن window را دارد. تا آن
زمان هیچ forward data، economic result یا Live readiness وجود ندارد و P11 قفل است.


## P10-002 acceptance / P10-003 candidate — 2026-09-21

P10-002 با PR #69، Final HEAD
`8161f96dff29e076ef34cc8198073c18c42a647f` و matching Actions
`35574963153` پذیرفته شد: **1319/1319** full suite و **23/23** focused.
candidate SHA برابر
`64f2e116616f84e09fbf70a19977395eac99b16fe7e24a283dd53a8b0b84ac86`،
gate registry SHA برابر
`f8d706df050bb095219ae4b76e400eff73e1a7a6755c4a197d489b03117a3e95`
و registration SHA برابر
`0e4914e98754bceebf9dc99cc0ae7ab65b2b1a5b135c1fd9d736a071d843f14e`
است. PR #69 squash-merge و checkpoint جدید `main` برابر
`e327e2b99a0883fc096941db18b27e572561a7d1` شد.

P10-003 مرز no-peek را قبل از ورود هر داده جدید seal می‌کند. development
evidence پذیرفته‌شده P3 در 2026-09-09 00:00 UTC پایان می‌یابد و آخرین source
تاریخی پذیرفته‌شده P1 حداکثر تا 2026-09-09 16:15 UTC است. forward window از
**2026-09-22 00:00 UTC** شروع می‌شود و هر observation قبل از آن برای P10 مردود
است، حتی اگر بعداً دانلود شود.

حداقل 90 روز در **2026-12-21 00:00 UTC** کامل می‌شود، اما اگر gate نمونه
60 معامله pooled / 20 برای هر symbol هنوز کامل نباشد observation ادامه می‌یابد؛
candidate و thresholdها تغییر نمی‌کنند. P10-003 هنوز market values، PnL یا
economic verdict تولید نمی‌کند. P10-004 فقط پس از merge صریح این checkpoint
می‌تواند ingestion واقعی read-only را شروع کند. P11 قفل است.


## P10-003 acceptance / P10-004 candidate — 2026-09-21

P10-003 با PR #70، Final HEAD
`8f28c8a0cc984b1b03b45e2f8731dfcded8cfefb` و matching Actions
`35577086427` پذیرفته شد: **1341/1341** full suite و **22/22** focused.
window SHA برابر
`115f72be7941f682ccd28a70058677eba2ea24ee8ed44b5380510fe685022867`
است. PR #70 squash-merge و checkpoint جدید `main` برابر
`179d0bed3a1191dee21a654eb965a3b108328b90` شد.

P10-004 collector واقعی read-only بازار را روی stack پذیرفته‌شده P1 می‌سازد:
public Binance Spot REST بدون credential، canonical Candle و health gate فعلی.
داده فقط در SQLite مستقل P10 که به window SHA قفل شده ذخیره می‌شود؛ DB غیرخالی
بدون metadata P10 پذیرفته نمی‌شود تا هیچ store قدیمی/P1 به‌اشتباه mutate نشود.

هر run با Binance server time کار می‌کند و فقط candleهای کاملاً بسته بعد از
forward start را می‌پذیرد. snapshot شش dataset دقیق BTC/ETH × 15m/1h/4h را با
dataset/health SHA ثبت می‌کند و gap/duplicate/malformed/open/pre-window را
fail-closed رد می‌کند.

Acceptance CI این checkpoint با transport mock است، زیرا forward window تا
**2026-09-22 00:00 UTC** شروع نمی‌شود. بنابراین در 21 سپتامبر هیچ داده واقعی
P10 به evidence اضافه نمی‌شود. پس از merge، deployment عملی collector روی VPS
می‌تواند برای شروع window آماده شود؛ economic evaluation هنوز ممنوع و P11 قفل
است.


## P10-004 acceptance / P10-005 candidate — 2026-09-21

P10-004 با PR #71، Final HEAD
`11860e3d72473ba938ec17bccc8b209ac57e39aa` و matching Actions
`35578517306` پذیرفته شد: **1365/1365** full suite و **24/24** focused.
PR #71 squash-merge و checkpoint جدید `main` برابر
`41c5e315a9b0595423d9d20186cc9a038b3e6630` شد.

P10-005 runner از ابتدای forward prefix در هر run کاملاً replay می‌شود تا
restart یا crash نتیجه را تغییر ندهد. strategy/candidate تغییر نمی‌کند،
quantity جدید محاسبه نمی‌شود و مقدار research پذیرفته‌شده P3 یعنی `0.001`
ثابت است. P4 numeric policy فقط veto است و اجازه افزایش quantity ندارد.

به‌دلیل اینکه P4 RiskAuthorization برای entry به historical P3 qualification
وابسته است، P10 آن label را جعل نمی‌کند و RiskAuthorization جدید نمی‌سازد.
strategy evidence تا P10-010 همچنان `INSUFFICIENT_EVIDENCE` است.

هیچ historical warm-up قبل از window به runner داده نمی‌شود. 51 کندل بسته 4h
لازم است؛ بنابراین اولین decision قانونی زودتر از
**2026-09-30 12:00 UTC / 15:00 Istanbul** نیست. تا آن زمان collector می‌تواند
داده واقعی را جمع و quality-gate کند ولی runner باید warm-up ناکافی را fail-closed
گزارش دهد.

P10-005 همچنان Paper-only و بدون network/order/credential/AI execution است.
P10-006 بعد از merge صریح این checkpoint، economics را از evidence همین runner
محاسبه خواهد کرد. P11 قفل است.

## P10-005 acceptance / P10-006 candidate — 2026-09-21

P10-005 با PR #72، Final HEAD
`747a7b91b32147aeb809cb669a3bd98fc76c56a7` و matching Actions
`35580837803` پذیرفته شد؛ هر دو job PASS شدند. PR #72 با همان HEAD به روش
squash merge شد و checkpoint جدید `main` برابر
`62c55b675a8efb55c18d4a420a17d2b4a62d65ac` است.

P10-006 فقط economics توصیفی را از exact P10-005 evidence تولید می‌کند. قبل از
محاسبه، همان store/snapshot دوباره replay و تمام fillها با P2 recost می‌شوند؛
portfolio نهایی، fee، slippage، realized/unrealized PnL و trade lifecycle باید
دقیقاً reconcile شوند. مقدارهای undefined و sample ناکافی صریح باقی می‌مانند.

تجمیع BTC/ETH بر پایه جمع دو portfolio مستقل 10,000 quote انجام می‌شود؛ این
گزارش ادعای shared account ندارد. P10-006 هیچ verdict نهایی PASS/FAIL صادر
نمی‌کند، evidence را ارتقا نمی‌دهد و P11 را باز نمی‌کند. داده CI ساختگی است و
real forward evidence محسوب نمی‌شود.


## P10-006 acceptance / P10-007 candidate — 2026-09-21

P10-006 با PR #73 و exact Final HEAD
`21b904d2b025396784c5f86a7602c8be7c411b75` روی matching Actions
`35612692034` پذیرفته شد؛ هر دو job PASS، full suite برابر **1403/1403**،
focused P10-005 برابر **12/12** و focused P10-006 برابر **26/26** بود.
mocked economics report SHA-256:
`36f3e1dcb35d002b286c81b1b192056789e8294777ecc49f5d03d9affe469c4e`.
PR #73 با همان expected HEAD به روش squash merge شد و checkpoint جدید `main`
برابر `846be6190ce936425e546ecca7528fed979aab7f` است.

P10-007 threshold جدیدی تعریف نمی‌کند. همان هفت criterion ثبت‌شده در P10-002
را دقیقاً یک‌بار ارزیابی می‌کند. gateهای sample-dependent تا رسیدن به حداقل sample
`INSUFFICIENT_DATA` می‌مانند؛ breach قطعی drawdown، out-of-regime entry،
failure/recovery یا risk-control می‌تواند زودتر `FAIL` شود. سه segment زمانی
بدون cherry-pick محاسبه می‌شوند، regime از همان point-in-time forward store
بازسازی می‌شود و هر Kill Switch latch بدون clear + manual-reset evidence unresolved
است. `PASS_CANDIDATE` همچنان Paper-only است، evidence را ارتقا نمی‌دهد و P11
را باز نمی‌کند.


## P10-007 acceptance / P10-008 candidate — 2026-09-21

P10-007 با PR #74 و exact Final HEAD
`d0b51c50896ce6bff00d1fad1e6f7d37b25485f9` روی matching Actions
`35620212752` پذیرفته شد؛ هر دو job PASS، full suite برابر **1428/1428**،
focused P10-005 برابر **12/12**، focused P10-006 برابر **26/26** و focused
P10-007 برابر **25/25** بود. mocked gate disposition برابر
`INSUFFICIENT_DATA` و report SHA-256 برابر
`a7761f5ee0b9c6a61626dae15dc93bc430c0f96387189e8d39e85f22cb0bdd2b` بود.
PR #74 با همان expected HEAD به روش squash merge شد و checkpoint جدید `main`
برابر `4bd187fe5780c1f672a6d386887fcf6fb0bc82c4` است.

P10-008 candidate/gate/window را تغییر نمی‌دهد و هیچ network collection یا execution
authority اضافه نمی‌کند. CLI فقط status/summary/export محلی و bounded ارائه می‌دهد،
upstream P10 evidence را read-only snapshot می‌کند، وجود WAL/SHM فعال را fail-closed
رد می‌کند و replay/economics/gate را فقط روی temporary copy اجرا می‌کند. export
canonical SHA-256 دارد، atomic و strict no-overwrite است، path/secret را echo نمی‌کند،
`INSUFFICIENT_EVIDENCE` را ارتقا نمی‌دهد و P11 را بسته نگه می‌دارد.


## P10-008 acceptance / P10-009 candidate — 2026-09-21

P10-008 با PR #75 و exact Final HEAD
`a26d7a96c6c9ffcacbdfa81ac195f6d53562f322` روی matching Actions
`35628760039` پذیرفته شد؛ هر دو job PASS، full suite برابر **1455/1455** و
focused P10-008 برابر **27/27** بود. canonical audit SHA-256 برابر
`1c11ea83affa5dd8d55644a573e765bb83435d0be6e39135384c9d79dda16be8`
بود. PR #75 با همان expected HEAD squash-merge شد و checkpoint جدید `main`
برابر `24190b29e769212bbc1a2cee376cc6fc6fc0ec88` است.

P10-009 فقط adversarial validation evidence تولید می‌کند. همه attackها دوباره
re-sign می‌شوند تا ردشدن متکی به stale outer hash نباشد. accepted candidate،
gate registry، sealed window، provenance، Paper/economics/gate identities باید
در تمام سناریوها ثابت بمانند. هیچ network، credential، order، sizing، threshold
tuning یا Live authorization اضافه نمی‌شود و P11 بسته می‌ماند.


## P10-009 acceptance / P10-010 candidate — 2026-09-21

P10-009 با PR #76 و exact Final HEAD
`1e25910851d2672e8fcd5e76a89a9ea043b20ac3` روی matching Actions
`35631525673` پذیرفته شد؛ هر دو job PASS، full suite برابر **1476/1476** و
focused P10-009 برابر **21/21** بود. adversarial matrix شامل 11 attack re-signed
بود و matrix SHA-256 برابر
`e9b36b749519c4793b94913e3d40c56aaf3aa60a82d42138cc17683568528b93`
ثبت شد. PR #76 با همان expected HEAD squash-merge شد و checkpoint جدید `main`
برابر `7baf3c7000bb66d406fa8348692f73d9907d3f15` است.

P10-010 کل زنجیره P10 را مستقل از artifactهای میانی بازسازی می‌کند، P10-009
evidence را byte-for-byte با recomputation تطبیق می‌دهد و فقط یکی از سه disposition
`INSUFFICIENT_DATA` / `FAIL` / `PASS_CANDIDATE` را می‌پذیرد. حتی
`PASS_CANDIDATE` فقط اجازه بررسی جداگانه P11 را می‌دهد؛
`p11_unlocked=false` و Live authorization همچنان false می‌ماند.

**Engineering completion is not economic acceptance.** روی CI mocked فعلی disposition
باید `INSUFFICIENT_DATA` بماند. پذیرش اقتصادی واقعی فقط از forward evidence
واقعی و gateهای از قبل ثبت‌شده حاصل می‌شود.


## P10-010 acceptance / operational collection — 2026-09-21

P10-010 با PR #77 و exact Final HEAD
`5943265e22a8a3ddbec97c3a924d7febf7f5c2da` روی matching Actions
`35639615088` پذیرفته شد؛ هر دو job PASS، full suite برابر **1502/1502** و
focused P10-010 برابر **26/26** بود. final mocked disposition برابر
`INSUFFICIENT_DATA`، `p11_unlocked=false` و `live_authorized=false` باقی
ماند. PR #77 squash-merge شد و checkpoint جدید `main` برابر
`ed7e7e705dc71dfc6a67d5b052d6facc08ee5e86` است.

مرحله بعدی P11 نیست. ابتدا real forward market data از پنجره sealed P10 روی VPS
جمع‌آوری می‌شود. collector عملیاتی فقط Binance Spot public REST را می‌خواند،
DB اختصاصی P10 و canonical snapshot را به‌روزرسانی می‌کند و هیچ credential،
account access، order endpoint یا Live authority ندارد. runbook:
`docs/P10-OPERATIONS.md`.


## Historical Strategy Lab checkpoint — 2026-09-25

این track برای قوی‌کردن یادگیری از تاریخ در کنار P10 forward validation ایجاد شد؛
جایگزین P10 نیست و evidence تاریخی و forward عمداً با هم مخلوط نمی‌شوند.
هدف تجاری نهایی همچنان یافتن edge اقتصادی قابل تکرار است، نه صرفاً زیادکردن
تعداد تحلیل‌ها یا محدودکردن سیستم تا جایی که هیچ معامله‌ای رخ ندهد.

CRL historical acquisition و quality work منبع دادهٔ پذیرفته‌شده HSL است.
HSL اجازه دارد تکنیک‌های متفاوت trading را روی گذشته به‌صورت preregistered،
point-in-time و بدون hindsight tuning مقایسه کند. رویدادهای کلان/بحرانی نیز در
Crisis Lab به‌عنوان stress context نگه داشته می‌شوند، نه به‌عنوان مجوز cherry-pick.
منابع آموزشی خارجی مثل transcript ویدیوها می‌توانند بعداً candidate مستقل بسازند؛
هیچ ادعای منبع خارجی مستقیماً به strategy production یا execution تبدیل نمی‌شود.

### HSL-001 — Walk-Forward Baseline Matrix — ACCEPTED

HSL-001 با PR #109 و Final HEAD
`1ead2cbdc74706d17e3d0ced76ad8f21b9b03b8a` پس از PASS شدن هر دو job
`unit-and-safety` و `accepted-public-data` squash-merge شد. checkpoint جدید
`main` برابر `e5ee1c291f5a715f5bd10311e86980e778ee439f` است.

پروتکل قبل از outcome در
`docs/research/historical-strategy-lab/HSL-001-WALK-FORWARD-PROTOCOL-v0.1.0.json`
فریز شد. دو strategy از قبل frozen یعنی `TREND_PULLBACK/1.0.0` و
`RANGE_BREAKOUT/1.0.0` روی BTCUSDT و ETHUSDT در پنج OOS fold شش‌ماهه از
2020-07 تا 2023-01 با expanding history مقایسه می‌شوند. quantity برابر 0.001،
fee برابر 10 bps، adverse slippage برابر 5 bps و execution برابر
NEXT_PRIMARY_OPEN_LONG_ONLY_SPOT است. state در مرز هر fold reset می‌شود ولی
market history فقط point-in-time در دسترس strategy است. source gapهای پذیرفته‌شده
CRL-003 interpolate نمی‌شوند.

HSL-001 عمداً P4/P10 risk veto را اعمال نمی‌کند تا edge خود signal/exit جدا از
risk overlay اندازه‌گیری شود. gate پژوهشی از قبل شامل حداقل sample، net PnL و
expectancy مثبت، profit factor، OOS-cell stability، outlier dependence و maximum
drawdown است. PASS احتمالی فقط `QUALIFIED_HSL_RESEARCH` است و هیچ P10/P11/Live
authorization ایجاد نمی‌کند.

### HSL-002 — Risk Overlay Challenger — ENGINEERING / CI ACCEPTED

HSL-002 با PR #110، Final HEAD
`9b25b85ce79b25436b174bfa5e84be1a6e7e829c` و matching Actions
`36174550993` پذیرفته شد؛ هر دو job `unit-and-safety` و
`accepted-public-data` PASS شدند. PR #110 squash-merge شد و checkpoint جدید
`main` برابر `cb930e3b44f32be883a07fba855e83c9cae8fd35` است.

پروتکل:
`docs/research/historical-strategy-lab/HSL-002-RISK-OVERLAY-PROTOCOL-v0.1.0.json`

HSL-002 یک سؤال محدود دارد: آیا رفتار risk overlay فعلی در historical OOS،
فرصت‌های مفید را بیش از حد مسدود می‌کند، و آیا recovery/cooldown از پیش تعریف‌شده
می‌تواند بدون افزایش drawdown ناموجه، participation اقتصادی بهتری بدهد؟

Control = P4-style latched behavior. Challenger = recovery/cooldown research-only:
drawdown breach تا انتهای OOS fold hard-latched می‌ماند و هرگز auto-reset نمی‌شود؛
session-loss فقط تا اولین UTC session بعدی entry را block می‌کند؛ loss-streak breach
برای 24 decision واجد شرایط یک‌ساعته entry را block می‌کند. بعد از پایان cooldown،
فقط اگر portfolio flat باشد، session-loss block فعال نباشد و drawdown زیر hard limit
باشد، counter پژوهشی entry-eligibility صفر می‌شود؛ streak واقعی برای telemetry حفظ
می‌شود. این reset فقط در challenger پژوهشی است و P4/P10 واقعی را تغییر نمی‌دهد.

این acceptance مربوط به runner، protocol، tests و safety boundary است. **Outcome
تاریخی HSL-002 هنوز صرفاً با merge/CI اثبات نشده است** و فقط پس از اجرای runner روی
corpus پذیرفته‌شده و ثبت artifact canonical می‌تواند نتیجه اقتصادی پژوهشی بدهد.

### HSL-003 — Entry Quality / Regime Ablation — ENGINEERING / CI ACCEPTED

HSL-003 با PR #111، Final HEAD
`e1a3a9b56f6fad687d715ba3309238927a837e82` و matching Actions
`36179547969` پذیرفته شد؛ هر دو job `unit-and-safety` و
`accepted-public-data` PASS شدند. PR #111 squash-merge شد و checkpoint جدید
`main` برابر `732542a39d9f4881f710174b4958cb583f3117a3` است.

پروتکل:
`docs/research/historical-strategy-lab/HSL-003-ENTRY-REGIME-ABLATION-PROTOCOL-v0.1.0.json`

HSL-003 اثر entry filterهای موجود را **تک‌به‌تک** اندازه می‌گیرد و ترکیب post-hoc
یا parameter search ممنوع است. برای هر دو strategy، confirmation و TREND_UP
entry gate جداگانه ablate می‌شوند. `RANGE_BREAKOUT/1.0.0` علاوه بر این یک
volatility-normalized extension gate واقعی دارد؛ `TREND_PULLBACK/1.0.0`
volatility-entry filter مستقل ندارد و هیچ فیلتر مصنوعی برای آن ساخته نشد.

این acceptance مربوط به preregistration، runner، tests و safety boundary است.
Outcome تاریخی HSL-003 فقط پس از اجرای canonical runner روی corpus پذیرفته‌شده
و ثبت artifact معتبر قابل تفسیر اقتصادی است.

### HSL-004A — Momentum Technique Candidate — ACTIVE / PREREGISTERED

branch فعال:
`hsl-004a-momentum-technique`

پروتکل:
`docs/research/historical-strategy-lab/HSL-004A-MOMENTUM-PROTOCOL-v0.1.0.json`

Technique Library به PRهای کوچک و مستقل شکسته می‌شود تا scope creep کنترل شود.
HSL-004A اولین candidate مستقل است: `MOMENTUM_24H_LONG/0.1.0`.
پارامترها قبل از outcome فریز شده‌اند: 24h return حداقل +3٪، close بالای EMA(24)،
RSI(14) بین 55 و 75، ATR(14) برای stop برابر 1.5 ATR، target برابر 2R و
momentum-reversal exit وقتی 12h return به صفر یا پایین‌تر برسد.

HSL-004A دقیقاً همان پنج OOS fold، BTC/ETH، quantity=0.001، fee=10 bps،
slippage=5 bps، next-primary-open Spot semantics و point-in-time history HSL-001
را استفاده می‌کند. parameter search و outcome-driven retuning ممنوع‌اند.
BUY-AND-HOLD و cash/no-trade benchmark گزارش می‌شوند اما برای انتخاب پارامتر
استفاده نمی‌شوند و outperform کردن buy-and-hold شرط qualification نیست.

PASS احتمالی فقط به معنی `QUALIFIED_HSL_RESEARCH` و شایستگی برای پژوهش مستقل
بعدی است؛ strategy production، P4، P10، P11 و Live را تغییر نمی‌دهد.

### HSL-004A — Momentum Technique Candidate — ENGINEERING / CI ACCEPTED

HSL-004A با PR #112، Final HEAD
`80ffa274d640987fe26139032eaa0b18e5892c29` و matching Actions
`36183422247` پذیرفته شد؛ هر دو job `unit-and-safety` و
`accepted-public-data` PASS شدند. PR #112 squash-merge شد و checkpoint جدید
`main` برابر `be72a45b5960e58ea3cd95ecca0e14046d5e6570` است.

این acceptance مربوط به protocol، runner، tests و safety boundary است و به‌تنهایی
هیچ outcome اقتصادی برای Momentum اثبات نمی‌کند.

### HSL-004A — Canonical Historical Outcome — NOT QUALIFIED — 2026-09-26

پس از کشف دو خطای عددی در اولین replay واقعی، PR #114 برای اصلاح
LongSetup decimal contract و هم‌ترازکردن closed-trade accounting با
`DECIMAL_PRECISION=256` باز شد. Diagnostic مستقل با precision=256 ریشه خطای
accounting را تأیید کرد و Final HEAD
`4ccf16e5c809bfb32043d26e6cdac52aa34479a1` هر دو GitHub Actions job
`accepted-public-data` و `unit-and-safety` را PASS کرد. این اصلاح فقط
implementation/accounting correctness است؛ strategy version، پارامترها، folds،
fee/slippage، qualification gate و P10 تغییر نکردند.

Canonical HSL-004A replay روی همان Final HEAD و quality manifest پذیرفته‌شده
CRL-CONTROL-DEV-POOL-001 اجرا شد. artifact immutable:

`historical-strategy-lab/technique-library/momentum-v0.1.0/hsl-004a-19ba7a4fde6e14a50d8b705d.json`

SHA-256 فایل:
`19ba7a4fde6e14a50d8b705dfc2278efd9f0bc84aa385ff0137787f2daa17981`

result SHA-256:
`0be5bd76b75565f6ee60466c36bf0775ae5757849b6c7bdc2b04bdfeb2ad6829`

Outcome رسمی روی 10 OOS cell و 1,357 معامله:
- BTCUSDT: 552 trade؛ ETHUSDT: 805 trade؛
- wins=423، losses=934، win rate≈31.17٪؛
- total net PnL after costs≈-56.639451 quote؛
- expectancy≈-0.041747 quote/trade؛
- profit factor≈0.6951؛
- positive OOS cells=1/10=10٪؛
- qualification=`NOT_QUALIFIED_HSL_RESEARCH`.

Failure reasons رسمی:
`TOTAL_NET_PNL_NOT_POSITIVE`,
`EXPECTANCY_NOT_POSITIVE`,
`PROFIT_FACTOR_GATE_FAILED`,
`POSITIVE_OOS_CELL_FRACTION_GATE_FAILED`.

این نتیجه به‌عنوان evidence منفی حفظ می‌شود. HSL-004A با دیدن outcome retune
نمی‌شود و parameter search پسینی روی همان OOS ممنوع است. این candidate هیچ
اثر P10 ندارد: `p10_evidence_effect=NONE`، P11 LOCKED و Live authorization=false.

### HSL-004B — Volatility Expansion Candidate — ACTIVE / PREREGISTERED

branch فعال:
`hsl-004b-volatility-expansion`

پروتکل:
`docs/research/historical-strategy-lab/HSL-004B-VOLATILITY-EXPANSION-PROTOCOL-v0.1.0.json`

فرضیه مستقل HSL-004B: ATR(14) حداقل 1.25 برابر baseline 48h باشد، close بالای
high قبلی 20h بشکند، close در 25٪ بالایی candle باشد و extension بیشتر از 1 ATR
نباشد. stop برابر 1.25 ATR، target برابر 2R و exit پژوهشی وقتی expansion ratio
به 1 یا پایین‌تر برگردد. پارامترها قبل از outcome فریز شده‌اند.

همان پنج OOS fold، BTC/ETH، quantity=0.001، هزینه‌ها و next-primary-open semantics
HSL-001 حفظ می‌شوند. parameter search و outcome-driven retuning ممنوع‌اند؛
P4/P10 دست‌نخورده و P11 LOCKED است.

### HSL-004B — Canonical Historical Outcome — NOT QUALIFIED — 2026-09-26

Canonical HSL-004B replay روی Final HEAD
`4ccf16e5c809bfb32043d26e6cdac52aa34479a1` و همان quality manifest
پذیرفته‌شده اجرا شد. artifact immutable:

`historical-strategy-lab/technique-library/volatility-expansion-v0.1.0/hsl-004b-d1acde6fa48c9e027bc9c9b2.json`

SHA-256 فایل:
`d1acde6fa48c9e027bc9c9b27110a5e9c0802aafc898d1c51750f4f2a8933a32`

result SHA-256:
`28e56d64716f811631cac8120bdf3deeb473051c2ef11fa39fab156d9072056b`

Outcome رسمی:
- 36 completed trades؛ BTCUSDT=22 و ETHUSDT=14؛
- wins=9، losses=27، win rate=25٪؛
- total net PnL after costs≈-8.248171 quote؛
- expectancy≈-0.229116 quote/trade؛
- profit factor≈0.181324؛
- positive OOS cells=1/10=10٪؛
- qualification=`NOT_QUALIFIED_HSL_RESEARCH`.

Failure reasons:
`TOTAL_NET_PNL_NOT_POSITIVE`,
`EXPECTANCY_NOT_POSITIVE`,
`PROFIT_FACTOR_GATE_FAILED`,
`POSITIVE_OOS_CELL_FRACTION_GATE_FAILED`.

Artifact SHA روی VPS byte-for-byte با manifest SHA تطبیق داده شد. نتیجه منفی
حفظ می‌شود و HSL-004B پس از outcome retune نمی‌شود. P10 write/evidence effect
ندارد، P11 LOCKED و Live authorization=false باقی می‌ماند.

### مسیر بعد از HSL-004B — Research Intake + Historical Strategy Search Engine

پس از بستن canonical outcome HSL-004B، مدل توسعه Past از ساخت بی‌پایان candidateهای
تک‌به‌تک به یک pipeline رسمی برای **کشف، بازتولید و جست‌وجوی کنترل‌شده Edge**
تغییر می‌کند. هدف این تغییر افزایش سرعت یادگیری است، نه حذف validation یا
تبدیل backtest به مجوز Live.

جریان رسمی از این checkpoint به بعد:

`External Research → Research Candidate Registry → Train Search → Frozen Survivor → Blind OOS → Crisis Stress → Forward Candidate Review`

#### Research Intake Engine — RIE

RIE ورودی انگلیسی و چینی را به candidateهای قابل‌آزمایش و دارای provenance تبدیل
می‌کند. منابع اولیه هدف شامل paperهای دانشگاهی/peer-reviewed یا working paperهای
معتبر، repositoryهای reproducible، کتاب/lecture/transcript حرفه‌ای، و strategy
libraryهای عمومی انگلیسی/چینی است. نتیجه گزارش‌شده یک منبع هرگز به‌عنوان evidence
YATL پذیرفته نمی‌شود؛ فقط hypothesis و implementation detail استخراج می‌شود.

Tierهای منبع:
- **Tier A — Research-grade**: paper یا پژوهش معتبر با methodology روشن، داده،
  فرمول/قواعد و ترجیحاً code/reproduction material؛
- **Tier B — Reproducible implementation**: repository یا notebook قابل‌ممیزی با
  strategy logic روشن و license/provenance مشخص؛
- **Tier C — Idea mining**: منابع عمومی انگلیسی/چینی، strategy marketplace،
  ویدیو/lecture/transcript یا community implementation؛ فقط برای ساخت hypothesis،
  نه اعتماد به performance claim.

برای هر ورودی، Research Candidate Registry حداقل این فیلدها را نگه می‌دارد:
source/provenance، publication/repository date، technique family، market/universe،
timeframe، signal، lookback، entry، exit، stop، sizing، cost assumptions، reported
metrics، data period، known limitations، leakage risk، implementation availability،
و وضعیت `NEW / DUPLICATE / REPRODUCIBLE / REJECTED_SOURCE / READY_FOR_TRAIN_SEARCH`.

هدف Sweep اولیه: **20 تا 50 candidate مستقل و غیرتکراری** با اولویت
Time-Series Momentum، Volume-Weighted Momentum، Trend/Breakout،
Mean-Reversion-after-extreme-moves، Volatility/Expansion و Regime-aware logic.
این عدد target پژوهشی است، نه quota برای اجبار به نگه‌داشتن strategy ضعیف.

RIE حق ندارد:
- code خارجی را مستقیماً وارد P10 یا execution کند؛
- performance claim منبع را evidence YATL بنامد؛
- candidate را به‌خاطر شهرت منبع promote کند؛
- credential، order endpoint، leverage/futures یا Live permission اضافه کند.

#### Historical Strategy Search Engine — HSSE

HSSE پس از HSL-004B ساخته می‌شود تا به‌جای retune پسینی روی OOS، search و
optimization را فقط داخل **development/train partition** انجام دهد.

قواعد:
- search space قبل از دیدن نتیجه validation ثبت و versioned می‌شود؛
- parameter search فقط روی Train/Development مجاز است؛
- OOS/validation و blind holdout برای انتخاب پارامتر دست‌نخورده می‌مانند؛
- fee و adverse slippage در تمام rankingهای اقتصادی لحاظ می‌شوند؛
- candidate family، parameter ranges، trial count و selection rule همگی در
  Candidate Registry ثبت می‌شوند؛
- تمام trialها، شامل شکست‌ها، retained evidence هستند تا multiple-testing و
  cherry-picking پنهان نشود؛
- انتخاب فقط بر اساس بیشترین raw PnL ممنوع است.

معیار selection باید چندبعدی باشد و حداقل شامل:
- net PnL after costs؛
- positive expectancy؛
- profit factor؛
- maximum drawdown / downside behavior؛
- stability across train folds/regimes؛
- sufficient completed-trade sample؛
- cost/slippage sensitivity؛
- concentration/outlier dependence؛
- complexity penalty / preference for simpler equivalent candidates.

خروجی Train Search فقط **Frozen Survivor** است. قبل از OOS، parameters،
implementation digest، data boundary و selection rule فریز می‌شوند. سپس survivor
فقط روی داده‌ای که در search استفاده نشده ارزیابی می‌شود. شکست OOS باعث برگشت و
retune همان holdout نمی‌شود؛ hypothesis بعدی باید به‌عنوان نسل جدید و با registry
شفاف ساخته شود.

#### Multiple-testing / overfitting controls

از آنجا که HSSE عمداً تعداد زیادی candidate/trial را بررسی می‌کند، نتیجه «بهترین
backtest» به‌تنهایی معتبر نیست. حداقل کنترل‌ها:
- ثبت تعداد واقعی hypothesis/trialهای آزموده‌شده؛
- deduplication candidateها و جلوگیری از بازآزمایی پنهانی یک ایده با نام جدید؛
- train/validation/holdout separation؛
- walk-forward stability؛
- sensitivity/neighbor checks برای جلوگیری از انتخاب یک نقطه پارامتری شکننده؛
- comparison با CASH و Buy-and-Hold و baseline family؛
- نگهداری failure ledger و negative evidence؛
- ممنوعیت بازکردن P10/P11 صرفاً با historical search result.

#### Gate انتقال از Past به Forward

یک strategy فقط وقتی برای `Forward Candidate Review` مطرح می‌شود که:
1. در Train Search survivor شده باشد؛
2. پارامترها قبل از OOS فریز شده باشند؛
3. blind OOS بعد از هزینه مثبت و از نظر sample/stability قابل‌قبول باشد؛
4. Crisis/Regime Stress شکست ایمنی یا شکنندگی ناموجه نشان ندهد؛
5. provenance، implementation digest و evidence chain قابل بازسازی باشند.

عبور از این Gate به معنی تغییر P10 جاری نیست. candidate جدید فقط در یک نسل
Forward مستقل و با protocol جدید بررسی می‌شود. real-forward فعلی sealed باقی
می‌ماند.

#### ترتیب ساخت پس از HSL-004B

1. **RIE-001 — Source & Candidate Registry**: schema، provenance، tier، dedupe،
   status lifecycle و immutable source references.
2. **RIE-002 — English/Chinese Research Sweep #001**: استخراج 20–50 candidate
   و ثبت بدون اجرای production.
3. **RIE-003 — Reproduction Packets**: تبدیل candidateهای برتر به specification
   دقیق قابل‌پیاده‌سازی، بدون performance trust.
4. **HSSE-001 — Search Protocol & Data Boundaries**: **IMPLEMENTED / PR CANDIDATE** — Development تا 2023-01 فقط search surface؛ Blind OOS 2023-01 تا 2025-01 sealed؛ Final historical audit 2025-01 تا 2026-07 sealed؛ search budget و anti-leakage rules فریز.
5. **HSSE-002 — Deterministic Search Runner — CANONICAL COMPLETE 2026-09-26**:
   Final HEAD `2b6354b5ea491b45ce460b76361da9d24e5e3b0d` روی Development اجرا شد.
   هر سه family دقیقاً 4,950 trial و در مجموع 14,850 trial را ثبت کردند؛
   Blind OOS و audit holdout خوانده نشدند. Development precheck فقط 16 trial را
   عبور داد: SMA=1، EMA=8، DEMA=7. Search index SHA-256:
   `ebcb31c2e17a82e417d7a947db0f1b3b5295a256e2f93e6ff8b981666e51e269`.
   result SHA-256:
   `a79ee4e92edb24d04b14b5b1f058658ae6e8264ee1c7783dd219088977e11eed`.
   این 16 مورد هنوز survivor نیستند و ranking_performed=false /
   survivor_selected=false باقی ماند.
6. **HSSE-003 — Survivor Ranking & Robustness — CANONICAL COMPLETE 2026-09-26**:
   Final HEAD `7f7097c076816bf2b4eacc6ca95597e54afb0995` روی سه ledger immutable
   HSSE-002 اجرا شد. از 16 precheck candidate، 15 مورد exact Decimal-256 gate و
   14 مورد neighbor robustness را پاس کردند. Pareto + deterministic ranking
   شش proposal داد: EMA(11,511)، EMA(11,491)، EMA(11,471)، DEMA(121,131)،
   DEMA(91,191)، DEMA(111,161). artifact SHA-256:
   `2dd4cd9711f3c58305fe97290b0e50ba6bcc18066e2029e9e7287484047de22f`؛
   result SHA-256:
   `9063db9a1e734a76ef30e175dc144c577c5159bba5b07a707d8251273ce44e23`.
   Blind OOS و audit holdout خوانده نشدند و survivor_freeze_performed=false بود.
7. **HSSE-004A — Survivor Freeze — ACTIVE / PREREGISTERED**:
   همین شش proposal و تمام signal/execution/cost semantics قبل از هر Blind OOS
   access immutable می‌شوند. بعد از freeze هیچ parameter/family/survivor-set
   تغییر یا blind-failure retuning مجاز نیست.
8. **HSSE-004B — Frozen Blind OOS — CANONICAL COMPLETE 2026-09-26**:
   event `HSSE-BLIND-OOS-001` با acquisition از 2022-11-01 (warm-up only)
   و Blind analysis از 2023-01-01 تا 2025-01-01 اجرا شد. corpus structural quality
   را 6/6 PASS کرد و سپس هر شش survivor دقیقاً یک‌بار، بدون rerank/retune/retry،
   adjudicate شدند. نتیجه canonical: **6 PASS / 0 FAIL**؛ artifact SHA-256
   `a768ae266fa318f027872a8fdd652b43d996171b0bac226c25c2d428613b139e`
   و result SHA-256
   `2515a47573daaac6fdf9771adaf70f348ca7b03d7f7a5d4abc634328c031bb01`.
   هر شش مورد PF>2، stress-net مثبت و 75% positive calendar quarters داشتند.
   این شش PASS شش edge مستقل محسوب نمی‌شوند: سه EMA و سه DEMA خوشه‌های
   هم‌بسته‌اند. مرحله بعد **HSSE-005 Crisis/Regime Certification** است؛ Audit
   Holdout همچنان sealed و Forward promotion همچنان ممنوع است.

9. **HSSE-005 — Crisis/Regime Certification — CANONICAL COMPLETE / 0 PASS 2026-09-26**: هر شش survivor بدون retune/rerank/retry روی 8 واحد de-duplicated بحران/regime تا پایان 2024 اجرا شدند و **0/6 PASS** شد. همه شش مورد فقط 25% واحدها را در base و stress مثبت کردند و median unit PnL هر شش منفی بود؛ drawdown و sample gates مشکل اصلی نبودند. correlation بین unit-PnLهای survivorها بسیار بالا بود (~0.83 تا ~0.999) و sign agreement برابر 0.875 تا 1.0 بود، بنابراین شش survivor عملاً شش edge مستقل محسوب نمی‌شوند. نسل فعلی در HSSE-005 رد شد؛ همان نسل retune یا survivor-replacement نمی‌شود. Audit Holdout 2025–2026 و recent reserve همچنان sealed هستند. HSSE-006 در صورت اجرا فقط rejection/pipeline integrity را audit می‌کند، نه promotion.
10. **HSSE-006 — Independent Audit**: recomputation، trial ledger audit، leakage
   audit و candidate registry audit.
11. **Generation-2 Research — ACTIVE / RIE-004**: پس از رد 0/6 در HSSE-005،
   نسل اول retune نمی‌شود. literature sweep جدید روی volatility management،
   downside-volatility، panic-state protection، stop-loss و crypto regime
   detection باز شده است. Candidateهای موجود `RIE-CAND-0011` و
   `RIE-CAND-0022` دوباره استفاده می‌شوند و Candidateهای `0025..0031`
   به registry افزوده شده‌اند. اول simple deterministic control layers تست
   می‌شوند؛ HMM/NHHM فقط بعد از شکست/نیازِ مدل‌های ساده وارد search می‌شوند.
   هیچ combination قبل از standalone evidence مجاز نیست.
12. فقط پس از Audit نسل اول و protocol جدید Gen-2: **Generation-2 Controlled
   Development/Search → Fresh Evaluation → Crisis Certification → Independent
   Audit → Forward Candidate Review**. P10 جاری untouched است و 2025–2026 تا
   تعیین protocol جدید sealed می‌ماند.
13. **RIE-005 — Gen-2 Method Extraction — ACTIVE**: Queue به‌ترتیب preregistered اجرا می‌شود. `0011`، `0022` و `0027` به‌دلیل source/method reproducibility blockers قبل از هر performance run در حالت NOT_READY باقی مانده‌اند؛ `0030` (crypto stop-loss overlay) اولین candidate با روش کافی برای specification است، ولی تا freeze شدن stop basis، bar trigger، execution timing، bounded threshold grid و costs هیچ Development run مجاز نیست.

قانون توقف scope creep همچنان پابرجاست: اگر search گسترده با protocol صحیح
candidate قابل‌قبولی پیدا نکند، نتیجه معتبر `NO_EDGE_FOUND` است. پاسخ به این
نتیجه افزایش کورکورانه trialها یا شکستن holdout نیست؛ باید hypothesis/source
family جدید وارد Research شود.

هدف این مسیر «پیداکردن بهترین backtest» نیست؛ هدف پیدا کردن **edge اقتصادی
پایدار، قابل‌تکرار و قابل‌دفاع پس از هزینه‌ها** است.

### وضعیت کل پروژه در این checkpoint

مسیر عملیاتی اصلی هنوز P10 real forward validation است و روی VPS به جمع‌آوری
داده ادامه می‌دهد. حداقل window آن تا 2026-12-21 00:00 UTC ادامه دارد و sample
gate نیز باید کامل شود. HSL مسیر موازی historical research است تا در مدت انتظار
P10، گذشته را عمیق و منظم مطالعه کنیم؛ HSL حق ندارد forward evidence را جعل یا
جایگزین کند.

P11 باز نشده است. `LIVE_MASTER_LOCK=OFF`، PAPER ONLY، Spot only، no leverage،
no withdrawal، no trade permission، no order endpoint و no AI direct execution
بدون تغییر باقی می‌مانند.

14. **GEN2 Master Protocol — REGISTERED BEFORE PERFORMANCE**: پایان نسل دوم فقط یکی از دو حالت است: `GEN2_FORWARD_CANDIDATE` یا `GEN2_NO_ROBUST_EDGE_FOUND`. حداکثر 8 hypothesis اصلی و 3 combination، بدون افزایش budget بعد از outcome. Fresh OOS = 2025-01-01 تا 2026-07-01 و recent reserve از 2026-07-01 همچنان sealed هستند.
15. **GEN2-001 Stop Overlay — PREREGISTERED**: Candidate `0030` روی هر شش survivor فریز‌شده نسل اول و فقط روی Development تا 2023-01-01 تست می‌شود. grid دقیق stop = 10/20/30/40/50% + control؛ 36 condition، بدون hidden trial. 2023–2024، HSSE-005 outcomes و Fresh OOS برای selection ممنوع‌اند. هیچ performance run هنوز انجام نشده.


16. **GEN2-001 Stop Overlay — CANONICAL COMPLETE / 0 PROPOSALS**: 36 registered
conditions were executed exactly once on Development evidence. The 10% stop
activated 20 times across 3/6 reference strategies but failed aggregate base/stress
economics and median improvement gates. 20/30/40/50% never activated. No stop
threshold is promoted; no same-evidence threshold refinement/retry is allowed.
Generation 2 continues to the next preregistered hypothesis. P10 untouched; Fresh
OOS sealed; P11 locked.

17. **GEN2-002 Volatility Scaling — CANONICAL INVALIDATED / 0 PROPOSALS — 2026-09-27**:
`RIE-CAND-0025` was implemented as the frozen YATL adaptation
`GEN2-ADAPT-0002-VOL-SCALING` with the preregistered 12% annualized target,
183 completed UTC-day estimator, monthly updates, `scale=min(1,0.12/sigma_ann)`,
no short, no leverage, and 12 total conditions across the six frozen reference
strategies. Final implementation HEAD
`3e8e5167414b26fb72ed80a620a74f6bdc60d38e` passed GitHub Actions run
`36307964173` and the focused GEN2-002 test suite.

The single canonical Development evaluation did **not** compute economic
performance. It was invalidated before economic evaluation because the frozen
183-day estimator window was structurally incomplete at **40 symbol-month
boundaries** in the admitted CRL Development corpus. The admitted corpus preserves
CRL-003-verified source gaps; the protocol forbids interpolation, forward-fill,
silent window shortening, alternate target/window/EWMA rescue, leverage, or hidden
retry. Canonical runtime artifact:
`generation-2/gen2-002/vol-scaling-25ac8f5fbee4fb9e75f79c7e.json`,
SHA-256
`25ac8f5fbee4fb9e75f79c7e769a3cc1b0c046ede0536c8f91a6d4eba5a0a701`.
Canonical acceptance record:
`docs/research/generation-2/GEN2-002-CANONICAL-RESULT-v0.1.0.json`.

Outcome state:
`status=FAIL`,
`evaluation_status=INVALIDATED_BEFORE_ECONOMIC_EVALUATION`,
`performance_outcome_computed=false`,
`failure_reasons=[INCOMPLETE_VOLATILITY_WINDOW]`,
`proposal_count=0`.
This negative result is retained. The same Development evidence may not be used
to relax the 183-day window, change the target, introduce an EWMA substitute, or
otherwise rescue this candidate. This does **not** establish that all volatility
scaling is invalid; it closes only this preregistered GEN2-002 adaptation on this
frozen evidence. P10 remains untouched; Fresh OOS and recent reserve remain
sealed; P11 remains locked; LIVE_MASTER_LOCK=OFF.

## YATL Alpha Factory — Authoritative Program Layer — 2026-09-27

از این checkpoint، هدف تحقیقاتی YATL فقط «پیداکردن یا تعمیر یک strategy» نیست.
برنامه بالادستی رسمی پروژه **Alpha Factory** است: یک pipeline برای کشف، رد،
اعتبارسنجی، تفکیک و در نهایت ترکیب edgeهای واقعاً مستقل و قابل‌مقیاس.

مرجع تفصیلی:
`docs/research/alpha-factory/ALPHA-FACTORY-MASTER-PLAN-v1.0.md`

قرارداد machine-readable مراحل:
`docs/research/alpha-factory/ALPHA-FACTORY-STAGE-GATES-v1.0.json`

این لایه، protocolهای frozen قبلی را بازنویسی نمی‌کند. GEN2-MASTER-001 و تمام
outcomeهای canonical قبلی immutable evidence باقی می‌مانند. Generation 2 یکی از
research trackهای Alpha Factory است.

### هدف شمالی

هدف YATL از این پس:

**کشف چند منبع مستقل opportunity/alpha که پس از fee/slippage ارزش اقتصادی مثبت
داشته باشند، روی داده واقعاً ندیده‌شده دوام بیاورند، در بحران رفتار قابل‌فهم و
کنترل‌شده داشته باشند، فرصت معامله را با محافظه‌کاری افراطی نابود نکنند، و در
صورت اثبات edge قابلیت رشد ظرفیت سرمایه داشته باشند.**

معیار اصلی پیشرفت:
**validated independent edge count + opportunity coverage + capacity**؛
نه تعداد backtest، تعداد تست، تعداد خطوط کد یا تعداد parameter variant.

### معماری سه‌لایه

1. **Alpha Discovery Plane** — کشف hypothesis، data expansion، source binding،
   method extraction، Development search و family diversity.
2. **Adjudication Plane** — exact recompute، anti-leakage، false-discovery control،
   robustness، cost stress، independence/correlation، Fresh OOS، crisis و audit.
3. **Forward & Capital Plane** — Paper/shadow forward، execution quality،
   opportunity realization و capacity research؛ بدون Live authority.

### نقشه مرحله‌ای ثابت

| Stage | نام | هدف | وضعیت |
|---|---|---|---|
| AF-00 | Program Governance | قفل معماری، lifecycle، stage gates | **ACTIVE / IMPLEMENTED IN PR** |
| AF-01 | Opportunity Data Foundation | universe point-in-time، gap policy، liquidity/capacity metadata | PENDING |
| AF-02 | Alpha Taxonomy & Registry v2 | family/mechanism/capacity classification | PENDING |
| AF-03 | Research Intake / Opportunity Sweep | ساخت hypothesisهای مستقل با provenance | PENDING |
| AF-04 | Standalone Alpha Development | تست هر edge به‌تنهایی قبل از combination | PENDING |
| AF-05 | Robust Search / False Discovery | multiple-testing، neighbor stability، trial ledger | PENDING |
| AF-06 | Independence & Opportunity Gate | correlation، overlap، regime coverage، cluster count | PENDING |
| AF-07 | Portfolio / Ensemble Lab | ترکیب فقط componentهای standalone-qualified | LOCKED |
| AF-08 | Fresh OOS | یک adjudication روی evidence sealed | SEALED |
| AF-09 | Crisis / Regime Certification | failure-map و stress certification | LOCKED |
| AF-10 | Independent Audit | provenance/code/trial/leakage/economics audit | LOCKED |
| AF-11 | Forward Opportunity Validation | real-time Paper/shadow evidence | LOCKED |
| AF-12 | Capacity & Capital Scaling | deployable capital / impact / net-dollar PnL | LOCKED |
| AF-13 | Adaptive Research Loop | نسل جدید hypothesis بدون rescue tuning | CONTINUOUS |

### خانواده‌های Alpha

Registry جدید باید candidateها را حداقل در این خانواده‌ها تفکیک کند:

- AF-TREND — trend / time-series momentum
- AF-BREAKOUT — breakout / volatility expansion
- AF-MEANREV — mean reversion
- AF-CRASHREB — panic / dislocation / rebound
- AF-VOLUME — volume-conditioned edge
- AF-LIQUIDITY — liquidity / spread / impact proxies
- AF-TIME — session / weekday / recurring time effects
- AF-RELATIVE — relative-strength / lead-lag / cross-asset information
- AF-REGIME — deterministic/probabilistic regime logic
- AF-EVENT — point-in-time external/event context
- AF-MICRO — microstructure only after trustworthy historical data exists

چند parameter variant از یک mechanism، چند edge مستقل محسوب نمی‌شوند.

### Candidate lifecycle اجباری

`DISCOVERED → SOURCE_BOUND → METHOD_SPECIFIED → PREREGISTERED → IMPLEMENTED →
DEVELOPMENT_EVALUATED → DEVELOPMENT_SURVIVOR/REJECTED → FROZEN_FOR_OOS →
OOS_SURVIVOR/OOS_REJECTED → CRISIS_CERTIFIED → INDEPENDENT_AUDIT_PASS →
FORWARD_CANDIDATE`

Blockerها نیز state رسمی‌اند:
`BLOCKED_SOURCE`, `BLOCKED_DATA`, `BLOCKED_REPRODUCIBILITY`,
`INVALIDATED_BEFORE_ECONOMICS`.

### Opportunity-preservation rule

YATL نباید به سیستمی تبدیل شود که با «تقریباً هیچ معامله‌ای نکردن» gateها را
پاس کند. هر candidate باید قبل از outcome، opportunity profile خود را تعریف کند.
برای overlayها و risk-layerها حداقل signal count، completed trades، active exposure،
notional utilization و starvation بررسی می‌شود. Sparse بودن فقط وقتی معتبر است
که بخشی از hypothesis اصلی و از قبل ثبت‌شده باشد.

### Scale principle

هدف بلندمدت فقط درصد بازده بالا نیست. هر edge مستقل باید در نهایت از نظر:
**edge quality، breadth، persistence، capacity، diversification، execution و
compounding** ارزیابی شود.

هیچ wealth target تضمین‌شده نیست. Alpha Factory به‌جای وعده نتیجه، زیرساختی
می‌سازد که در صورت کشف edge قوی، ظرفیت رشد آن در یک سیستم تک‌استراتژی کوچک
محبوس نشود.

### ترتیب اجرایی فوری

ترتیب بعدی پروژه از این checkpoint:

1. **AF-00 closeout** — docs + machine-readable gates + CI.
2. **GEN2-002 canonical closeout** — outcome فعلی حفظ؛ no rescue.
3. **AF-03A Source Unblock Sprint** — فقط یک تلاش bounded برای
   RIE-CAND-0011 / 0022 / 0027؛ هیچ rule حدس زده نمی‌شود.
4. **GEN2 queue continuation** — اگر blockerها باقی ماندند، candidate بعدی eligible
   در queue با protocol تازه؛ Queue B از 0028 شروع می‌شود.
5. **AF-01 Opportunity Data Design** — قبل از universe expansion، policy و
   point-in-time eligibility فریز شود.
6. **AF-02 Registry v2** — family/mechanism/capacity/opportunity fields.
7. **AF-03B Independent Alpha Sweep #2** — عمداً خارج از trend-overlay cluster،
   با اولویت mean reversion، volume/liquidity، time effects، crash/rebound و
   relative/lead-lag.
8. **AF-04 Standalone Development** — هنوز combination ممنوع.
9. **AF-06 Independence Gate** — survivorها به edge-cluster واقعی تبدیل شوند.
10. AF-07 به بعد فقط پس از standalone evidence باز می‌شود.

### Safety / authority unchanged

این برنامه هیچ authorization جدیدی ایجاد نمی‌کند:
PAPER / RESEARCH ONLY، `LIVE_MASTER_LOCK=OFF`، no Futures execution،
no leverage، no short، no live execution، no order endpoint، no AI direct
execution، P10 independent/untouched و P11 LOCKED باقی می‌مانند.

### Execution Routing — Chat / Work / Astra — 2026-09-27

Alpha Factory از این checkpoint به work packageهای کوچک‌تر تقسیم شده است و
نوع اجرای هر بسته قبل از شروع مشخص می‌شود.

مرجع authoritative:
`docs/research/alpha-factory/EXECUTION-MODE-MATRIX-v1.0.md`

کلاس‌ها:
- `CHAT_DIRECTOR`: تصمیم، protocol، blocker، اجرای canonical تحت نظارت؛
- `WORK_REQUIRED`: کار چندمرحله‌ای روی فایل‌ها، datasetها و artifactهای متعدد؛
- `ASTRA_REQUIRED`: synthesis در مقیاس corpus بزرگ؛
- `WORK_AND_ASTRA_REQUIRED`: هر دو نیاز همزمان.

**قانون هشدار اجباری:** قبل از ورود به هر work package که Work یا Astra لازم
دارد، Director باید قبل از شروع اجرا به Yahya هشدار دهد. دستورهای عمومی
«ادامه» یا «بریم» به‌تنهایی اجازه عبور خاموش از این gate را نمی‌دهند.

هشدارهای استاندارد:
- `⚠️ WORK GATE`
- `⚠️ ASTRA GATE`
- `⚠️ WORK + ASTRA GATE`

Astra فقط برای مسئله سخت استفاده نمی‌شود؛ trigger آن corpus-scale بودن است.
نمونه thresholdها: 50 source عمیق جدید، 25 method قابل‌بازتولید جدید،
100 candidate برای clustering سراسری، 20 survivor variant، 10 independent edge
cluster یا 3 نسل پژوهشی کامل.

Fresh OOS و evidenceهای sealed حتی در Work/Astra به‌صورت autonomous مصرف
نمی‌شوند؛ بازکردن و اجرای canonical آن‌ها همچنان Director-supervised باقی
می‌ماند.

18. **AF-03A Source Unblock Sprint — COMPLETE / 1 UNBLOCKED / 2 BLOCKED — 2026-09-27**:
The bounded source/reproducibility sprint rechecked the three preregistered
Queue-A blockers without running market performance. `RIE-CAND-0011` remains
`BLOCKED_REPRODUCIBILITY`: its 2-week formation / 1-week holding / weekly
quintile WML construction is exposed, but the exact paper-specific risk-scaling
implementation is still not sufficiently bound. `RIE-CAND-0022` remains
`BLOCKED_SOURCE`: Expansion/Neutral/Contraction and short-vs-long realized
volatility plus normalized momentum are visible, but the exact horizons,
equation, thresholds and update semantics remain unavailable. `RIE-CAND-0027`
is now `METHOD_SPECIFIED`: the author-hosted full text exposes exact downside
volatility, lag, inverse-volatility scaling and real-time expanding-window
normalization. No performance evidence was generated by AF-03A.

19. **GEN2-003 Downside-Volatility Scaling — PREREGISTERED / ZERO PERFORMANCE RUNS**:
`RIE-CAND-0027` is frozen as
`GEN2-ADAPT-0003-DOWNSIDE-VOL-SCALING` under protocol
`GEN2-003-DOWNSIDE-VOL-SCALING-001`. The source method computes monthly
downside realized volatility from negative daily returns, scales the next
month by inverse lagged downside volatility, and estimates the scale
normalization only from prior expanding history. YATL retains the six frozen
HSSE-004A trend survivors unchanged, adds a source-style total-volatility
comparator, caps both managed exposures at 1.0 because leverage is forbidden,
and registers 18 total conditions (6 × control/total/downside). No target-vol,
EWMA, fixed-weight, threshold or alternate-warmup grid is authorized.
Missing estimator data is never imputed; an unavailable monthly estimator does
not fabricate a new scale and instead carries the prior valid non-levered scale,
with scale=1.0 before the first valid decision. Opportunity-preservation,
valid-scale-decision and after-cost superiority gates are frozen before
outcomes. Fresh OOS, recent reserve and P10 remain unread. Performance is
blocked until deterministic implementation + protocol-specific tests have a
green Final HEAD.

**Next execution gate: `⚠️ WORK GATE` — GEN2-003 deterministic implementation
and tests are `WORK_REQUIRED`. A generic “ادامه/بریم” does not silently cross
this gate.**

### Blind-Spot Audit + Conditional Edge Track — 2026-09-27

YATL از این checkpoint به بعد هر failure را معادل NO_EDGE تلقی نمی‌کند.

مرجع authoritative:
docs/research/alpha-factory/BLIND-SPOT-AND-CONDITIONAL-EDGE-GOVERNANCE-v1.0.md

هر rejection مهم باید failure mechanism را طبقه‌بندی کند:
NO_EDGE، CONDITIONAL_EDGE، OVERFIT، DATA_BLOCKED، EXECUTION_LIMITED،
CAPACITY_LIMITED، REGIME_MISMATCH، REDUNDANT_EDGE،
IMPLEMENTATION_INVALIDATED، INSUFFICIENT_EVIDENCE یا
UNKNOWN_FAILURE_MECHANISM.

دو مسیر اقتصادی رسمی وجود دارد:

- ALL_REGIME_EDGE: ادعای edge در مجموعه regimeهای preregistered و نیازمند عبور
  از gateهای کامل robustness.
- REGIME_CONDITIONAL_EDGE: ادعای edge فقط داخل operating envelope از پیش
  ثبت‌شده. بیرون envelope معیار اصلی detection، containment، capital
  preservation و safe re-entry است، نه الزاماً profitability.
- UNKNOWN_EDGE_SCOPE: حالت پیش‌فرض تا زمانی که evidence کافی وجود ندارد.

تغییر برچسب پس از failure اجازه rescue همان candidate نیست. هر detector،
operating envelope، threshold، sizing یا logic جدید باید candidate ID و protocol
جدید با evidence budget جدید بگیرد. negative evidence قبلی حذف نمی‌شود.

برای conditional edge، metrics اجباری شامل false activation/deactivation،
recognition lag، missed-opportunity cost، loss-before-shutdown، re-entry lag و
false re-entry است.

شش survivor تاریخی HSSE-004A همچنان ALL_REGIME certified نیستند و failure
قبلی crisis/regime آنها حفظ می‌شود. در عین حال فرضیه استفاده شرطی/normal-regime
از آنها به‌عنوان research path جدید مجاز است، اما هنوز اثبات یا Live-authorized
نیست.

هر rejection و generation closeout باید Blind-Spot / Assumption Review داشته
باشد:
ASSUMPTION -> WHY WE BELIEVE IT -> WHAT IF FALSE? -> TEST -> EVIDENCE -> STATUS.

Audit باید حداقل multiple testing، opportunity starvation، opportunity cost
فیلترها، detector delay، strategy decay، venue/quote dependence، execution،
capacity، benchmark choice، common-factor correlation و signal/sizing/execution
attribution را بررسی کند.

### Work Token Conservation

به‌دلیل محدودیت توکن Work، Work mode منبع اجرایی محدود تلقی می‌شود و default
نیست.

کارهای governance، protocol design، assumption audit، rejection review،
candidate classification، queue decision، narrow source extraction و ویرایش
محدود مستندات تا جای ممکن در CHAT_DIRECTOR انجام می‌شوند.

WORK_REQUIRED فقط برای implementation قابل‌توجه، bulk dataset work، تحلیل
عددی سنگین، repository-wide migration، artifact orchestration سنگین یا
testing/build workflowی که واقعاً از Work سود می‌برد استفاده می‌شود.

قبل از هر WORK GATE، Director ابتدا باید بررسی کند آیا همان کار با خطای قابل‌قبول
در CHAT_DIRECTOR قابل انجام است یا نه. اگر بله، Work مصرف نمی‌شود.

Astra همچنان فقط برای corpus-scale synthesis طبق thresholdهای قبلی استفاده
می‌شود.

### Mass Canonical Candidate Factory — 2026-09-27

YATL از مسیر candidate-by-candidate به یک strategy discovery factory در مقیاس
بزرگ گسترش پیدا می‌کند.

مرجع authoritative:
`docs/research/alpha-factory/MASS-CANONICAL-CANDIDATE-FACTORY-v1.0.md`

هدف معماری:
- پشتیبانی از 100,000+ candidate canonical در طول زمان؛
- بدون ساخت branch/PR/file مستقل برای هر candidate؛
- deterministic generator + family manifests + sharded batch runner + append-only
  result ledger + content-addressed artifacts.

گسترش پژوهشی مرحله‌ای است:
- حدود 1,000 candidate برای calibration؛
- حدود 10,000 candidate برای expansion؛
- تا 100,000 candidate پس از اثبات throughput، determinism، storage،
  exact-recompute و multiple-testing accounting.

این اعداد quota قبولی نیستند. صفر survivor معتبر است.

تمرکز YATL دیگر روی شش survivor trend تاریخی نیست. آن شش مورد فقط یک
common-factor cluster محسوب می‌شوند. broad discovery باید mechanismهای مستقل
مثل trend، breakout، mean-reversion، crash/rebound، volume، volatility،
session/time، liquidity، relative-strength، lead-lag، regime-conditional،
multi-venue و sizing/exit overlays را پوشش دهد.

فیلتر اصلی:
F0 structural -> F1 opportunity -> F2 after-cost Development ->
F3 temporal robustness -> F4 neighbor stability -> F5 multiple-testing ->
F6 duplicate/common-factor cluster -> F7 mechanism survivor freeze ->
F8 Fresh OOS -> F9 edge-scope certification -> F10 audit/Forward.

Historical research را می‌توان با compute/automation شدیداً سریع کرد، اما:
- real Forward time؛
- future regimes؛
- real execution experience
قابل فشرده‌سازی نیستند.

بنابراین timeline مهندسی/Development می‌تواند به‌جای ماه‌ها بسیار کوتاه‌تر شود،
اما هیچ historical batch جای calendar-time Forward evidence را نمی‌گیرد.

Work-token policy:
- طراحی، manifests، filters، classification و closeout در CHAT_DIRECTOR؛
- Work فقط برای ساخت reusable Mass Candidate Engine یا data plumbing سنگین؛
- نه Work per candidate؛
- batch execution روی VPS/runtime.



### Alpha Factory Production Readiness — 2026-09-27

AF-01B point-in-time Opportunity Data Foundation روی main پذیرفته شد.

مسیر بعدی قبل از اولین Mass Development run:

1. AF-01C historical archive inventory/acquisition adapter؛
2. archive-backed broad Spot/USDT Development population؛
3. MCF-03 dynamic-universe production runner؛
4. MCF-04 severe statistical/neighbor/common-factor adjudication؛
5. MCF-PROD-001 با حدود 8k–12k raw candidate؛
6. فقط survivorهای frozen بعد از F0–F7 حق نزدیک‌شدن به Fresh OOS دارند.

Development نسل اول فقط از بازه شناخته‌شده
2020-03-01 تا 2023-01-01 استفاده می‌کند و داده بعد از آن را برای این run باز
نمی‌کند.

Universe اولیه point-in-time و ماهانه بازسازی می‌شود:
حداکثر 50 عضو بر اساس trailing 30d quote volume گذشته، با حداقل 60 روز سابقه
admitted و continuity حداقل 99.5%.

current exchangeInfo به‌تنهایی historical-universe source محسوب نمی‌شود؛
historical archive inventory باید جداگانه freeze و hash شود.

Search-space اولیه در
`MCF-PROD-001-FAMILY-DOMAIN-PLAN-v1.0.json`
قبل از outcome فریز شده و raw Cartesian upper bound آن 9,176 candidate و expected structurally-valid count آن 8,640 است.

هیچ survivor quota وجود ندارد. صفر survivor نتیجه معتبر است.
Fresh OOS، recent reserve و P10 همچنان untouched هستند.

## به‌روزرسانی مدیریتی ۳۰ سپتامبر ۲۰۲۶ — وضعیت دقیق مسیر تولید انبوه

این بخش، وضعیت‌های قدیمی‌ترِ «مرحله جاری» در همین سند را برای مسیر
`MCF-PROD-001` جایگزین می‌کند. هدف فعلی هنوز اجرای نتیجه عملکردی نیست؛
هدف این است که **ورودی جهان ماهانه، طبقه‌بندی محصول، داده اجرایی و ورودی رانر
را قبل از دیدن نتیجه ۶٬۸۵۲ نامزد کاملاً قفل کنیم**.

### آنچه تا این لحظه بسته شده است

1. پیاده‌سازی رانر تولیدی و داوری آماری پذیرفته و ادغام شده است.
2. شمار نامزدها قبل از نتیجه قفل شده است:
   - ۹٬۱۷۶ ترکیب خام؛
   - ۸٬۶۴۰ ترکیب ساختاری معتبر؛
   - ۱٬۷۸۸ مورد مسدود در پیاده‌سازی؛
   - **۶٬۸۵۲ نامزد قابل اجرا**.
3. جمعیت تاریخی `AF-01C` کامل و آشتی داده شده است:
   - ۹٬۳۰۶ هویت ماهانه؛
   - ۶٬۴۴۳ ماه موفق؛
   - ۲٬۸۶۳ ماه با شکاف/عدم موفقیت حفظ‌شده و بدون دستکاری.
4. پیش‌بررسی جهان تولیدی و منطق مرز طبقه‌بندی پذیرفته شده‌اند.
5. موج اول طبقه‌بندی تاریخی با ۱۷۶ نماد اجرا شد:
   - ۱۷۶ از ۱۷۶ تعیین تکلیف؛
   - ۱۷۳ نماد عادی بازار نقدی؛
   - ۳ محصول غیرعادی؛
   - هیچ نتیجه عملکردی خوانده نشد.
6. پیش‌بررسی واقعی پس از موج اول، فایل تغییرناپذیر
   `c8c38375ecffaa03bb30262ae14ca9b431e242b622d693214ed1a938330fad2a`
   را ساخت و نشان داد:
   - عضویت ماهانه هنوز نهایی نشده؛
   - ۲۰۸ نماد داده‌پذیر هنوز طبقه‌بندی نشده‌اند؛
   - اما فقط **۲ نماد** هنوز می‌توانند عضویت پنجاه‌تایی ماهانه را تغییر دهند:
     `BTSUSDT` و `OCEANUSDT`.
7. درخواست ادغام شماره ۱۶۵ پذیرفته و با شناسه
   `7413c1743250b59199ec1e292c6e0642df14a04d` ادغام شد.
8. پشتیبانی از «نقشه طبقه‌بندی تجمعی» در درخواست ادغام شماره ۱۶۶ پذیرفته و با
   شناسه `db87f6f813b000363719c1d30097a581e3b95091` ادغام شد. این تغییر تضمین
   می‌کند موج دوم، ۱۷۶ مدرک پذیرفته‌شده موج اول را حذف یا جایگزین نکند.

### کار جاری

کار جاری، درخواست ادغام شماره ۱۶۷ است:

`MCF-PROD-001-CLASSIFICATION-WAVE-002-ACQUISITION`

مرز ورودی آن از قبل قفل شده و فقط شامل دو نماد زیر است:

- `BTSUSDT`
- `OCEANUSDT`

برای هر دو، مدرک تاریخی مستقلِ صرافی برای بازار نقدی ثبت شده و طبقه‌بندی
`ORDINARY_SPOT_CONFIRMED` است. آزمون مخزن باید ثابت کند که پس از افزودن این
دو مورد، نقشه تجمعی دقیقاً **۱۷۸ طبقه‌بندی** دارد و مدارک ۱۷۶ مورد قبلی بدون
تغییر باقی مانده‌اند.

این مرحله هنوز هیچ اجرای عملکردی روی ۶٬۸۵۲ نامزد انجام نمی‌دهد.

### ترتیب قطعی بعد از پذیرفته‌شدن موج دوم

پس از سبز شدن آزمون نهایی و ادغام درخواست ۱۶۷، ترتیب مجاز دقیقاً این است:

1. روی سرور، موج دوم با نقشه پایه موج اول به‌صورت تجمعی مادی‌سازی شود.
2. باید یک نقشه طبقه‌بندی جدید با ۱۷۸ ورودی ساخته شود؛ مدارک موج اول باید
   همان فایل‌های قبلی باقی بمانند.
3. پیش‌بررسی تولیدی دوباره روی همان جمعیت تاریخی `AF-01C` اجرا شود.
4. اگر فهرست مرز بعدی خالی و `membership_resolved=true` باشد:
   - حلقه طبقه‌بندی بسته می‌شود؛
   - عضویت دقیق ماهانه و نقطه‌درزمان پنجاه نماد قفل می‌شود.
5. اگر مرز بعدی خالی نباشد:
   - فقط همان نمادهای خروجی پیش‌بررسی وارد موج بعدی می‌شوند؛
   - هیچ نماد دلخواهی اضافه نمی‌شود.
6. پس از نهایی‌شدن عضویت ماهانه:
   - اجتماع نمادهای انتخاب‌شده ساخته می‌شود؛
   - داده‌های ۱۵ دقیقه، ۱ ساعت و ۴ ساعت مخصوص اجرای توسعه مادی‌سازی می‌شوند؛
   - فهرست ورودی رانر قفل می‌شود.
7. **فقط بعد از بسته‌شدن تمام مراحل بالا** اجرای عملکرد ۶٬۸۵۲ نامزد در بازه
   توسعه مجاز است.
8. بعد از اجرای عملکرد، فیلترهای از پیش ثبت‌شده `F0` تا `F7` اعمال می‌شوند.
9. تنها نمایندگان مستقل و واجد شرایط می‌توانند برای مرحله داده واقعاً ندیده‌شده
   منجمد شوند.

### چک‌لیست کوتاه این مسیر

- [x] جمعیت تاریخی کامل و آشتی داده شده
- [x] رانر تولیدی و داوری آماری پیاده‌سازی و پذیرفته شده
- [x] ۶٬۸۵۲ هویت اجرایی قبل از نتیجه قفل شده
- [x] منطق مرز طبقه‌بندی تاریخی پذیرفته شده
- [x] موج اول ۱۷۶ نمادی تعیین تکلیف شده
- [x] پیش‌بررسی واقعی پس از موج اول انجام شده
- [x] مرز موج دوم دقیقاً به دو نماد کاهش یافته
- [x] نقشه طبقه‌بندی تجمعی پیاده‌سازی و پذیرفته شده
- [ ] درخواست ادغام شماره ۱۶۷ سبز و پذیرفته شود
- [ ] موج دوم روی سرور به نقشه ۱۷۸ عضوی مادی‌سازی شود
- [ ] پیش‌بررسی تولیدی دوباره اجرا شود
- [ ] عضویت ماهانه نهایی شود یا موج بعدی دقیقاً از خروجی پیش‌بررسی قفل شود
- [ ] عضویت‌های ماهانه نقطه‌درزمان منجمد شوند
- [ ] داده‌های اجرایی ۱۵ دقیقه، ۱ ساعت و ۴ ساعت برای اجتماع انتخاب‌شده ساخته شوند
- [ ] ورودی دقیق رانر منجمد شود
- [ ] اجرای عملکرد ۶٬۸۵۲ نامزد آغاز شود
- [ ] فیلترهای `F0` تا `F7` اجرا و نمایندگان مستقل منجمد شوند
- [ ] تنها پس از آن، مرحله داده واقعاً ندیده‌شده بررسی شود

### مسیر موازی P10 در ۳۰ سپتامبر

مسیر `P10` مستقل از کارخانه نامزدها ادامه دارد و نباید برای انتخاب تاریخی
خوانده یا تغییر داده شود.

- جمع‌آوری واقعی آینده‌نگر از ۲۲ سپتامبر ادامه دارد.
- گرم‌شدن ۵۱ کندل چهارساعته امروز به مرز تصمیم رسیده است.
- به‌دلیل شرط بسته‌شدن کندل بعدی، نخستین بررسی عملی پس از گرم‌شدن باید بعد از
  اجرای جمع‌آورنده عصر ۳۰ سپتامبر انجام شود.
- نتیجه امروز فقط نخستین شواهد واقعی پس از گرم‌شدن است، نه داوری نهایی.
- داوری اقتصادی ثبت‌شده زودتر از ۲۱ دسامبر ۲۰۲۶ مجاز نیست و شرط تعداد معامله
  نیز همچنان باید برقرار شود.
- هیچ تنظیم دوباره، تغییر نامزد، تغییر آستانه یا بازکردن `P11` مجاز نیست.

### قفل‌های تغییرناپذیر

در تمام مراحل بالا:

- فقط پژوهش و اجرای کاغذی؛
- قفل اجرای واقعی خاموش باقی می‌ماند؛
- بازار آتی، اهرم و فروش استقراضی ممنوع؛
- هیچ مسیر ثبت سفارش وجود ندارد؛
- هوش مصنوعی حق اجرای مستقیم ندارد؛
- داده واقعاً ندیده‌شده و ذخیره اخیر بسته می‌مانند؛
- مسیر `P10` برای انتخاب تاریخی خوانده یا نوشته نمی‌شود؛
- `P11` قفل است.

## به‌روزرسانی تکمیلی ۳۰ سپتامبر ۲۰۲۶ — حلقه طبقه‌بندی بسته شد

این بخش، قسمت «کار جاری» در به‌روزرسانی قبلی ۳۰ سپتامبر را جایگزین می‌کند.

### نتیجه قطعی پیش‌بررسی پس از موج دوم

موج دوم روی سرور با موفقیت به نقشه قبلی اضافه شد و نقشه تجمعی ۱۷۸ عضوی ساخته شد.

هویت نقشه تجمعی:

`e19cb8539c29e6a95c453b6a680b56b5b88bddad65df8a67ca32a14ceab41012`

هویت خروجی مادی‌سازی موج دوم:

`277dfab59f61f70f87d6cd572cc94c69ba5cb8390ce2e9ccc62639e9a73b7594`

پس از آن، پیش‌بررسی تولیدی دوباره اجرا شد و نتیجه زیر را داد:

- وضعیت: آماده برای بستن ورودی تولیدی؛
- هویت پیش‌بررسی:
  `f0a177cc98d3946ead55dc69016d65178539ecd0c778c9c4ae0a193e3ba61cfc`;
- تعداد ماه‌ها: ۳۴؛
- عضویت ماهانه حل‌شده: بله؛
- تعداد نمادهای مرز بعدی: صفر؛
- تعداد نمادهای داده‌پذیر حل‌نشده پایین‌تر: ۲۰۶؛
- تعداد نمادهای موجود در اجتماع عضویت‌های ماهانه: **۱۷۵**؛
- خواندن نتیجه عملکرد: خیر؛
- خواندن داده واقعاً ندیده‌شده: خیر؛
- خواندن ذخیره اخیر: خیر؛
- خواندن/نوشتن مسیر آینده‌نگر: خیر؛
- اجرای واقعی: خاموش؛
- مرحله زنده بعدی: قفل.

### معنای مهم نتیجه

`classification_complete=false` مانع ادامه نیست.

علت این است که ۲۰۶ نماد پایین‌تر هنوز از نظر نوع محصول تعیین تکلیف نشده‌اند،
اما طبق ترتیب نقدشوندگی هیچ‌کدام دیگر قادر نیستند وارد پنجاه نماد انتخابی هیچ
ماه شوند یا عضویت آن را تغییر دهند.

بنابراین از این نقطه:

- حلقه طبقه‌بندی تاریخی **بسته است**؛
- موج سوم وجود ندارد؛
- بررسی همه ۲۰۶ نماد باقی‌مانده اتلاف کار و خلاف قاعده مرز تصمیم‌ساز است.

### مرحله جاری جدید

مرحله جاری:

**انجماد دقیق ۳۴ عضویت ماهانه نقطه‌درزمان**

ورودی فقط همان پیش‌بررسی
`f0a177cc98d3946ead55dc69016d65178539ecd0c778c9c4ae0a193e3ba61cfc`
است.

خروجی باید:

- هر ۳۴ ماه را دقیقاً حفظ کند؛
- فهرست نمادهای هر ماه را قفل کند؛
- هش رده‌بندی همان ماه را به عضویت متصل کند؛
- برای هر ماه هش عضویت مستقل بسازد؛
- اجتماع ۱۷۵ نماد را ثبت کند؛
- ماه خالی را در صورت وجود صریحاً حفظ کند؛
- هیچ نتیجه عملکردی را نخواند.

### مسیر بعدی تا اولین اجرای عملکرد

1. انجماد ۳۴ عضویت ماهانه.
2. اجرای واقعی انجماد روی سرور و ثبت هش.
3. مادی‌سازی داده‌های ۱۵ دقیقه، ۱ ساعت و ۴ ساعت فقط برای اجتماع انتخاب‌شده.
4. بررسی پوشش زمانی، شکاف‌ها و هویت همه داده‌های اجرایی.
5. انجماد ورودی دقیق رانر توسعه.
6. اثبات اینکه رانر فقط همین ورودی منجمد را مصرف می‌کند.
7. سپس و فقط سپس اجرای ۶٬۸۵۲ نامزد.
8. اعمال فیلترهای از پیش ثبت‌شده تا مرحله هفت.
9. انجماد نمایندگان مستقل واجد شرایط.
10. بعد از آن امکان ورود به داده واقعاً ندیده‌شده بررسی می‌شود.

### وضعیت چک‌لیست

- [x] جمعیت تاریخی
- [x] هویت نامزدها
- [x] رانر و داوری آماری
- [x] طبقه‌بندی موج اول
- [x] طبقه‌بندی موج دوم
- [x] نقشه تجمعی ۱۷۸ عضوی
- [x] عضویت ماهانه از نظر تصمیم‌گیری حل شده
- [x] مرز طبقه‌بندی بعدی صفر
- [ ] انجماد ۳۴ عضویت ماهانه
- [ ] مادی‌سازی اجتماع داده اجرایی
- [ ] انجماد ورودی رانر
- [ ] اجرای ۶٬۸۵۲ نامزد
- [ ] داوری مراحل صفر تا هفت
- [ ] انجماد نمایندگان مستقل
- [ ] بررسی داده واقعاً ندیده‌شده



## به‌روزرسانی ۳۰ سپتامبر ۲۰۲۶ — داده اجرایی و انجماد ورودی رانر

واحد کاری: `MCF-PROD-001-RUNTIME-DATA-MATERIALIZATION-AND-RUNNER-INPUT-FREEZE`.
این بخش وضعیت جاری قبلی درباره انجماد عضویت ماهانه را جایگزین می‌کند.

عضویت ماهانه بسته است و انجماد واقعی VPS در شواهد پذیرفته‌شده PR #168 ثبت شده است:

- main پذیرفته‌شده مبنا: `b71ae8fee40ab0b80c3dbc0349fbe7fb3b8be55a`؛
- آزمون نهایی PR #168: اجرای GitHub #398، شناسه `36687440489`، موفق؛
- هش عضویت: `c75aa5c4347dff5daeed1ca2625fb86e2df3f4e105fde55aed0248df4ce868b7`؛
- ۳۴ ماه و اجتماع دقیق ۱۷۵ نماد؛
- ۲۲ ماه با ۵۰ نماد، ۱۱ ماه صریحاً خالی، ۱ ماه با ۱۵ نماد؛
- `classification_complete=false` و `membership_resolved=true` عمدی و پذیرفته‌شده‌اند؛
- ۲۰۶ نماد پایین‌تر در تصمیم عضویت تأثیر ندارند و موج طبقه‌بندی دیگری لازم نیست.

مرحله جاری: **مادی‌سازی داده اجرایی + انجماد ورودی دقیق رانر**.
کد reusable در `production_runtime_data.py`، `production_runner_input.py` و
`production_input_vps.py` قرار دارد. داده بازار فقط برای اجتماع منجمد از AF-01C
خوانده می‌شود؛ اسکن خارج از اجتماع فقط هویت دفتر ماهانه را با آشتی پذیرفته‌شده
تطبیق می‌دهد. ۱ ساعت و ۴ ساعت با منطق پذیرفته‌شده `opportunity_data.views.derive`
و فقط bucket کامل ساخته می‌شوند. شکاف‌های ابتدا، انتها، ماه فاقد داده و bucket
ناقص به‌صورت صریح ثبت می‌شوند. هیچ شکافی ترمیم نمی‌شود.

رانر تولیدی ورودی آزاد نمی‌پذیرد. مسیر `ProductionRuntime.from_frozen_input`
فقط ماتریس نماد/بازه، عضویت، هزینه، نامزدها و داده دارای هش منجمد را مصرف می‌کند.
حالت آزمون مصنوعی به یک نامزد و شناسه داده `SYNTHETIC-` محدود است و freeze
تولیدی پذیرفته‌شده را قبول نمی‌کند. `run()` تولیدی پیش‌فرض بسته است و مجوز صریح
Director را لازم دارد؛ ابزارهای مادی‌سازی، freeze و verify هرگز آن را صدا نمی‌زنند.

وضعیت واقعی این PR: زیرساخت و تست، نه اجرای حجیم واقعی VPS.
تا دریافت خروجی واقعی VPS، داده ۵۲۵ مجموعه و هش نهایی runner input اثبات نشده‌اند.

- [x] عضویت ماهانه منجمد و شواهد واقعی VPS پذیرفته‌شده؛
- [x] ابزار reusable داده و انجماد ورودی رانر در این واحد کاری پیاده‌سازی شده؛
- [ ] مادی‌سازی واقعی ۱۷۵ × ۳ مجموعه روی VPS؛
- [ ] آشتی واقعی پوشش و شکاف‌ها و ثبت هش index؛
- [ ] انجماد واقعی runner input و ثبت هش مستقل؛
- [ ] verify روی همان HEAD بررسی‌شده و ثبت خروجی واقعی؛
- [ ] پذیرش صریح Director برای هر اجرای عملکرد بعدی.

**اجرای ۶٬۸۵۲ نامزد همچنان ممنوع است.** performance read=false؛ Fresh OOS و
recent reserve بسته و نخوانده؛ P10 read/write=false؛ LIVE_MASTER_LOCK=OFF؛
P11 قفل؛ PAPER/RESEARCH ONLY. شاخه RIE-006 و PR #152 دست‌نخورده می‌مانند.
قرارداد و دستور VPS در
`docs/research/alpha-factory/MCF-PROD-001-RUNTIME-INPUT-CONTRACT-v1.0.md` ثبت شده است.
