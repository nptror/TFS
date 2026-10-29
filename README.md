# Tổng hợp báo vắng

Ứng dụng dành cho giáo vụ: dán tin nhắn từ nhóm lớp, chuẩn hóa tên và trạng thái,
kiểm tra cảnh báo, sửa báo cáo trực tiếp và tải Excel. Bản này triển khai theo
đặc tả FastAPI trong tệp yêu cầu mới nhất.

## Cài đặt và chạy

Cần Python **3.11 trở lên**. Mở terminal tại thư mục chứa `requirements.txt`.

Windows PowerShell:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
uvicorn app.main:app --reload
```

Nếu PowerShell không cho chạy script kích hoạt, dùng trực tiếp Python của môi trường:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload
```

macOS / Linux:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload
```

Mở **http://127.0.0.1:8000**. Frontend được backend phục vụ trực tiếp;
không mở HTML bằng `file://`. Dán tin nhắn và xuất Excel hoạt động ngay,
không cần Internet sau khi cài thư viện.

## Sử dụng

1. Dán tin nhắn ở cột trái, hoặc bấm **Dùng ví dụ** để thử dữ liệu mẫu.
2. Chọn buổi, ngày, ca. Ngày mặc định hôm nay theo thiết bị; thứ tự tính từ ngày.
3. Bấm **Format**, hoặc **Ctrl+Enter** (macOS: **Cmd+Enter**).
4. Xem các mục tô vàng. Sửa trực tiếp bản báo cáo ở bên phải nếu cần.
5. Bấm **Copy** hoặc **Xuất Excel**. Excel đọc lại **bản đang hiển thị**,
   không lấy danh sách cũ trước khi sửa.

Đầu vào và bản báo cáo được tự lưu trong `localStorage` của trình duyệt. Nếu có báo
cáo đã soạn, lần mở lại giữ ngày cũ của bản nháp; nếu chưa có báo cáo thì dùng hôm nay.
**Xóa nội dung** xóa text và báo cáo đang làm.

## Nhập điểm từ phiếu scan (`/nhapdiem`)

Trang **http://127.0.0.1:8000/nhapdiem**: tải Excel danh sách (cột điểm còn trống) và PDF
phiếu điểm viết tay → kiểm tra các dòng ⚠ → tải Excel đã có điểm. Lõi OCR nằm trong `app/ocr/`.

Cài thêm (không bắt buộc cho trang báo vắng):

1. Thư viện Python: `pip install -r requirements-nhapdiem.txt`
   (OpenCV phải là bản 4.x; bản 5 đã bỏ HOG mà mô hình chữ số cần).
2. Chương trình **Tesseract OCR** để đọc họ tên, ngày sinh in sẵn:
   - Windows: bộ cài UB Mannheim — https://github.com/UB-Mannheim/tesseract/wiki
     (cài vào thư mục mặc định; tick **Vietnamese** để đọc tên có dấu).
   - Ubuntu/Docker: `apt install tesseract-ocr tesseract-ocr-vie`.

Chưa cài thì trang vẫn mở nhưng báo lỗi rõ ràng khi bấm Đọc. Render (bản Python thường)
không có Tesseract; muốn chạy trang này trên Render cần deploy bằng Docker.

- Ghép học sinh theo họ tên (bỏ dấu, so gần đúng) + ngày sinh + lớp; không dùng SBD.
- Dòng ⚠: điểm chưa chắc (< 0.85), không đọc được, vắng/trống, tên chưa chắc, ô Excel đã có điểm.
  Điểm viết tay đọc đúng khoảng 87%, nên **luôn duyệt các dòng ⚠ trước khi xuất**.
- **Xem trước** trước khi tải: bảng cột điểm sau khi ghi (điểm mới, điểm ghi đè, học sinh
  chưa có điểm) và phiếu scan bên cạnh; bấm số trang để mở đúng trang phiếu.
- Một học sinh bị ghép 2 lần thì không cho xuất. Dòng không chọn học sinh hoặc để trống điểm
  sẽ không được ghi. File xuất giữ nguyên công thức và dữ liệu khác.
