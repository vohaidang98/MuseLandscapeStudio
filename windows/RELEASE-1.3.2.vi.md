# Muse Landscape Studio 1.3.2

- Sửa lỗi treo cứng giao diện ngay khi mở app. Nguyên nhân: màn hình ứng dụng tự quét (reflection) sang toàn bộ đối tượng cửa sổ gốc của WebView2 (bao gồm AccessibilityObject), rơi vào một vòng lặp không dừng (Bounds.Empty.Empty...) làm app đơ. Đã chặn việc quét này.
