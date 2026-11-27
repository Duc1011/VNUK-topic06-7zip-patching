# VNUK Topic 06 — Tối ưu kích thước archive 7z trên Windows x64

`bin\7za-ppmd.exe` là bản vá của `x64/7za.exe` từ **7-Zip Extra 26.06**. Khi chạy trực tiếp để tạo `.7z` mà bỏ `-m0` và `-mx`, EXE vá mặc định dùng **PPMd mức 5**. `Compress-Topic06.ps1` chạy ba cấu hình, kiểm tra từng archive bằng 7-Zip gốc và xuất archive hợp lệ nhỏ nhất đã đo được.

## Thiết lập và nén dữ liệu

Chạy từ thư mục repo trên Windows x64 bằng Windows PowerShell 5.1 hoặc PowerShell 7 x64. Thiết lập cần **Python 3.11+** và `tar.exe` của Windows. Sau khi thiết lập, có thể chạy script nén hoặc EXE trực tiếp.

```powershell
python .\setup_compression.py

# Hoặc dùng gói chính thức đã tải sẵn để thiết lập ngoại tuyến
python .\setup_compression.py --package 'D:\Tải xuống\7z2606-extra.7z'

powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\Compress-Topic06.ps1 `
    -Source 'D:\Tài liệu dự án' -Output 'D:\Backup\Tài liệu dự án.7z'
