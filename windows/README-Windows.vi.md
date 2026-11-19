# Muse Landscape Studio — Windows Preview

Ứng dụng riêng chỉ dùng Muse AI để tạo các cảnh phong cảnh không có người.
Không cần Google Flow, extension Flow hoặc API Google. Cài riêng với bản cũ;
hãy thoát FrameWeaver trước khi mở vì cùng dùng cổng 8100 và phiên Muse.

## Cài và kết nối

Chạy Muse-Landscape-Studio-1.0.22-Windows-x64-Setup.exe trên Windows 10/11 x64.
Cần Google Chrome và Microsoft Edge WebView2 Runtime. Python và gateway đã
đi kèm. Giao diện mở trong cửa sổ ứng dụng; nếu WebView2 không hoạt động,
có chế độ trình duyệt dự phòng. Bộ cài chưa ký số.

Mở ứng dụng → Kết nối Muse (góc trên phải) → Khởi động Muse → cho phép lưu
phiên → Mở Chrome đăng nhập. Đăng nhập muse.ai trong cửa sổ Chrome riêng,
quay lại → Tôi đã đăng nhập — Kết nối. Nếu đã lưu phiên từ bản trước, chỉ cần
khởi động gateway. Một phản hồi hoặc media thật mới xác nhận dùng được tài khoản.

Phiên và dữ liệu giữ ở D:\Code\MuseLandscapeStudio\Data\.flowkit\muse-gateway
để dùng lại tài khoản bản trước. Không chia sẻ thư mục này, cookie hoặc mật khẩu.
Không dùng cookie Google/Gmail.

## Thiết kế bộ cảnh

1. Nhập mô tả bối cảnh riêng cho lần tạo này. Không còn các nút bối cảnh mẫu.
2. Chọn số cảnh (1–1.000), tỉ lệ, phong cách và ánh sáng.
3. Có sẵn 6 góc: Fly cam, Zoom xa đến gần, Góc tĩnh, Góc pan,
   Gần đến xa, Góc quay cận. Tích nhiều góc camera. Mỗi cảnh tự chọn ngẫu nhiên một góc trong danh sách.
   Góc có thể lặp giữa các cảnh, được giữ cố định khi tạo ảnh/video.
   Các góc ưu tiên phong cảnh rộng, chuyển động chậm, giữ không gian. Góc cận
   dùng chi tiết cảnh vật (sóng, lúa, lá, đá), không phải chân dung/sản phẩm.
4. Thêm góc riêng: nhập tên và mô tả. Ví dụ tên “Sát mặt nước”, mô tả “Máy
   sát mặt nước, nhìn về chân trời, tiến chậm”. Bấm Thêm & chọn góc này.
   Các góc riêng được lưu trên máy cho lần sau.
5. Bấm Muse lập cảnh. Đây là một yêu cầu viết prompt, chưa tạo media.

## Duyệt và tạo

Duyệt từng tên cảnh, prompt ảnh, prompt chuyển động và camera. Có thể sửa
camera/prompt trước khi gửi. Prompt luôn bổ sung không có người, chữ hoặc
watermark. Đây là chỉ dẫn cho mô hình; cần duyệt vì AI có thể không tuân theo.

- Chỉ tạo ảnh: tạo lần lượt ảnh để kiểm tra bố cục.
- Duyệt & tạo video các cảnh: mỗi cảnh tạo video trực tiếp từ mô tả, yêu cầu
  khoảng 8 giây. Không gửi yêu cầu tạo ảnh trước khi tạo video.
- Sau khi tạo ảnh trước, bấm Tiếp tục tạo video để tạo video trực tiếp từ mô tả cảnh.
- Cảnh đã gửi khóa prompt/camera để giữ đúng với kết quả cũ. Muốn đổi, lập bộ
  cảnh mới. Bộ cũ vẫn nằm trong danh sách đã lưu.

## Tiến độ và tải về

Chạy tuần tự, một bộ cảnh mỗi lần. Nút Dừng ngừng chờ và ngừng gửi thêm ngay. Giữ ứng dụng mở khi tạo. Đóng ứng dụng có thể làm gián đoạn;
Muse vẫn có thể chạy/tính hạn mức ở phía dịch vụ.