- Giới hạn: Excel 10 MB, PDF 40 MB, tối đa 30 trang mỗi lần. File `.xls` cũ cần LibreOffice
  để tự chuyển, hoặc lưu lại thành `.xlsx`.
- Mô hình chữ số dùng mẫu có sẵn trong `app/ocr/du_lieu_hoc/digits.npz`; trang web không tự học thêm
  nét chữ từ các điểm đã duyệt.

## Danh sách lớp

Sửa `config.json` để cập nhật các lớp cần báo:

```json
{
  "classes": ["10C2", "10C4", "10C5", "10C6", "10C10", "12C2", "12C3", "12C8", "12C9", "12C11", "12C12", "12C16", "12C17", "12C18"]
}
```

Backend đọc lại config mỗi lần xử lý, không cần khởi động lại. Tải lại trang để
cập nhật danh sách hiển thị bên dưới. Lớp thiếu báo cáo vẫn xuất hiện với số vắng
để trống, kèm cảnh báo **Chưa báo**. Mã ngoài danh sách vẫn được giữ nhưng có cảnh báo.
Dùng `{"classes": []}` (mặc định) nếu không có danh sách cố định; khi đó chỉ các lớp
bạn dán vào được báo cáo, không thêm lớp thiếu và không cảnh báo mã lạ.

## Quy tắc và các trường hợp cần kiểm tra

- Chuẩn hóa `Lớp 12c9`, `12 C9`, `10 C 6` thành mã lớp viết hoa.
- Nhận cả mã lớp dính từ khóa: `12c6vắng 0`, `12c6v 0`, `12c6v0`.
- Bỏ thời gian và tên người gửi trong tin xuất từ chat như
  `[24/10/2026 07:19:35] Nguyễn Quốc Khánh: 12c13 vắng 0`. Ranh giới tin nhắn
  vẫn được giữ để tin không có lớp không dính vào tên học sinh của lớp trước.
- Mỗi mã lớp mở một khối đến mã lớp kế tiếp, kể cả nhiều dòng.
- Nhận `vắng`, `văng`, `vang`; tách `sĩ số40`, `sĩ số 40`, `si so 40`, `ss 40`.
- Nhận `vắng2`, `vắng0`, `v3`, `v 1`, `v:0`, `vắng (3)`; `đủ`, `đi đủ`,
  `đủ ạ`, `lớp đủ` được hiểu là 0 vắng. Không xóa các từ giống từ khóa nằm trong họ tên.
- Tách số thứ tự khỏi tổng khai báo: `11c1 vắng2 1 tấn phát 2. Nhật uy`
  thành hai tên Tấn Phát và Nhật Uy, đều mặc định K nếu không ghi P/K.
- Tách tên theo dấu phẩy, chấm phẩy, xuống dòng hoặc ngay sau `(P)/(K)/(?)`.
- Nhóm `4K ... 1P ...` duy trì trạng thái qua các dòng; trạng thái sau tên ưu tiên
  hơn trạng thái nhóm. `(?)` giữ trạng thái chưa rõ, kể cả trong nhóm P/K.
- Nhận nhóm viết đầy đủ: `Vắng không phép: (6) ...` hoặc `Vắng có phép: ...`.
  Có thể bỏ số đếm nhóm; ứng dụng chỉ đối chiếu số đếm khi thực sự được khai báo.
- Nhận nhãn ngắn `K: a, b` / `P: c` (bắt buộc có `:` hoặc `=`), cùng dòng hoặc xuống dòng.
  Dấu `...` cuối danh sách được bỏ qua.
- `có phép hết`, `không phép cả` đứng sau danh sách tên áp cho các tên chưa ghi P/K trước đó.
- Phần `Trễ: (2) ...`, `trễ 1 ...` và các tên có `(T)`, `(t)`, `(T 1t)`,
  `(T 2t)`, `(trễ)`, `(muộn)` được bỏ qua hoàn toàn khi xuất báo cáo:
  không nằm trong danh sách vắng, không hiện trong cảnh báo hay Ghi chú Excel.
  Nếu khai báo `Vắng 2` nhưng cả hai tên đều `(T)`, kết quả là 0 vắng kèm cảnh báo
  chênh số; không tự chuyển T thành K. Ký hiệu lạ như `(X)` vẫn giữ tên với `(?)`
  và cảnh báo ký hiệu gốc.
