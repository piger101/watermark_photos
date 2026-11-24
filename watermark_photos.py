#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""批量给照片的左下角添加图片水印。

原图不会被修改，默认把处理结果写入与照片文件夹同级的
``<照片文件夹名>_watermarked`` 文件夹。
"""

from __future__ import annotations

import argparse
import os
import sys
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

from PIL import Image, ImageOps, UnidentifiedImageError

# 扩展名 -> Pillow 保存格式
PHOTO_FORMATS = {
    ".jpg": "JPEG",
    ".jpeg": "JPEG",
    ".jfif": "JPEG",
    ".png": "PNG",
    ".webp": "WEBP",
    ".bmp": "BMP",
    ".tif": "TIFF",
    ".tiff": "TIFF",
}

SUPPORTED_HINT = "JPG/JPEG/JFIF、PNG、WebP、BMP、TIFF"


class WatermarkError(Exception):
    """可以直接展示给用户的错误。"""


@dataclass(frozen=True)
class Settings:
    scale: float = 0.20
    margin_ratio: float = 0.03
    opacity: float = 1.0
    jpeg_quality: int = 95
    skip_existing: bool = False


def _path_arg(raw_value: str) -> Path:
    """清理路径两端的空格/引号，并转为绝对路径。"""
    value = raw_value.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {'"', "'"}:
        value = value[1:-1]
    return Path(value).expanduser().resolve()


def _is_relative_to(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
        return True
    except ValueError:
        return False


def _safe_dpi(info: dict) -> tuple[float, float] | None:
    dpi = info.get("dpi")
    if not isinstance(dpi, (tuple, list)) or len(dpi) != 2:
        return None
    try:
        x, y = float(dpi[0]), float(dpi[1])
    except (TypeError, ValueError):
        return None
    if not (1 <= x <= 10000 and 1 <= y <= 10000):
        return None
    return (round(x, 2), round(y, 2))


def load_watermark(path: Path) -> Image.Image:
    """载入水印，并统一转换为 RGBA。"""
    try:
        with Image.open(path) as image:
            image.load()
            # 水印图片本身也可能带手机拍摄的 EXIF 方向
            image = ImageOps.exif_transpose(image)
            return image.convert("RGBA")
    except FileNotFoundError as exc:
        raise WatermarkError(f"找不到水印图片：{path}") from exc
    except UnidentifiedImageError as exc:
        raise WatermarkError(f"无法识别水印图片格式：{path}") from exc
    except OSError as exc:
        raise WatermarkError(f"读取水印图片失败：{path}（{exc}）") from exc


def calculate_placement(
    frame_size: tuple[int, int],
    watermark_size: tuple[int, int],
    scale: float,
    margin_ratio: float,
) -> tuple[int, int, int, int]:
    """计算水印尺寸和左下角坐标，返回 (宽, 高, x, y)。"""
    frame_width, frame_height = frame_size
    mark_width, mark_height = watermark_size

    short_side = min(frame_width, frame_height)
    margin = round(short_side * margin_ratio)
    margin = max(0, min(margin, (short_side - 1) // 2))
    available_width = max(1, frame_width - 2 * margin)
    available_height = max(1, frame_height - 2 * margin)

    target_width = max(1, min(round(frame_width * scale), available_width))
    target_height = max(1, round(mark_height * target_width / mark_width))
    if target_height > available_height:
        target_height = available_height
        target_width = max(1, min(round(mark_width * target_height / mark_height), available_width))

    x = margin
    y = max(0, frame_height - margin - target_height)
    return target_width, target_height, x, y


def _resize_watermark(image: Image.Image, size: tuple[int, int]) -> Image.Image:
    """按目标尺寸缩放水印，保留透明通道。"""
    width, height = size
    alpha = image.getchannel("A").resize((width, height), Image.Resampling.LANCZOS)
    rgb = image.convert("RGB").resize((width, height), Image.Resampling.LANCZOS)
    rgb.putalpha(alpha)
    return rgb


def _prepare_watermark(
    watermark: Image.Image,
    frame_size: tuple[int, int],
    settings: Settings,
) -> tuple[Image.Image, int, int]:
    width, height, x, y = calculate_placement(
        frame_size, watermark.size, settings.scale, settings.margin_ratio
    )
    mark = watermark
    if watermark.size != (width, height):
        mark = _resize_watermark(watermark, (width, height))

    if settings.opacity < 1:
        mark = mark.copy()
        alpha = mark.getchannel("A").point(
            lambda value: int(round(value * settings.opacity))
        )
        mark.putalpha(alpha)

    return mark, x, y


def _flatten_on_white(image: Image.Image) -> Image.Image:
    """JPEG/BMP 不支持透明时，用白底压平。"""
    rgba = image.convert("RGBA")
    background = Image.new("RGBA", rgba.size, (255, 255, 255, 255))
    background.alpha_composite(rgba)
    return background.convert("RGB")


def _save_atomic(
    image: Image.Image,
    destination: Path,
    save_format: str,
    settings: Settings,
    exif: bytes | None,
    icc_profile: bytes | None,
    dpi: tuple[float, float] | None,
) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_name(
        f".{destination.name}.{uuid.uuid4().hex[:10]}.tmp"
    )

    if save_format in {"JPEG", "BMP"} and image.mode not in {"RGB", "L"}:
        image = _flatten_on_white(image)

    save_kwargs: dict = {}
    if exif and save_format in {"JPEG", "PNG", "WEBP"}:
        save_kwargs["exif"] = exif
    if icc_profile and save_format in {"JPEG", "PNG", "WEBP", "TIFF"}:
        save_kwargs["icc_profile"] = icc_profile
    if dpi and save_format in {"JPEG", "PNG", "TIFF"}:
        save_kwargs["dpi"] = dpi

    if save_format == "JPEG":
        save_kwargs.update(quality=settings.jpeg_quality, optimize=True)
    elif save_format == "WEBP":
        save_kwargs.update(quality=settings.jpeg_quality, method=4)
    elif save_format == "PNG":
        save_kwargs.update(optimize=True)
    elif save_format == "TIFF":
        save_kwargs.update(compression="tiff_lzw")

    try:
        image.save(temporary, format=save_format, **save_kwargs)
        os.replace(temporary, destination)
    finally:
        try:
            temporary.unlink(missing_ok=True)
        except OSError:
            pass


def apply_watermark(
    source: Path,
    destination: Path,
    watermark: Image.Image,
    settings: Settings,
) -> None:
    """处理一张照片并写入 destination。"""
    save_format = PHOTO_FORMATS.get(source.suffix.lower())
    if save_format is None:
        raise WatermarkError(f"不支持的文件格式：{source.suffix}")

    with Image.open(source) as photo:
        photo.load()

        # 先按 EXIF 方向把照片转正，再在“所见方向”的左下角定位水印。
        frame = ImageOps.exif_transpose(photo)
        frame.load()
        source_mode = frame.mode
        frame_size = frame.size

        try:
            exif_data = frame.getexif()
            exif = exif_data.tobytes() if exif_data else None
        except Exception:
            exif = None

        icc_profile = frame.info.get("icc_profile")
        if source_mode not in {"RGB", "RGBA"}:
            # 色彩模式已改变时，不强行复用原色彩配置文件，避免颜色配置不一致。
            icc_profile = None
        dpi = _safe_dpi(frame.info)

        has_alpha = source_mode in {"RGBA", "LA"} or (
            source_mode == "P" and "transparency" in frame.info
        )
        canvas = frame.convert("RGBA" if has_alpha else "RGB")

        mark, x, y = _prepare_watermark(watermark, frame_size, settings)
        if canvas.mode == "RGBA":
            canvas.alpha_composite(mark, (x, y))
        else:
            canvas.paste(mark, (x, y), mark)

        _save_atomic(
            canvas,
            destination,
            save_format,
            settings,
            exif,
            icc_profile,
            dpi,
        )


def collect_photos(
    input_dir: Path,
    output_dir: Path,
    watermark_path: Path,
    recursive: bool,
) -> list[Path]:
    """收集待处理照片；自动排除水印文件和输出目录。"""
    input_dir = input_dir.resolve()
    output_dir = output_dir.resolve()
    watermark_path = watermark_path.resolve()

    prune_output = (
        output_dir != input_dir and _is_relative_to(output_dir, input_dir)
    )
    photos: list[Path] = []

    for dirpath, dirnames, filenames in os.walk(input_dir, followlinks=False):
        current = Path(dirpath)

        # 输出目录若在输入目录内，剪枝，避免处理上一次的成品。
        if prune_output:
            dirnames[:] = [
                name
                for name in dirnames
                if (current / name).resolve() != output_dir
            ]

        for filename in filenames:
            path = current / filename
            if path.suffix.lower() not in PHOTO_FORMATS:
                continue
            try:
                resolved = path.resolve()
            except OSError:
                resolved = path.absolute()
            if resolved == watermark_path:
                continue
            if prune_output and _is_relative_to(resolved, output_dir):
                continue
            photos.append(path)

        if not recursive:
            dirnames.clear()

    photos.sort(key=lambda path: str(path.relative_to(input_dir)).casefold())
    return photos


def _default_output_dir(input_dir: Path) -> Path:
    name = input_dir.name or "photos"
    return input_dir.parent / f"{name}_watermarked"


def run_batch(
    input_dir: Path,
    watermark_path: Path,
    output_dir: Path,
    settings: Settings,
    recursive: bool = False,
    verbose: bool = False,
) -> int:
    input_dir = input_dir.resolve()
    watermark_path = watermark_path.resolve()
    output_dir = output_dir.resolve()

    if not input_dir.exists():
        raise WatermarkError(f"照片文件夹不存在：{input_dir}")
    if not input_dir.is_dir():
        raise WatermarkError(f"照片路径不是文件夹：{input_dir}")
    if not watermark_path.exists():
        raise WatermarkError(f"水印图片不存在：{watermark_path}")
    if not watermark_path.is_file():
        raise WatermarkError(f"水印路径不是文件：{watermark_path}")
    if output_dir == input_dir:
        raise WatermarkError("输出文件夹不能与照片文件夹相同，以免覆盖原图。")
    if output_dir.exists() and not output_dir.is_dir():
        raise WatermarkError(f"输出路径已存在且不是文件夹：{output_dir}")

    watermark = load_watermark(watermark_path)
    photos = collect_photos(input_dir, output_dir, watermark_path, recursive)
    if not photos:
        raise WatermarkError(
            f"在 {input_dir} 中没有找到可处理的照片。支持：{SUPPORTED_HINT}"
        )

    output_existed = output_dir.exists()
    try:
        output_dir.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise WatermarkError(f"无法创建输出文件夹：{output_dir}（{exc}）") from exc

    print(f"找到 {len(photos)} 张照片。")
    if output_existed:
        print("输出文件夹已存在，将写入该文件夹。")
    else:
        print("输出文件夹不存在，已自动创建。")
    print(f"输出路径：{output_dir}")
    print()

    succeeded = 0
    skipped = 0
    failed = 0
    total = len(photos)

    for index, source in enumerate(photos, start=1):
        relative = source.relative_to(input_dir)
        destination = output_dir / relative

        if settings.skip_existing and destination.exists():
            skipped += 1
            print(f"[{index}/{total}] 跳过（已存在）：{relative}")
            continue

        try:
            apply_watermark(source, destination, watermark, settings)
        except (UnidentifiedImageError, OSError, ValueError) as exc:
            failed += 1
            print(
                f"[{index}/{total}] 失败：{relative}\n    {exc}",
                file=sys.stderr,
            )
            if verbose:
                import traceback

                traceback.print_exc()
        except Exception as exc:  # 单张照片出错时继续处理其余照片
            failed += 1
            print(
                f"[{index}/{total}] 失败：{relative}\n    {type(exc).__name__}: {exc}",
                file=sys.stderr,
            )
            if verbose:
                import traceback

                traceback.print_exc()
        else:
            succeeded += 1
            print(f"[{index}/{total}] 已处理：{relative}")

    print()
    print(f"完成：成功 {succeeded} 张，失败 {failed} 张，跳过 {skipped} 张。")
    print(f"输出目录：{output_dir}")
    return 1 if failed else 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="批量给照片左下角添加图片水印（原图不会被修改）。",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "示例：\n"
            '  python watermark_photos.py "D:\\照片" "D:\\素材\\logo.png"\n'
            '  python watermark_photos.py "D:\\照片" "D:\\素材\\logo.png" -r\n'
            '  python watermark_photos.py "D:\\照片" "D:\\素材\\logo.png" '
            '-o "D:\\成片" --scale 0.15 --opacity 0.85\n'
        ),
    )
    parser.add_argument("input_folder", help="照片所在的文件夹")
    parser.add_argument(
        "watermark",
        help="水印图片的完整路径（推荐透明背景 PNG）",
    )
    parser.add_argument(
        "-o",
        "--output",
        help="输出文件夹（不存在会自动创建）；默认在照片文件夹同级创建“<文件夹名>_watermarked”",
    )
    parser.add_argument(
        "-r",
        "--recursive",
        action="store_true",
        help="递归处理子文件夹，并保持原有目录结构",
    )
    parser.add_argument(
        "--scale",
        type=float,
        default=0.20,
        metavar="比例",
        help="水印宽度占照片宽度的比例，默认 0.20",
    )
    parser.add_argument(
        "--margin",
        type=float,
        default=0.03,
        metavar="比例",
        help="水印距左边和下边的距离，占照片短边的比例，默认 0.03",
    )
    parser.add_argument(
        "--opacity",
        type=float,
        default=1.0,
        metavar="0-1",
        help="水印不透明度，默认 1.0（完全使用水印原图的透明度）",
    )
    parser.add_argument(
        "--quality",
        type=int,
        default=95,
        metavar="1-100",
        help="JPEG/WebP 输出质量，默认 95",
    )
    parser.add_argument(
        "--skip-existing",
        action="store_true",
        help="输出文件已存在时跳过（适合中断后继续处理）",
    )
    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="打印详细的错误堆栈",
    )
    parser.add_argument(
        "--version",
        action="version",
        version="%(prog)s 1.1",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if not 0 < args.scale <= 1:
        parser.error("--scale 必须大于 0 且不超过 1")
    if not 0 <= args.margin < 0.5:
        parser.error("--margin 必须大于等于 0 且小于 0.5")
    if not 0 < args.opacity <= 1:
        parser.error("--opacity 必须大于 0 且不超过 1")
    if not 1 <= args.quality <= 100:
        parser.error("--quality 必须在 1 到 100 之间")

    input_dir = _path_arg(args.input_folder)
    watermark_path = _path_arg(args.watermark)
    output_dir = (
        _path_arg(args.output)
        if args.output
        else _default_output_dir(input_dir)
    )

    settings = Settings(
        scale=args.scale,
        margin_ratio=args.margin,
        opacity=args.opacity,
        jpeg_quality=args.quality,
        skip_existing=args.skip_existing,
    )

    print(f"照片文件夹：{input_dir}")
    print(f"水印图片：{watermark_path}")
    print()

    try:
        return run_batch(
            input_dir,
            watermark_path,
            output_dir,
            settings,
            recursive=args.recursive,
            verbose=args.verbose,
        )
    except WatermarkError as exc:
        print(f"错误：{exc}", file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        print("\n已中断。已经完成的照片会保留在输出文件夹中。", file=sys.stderr)
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