Danh sách, camera và ID tác vụ lưu tự động. Mở lại → chọn bộ đã lưu → Tiếp tục.
Tác vụ cũ được kiểm tra lại, không tự gửi trùng. Nếu gateway xác nhận thất bại,
bấm Cho phép thử lại cảnh thất bại rồi Tiếp tục. Nếu chưa rõ yêu cầu cũ đã được
nhận chưa, cần kiểm tra lịch sử Muse trước; ứng dụng không tự gửi lại.

Tải từng ảnh/video hoặc Tải tất cả ZIP. ZIP gồm media và scenes.json chứa
prompt/camera, không có cookie. Mỗi video là clip riêng, chưa tự ghép lại.

## Giới hạn

Tài khoản cần quyền và hạn mức Muse phù hợp. Tỉ lệ, thời lượng và camera là
yêu cầu tới mô hình, không bảo đảm tuyệt đối. Không có người dẫn/nhân vật.
Gateway cộng đồng ghim efc06dd9741efe3b56a4bb02bb4761c0003eae30; không phải
ứng dụng hoặc SDK chính thức của Muse.

60 kiểm thử Muse/bộ cảnh đạt. Kiểm thử dùng dữ liệu giả lập, không chứng nhận
tạo media thật. Chrome trong môi trường Codex bị chặn IPC; cần kiểm tra tài
khoản trực tiếp sau khi cài trên Windows. Nhật ký: app.log và desktop.log trong
D:\Code\MuseLandscapeStudio\Data.

## Giao diện và lưu kết quả (1.0.3)

Không còn các nút Đồng quê, Biển, Thành phố hay Thêm bối cảnh. Chỉ nhập mô tả
riêng cho từng lần tạo; mô tả ban đầu để trống.

Mỗi ảnh/video hoàn tất tự sao chép vào D:\Code\MuseLandscapeStudio\Videos → tên bộ cảnh kèm mã riêng. Tên file theo số cảnh:
01-image.png, 01-video.mp4, 02-video.mp4… Định dạng thực tế tùy Muse.
Ứng dụng hiển thị đường dẫn đầy đủ và nút Mở thư mục video. Bản nguồn media
trong thư mục Data trên ổ D vẫn được giữ để xem lại và tiếp tục hàng đợi.

Nút tải từng media hoặc Tải tất cả ZIP vẫn dùng được để lưu thêm bản sao;
vị trí của các bản tải thủ công do hộp thoại lưu/trình duyệt của máy quyết định.
Những bộ cảnh tạo bằng bản trước được sao chép sang thư mục mới khi bấm
Tiếp tục. Các file người dùng đã đặt trong thư mục kết quả không bị ghi đè.

## Sửa kết nối Muse (1.0.4)

Phiên Muse hiện tại có thể không có hatch_gw. Bản mới làm mới và xác minh
/api/session trước khi lấy cookie; không chặn phiên hợp lệ chỉ vì thiếu hatch_gw.
Sau khi cài: Khởi động Muse → Mở Chrome đăng nhập → Tôi đã đăng nhập — Kết nối.
Hồ sơ Chrome riêng cũ được dùng lại. Không cần gửi cookie/mật khẩu vào chat.

## Chọn thư mục đầu ra (1.0.6)

Bấm Chọn thư mục… để mở cửa sổ chọn của Windows, hoặc nhập đường dẫn đầy đủ và bấm Lưu thư mục. Lựa chọn được nhớ cho lần sau, áp dụng cho bộ đang mở và các bộ mới. Kết quả hiện có của bộ đang mở được sao chép sang đích mới; tệp cũ vẫn giữ nguyên. Dừng tác vụ trước khi đổi thư mục.

Bước 1: Lập prompt cho các cảnh (chưa tạo media). Bước 2: duyệt cảnh, bấm Tạo video từ các cảnh này. Khi đó ứng dụng tạo video trực tiếp từ prompt cho từng cảnh.


## Cập nhật 1.0.7

