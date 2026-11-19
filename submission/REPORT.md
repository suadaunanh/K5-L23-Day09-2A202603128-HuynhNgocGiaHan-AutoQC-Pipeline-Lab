# Báo cáo Day 09 — Huỳnh Ngọc Gia Hân, 2A202603128

## 1. Kết luận trước

Pipeline kết luận **Hold** (mã thoát 10). Vào **224** ảnh, nhận **202** ảnh (loại 22 ở cửa vào), xuất **202** ảnh vào `export/clean_v1` dưới dạng **bản nháp, chưa phát hành**.
Lý do: sau sửa tự động và người duyệt (80/80 ảnh ngân sách) **không còn lỗi bắt buộc** (0), nhưng **38/202 ảnh (18,8%)** vẫn còn cảnh báo chưa được người xem, ≥ ngưỡng 10% (`08_summary.json`).

## 2. Lỗi và phân việc

Từ `02_error_list_v1` (QC vòng 1, 202 ảnh) và `01_intake` (224 ảnh):

| Mã lỗi                                       |          Số ảnh/dòng | Ai sửa (máy/người)              | Vì sao                                                                 |
| ---------------------------------------------- | ----------------------: | ----------------------------------- | ----------------------------------------------------------------------- |
| CORRUPT_IMAGE / BAD_SIZE                       |              2 / 3 ảnh | máy (loại ở cửa vào)           | ảnh không mở được / cạnh ngắn < 250 px: quy tắc rõ ràng      |
| DUP_IMAGE_EXACT / DUP_IMAGE_NEAR               |              8 / 4 ảnh | máy (loại)                        | md5 trùng / phash ≤ 10: giữ ảnh đầu, bỏ bản sao                 |
| LEAK_TEST                                      |                  5 ảnh | máy (loại)                        | trùng ảnh tập test: để lại sẽ làm mAP ảo                       |
| BAD_FORMAT / BAD_CLASS_ID / BOX_ZERO / DUP_BOX |     3 / 6 / 4 / 7 dòng | máy (`drop_line`)                | dòng hỏng cú pháp, không thể đoán ý người gán → xoá dòng |
| BOX_OUT_OF_IMAGE                               |                 8 dòng | người (`clip_box`)              | chỉ là tràn mép, giữ nguyên lớp, cắt về [0,1]                  |
| BAD_CLASS_NAME                                 |  1 file (`data.yaml`) | người (`rename_classes`)        | tên lớp sai chữ hoa/thường so với guideline                       |
| MISSING_LABEL_FILE                             |                  6 ảnh | **người** (`needs_label`) | máy không được bịa nhãn; file rỗng ≠ "chưa gán"              |
| POSSIBLE_MISSING                               | 53 cảnh báo / 52 ảnh | **người**                   | lỗi ngữ nghĩa, model lớn chỉ gợi ý (có thể sai)                |
| POSSIBLE_FALSE_POS                             |            29 / 27 ảnh | **người**                   | như trên                                                              |
| POSSIBLE_LOOSE_BOX                             |            28 / 24 ảnh | **người**                   | như trên                                                              |
| POSSIBLE_WRONG_CLASS                           |            18 / 18 ảnh | **người**                   | như trên (car/truck/bus dễ nhầm)                                    |
| EMPTY_LABEL, BOX_TINY, BOX_HUGE, CLASS_RARE    |     12 / 4 / 3 / 1 ảnh | **người**                   | cảnh báo quy tắc, cần mắt người quyết định                    |

Mình tự sửa **35** thay đổi (`03_fixes.csv`: 20 drop_line, 8 clip_box, 6 needs_label, 1 rename_classes).

**Hàng đợi** (`05_review_queue.csv`, 125 ảnh): xếp theo tổng trọng số `review.weights`. Đầu hàng là img_0020 (11,5: vừa bị máy xoá dòng, vừa MISSING + WRONG_CLASS), tiếp theo là 6 ảnh `NEEDS_LABEL` (trọng số 10: chưa có nhãn thì không thể phát hành). Sau đó là các ảnh có nhiều cờ WRONG_CLASS/MISSING (trọng số 3 và 2). Với ngân sách 80 ảnh, người xem được **74/103** ảnh có cảnh báo ngữ nghĩa (`POSSIBLE_*`). Từ v2 → v3: MISSING 53→13, WRONG_CLASS 18→3, LOOSE_BOX 28→20, FALSE_POS 24→21.