- Lớp trùng lấy lần cuối, kèm cảnh báo đã ghi đè. Riêng tin `10C8 bổ sung vắng ...`
  (`bổ sung`, `bs`, `thêm` ngay sau mã lớp) được cộng thêm vào lần báo trước.
  “Lần cuối” là thứ tự trong nội dung dán, không phải thời gian trong dấu ngoặc.
  Khi dán lịch sử nhiều ngày, ứng dụng không tự lọc ngày hoặc sắp xếp lại tin nhắn.
- Khi có tên, số vắng đầu ra bằng số tên. Nếu số khai báo khác số tên, cảnh báo
  giữ nguyên số khai báo để đối chiếu. Nếu chỉ có `vắng 3` mà không có tên,
  vẫn giữ số 3 và cảnh báo thiếu tên, không đổi thành 0.
- Khi không có số lẫn tên, để trống số vắng. `Vắng 0` chỉ dùng khi thực sự khai báo 0.
- Tên không ghi P/K (và không thuộc nhóm P/K) mặc định là **K**, kèm cảnh báo "Không ghi P/K, mặc định K" liệt kê riêng. `(?)` là ký hiệu chưa rõ: ghi `(?)` và đưa vào "Chưa rõ P/K".
- Tên viết hoa đầu từ; dấu tiếng Việt được chuẩn hóa Unicode NFC.
  Tên viết tắt như `h.l bảo ngọc` thành `H.L Bảo Ngọc`, không đoán tên đầy đủ.
- Phần trước mã lớp đầu tiên và các đoạn sai cú pháp được giữ trong cảnh báo.
- Một chuỗi chỉ có chữ, nằm trong khối lớp, có thể là tên hoặc câu bình luận.
  Regex không tự suy đoán ngữ nghĩa; tên không có P/K sẽ được cảnh báo để kiểm tra.
  Các tên không có bất kỳ dấu phân cách nào cần được sửa tay.

Mẫu đầu ra:

```text
Chiều thứ 6, ngày 23/10/2026, ca 1:
10C2 Vắng  0
10C4 Vắng  1 Thịnh (P)
10C10 Vắng  

12C9 Vắng  3 Nhật Huy (P), Tuấn Huy (P), Duy Hải (K)
12C11 Vắng  1 Phương Thảo (?)
```

Sắp xếp theo khối rồi số lớp, sau đó chữ cái nếu cùng số; giữa các khối có dòng trống.
Chủ nhật viết `Sáng Chủ nhật, ngày ...`, không viết `thứ Chủ nhật`.

## Sửa tay và Excel

Khi sửa kết quả, cảnh báo tự kiểm tra lại sau khoảng nửa giây qua `/api/preview`.
Copy giữ nguyên nội dung đang sửa; Excel parse lại
nội dung đó, nhóm/sắp xếp lại và làm mới cảnh báo.

Sĩ số gốc được giữ khi xuất vì mẫu text không hiển thị sĩ số. Có thể sửa rõ sĩ số
trong bản kết quả bằng cách thêm `sĩ số 42` vào dòng lớp. Nếu nhập một bản báo cáo
mới trực tiếp mà không Format đầu vào, cột sĩ số để trống trừ khi bản đó có sĩ số.

Cảnh báo gốc như chênh số khai báo hoặc đã ghi đè được giữ cho những dòng chưa sửa.
Khi nội dung dòng thực sự thay đổi, cảnh báo của dòng được tính lại. Phần ngoài lớp
từ đầu vào vẫn được giữ trong ghi chú cuối bảng Excel để không bỏ sót thông tin.
Xóa một dòng lớp nằm trong config khiến lớp đó trở về trạng thái chưa báo.

