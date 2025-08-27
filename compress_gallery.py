#!/usr/bin/env python3
# -*- coding: utf-8 -*-

# python compress_gallery.py --src .\gallery --dst .\gallery_5MB
# python compress_gallery.py --src .\gallery --dst .\gallery_5MB --limit 5
# python compress_gallery.py --src .\gallery --dst .\gallery_10MB --limit 10


import os, sys, io, shutil, argparse
from pathlib import Path
from PIL import Image, ImageOps

# 可选支持 HEIC/HEIF
try:
    from pillow_heif import register_heif_opener  # type: ignore
    register_heif_opener()
except Exception:
    pass

IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".tif", ".tiff", ".bmp", ".webp", ".heic", ".heif"}

def is_image_file(p: Path) -> bool:
    return p.suffix.lower() in IMAGE_EXTS

def ensure_dir(p: Path):
    p.parent.mkdir(parents=True, exist_ok=True)

def normalize_orientation(img: Image.Image, strategy: str = "auto") -> tuple[Image.Image, bytes | None]:
    """
    返回 (像素已标准化的图像, EXIF字节或None)。写回的EXIF已将 Orientation(274)=1。
    strategy: "auto" | "force" | "strip"
    """
    try:
        exif = img.getexif()
    except Exception:
        exif = None

    ori = 1
    if exif and len(exif):
        ori = exif.get(274, 1)

    if strategy == "strip":
        if exif:
            exif[274] = 1
            return img, exif.tobytes()
        return img, None

    if strategy == "force":
        base = ImageOps.exif_transpose(img)
        if exif:
            exif[274] = 1
            return base, exif.tobytes()
        return base, None

    # strategy == "auto"
    w, h = img.size
    need_rotate = False
    if ori in (3, 4):         # 180°
        need_rotate = True
    elif ori in (5, 6, 7, 8): # 90°/270°
        need_rotate = (w >= h)  # 横图才旋转；已是竖图则不旋

    base = ImageOps.exif_transpose(img) if need_rotate else img
    if exif:
        exif[274] = 1
        return base, exif.tobytes()
    return base, None

def save_jpeg_under_limit(img: Image.Image,
                          limit_bytes: int,
                          exif_bytes: bytes | None,
                          icc: bytes | None,
                          min_side: int = 800,
                          quality_steps = (92, 85, 80, 72, 65, 60, 50)) -> bytes:
    """逐步降质，必要时等比缩放，直到 <= limit_bytes。此时 img 已完成方向归一化。"""
    base = img
    if base.mode not in ("RGB", "L"):
        base = base.convert("RGB")

    w, h = base.size
    scale = 1.0
    last_data = None

    while True:
        work = base if scale == 1.0 else base.resize((max(1,int(w*scale)), max(1,int(h*scale))), Image.LANCZOS)

        for q in quality_steps:
            buf = io.BytesIO()
            save_kwargs = dict(format="JPEG", quality=q, optimize=True, progressive=True, subsampling="4:2:0")
            if exif_bytes: save_kwargs["exif"] = exif_bytes
            if icc:        save_kwargs["icc_profile"] = icc
            work.save(buf, **save_kwargs)
            data = buf.getvalue()
            last_data = data
            if len(data) <= limit_bytes:
                return data

        if min(work.size) <= min_side:
            return last_data
        scale *= 0.85

def save_webp_under_limit(img: Image.Image,
                          limit_bytes: int,
                          exif_bytes: bytes | None,
                          icc: bytes | None,
                          min_side: int = 800,
                          quality_steps = (95, 90, 85, 80, 75, 70, 65, 60)) -> bytes:
    """保存为 WebP（可带透明），逐步降质与缩放至 <= limit_bytes。此时 img 已完成方向归一化。"""
    base = img
    has_alpha = (base.mode in ("RGBA", "LA")) or (base.mode == "P" and "transparency" in base.info)
    if has_alpha:
        if base.mode != "RGBA":
            base = base.convert("RGBA")
    else:
        if base.mode not in ("RGB", "L"):
            base = base.convert("RGB")

    w, h = base.size
    scale = 1.0
    last_data = None

    while True:
        work = base if scale == 1.0 else base.resize((max(1,int(w*scale)), max(1,int(h*scale))), Image.LANCZOS)

        for q in quality_steps:
            buf = io.BytesIO()
            save_kwargs = dict(format="WEBP", quality=q, method=6)
            if exif_bytes: save_kwargs["exif"] = exif_bytes  # 某些查看器可能忽略 WebP EXIF，但我们仍写入
            if icc:        save_kwargs["icc_profile"] = icc
            work.save(buf, **save_kwargs)
            data = buf.getvalue()
            last_data = data
            if len(data) <= limit_bytes:
                return data

        if min(work.size) <= min_side:
            return last_data
        scale *= 0.85