## 3. Calibration (2 ngưỡng)

| Tham số                  | Khởi đầu | Đã chọn    | Precision / Recall (trước → sau)                                                                                                                         | Lý do (đánh đổi)                                                                                                                                                           |
| ------------------------- | ----------- | ------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `duplicates.phash_dist` | 2           | **10**  | DUP_IMAGE_NEAR: 1,00/0,50 → 1,00/0,67 (EXACT giữ 1,00/1,00)                                                                                               | 4–14 cho cùng F1 0,80 trên calib; chọn 10 vì trên raw nó bắt thêm cặp trùng thật img_0186≈img_0061 (dist 10) mà chưa gộp nhầm ảnh khác                       |
| `second_opinion.conf`   | 0,25        | **0,6** | MISSING 0,50/1,00 → 0,57/1,00; WRONG_CLASS 0,56/0,83 → 0,62/0,83; LOOSE_BOX 0,29/0,40 → 0,20/0,20; FALSE_POS không đổi (dùng `fp_conf` cố định) | F1 MISSING cao nhất (0,73) mà **vẫn giữ recall 1,00**; giảm báo động giả cho hàng đợi. Đánh đổi: LOOSE_BOX tệ đi (chỉ 5 ca chèn nên số nhảy mạnh) |

**Chỗ calibration đánh lừa:**

- *phash_dist*: trên calib, F1 cao nhất là **16** (0,91). Nhưng trên raw, 16 làm LEAK_TEST tăng 5 → 11 và NEAR 4 → 7. Mở ảnh ra xem thì là gộp nhầm: img_0017 (người trong văn phòng) bị coi là trùng test_071 (cưỡi ngựa), img_0177 (lướt sóng) bị coi là trùng img_0113 (người ngồi bàn). Ở 20, LEAK_TEST lên tới 105. Calib không có ca LEAK_TEST nào nên không phạt được lỗi này.
- *conf*: 0,8 có F1 trung bình cao nhất trên calib (WRONG_CLASS 0,91) và **làm pipeline ra Release** (16/202 = 7,9%). Mình không chọn vì: recall MISSING giảm còn 0,75; F1 0,91 chỉ dựa trên 6 ca chèn, mà WRONG_CLASS trong calib chủ yếu là person→car còn raw nghiêng về car/truck/bus; và 0,8 nằm ở đầu mút dải sweep. Chọn nó sẽ là "Release giả" do checker mù.

## 4. Cửa chặn và điều pipeline KHÔNG bắt được

**(a) Gate chặn đúng:** `python -m pipeline.run --budget 0 --reports work/rep_nb --export-dir work/exp_nb` → kết luận **REWORK — còn 6 lỗi bắt buộc** (6 ảnh `MISSING_LABEL_FILE` không ai gán), **mã thoát 20**, log in "KHÔNG xuất: còn lỗi bắt buộc (Rework)" và thư mục `work/exp_nb` **không được tạo**.

**(b) Điểm mù có bằng chứng** (mình tự xem `viz_labels.py` trước khi chạy pipeline, ghi 4 ảnh lỗi; pipeline bắt được img_0001, img_0030, bỏ sót 2 ảnh):

1. **Model lớn nhầm giống người gán — img_0002:** dòng 2 là box `person` (0,80; 0,65) nhưng không phải người. yolo26l cũng dự đoán `person` ở đúng chỗ đó (conf 0,37 ≥ `fp_conf` 0,1) nên POSSIBLE_FALSE_POS không bật. Ý kiến thứ hai không giúp khi hai bên cùng sai.
2. **Vật nhỏ dưới `min_area_px` — img_0007:** thiếu vài box xe ở xa. Model có thấy (vd. car conf 0,85 tại (0,833; 0,83), conf 0,65 tại (0,845; 0,80)) nhưng diện tích ≈ 470 px² và 370 px² < 600 px² nên bị lọc; một xe khác conf 0,48 < `conf` 0,6. POSSIBLE_MISSING không bật.
3. **Ảnh trùng biến đổi mạnh:** trên calib, DUP_IMAGE_NEAR recall chỉ 0,67 ở phash 10 (bỏ sót 2/6 bản sao chèn); muốn bắt hết phải nâng phash lên mức gộp nhầm ảnh khác (xem §3).

## 5. Train: raw vs clean (tùy chọn, chấm riêng)

