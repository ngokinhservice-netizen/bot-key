# MTK KEY BOT – HỆ THỐNG BÁN KEY PHẦN MỀM TỰ ĐỘNG 24/7

**MTK Key Bot** là giải pháp phần mềm chuyên nghiệp toàn diện dành cho việc kinh doanh và phân phối bản quyền phần mềm tự động qua nền tảng **Telegram Bot API**, tích hợp cổng thanh toán ngân hàng tự động **SePay Webhook**, ví số dư nội bộ, hệ thống chống bán trùng key với Database Row Locking, trang quản trị Web Dashboard hiện đại (FastAPI) và phân quyền 3 cấp độ (RBAC).

---

## 🌟 TÍNH NĂNG NỔI BẬT

1. **Giao diện Telegram Bot chuyên nghiệp (aiogram 3):**
   - Đầy đủ menu: 🛒 Mua key, 📦 Key của tôi, 💰 Nạp tiền, 🧾 Lịch sử giao dịch, 🎁 Mã giảm giá, 👥 Cộng tác viên (Affiliate), 🎧 Hỗ trợ, 📜 Điều khoản sử dụng.
   - Trình bày trực quan, inline keyboard mượt mà trên cả điện thoại và máy tính.
   - Tự động nhận diện link giới thiệu `/start REF...`.

2. **Thanh toán tự động qua SePay (VietQR):**
   - Sinh ảnh mã VietQR kèm số tiền và mã đơn hàng tự động.
   - Nhận webhook từ SePay khi có biến động số dư ngân hàng (MBBank, Vietcombank, Techcombank,...).
   - Xác thực Header `Authorization: Apikey <token>` hoặc Query Param.
   - **Chống webhook lặp lại (Idempotency)** qua bảng `webhook_events`.
   - **Xử lý thiếu tiền an toàn:** Giao dịch thiếu tiền tự động đưa vào trạng thái `PARTIAL_PAID`, gửi cảnh báo và **không bao giờ giao key**.

3. **Quản lý kho key & Khóa chống bán trùng (Concurrency Row-level Locking):**
   - Mỗi key là một bản ghi độc lập (`AVAILABLE`, `SOLD`, `REVOKED`).
   - Sử dụng cơ chế khóa dòng `SELECT ... FOR UPDATE` khi xuất kho -> đảm bảo khi 2 người mua key cuối cùng trong cùng 1 tích tắc, chỉ 1 người nhận được key, người còn lại nhận thông báo hết hàng.
   - Không bán key đã bán, không bán key khi hết hàng, không tự sinh key ảo.
   - Import hàng loạt từ file TXT hoặc CSV, tự động loại bỏ trùng lặp.

4. **Đảm bảo quyền lợi khách hàng (Blocked Bot Protection):**
   - Nếu khách hàng chặn bot hoặc chưa mở chat, giao dịch **vẫn được bảo toàn trong database**. Người dùng có thể mở lại bot và bấm **📦 Key của tôi** để lấy mã key bất cứ lúc nào.

5. **Ví số dư nội bộ & Nạp tiền tự động:**
   - Nạp tiền tự động qua chuyển khoản với cú pháp `NAP{telegram_id}`.
   - Mua key siêu tốc bằng số dư ví (xử lý tức thì không cần chờ ngân hàng).
   - Ràng buộc an toàn `balance >= 0`, chống số dư âm.

6. **Web Admin Dashboard (FastAPI + Tailwind CSS):**
   - Thống kê doanh thu thời gian thực (Hôm nay, 7 ngày, 30 ngày, Tổng lũy kế).
   - Biểu đồ biến động doanh thu (Chart.js).
   - Quản lý sản phẩm, giá bán, thời hạn sử dụng.
   - Quản lý kho key & import hàng loạt.
   - Quản lý đơn hàng, tìm kiếm theo mã đơn hoặc Telegram ID.
   - Hoàn tiền (Refund) thu hồi key và hoàn tiền vào ví khách.
   - Quản lý khách hàng, khóa/mở khóa tài khoản, điều chỉnh số dư kèm lý do kiểm toán.
   - Quản lý mã giảm giá (Voucher % hoặc cố định).
   - Trung tâm hỗ trợ tiếp nhận báo lỗi và gửi phản hồi trực tiếp vào Telegram của khách.
   - Phát sóng thông báo (Broadcast) đến toàn bộ người dùng bot.
   - Xuất dữ liệu báo cáo đơn hàng ra file CSV.

