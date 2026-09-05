# Yahya AI Trading Lab

P0 شامل محیط قابل تکرار Python، بررسی اتصال عمومی Binance و ذخیره کندل‌ها در CSV است.
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

- فقط دو endpoint عمومی `GET /api/v3/ping` و `GET /api/v3/klines` روی میزبان‌های ثابت.
- بدون دریافت API key، خواندن فایل اعتبارنامه یا پشتیبانی از endpoint سفارش و حساب.
- timeout شبکه ۱۵ ثانیه، کنترل اندازه و قالب پاسخ، و توقف در خطای محدودیت نرخ.
- حداکثر ۱۰۰۰ کندل در هر اجرا؛ دانلود تاریخی صفحه‌بندی‌شده و تلاش مجدد هنوز پیاده‌سازی نشده‌اند.
- برای شروع نیازی به Docker، WSL، Jupyter یا Node.js نیست.

## مسیر بعدی

1. اتصال همین مخزن به یک repository خصوصی GitHub و اجرای CI.
2. تعریف بازار، تایم‌فریم و بازه داده موردنیاز.
3. دریافت تاریخی، تشخیص شکاف و کندل باز، سپس بک‌تست با کارمزد و لغزش قیمت.

وضعیت تست‌های همین تحویل در `docs/STATUS.md` ثبت شده است.
