# Muse Landscape Studio 1.2.0

## Tự điều phối

Mặc định Cân bằng: tối đa 3 tài khoản, 2 video/tài khoản (6 video). Tự điều phối bật mặc định: bắt đầu ít tác vụ và tăng dần khi CPU/RAM thấp ổn định. Không tăng vượt mức đã chọn. CPU cao kéo dài hoặc RAM cao làm giảm số tác vụ mới. Nếu RAM dùng từ 96% hoặc còn dưới 0,5 GB, tạm ngừng giao việc mới; tác vụ đã gửi tiếp tục chạy. Khi tải giảm ổn định, tiếp tục từ một luồng. Tải là CPU/RAM toàn máy, đọc bằng Windows API mỗi 5 giây; không tạo tiến trình phụ để lấy số liệu.

Ba mức: Tiết kiệm (2 tài khoản × 1 video), Cân bằng (3 × 2), Nhanh (5 × 3). Đổi mức hoặc tắt tự điều phối khi đã dừng công việc. Tác vụ đã gửi không bị hủy vì thay đổi tải máy. Khi hiện Đang chạy / mục tiêu là 3 / 2, app đang đợi tác vụ cũ hoàn tất trước khi nhận việc mới, không có nghĩa gửi thêm hai tác vụ.

Nhóm tài khoản cố định, không luân phiên. Chỉ thay khi không còn khả dụng. Khi chưa có prompt, nhóm được dùng viết prompt; khi có prompt, một tài khoản viết và phần còn lại tạo video, không dùng chung tài khoản cho hai việc. Viết xong, tài khoản viết tham gia video. Giãn gửi riêng 1–2 giây/tài khoản.

## Hàng đợi và dữ liệu

Prompt nhận được lưu ngay; có thể lập thêm trong lúc tạo video. Bộ sau dùng các luồng rảnh khi bộ trước còn video chậm. Các bộ dùng chung giới hạn, không cộng riêng thành nhiều lần số luồng. Chạy lượt chính trước; sau đó thử lại lỗi tối đa 5 lần. Giữ mã gửi chống tạo trùng khi mất phản hồi. Cảnh cũ không rõ tác vụ cần xác nhận Gửi lại cảnh lỗi; video hoàn thành không bị tạo lại.

Dừng giữ tiến độ và mã tác vụ. Tác vụ đã gửi Muse có thể vẫn chạy trên dịch vụ. Dọn prompt hoặc xóa tài khoản không xóa video đã lưu. Không tự xóa tài khoản. Chọn thư mục trước khi chạy; khi chưa chọn mặc định D:\video. Kết quả nằm thẳng trong thư mục chọn.

## Giảm tải và giao diện

- Chỉ kiểm tra token bổ sung khi tài khoản báo giới hạn, lưu nhãn/thời điểm rồi đóng tab. Không đọc được báo Không rõ; không tự coi là hết token. Tạm ngừng đọc token và xem trước video lúc đang sản xuất.
- Quét trạng thái tab video tối đa mỗi 5 giây; giảm nhật ký HTTP; dùng chỉ mục tác vụ; cập nhật giao diện không chồng yêu cầu.
- Đóng tab/phiên không dùng, giữ tab đang có công việc. Khi máy chịu tải cao, dọn tab rảnh sớm hơn. Chrome nền chung vẫn giữ để kết nối; khi thoát app đóng Chrome riêng của Muse, không đóng Chrome cá nhân.
- Bảng điều phối hiển thị CPU/RAM, số tác vụ và lý do chờ/giảm luồng. Thống kê riêng đang chờ/đang xử lý/lỗi/hoàn thành; lọc danh sách từng prompt và thanh tiến độ.

## Cài đặt và kiểm tra

Dừng công việc và thoát app trước khi cài. Giữ nguyên thư mục Data và video, không cần thêm lại tài khoản. Bộ cài không tự chạy hàng đợi.

194 kiểm tra tự động; giao diện kiểm tra bằng Chrome với dữ liệu giả lập ở 1400×1000 và 1000×800. Có kiểm tra bộ đo CPU/RAM Windows thực tế, nhưng chưa chạy tạo video thật để đo mức giảm CPU/RAM. Không thể bảo đảm hết lỗi từ dịch vụ Muse. Hạn mức, thời lượng và khả năng tạo video do Muse quyết định; mua thêm token không nhất thiết tăng số video trong 24 giờ.
