# Yahya AI Trading Lab

P0، P1، P2 و P3 با شواهد runtime پذیرفته شده‌اند. P4 فاز فعال است؛
P4-007 روی `main` merge شده و P4-008 adapter محافظت‌شده P3→P4→P2 را برای
اعتبارسنجی GitHub آماده کرده است.
Python پروژه **3.12.14** است. تنها وابستگی خارجی، `websockets==17.1` برای اجرای
صحیح پروتکل WebSocket است و نسخه آن در `uv.lock` ثابت شده است.

## شروع در PowerShell

ترمینال را در پوشه همین مخزن باز کنید:

```powershell
uv sync --locked
uv run --locked python -m unittest discover -s tests
uv run --locked python -m yatl ping
uv run --locked python -m yatl candles --symbol BTCUSDT --interval 1h --limit 100
```

پیش‌فرض Spot Testnet است. برای دریافت داده عمومی بازار اصلی:

```powershell
uv run --locked python -m yatl --environment public candles --symbol BTCUSDT --interval 1h --limit 100
```

فایل‌ها در `data/testnet/` یا `data/public/` ذخیره می‌شوند و وارد Git نمی‌شوند.
فایل موجود بازنویسی نمی‌شود. مقدارهای اعشاری با دقت رشته دریافتی از صرافی حفظ می‌شوند.
زمان‌ها Unix milliseconds بر مبنای UTC هستند؛ آخرین کندل ممکن است هنوز بسته نشده باشد.
داده Testnet برای بررسی عملکرد است؛ ارزیابی استراتژی به داده واقعی و بررسی کیفیت نیاز دارد.

## محدوده این نسخه

- دو endpoint عمومی `GET /api/v3/ping` و `GET /api/v3/klines` روی میزبان‌های ثابت.
- فقط یک endpoint احرازهویت‌شده: `GET /api/v3/account` روی Spot Testnet؛ بدون endpoint سفارش.
- timeout شبکه ۱۵ ثانیه، کنترل اندازه و قالب پاسخ، و توقف در خطای محدودیت نرخ.
- هر صفحه حداکثر ۱۰۰۰ کندل دارد؛ دانلود تاریخی بازه‌دار، تلاش مجدد محدود و ذخیره SQLite پیاده‌سازی شده‌اند.
- برای شروع نیازی به Docker، WSL، Jupyter یا Node.js نیست.

## مسیر بعدی

مرجع ترتیب اجرا: [نقشه پروژه](docs/MASTER-PLAN.md).
وضعیت جاری **P0، P1، P2 و P3 پذیرفته‌شده در runtime** است. P1 در `4e77e34` بسته شد.
P2 بارگذاری point-in-time، ساعت رویداد، fill محافظه‌کارانه، هزینه، دفتر پرتفوی،
معیارها، artifact تکرارپذیر و شش سناریوی واقعی BTC/ETH را تکمیل کرده است. ممیزی
نهایی P2 همه این gateها را بازسازی و تأیید می‌کند. P3 در `90d5847` بسته شد؛
P4-001 تا P4-007 نیز به‌ترتیب پذیرفته و روی `main` merge شده‌اند و P4-008 اکنون
در حال اعتبارسنجی است. ترتیب و معیارهای P4 در `docs/P4-IMPLEMENTATION-PLAN.md`
قفل شده‌اند.

P3-001 قرارداد research-only سیگنال را اضافه می‌کند. تصمیم فقط یکی از `NO_TRADE`،
`ENTER_LONG` یا `EXIT_LONG` است و به context نقطه‌زمانی و digest آن متصل می‌شود.
این قرارداد هیچ quantity، حساب، credential، broker یا مسیر سفارش ندارد.

```powershell
uv run --locked python -m yatl strategy-contract-check
```

P3-002 هفت feature دقیق را روی candleهای بسته و قبل از زمان تصمیم محاسبه می‌کند:
بازده ساده، rolling high/low، SMA، EMA و Wilder ATR/RSI. EMA با SMA اولیه و
`2/(period+1)` آغاز می‌شود؛ ATR و RSI از Wilder smoothing استفاده می‌کنند. warm-up
ناکافی صریحاً unavailable است و candle آینده حتی اگر تغییر کند روی مقدار گذشته اثر ندارد.

```powershell
uv run --locked python -m yatl strategy-feature-check
```

P3-003 رژیم 4h را با قواعد پژوهشی ثابت `SMA_4H_V1` و حداقل ۵۱ کندل بسته
تشخیص می‌دهد. خروجی صعودی، نزولی، خنثی یا نامشخص است؛ تضاد شواهد به
`UNKNOWN` می‌رسد. فرمول‌ها و آستانه‌های دقیق در برنامه P3 ثبت شده‌اند.
فرمان زیر داده تاریخی پذیرفته‌شده BTC/ETH را فقط خواندنی بررسی می‌کند:

