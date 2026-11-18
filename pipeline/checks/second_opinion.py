"""CHECK 6 — Ý kiến thứ hai: so nhãn với một model LỚN HƠN (yolo26l).   ★★★ (khó nhất, đáng điểm nhất)

Test:  pytest tests/test_second_opinion.py -q

Máy kiểm quy tắc, người kiểm ý nghĩa (slide). Các lỗi như thiếu nhãn / gán nhầm lớp hợp lệ / box lỏng
KHÔNG bắt được bằng quy tắc cú pháp. Ta nhờ một model mạnh hơn "nhìn lại" và CHỈ CẢNH BÁO (model cũng có thể sai):
những ảnh bị cờ sẽ vào hàng đợi cho NGƯỜI duyệt.

`preds[stem]` = list `[id_lớp, conf, cx, cy, w, h]` của model (lấy qua `get_preds(ds, cfg, "checker")` nếu preds=None).
`L = ds.valid_boxes(stem)` = list `(id_lớp, cx, cy, w, h)` của nhãn (đã bỏ dòng hỏng).
Ngưỡng ở `cfg["second_opinion"]`: conf, min_area_px, fp_conf, iou_missing, iou_match, iou_loose.

Thuật toán gợi ý, với từng ảnh (bỏ qua ảnh không có trong preds hoặc không có file nhãn):
  P = dự đoán có conf >= conf  VÀ diện tích px (w*W * h*H) >= min_area_px
  Với mỗi dự đoán r trong P: lấy các nhãn có IoU(r, nhãn) >= iou_missing  (cands)
   - không có cands                            -> POSSIBLE_MISSING     (model thấy vật mà nhãn không có box)
   - có cands cùng lớp, tốt nhất IoU < iou_loose -> POSSIBLE_LOOSE_BOX  (đúng vật, box lỏng/lệch)
   - không có cands cùng lớp, nhưng cands tốt nhất IoU >= iou_match (khác lớp) -> POSSIBLE_WRONG_CLASS
  Với mỗi dòng nhãn hợp lệ: nếu IoU với MỌI dự đoán (conf >= fp_conf, không lọc diện tích) đều < iou_missing
                                             -> POSSIBLE_FALSE_POS  (box nhãn không khớp vật nào model thấy; Issue.line = số dòng)

Chi tiết các ca biên (test kiểm đúng các ca này)
- `cands` gồm nhãn MỌI lớp có IoU >= iou_missing; "tốt nhất cùng lớp" = cands cùng lớp có IoU lớn nhất; "tốt nhất khác lớp" tương tự với cands khác lớp.
- Thứ tự quyết định cho mỗi dự đoán: (1) cands rỗng -> MISSING. (2) có cands cùng lớp: IoU tốt nhất < iou_loose -> LOOSE_BOX, ngược lại KHÔNG cờ
  (nhãn đúng lớp đã phủ vật này, kể cả khi còn nhãn khác lớp chồng lên). (3) không có cands cùng lớp: nếu IoU tốt nhất khác lớp >= iou_match -> WRONG_CLASS;
  nếu chỉ có khác lớp với IoU trong [iou_missing, iou_match) -> không cờ gì (mơ hồ: để cho FALSE_POS / lần duyệt khác).
- Một dự đoán sinh tối đa MỘT issue (MISSING / LOOSE_BOX / WRONG_CLASS); một ảnh có thể có nhiều issue.
- Thứ tự issue: theo `ds.image_files()` rồi theo thứ tự dự đoán trong `preds[stem]`, cuối cùng là các FALSE_POS theo số dòng; `Issue.image` = stem, `Issue.line` chỉ đặt cho FALSE_POS.

Lưu ý số dòng: dùng `ds.read_label_lines(stem)` (giữ số dòng gốc, kể cả dòng hỏng/trống) để lấy `Issue.line`; `valid_boxes` KHÔNG giữ số dòng.

Tất cả severity WARN; `Issue.extra` nên có {"conf": ...} hoặc {"iou": ...} (hàng đợi duyệt dùng conf để xếp ưu tiên).

Gợi ý
- `iou_xywh` có sẵn. Dòng nhãn hỏng không được làm script chết (dùng `ds.valid_boxes` và `parse_yolo_line` trong try).
- Kết quả phụ thuộc mạnh vào ngưỡng: calibrate chúng ở Bước 3 thay vì đoán.
"""
from ..common import WARN, Issue, iou_xywh, parse_yolo_line  # noqa: F401
from ..model_cache import get_preds  # noqa: F401