```

Script thiết lập kiểm tra SHA-256 của [gói phát hành](https://github.com/ip7z/7zip/releases/expanded_assets/26.06), EXE gốc và EXE đã vá rồi tạo `bin\7za.exe`, `bin\7za-ppmd.exe` và `bin\License.txt`. Các tệp có sẵn với đúng nội dung được dùng lại. Nếu chọn thư mục cài riêng với `--output-dir`, truyền cùng thư mục cho `-BinaryDirectory` khi nén.

`-Source` nhận một tệp hoặc thư mục. `-Output` cần đuôi `.7z`, thư mục cha có sẵn và tên archive chưa tồn tại. Đối với thư mục, archive chứa thư mục nguồn, các thư mục con và tệp trong đó. 7-Zip lưu liên kết tượng trưng dưới dạng liên kết qua `-snl`. Giữ dữ liệu nguồn ổn định trong lúc chạy các ứng viên.

| Ứng viên | Cấu hình |
| --- | --- |
| `Original default` | `7za.exe` với mặc định LZMA2 mức 5 |
| `Patched default` | `7za-ppmd.exe` với mặc định PPMd mức 5 |
| `PPMd Ultra` | `7za.exe -m0=PPMd -mx=9`, có lợi trên mẫu 64 MiB |

Bảng đầu ra ghi `Method` từ `7za l -slt`, `Bytes` theo kích thước tệp và `Check` theo trạng thái nén và kiểm tra. `PASS` yêu cầu `a`, `t` và `l` trả mã 0. Khi bằng kích thước, ứng viên xuất hiện trước trong bảng thắng. Dòng `Reduction vs. original default` ghi số byte và phần trăm tiết kiệm khi bản gốc hợp lệ. Dòng `Archive` ghi đường dẫn đích cuối cùng. Mã thoát là 1 khi xảy ra lỗi, kể cả khi toàn bộ ứng viên thất bại.

Script tạo từng archive thử ở ngoài thư mục nguồn, kể cả khi đặt `-Output` bên trong nguồn. Sau khi kiểm tra, nó sao chép archive thắng vào một tệp tạm cạnh đích và đổi tên sang đường dẫn đã chọn. Thao tác đổi tên từ chối ghi đè nếu đích được tạo trong lúc chạy. Cần đủ chỗ cho các archive ứng viên và bản sao tạm cạnh đích. Script dọn các tệp tạm của lượt chạy.

## Benchmark và lựa chọn mặc định

Đo trên EXE gốc đã xác minh với `.7z`, `-mmt=1`, cùng đầu vào và archive mới mỗi ca. Số giây là thời gian của lệnh `a`. Cả 15 ca trả mã 0 ở `a`, `l`, `t` và `x`. Đường dẫn tương đối và SHA-256 khớp sau khi giải nén bằng EXE gốc. [Kết quả đầy đủ](evidence/size-optimization/benchmark/results.json)

| Cấu hình trên EXE gốc | `input.txt` 64 MiB (byte · giây) | Thư mục văn bản/log (byte · giây) | Mẫu ZIP (byte · giây) |
| --- | ---: | ---: | ---: |
| Mặc định | 3.290.062 · 28,7564 | 643.952 · 1,8450 | **2.098.189 · 0,6142** |
| `-m0=LZMA2 -mx=5` | 3.290.062 · 33,5633 | 643.952 · 2,2878 | 2.098.189 · 0,5641 |
| `-m0=LZMA2 -mx=9` | 3.897.111 · 47,6442 | 589.317 · 3,8183 | 2.098.189 · 0,5778 |
| `-m0=PPMd -mx=5` | 5.762.260 · 1,3599 | **351.369 · 0,1350** | 2.149.717 · 1,3222 |
| `-m0=PPMd -mx=9` | **2.411.600 · 7,3983** | 396.442 · 1,3690 | 2.142.466 · 1,2342 |

Chọn **PPMd mức 5** cho EXE vì bộ văn bản/log mục tiêu giảm **292.583 byte (45,44%)** so với mặc định gốc. Với tệp 64 MiB, PPMd mức 9 giảm **878.462 byte (26,70%)** và PPMd mức 5 tăng 2.472.198 byte. Mẫu ZIP giữ kết quả gốc với mức giảm **0 byte**. LZMA2 mức 9 chỉ cải thiện kích thước so với mặc định trên bộ văn bản/log trong ba mẫu này, nơi cả hai cấu hình PPMd đều nhỏ hơn, nên ba ứng viên trên đủ để chọn kết quả tốt nhất đã đo được. Kích thước và thời gian phụ thuộc dữ liệu. Chi phí của script là chạy nhiều ứng viên tuần tự. RAM chưa được đo.

`-m0` chọn phương pháp nén có chỉ số 0, ví dụ `-m0=LZMA2` hoặc `-m0=PPMd`. `-mx` chọn mức cấu hình, ví dụ Normal (`5`) và Ultra (`9`). LZMA2 dùng từ điển để thay chuỗi lặp bằng tham chiếu rồi mã hóa xác suất. PPMd dự đoán byte tiếp theo dựa trên ngữ cảnh các byte trước đó và mã hóa theo xác suất dự đoán. Tăng mức có thể đổi kích thước từ điển hoặc mô hình và ảnh hưởng đến thời gian, bộ nhớ và kích thước archive. [Định dạng 7z](https://www.7-zip.org/7z.html) · [Mã nguồn 7-Zip 26.06](https://github.com/ip7z/7zip/tree/26.06)

## Chạy trực tiếp EXE và tái tạo bản vá

Chạy ở thư mục repo và dùng tên archive mới cho mỗi lệnh. Dòng `Method` trong `l -slt` của `demo-ppmd.7z` là `PPMD`. Dùng 7-Zip gốc để đọc, kiểm tra và giải nén archive.

```powershell
.\bin\7za-ppmd.exe a -t7z -mmt=1 demo-ppmd.7z 'D:\Tài liệu dự án'
.\bin\7za.exe l -slt demo-ppmd.7z
.\bin\7za-ppmd.exe a -t7z -mmt=1 -m0=LZMA2 demo-lzma2.7z 'D:\Tài liệu dự án'
.\bin\7za-ppmd.exe a -t7z -mmt=1 -mx=9 demo-ultra.7z 'D:\Tài liệu dự án'
.\bin\7za-ppmd.exe a -t7z -mmt=1 -mx=0 demo-copy.7z 'D:\Tài liệu dự án'
```

Ghidra 12.2 định vị `CHandler::SetMainMethod` tại `FUN_0047829c`. Lệnh vá nằm trong nhánh danh sách phương pháp rỗng ở RVA **`0x78339`**, file offset **`0x77739`**, VA **`0x00478339`** tại image base `0x00400000`. Chín byte thay thế đặt con trỏ mặc định về chuỗi `PPMD` sẵn có trong `.rdata`, tại RVA `0xFD1E0`, rồi đệm hai `NOP`. Nhánh sau kiểm tra mức bằng 0 và vẫn thay con trỏ bằng `Copy` qua `cmove`. Giá trị mức chưa chỉ định (`FFFFFFFF`) và mức mặc định 5 đều vượt qua cùng phép kiểm tra khác 0. Các phương pháp cụ thể từ `-m0` đến qua nhánh danh sách có phần tử và xử lý mức từ `-mx` nằm sau điểm vá. [Mã nguồn `SetMainMethod`](https://github.com/ip7z/7zip/blob/26.06/CPP/7zip/Archive/7z/7zHandlerOut.cpp) · [Ghidra gốc](evidence/size-optimization/ghidra-original.txt) · [Ghidra bản vá](evidence/size-optimization/ghidra-patched.txt)

```text
Gốc
  78339  8D 53 05              lea edx,[rbx+0x5]
  7833C  83 F9 FF              cmp ecx,-1
  7833F  0F 44 CA              cmove ecx,edx
Vá
  78339  4C 8D 2D A0 4E 08 00  lea r13,[rip+0x84ea0]  ; PPMD
  78340  90                    nop
  78341  90                    nop