```powershell
uv run --locked python -m yatl strategy-regime-check
```

وضعیت تست‌های همین تحویل در `docs/STATUS.md` ثبت شده است.

بررسی محلی قرارداد P2-001:

```powershell
uv run --locked python -m yatl backtest-contract-check
```

این بررسی ثابت می‌کند تصمیم فقط داده بسته و قابل‌مشاهده در همان لحظه را می‌بیند و
سیاست fill روی open بعدی 1h قفل است. هیچ سفارش صرافی یا credential استفاده نمی‌شود.

P2-002 دیتابیس پذیرفته‌شده P1 را فقط read-only و پس از قبولی manifest بارگذاری می‌کند:

```powershell
uv run --locked python -m yatl backtest-load-check --symbol BTCUSDT --hours 24
uv run --locked python -m yatl backtest-load-check --symbol ETHUSDT --hours 24
```

هر snapshot فقط کندل‌هایی را برمی‌گرداند که پیش از زمان تصمیم بسته شده‌اند. اختلاف
schema، بازه، تعداد، gap، کندل باز یا manifest باعث توقف می‌شود.

P2-003 رویدادهای تصمیم را روی مرزهای دقیق 1h و به‌ترتیب قطعی تولید می‌کند:

```powershell
uv run --locked python -m yatl backtest-clock-check --symbol BTCUSDT --hours 24
```

این فرمان ساعت را دوبار replay می‌کند و فقط در صورت برابری کامل ترتیب و snapshotها
PASS می‌شود. زمان fill مجاز، open کندل اصلی بعد از داده مشاهده‌شده است؛ قیمت آن کندل
داخل snapshot تصمیم قرار نمی‌گیرد.

P2-004 چرخه محلی ENTER_LONG / HOLD / EXIT_LONG را بدون اتصال به صرافی شبیه‌سازی
می‌کند. اگر Stop و Target در یک کندل لمس شوند و ترتیب درون کندل معلوم نباشد، Stop
به‌صورت محافظه‌کارانه مقدم است. gap شناخته‌شده در open پیش از حرکت درون کندل بررسی
می‌شود و fillهای یک کندل نمی‌توانند از base volume آن بیشتر باشند.

```powershell
uv run --locked python -m yatl backtest-fill-check
```

خروجی P2-004 فقط `FillReference` است. fee و slippage هنوز روی آن اعمال نشده‌اند و
در P2-005 پیش از ورود به حسابداری اجباری خواهند شد.

P2-005 هر FillReference را با دقت داخلی ۲۵۶رقمی به CostedFill تبدیل می‌کند. slippage
برای خرید قیمت را افزایش و برای فروش کاهش می‌دهد؛ fee روی ارزش واقعی fill محاسبه
می‌شود. حسابداری پول و دارایی از float استفاده نمی‌کند.

```powershell
uv run --locked python -m yatl backtest-cost-check
```

این بررسی fee، slippage و اثر خالص نقدی یک رفت‌وبرگشت محافظه‌کارانه را با Decimal
گزارش می‌کند. افزایش هزینه در تست‌ها هرگز نتیجه نقدی را بهتر نمی‌کند.

P2-006 دفتر دقیق cash، دارایی، cost basis، سود تحقق‌یافته/نشده و equity قابل‌تسویه
را اضافه می‌کند. fill تکراری، خروج ناقص، موجودی ناکافی و سیاست هزینه متفاوت رد می‌شود.

```powershell
uv run --locked python -m yatl backtest-portfolio-check
```

P2-007 معیارهای قطعی بازده، تعداد و نرخ برد، سود ناخالص/خالص، هزینه کل، افت سرمایه
و نسبت‌های توصیفی ریسک را فقط برای منحنی کامل و بسته‌شده محاسبه می‌کند. نمونه ناکافی
یا مخرج صفر با مقدار تعریف‌نشده گزارش می‌شود و حدس زده نمی‌شود.

```powershell
uv run --locked python -m yatl backtest-metrics-check
```

P2-008 یک manifest قطعی JSON می‌سازد که هویت داده، تنظیمات، seed، نسخه موتور،
digest ورودی، معاملات، خلاصه منحنی سرمایه و معیارها را نگه می‌دارد. خروجی به‌صورت
اتمی نوشته می‌شود و مسیر محلی، credential و زمان اجرای سیستم در آن جایی ندارد.

```powershell
uv run --locked python -m yatl backtest-artifact-check
```

P2-009 سه سناریوی ازپیش‌تعیین‌شده را روی داده واقعی پذیرفته‌شده BTCUSDT و ETHUSDT
اجرا می‌کند: بدون معامله، یک رفت‌وبرگشت و سه معامله کنترل‌شده. هر اجرا دوباره پخش
می‌شود و نتیجه دارای هزینه باید از همان سناریو با هزینه صفر ضعیف‌تر باشد.

