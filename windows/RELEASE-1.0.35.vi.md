# Muse Landscape Studio 1.0.35

- Hàng đợi không phải chờ hết một bộ mới chạy bộ sau. Các bộ dùng chung tối đa 15 tác vụ.
- Tối đa 5 tài khoản cố định; 3 video/tài khoản. Đang viết prompt: một tài khoản viết và tối đa bốn tài khoản tạo video; viết xong cả năm có thể tạo video.
- Tài khoản hết hạn mức hoặc phiên không còn dùng được mới được thay. Không luân phiên sau mỗi lượt gửi.
- Chạy hết lượt chính trước rồi thử lại cảnh lỗi tối đa 5 lần. Cảnh không rõ yêu cầu cũ cần xác nhận trước khi gửi lại.
- Tách số đang chờ, đang xử lý, lỗi và hoàn thành; lọc danh sách từng prompt theo trạng thái.
- Đọc trạng thái gateway nội bộ trực tiếp; giảm đọc trạng thái tab video xuống tối đa mỗi 2 giây; không gửi chồng nhiều lượt cập nhật giao diện.
- Chỉ kiểm tra token bổ sung cho tài khoản báo giới hạn. Kiểm tra xong lưu nhãn và thời gian rồi đóng tab. Không đọc được báo Không rõ, không tự xóa tài khoản.
- Đóng tab/phiên rảnh sau 30 giây hoặc khi tài khoản không còn dùng. Giữ tab có tác vụ đang chạy; mở lại khi cần. Chrome nền chung vẫn giữ kết nối. Thoát app chỉ đóng Chrome riêng của Muse.

## Cập nhật

Dừng công việc và thoát app trước khi cài. Giữ nguyên thư mục Data và các thư mục video. Bộ cài không gửi yêu cầu tạo video hay tự chạy hàng đợi.

## Sử dụng

Nhập mô tả, số prompt và camera, rồi bấm Thêm prompt. Prompt hoàn thành được giữ ngay trong hàng đợi. Có thể viết thêm trong khi video chạy. Bấm Dừng hàng đợi để ngừng công việc mới; tác vụ đã gửi Muse có thể vẫn chạy. Bộ lọc Cảnh lỗi giúp xem lý do. Gửi lại cảnh lỗi cần xác nhận vì yêu cầu cũ chưa rõ có thể đã được Muse nhận.

Chọn thư mục đầu ra trước khi chạy. Mặc định khi chưa chọn là D:\video; kết quả nằm thẳng trong thư mục đã chọn. Video đã hoàn thành được giữ khi dọn prompt hoặc xóa tài khoản.

## Kiểm tra

Các kiểm tra tự động dùng dữ liệu giả lập, bao gồm chờ video chậm ở bộ trước, chia ngân sách 15 tác vụ, dừng nhiều bộ, thử lại sau lượt chính, giữ mã gửi, phân vai tài khoản, token và phạm vi đóng Chrome. Kiểm tra giao diện trong Chrome dùng dữ liệu giả, hai kích thước 1400x1000 và 1000x800. Không gửi video trả phí để kiểm tra.

Hạn mức, thời lượng clip và khả năng tạo video thực tế do Muse quyết định. Không thể bảo đảm dịch vụ bên ngoài không lỗi hoặc mức CPU/RAM giống nhau trên mọi máy.
