# Conversor PDF a Imagen (Windows - 100% Local)

Programa de escritorio para **Windows 10 / Windows 11** que convierte archivos **PDF a imágenes PNG o JPG de alta calidad**, funcionando **100% de forma local y sin conexión a internet**.

Diseñado para preservar al máximo la nitidez de texto, planos y gráficos sin depender de servicios en la nube ni de herramientas externas como Poppler.

---

## Características principales

- **100% local, privado y portátil**:
  - Todo el procesamiento se realiza en tu equipo usando **PyMuPDF** y **Pillow**.
  - Al usar el ejecutable compilado (`PDFaImagen.exe`), **el usuario final no necesita instalar Python ni tener internet**.
- **Calidad profesional**:
  - Resolución configurable: `150 DPI` (pantalla/web), `300 DPI` (alta / impresión, recomendado), `600 DPI` (ultra alta) o valor personalizado (`36–1200 DPI`).
  - **PNG** sin pérdida de calidad con opción de **fondo transparente** (`RGBA`).
  - **JPG** de alta calidad (`60–100%` en interfaz / `1–100%` por CLI, por defecto `95%`) con submuestreo cromático `4:4:4` (`subsampling=0`) para evitar bordes borrosos en texto.
  - Metadatos **DPI** incrustados en cada imagen generada.
- **Soporte para PDFs de muchas páginas**:
  - Renderiza **página por página** liberando memoria entre páginas y compactando la caché interna periódicamente, permitiendo convertir documentos extensos de cientos de páginas de forma estable.
  - Numeración ordenada con ceros a la izquierda (`_pag_001`, `_pag_002`, …, `_pag_1000`).
- **Interfaz cómoda e intuitiva**:
  - Arrastrar y soltar (**Drag & Drop**) archivos PDF o carpetas directamente sobre la ventana o sobre `PDFaImagen.exe`.
  - Conversión por lotes de múltiples PDFs y opción para **cancelar** de forma segura en cualquier momento.
  - Rango de páginas personalizado (por ejemplo: `1-3, 5` o vacío para todas).
  - Soporte para PDFs protegidos con contraseña.
  - Elección clara de destino: **En la misma carpeta del PDF** o **En una carpeta elegida por mí**, con opción de crear subcarpeta por cada PDF.
  - **Tooltips** de ayuda al pasar el cursor sobre cada botón y control.
- **Modo consola (CLI) incluido**: ideal para automatizaciones y scripts.

---

## Uso rápido (Ejecutable `.exe`)

1. Descarga o compila `PDFaImagen.exe` (ver sección de compilación).
2. Haz doble clic en `PDFaImagen.exe` (o arrastra uno o varios archivos PDF directamente encima del `.exe`).
3. Selecciona el formato (`PNG` o `JPG`), la resolución (`DPI`) y dónde guardar las imágenes.
4. Haz clic en **Convertir a Imágenes**.

---

## Uso desde código fuente (Desarrollo)

### Requisitos

- Windows 10 o Windows 11 (64 bits)
- Python 3.11 o superior

### Instalación de dependencias

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

### Abrir la interfaz gráfica

```powershell
.\.venv\Scripts\python.exe -m src.main
```

### Modo consola (CLI)

```powershell
# Convertir todas las páginas a JPG de 300 DPI y calidad 95%
.\.venv\Scripts\python.exe -m src.main --cli documento.pdf --format jpg --dpi 300 --quality 95

# Convertir páginas específicas a PNG con fondo transparente en una carpeta concreta
.\.venv\Scripts\python.exe -m src.main --cli documento.pdf --format png --dpi 300 --transparent --pages "1-3, 5" --out ".\salida"
```

Opciones disponibles en `--cli`:
- `-f, --format`: `png` o `jpg` (defecto: `PNG`)
- `--dpi`: resolución entre `36` y `1200` (defecto: `300`)
- `--quality`: calidad JPG de `1` a `100` (defecto: `95`)
- `--transparent`: fondo transparente (solo `PNG`)
- `--pages`: rango de páginas, ej. `"1-3, 5"` (vacío = todas)
- `-o, --out`: carpeta de salida personalizada
- `--no-subfolder`: guarda directamente en la carpeta destino sin crear subcarpeta por PDF
- `--password`: contraseña para PDFs cifrados

---

## Compilar ejecutable portátil (`.exe`)

```powershell
.\build_exe.ps1
```

El ejecutable independiente se generará en `dist\PDFaImagen.exe` con los metadatos de versión incluidos (`version_info.txt`).

---

## Pruebas automatizadas

```powershell
.\.venv\Scripts\python.exe -m pytest tests -v
```

---

## Estructura del proyecto

```text
pdf-to-image/
├── src/
│   ├── __init__.py       # Metadatos y versión
│   ├── converter.py      # Motor de conversión PDF -> PNG/JPG con PyMuPDF y Pillow
│   ├── gui.py            # Interfaz gráfica de escritorio (CustomTkinter + TkinterDnD2)
│   └── main.py           # Punto de entrada GUI y modo CLI
├── tests/
│   └── test_converter.py # Pruebas unitarias y de integración
├── build_exe.ps1         # Script de compilación con PyInstaller
├── version_info.txt      # Metadatos de propiedades para Windows (.exe)
├── pyproject.toml        # Configuración del proyecto y pytest
├── requirements.txt      # Dependencias
└── README.md
```

---

## Autor

**Ivan J. Ch. P.**  
GitHub: [https://github.com/ivanJossephChuctayaPaucar](https://github.com/ivanJossephChuctayaPaucar)  
Repositorio: [https://github.com/ivanJossephChuctayaPaucar/Pdf_Imagen](https://github.com/ivanJossephChuctayaPaucar/Pdf_Imagen)
