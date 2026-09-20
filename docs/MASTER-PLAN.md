# YATL — نقشه مرجع اجرا و وضعیت پروژه

نسخه بازیابی و supersede‌شده: 2026-09-09
وضعیت جاری: **P0 تا P7 RUNTIME ACCEPTED AND MERGED**
قدم جاری: **P8-008 GUARDED DASHBOARD CLI / ATOMIC PUBLICATION — CANDIDATE**

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
| P8 Dashboard | نمایش وضعیت، معاملات، عملکرد و خطاها | **NEXT — implementation plan opened** |
| P9 Telegram | هشدار و کنترل محدود طبق قواعد امنیتی | شروع نشده |
| P10 Forward/Paper Validation | ارزیابی روی داده جدید، هزینه‌ها، افت سرمایه و تست خطا/توقف | شروع نشده |
| P11 Tiny Live Candidate | فقط پس از پذیرش P10، ممیزی امنیت، الزامات حساب و تأیید صریح | LOCKED |

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
| فازهای تحویل نرم‌افزاری P0 تا P9 | 8 از 10 | 2 فاز | **80% بر مبنای شمارش ساده فازها**؛ تخمین زمان یا حجم کار نیست |
| checkpointهای P7 | 10 از 10 | صفر | P7-001 تا P7-010 پذیرفته و روی `main` بسته شده‌اند |
| فازهای پیش از Forward Validation | P0 تا P7 | P8 تا P9 | پس از آن P10 باید روی داده جدید اجرا و پذیرفته شود |
| مسیر Live | هیچ | P5 تا P10 و ممیزی‌های P11 | P11 همچنان LOCKED و مشروط به تأیید صریح است |

### کار باقی‌مانده تا نسخه آزمایشی نرم‌افزار

1. P8: Dashboard local/read-only روی export پذیرفته‌شده P7.
2. P9: Telegram محدود و ایمن روی status/alertهای پذیرفته‌شده upstream.

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

بنابراین گزارش کوتاه این است: **80% فازهای نرم‌افزاری P0 تا P9 بسته شده‌اند؛
P7-001 تا P7-010 runtime accepted و merge شده‌اند و P8 مرحله بعدی است.** این عدد
پیشرفت مهندسی است، نه درصد آمادگی برای سود یا Live.

در گفت‌وگوی قبلی برای P10 بازه ۳۰–۶۰ روز واقعی بازار مطرح شده است؛ این تخمین است،
نه تضمین کافی‌بودن نمونه. تاریخ‌های قبلی پایان توسعه و شروع Live، تعهد اجرایی نیستند.
درصد وزنیِ زمان/حجم کار نداریم؛ درصد 80% بالا فقط شمارش ساده فازهای بسته‌شده است.
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
