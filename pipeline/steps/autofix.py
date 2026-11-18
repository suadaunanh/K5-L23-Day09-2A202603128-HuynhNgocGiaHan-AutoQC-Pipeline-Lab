"""BƯỚC 2/4 — Sửa tự động những lỗi bắt buộc mà máy sửa được AN TOÀN.   ★★

Test:  pytest tests/test_autofix.py -q

`fix(ds, issues, cfg) -> list[dict]`: duyệt `issues` (chỉ lỗi severity ERROR), sửa thẳng vào thư mục `ds`,
và trả về danh sách thay đổi; mỗi phần tử có khoá: image, line, action, before, after
(đây chính là file `03_fixes.csv` — bằng chứng pipeline đã làm gì, người có thể kiểm lại).

| code lỗi                                       | cách sửa                                    | action           |
|------------------------------------------------|---------------------------------------------|------------------|
| BAD_FORMAT, BAD_CLASS_ID, BOX_ZERO, DUP_BOX    | xoá dòng đó khỏi file nhãn                  | "drop_line"      |
| BOX_OUT_OF_IMAGE                               | cắt box về trong [0,1] (giữ nguyên lớp)     | "clip_box"       |
| MISSING_LABEL_FILE                             | KHÔNG sửa file (máy không thể bịa nhãn): ghi 1 dòng fix, before="(không có file)", after="chuyển người gán" | "needs_label" |
| BAD_CLASS_NAME                                 | ghi lại `names` trong data.yaml đúng `cfg["classes"]` | "rename_classes" |
| DUP_IMAGE_*, LEAK_TEST, CORRUPT_IMAGE, BAD_SIZE| xoá ảnh + nhãn khỏi `ds`                    | "remove_image"   |

Bẫy cần nghĩ tới (có test cho từng cái)
- Một file có NHIỀU dòng lỗi: số dòng trong `issues` là số dòng GỐC. Nếu xoá từng dòng một thì số dòng lệch.
  Gom theo file, rồi ghi lại MỘT lần.
- Sau khi cắt, box có thể không còn diện tích (nằm hẳn ngoài ảnh): lúc đó xoá dòng thay vì ghi box rỗng.
- Một dòng có 2 lỗi (vd. BOX_OUT_OF_IMAGE + DUP_BOX): xoá dòng thắng, chỉ ghi 1 fix `drop_line`, không ghi thêm `clip_box`. Dòng trống ở giữa file vẫn đếm vào số dòng gốc.
- Ảnh vừa bị xoá (DUP_IMAGE_*...) mà còn issue dòng của chính nó: bỏ qua êm, không được báo lỗi/chết.
- Không động tới lỗi WARN (cảnh báo là việc của người). Không sửa file ở `data/raw/` — chỉ sửa `ds`.
- Chạy lần 2 trên dữ liệu đã sửa phải không làm gì thêm (idempotent) — NGOẠI LỆ duy nhất: `needs_label` được ghi lại mỗi lần còn lỗi `MISSING_LABEL_FILE` (vì ảnh vẫn chưa có nhãn).

- `needs_label` KHÔNG tạo file nhãn rỗng (rỗng = "ảnh nền", khác với "chưa gán"). `review_queue` sẽ đẩy ảnh này lên đầu hàng đợi cho người.

Gợi ý: `yaml.safe_load / safe_dump`.
"""
from collections import defaultdict  # noqa: F401

import yaml  # noqa: F401

from ..common import ERROR, parse_yolo_line  # noqa: F401


DROP_CODES = {"BAD_FORMAT", "BAD_CLASS_ID", "BOX_ZERO", "DUP_BOX"}
REMOVE_CODES = {"LEAK_TEST", "CORRUPT_IMAGE", "BAD_SIZE"}


def _is_remove(code):
    return code in REMOVE_CODES or code.startswith("DUP_IMAGE_")


def _clip(x, y, w, h):
    """Cắt box về [0,1]. Trả None nếu sau khi cắt không còn diện tích."""
    x1, y1 = max(0.0, x - w / 2), max(0.0, y - h / 2)
    x2, y2 = min(1.0, x + w / 2), min(1.0, y + h / 2)
    if x2 <= x1 or y2 <= y1:
        return None
    return (x1 + x2) / 2, (y1 + y2) / 2, x2 - x1, y2 - y1


def fix(ds, issues, cfg):
    fixes = []
    errors = [i for i in issues if i.severity == ERROR]

    # --- 1) Lỗi cấp ảnh: xoá ảnh + nhãn
    removed = set()
    for i in errors:
        if _is_remove(i.code) and i.image not in removed:
            img = ds.image_path(i.image)
            lab = ds.label_path(i.image)
            if img is None and not lab.exists():
                continue
            if img is not None:
                img.unlink()
            if lab.exists():
                lab.unlink()
            removed.add(i.image)
            fixes.append({"image": i.image, "line": "", "action": "remove_image",
                          "before": img.name if img else "(không có ảnh)", "after": f"đã xoá ({i.code})"})

    # --- 2) Thiếu file nhãn: không bịa, chuyển người gán
    for i in errors:
        if i.code == "MISSING_LABEL_FILE" and i.image not in removed:
            fixes.append({"image": i.image, "line": "", "action": "needs_label",
                          "before": "(không có file)", "after": "chuyển người gán"})

    # --- 3) Sai tên lớp trong data.yaml
    if any(i.code == "BAD_CLASS_NAME" for i in errors) and ds.yaml_path.exists():
        d = yaml.safe_load(ds.yaml_path.read_text(encoding="utf-8")) or {}
        before = d.get("names")
        if before != list(cfg["classes"]):
            d["names"] = list(cfg["classes"])
            ds.yaml_path.write_text(yaml.safe_dump(d, allow_unicode=True, sort_keys=False), encoding="utf-8")
            fixes.append({"image": "data.yaml", "line": "", "action": "rename_classes",
                          "before": str(before), "after": str(cfg["classes"])})

    # --- 4) Lỗi theo dòng: gom theo file
    drop = defaultdict(set)
    clip = defaultdict(set)
    for i in errors:
        if i.line is None or i.image in removed:
            continue
        if i.code in DROP_CODES:
            drop[i.image].add(i.line)
        elif i.code == "BOX_OUT_OF_IMAGE":
            clip[i.image].add(i.line)

    for stem in sorted(set(drop) | set(clip)):
        p = ds.label_path(stem)
        if not p.exists():
            continue
        old = p.read_text(encoding="utf-8").splitlines()
        new = []
        for n, text in enumerate(old, 1):
            if n in drop[stem]:
                fixes.append({"image": stem, "line": n, "action": "drop_line", "before": text, "after": ""})
                continue
            if n in clip[stem]:
                try:
                    c, x, y, w, h = parse_yolo_line(text)
                    box = _clip(x, y, w, h)
                except ValueError:
                    box = None
                if box is None:
                    fixes.append({"image": stem, "line": n, "action": "drop_line", "before": text, "after": ""})
                    continue
                after = f"{c} " + " ".join(f"{v:.6f}" for v in box)
                fixes.append({"image": stem, "line": n, "action": "clip_box", "before": text, "after": after})
                new.append(after)
                continue
            new.append(text)
        p.write_text("".join(l + "\n" for l in new), encoding="utf-8")

    return fixes
