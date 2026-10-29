# Family AI Game Day

Ứng dụng Python + Streamlit cho **Football, Tic Tac Toe, Rock Paper Scissors,
Red Light Green Light và Basketball**. Giao diện tiếng Việt, bốn người chơi chia
hai đội, chấm video tại máy chạy ứng dụng và xuất kết quả JSON có SHA-256.

## Chạy trên máy này

Môi trường Python riêng nằm trong `.venv`; không thay đổi Python hệ thống.

```bash
cd /Users/dolavietnamdolavietnam/Desktop/test2/family_ai_app
bash run.sh
```

Mở **http://localhost:8501**. Dừng ứng dụng bằng `Ctrl+C` trong terminal.

## Deploy miễn phí lên Streamlit Community Cloud

1. Đăng nhập hoặc tạo tài khoản tại [share.streamlit.io](https://share.streamlit.io/) bằng GitHub.
2. Bấm **Create app** → **Use existing repo**.
3. Chọn repository `tueanh310510-ux/game-python-app`, branch `main`, và main file path `app.py`.
4. Bấm **Deploy**. Nếu repository chưa xuất hiện, cấp quyền cho Streamlit Community Cloud truy cập repository trong phần GitHub permissions.

`requirements.txt` đã có sẵn ở thư mục gốc của repository, nên Cloud sẽ cài dependencies tự động. App vẫn chạy nếu không có model MediaPipe: Football, Basketball và Tic Tac Toe hoạt động; Rock Paper Scissors và Red Light Green Light cần model tương ứng. Trong app đã có tải clip mẫu, không cần chạy `generate_samples.py` trên Cloud.

Lưu ý: Community Cloud có tài nguyên và thời gian xử lý giới hạn. Phân tích video dài hoặc nặng có thể vượt giới hạn; bảng điểm chỉ tồn tại trong phiên và sẽ mất khi phiên bị khởi động lại. Không tải lên video riêng tư vì nội dung được gửi đến máy chủ để xử lý.

## Cài trên máy khác

Khuyến nghị Python **3.11**. Code yêu cầu Python 3.10 trở lên.

```bash
python3.11 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python download_models.py
python generate_samples.py
streamlit run app.py
```

Windows: kích hoạt bằng `.venv\Scripts\activate`. Hai model bàn tay và tư thế
được tải từ kho MediaPipe chính thức; sau đó phân tích video không cần mạng.
Nếu không tải model, bóng đá, bóng rổ và cờ caro vẫn hoạt động.

## Cách sử dụng

1. Chọn một trong năm trò chơi.
2. Đặt tên P1–P4: P1/P2 thuộc A, P3/P4 thuộc B. Sau khi lưu vòng đầu, danh sách
   được giữ nguyên trong giải để điểm từng người không bị chuyển nhầm.
3. Đặt người đại diện, thời gian (10–600 giây), điểm mỗi lượt (1–10) và luật riêng.
4. Bấm **Bắt đầu vòng**. Cờ caro chơi ngay trên màn hình. Các trò vận động quay
   bằng điện thoại/webcam bên ngoài, giữ camera cố định. Có clip sẵn thì chọn
   **Tôi đã có video**.
5. Tải video, căn vạch/vùng trong ảnh xem trước, bấm **Phân tích video**, kiểm tra
   sự kiện và **Xác nhận & ghi vào bảng điểm**. Kết quả cờ caro trên màn hình đi
   thẳng đến bước xác nhận.
6. Xem tổng điểm, MVP và tải JSON. Tạo vòng mới để đổi trò hoặc đổi người đại diện.
   Hòa giữ nguyên điểm; có thể chơi vòng phụ.

### Quy tắc và cách quay từng trò

| Trò | Cách chơi / đầu vào | Cách chấm |
| --- | --- | --- |
| Football | Thi sút lần lượt, **một người mỗi clip**; chọn đội và màu bóng. Đặt vạch trùng mặt phẳng cầu môn nhìn từ bên hông. | Bóng màu tròn vượt đoạn vạch theo hướng chỉ định; chống đếm lặp 1,5 giây. Mỗi lần cộng số điểm đã đặt. |
| Tic Tac Toe | A = X, B = O; X đi trước. Bấm các ô trên màn hình, hoặc quay bàn trắng nét đen 3×3 từ trên xuống. | Kiểm tra trạng thái hợp lệ, hàng ngang/dọc/chéo và hòa; video cần giữ bàn cờ kết thúc ổn định ≥1 giây. |
| Rock Paper Scissors | Một tay mỗi người, A ở trái ảnh, B ở phải. Giữ rõ cử chỉ ≥0,55 giây; cả hai rút tay ≥0,4 giây giữa các lượt. | MediaPipe Hand Landmarker → trạng thái ngón → luật kéo/búa/bao. Hòa không cộng điểm. |
| Red Light Green Light | A ở trái, B ở phải; nhìn rõ vai, tay, hông, chân. Người chơi nhìn đèn trên app. Video bắt đầu đồng thời với đồng hồ. | MediaPipe Pose Landmarker; so với tư thế đầu pha đỏ sau thời gian phản ứng. Mỗi pha đỏ hoàn chỉnh đứng yên cộng điểm; di chuyển nhận 0 điểm pha đó. |
| Basketball | Thi ném lần lượt, **một người mỗi clip**, quay cố định từ bên; căn đoạn vạch trùng vành rổ. | Bóng màu đi xuống qua đoạn vành rổ, chống đếm lặp; mặc định 2 điểm/lần. |

Các tọa độ vùng chấm dùng tỷ lệ 0–1 của ảnh. Không đảo gương hoặc đổi vị trí
hai người giữa video. Mặc định bóng màu cam. Tránh nền/áo cùng màu bóng; trắng
dễ nhầm với nền và đường kẻ. Cần nhìn thấy bóng liên tục ở hai phía vạch.

Đèn đỏ/đèn xanh mặc định chu kỳ xanh 4 giây, đỏ 3 giây, phản ứng 0,5 giây.
Nếu video bắt đầu ở giây thứ 2 của đồng hồ, nhập độ lệch `2`. Nếu quay trước khi
đồng hồ chạy, cắt phần đầu video để đồng bộ. Chỉ pha đỏ đủ thời gian quan sát
(≥70% khoảng sau thời gian phản ứng) mới có điểm đứng yên. Pha cuối chưa kết thúc
không có điểm. Di chuyển chậm vẫn bị phát hiện do so với tư thế mốc của pha.

### MVP và tổng điểm

MVP xét điểm trước, sau đó thời gian quan sát. Với bóng đá/bóng rổ, thời gian
quan sát là thời gian thấy bóng của **người được gán clip**; không phải nhận diện
danh tính hay đo quyền kiểm soát bóng. Kéo búa bao và đèn đỏ/đèn xanh gán người
theo nửa ảnh. Cờ caro xét người thắng. Đồng chỉ số thì đồng MVP; không có bằng
chứng thì không gán MVP.

Mỗi vòng và mỗi nội dung video chỉ được ghi điểm một lần trong phiên, kể cả khi
đổi cấu hình. Video mô phỏng có nhãn riêng và không cộng vào giải qua chế độ demo.
Bảng điểm lưu trong **phiên Streamlit**, không có cơ sở dữ liệu; tải JSON trước
khi tải lại trang hoặc tắt server. Mục kiểm tra JSON xác minh báo cáo, không nhập
báo cáo vào giải đang chơi.

## Kiểm thử

```bash
.venv/bin/python -m unittest discover -s tests -v
```

Bộ kiểm thử gồm toàn bộ 19.683 trạng thái bàn cờ (đối chiếu 5.478 trạng thái
có thể đạt được), luật kéo/búa/bao, điều kiện vượt vạch, chống đếm lặp, phát hiện
dịch chuyển chậm khi đèn đỏ, SHA-256, video sai, video mô phỏng có điểm biết trước
và luồng Streamlit chọn trò → chơi → xác nhận → bảng điểm → vòng mới.

`generate_samples.py` tạo ba clip hình học, không chứa người thật:

- `samples/football_demo.mp4`: 2 lần qua cầu môn với cấu hình mặc định.
- `samples/basketball_demo.mp4`: 2 lần qua vành rổ, được 4 điểm nếu đặt 2 điểm/lần.
- `samples/tic_tac_toe_demo.mp4`: X thắng hàng trên, 1 điểm với cấu hình mặc định.

## API và các file

```python
from ai_judge import JudgeConfig, process_game_video, verify_results_hash

report = process_game_video(
    "match.mp4", "football",
    JudgeConfig(active_team="A", active_player="P1", ball_color="orange"),
)
assert verify_results_hash(report)
```

`process_game_video(video_path, game_type)` vẫn dùng được với đúng hai tham số
như tài liệu ban đầu. Tùy chọn thứ ba `JudgeConfig` đặt luật/vùng; tùy chọn thứ tư
là callback tiến trình. Tên game: `football`, `tic_tac_toe`, `rock_paper_scissors`,
`red_light_green_light`, `basketball`.

- `app.py`: toàn bộ UI Streamlit, đồng hồ, luồng 6 bước, quản lý phiên và tải báo cáo.
- `ai_judge.py`: bộ luật, OpenCV/MediaPipe, sự kiện, điểm, MVP và SHA-256.
- `download_models.py`: tải model chính thức vào `models/`.
- `generate_samples.py`: tạo video kiểm thử có thể tái tạo.
- `tests/`: kiểm thử luật, video và ứng dụng.
- `.streamlit/config.toml`: giao diện, giới hạn tải 150 MB, tắt thống kê sử dụng.

## Phạm vi của bản triển khai

Đây là bản prototype thi đấu gia đình với camera cố định và vùng được căn chỉnh.
Bóng đá/bóng rổ dùng OpenCV theo màu và đường đi trong ảnh 2D; sự kiện là **ước
lượng cần xem lại**, chưa chứng minh bóng qua cầu môn/rổ trong không gian 3D.
Không tự phân biệt cú ném 2/3 điểm, không đọc bảng điểm TV, không xử lý phát lại,
không chấm trận nhiều người chung một sân, không xử lý âm thanh. MediaPipe có
thể bỏ sót khi thiếu sáng, che tay/chân, nhiều người cùng làn hoặc máy quay rung.
Video biến thiên FPS nên được chuyển sang FPS cố định để đồng hồ chính xác.

Tài liệu và `football_prototype.py` đã được đọc để giữ nguyên nguyên tắc theo
dõi thời gian, chặn quan sát gián đoạn và không biến một ước lượng thành sự kiện
chắc chắn. Bản này dùng video tải lên và bóng có màu để cài đặt gọn hơn; không
tích hợp quay màn hình MSS hoặc tải model YOLO của prototype.

SHA-256 tính trên JSON UTF-8, sắp xếp khóa, không khoảng trắng, bỏ trường `hash`.
Nó phát hiện nội dung không khớp mã đi kèm; **không phải chữ ký số hay bằng chứng
chống gian lận**. Ai sửa nội dung và tính lại hash vẫn có thể tạo báo cáo hợp lệ.
Giữ một bản hash đáng tin độc lập nếu muốn so sánh báo cáo sau này.

Tài liệu API tham khảo: [MediaPipe Hand Landmarker](https://ai.google.dev/edge/mediapipe/solutions/vision/hand_landmarker/python),
[Pose Landmarker](https://ai.google.dev/edge/mediapipe/solutions/vision/pose_landmarker/python),
[Streamlit fragments](https://docs.streamlit.io/develop/api-reference/execution-flow/st.fragment),
[Streamlit AppTest](https://docs.streamlit.io/develop/api-reference/app-testing/st.testing.v1.apptest).
