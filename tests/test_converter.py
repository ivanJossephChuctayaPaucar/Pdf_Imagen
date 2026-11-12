from __future__ import annotations

import threading
from pathlib import Path

import pymupdf
import pytest
from PIL import Image

from src.converter import (
    ConversionOptions,
    convert_pdf_to_images,
    get_pdf_info,
    parse_page_range,
)
from src.main import main


def _create_sample_pdf(path: Path, pages: int = 3) -> Path:
    doc = pymupdf.open()
    for i in range(pages):
        # 200 x 100 puntos (200/72 x 100/72 pulgadas)
        page = doc.new_page(width=200, height=100)
        page.insert_text((20, 55), f"Pagina {i + 1}", fontsize=20, color=(0.1, 0.2, 0.7))
    doc.save(path)
    doc.close()
    return path


def test_parse_page_range_valid() -> None:
    assert parse_page_range("", 5) == [0, 1, 2, 3, 4]
    assert parse_page_range("1, 3-5", 6) == [0, 2, 3, 4]
    assert parse_page_range("4-2, 2", 5) == [1, 2, 3]


def test_parse_page_range_invalid() -> None:
    with pytest.raises(ValueError):
        parse_page_range("0", 5)
    with pytest.raises(ValueError):
        parse_page_range("6", 5)
    with pytest.raises(ValueError):
        parse_page_range("abc", 5)


def test_convert_pdf_to_png_high_dpi(tmp_path: Path) -> None:
    pdf_path = _create_sample_pdf(tmp_path / "prueba.pdf", pages=3)
    out_dir = tmp_path / "salida"

    options = ConversionOptions(
        output_format="PNG",
        dpi=300,
        transparent_png=False,
        page_range="1, 3",
        output_dir=out_dir,
        create_subfolder=False,
    )
    result = convert_pdf_to_images(pdf_path, options)

    assert not result.cancelled
    assert result.total_pages_converted == 2
    assert len(result.generated_files) == 2
    assert result.generated_files[0].name == "prueba_pag_001.png"
    assert result.generated_files[1].name == "prueba_pag_003.png"

    with Image.open(result.generated_files[0]) as img:
        assert img.mode == "RGB"
        # 200 * 300 / 72 = 833.33 -> 833 px; 100 * 300 / 72 = 416.66 -> 417 px
        assert abs(img.width - 833) <= 2
        assert abs(img.height - 417) <= 2
        dpi = img.info.get("dpi")
        assert dpi is not None
        assert round(dpi[0]) == 300


def test_convert_pdf_to_transparent_png(tmp_path: Path) -> None:
    pdf_path = _create_sample_pdf(tmp_path / "transp.pdf", pages=1)
    options = ConversionOptions(
        output_format="PNG",
        dpi=150,
        transparent_png=True,
        output_dir=tmp_path,
        create_subfolder=True,
    )
    result = convert_pdf_to_images(pdf_path, options)
    assert result.output_dir == tmp_path / "transp_imagenes"
    with Image.open(result.generated_files[0]) as img:
        assert img.mode == "RGBA"


def test_convert_pdf_to_jpg_high_quality(tmp_path: Path) -> None:
    pdf_path = _create_sample_pdf(tmp_path / "doc.pdf", pages=2)
    options = ConversionOptions(
        output_format="JPG",
        dpi=300,
        jpg_quality=96,
        output_dir=tmp_path / "jpgs",
        create_subfolder=False,
    )
    result = convert_pdf_to_images(pdf_path, options)
    assert result.total_pages_converted == 2
    assert all(p.suffix == ".jpg" for p in result.generated_files)

    with Image.open(result.generated_files[0]) as img:
        assert img.format == "JPEG"
        assert img.mode == "RGB"
        dpi = img.info.get("dpi")
        assert dpi == (300, 300)


def test_cancellation(tmp_path: Path) -> None:
    pdf_path = _create_sample_pdf(tmp_path / "largo.pdf", pages=5)
    cancel_event = threading.Event()

    def on_page(cur: int, total: int, out_path: Path) -> None:
        if cur == 2:
            cancel_event.set()

    options = ConversionOptions(output_format="PNG", dpi=150, output_dir=tmp_path / "cancel_out")
    result = convert_pdf_to_images(pdf_path, options, progress_cb=on_page, cancel_event=cancel_event)
    assert result.cancelled
    assert result.total_pages_converted == 2


def test_get_pdf_info_and_cli(tmp_path: Path) -> None:
    pdf_path = _create_sample_pdf(tmp_path / "cli_doc.pdf", pages=2)
    info = get_pdf_info(pdf_path)
    assert info.page_count == 2
    assert not info.needs_password

    out_dir = tmp_path / "cli_out"
    code = main(
        [
            "--cli",
            str(pdf_path),
            "--format",
            "jpg",
            "--dpi",
            "200",
            "--quality",
            "95",
            "--out",
            str(out_dir),
            "--no-subfolder",
        ]
    )
    assert code == 0
    assert (out_dir / "cli_doc_pag_001.jpg").exists()
    assert (out_dir / "cli_doc_pag_002.jpg").exists()


def test_convert_many_pages_pdf(tmp_path: Path) -> None:
    pdf_path = _create_sample_pdf(tmp_path / "muchas_hojas.pdf", pages=30)
    out_dir = tmp_path / "lote_30"
    options = ConversionOptions(
        output_format="PNG",
        dpi=100,
        output_dir=out_dir,
        create_subfolder=False,
    )
    result = convert_pdf_to_images(pdf_path, options)
    assert result.total_pages_converted == 30
    assert result.generated_files[0].name == "muchas_hojas_pag_001.png"
    assert result.generated_files[-1].name == "muchas_hojas_pag_030.png"
