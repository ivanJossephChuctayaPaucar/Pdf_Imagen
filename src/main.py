from __future__ import annotations

import argparse
import sys
from pathlib import Path

from src.converter import ConversionOptions, convert_pdf_to_images


def _run_cli(args: argparse.Namespace) -> int:
    if not args.inputs:
        print("Error: debes especificar al menos un archivo o carpeta PDF con --cli.", file=sys.stderr)
        return 2

    pdf_files: list[Path] = []
    for raw in args.inputs:
        p = Path(raw)
        if p.is_dir():
            pdf_files.extend(sorted(p.glob("*.pdf")))
        elif p.is_file():
            pdf_files.append(p)
        else:
            print(f"Advertencia: no se encontró '{p}'", file=sys.stderr)

    if not pdf_files:
        print("Error: no se encontraron archivos PDF válidos.", file=sys.stderr)
        return 1

    options = ConversionOptions(
        output_format=args.format.upper(),  # type: ignore[arg-type]
        dpi=args.dpi,
        jpg_quality=args.quality,
        transparent_png=args.transparent,
        page_range=args.pages,
        output_dir=Path(args.out) if args.out else None,
        create_subfolder=not args.no_subfolder,
        password=args.password,
    )
    options.validate()

    for pdf_path in pdf_files:
        print(f"Convirtiendo: {pdf_path.name} ({options.output_format} @ {options.dpi} DPI)...")

        def on_progress(cur: int, total: int, out_file: Path) -> None:
            print(f"  [{cur}/{total}] -> {out_file.name}")

        result = convert_pdf_to_images(pdf_path, options, progress_cb=on_progress)
        print(
            f"Listo: {result.total_pages_converted} páginas en {result.elapsed_seconds:.2f}s "
            f"(carpeta: {result.output_dir})"
        )

    return 0


def main(argv: list[str] | None = None) -> int:
    raw_argv = list(sys.argv[1:] if argv is None else argv)

    if "--cli" in raw_argv or "-h" in raw_argv or "--help" in raw_argv:
        parser = argparse.ArgumentParser(
            prog="PDFaImagen",
            description="Conversor local de PDF a JPG o PNG de alta calidad.",
        )
        parser.add_argument("inputs", nargs="*", help="Archivos PDF o carpetas a convertir.")
        parser.add_argument("--cli", action="store_true", help="Ejecutar en modo consola sin ventana.")
        parser.add_argument(
            "-f",
            "--format",
            choices=["png", "jpg", "PNG", "JPG"],
            default="PNG",
            help="Formato de salida (PNG o JPG).",
        )
        parser.add_argument("--dpi", type=int, default=300, help="Resolución en DPI (36-1200). Defecto: 300.")
        parser.add_argument(
            "--quality",
            type=int,
            default=95,
            help="Calidad JPG (1-100). Defecto: 95.",
        )
        parser.add_argument(
            "--transparent",
            action="store_true",
            help="Fondo transparente (solo PNG).",
        )
        parser.add_argument(
            "--pages",
            default="",
            help="Rango de páginas, ej. '1-3, 5'. Vacío = todas.",
        )
        parser.add_argument(
            "-o",
            "--out",
            default=None,
            help="Carpeta de salida personalizada.",
        )
        parser.add_argument(
            "--no-subfolder",
            action="store_true",
            help="Guardar directamente en la carpeta de salida sin crear subcarpeta por PDF.",
        )
        parser.add_argument("--password", default=None, help="Contraseña si el PDF está protegido.")
        parsed = parser.parse_args(raw_argv)
        return _run_cli(parsed)

    from src.gui import launch_gui

    initial_paths = [Path(p) for p in raw_argv if Path(p).exists()]
    return launch_gui(initial_files=initial_paths)


if __name__ == "__main__":
    raise SystemExit(main())
