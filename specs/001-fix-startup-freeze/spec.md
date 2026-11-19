# Feature Specification: Fix startup freeze

**Feature Branch**: `001-fix-startup-freeze`

**Created**: 2026-11-19

**Status**: Implemented (retroactive spec written after fix, at user's request, for verification)

**Input**: User description: "App Muse Landscape Studio bị đơ (treo cứng giao diện) mỗi lần mở lên. Cần tìm nguyên nhân và sửa."

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Mở app bình thường (Priority: P1)

Người dùng bấm mở Muse Landscape Studio từ icon hoặc Start Menu, mong đợi giao diện hiện ra và dùng được trong vài giây.

**Why this priority**: Đây là lỗi chặn hoàn toàn việc dùng app — không mở được thì không làm gì khác được.

**Independent Test**: Mở app, đo thời gian từ lúc cửa sổ xuất hiện đến lúc giao diện (danh sách cảnh, nút tạo video...) hiển thị và bấm được.

**Acceptance Scenarios**:

1. **Given** app chưa chạy, **When** người dùng mở Muse Landscape Studio, **Then** giao diện hiển thị đầy đủ và phản hồi được trong vòng vài giây, không bị treo trắng/đứng hình.
2. **Given** máy đang chạy phần mềm điều khiển máy từ xa (AnyDesk/UltraViewer) hoặc phần mềm hỗ trợ tiếp cận (Narrator...), **When** người dùng mở app, **Then** app vẫn mở bình thường, không bị ảnh hưởng.

### User Story 2 - Mở lại app nhiều lần liên tiếp (Priority: P2)

Người dùng tắt rồi mở lại app nhiều lần trong một buổi làm việc.

**Why this priority**: Lỗi gốc là một vòng lặp đệ quy xảy ra mỗi lần tạo cửa sổ mới — cần đảm bảo không chỉ lần mở đầu mà mọi lần mở sau đều ổn định.

**Independent Test**: Mở, đóng, mở lại app liên tiếp ít nhất 3 lần; theo dõi file log (`Data/app.log`) không phát sinh lỗi lặp lại.

**Acceptance Scenarios**:

1. **Given** app đã đóng hoàn toàn, **When** mở lại, **Then** hành vi giống lần mở đầu (không treo, không lỗi log).

### Edge Cases

- App vẫn phải mở được khi không có mạng/không có tài khoản Muse nào kết nối (màn hình chính vẫn render, chỉ phần trạng thái tài khoản báo "chưa sẵn sàng").
- Nếu WebView2 Runtime chưa cài hoặc lỗi hoàn toàn, app phải rơi về chế độ trình duyệt (browser mode) đã có sẵn, không crash im lặng.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: Ứng dụng MUST hiển thị xong giao diện chính (render đầy đủ) trong vòng tối đa 15 giây sau khi cửa sổ được tạo, trong điều kiện máy bình thường.
- **FR-002**: Quá trình khởi tạo cửa sổ MUST không được rơi vào vòng lặp xử lý nội bộ không có điểm dừng (không giới hạn thời gian/số bước).
- **FR-003**: File log của ứng dụng (`app.log`) MUST không chứa chuỗi lỗi lặp lại hàng loạt liên quan đến việc dò thuộc tính cửa sổ gốc (native window) sau khi mở app thành công.
- **FR-004**: Hành vi mở app MUST giống nhau dù máy có đang chạy phần mềm điều khiển từ xa (AnyDesk/UltraViewer) hay không — không được là nguyên nhân gây treo.

### Key Entities

- **Cửa sổ ứng dụng (app window)**: cửa sổ giao diện chính người dùng thấy khi mở app, dựng trên nền WebView2.
- **Cầu nối JS API (update bridge)**: cơ chế cho phép giao diện web gọi vào vài hàm Python của app (ví dụ nút "Cập nhật"); không được vô tình để lộ toàn bộ cấu trúc nội bộ của cửa sổ ra cho cơ chế dò quét tự động.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: 100% số lần mở app trong 3 lần thử liên tiếp, giao diện hiển thị và dùng được trong dưới 15 giây.
- **SC-002**: 0 dòng lỗi lặp dạng dò thuộc tính cửa sổ gốc xuất hiện trong `app.log` sau khi mở app.
- **SC-003**: Dung lượng `app.log` sinh ra cho một lần mở-rồi-đóng app giảm từ hàng MB (trước khi sửa) xuống dưới vài KB.

## Assumptions

- Phạm vi chỉ sửa nguyên nhân gây treo khi KHỞI ĐỘNG app; không mở rộng sang các luồng khác (tạo video, quản lý tài khoản Muse...).
- Môi trường thử nghiệm là Windows 10/11 có WebView2 Runtime đã cài (điều kiện vận hành bình thường của app).
- Không cần sửa gì ở phần giao diện web (dashboard/React) — lỗi nằm hoàn toàn ở lớp host Windows (desktop launcher).
