# Yahya AI Trading Lab

P0 شامل محیط قابل تکرار Python، داده عمومی Binance و خواندن امن حساب Spot Testnet است.
Python پروژه **3.12.14** است و هیچ وابستگی خارجی Python ندارد.

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
- حداکثر ۱۰۰۰ کندل در هر اجرا؛ دانلود تاریخی صفحه‌بندی‌شده و تلاش مجدد هنوز پیاده‌سازی نشده‌اند.
- برای شروع نیازی به Docker، WSL، Jupyter یا Node.js نیست.

## مسیر بعدی

مرجع ترتیب اجرا: [نقشه پروژه](docs/MASTER-PLAN.md).
وضعیت جاری **P0 در حال تکمیل** است؛ موفقیت اتصال حساب به معنای پایان P0 نیست.
قدم بعدی: آموزش و تمرین دستی Paper، ممیزی نهایی P0، سپس P1 (لایه داده).
GitHub/CI و کیفیت داده در نقشه پیگیری می‌شوند و جای تمرین و پذیرش P0 را نمی‌گیرند.

وضعیت تست‌های همین تحویل در `docs/STATUS.md` ثبت شده است.

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
