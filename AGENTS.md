# Bối cảnh VNUK Topic 06

Giảng viên yêu cầu demo binary patching trên phần mềm thực tế. Nhóm chọn `x64/7za.exe`, bản dòng lệnh độc lập trong gói chính thức **7-Zip Extra 26.06 x64** (`7z2606-extra.7z`). Thí nghiệm ban đầu đổi mức nén mặc định khi tạo `.7z` từ **Normal (5)** sang **Fast (3)** và giữ khả năng ghi đè bằng `-mx`. Demo nén và giải nén chạy trên Windows x64 qua PowerShell. x64dbg GUI dùng để trình diễn thao tác vá, còn giao diện 7-Zip nằm ngoài phạm vi đề tài.

Công cụ hiện tại ưu tiên kích thước archive và dùng bản vá PPMd mức 5. Xem `README.md` cho công cụ hiện tại và `legacy-fast3/README.md` cho thí nghiệm ban đầu.

Ưu tiên độ chính xác của project và khả năng trình diễn trước giảng viên. Người dùng đã hoãn phần báo cáo, nên chỉ chỉnh `docs/` hoặc PDF khi có yêu cầu mới về phần đó. `docs/VNUK-Project-Proposal-06-EN.pdf` là đề cương tiếng Anh. Báo cáo cuối kỳ `VNUK-Topic06-Final-Report-EN.pdf` từng được tạo ở workspace Codex cũ và hiện chưa có trong repo. Khi làm tiếp phần báo cáo, giữ bố cục mẫu VNUK và tập trung vào nguyên lý, kỹ thuật binary patching.

## Cơ chế bản vá Fast (3)

- Kỹ thuật đã chốt là **in-place instruction replacement with NOP padding**. Điểm vá thuộc hàm khởi tạo `FUN_004777a0`, tại RVA `0x777C8`, file offset `0x76BC8` và VA `0x004777C8` khi image base là `0x00400000`. Vùng thay thế dài 24 byte, với 17 byte thực sự thay đổi.
- Bản gốc khởi tạo `_level` bằng `0xFFFFFFFF`, biểu thị mức nén chưa được chỉ định. Khi bỏ `-mx`, giá trị này dẫn đến mặc định Normal (5). Bản vá tận dụng `EDX = 0` để gộp bốn lần ghi byte về 0 thành một lần ghi DWORD, dùng khoảng trống để đặt `_level = 3` ở `[RCX+0x28]`, rồi đệm 11 byte `NOP`. 7-Zip đọc `-mx` sau khi khởi tạo, nên tham số được truyền vẫn ghi đè giá trị 3.

## Tệp trong `legacy-fast3/`

| Tệp hoặc thư mục | Vai trò |
| --- | --- |
| `README.md` | Hướng dẫn demo tự động, vá thủ công bằng x64dbg và kiểm tra headless. |
| `reproduce.py` | Xác minh bản gốc, tạo hoặc nhận bản vá qua `--patched`, sinh dữ liệu thử 64 MiB và chạy T01–T07. Kết quả mới nằm trong `topic06-*`. |
| `verify_patch.py` và `topic06.1337` | Đối chiếu bản vá theo byte. Tệp `.1337` cũng dùng để nhập bản vá nhanh trong x64dbg. |
| `x64dbg-apply-template.txt` và `x64dbg-handler-template.txt` | Mẫu lệnh headless để ráp và xuất byte vá, rồi kiểm tra giá trị `_level` khi chạy. |
| `tools/Topic06Ghidra.java` | Trích disassembly và mã giả bằng Ghidra headless. |
| `tools/Get-Topic06Hashes.ps1` và `tools/Run-HandlerChecks.ps1` | Đối chiếu SHA-256 trong PowerShell và chạy bốn ca x64dbg headless. |
| `evidence/` | Kết quả T01–T07 và log, báo cáo đối chiếu byte, SHA-256 PowerShell, phân tích Ghidra, log debugger và ảnh GUI trước/sau. |

## Tiêu chí demo và lần xác minh gần nhất trong chat cũ

- T01 (gốc, mặc định) trùng T03 (gốc, `-mx=5`). T04 (vá, mặc định) trùng T02 (gốc, `-mx=3`) từng byte. T05 (vá, `-mx=5`) trùng T03. T06 (vá, `-mx=0`) dùng `Copy`. T07 dùng EXE gốc để kiểm tra và giải nén T04, rồi đối chiếu SHA-256 với `input.txt`.
- Với dữ liệu thử đã lưu, mức 3 cho `LZMA2:22` và 3.578.912 byte, mức 5 cho `LZMA2:25` và 3.290.062 byte. Thực nghiệm đo kích thước, phương thức nén, SHA-256 và tính toàn vẹn. Thời gian nén chưa được đo.
- Hai lỗi đã sửa ở commit `156e2fd`. Trong x64dbg 2026.05.27, bước đệm của demo GUI dùng `Binary → Fill...` trong Dump với hex `90`, rồi lưu EXE qua `File → Patch file`. `Run-HandlerChecks.ps1` trả 0 khi cả bốn ca đạt, mỗi ca có `FINAL status=pass asserts=2` và tiến trình thoát với mã 0. Bốn giá trị `_level` mong đợi lần lượt là `FFFFFFFF`, `3`, `5`, `0`.
- Lần xác minh cuối trong chat cũ ghi nhận T01–T07 đạt 7/7 và x64dbg headless đạt 4/4. Truyền EXE gốc vào `-Patched` làm ca `patched-default` thất bại và trả mã 1. Các tình huống mô phỏng timeout, thiếu dòng `FINAL`, sai số assertion hoặc debugger trả mã lỗi cũng được phát hiện.
- Lần đó đã chạy lại 7-Zip, đối chiếu SHA-256 bằng PowerShell và chạy x64dbg headless. Phần Ghidra 12.2 PUBLIC và x64dbg GUI được đối chiếu từ minh chứng đã lưu. Chat cũ ghi nhận 65 địa chỉ Ghidra khớp với EXE gốc và hai đoạn disassembly khớp `objdump`. README mô tả cả demo tự động và thao tác GUI để tập trước khi trình diễn trực tiếp.

## Git và nguồn trao đổi

Workspace hiện là repo `malware_project`, với remote `Duc1011/VNUK-topic06-7zip-patching`. Khi lưu ghi chú này, nhánh đang mở là `topic06-complete`, theo dõi `origin/topic06-complete`, ở commit `156e2fd`. Theo chat cũ, repo được đặt Private vì PDF có thông tin sinh viên. Ruleset `Protect main` đã được lưu, và GitHub lúc đó báo gói hiện tại chưa thực thi ruleset trên repo Private. Khi tiếp tục công việc, chỉ commit hoặc push theo yêu cầu của người dùng.

Nguồn lịch sử: [Đọc nội dung link ChatGPT](https://chatgpt.com/s/cx_6b05432f8c308191969ecdc27a6bb1db) và [Sửa báo cáo patching](https://chatgpt.com/share/6b008fad-3b2c-83ec-967e-fa2f6dd3fb08).