Đã bỏ toàn bộ lọc trùng tự động và yêu cầu duyệt lại chống trùng. Lập cảnh không gọi thêm Muse để kiểm tra/viết lại cảnh trùng. Prompt có thể lặp lại; hãy tự duyệt trước khi tạo media.

Hộp chọn thư mục dùng kiểu Explorer có thanh địa chỉ, điều hướng và tìm kiếm; chọn thư mục đầu ra thay vì chọn tệp. Cơ chế lưu lựa chọn giữ nguyên.


## Text to Video (1.0.8)

Nút Tạo video dùng mô tả phong cảnh + prompt chuyển động + camera + phong cách + ánh sáng để tạo video trực tiếp, không tạo hoặc đính kèm ảnh trước. Chỉ tạo ảnh vẫn là tùy chọn riêng. Ảnh/video cũ được giữ nguyên. ID video đã gửi được kiểm tra lại khi tiếp tục, không tự tạo lại. Muse quyết định thời lượng thực tế và quyền/hạn mức tài khoản.


## Nhiều tài khoản và 1.000 cảnh (1.0.9)

Kết nối Muse → nhập tên mới (Muse 2, Muse 3…) → cho phép lưu phiên → Mở Chrome đăng nhập → đăng nhập tài khoản tương ứng → Tôi đã đăng nhập — Kết nối. Mỗi tên có hồ sơ Chrome đăng nhập riêng. Không thêm lại cùng một tài khoản dưới nhiều tên. Dùng tên đã có để đăng nhập lại và cập nhật phiên. Danh sách có nút Bật/Tắt; tắt chỉ ngăn việc phân phối mới, không hủy video đã gửi.

Gateway phân phối vòng tròn giữa các tài khoản khả dụng, tối đa 5 video đang chạy/tài khoản. Khoảng nghỉ giữa các lần gửi prompt 1–2 giây được tính RIÊNG cho từng tài khoản, không chặn tài khoản khác. Để cập nhật số luồng sau khi thêm tài khoản, dừng và tiếp tục hàng đợi. Chưa có cài đặt hạn mức riêng. Muse có thể từ chối do quyền/hạn mức; app không tự gửi lại yêu cầu đã nhận.

Tối đa 1.000 cảnh, lập prompt theo lô tối đa 30. Mỗi lô hoàn thành được lưu. Nếu dừng hoặc lỗi, mở bộ đã lưu và bấm Tiếp tục lập cảnh để tiếp tục phần chưa có. Cần lập đủ cảnh trước khi tạo media. Giao diện hiển thị 20 cảnh/trang để tránh tải hàng nghìn ô nhập cùng lúc.


Lập prompt cũng chia song song giữa các tài khoản khả dụng, mỗi lô tối đa 30 cảnh. Lô hoàn thành trước được lưu ngay, hiển thị đúng số cảnh gốc; hoàn tất sẽ ghép đúng thứ tự. Lô lỗi hoặc bị dừng có thể tiếp tục mà không viết lại những lô đã lưu. Các cảnh tạm thời chỉ đọc cho đến khi lập đủ số lượng.


## Hàng đợi tích lũy (1.0.10)

Nhập mô tả, số cảnh và camera → Lập & thêm prompt vào hàng đợi. Lặp lại tùy ý: 10 cảnh A + 10 cảnh A, hoặc 10 A + 10 B đều là các bộ độc lập. Không lọc trùng, không ghi đè bộ trước. Mỗi bộ có thư mục kết quả riêng. Có thể Duyệt prompt, lưu chỉnh sửa, hoặc Bỏ khỏi hàng đợi (không xóa bộ cảnh/media).

Chỉ khi đã đủ prompt, bấm Chạy toàn bộ hàng đợi để tạo video. Hàng đợi chạy từng bộ theo thứ tự thêm; bên trong mỗi bộ sử dụng nhiều tài khoản và tối đa 5 video/tài khoản. Lập prompt chỉ tiêu thụ yêu cầu nội dung, chưa gửi tạo video. Những bộ thêm sau khi bấm chạy phải được bấm chạy ở lượt sau, không tự gửi video.

