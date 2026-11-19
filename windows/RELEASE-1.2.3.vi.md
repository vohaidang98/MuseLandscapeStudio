# Muse Landscape Studio 1.2.3

- Khi mở lại hoặc dừng app, cảnh không còn luồng xử lý được chuyển về Tạm dừng, không tính vào Đang xử lý. Giữ ID yêu cầu cũ để kiểm tra khi tiếp tục.
- Không mở tab kiểm tra token trước khi gateway khởi động xong. Tăng thời gian chờ khởi động gateway từ 40 lên 120 giây cho máy đang tải nặng hoặc lịch sử lớn.
- Khi kết nối chưa xác minh, không kết luận tất cả tài khoản hết hạn mức.
- Bao gồm nhận diện hạn mức, kiểm tra token một lần và đóng tab, nhập TXT và tự điều phối tải máy từ bản trước.
- Dừng công việc, thoát app rồi cài cập nhật. Giữ nguyên dữ liệu tài khoản, prompt và video.