```powershell
uv run --locked python -m yatl backtest-scenario-check
```

ممیزی نهایی P2، manifest پذیرفته‌شده P1، هر شش سناریو، هشت معامله، حسابداری،
digest ورودی و نتیجه و نبود مسیر اجرای سفارش را مستقل بررسی می‌کند:

```powershell
uv run --locked python -m yatl p2-audit
```

## تمرین دستی و قابل‌تکرار Paper

فایل `fixtures/p0-paper-workflows.json` دو سناریوی آموزشی ثابت برای BTCUSDT و
ETHUSDT دارد. قیمت‌ها سیگنال بازار نیستند و فقط برای تمرین محاسبات استفاده می‌شوند.

```powershell
uv run --locked python -m yatl paper-check
```

هر سناریو این فیلدها را دارد:

- `entry`: قیمت فرضی ورود؛
- `stop`: خروج فرضی برای محدودکردن زیان؛
- `target`: هدف فرضی سود؛
- `position_size`: تعداد واحد دارایی، نه مبلغ دلاری؛
- `account_equity` و `risk_percent`: مبنای سقف زیان؛
- `max_loss`، `potential_reward` و `risk_reward_ratio`: نتایج قابل‌بازبینی محاسبه.

اعتبارسنجی فقط محلی است و هیچ درخواست شبکه یا سفارشی تولید نمی‌کند. فقط Spot،
Long-only، BTCUSDT/ETHUSDT، ریسک حداکثر ۱٪، نسبت ریسک/بازده حداقل ۲ و
`LIVE_MASTER_LOCK=OFF` پذیرفته می‌شوند. اندازه معامله نباید ارزش اسمی بیشتر از
سرمایه فرضی داشته باشد؛ بنابراین اهرم رد می‌شود. 1h تایم‌فریم اصلی، 4h تشخیص
وضعیت و 15m زمینه ورود است. 5m در P0 غیرفعال است.

## خواندن امن حساب Spot Testnet

در ویرایشگر متن، فایل محلی `.env` را مطابق `.env.example` پر کنید.
کلید HMAC-SHA-256 باید فقط USER_DATA داشته باشد؛ TRADE و USER_STREAM خاموش بمانند.
کلید یا Secret را در فرمان ترمینال، پیام یا Git قرار ندهید.
`YATL_ENVIRONMENT=testnet` و `LIVE_MASTER_LOCK=OFF` الزامی هستند.

```powershell
uv run --locked python -m yatl account
```

خروجی فقط موفقیت، نوع SPOT و تعداد دارایی‌ها/موجودی‌های غیرصفر آزمایشی را نشان می‌دهد.
کلید، Secret، امضا، شناسه حساب و مقدار موجودی چاپ یا ذخیره نمی‌شوند.
برای مسیر دیگر از `account --env-file PATH` استفاده کنید؛ پیش‌فرض `.env` در پوشه جاری است.
فرمان `--environment public account` پیش از خواندن اعتبارنامه یا اتصال رد می‌شود.

فایل حداکثر ۱۶ KiB و دقیقاً شامل چهار متغیر نمونه است. UTF-8 با یا بدون BOM، خط خالی،
توضیح تمام‌خط با `#` و مقدار ساده یا دارای جفت کوتیشن پشتیبانی می‌شوند.
متغیر تکراری/ناشناخته، مقدار ناقص و تنظیمات متناقض محیط فرایند رد می‌شوند.
فایل اجرا نمی‌شود؛ درون‌یابی انجام نمی‌شود و متغیرهای فرایند تغییر نمی‌کنند.

درخواست با HMAC-SHA-256، ساعت سیستم برحسب میلی‌ثانیه و `recvWindow=5000` امضا می‌شود.
فقط URL دقیق `https://testnet.binance.vision/api/v3/account` با GET مجاز است.
Redirect و پراکسی محیط برای این درخواست غیرفعال‌اند؛ اعتبارسنجی پیش‌فرض TLS فعال است.
timeout برابر ۱۵ ثانیه است؛ خطای شبکه/API، پاسخ نامعتبر یا بزرگ‌تر از ۲ MB باعث توقف می‌شود.
تلاش مجدد خودکار وجود ندارد. در صورت رد درخواست، ساعت سیستم و مجوز USER_DATA را بررسی کنید.

فیلد `canTrade` قابلیت حساب است و اثبات مجوز TRADE برای کلید نیست.
این فرمان مجوزهای کلید را تغییر نمی‌دهد یا مستقلاً ممیزی نمی‌کند؛ محدودیت USER_DATA
باید در مدیریت Testnet حفظ شود. هیچ درخواست معامله‌ای برای آزمایش مجوز ارسال نمی‌شود.