Dừng hàng đợi giữ ID tác vụ hiện tại và không bắt đầu bộ tiếp theo. Đóng/mở app vẫn giữ hàng đợi; cần bấm chạy để tiếp tục, không tự chạy khi mở app. Tác vụ đã gửi Muse có thể vẫn tiếp tục phía dịch vụ. Nếu một bộ lỗi, hàng đợi ngừng tiến thêm để bạn kiểm tra.

Đầu ra mặc định khi chưa chọn thư mục: D:\video. Nếu đã lưu lựa chọn khác, app giữ nguyên lựa chọn đó. Nút chọn thư mục vẫn sử dụng bình thường.

## Xóa góc camera (1.0.11)

Tích các góc muốn xóa → Xóa góc đã tích → xác nhận. Áp dụng cho cả góc mặc định và góc tự thêm, ghi nhớ khi mở lại. Các bộ cảnh cũ vẫn giữ mô tả camera đã dùng. Sau khi xóa, chọn hoặc thêm góc khác để lập prompt mới.

## Lưu trực tiếp (1.0.22)

Lưu ảnh/video thẳng vào thư mục đầu ra đã chọn, không tạo thư mục con cho từng bộ. Tên tệp gồm mã bộ, số cảnh và loại media để phân biệt nhiều bộ cùng lưu một nơi. Kết quả cũ trong thư mục con trước đây không bị xóa hay tự di chuyển. Chưa chọn thư mục thì dùng D:\video; vẫn nhớ thư mục đã chọn.

## Cảnh lỗi (1.0.22)

Một cảnh lỗi không ngăn các cảnh hoặc bộ khác chạy lượt chính. Sau khi chạy lượt chính toàn hàng đợi, tự thử lại cảnh lỗi tối đa 5 lần ngoài lần đầu. Giữ kết quả đã thành công, lưu số lần thử khi dừng/mở lại. Cảnh vẫn lỗi hiển thị số lần và thông báo. Chỉ gửi yêu cầu mới nếu gateway xác nhận tác vụ trước thất bại hoặc bị hủy. Tác vụ còn chạy được kiểm tra lại ID cũ. Nếu không rõ yêu cầu trước có được nhận không, giữ trạng thái lỗi và không tự tạo thêm bản trùng.

## 9.999 prompt và tự thử lại (1.0.22)

Tối đa 9.999 cảnh/prompt mỗi bộ. Vẫn lập theo lô tối đa 30 cảnh và chạy song song theo số tài khoản. Lô bị lỗi nội dung/định dạng hoặc kết nối sẽ tự thử lại tối đa 5 lần ngoài lần đầu, nghỉ tăng dần 2, 4, 8, 15, 15 giây. Lô đã hoàn thành giữ nguyên. Hết 5 lần vẫn lỗi thì báo lỗi và giữ phần đã lưu để Tiếp tục lập cảnh. Nút Dừng hủy cả lúc đang chờ thử lại. Khi Muse báo hết hạn mức, không thử lại. Tạo video vẫn chỉ bắt đầu khi bạn bấm chạy hàng đợi.

## Prompt trực tiếp vào hàng đợi và tạo video đồng thời (1.0.22)

Mỗi prompt hợp lệ hoàn chỉnh được lưu và thêm vào hàng đợi ngay khi Muse đang trả lời, không cần chờ hết bộ. Dừng ở 300/500 giữ 300 prompt trong hàng đợi; có thể chạy phần đã có hoặc tiếp tục lập phần còn thiếu. Phần câu đang viết dở, chưa thành prompt hợp lệ không được tính.

Bật Tự khởi động video khi có prompt (mặc định bật): khi có prompt đầu tiên, video bắt đầu, các prompt tiếp theo được thêm và xử lý nối tiếp trong cùng hàng đợi. Nếu tắt tùy chọn và hàng đợi chưa chạy, chỉ tích lũy; khi đang chạy, prompt mới sẽ được xử lý tiếp. Dừng hàng đợi ngăn tự khởi động lại dù Muse còn đang viết; cần chủ động chạy tiếp hoặc bắt đầu lần lập prompt mới.

