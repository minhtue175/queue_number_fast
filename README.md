# Hệ Thống Web Quét QR Bốc Số Thứ Tự (Client-Driven Queue System)

Dự án thiết kế & hiện thực hóa mô hình bốc số thứ tự tự động 1 chiều (Client-driven Queue) kèm bảng điều khiển Admin quản lý lượt chạy trên hạ tầng Cloud / VPS / Serverless Free tier.

---

## 🌟 TÍNH NĂNG NỔI BẬT

1. **Auto-reset ngày mới:** Tự động reset số thứ tự về `#001` khi bước sang ngày mới (`YYYY-MM-DD`), không phụ thuộc cron job.
2. **Chống Race Condition (Trùng số):** Sử dụng DB Transaction isolation với `BEGIN EXCLUSIVE` (SQLite WAL Mode) đảm bảo nhiều khách bốc vé cùng 1 millisecond không bị trùng số.
3. **Giữ vé an toàn khi F5 / Quét lại:** Trạng thái vé được lưu trong `localStorage`, kèm theo `idempotency_key` chống cấp trùng vé khi mất kết nối mạng.
4. **Chống gian lận bằng ảnh chụp màn hình:** Tích hợp Canvas Wave Animation chuyển động liên tục + Live UTC Clock đếm giây real-time + Mã Checksum HMAC-SHA256.
5. **Role Admin Quản Lý Hàng Chờ (Admin Dashboard):**
   - Đăng nhập bảo mật qua API với tài khoản quản lý.
   - Thống kê real-time: Tổng vé, Số lượng đang chờ, Số lượng đã hoàn tất.
   - Nút gọi số nhanh `📢 Gọi Số Tiếp Theo`, `🔄 Reset Ngày`, `Hoàn tất vé` trực tiếp.
   - **Tự động đồng bộ Live (Real-time Polling 2s)**: Khi Admin hoàn tất vé, màn hình máy khách tự động chuyển trạng thái `✓ ĐÃ HOÀN TẤT DỊCH VỤ` và hiện nút `✨ Bốc Số Lượt Mới`.
   - **Bảo mật giao diện**: Nút `🔐 Just For Admin` chỉ xuất hiện ở màn hình khởi tạo đầu tiên, tự động ẩn khi khách đã bốc vé để tránh thao tác nhầm.

---

## 📁 CẤU TRÚC MÃ NGUỒN

- `server.py`: Server Backend Python 3 production-ready (Không cần cài thư viện ngoài, tích hợp sẵn SQLite WAL mode + Atomic Transaction + HMAC SHA-256 + Static Web Server).
- `server.js`: Mã nguồn Backend tham chiếu cho môi trường Node.js / Express (sử dụng `better-sqlite3`).
- `index.html`: Single-page Frontend HTML5/CSS3/JS với giao diện Cute Watercolor Glassmorphism, Canvas Watermark động, Admin Modal và Live Sync Poller.
- `schema.sql`: Script khởi tạo cơ sở dữ liệu SQLite.

---

## 🚀 HƯỚNG DẪN CHẠY DỰ ÁN

### 1. Chạy Cục Bộ (Local Machine)
```bash
# Chạy bằng Python (Khuyên dùng - Zero setup)
python server.py
```
Truy cập ứng dụng: `http://localhost:8000`

### 2. Triển khai Cloud (Render.com)
- **Service Type**: `Web Service`
- **Runtime**: `Python 3`
- **Build Command**: `echo "done"`
- **Start Command**: `python server.py`
- **Instance Type**: `Free ($0/month)`
