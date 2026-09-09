# Yahya AI Trading Lab

P0 پذیرفته شده است و P1 لایه داده عمومی Binance Spot را مرحله‌به‌مرحله می‌سازد.
Python پروژه **3.12.14** است. تنها وابستگی خارجی، `websockets==17.1` برای اجرای
صحیح پروتکل WebSocket است و نسخه آن در `uv.lock` ثابت شده است.

## شروع در PowerShell

ترمینال را در پوشه همین مخزن باز کنید:

```powershell
uv sync --locked
uv run --locked python -m unittest discover -s tests -v
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
وضعیت جاری **P0 پذیرفته‌شده و P1 در حال اجرا** است.
P1-006 در `c63d88e` checkpoint شده و P1-007 WebSocket عمومی بازار را تکمیل کرده
است. قدم بعدی پس از checkpoint تمیز، P1-008 (گزارش سلامت داده) است. P2 هنوز
شروع نشده است.

وضعیت تست‌های همین تحویل در `docs/STATUS.md` ثبت شده است.

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