7. **Bảo mật & Phân quyền RBAC 3 cấp:**
   - `SUPER_ADMIN`: Toàn quyền cấu hình, tài chính, duyệt hoa hồng, phân quyền.
   - `ORDER_MANAGER`: Quản lý kho key, duyệt đơn, tạo sản phẩm và khuyến mãi.
   - `SUPPORT`: Tiếp nhận và trả lời phiếu hỗ trợ của khách hàng.
   - Nhật ký kiểm toán `audit_logs` lưu vết tất cả các thao tác nhạy cảm.

---

## 🗂️ CẤU TRÚC THƯ MỤC

```
.
├── app/
│   ├── admin/               # Web Dashboard, Auth JWT, RBAC & Templates HTML
│   │   ├── auth.py
│   │   ├── routes.py
│   │   └── templates/       # Giao diện Jinja2 + Tailwind CSS (MTK Navy/Cyan)
│   ├── bot/                 # Aiogram 3 Handlers, Keyboards & Middlewares
│   │   ├── bot_instance.py
│   │   ├── handlers/        # /start, buy_key, my_keys, deposit, tickets...
│   │   ├── keyboards/       # Inline Keyboards
│   │   └── middlewares/     # Database session, Throttling, Auth/Ban check
│   ├── config/              # Pydantic Settings (.env)
│   ├── database/            # SQLAlchemy 2.0 Async Models & Session
│   ├── payments/            # SePay Webhook, VietQR Generator
│   ├── services/            # Nghiệp vụ: Key locking, Order, Wallet, Affiliate...
│   ├── utils/               # Structured Logger, Helpers format tiền tệ
│   └── main.py              # Entry Point ứng dụng FastAPI & Bot Polling
├── tests/                   # 10 Kịch bản kiểm thử tự động toàn diện
├── Dockerfile               # Build container Python 3.12-slim
├── docker-compose.yml       # Cụm dịch vụ: App + PostgreSQL 16
├── nginx.conf               # Cấu hình Reverse Proxy & SSL Nginx
├── requirements.txt
├── .env.example
└── README.md
```

---

## 📋 THÔNG TIN & TÀI KHOẢN CẦN TỰ CHUẨN BỊ

Trước khi đưa vào vận hành thực tế, bạn cần chuẩn bị:

