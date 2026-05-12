"""
prescription_cropper.py
────────────────────────────────────────────────────────────────────────────
Detects the borders of a prescription document in a photo and returns a
clean, deskewed, top-down crop ready for OCR.

Pipeline
────────
  load_image  ──►  preprocess  ──►  find_document_contour
       │                                      │
       │                              order_corner_points
       │                                      │
       └──────────────────────────►  perspective_transform
                                              │
                                        clean image ◄──── optional enhance()
"""

import cv2
import numpy as np
from pathlib import Path


# ─────────────────────────────────────────────────────────────────────────────
# 1.  PREPROCESSING  (edge map used for contour detection)
# ─────────────────────────────────────────────────────────────────────────────

def preprocess_for_detection(image: np.ndarray) -> np.ndarray:
    """
    Convert the image to a clean edge map that makes document borders easy to
    find even on cluttered or low-contrast backgrounds.

    Returns a binary edge image (uint8, same H×W as input).
    """
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)

    # ── mild blur to suppress noise while keeping hard edges ──
    blurred = cv2.GaussianBlur(gray, (5, 5), 0)

    # ── adaptive threshold → works for uneven lighting ──
    thresh = cv2.adaptiveThreshold(
        blurred, 255,
        cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
        cv2.THRESH_BINARY,
        blockSize=11, C=2
    )

    # ── Canny on the thresholded image (sharper edges) ──
    edges = cv2.Canny(thresh, threshold1=30, threshold2=100)

    # ── dilate to close small gaps in the border line ──
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (5, 5))
    edges = cv2.dilate(edges, kernel, iterations=1)

    return edges


# ─────────────────────────────────────────────────────────────────────────────
# 2.  CONTOUR DETECTION  (find the quadrilateral that is the prescription)
# ─────────────────────────────────────────────────────────────────────────────

def find_document_contour(
    edges: np.ndarray,
    min_area_ratio: float = 0.10,
    fallback_to_full: bool = True,
) -> np.ndarray | None:
    """
    Locate the largest 4-corner contour in the edge image.

    Parameters
    ----------
    edges           : binary edge image from preprocess_for_detection()
    min_area_ratio  : contour must cover at least this fraction of the image area
    fallback_to_full: if no quad is found, return the full-image corners instead
                      of None – useful when the prescription already fills the frame

    Returns
    -------
    np.ndarray of shape (4, 2) with the four corner points (float32),
    or None if nothing is found and fallback_to_full is False.
    """
    h, w = edges.shape[:2]
    image_area = h * w

    contours, _ = cv2.findContours(
        edges, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE
    )
    contours = sorted(contours, key=cv2.contourArea, reverse=True)

    for cnt in contours[:10]:                      # inspect only the 10 largest
        area = cv2.contourArea(cnt)
        if area < min_area_ratio * image_area:     # too small → skip
            continue

        # ── approximate the contour to a polygon ──
        peri    = cv2.arcLength(cnt, closed=True)
        epsilon = 0.02 * peri                      # 2 % tolerance
        approx  = cv2.approxPolyDP(cnt, epsilon, closed=True)

        if len(approx) == 4:                       # perfect quad → done
            return approx.reshape(4, 2).astype(np.float32)

        # ── try tighter epsilon if we got too many points ──
        for eps_factor in [0.03, 0.05, 0.08]:
            approx = cv2.approxPolyDP(cnt, eps_factor * peri, closed=True)
            if len(approx) == 4:
                return approx.reshape(4, 2).astype(np.float32)

        # ── last resort: bounding rotated rectangle of this contour ──
        rect   = cv2.minAreaRect(cnt)
        box    = cv2.boxPoints(rect)
        return box.astype(np.float32)

    # ── nothing found ──
    if fallback_to_full:
        return np.array([[0, 0], [w, 0], [w, h], [0, h]], dtype=np.float32)
    return None


# ─────────────────────────────────────────────────────────────────────────────
# 3.  CORNER ORDERING  (TL, TR, BR, BL)
# ─────────────────────────────────────────────────────────────────────────────