Nếu sửa tiêu đề đúng mẫu, ngày/buổi/ca trong tiêu đề được ưu tiên khi xuất. Thứ được
tính lại từ ngày để bảo đảm đúng lịch. Tiêu đề sai mẫu sẽ báo lỗi để bạn sửa lại.

Excel có 7 cột: **Lớp | Sĩ số | Số vắng | Có phép | Không phép | Danh sách vắng | Ghi chú**.
Tiêu đề gộp `A1:G1`, in đậm; dòng có cảnh báo tô vàng, nội dung cảnh báo ở Ghi chú.
Cột rộng, tự ngắt dòng, cố định hai dòng đầu, in ngang A4. File mẫu:
`bao-vang_2026-10-23_chieu_ca1.xlsx`.

## API

Tài liệu tương tác: **http://127.0.0.1:8000/docs**.

### `POST /api/format`

`multipart/form-data`:

| Trường | Giá trị |
| --- | --- |
| `text` | Text đầu vào, tối đa 100.000 ký tự |
| `buoi` | `Sáng` hoặc `Chiều` |
| `ngay` | `YYYY-MM-DD` |
| `ca` | Số nguyên từ 1 đến 99 |

Trả về `data` (schema `lop` cùng metadata đối chiếu), `text`, `warnings`, `session`,
`summary`. Mỗi cảnh báo có `code`, `class_name`, `message`, `raw`.

### `POST /api/export`

JSON:

```json
{
  "text": "Chiều thứ 6, ngày 23/10/2026, ca 1:\n12C9 Vắng  1 An (P)",
  "buoi": "Chiều",
  "ngay": "2026-10-23",
  "ca": 1,
  "source_data": null
}
```

Frontend truyền `source_data` từ lần Format gần nhất để giữ sĩ số và cảnh báo gốc
cho các dòng chưa đổi. API cũng dùng được khi không có `source_data`.
Trả file `.xlsx` với `Content-Disposition: attachment`.

### API phụ

- `POST /api/preview`: cùng payload như export, trả dữ liệu và cảnh báo đã tính lại.
- `GET /api/config`: danh sách lớp.

Lỗi trả JSON `{"detail": "Thông báo tiếng Việt"}`. Giao diện giữ lại
nội dung đang có khi một yêu cầu thất bại.

## Kiểm thử

```bash
python -m pytest -q
```

Bao gồm từng lớp trong dữ liệu mẫu, khoảng trắng/dấu tiếng Việt, sĩ số, trạng thái
nhóm/riêng, lớp trùng, thiếu thông tin, sắp xếp số, Chủ nhật, API và đọc ngược file
Excel để kiểm tra nội dung, màu nền, gộp ô và số liệu sau khi sửa tay.

## Cấu trúc

```text
app/
  __init__.py
  main.py              # FastAPI, routes và xử lý bản sửa tay
  models.py            # Schema Pydantic dùng chung
  parser.py            # Regex thuần, parse_message(text)
  validator.py         # Cảnh báo, lớp thiếu, sắp xếp
  formatter.py         # Dữ liệu -> text, đọc tiêu đề
  excel_export.py      # openpyxl -> file trong bộ nhớ
  nhapdiem.py          # Router /nhapdiem
  ocr/                 # Tách bảng, đọc chữ in (Tesseract), mô hình chữ số viết tay
  static/index.html    # Toàn bộ HTML, CSS, JavaScript thuần
  static/nhapdiem.html # Trang nhập điểm
tests/
  conftest.py
  test_parser.py
  test_api.py
  test_nhapdiem.py     # Bỏ qua nếu chưa cài requirements-nhapdiem.txt
config.json
requirements.txt
requirements-nhapdiem.txt
pytest.ini
README.md
```

Không database. Text không được backend lưu, Excel tạo trong RAM.
Mặc định uvicorn chỉ mở trên `127.0.0.1`; ứng dụng dành cho chạy cục bộ, chưa có
đăng nhập cho triển khai công khai. Nháp tồn tại trong trình duyệt cho tới khi xóa.