1. **Telegram Bot Token:**
   - Mở ứng dụng Telegram, tìm đến [@BotFather](https://t.me/BotFather).
   - Gõ lệnh `/newbot`, đặt tên bot (ví dụ: `MTK Key Bot`) và username bot (ví dụ: `mtk_key_bot`).
   - Copy mã Token được cấp (dạng `1234567890:ABCdefGHIjklMNOpqrsTUVwxyz`).

2. **Telegram ID của bạn:**
   - Chat với [@userinfobot](https://t.me/userinfobot) để lấy ID số (ví dụ: `123456789`).
   - Điền ID này vào `SUPER_ADMIN_TELEGRAM_ID` để bot gửi thông báo đơn hàng và cảnh báo hệ thống cho bạn.

3. **Tài khoản SePay:**
   - Đăng ký tài khoản miễn phí tại [https://my.sepay.vn](https://my.sepay.vn).
   - Kết nối tài khoản ngân hàng của bạn (MBBank, Vietcombank, Techcombank, VPBank, TPBank, ACB, BIDV,...).
   - Tạo Webhook trên SePay trỏ về địa chỉ server của bạn:
     - URL: `https://domain-cua-ban.com/api/v1/payments/sepay/webhook`
     - Phương thức: `POST`
     - Kiểu xác thực: `API Key` (Copy API Key này dán vào biến `SEPAY_API_KEY`).

4. **Máy chủ VPS Linux & Tên miền (Domain):**
   - VPS cài đặt Ubuntu 22.04 LTS hoặc 24.04 LTS (RAM tối thiểu 1GB).
   - Một tên miền đã trỏ DNS bản ghi A về địa chỉ IP của VPS.

---

## 🚀 HƯỚNG DẪN CÀI ĐẶT & CHẠY LOCAL (PHÁT TRIỂN)

### Bước 1: Sao chép cấu hình môi trường
Tạo file `.env` từ `.env.example`:
```bash
cp .env.example .env
```
Mở file `.env` và cập nhật các thông tin cơ bản:
```ini
TELEGRAM_BOT_TOKEN=token_lay_tu_botfather
SUPER_ADMIN_TELEGRAM_ID=id_telegram_cua_ban
DATABASE_URL=sqlite+aiosqlite:///./mtk_bot.db
SEPAY_API_KEY=sepay_key_cua_ban
SEPAY_BANK_ACCOUNT=so_tai_khoan_ngan_hang
SEPAY_BANK_NAME=MBBank
SEPAY_ACCOUNT_NAME=NGUYEN VAN A
ALLOW_TEST_PAYMENTS=True   # Bật chế độ giả lập thanh toán khi test local
```

### Bước 2: Cài đặt thư viện Python
Khởi tạo môi trường ảo và cài đặt dependencies:
```bash
python -m venv venv

# Kích hoạt trên Linux/macOS:
source venv/bin/activate
# Kích hoạt trên Windows PowerShell:
.\venv\Scripts\Activate.ps1

pip install -r requirements.txt
```

### Bước 3: Khởi chạy hệ thống
Chạy lệnh khởi động:
```bash
python -m app.main
```
Khi chạy, hệ thống sẽ tự động:
- Khởi tạo toàn bộ 15 bảng trong Database.
- Tự động tạo tài khoản Super Admin mặc định: `admin` / `Admin@MTK2026!`.
- Khởi tạo 3 sản phẩm mẫu MTK Task (30 ngày, 90 ngày, 365 ngày).
- Khởi chạy Telegram Bot và Web Server tại `http://localhost:8000`.

Truy cập Admin Dashboard tại: `http://localhost:8000/admin/login`

---

## 🧪 CHẠY BỘ KIỂM THỬ TỰ ĐỘNG (TEST SUITE)

Hệ thống đi kèm bộ kiểm thử tự động toàn diện kiểm chứng 10 kịch bản then chốt:
1. **Mua key thành công** bằng ví nội bộ (`tests/test_order_flow.py`).
2. **Thanh toán thiếu tiền** -> Chuyển `PARTIAL_PAID`, không giao key (`tests/test_sepay_webhook.py`).
3. **Webhook gửi lặp lại (Idempotency)** -> Không bán thừa key (`tests/test_sepay_webhook.py`).
4. **Hai người mua key cuối cùng cùng lúc (Race Condition)** -> Khóa dòng an toàn, 1 người thành công, 1 người hết hàng (`tests/test_concurrency.py`).
5. **Hết kho key** -> Xử lý thông báo hết hàng chính xác (`tests/test_order_flow.py`).
6. **Người dùng chặn bot** -> Key được lưu an toàn trong DB và lấy lại được qua "Key của tôi" (`tests/test_blocked_bot.py`).
7. **Đơn hàng bị timeout** -> Tự động hủy đơn quá hạn (`tests/test_order_flow.py`).
8. **Hoàn tiền đơn hàng** -> Thu hồi key, hoàn tiền vào ví, hủy hoa hồng (`tests/test_order_flow.py`).
9. **Chống truy cập chéo (IDOR)** -> Người dùng không thể thấy key của người khác (`tests/test_rbac_security.py`).
10. **Phân quyền RBAC** -> Nhân viên thường không thể thực hiện thao tác của Super Admin (`tests/test_rbac_security.py`).

Chạy kiểm thử:
```bash
pytest -v
```

---

## 🚢 TRIỂN KHAI LÊN VPS LINUX VỚI DOCKER & POSTGRESQL

### Bước 1: Cài đặt Docker & Docker Compose trên VPS
```bash
curl -fsSL https://get.docker.com -o get-docker.sh
sudo sh get-docker.sh
sudo usermod -aG docker $USER
```

### Bước 2: Tải mã nguồn lên VPS
Tải toàn bộ thư mục dự án lên VPS (ví dụ tại `/opt/mtk-key-bot`).

### Bước 3: Cấu hình file `.env` cho Production
Tại thư mục dự án trên VPS:
```bash
nano .env
```
Cấu hình:
```ini
ENVIRONMENT=production
DEBUG=False
APP_SECRET_KEY=mot_chuoi_ngau_nhien_dai_it_nhat_32_ky_tu_bao_mat

TELEGRAM_BOT_TOKEN=token_lay_tu_botfather
SUPER_ADMIN_TELEGRAM_ID=id_telegram_cua_ban

# SePay cấu hình thật
SEPAY_API_KEY=api_key_chinh_thuc_sepay
SEPAY_BANK_ACCOUNT=so_tai_khoan_that
SEPAY_BANK_NAME=MBBank
SEPAY_ACCOUNT_NAME=NGUYEN VAN A
ALLOW_TEST_PAYMENTS=False   # BẮT BUỘC False trên Production!

# Đổi mật khẩu Super Admin
ADMIN_DEFAULT_USERNAME=superadmin
ADMIN_DEFAULT_PASSWORD=MatKhauPhucTap@2026!

# PostgreSQL Production
POSTGRES_USER=mtk_user
POSTGRES_PASSWORD=MatKhauPostgresKinhDien@2026!
POSTGRES_DB=mtk_key_bot
```

### Bước 4: Khởi chạy ứng dụng bằng Docker Compose
```bash
docker compose up -d --build
```
Kiểm tra trạng thái container:
```bash
docker compose ps
docker compose logs -f app
```

---

## 🔒 CẤU HÌNH DOMAIN, NGINX & SSL HTTPS (LET'S ENCRYPT)

SePay Webhook bắt buộc giao thức **HTTPS** có chứng chỉ hợp lệ.

### Bước 1: Cài đặt Certbot và lấy chứng chỉ SSL
```bash
sudo apt update && sudo apt install -y certbot python3-certbot-nginx nginx
sudo certbot certonly --standalone -d domain-cua-ban.com
```

### Bước 2: Cập nhật file `nginx.conf`
Chỉnh sửa tên miền trong file `nginx.conf`:
```nginx
server_name domain-cua-ban.com;
ssl_certificate /etc/letsencrypt/live/domain-cua-ban.com/fullchain.pem;
ssl_certificate_key /etc/letsencrypt/live/domain-cua-ban.com/privkey.pem;
```

### Bước 3: Áp dụng Nginx trên VPS
Sao chép cấu hình vào Nginx của hệ thống và reload:
```bash
sudo cp nginx.conf /etc/nginx/sites-available/mtk_bot.conf
sudo ln -s /etc/nginx/sites-available/mtk_bot.conf /etc/nginx/sites-enabled/
sudo nginx -t
sudo systemctl reload nginx
```

Bây giờ bạn có thể:
1. Đăng nhập Admin Panel tại: `https://domain-cua-ban.com/admin/login`
2. Cấu hình Webhook URL trên SePay: `https://domain-cua-ban.com/api/v1/payments/sepay/webhook`

---

## 💾 SAO LƯU DỮ LIỆU ĐỊNH KỲ (BACKUP & RESTORE)

### 1. Sao lưu tự động PostgreSQL
Tạo lệnh sao lưu cơ sở dữ liệu:
```bash
docker exec -t mtk_postgres pg_dump -U mtk_user mtk_key_bot > /opt/backups/mtk_backup_$(date +%Y%m%d_%H%M%S).sql
```
Bạn có thể đưa vào `crontab -e` để tự động sao lưu mỗi ngày vào 02:00 sáng:
```cron
0 2 * * * docker exec -t mtk_postgres pg_dump -U mtk_user mtk_key_bot > /opt/backups/mtk_backup_$(date +\%Y\%m\%d).sql
```

### 2. Phục hồi dữ liệu (Restore)
```bash
cat /opt/backups/mtk_backup_file.sql | docker exec -i mtk_postgres psql -U mtk_user -d mtk_key_bot
```

---

## 📞 HỖ TRỢ KỸ THUẬT

Hệ thống được phát triển chuẩn chỉ theo kiến trúc Module, Async hoàn toàn, đảm bảo khả năng chịu tải hàng nghìn đơn hàng mỗi ngày. Nếu bạn cần mở rộng thêm tính năng (như tích hợp thêm cổng USDT Crypto, MoMo, ZaloPay), vui lòng tham khảo mã nguồn trong module `app/payments/` và `app/services/`.