Dữ liệu hai bước được hợp nhất khi lưu để không mất prompt mới hoặc ID/kết quả video. Tiếp tục lập prompt giữ lại ID và media đã có. Mở lại app cố khôi phục một lần các bộ prompt dở đã lưu ở bản cũ vào hàng đợi. Bỏ một bộ đã khôi phục thì không tự thêm lại.

## Chạy từ đầu đến cuối, thử lỗi sau (1.0.22)

Lượt chính: mỗi lô prompt hoặc cảnh video chỉ thử một lần, lỗi thì ghi nhận và chuyển ngay sang phần khác. Không thử 5 lần tại chỗ, không hủy các lô còn lại vì một lô lỗi. Sau khi chạy hết lượt chính mới quay lại lỗi, tối đa 5 lần bổ sung. Nếu lô prompt vẫn lỗi sau đó, giữ các prompt đã xong và báo phần thiếu; không ngăn video của phần đã có.

Sửa việc hàng đợi bỏ qua cả bộ mang trạng thái lỗi khi bộ đó tiếp tục nhận prompt mới. Các prompt mới chưa từng chạy vẫn được xử lý, còn cảnh lỗi cũ chờ lượt thử lại cuối. Dừng do người dùng hoặc Muse xác nhận hết hạn mức vẫn được ưu tiên.

Bản đang mở cần được thoát và cập nhật lên 1.0.22 để dùng cơ chế này. Không thay đổi bản đang chạy hoặc tự gửi lại video trên máy trong quá trình sửa.

## Giao diện sản xuất (1.0.22)

Bỏ khối Duyệt & tạo video lặp chức năng. Cột trái tập trung mô tả, số prompt, camera, phong cách/ánh sáng, thư mục đầu ra và nút thêm prompt. Cột phải là hàng đợi duy nhất: chạy/dừng, tiến độ từng bộ, lỗi, tiếp tục lập phần thiếu và bỏ bộ khỏi hàng đợi. Bốn số tổng hợp phía trên hiển thị bộ cảnh, prompt đã nhận, video hoàn thành và trạng thái.

Chi tiết prompt/kết quả mặc định thu gọn, mở bằng Chi tiết tại từng bộ. Các bản đã lưu được mở từ danh sách. Có nút Thư mục ở từng bộ để mở đúng nơi lưu của bộ đó. Thư mục ở cột thiết lập áp dụng cho bộ mới, không tự sao chép media hoặc thay nơi lưu bộ cũ khi đổi thiết lập.

## Khôi phục dữ liệu gateway (1.0.22)

Kiểm tra tệp tài khoản/tác vụ trước khi mở Chrome. Tự dùng bản .bak hợp lệ nếu JSON chính hỏng, giữ bản .corrupt riêng. Các lần lưu mới flush và fsync trước khi thay tệp, giữ bản JSON dự phòng. Nếu cả hai bản không hợp lệ thì báo rõ tệp dữ liệu, không tự xóa về danh sách rỗng và không báo nhầm lỗi Chrome.

## Tự kết nối khi mở ứng dụng (1.0.22)

Sau khi đăng nhập và lưu phiên một lần, các lần mở app sau tự khởi động gateway/Chrome nền với tài khoản đã lưu đang bật. Giao diện vẫn mở trong lúc kết nối. Không tự mở cửa sổ Chrome đăng nhập, không tự gửi prompt hay chạy video chỉ do mở app. Khi kết nối không thành công hoặc không có tài khoản khả dụng, hiện thông báo và nút mở tài khoản Muse để xử lý. Phiên hết hạn cần đăng nhập lại; không bảo đảm phiên được Muse giữ vĩnh viễn.

## Danh sách từng prompt (1.0.22)

Hàng đợi hiển thị mỗi prompt là một dòng riêng với số thứ tự, tiêu đề, mô tả, camera, trạng thái, chuyển động và thông báo lỗi. Prompt mới hoàn thành xuất hiện ngay trong danh sách. Có nút Xem video khi đã có kết quả và Mở thư mục. Chi tiết prompt mở phần chỉnh sửa/kết quả khi cần. Phân trang 20 prompt/trang, thứ tự theo thứ tự thêm vào hàng đợi rồi số cảnh trong mỗi lần tạo.