```

| Tệp | SHA-256 |
| --- | --- |
| `7z2606-extra.7z` | `396c180f12d2247c24b0b1fcd482c6fc2a2700f61211ffede1061dd971f5e104` |
| `bin/7za.exe` | `dd3757f31c97e33776f2590317d4fb12f2da075db3dbb1e3f94d0f2a01d84ffa` |
| `bin/7za-ppmd.exe` | `1cb1b0b4546dc11598a2ea3a22a639e475c2d33b8f7b8a94e304a3a18faa6b19` |

Thiết lập thông thường tái tạo EXE bằng chín byte đã xác minh. Để lặp lại bước debugger, điền đường dẫn tệp xuất vào `EXPORT_PATH` trong bản sao của `x64dbg-ppmd-template.txt`, chạy x64dbg headless 2026.05.27 trên EXE gốc rồi dùng `--x64dbg-export` để ghép byte và đối chiếu SHA-256 toàn EXE. [Log x64dbg](evidence/size-optimization/x64dbg-apply.txt) · [Log thiết lập](evidence/size-optimization/setup.txt)

```powershell
& 'C:\tools\x64dbg\release\x64\headless.exe' -testing -cf 'D:\Lab\apply-ppmd.txt' `
    (Resolve-Path .\bin\7za.exe).Path
python .\setup_compression.py --package 'D:\Tải xuống\7z2606-extra.7z' `
    --x64dbg-export 'D:\Lab\ppmd-export.bin'
```

Tái chạy benchmark và kiểm thử vào thư mục minh chứng mới. `--fixture` có thể dùng để đưa lại tệp `input.txt` cũ. Khi bỏ tham số này, script tái tạo đúng tệp từ seed và đối chiếu SHA-256.

```powershell
python .\benchmark_compression.py --package 'D:\Tải xuống\7z2606-extra.7z' `
    --evidence-dir .\topic06-benchmark-moi
python .\test_compression.py --evidence-dir .\topic06-xac-minh-moi
```

Tám ca chạy EXE trực tiếp đạt, gồm các đối chiếu archive từng byte cho mặc định PPMd, `-m0=LZMA2`, `-mx=9` và `-mx=0` (`Copy`). Bảy ca trên Windows PowerShell 5.1 đạt, gồm tệp văn bản, thư mục Unicode có đích bên trong nguồn, ZIP, nguồn thiếu, đích có sẵn, một ứng viên thất bại và toàn bộ ứng viên thất bại. Các archive được xuất đều giải nén bằng 7-Zip gốc và khớp đường dẫn cùng SHA-256. PowerShell 7 cũng được kiểm tra với một tệp Unicode. [EXE trực tiếp](evidence/size-optimization/verification/direct-results.json) · [Windows PowerShell 5.1](evidence/size-optimization/verification/cli-results.json) · [PowerShell 7](evidence/size-optimization/powershell7.txt)

## Kịch bản trình bày 3–5 phút

1. **Phút 0–1.** Chọn một thư mục văn bản có vài tệp, ví dụ `D:\Tài liệu dự án`. Chạy lệnh `Compress-Topic06.ps1` ở phần thiết lập.
2. **Phút 1–2.** Chỉ vào `Original default`, số byte của ứng viên thắng, `Check = PASS` và đường dẫn `Archive`.
3. **Phút 2–3.** Giải nén bằng EXE gốc vào thư mục mới. Đối chiếu đường dẫn tương đối và SHA-256. Kết quả khớp khi `Compare-Object` không in khác biệt.

   ```powershell
   .\bin\7za.exe x 'D:\Backup\Tài liệu dự án.7z' '-oD:\Khôi phục demo'
   function Get-TreeHashes($Root) {
       $base = (Get-Item -LiteralPath $Root).FullName.TrimEnd('\')
       Get-ChildItem -LiteralPath $base -File -Recurse -Force | ForEach-Object {
           '{0} {1}' -f (Get-FileHash -LiteralPath $_.FullName -Algorithm SHA256).Hash,
               $_.FullName.Substring($base.Length + 1)
       }
   }
   Compare-Object @(Get-TreeHashes 'D:\Tài liệu dự án') `
       @(Get-TreeHashes 'D:\Khôi phục demo\Tài liệu dự án')
   ```

4. **Phút 3–5.** Chạy riêng `bin\7za-ppmd.exe` bỏ `-m0` và `-mx`, rồi chiếu `Method = PPMD` và vùng RVA `78339` trong log x64dbg hoặc Ghidra. EXE quyết định PPMd mặc định. PowerShell tự động thử ứng viên, kiểm tra tính hợp lệ và chọn theo số byte.

## Thí nghiệm Fast (3) ban đầu

Hướng dẫn, script tái tạo, tệp vá x64dbg và minh chứng của bản Fast (3) nằm trong [`legacy-fast3/`](legacy-fast3/README.md).