def compress_one(input_path: Path, output_path: Path, limit_bytes: int, min_side: int = 800, orient_strategy: str = "auto") -> tuple[bool, str]:
    try:
        if input_path.stat().st_size <= limit_bytes:
            ensure_dir(output_path)
            shutil.copy2(input_path, output_path)
            return True, f"SKIP (<= limit): {input_path}"

        with Image.open(input_path) as im:
            base, exif_bytes = normalize_orientation(im, strategy=orient_strategy)
            icc  = im.info.get("icc_profile", None)
            ext = input_path.suffix.lower()

            if ext == ".png":
                data = save_webp_under_limit(base, limit_bytes, exif_bytes, icc, min_side=min_side)
                out = output_path.with_suffix(".webp")
                ensure_dir(out)
                with open(out, "wb") as f:
                    f.write(data)
                return True, f"PNG->WebP->OK: {input_path} -> {out.name}"

            elif ext in (".jpg", ".jpeg", ".webp", ".tif", ".tiff", ".bmp", ".heic", ".heif"):
                data = save_jpeg_under_limit(base, limit_bytes, exif_bytes, icc, min_side=min_side)
                out = output_path.with_suffix(".jpg")
                ensure_dir(out)
                with open(out, "wb") as f:
                    f.write(data)
                return True, f"{ext.upper().lstrip('.')}->JPEG->OK: {input_path} -> {out.name}"

            else:
                data = save_jpeg_under_limit(base, limit_bytes, exif_bytes, icc, min_side=min_side)
                out = output_path.with_suffix(".jpg")
                ensure_dir(out)
                with open(out, "wb") as f:
                    f.write(data)
                return True, f"OTHER->JPEG->OK: {input_path} -> {out.name}"

    except Exception as e:
        return False, f"FAIL: {input_path} ({e})"

def walk_and_compress(src: Path, dst: Path, limit_mb: float, min_side: int, orient_strategy: str):
    limit_bytes = int(limit_mb * 1024 * 1024)
    total = ok = fail = 0
    for root, _, files in os.walk(src):
        for name in files:
            total += 1
            in_path = Path(root) / name
            rel = in_path.relative_to(src)
            out_path = (dst / rel)

            if not is_image_file(in_path):
                try:
                    ensure_dir(out_path)
                    shutil.copy2(in_path, out_path)
                    ok += 1
                    print(f"COPY (non-image): {in_path}")
                except Exception as e:
                    fail += 1
                    print(f"FAIL COPY: {in_path} ({e})")
                continue

            success, msg = compress_one(in_path, out_path, limit_bytes, min_side=min_side, orient_strategy=orient_strategy)
            print(msg)
            ok += int(success)
            fail += int(not success)

    print("\n=== Summary ===")
    print(f"Source: {src}")
    print(f"Output: {dst}")
    print(f"Limit : {limit_mb} MB")
    print(f"Total : {total} | OK: {ok} | FAIL: {fail}")

def main():
    ap = argparse.ArgumentParser(description="Compress images; PNG->WebP (alpha), others->JPEG. Orientation fixed.")
    ap.add_argument("--src", type=str, required=True, help="Source folder (e.g., ./gallery)")
    ap.add_argument("--dst", type=str, required=True, help="Output folder (e.g., ./gallery_5MB)")
    ap.add_argument("--limit", type=float, default=5.0, help="Max size per image in MB (default: 5)")
    ap.add_argument("--min-side", type=int, default=800, help="Do not scale below this shorter side (default: 800px)")
    ap.add_argument("--orientation", type=str, choices=["auto","force","strip"], default="auto",
                    help="Orientation fix strategy: auto (default), force (always rotate by EXIF), strip (no rotate, set Orientation=1)")
    args = ap.parse_args()

    src = Path(args.src).resolve()
    dst = Path(args.dst).resolve()

    if not src.exists():
        print(f"Source folder not found: {src}")
        sys.exit(1)
    dst.mkdir(parents=True, exist_ok=True)

    walk_and_compress(src, dst, args.limit, args.min_side, args.orientation)

if __name__ == "__main__":
    main()