Không hiển thị từng bộ thành một dòng nữa. Các bộ vẫn được lưu nội bộ để giữ mô tả, tiến độ và ID cũ. Mục cũ mất dữ liệu không tạo dòng prompt trống; hiện cảnh báo và có thể bỏ mục trống. Cơ chế chạy, lỗi, thử lại và kết nối tự động giữ nguyên.


Bản 1.0.23: hàng đợi bỏ qua mục không còn dữ liệu để tiếp tục tạo video. Nút Dọn prompt làm trống hàng đợi khi đã dừng viết prompt và tạo video; giữ nguyên video trên ổ đĩa và bộ cảnh đã lưu.


Bản 1.0.24: tự tạm loại tài khoản hết hạn mức, chuyển yêu cầu sang tài khoản còn khả dụng, chỉ dừng khi không còn tài khoản dùng được. Hiện tên tài khoản hết hạn mức trên hàng đợi. Trạng thái tạm nghỉ lưu qua lần mở ứng dụng; thử lại sau tối thiểu một giờ, không khẳng định Muse đã cấp lại hạn mức.


Bản 1.0.25: mã gửi video cố định chống tạo trùng khi mất phản hồi; tra tác vụ qua kho gateway khi lịch sử giao diện thiếu; giữ lịch sử lớn và không loại tác vụ đang chạy. Cảnh cũ không xác định được mã chuyển sang Cần đối chiếu tác vụ. Kiểm tra gateway chờ 15 giây thay vì 2 giây.


Bản 1.0.26: nút Gửi lại cảnh lỗi có xác nhận cho cảnh cũ chưa rõ tác vụ hoặc hết lần thử. Giữ nguyên video hoàn thành và mã tác vụ còn chạy; lưu mã cũ để đối chiếu. Nút Chạy giải thích rõ nếu không còn cảnh đủ điều kiện tự chạy.


Bản 1.0.27: bảng tài khoản luôn đọc danh sách đã lưu trên máy, không phụ thuộc gateway trả lời. Tách trạng thái chưa xác minh với mất kết nối; không chồng nhiều lượt kiểm tra khi gateway chậm. Chỉ trả trường công khai, không đưa cookie ra giao diện.


Bản 1.0.28: nút Xóa cạnh mỗi tài khoản, có xác nhận. Ngừng giao việc mới rồi xóa tài khoản khỏi ứng dụng; giữ nguyên video và prompt đã lưu. Có thể đăng nhập lại để thêm sau.


Bản 1.0.29: cột Token bổ sung theo từng tài khoản; đọc nhãn tokens left trực tiếp từ Usage trong tab riêng. Lưu số liệu gần nhất và thời gian cập nhật, có nút Cập nhật token. Không suy ra 0 khi mất kết nối; không gửi prompt để đọc token.


Bản 1.0.30: tối đa 5 tài khoản hoạt động đồng thời. Chưa có prompt: tối đa 5 tài khoản viết, mỗi tài khoản một lô. Có prompt: 1 tài khoản viết và tối đa 4 tài khoản tạo video, mỗi tài khoản tối đa 5 video. Viết xong: tối đa 5 tài khoản tạo video. Hai vai trò không dùng chung tài khoản đồng thời; yêu cầu cũ hoàn tất trước khi đổi vai trò. Tài khoản hết hạn mức được thay bằng tài khoản dự phòng.


Bản 1.0.31: thoát ứng dụng chủ động dừng dịch vụ trước khi chờ các kết nối dài đóng. Dọn cây tiến trình Chrome chỉ khi khớp thư mục profile Muse và cổng debug riêng 19210/19211; không đóng Chrome cá nhân. Bấm Dừng chỉ dừng gửi/chờ công việc; thoát ứng dụng mới đóng toàn bộ Chrome Muse.


Bản 1.0.32: luân phiên tài khoản rảnh theo lần dùng gần nhất. Mỗi lượt tài khoản nhận tối đa 5 video rồi chờ các tác vụ đó hoàn tất trước khi nhường chỗ; prompt luân phiên sau mỗi lô. Vẫn tối đa 5 tài khoản hoạt động, tách vai trò prompt/video và giữ giãn gửi 1–2 giây.