def _valid_lines(ds, stem):
    """[(số dòng gốc, (id, cx, cy, w, h))] của các dòng nhãn hợp lệ (bỏ dòng hỏng / id lạ)."""
    out = []
    for ln_no, text in ds.read_label_lines(stem) or []:
        try:
            b = parse_yolo_line(text)
        except ValueError:
            continue
        if 0 <= b[0] < len(ds.classes):
            out.append((ln_no, b))
    return out


def run(ds, cfg, preds=None):
    # --- Bước 1: ngưỡng + dự đoán
    so = cfg["second_opinion"]
    conf, min_area, fp_conf = so["conf"], so["min_area_px"], so["fp_conf"]
    iou_missing, iou_match, iou_loose = so["iou_missing"], so["iou_match"], so["iou_loose"]
    if preds is None:
        preds = get_preds(ds, cfg, "checker")

    issues = []

    def add(code, stem, msg, line=None, extra=None):
        issues.append(Issue("second_opinion", WARN, code, stem, msg, line=line, extra=extra or {}))

    for img in ds.image_files():
        stem = img.stem
        # --- Bước 2: bỏ qua ảnh không có dự đoán hoặc không có file nhãn
        if stem not in preds or not ds.label_path(stem).exists():
            continue
        size = ds.image_size(stem)
        if size is None:                       # ảnh hỏng: check `images` đã báo
            continue
        W, H = size
        labels = _valid_lines(ds, stem)        # [(số dòng, (id, cx, cy, w, h))]

        # --- Bước 3: mỗi dự đoán đủ tin cậy + đủ lớn -> so với nhãn
        for p in preds[stem]:
            pc, pconf, pbox = int(p[0]), p[1], tuple(p[2:6])
            if pconf < conf or pbox[2] * W * pbox[3] * H < min_area:
                continue
            cands = []                         # (iou, lớp nhãn) có IoU >= iou_missing
            for _, (lc, *lbox) in labels:
                iou = iou_xywh(pbox, lbox)
                if iou >= iou_missing:
                    cands.append((iou, lc))
            same = [iou for iou, lc in cands if lc == pc]
            other = [iou for iou, lc in cands if lc != pc]

            if not cands:                                          # (1) không nhãn nào phủ vật
                add("POSSIBLE_MISSING", stem, f"model thấy {ds.classes[pc]} (conf {pconf:.2f}) mà nhãn không có box",
                    extra={"conf": pconf})
            elif same:                                             # (2) có nhãn cùng lớp
                if max(same) < iou_loose:
                    add("POSSIBLE_LOOSE_BOX", stem, f"box {ds.classes[pc]} lệch/lỏng (IoU {max(same):.2f})",
                        extra={"conf": pconf, "iou": round(max(same), 4)})
            elif max(other) >= iou_match:                          # (3) chỉ có nhãn khác lớp, khớp rõ
                add("POSSIBLE_WRONG_CLASS", stem, f"model nói {ds.classes[pc]} (conf {pconf:.2f}) nhưng nhãn khác lớp",
                    extra={"conf": pconf, "iou": round(max(other), 4)})
            # còn lại: khác lớp, IoU trong [iou_missing, iou_match) -> mơ hồ, không cờ

        # --- Bước 4: mỗi dòng nhãn không khớp dự đoán nào -> có thể là box thừa
        fp_preds = [tuple(p[2:6]) for p in preds[stem] if p[1] >= fp_conf]   # KHÔNG lọc diện tích
        for ln_no, (lc, *lbox) in labels:
            best = max((iou_xywh(lbox, pb) for pb in fp_preds), default=0.0)
            if best < iou_missing:
                add("POSSIBLE_FALSE_POS", stem, f"box {ds.classes[lc]} không khớp vật nào model thấy (IoU tốt nhất {best:.2f})",
                    line=ln_no, extra={"iou": round(best, 4)})

    return issues
