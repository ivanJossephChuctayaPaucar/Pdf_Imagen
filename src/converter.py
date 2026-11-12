from __future__ import annotations

import re
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Literal

import pymupdf
from PIL import Image

OutputFormat = Literal["PNG", "JPG"]

INVALID_FILENAME_CHARS = re.compile(r'[<>:"/\\|?*\x00-\x1f]')


@dataclass(slots=True)
class PdfInfo:
    path: Path
    page_count: int
    needs_password: bool = False


@dataclass(slots=True)
class ConversionOptions:
    output_format: OutputFormat = "PNG"
    dpi: int = 300
    jpg_quality: int = 95
    transparent_png: bool = False
    page_range: str = ""
    output_dir: Path | None = None
    create_subfolder: bool = True
    password: str | None = None

    def validate(self) -> None:
        fmt = self.output_format.upper()
        if fmt not in ("PNG", "JPG"):
            raise ValueError(f"Formato no soportado: {self.output_format}. Usa PNG o JPG.")
        if not (36 <= self.dpi <= 1200):
            raise ValueError("La resolución DPI debe estar entre 36 y 1200.")
        if not (1 <= self.jpg_quality <= 100):
            raise ValueError("La calidad JPG debe estar entre 1 y 100.")


@dataclass(slots=True)
class ConversionResult:
    pdf_path: Path
    output_dir: Path
    generated_files: list[Path] = field(default_factory=list)
    total_pages_converted: int = 0
    elapsed_seconds: float = 0.0
    cancelled: bool = False


ProgressCallback = Callable[[int, int, Path], None]


def sanitize_filename(name: str) -> str:
    cleaned = INVALID_FILENAME_CHARS.sub("_", name).strip(" .")
    return cleaned or "documento"


def parse_page_range(range_str: str, total_pages: int) -> list[int]:
    """Convierte un rango de páginas 1-based (ej. '1-3, 5') a índices 0-based ordenados."""
    if total_pages <= 0:
        raise ValueError("El documento PDF no tiene páginas.")

    cleaned = range_str.strip()
    if not cleaned:
        return list(range(total_pages))

    selected: set[int] = set()
    parts = [p.strip() for p in cleaned.split(",") if p.strip()]
    if not parts:
        return list(range(total_pages))

    for part in parts:
        if "-" in part:
            bounds = [b.strip() for b in part.split("-")]
            if len(bounds) != 2 or not bounds[0].isdigit() or not bounds[1].isdigit():
                raise ValueError(f"Rango de páginas inválido: '{part}'. Ejemplo válido: 1-5, 8")
            start = int(bounds[0])
            end = int(bounds[1])
            if start < 1 or end < 1 or start > total_pages or end > total_pages:
                raise ValueError(
                    f"El rango '{part}' está fuera de límites (el PDF tiene {total_pages} páginas)."
                )
            step = 1 if start <= end else -1
            for page_num in range(start, end + step, step):
                selected.add(page_num - 1)
        else:
            if not part.isdigit():
                raise ValueError(f"Número de página inválido: '{part}'.")
            page_num = int(part)
            if page_num < 1 or page_num > total_pages:
                raise ValueError(
                    f"La página {page_num} está fuera de límites (el PDF tiene {total_pages} páginas)."
                )
            selected.add(page_num - 1)

    return sorted(selected)


def get_pdf_info(pdf_path: Path) -> PdfInfo:
    if not pdf_path.exists():
        raise FileNotFoundError(f"No se encontró el archivo: {pdf_path}")

    with pymupdf.open(pdf_path) as doc:
        if doc.needs_pass:
            # Intenta contraseña vacía por si solo tiene restricciones de permisos
            if not doc.authenticate(""):
                return PdfInfo(path=pdf_path, page_count=0, needs_password=True)
        return PdfInfo(path=pdf_path, page_count=doc.page_count, needs_password=False)


def resolve_output_dir(pdf_path: Path, options: ConversionOptions) -> Path:
    base_dir = options.output_dir if options.output_dir is not None else pdf_path.parent
    if options.create_subfolder:
        safe_stem = sanitize_filename(pdf_path.stem)
        return base_dir / f"{safe_stem}_imagenes"
    return base_dir


def convert_pdf_to_images(
    pdf_path: Path,
    options: ConversionOptions,
    progress_cb: ProgressCallback | None = None,
    cancel_event: threading.Event | None = None,
) -> ConversionResult:
    options.validate()

    if not pdf_path.exists() or not pdf_path.is_file():
        raise FileNotFoundError(f"No se encontró el archivo PDF: {pdf_path}")

    start_time = time.perf_counter()
    fmt = options.output_format.upper()
    use_alpha = fmt == "PNG" and options.transparent_png
    ext = "png" if fmt == "PNG" else "jpg"

    target_dir = resolve_output_dir(pdf_path, options)
    target_dir.mkdir(parents=True, exist_ok=True)

    safe_stem = sanitize_filename(pdf_path.stem)
    generated_files: list[Path] = []

    with pymupdf.open(pdf_path) as doc:
        if doc.needs_pass:
            password = options.password or ""
            if not doc.authenticate(password):
                raise PermissionError(
                    f"El PDF '{pdf_path.name}' está protegido con contraseña."
                )

        total_pages = doc.page_count
        page_indices = parse_page_range(options.page_range, total_pages)
        digits = max(3, len(str(total_pages)))

        zoom = options.dpi / 72.0
        matrix = pymupdf.Matrix(zoom, zoom)

        total_selected = len(page_indices)
        for idx, page_index in enumerate(page_indices, start=1):
            if cancel_event is not None and cancel_event.is_set():
                return ConversionResult(
                    pdf_path=pdf_path,
                    output_dir=target_dir,
                    generated_files=generated_files,
                    total_pages_converted=len(generated_files),
                    elapsed_seconds=time.perf_counter() - start_time,
                    cancelled=True,
                )

            page = doc.load_page(page_index)
            pixmap = page.get_pixmap(
                matrix=matrix,
                colorspace=pymupdf.csRGB,
                alpha=use_alpha,
            )

            mode = "RGBA" if use_alpha else "RGB"
            image = Image.frombytes(mode, (pixmap.width, pixmap.height), pixmap.samples)

            page_label = str(page_index + 1).zfill(digits)
            out_path = target_dir / f"{safe_stem}_pag_{page_label}.{ext}"

            if fmt == "PNG":
                image.save(
                    out_path,
                    format="PNG",
                    optimize=True,
                    compress_level=6,
                    dpi=(options.dpi, options.dpi),
                )
            else:
                image.save(
                    out_path,
                    format="JPEG",
                    quality=options.jpg_quality,
                    subsampling=0,  # 4:4:4 para máxima nitidez en texto y gráficos
                    optimize=True,
                    dpi=(options.dpi, options.dpi),
                )

            generated_files.append(out_path)
            del image, pixmap

            if idx % 25 == 0:
                pymupdf.TOOLS.store_shrink(100)

            if progress_cb is not None:
                progress_cb(idx, total_selected, out_path)

    return ConversionResult(
        pdf_path=pdf_path,
        output_dir=target_dir,
        generated_files=generated_files,
        total_pages_converted=len(generated_files),
        elapsed_seconds=time.perf_counter() - start_time,
        cancelled=False,
    )