Bản 1.0.33: bỏ luân phiên, giữ nhóm tối đa 5 tài khoản cố định. Chỉ thay tài khoản hết hạn mức, bị tắt/xóa hoặc phiên không còn dùng được. Giữ tách vai trò 1 viết prompt + 4 tạo video; viết xong cả 5 tạo video.


Bản 1.0.34: tự đóng tab/phiên Muse khi tài khoản bị loại khỏi nhóm, tắt/xóa, hết hạn mức; tab rảnh quá 30 giây cũng được dọn. Giữ nguyên tab có tác vụ đang chạy. Khi cần dùng lại, trình kết nối tự mở phiên và nạp đăng nhập đã lưu. Chrome dùng chung còn chạy để gateway sẵn sàng; Chrome cá nhân không bị tác động.

Giảm tải theo lựa chọn người dùng: tối đa 3 video/tài khoản, tổng tối đa 15 video; khi còn viết prompt tối đa 12 video với 4 tài khoản.


Bản 1.0.35 tổng hợp: hàng đợi chạy xuyên bộ với ngân sách chung 15 tác vụ, tối đa 5 tài khoản, 3 video/tài khoản. Lỗi được thử lại sau lượt chính; dừng giữ mã cũ, gửi lại cảnh chưa rõ cần xác nhận. Bộ lọc prompt theo trạng thái và thống kê tách đang chờ/đang xử lý/lỗi/hoàn thành. Giảm kiểm tra DOM video còn tối đa một lần mỗi 2 giây; tra trạng thái gateway trực tiếp trong tiến trình; lập chỉ mục kho tác vụ tránh đọc lại nhiều lần. Không tự cập nhật token khi đang tạo video; vẫn có nút cập nhật thủ công. Tự dọn phiên rảnh và chỉ đóng Chrome riêng của Muse khi thoát. Kiểm tra giao diện dùng dữ liệu giả lập, không gửi yêu cầu Muse.

Token: chỉ tự kiểm tra tài khoản báo hết hạn mức, giữ kết quả cũ; không quét toàn bộ tài khoản khi mở giao diện. Nút kiểm tra token áp dụng cho tài khoản đang bị giới hạn.

Khi tài khoản báo giới hạn: chỉ kiểm tra token bổ sung một lần cho đợt giới hạn đó, lưu nhãn và thời điểm rồi đóng tab Usage dù thành công hay lỗi. Không tự xóa tài khoản. Số token khác với lượt video 24 giờ.


Bản 1.0.36: chọn hiệu năng Tiết kiệm (2 tài khoản × 1 video), Cân bằng mặc định (3 × 2, tối đa 6 video), Nhanh (5 × 3). Giảm quét trạng thái video còn tối đa mỗi 5 giây. Đổi chế độ khi đã dừng công việc; ngừng đọc token trong khi tạo video/viết prompt. Tự đóng phiên rảnh vẫn được giữ.


Bản 1.2.0: điều phối tài nguyên tự động bật mặc định trong giới hạn chế độ đã chọn. Bắt đầu ít tác vụ, đo CPU/RAM toàn máy mỗi 5 giây bằng Windows API. Tải CPU cao kéo dài hoặc RAM cao thì giảm luồng mới. RAM >=96% hoặc còn dưới 0,5 GB sẽ tạm dừng nhận việc mới, tác vụ đã gửi vẫn tiếp tục. Chỉ tăng dần sau tải thấp ổn định; RAM giảm đủ và ổn định ba lần đo mới tiếp tục. Không hủy/gửi lại video vì tải máy. Có thể tắt tự điều phối khi công việc đã dừng. Bảng Điều phối hiển thị số tác vụ, mức nhận mới, trần và lý do. CPU/RAM là toàn máy, không riêng ứng dụng; giảm tải không có hiệu lực tức thì với tác vụ đang chạy.

Chi tiết bản tổng hợp 1.2.0: xem windows/RELEASE-1.2.0.vi.md trong mã nguồn.
