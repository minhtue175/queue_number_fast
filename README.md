# Hệ Thống Web Quét QR Bốc Số Thứ Tự (Client-Driven Queue MVP)

Dự án thiết kế & hiện thực hóa mô hình bốc số thứ tự tự động 1 chiều (Client-driven Queue) chạy trên hạ tầng Cloud / Serverless Free tier.

---

## YÊU CẦU ĐÃ ĐÁP ỨNG

1. **Auto-reset ngày mới:** Tự động reset số thứ tự về #001 khi bước sang ngày mới (`YYYY-MM-DD`), không phụ thuộc cron job.
2. **Chống Race Condition:** Sử dụng DB Transaction isolation với `BEGIN EXCLUSIVE` (SQLite) / `SELECT FOR UPDATE` (PostgreSQL) đảm bảo 50 người quét cùng 1 ms không bị trùng số.
3. **Giữ vé khi F5/Quét lại:** Trạng thái vé được lưu an toàn trong `localStorage`, kèm theo `idempotency_key` chống cấp trùng vé khi rớt mạng.
4. **Chống gian lận bằng ảnh chụp màn hình:** Tích hợp Canvas Wave Animation chuyển động liên tục + Live UTC Clock đếm giây real-time + Mã Checksum HMAC-SHA256.

---

## CẤU TRÚC MÃ NGUỒN

- `server.py`: Server Backend Python 3 production-ready (Không cần cài thư viện ngoài, tích hợp sẵn SQLite WAL mode + Atomic Transaction + HMAC SHA-256 + Static Web Server).
- `server.js`: Mã nguồn Backend tham chiếu cho môi trường Node.js / Express (sử dụng `better-sqlite3`).
- `index.html`: Single-page Frontend HTML5/CSS3/JS với giao diện Dark Mode Glassmorphism cao cấp, đếm giây Live Clock, Canvas Watermark động và Modal xác nhận 2 bước.
- `schema.sql`: Script khởi tạo cơ sở dữ liệu SQLite / PostgreSQL.

---

## HƯỚNG DẪN CHẠY DỰ ÁN

### Cách 1: Chạy bằng Python (Khuyên dùng - Không cần cài đặt gì thêm)
```bash
python server.py
```
Truy cập ứng dụng trên trình duyệt: `http://localhost:8000`

### Cách 2: Chạy bằng Node.js (Nếu có môi trường Node.js)
```bash
npm install express better-sqlite3
node server.js
```
Truy cập ứng dụng trên trình duyệt: `http://localhost:8000`