Train **cục bộ trên Apple M5 (`mps`)** bằng `make train` (không dùng Colab T4): yolo26n, 20 epoch, 2 seed (0, 1), imgsz 640, đo trên test 100 ảnh. `clean` là bản nháp từ kết luận Hold.

| biến thể | #ảnh train | số seed | map50 (TB ± độ lệch) | map50_95 (TB ± độ lệch) | precision (TB ± độ lệch) | recall (TB ± độ lệch) |
| ---------- | ----------- | -------- | ------------------------ | --------------------------- | ---------------------------- | ------------------------- |
| raw        | 224         | 2        | 0.712 ± 0.018           | 0.511 ± 0.021              | 0.675 ± 0.039               | 0.678 ± 0.027            |
| clean      | 202         | 2        | 0.710 ± 0.004           | 0.500 ± 0.004              | 0.730 ± 0.002               | 0.620 ± 0.025            |

**Kết luận: chưa kết luận được clean tốt hơn raw.** Chênh mAP50 (clean − raw) = **−0,002**, nhỏ hơn nhiều so với độ lệch giữa các seed của raw (±0,018; hai seed raw cách nhau 0,025: 0,699 vs 0,725). mAP50-95 cũng nằm trong nhiễu (−0,011 vs ±0,021). Điểm khác rõ hơn nhiễu: clean có precision cao hơn (0,730 vs 0,675) nhưng recall thấp hơn (0,620 vs 0,678); chỉ 2 seed nên cũng chưa chắc.

Giả thuyết và cách kiểm:

1. **Rò rỉ test làm raw được điểm ảo:** raw còn 5 ảnh LEAK_TEST (trùng test_009/033/039/044/085) và 12 ảnh trùng. Kiểm: đo lại trên test **bỏ 5 ảnh bị rò rỉ** và so raw vs clean.
2. **Nhãn trong clean chưa sạch hết:** 38/202 ảnh còn cảnh báo (13 MISSING, 20 LOOSE_BOX, 21 FALSE_POS) và 4 ảnh EMPTY_LABEL; box thiếu có thể là lý do recall clean thấp hơn. Kiểm: duyệt hết hàng đợi (hoặc chạy thêm biến thể `oracle`) rồi train lại.
3. **Mẫu nhỏ:** clean ít hơn raw 22 ảnh, test chỉ 100 ảnh, chỉ 2 seed × 20 epoch. Kiểm: chạy 3+ seed, 40 epoch như gợi ý trong `train_compare.py`.

## 6. Quyết định và ghi chú AI

**(a) Quyết định cuối: Hold.** Không có lỗi bắt buộc, nhưng 38/202 ảnh còn cảnh báo. Để thành Release: (1) tăng ngân sách duyệt thêm ≥ 18 ảnh trong số 45 ảnh còn lại của hàng đợi (để còn < 20/202 = 10%), ưu tiên 13 ảnh POSSIBLE_MISSING và 3 ảnh WRONG_CLASS; hoặc (2) cải thiện checker để giảm báo động giả (FALSE_POS precision chỉ 0,31 trên calib), **không** nâng `conf` chỉ để hàng đợi nhỏ lại.

**(b) Dùng AI (trợ lý AI trong VS Code):**

- Prompt chính: "hướng dẫn viết label_format.py / gate.py / autofix.py / second_opinion.py" theo docstring của từng stub; sau đó mình xem lại logic code. Rồi mới cho phép chỉnh sửa.`gate.py` mình **tự viết lại** từ stub theo gợi ý dạng câu hỏi (sau khi đã xem bản AI viết trước đó), 10/10 test xanh; sau đó nhờ chạy lênh test và rà lại, AI sửa 2 lỗi mà test không bắt được: so ngưỡng bằng tỉ lệ đã làm tròn
- Cách kiểm: chạy `pytest` (79/79 xanh), chạy từng check trên `data/raw` xem số lỗi mỗi mã có hợp lý không, đối chiếu với 4 ảnh mình tự xem bằng `viz_labels.py`, và mở ảnh các cặp bị cho là trùng khi calibrate.
- AI sai: AI đưa lệnh terminal có chú thích `# ...` ở cuối dòng; zsh trên macOS không coi `#` là chú thích nên `pytest` báo "file not found: #" và `viz_labels.py` coi các chữ trong chú thích là tên ảnh. Sửa bằng cách chạy lệnh không kèm chú thích.
- Claude giúp hỗ trợ chỉnh sửa cú pháp và chỉnh sửa lai câu từ trong báo cáo cho dễ hiểu hơn.
