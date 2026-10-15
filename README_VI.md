# Stock AI GitHub – bản hoàn chỉnh

## Chức năng
- GitHub Pages dashboard.
- GitHub Actions quét khoảng 30 phút/lần.
- Google News RSS.
- Giá Yahoo Finance.
- RSI, MFI, StochK, MACD, EMA5/10/20, Volume MA20.
- BUY4 = BẮT ĐÁY theo điều kiện đã thống nhất.
- EMA = MUA MẠNH: cả EMA5 cắt EMA10 và EMA10 cắt EMA20 cùng phiên.
- AI OpenAI hoặc Gemini.
- Telegram cảnh báo.
- Dashboard JSON, không dùng SQLite.
- Login giao diện + nhớ 30 ngày.

## GitHub Secrets
Tạo tại Settings → Secrets and variables → Actions → Secrets → New repository secret:

STOCK_TICKERS = APG,MSR,VPB,VPG,PET,SGR,VPI,HHP
AI_PROVIDER = gemini (hoặc openai)
GEMINI_API_KEY = key Gemini
GEMINI_MODEL = gemini-2.5-flash
OPENAI_API_KEY = key OpenAI
OPENAI_MODEL = gpt-4.1-mini
TELEGRAM_ENABLED = 1
TELEGRAM_BOT_TOKEN = token BotFather
TELEGRAM_CHAT_ID = số Chat ID

Chỉ điền key của provider đang dùng; key provider kia có thể để trống.

## Chạy thử
Actions → Stock AI Scan → Run workflow → Run workflow.
Mở job → Run Stock AI.

## Pages
Settings → Pages → Source = GitHub Actions.
Sau đó workflow Stock AI Pages deploy website.

## Login mặc định
admin / StockAI@2026

Login này chỉ là lớp giao diện phía trình duyệt, không phải xác thực server-side. Không coi nó là bảo mật thực sự. Với dữ liệu riêng tư nên dùng Cloudflare Access hoặc backend có authentication.

## Domain
Settings → Pages → Custom domain. Với subdomain, DNS CNAME trỏ về USERNAME.github.io. Với apex domain GitHub hiện hỗ trợ A/AAAA/ALIAS/ANAME theo hướng dẫn của GitHub.
