"""CHECK 2 — Dòng nhãn YOLO: sai định dạng, ID lớp lạ, box tràn ảnh, box rỗng, box lặp.   (Script 2 trong slide)   ★★

Test:  pytest tests/test_label_format.py -q

Mỗi dòng nhãn: `id cx cy w h` (5 số, toạ độ 0–1). Trả về list[Issue]; `Issue.line` = số dòng (đếm từ 1).

| code             | severity | khi nào                                                                  |
|------------------|----------|--------------------------------------------------------------------------|
| BAD_FORMAT       | ERROR    | không đúng 5 cột số (dùng `parse_yolo_line`, bắt `ValueError`)           |
| BAD_CLASS_ID     | ERROR    | id lớp ngoài 0..len(ds.classes)-1                                        |
| BOX_ZERO         | ERROR    | w <= 0 hoặc h <= 0                                                       |
| BOX_OUT_OF_IMAGE | ERROR    | mép box vượt [0,1] quá `cfg["label_format"]["overflow_tol"]`; extra={"overflow": mức tràn} |
| DUP_BOX          | ERROR    | cùng lớp với một dòng TRƯỚC ĐÓ và IoU > `dup_box_iou`; báo ở dòng SAU    |
| BOX_TINY         | WARN     | cạnh ngắn của box (px) < `min_box_px`  (cần `ds.image_size(stem)`)       |
| BOX_HUGE         | WARN     | w*h > `max_box_frac`                                                     |

Gợi ý
- Mép trái = x - w/2, mép phải = x + w/2 (xem câu hỏi "dòng YOLO nào lỗi?" trong slide).
- Một dòng hỏng (BAD_FORMAT, BAD_CLASS_ID, BOX_ZERO) thì `continue`, đừng kiểm tiếp hình học của dòng đó.
- Dòng thiếu cột làm script của slide dừng giữa chừng: đây là lý do phải `try/except`.
- `iou_xywh(a, b)` có sẵn trong common.py.
- Ngưỡng nằm trong `cfg["label_format"]` — đừng viết cứng số vào code.
"""
from ..common import ERROR, WARN, Issue, iou_xywh, parse_yolo_line  # noqa: F401


def run(ds, cfg):
    # --- Bước 1: đọc ngưỡng + hàm phụ
    lf = cfg["label_format"]
    tol, min_px = lf["overflow_tol"], lf["min_box_px"]
    max_frac, dup_iou = lf["max_box_frac"], lf["dup_box_iou"]
    n_cls = len(ds.classes)
    issues = []

    def add(sev, code, stem, msg, line, extra=None):
        issues.append(Issue("label_format", sev, code, stem, msg, line=line, extra=extra or {}))

    # --- Bước 2: duyệt từng file, từng dòng
    for lab in ds.label_files():
        stem = lab.stem
        size = ds.image_size(stem)
        seen = []
        for ln_no, text in ds.read_label_lines(stem) or []:
            # --- Bước 3: dòng hỏng -> báo rồi continue
            try:
                c, x, y, w, h = parse_yolo_line(text)
            except ValueError as e:
                add(ERROR, "BAD_FORMAT", stem, f"sai định dạng: {e}", ln_no)
                continue
            if not 0 <= c < n_cls:
                add(ERROR, "BAD_CLASS_ID", stem, f"id lớp {c} ngoài 0..{n_cls - 1}", ln_no)
                continue
            if w <= 0 or h <= 0:
                add(ERROR, "BOX_ZERO", stem, f"box rỗng w={w} h={h}", ln_no)
                continue

            # --- Bước 4: box tràn ảnh
            overflow = max(0.0, -(x - w / 2), (x + w / 2) - 1, -(y - h / 2), (y + h / 2) - 1)
            if overflow > tol:
                add(ERROR, "BOX_OUT_OF_IMAGE", stem, f"box tràn ảnh {overflow:.4f}", ln_no,
                    {"overflow": round(overflow, 6)})

            # --- Bước 5: box trùng với dòng trước
            box = (x, y, w, h)
            for pc, pbox in seen:
                if pc == c and iou_xywh(box, pbox) > dup_iou:
                    add(ERROR, "DUP_BOX", stem, "box trùng với một dòng trước", ln_no)
                    break
            seen.append((c, box))

            # --- Bước 6: cảnh báo box nhỏ / to
            if size:
                short = min(w * size[0], h * size[1])
                if short < min_px:
                    add(WARN, "BOX_TINY", stem, f"cạnh ngắn {short:.1f}px < {min_px}px", ln_no)
            if w * h > max_frac:
                add(WARN, "BOX_HUGE", stem, f"box chiếm {w * h:.2f} ảnh", ln_no)

    return issues
