# Muse Landscape Studio 1.2.4

- Bản đánh số mới để dễ nhận diện khi cài và chạy thử. Các bản cũ không bị thay thế hoặc xóa.
- Đóng gói lại từ mã nguồn hiện tại, gồm agent/main.py sửa ngày 03/11/2026. Giữ nguyên các thay đổi của bản 1.2.3.
- Tiện ích Chrome (extension/background.js): gửi kèm tiêu đề X-Callback-Secret khi trả kết quả về agent qua HTTP. Nếu chưa có secret (cài mới hoặc agent khởi động lại giữa yêu cầu), kết quả được gửi qua WebSocket. Tiện ích này không nằm trong bộ cài này, cần đóng gói riêng (FrameWeaver-Google-Flow-Extension.zip).
- Chưa kiểm thử runtime trên Google Flow thật. Dừng công việc, thoát app rồi cài cập nhật. Dữ liệu tài khoản, prompt và video được giữ nguyên.