**PAPER ONLY · NO FUTURES · NO LEVERAGE · NO WITHDRAWAL API · NO AI DIRECT EXECUTION · LIVE_MASTER_LOCK=OFF**

مرجع: [مستندات رسمی Spot Testnet](https://github.com/binance/binance-spot-api-docs/blob/master/testnet/rest-api.md).

## وضعیت P1

P1-001 قرارداد استاندارد Candle را برای داده عمومی Spot تعریف می‌کند. تنظیمات این لایه
فقط `BTCUSDT` و `ETHUSDT`، تایم‌فریم‌های `15m`، `1h` و `4h` و میزبان عمومی ثابت
Binance را می‌پذیرد. قیمت و حجم به‌صورت رشته اعشاری نگه‌داری می‌شوند تا دقت ورودی
از بین نرود. timestampها باید دقیقاً روی مرز UTC تایم‌فریم باشند و وضعیت کندل باز/بسته
صریح است. این مرحله transport شبکه، WebSocket، SQLite یا execution ندارد.

کلاینت عمومی P1-002 فقط سه مسیر GET مربوط به زمان سرور، اطلاعات یک symbol و klines
را روی میزبان اصلی Binance Spot می‌پذیرد. برای بررسی زنده بدون credential:

```powershell
uv run --locked python -m yatl data-check
```

این فرمان برای BTCUSDT و ETHUSDT وضعیت بازار و دو کندل 1h را بررسی می‌کند، چیزی
روی دیسک نمی‌نویسد و به `.env` دست نمی‌زند. دانلود تاریخی صفحه‌بندی‌شده در P1-003
به‌صورت بازه نیمه‌باز و محدود پیاده‌سازی شده است. بررسی زنده آن:

```powershell
uv run --locked python -m yatl history-check
```

این بررسی برای هر دو symbol و هر سه تایم‌فریم، دو کندل بسته را با صفحه‌های یک‌ردیفی
می‌گیرد تا pagination واقعی آزمایش شود. چیزی ذخیره نمی‌شود. نرمال‌سازی REST/WebSocket
و تعیین نهایی وضعیت کندل در P1-004 پیاده‌سازی شده است. بررسی زنده:

```powershell
uv run --locked python -m yatl normalize-check
```

REST با زمان سرور Binance و WebSocket با فیلد رسمی `x` وضعیت کندل را تعیین می‌کند.
payload خام و combined stream به قرارداد Candle یکسان تبدیل می‌شوند. اتصال زنده WebSocket
هنوز شروع نشده و متعلق به P1-007 است؛ P1-004 فقط قالب ثبت‌شده آن را تست می‌کند.

P1-005 یک پایگاه داده SQLite نسخه‌دار با کلید یکتای
`(source, symbol, interval, open_time_ms)` اضافه می‌کند. اجرای تکراری، ردیف دوم
نمی‌سازد؛ کندل باز می‌تواند به‌روزرسانی و سپس بسته شود، اما تغییر یا بازکردن دوباره
کندل بسته با خطا متوقف می‌شود. نوشتن گروهی تراکنشی است و در صورت تعارض کامل rollback
می‌شود. فایل‌های runtime زیر `data/` و خارج از Git باقی می‌مانند.

```powershell
uv run --locked python -m yatl storage-check
```

این فرمان یک پایگاه داده موقت می‌سازد، چرخه ذخیره و بازگشایی را بررسی می‌کند و فایل
موقت را حذف می‌کند. هیچ credential یا endpoint اجرایی استفاده نمی‌شود.

P1-006 زمان‌های کندل را فقط روی شبکه دقیق UTC همان تایم‌فریم بررسی می‌کند. duplicateها
پیش از persistence قابل تشخیص‌اند و کلید یکتای SQLite نیز از تکرار در پایگاه داده
جلوگیری می‌کند. کندل باز فعلی که هنوز دریافت نشده، شکاف تاریخی محسوب نمی‌شود.
شکاف‌های تاریخی پیوسته به بازه‌های نیمه‌باز و محدود برای repair تبدیل می‌شوند؛ این
مرحله هیچ دانلود یا repair خودکاری انجام نمی‌دهد.

```powershell
uv run --locked python -m yatl quality-check
```

این بررسی کاملاً محلی و deterministic است و شبکه، credential یا اجرای معامله ندارد.

P1-007 فقط از combined kline stream عمومی و market-data-only روی
`data-stream.binance.vision` استفاده می‌کند. subscriptionها به BTCUSDT/ETHUSDT و
15m/1h/4h محدودند. پیام‌ها normalize و idempotent ذخیره می‌شوند؛ پیام عقب‌افتاده
رد می‌شود. قطع اتصال حداکثر دو reconnect با backoff سقف‌دار دارد و فاصله بسته‌شده
را با REST در حداکثر ۱۰۰۰ کندل backfill می‌کند.

```powershell
uv run --locked python -m yatl stream-check --symbol BTCUSDT --interval 1h --messages 1
```

این بررسی یک پیام زنده عمومی را در SQLite حافظه‌ای ثبت می‌کند و سپس اتصال را می‌بندد.
هیچ `.env`، API key، user stream یا endpoint اجرایی استفاده نمی‌شود.

P1-008 برای هر بازه، اولین/آخرین timestamp، تعداد کل و یکتا، open/closed، duplicate،
gap، repair range، malformed/conflicting، freshness و آمادگی backtest را گزارش می‌کند.
کندل باز فعلی می‌تواند در داده باشد، ولی از شمارش بسته جداست؛ کندل باز تاریخی، شکاف
حل‌نشده یا تعارض باعث FAIL و کد خروج غیرصفر می‌شود.

```powershell
uv run --locked python -m yatl health-check
uv run --locked python -m yatl health-check --json
```

این مرحله از fixture محلی canonical استفاده می‌کند. اتصال گزارش به dataset واقعی در
P1-009 انجام می‌شود.

P1-009 با فرمان زیر ۳۰ روز کندل بسته عمومی واقعی را برای هر دو نماد و هر سه
تایم‌فریم می‌سازد:

```powershell
uv run --locked python -m yatl dataset-build --days 30
```

SQLite در `data/p1/market.sqlite3` و خارج از Git است. manifest قابل‌ممیزی در
`manifests/p1-market-data.json` ثبت می‌شود. اجرای مجدد idempotent است و فقط
timestampهای گمشده را دریافت می‌کند. هر dataset باید بدون open candle، duplicate، gap،
malformed یا conflict و با `backtest_ready=true` باشد.

دروازه نهایی P1، manifest ثبت‌شده را بدون شبکه و credential بررسی می‌کند:

```powershell
uv run --locked python -m yatl p1-audit
```

قبولی آن مستلزم دقیقاً شش مجموعه، ۷۵۶۰ کندل بسته، پوشش ۳۰روزه، تازگی داده و
صفر gap، duplicate، malformed، conflict و open row است. این فرمان سفارش یا
درخواست احرازهویت‌شده نمی‌سازد. شواهد دقیق پذیرش P1 در `docs/STATUS.md` ثبت شده است.

## P3-004 — Frozen research configuration

Versioned strategy definitions declare bounded integer or exact decimal-string parameters.
Configuration is immutable; canonical JSON and SHA-256 include the ID, version, schema,
bounds, values and fixed paper policy. Duplicate ID/version pairs, unknown/missing fields,
invalid numeric types and out-of-range values fail closed. Different versions may coexist.
Limits: 128 definitions, 32 parameters per definition, numeric bounds from 0 to 10000.
Cross-parameter candidate rules belong to the later candidate implementation.
The runtime fixture is a registry check, not a trading strategy or tuned parameter set.

```powershell
uv run --locked python -m yatl strategy-registry-check
```

P3-004: 225 tests passed; runtime replay, changed-digest and rejection gates passed.

## P3-005 — Trend-pullback research candidate

The frozen `TREND_PULLBACK` version `1.0.0` requires an accepted 4h up regime,
a closed 1h pullback through SMA(20) followed by a close above it, and bullish
confirmation from the latest two closed 15m candles. Its invalidation is the
three-bar 1h low minus 0.25 ATR(14); its target is two times that visible risk.
Insufficient history, blocked/unknown regime, absent setup and failed confirmation
produce explicit no-trade decisions. Existing research state has deterministic
hold and exit rules. No account quantity or execution capability exists here.

```powershell
uv run --locked python -m yatl strategy-trend-check
```

P3-005: 234 tests passed. Accepted historical runtime replay returned
BTCUSDT `NO_TRADE/REGIME_UNKNOWN` and ETHUSDT
`ENTER_LONG/TREND_PULLBACK_ENTRY`. These are integration observations, not
performance evidence or trading instructions. P3-005 was accepted in `a4a8ef8`.
PAPER ONLY; LIVE_MASTER_LOCK=OFF.

## P3-006 — Range-breakout research candidate

The independent frozen `RANGE_BREAKOUT/1.0.0` candidate requires a 4h up
regime and a closed 1h close above the highest high of the preceding 20 bars.
It rejects a breakout when the close is below the top 25% of its candle or its
extension exceeds one prior ATR(14). The latest two closed 15m candles provide
bullish confirmation. Invalidation is the breakout-candle low minus 0.25 prior
ATR and the target is 2R. False breakouts and regime loss have explicit exits.

```powershell
uv run --locked python -m yatl strategy-breakout-check
```

P3-006: 243 tests passed. Accepted historical replay returned
BTCUSDT `NO_TRADE/REGIME_UNKNOWN` and ETHUSDT
`NO_TRADE/SETUP_ABSENT`. This is integration evidence only. P3-006 was
accepted in `1e8ffb0`. PAPER ONLY; LIVE_MASTER_LOCK=OFF.

## P3-007 — Signal lifecycle and P2 paper adapter

`ResearchSignalAdapter` accepts only the two registered P3 identities and
approved BTCUSDT/ETHUSDT symbols. It translates strategy decisions into the
accepted P2 `HOLD`, `ENTER_LONG` and `EXIT_LONG` intents, then delegates
next-open and protective fills to the P2 engine. It rejects duplicate,
out-of-order and overlapping signals without consuming the failed event.

The adapter uses the fixed fixture quantity `0.001`; callers cannot supply or
calculate quantity. P4 remains responsible for future risk-based sizing.
Protective Stop/Target behavior, ambiguous Stop priority, fees and slippage
remain the accepted P2 policies.

```powershell
uv run --locked python -m yatl strategy-adapter-check
```

P3-007: 253 tests passed. The deterministic runtime round trip produced two
fills, applied costs, closed one paper trade and finished flat. P3-007 was
accepted in `2e43a12`. PAPER ONLY; LIVE_MASTER_LOCK=OFF.

## P3-008 — Evaluation and anti-overfitting protocol

Each candidate evaluation is bound to an immutable strategy version,
configuration SHA-256, separate training/evaluation windows and exactly two
symbol reports. Qualification requires at least 180 evaluation days, 30 closed
trades per symbol and 60 pooled, three chronological segments, deterministic
replay, point-in-time proof and future-data isolation.

After sample sufficiency, each symbol must beat the zero-return no-trade
reference and its own Buy-and-Hold return, remain within the absolute and
Buy-and-Hold drawdown limits, and pass multi-segment stability. The result is
one of `INSUFFICIENT_EVIDENCE`, `REJECTED` or
`QUALIFIED_FOR_P4_RESEARCH`. Qualification is never trading approval.

```powershell
uv run --locked python -m yatl strategy-evaluation-check
```

P3-008: 265 tests passed. Runtime reproduced all three labels and a canonical
report. Mutating data after the frozen cutoff leaves the input digest unchanged;
mutating visible data changes it. The current 30-day dataset cannot pass the
180-day evidence gate.

## P3-009 — Accepted public-data candidate runs

The accepted 30-day BTCUSDT and ETHUSDT Spot checkpoint can be reconstructed
without credentials and both frozen candidates can then be replayed through the
P2 paper lifecycle:

```powershell
uv run --locked python -m yatl dataset-restore-checkpoint
uv run --locked python -m yatl strategy-candidate-check
```

Each candidate/symbol run records costed and zero-cost artifacts, no-trade and
Buy-and-Hold baselines, a point-in-time decision trace, cost drag and future-data
isolation proof. GitHub Actions runs the matrix twice and requires a recursive
byte-equal diff before publishing the 21-file evidence artifact.

Runtime on 2026-09-12 produced index SHA-256
`59f0af64843baeb2ecf593142e3247be190bb24c8768de80dd971bc677d8e92a`.
`TREND_PULLBACK/1.0.0` closed 31 pooled trades and
`RANGE_BREAKOUT/1.0.0` closed 4; both remain honestly labelled
`INSUFFICIENT_EVIDENCE` because the 20-day evaluation window and per-symbol/
pooled trade minima do not satisfy the frozen P3 protocol. No parameter was
changed in response to the result. P3-010 final-audit evidence follows.

## P3-010 — Final deterministic audit

The final audit independently rebuilds and byte-compares the complete P3 evidence
set, validates every embedded P2 artifact and enforces the frozen configuration,
trade-count, label and safety contracts:

```powershell
uv run --locked python -m yatl p3-audit
```

GitHub Actions run `34699232936` passed the complete 283-test suite and three
deterministic matrix computations. Each produced index SHA-256
`59f0af64843baeb2ecf593142e3247be190bb24c8768de80dd971bc677d8e92a`.
The final audit verified 2 candidates, 2 symbols, 4 runs, 21 evidence files,
16 P2 artifacts and 35 closed trades. Both candidates remain
`INSUFFICIENT_EVIDENCE`; P3 framework runtime is accepted without a profitability
claim or trade permission.

## P4-001 — Independent risk contract

P4 starts with immutable Paper-only policy, portfolio-state, request and decision
records. Each request binds the exact P3 context, evidence label and point-in-time
portfolio state to a canonical SHA-256:

```powershell
uv run --locked python -m yatl risk-contract-check
```

The frozen `P4_RISK_V1` contract prevents an `INSUFFICIENT_EVIDENCE` candidate
from receiving entry approval. A Kill Switch blocks new exposure but never a
matching risk-reducing exit. This step does not yet implement position sizing or
the circuit-breaker engine and cannot submit an exchange order.

GitHub Actions run `34701891824` passed all **293 tests**, the deterministic P4
runtime check, safety scans and the unchanged P3 evidence replay. P4-001 was
accepted and merged in `be3c042`.

## P4-002 — Exact loss-budget position sizing

The sizing layer computes a qualified Paper fixture quantity from the 1% equity
loss budget, entry and stop, including the accepted P2 fee/slippage defaults. It
uses isolated high-precision Decimal arithmetic and always rounds downward to the
frozen `0.000001` research step:

```powershell
uv run --locked python -m yatl risk-sizing-check
```

Current candidates remain blocked before sizing because their evidence is
insufficient. This step returns a sizing record, not a trade approval; cash,
notional and exposure limits belong to P4-003. No exchange order is possible.
GitHub Actions run `34702613220` passed all **305 tests**, deterministic sizing,
safety scans and unchanged P3 evidence gates. Qualified-fixture quantity was
`9.708733` for a `100.00` budget with planned loss `99.9999984436650`.
P4-002 was runtime accepted and merged in `bc2bd30`.

## P4-003 — Cash, notional and exposure limits

The limit layer checks the P4-002 quantity against available cash, entry fee,
the 25% single-position cap and the 25% gross-exposure cap:

```powershell
uv run --locked python -m yatl risk-limit-check
```

It returns canonical PASS/REJECT evidence only. It cannot approve a trade, borrow
cash, use leverage or submit an order. State transitions remain P4-004.
GitHub Actions run `34714934702` passed all **314 tests**, safety scans, the exact
limit runtime and unchanged accepted-public-data replay/audit gates. Runtime
recorded `normal=PASS/WITHIN_LIMITS`,
`low_cash=REJECT/CASH_INSUFFICIENT`, notional `1019.9266734825` and cap
`2500.00`. P4-003 was runtime accepted and merged in `27dfd86`.

## P4-004 — Point-in-time portfolio/session state

The state layer accepts complete hourly paper-ledger observations in a strict
sequence and produces a canonical SHA-256-linked state chain:

```powershell
uv run --locked python -m yatl risk-state-check
```

It deterministically maintains UTC session start equity, session realized PnL,
all-time equity peak, gross Spot exposure and consecutive closed losses. Missing,
duplicate, stale, out-of-order, cross-symbol and semantically inconsistent updates
fail closed. GitHub Actions run `34717094100` passed all **326 tests**, safety
scans, the new state runtime and unchanged public-data replay/audit gates. The
loss fixture ended at sequence 2 with session PnL `-100`, one consecutive loss,
zero exposure and state SHA-256
`1b6700b922e2f7f6693b381222c81ebc10a1362c01dc4eca576dc6cb02e05bd0`.
P4-004 was runtime accepted and merged in `99cd8d5`; circuit-breaker decisions
remain P4-006 and no trade approval or order is emitted.

## P4-005 — Protective-level and post-cost gate

The protective gate independently recomputes adverse entry, stop and target
execution prices, both-side fees, worst planned loss and target reward after all
accepted P2 costs:

```powershell
uv run --locked python -m yatl risk-protective-check
```

A valid setup must retain a reachable stop below entry, stay inside the frozen 1%
loss budget and have strictly positive post-cost reward. Prior cash/exposure
rejection has deterministic priority. The gate produces immutable SHA-256-bound
PASS/REJECT evidence only. Local verification passed all **338 tests**; GitHub
Actions run `34747422371` then passed the complete suite, safety scans, protective
runtime and unchanged public-data replay/audit gates. Runtime recorded
`normal=PASS/PROTECTIVE_GATE_PASSED`,
`weak_target=REJECT/NON_POSITIVE_POST_COST_REWARD`, worst loss
`99.9999984436650`, net reward `93.8834966536650` and gate SHA-256
`950dd5ed79315453701b122ddd2e3a93b9002d8c2e1628e5ba3e89d048718ae9`.
P4-005 is runtime accepted and PR #7 was squash-merged in `41411ef`. No approval
or order is emitted.

## P4-006 — Loss and drawdown circuit breakers

The circuit layer binds a risk request to the exact managed portfolio-state SHA,
then evaluates the frozen 2% session loss, 10% peak-to-current drawdown and three-
loss streak limits using isolated 256-digit Decimal arithmetic:

```powershell
uv run --locked python -m yatl risk-circuit-check
```

Every exact boundary blocks new entry. A later valid state clears the relevant
condition only when it is strictly back inside its limit; UTC session reset clears
session loss and a recorded win/breakeven clears the loss streak. Risk-reducing
exits are never blocked. The immutable result records stable breaker order and a
material SHA-256, but does not latch a Kill Switch or emit approval/execution.
GitHub Actions run `34749363210` passed 14 focused circuit tests, 69 focused P4
tests, the complete **352/352** suite and every safety/runtime gate. The accepted
public checkpoint rebuilt 6 datasets and 7,560 closed rows; two candidate runs
were byte-identical and the independent audit retained index SHA-256
`59f0af64843baeb2ecf593142e3247be190bb24c8768de80dd971bc677d8e92a`.
Final HEAD GitHub Actions run `34749628926` also passed both jobs. P4-006 was
squash-merged from PR #8 in checkpoint `98320df`.

## P4-007 — Fail-closed Kill Switch state machine

The Paper Kill Switch begins active on every fresh startup, consumes ordered
P4-006 circuit evidence and records every transition in a canonical SHA-256 chain:

```powershell
uv run --locked python -m yatl risk-kill-switch-check
```

A circuit trigger latches the switch. Later clear observations cannot reset it;
only an explicit manual-reset event with newer clear circuit evidence can return
the state to inactive. Duplicate, missing, stale or out-of-order events and reused
circuit evidence fail closed. Entry is blocked while active, while a matching
risk-reducing exit remains permitted. Local verification passed 13 focused Kill
Switch tests, 82 focused P4 tests and all **365/365** tests. Final HEAD GitHub
Actions run `34754437777` passed both jobs, including every safety/runtime gate, reconstruction
of 6 public datasets and 7,560 closed rows, two byte-identical candidate matrices
and the unchanged independent P3 audit. P4-007 was squash-merged from PR #9 in
checkpoint `e09dc0e`.

## P4-008 — Guarded P3-to-P2 Paper adapter

The new adapter binds the original P3 decision, P4 request, managed portfolio
state, latest circuit assessment, Kill Switch state and protective evidence into
one deterministic authorization before invoking the frozen P2 Paper adapter:

```powershell
uv run --locked python -m yatl risk-adapter-check
```

Qualified entry requires complete matching evidence, a clear latest circuit and
an inactive Kill Switch. The exact P4-approved quantity is the only quantity that
can reach P2. Missing or insufficient evidence becomes `HOLD` with no fill;
existing positions can still exit atomically under an active Kill Switch. The
accepted P3 `ResearchSignalAdapter` remains unchanged and is restricted to frozen
research replay. Local verification passed 16 adapter tests, 98 focused P4 tests
and all **381/381** tests. GitHub Actions run `34764015703` passed both jobs and
all safety/runtime gates. Runtime recorded entry quantity `18.894653`, blocked an
insufficient-evidence entry, closed the position under Kill Switch and produced
authorization SHA-256
`3c65d4dca84c2ef17b73130461ee19552e3279a4b7a9753f0206fd8628b0ae72`.
The accepted public checkpoint rebuilt 6 datasets and 7,560 closed rows; two
candidate matrices were byte-identical and the independent audit retained 2
candidates, 2 symbols, 4 runs, 21 files, 16 P2 artifacts and 35 trades with index
SHA-256 `59f0af64843baeb2ecf593142e3247be190bb24c8768de80dd971bc677d8e92a`.
Both labels remain `INSUFFICIENT_EVIDENCE`. Final HEAD run `34764434584` also
passed both jobs. P4-008 was squash-merged from PR #10 in checkpoint `b268fa7`.

## P4-009 — Deterministic adversarial scenario matrix

The P4 matrix replays eight fail-closed scenarios for each accepted BTCUSDT and
ETHUSDT public Spot dataset: exact session-loss boundary, missing expected fill
candle, post-cost rejection, consecutive-loss boundary, drawdown boundary, stale
state, insufficient evidence and a risk-reducing exit under active Kill Switch:

```powershell
uv run --locked python -m yatl risk-scenario-check
```

Every one of the 16 runs emits canonical secret-free JSON. The complete matrix is
executed twice and the two evidence directories must be byte-identical before the
index is published. Existing output is never overwritten. Local verification has
passed 11 scenario tests, 109 focused P4 tests and the complete **392/392** suite.
GitHub Actions run `34769959024` passed both jobs and every safety/runtime gate.
The accepted public checkpoint rebuilt 6 datasets and 7,560 closed rows; both P4
matrices were byte-identical and produced index SHA-256
`56c945c38571af294bb44bfd7e788f314d9ee3e9fc76457c6bedb018daae0783`.
The unchanged P3 audit retained 35 trades and both candidate labels remain
`INSUFFICIENT_EVIDENCE`. P4-009 is runtime accepted on PR #11; merge is pending.
