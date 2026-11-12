# Conversor PDF a Imagen (Windows - 100% Local)

Aplicación de escritorio para Windows que convierte documentos PDF a **PNG** o **JPG** en alta calidad, de forma completamente local y sin conexión a internet.

## Características

- **100% local y privado**: Todo el procesamiento ocurre en tu PC mediante PyMuPDF y Pillow (sin subir archivos ni instalar Poppler por separado).
- **Alta calidad**:
  - Resolución configurable: `150 DPI`, `300 DPI` (recomendado), `600 DPI` o personalizado (`36–1200 DPI`).
  - **PNG** sin pérdida con opción de **fondo transparente**.
  - **JPG** de alta calidad (`1–100%`, por defecto `95%`) con submuestreo cromático `4:4:4` para conservar máxima nitidez en texto y gráficos.
  - Metadatos DPI incrustados en cada imagen generada.
- **Lotes y Drag & Drop**: Arrastra varios archivos PDF o carpetas directamente sobre la ventana (o sobre `PDFaImagen.exe`).
- **Rango de páginas**: Convierte todo el documento o páginas específicas (ej. `1-3, 5`).
- **PDFs protegidos**: Solicita contraseña si el archivo está cifrado.
- **Modo CLI opcional**: Soporta conversión por consola mediante `--cli`.

## Ejecutar desde código fuente

```powershell
.\.venv\Scripts\python.exe -m src.main
```

### Modo CLI

```powershell
.\.venv\Scripts\python.exe -m src.main --cli documento.pdf --format jpg --dpi 300 --quality 95
```

## Generar ejecutable `.exe`

```powershell
.\build_exe.ps1
```

El ejecutable portátil quedará en `dist\PDFaImagen.exe`.

## Pruebas

```powershell
.\.venv\Scripts\python.exe -m pytest tests -v
```

## Autor

**Ivan J. Ch. P.** — [https://github.com/ivanJossephChuctayaPaucar](https://github.com/ivanJossephChuctayaPaucar)