def order_points(pts: np.ndarray) -> np.ndarray:
    """
    Reorder four corner points to (top-left, top-right, bottom-right, bottom-left).

    Works for any quadrilateral, including skewed/rotated ones.
    """
    pts = pts.reshape(4, 2)
    ordered = np.zeros((4, 2), dtype=np.float32)

    s = pts.sum(axis=1)
    ordered[0] = pts[np.argmin(s)]    # top-left     (smallest x+y)
    ordered[2] = pts[np.argmax(s)]    # bottom-right (largest  x+y)

    d = np.diff(pts, axis=1).ravel()  # y - x  for each point
    ordered[1] = pts[np.argmin(d)]    # top-right    (smallest y-x)
    ordered[3] = pts[np.argmax(d)]    # bottom-left  (largest  y-x)

    return ordered


# ─────────────────────────────────────────────────────────────────────────────
# 4.  PERSPECTIVE TRANSFORM  (warp to flat rectangle)
# ─────────────────────────────────────────────────────────────────────────────

def perspective_transform(
    image: np.ndarray,
    corners: np.ndarray,
    output_size: tuple[int, int] | None = None,
    dpi_padding: int = 10,
) -> np.ndarray:
    """
    Apply a four-point perspective warp to produce a flat, rectangular crop.

    Parameters
    ----------
    image       : original BGR image
    corners     : (4, 2) array from order_points()
    output_size : (width, height) of the output; auto-computed if None
    dpi_padding : pixels of white padding added on each side

    Returns
    -------
    Warped (cropped) BGR image.
    """
    tl, tr, br, bl = order_points(corners)

    # ── compute natural output dimensions if not specified ──
    if output_size is None:
        width_top    = np.linalg.norm(tr - tl)
        width_bottom = np.linalg.norm(br - bl)
        width        = int(max(width_top, width_bottom))

        height_left  = np.linalg.norm(bl - tl)
        height_right = np.linalg.norm(br - tr)
        height       = int(max(height_left, height_right))
    else:
        width, height = output_size

    dst = np.array([
        [0,         0],
        [width - 1, 0],
        [width - 1, height - 1],
        [0,         height - 1],
    ], dtype=np.float32)

    src = np.array([tl, tr, br, bl], dtype=np.float32)

    M       = cv2.getPerspectiveTransform(src, dst)
    warped  = cv2.warpPerspective(image, M, (width, height))

    # ── optional padding ──
    if dpi_padding > 0:
        warped = cv2.copyMakeBorder(
            warped,
            dpi_padding, dpi_padding, dpi_padding, dpi_padding,
            cv2.BORDER_CONSTANT, value=(255, 255, 255),
        )

    return warped


# ─────────────────────────────────────────────────────────────────────────────
# 5.  OPTIONAL POST-PROCESSING  (improve contrast for OCR)
# ─────────────────────────────────────────────────────────────────────────────

def enhance_for_ocr(image: np.ndarray) -> np.ndarray:
    """
    Apply contrast enhancement and sharpening to improve OCR accuracy.

    Call this on the warped image before passing it to your medicine extractor.
    """
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)

    # ── CLAHE: adaptive contrast equalisation ──
    clahe = cv2.createCLAHE(clipLimit=2.5, tileGridSize=(8, 8))
    gray  = clahe.apply(gray)

    # ── sharpen ──
    kernel = np.array([[0, -1, 0],
                       [-1, 5, -1],
                       [0, -1, 0]])
    sharp = cv2.filter2D(gray, -1, kernel)

    # ── Otsu binarisation (optional – comment out to keep grayscale) ──
    _, binary = cv2.threshold(sharp, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)

    # return as BGR so it integrates with any BGR pipeline
    return cv2.cvtColor(binary, cv2.COLOR_GRAY2BGR)


# ─────────────────────────────────────────────────────────────────────────────
# 6.  HIGH-LEVEL  extract_prescription()  – the function you call
# ─────────────────────────────────────────────────────────────────────────────

