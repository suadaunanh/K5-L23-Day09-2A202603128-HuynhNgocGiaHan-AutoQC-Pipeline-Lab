"""BƯỚC 4 — Cửa chặn: quyết định Release / Hold / Rework.   ★

Test:  pytest tests/test_gate.py -q

Cây quyết định Day 07 (slide Day 09: "Lỗi bắt buộc chặn pipeline; lỗi cảnh báo chuyển người xem"):

  còn ≥ 1 lỗi bắt buộc (severity ERROR)                          -> "Rework"
  không còn lỗi bắt buộc, nhưng tỉ lệ ẢNH còn cảnh báo
      >= cfg["gate"]["warn_ratio_hold"]                          -> "Hold"
  còn lại                                                        -> "Release"

Tỉ lệ cảnh báo = (số ẢNH khác nhau có ≥ 1 cảnh báo) / (tổng số ảnh).  Chú ý:
- chỉ đếm issue có `image` nằm trong `image_stems` (bỏ "<dataset>", "data.yaml");
- bỏ qua ảnh nằm trong `reviewed` (người đã xem, cảnh báo của ảnh đó coi như đã xử lý) — nhưng LỖI BẮT BUỘC thì không bao giờ được bỏ qua;
- mẫu số là số ảnh, không phải số issue.

Trả về dict: decision, n_errors, n_warn_images, n_images, warn_ratio (làm tròn 4 chữ số), reasons (list[str], giải thích bằng tiếng Việt, có số liệu).
"""

from ..common import ERROR, WARN  # noqa: F401


def _get(issue, key):
    """Đọc field của issue, chạy được cả khi issue là dict lẫn object/dataclass."""
    if isinstance(issue, dict):
        return issue.get(key)
    return getattr(issue, key, None)


def decide(issues, image_stems, cfg, reviewed=frozenset()):
    image_stems = set(image_stems)
    reviewed = set(reviewed)
    n_images = len(image_stems)

    # 1) Đếm lỗi bắt buộc: tính MỌI issue ERROR, kể cả "<dataset>", "data.yaml",
    #    và kể cả ảnh đã nằm trong reviewed (lỗi bắt buộc không bao giờ được bỏ qua)
    n_errors = sum(1 for it in issues if _get(it, "severity") == ERROR)

    # 2) Tập ẢNH khác nhau có ≥ 1 cảnh báo (chỉ lấy ảnh thật, bỏ ảnh đã review)
    warn_images = {
        _get(it, "image")
        for it in issues
        if _get(it, "severity") == WARN
        and _get(it, "image") in image_stems
        and _get(it, "image") not in reviewed
    }
    n_warn_images = len(warn_images)

    # 3) Tỉ lệ = số ảnh có cảnh báo / tổng số ảnh (không chia cho số issue)
    #    So ngưỡng bằng tỉ lệ CHÍNH XÁC; chỉ làm tròn khi trả về / in ra
    #    (vd 1999/20000 = 0.09995 làm tròn thành 0.1 sẽ thành Hold sai).
    exact_ratio = n_warn_images / n_images if n_images else 0.0
    warn_ratio = round(exact_ratio, 4)
    threshold = cfg["gate"]["warn_ratio_hold"]
    # Số ảnh đã review thực sự có cảnh báo bị bỏ qua (không đếm ảnh review mà không có cảnh báo)
    n_reviewed_skipped = len({
        _get(it, "image")
        for it in issues
        if _get(it, "severity") == WARN
        and _get(it, "image") in image_stems
        and _get(it, "image") in reviewed
    })

    # 4) Cây quyết định
    reasons = []
    if n_errors >= 1:
        decision = "Rework"
        reasons.append(f"Còn {n_errors} lỗi bắt buộc (ERROR) -> phải sửa lại dữ liệu.")
    elif exact_ratio >= threshold:
        decision = "Hold"
        reasons.append("Không còn lỗi bắt buộc.")
        reasons.append(
            f"{n_warn_images}/{n_images} ảnh còn cảnh báo "
            f"(tỉ lệ {warn_ratio:.2%} >= ngưỡng {threshold:.2%}) -> chuyển người xem."
        )
    else:
        decision = "Release"
        reasons.append("Không còn lỗi bắt buộc.")
        reasons.append(
            f"{n_warn_images}/{n_images} ảnh còn cảnh báo "
            f"(tỉ lệ {warn_ratio:.2%} < ngưỡng {threshold:.2%}) -> cho phát hành."
        )
    if n_reviewed_skipped:
        reasons.append(f"Đã bỏ qua cảnh báo của {n_reviewed_skipped} ảnh người đã xem.")

    return {
        "decision": decision,
        "n_errors": n_errors,
        "n_warn_images": n_warn_images,
        "n_images": n_images,
        "warn_ratio": warn_ratio,
        "reasons": reasons,
    }