def extract_prescription(
    image_input: str | Path | np.ndarray,
    enhance: bool = True,
    debug: bool = False,
    debug_output_path: str | Path | None = None,
) -> np.ndarray:
    """
    Full pipeline: load → detect borders → crop → (optionally) enhance.

    Parameters
    ----------
    image_input        : file path (str / Path) OR a BGR numpy array
    enhance            : run enhance_for_ocr() on the cropped result
    debug              : draw the detected contour on a copy and show/save it
    debug_output_path  : if given, save the debug image here instead of displaying

    Returns
    -------
    Clean prescription image as a BGR numpy array, ready for OCR.

    Raises
    ------
    FileNotFoundError  if image_input is a path that does not exist
    ValueError         if the image cannot be decoded
    """
    # ── load ──
    if isinstance(image_input, (str, Path)):
        path = Path(image_input)
        if not path.exists():
            raise FileNotFoundError(f"Image not found: {path}")
        image = cv2.imread(str(path))
        if image is None:
            raise ValueError(f"cv2.imread failed for: {path}")
    else:
        image = image_input.copy()

    # ── edge map ──
    edges = preprocess_for_detection(image)

    # ── find document quad ──
    corners = find_document_contour(edges)
    if corners is None:
        raise RuntimeError("No document border found in the image.")

    # ── optional debug overlay ──
    if debug:
        debug_img = image.copy()
        ordered   = order_points(corners).astype(np.int32)
        cv2.polylines(debug_img, [ordered], isClosed=True, color=(0, 255, 0), thickness=3)
        for i, (x, y) in enumerate(ordered):
            cv2.circle(debug_img, (int(x), int(y)), 10, (0, 0, 255), -1)
            cv2.putText(debug_img, ["TL", "TR", "BR", "BL"][i],
                        (int(x) + 12, int(y) - 12),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.9, (255, 0, 0), 2)

        if debug_output_path:
            cv2.imwrite(str(debug_output_path), debug_img)
            print(f"[debug] contour saved → {debug_output_path}")
        else:
            cv2.imshow("Detected Prescription Border", debug_img)
            cv2.waitKey(0)
            cv2.destroyAllWindows()

    # ── warp ──
    warped = perspective_transform(image, corners)

    # ── enhance (for OCR) ──
    if enhance:
        warped = enhance_for_ocr(warped)

    return warped


# ─────────────────────────────────────────────────────────────────────────────
# 7.  BATCH HELPER
# ─────────────────────────────────────────────────────────────────────────────

def batch_extract(
    input_dir: str | Path,
    output_dir: str | Path,
    extensions: tuple[str, ...] = (".jpg", ".jpeg", ".png", ".bmp", ".tiff"),
    enhance: bool = True,
    debug: bool = False,
) -> list[Path]:
    """
    Process every prescription image in input_dir and save results to output_dir.

    Returns a list of successfully written output paths.
    """
    input_dir  = Path(input_dir)
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    written = []
    for img_path in sorted(input_dir.iterdir()):
        if img_path.suffix.lower() not in extensions:
            continue
        try:
            clean     = extract_prescription(img_path, enhance=enhance, debug=debug)
            out_path  = output_dir / img_path.name
            cv2.imwrite(str(out_path), clean)
            written.append(out_path)
            print(f"  ✓  {img_path.name}  →  {out_path}")
        except Exception as exc:
            print(f"  ✗  {img_path.name}  –  {exc}")

    return written


# ─────────────────────────────────────────────────────────────────────────────
# CLI  (python prescription_cropper.py  input.jpg  [output.jpg]  [--debug])
# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import sys

    args  = [a for a in sys.argv[1:] if not a.startswith("--")]
    flags = [a for a in sys.argv[1:] if a.startswith("--")]

    if not args:
        print("Usage: python prescription_cropper.py <input> [output] [--debug] [--no-enhance]")
        sys.exit(1)

    src     = args[0]
    dst     = args[1] if len(args) > 1 else None
    debug   = "--debug" in flags
    enhance = "--no-enhance" not in flags

    result = extract_prescription(src, enhance=enhance, debug=debug)

    if dst:
        cv2.imwrite(dst, result)
        print(f"Saved clean prescription → {dst}")
    else:
        cv2.imshow("Clean Prescription", result)
        cv2.waitKey(0)
        cv2.destroyAllWindows()
