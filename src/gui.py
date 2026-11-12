from __future__ import annotations

import os
import queue
import sys
import threading
import tkinter as tk
import webbrowser
from dataclasses import dataclass
from pathlib import Path
from tkinter import filedialog, messagebox, simpledialog
from typing import Any

import customtkinter as ctk

try:
    from tkinterdnd2 import DND_FILES, TkinterDnD

    HAS_DND = True
except Exception:
    DND_FILES = None
    TkinterDnD = None
    HAS_DND = False

from src import __author__, __github_url__, __version__
from src.converter import (
    ConversionOptions,
    ConversionResult,
    PdfInfo,
    convert_pdf_to_images,
    get_pdf_info,
    resolve_output_dir,
)


@dataclass
class QueueItem:
    path: Path
    info: PdfInfo
    password: str | None = None
    status: str = "Pendiente"
    last_output_dir: Path | None = None


def _enable_windows_dpi_awareness() -> None:
    if sys.platform != "win32":
        return
    try:
        import ctypes

        ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except Exception:
        pass


class _BaseWindow(ctk.CTk, TkinterDnD.DnDWrapper if HAS_DND else object):  # type: ignore[misc]
    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.dnd_enabled = False
        if HAS_DND and TkinterDnD is not None:
            try:
                self.TkdndVersion = TkinterDnD._require(self)
                self.dnd_enabled = True
            except Exception:
                self.dnd_enabled = False


class ToolTip:
    """Tooltip flotante compatible con widgets compuestos de CustomTkinter."""

    def __init__(self, widget: tk.Misc, text: str, delay_ms: int = 350) -> None:
        self.widget = widget
        self.text = text
        self.delay_ms = delay_ms
        self._after_id: str | None = None
        self._leave_id: str | None = None
        self._tip_window: tk.Toplevel | None = None
        self._bound_widgets: set[int] = set()
        self._bind_recursive(widget)

    def _bind_recursive(self, target: tk.Misc) -> None:
        wid = id(target)
        if wid in self._bound_widgets:
            return
        self._bound_widgets.add(wid)

        try:
            target.bind("<Enter>", self._on_enter, add="+")
            target.bind("<Leave>", self._on_leave, add="+")
            target.bind("<ButtonPress>", self._on_press, add="+")
        except Exception:
            pass

        for child in target.winfo_children():
            self._bind_recursive(child)

    def _on_enter(self, _event: tk.Event[Any] | None = None) -> None:
        # Re-vincula hijos por si CustomTkinter creó widgets internos después de __init__
        self._bind_recursive(self.widget)
        if self._leave_id is not None:
            try:
                self.widget.after_cancel(self._leave_id)
            except Exception:
                pass
            self._leave_id = None

        if self._tip_window is None and self._after_id is None:
            self._after_id = self.widget.after(self.delay_ms, self._show)

    def _on_leave(self, _event: tk.Event[Any] | None = None) -> None:
        if self._leave_id is not None:
            try:
                self.widget.after_cancel(self._leave_id)
            except Exception:
                pass
        self._leave_id = self.widget.after(40, self._check_pointer_and_hide)

    def _on_press(self, _event: tk.Event[Any] | None = None) -> None:
        self._cancel_pending()
        self._hide()

    def _check_pointer_and_hide(self) -> None:
        self._leave_id = None
        try:
            if not self.widget.winfo_exists():
                self._cancel_pending()
                self._hide()
                return
            px, py = self.widget.winfo_pointerxy()
            rx = self.widget.winfo_rootx()
            ry = self.widget.winfo_rooty()
            rw = self.widget.winfo_width()
            rh = self.widget.winfo_height()
            if rx <= px <= rx + rw and ry <= py <= ry + rh:
                return
        except Exception:
            pass
        self._cancel_pending()
        self._hide()

    def _cancel_pending(self) -> None:
        if self._after_id is not None:
            try:
                self.widget.after_cancel(self._after_id)
            except Exception:
                pass
            self._after_id = None

    def _show(self) -> None:
        self._after_id = None
        if self._tip_window is not None:
            return
        try:
            if not self.widget.winfo_exists() or not self.widget.winfo_viewable():
                return
        except Exception:
            return

        is_dark = ctk.get_appearance_mode() == "Dark"
        bg = "#2b303b" if is_dark else "#fffff2"
        fg = "#f2f4f8" if is_dark else "#1f2328"
        border = "#4a5366" if is_dark else "#c8c8b8"

        tip = tk.Toplevel(self.widget)
        tip.wm_overrideredirect(True)
        try:
            tip.wm_attributes("-topmost", True)
        except Exception:
            pass

        frame = tk.Frame(tip, bg=border, bd=1)
        frame.pack(fill="both", expand=True)

        label = tk.Label(
            frame,
            text=self.text,
            justify="left",
            wraplength=290,
            bg=bg,
            fg=fg,
            font=("Segoe UI", 9),
            padx=9,
            pady=6,
        )
        label.pack(fill="both", expand=True)

        tip.update_idletasks()
        tip_w = tip.winfo_reqwidth()
        tip_h = tip.winfo_reqheight()

        px, py = self.widget.winfo_pointerxy()
        screen_w = self.widget.winfo_screenwidth()
        screen_h = self.widget.winfo_screenheight()

        x = min(px + 14, max(8, screen_w - tip_w - 12))
        y = py + 20
        if y + tip_h > screen_h - 12:
            y = max(8, py - tip_h - 14)

        tip.wm_geometry(f"+{x}+{y}")
        self._tip_window = tip

    def _hide(self) -> None:
        if self._tip_window is not None:
            try:
                self._tip_window.destroy()
            except Exception:
                pass
            self._tip_window = None


class PdfConverterApp(_BaseWindow):
    def __init__(self, initial_files: list[Path] | None = None) -> None:
        super().__init__()

        ctk.set_appearance_mode("System")
        ctk.set_default_color_theme("blue")

        self.title("Conversor PDF a Imagen (Alta Calidad - Local)")
        screen_h = self.winfo_screenheight()
        target_h = min(840, max(660, screen_h - 90))
        self.geometry(f"960x{target_h}")
        self.minsize(820, 620)

        self.items: list[QueueItem] = []
        self._tooltips: list[ToolTip] = []
        self.ui_queue: queue.Queue[tuple[str, Any]] = queue.Queue()
        self.cancel_event = threading.Event()
        self.worker_thread: threading.Thread | None = None
        self.last_opened_dir: Path | None = None

        self._build_ui()
        self._bind_dnd()

        if initial_files:
            self.after_idle(lambda: self.add_paths(initial_files))

        self.after(100, self._process_ui_queue)
        self.protocol("WM_DELETE_WINDOW", self._on_close)

    def _build_ui(self) -> None:
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)

        # Encabezado
        header = ctk.CTkFrame(self, corner_radius=10)
        header.grid(row=0, column=0, padx=16, pady=(14, 8), sticky="ew")
        header.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            header,
            text="Conversor PDF a JPG / PNG",
            font=ctk.CTkFont(size=20, weight="bold"),
        ).grid(row=0, column=0, padx=16, pady=(10, 2), sticky="w")

        ctk.CTkLabel(
            header,
            text="100% local y sin conexión • Renderizado de alta precisión sin pérdida de nitidez",
            font=ctk.CTkFont(size=12),
            text_color=("gray35", "gray70"),
        ).grid(row=1, column=0, padx=16, pady=(0, 10), sticky="w")

        # Contenido principal: lista de archivos + configuración
        main_pane = ctk.CTkFrame(self, fg_color="transparent")
        main_pane.grid(row=1, column=0, padx=16, pady=4, sticky="nsew")
        main_pane.grid_columnconfigure(0, weight=3)
        main_pane.grid_columnconfigure(1, weight=2)
        main_pane.grid_rowconfigure(0, weight=1)

        # Panel izquierdo: Archivos PDF
        files_frame = ctk.CTkFrame(main_pane, corner_radius=10)
        files_frame.grid(row=0, column=0, padx=(0, 8), pady=0, sticky="nsew")
        files_frame.grid_columnconfigure(0, weight=1)
        files_frame.grid_rowconfigure(2, weight=1)

        files_top = ctk.CTkFrame(files_frame, fg_color="transparent")
        files_top.grid(row=0, column=0, padx=12, pady=(12, 6), sticky="ew")
        files_top.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            files_top,
            text="Archivos PDF",
            font=ctk.CTkFont(size=15, weight="bold"),
        ).grid(row=0, column=0, sticky="w")

        btn_row = ctk.CTkFrame(files_frame, fg_color="transparent")
        btn_row.grid(row=1, column=0, padx=12, pady=(0, 8), sticky="ew")

        self.btn_add_files = ctk.CTkButton(
            btn_row, text="+ Agregar PDF(s)", width=130, command=self._pick_files
        )
        self.btn_add_files.pack(side="left", padx=(0, 6))

        self.btn_add_folder = ctk.CTkButton(
            btn_row,
            text="+ Carpeta",
            width=95,
            fg_color=("gray75", "gray30"),
            text_color=("gray10", "gray95"),
            hover_color=("gray65", "gray40"),
            command=self._pick_folder,
        )
        self.btn_add_folder.pack(side="left", padx=(0, 6))

        self.btn_remove = ctk.CTkButton(
            btn_row,
            text="Quitar",
            width=75,
            fg_color=("gray75", "gray30"),
            text_color=("gray10", "gray95"),
            hover_color=("gray65", "gray40"),
            command=self._remove_selected,
        )
        self.btn_remove.pack(side="left", padx=(0, 6))

        self.btn_clear = ctk.CTkButton(
            btn_row,
            text="Limpiar",
            width=75,
            fg_color=("gray75", "gray30"),
            text_color=("gray10", "gray95"),
            hover_color=("gray65", "gray40"),
            command=self._clear_files,
        )
        self.btn_clear.pack(side="left")

        # Listbox clásico dentro de contenedor estilizado para selección múltiple rápida
        list_container = ctk.CTkFrame(files_frame, corner_radius=8)
        list_container.grid(row=2, column=0, padx=12, pady=(0, 8), sticky="nsew")
        list_container.grid_columnconfigure(0, weight=1)
        list_container.grid_rowconfigure(0, weight=1)

        self.file_listbox = tk.Listbox(
            list_container,
            selectmode=tk.EXTENDED,
            activestyle="none",
            borderwidth=0,
            highlightthickness=0,
            font=("Segoe UI", 10),
            bg="#1e222a" if ctk.get_appearance_mode() == "Dark" else "#f5f6f8",
            fg="#e6e9ef" if ctk.get_appearance_mode() == "Dark" else "#1f2328",
            selectbackground="#1f6aa5",
            selectforeground="#ffffff",
        )
        self.file_listbox.grid(row=0, column=0, padx=6, pady=6, sticky="nsew")

        scrollbar = ctk.CTkScrollbar(list_container, command=self.file_listbox.yview)
        scrollbar.grid(row=0, column=1, padx=(0, 4), pady=6, sticky="ns")
        self.file_listbox.configure(yscrollcommand=scrollbar.set)

        dnd_hint = (
            "Tip: Puedes arrastrar y soltar archivos PDF o carpetas aquí."
            if self.dnd_enabled
            else "Usa '+ Agregar PDF(s)' para seleccionar uno o varios documentos."
        )
        self.drop_hint_label = ctk.CTkLabel(
            files_frame,
            text=dnd_hint,
            font=ctk.CTkFont(size=11),
            text_color=("gray40", "gray65"),
        )
        self.drop_hint_label.grid(row=3, column=0, padx=12, pady=(0, 10), sticky="w")

        # Panel derecho: Opciones de calidad y salida (con scroll automático si la pantalla es pequeña)
        opts_frame = ctk.CTkScrollableFrame(main_pane, corner_radius=10)
        opts_frame.grid(row=0, column=1, padx=(8, 0), pady=0, sticky="nsew")
        opts_frame.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            opts_frame,
            text="Opciones de Calidad",
            font=ctk.CTkFont(size=15, weight="bold"),
        ).grid(row=0, column=0, padx=10, pady=(6, 8), sticky="w")

        # Formato
        ctk.CTkLabel(opts_frame, text="Formato de salida:").grid(
            row=1, column=0, padx=10, pady=(0, 3), sticky="w"
        )
        self.format_var = ctk.StringVar(value="PNG")
        self.format_seg = ctk.CTkSegmentedButton(
            opts_frame,
            values=["PNG", "JPG"],
            variable=self.format_var,
            command=self._on_format_change,
        )
        self.format_seg.grid(row=2, column=0, padx=10, pady=(0, 8), sticky="ew")

        # Resolución DPI
        ctk.CTkLabel(opts_frame, text="Resolución (DPI):").grid(
            row=3, column=0, padx=10, pady=(0, 3), sticky="w"
        )
        self.dpi_preset_var = ctk.StringVar(value="300 DPI (Alta - Recomendado)")
        self.dpi_menu = ctk.CTkOptionMenu(
            opts_frame,
            values=[
                "150 DPI (Pantalla / Web)",
                "300 DPI (Alta - Recomendado)",
                "600 DPI (Ultra Alta / Impresión)",
                "Personalizado",
            ],
            variable=self.dpi_preset_var,
            command=self._on_dpi_preset_change,
        )
        self.dpi_menu.grid(row=4, column=0, padx=10, pady=(0, 5), sticky="ew")

        dpi_custom_row = ctk.CTkFrame(opts_frame, fg_color="transparent")
        dpi_custom_row.grid(row=5, column=0, padx=10, pady=(0, 8), sticky="ew")
        dpi_custom_row.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(dpi_custom_row, text="DPI exacto:").grid(
            row=0, column=0, padx=(0, 8), sticky="w"
        )
        self.dpi_entry = ctk.CTkEntry(dpi_custom_row, width=90)
        self.dpi_entry.insert(0, "300")
        self.dpi_entry.configure(state="disabled")
        self.dpi_entry.grid(row=0, column=1, sticky="w")

        # Calidad JPG
        self.jpg_label = ctk.CTkLabel(opts_frame, text="Calidad JPG: 95% (4:4:4 Máx. nitidez)")
        self.jpg_label.grid(row=6, column=0, padx=10, pady=(0, 2), sticky="w")

        self.jpg_slider = ctk.CTkSlider(
            opts_frame,
            from_=60,
            to=100,
            number_of_steps=40,
            command=self._on_jpg_slider,
        )
        self.jpg_slider.set(95)
        self.jpg_slider.grid(row=7, column=0, padx=10, pady=(0, 8), sticky="ew")

        # Fondo transparente (PNG)
        self.transparent_var = ctk.BooleanVar(value=False)
        self.transparent_switch = ctk.CTkSwitch(
            opts_frame,
            text="Fondo transparente (solo PNG)",
            variable=self.transparent_var,
        )
        self.transparent_switch.grid(row=8, column=0, padx=10, pady=(0, 8), sticky="w")

        # Rango de páginas
        ctk.CTkLabel(
            opts_frame, text="Páginas (opcional, ej. 1-3, 5; vacío = todas):"
        ).grid(row=9, column=0, padx=10, pady=(0, 3), sticky="w")
        self.pages_entry = ctk.CTkEntry(opts_frame, placeholder_text="Todas las páginas")
        self.pages_entry.grid(row=10, column=0, padx=10, pady=(0, 10), sticky="ew")

        # Carpeta de salida
        ctk.CTkLabel(
            opts_frame,
            text="Dónde guardar las imágenes:",
            font=ctk.CTkFont(weight="bold"),
        ).grid(row=11, column=0, padx=10, pady=(0, 4), sticky="w")

        self.output_mode_var = ctk.StringVar(value="same")
        self.radio_same_dir = ctk.CTkRadioButton(
            opts_frame,
            text="En la misma carpeta del PDF",
            variable=self.output_mode_var,
            value="same",
            command=self._on_output_mode_change,
        )
        self.radio_same_dir.grid(row=12, column=0, padx=10, pady=(0, 4), sticky="w")

        self.radio_custom_dir = ctk.CTkRadioButton(
            opts_frame,
            text="En una carpeta elegida por mí",
            variable=self.output_mode_var,
            value="custom",
            command=self._on_output_mode_change,
        )
        self.radio_custom_dir.grid(row=13, column=0, padx=10, pady=(0, 6), sticky="w")

        out_dir_row = ctk.CTkFrame(opts_frame, fg_color="transparent")
        out_dir_row.grid(row=14, column=0, padx=10, pady=(0, 6), sticky="ew")
        out_dir_row.grid_columnconfigure(0, weight=1)

        self.out_dir_entry = ctk.CTkEntry(
            out_dir_row, placeholder_text="Selecciona una carpeta de destino..."
        )
        self.out_dir_entry.configure(state="disabled")
        self.out_dir_entry.grid(row=0, column=0, padx=(0, 6), sticky="ew")

        self.btn_browse_out = ctk.CTkButton(
            out_dir_row,
            text="Elegir...",
            width=76,
            state="disabled",
            command=self._pick_output_dir,
        )
        self.btn_browse_out.grid(row=0, column=1)

        self.subfolder_var = ctk.BooleanVar(value=True)
        self.subfolder_check = ctk.CTkCheckBox(
            opts_frame,
            text="Crear subcarpeta por cada PDF",
            variable=self.subfolder_var,
        )
        self.subfolder_check.grid(row=15, column=0, padx=10, pady=(2, 10), sticky="w")

        # Pie: Progreso y botones de acción
        footer = ctk.CTkFrame(self, corner_radius=10)
        footer.grid(row=2, column=0, padx=16, pady=(8, 4), sticky="ew")
        footer.grid_columnconfigure(0, weight=1)

        self.status_label = ctk.CTkLabel(
            footer,
            text="Listo. Agrega uno o varios archivos PDF para comenzar.",
            anchor="w",
        )
        self.status_label.grid(row=0, column=0, padx=14, pady=(10, 4), sticky="ew")

        self.progress_bar = ctk.CTkProgressBar(footer)
        self.progress_bar.set(0)
        self.progress_bar.grid(row=1, column=0, padx=14, pady=(0, 10), sticky="ew")

        action_row = ctk.CTkFrame(footer, fg_color="transparent")
        action_row.grid(row=2, column=0, padx=14, pady=(0, 12), sticky="ew")
        action_row.grid_columnconfigure(0, weight=1)

        self.btn_open_out = ctk.CTkButton(
            action_row,
            text="Abrir carpeta de salida",
            state="disabled",
            fg_color=("gray75", "gray30"),
            text_color=("gray10", "gray95"),
            hover_color=("gray65", "gray40"),
            command=self._open_last_output,
        )
        self.btn_open_out.pack(side="left")

        self.btn_convert = ctk.CTkButton(
            action_row,
            text="Convertir a Imágenes",
            height=38,
            width=190,
            font=ctk.CTkFont(size=14, weight="bold"),
            command=self._start_conversion,
        )
        self.btn_convert.pack(side="right")

        self.btn_cancel = ctk.CTkButton(
            action_row,
            text="Cancelar",
            height=38,
            width=100,
            fg_color="#b53333",
            hover_color="#8e2424",
            state="disabled",
            command=self._cancel_conversion,
        )
        self.btn_cancel.pack(side="right", padx=(0, 8))

        # Marca sutil inferior estilo Windows (autor y repositorio GitHub)
        credits_bar = ctk.CTkFrame(self, fg_color="transparent", height=22)
        credits_bar.grid(row=3, column=0, padx=20, pady=(0, 8), sticky="ew")
        credits_bar.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            credits_bar,
            text=f"v{__version__}  •  © 2026 {__author__}",
            font=ctk.CTkFont(size=11),
            text_color=("gray45", "gray60"),
        ).grid(row=0, column=0, sticky="w")

        self.github_link = ctk.CTkLabel(
            credits_bar,
            text=__github_url__.replace("https://", ""),
            font=ctk.CTkFont(size=11, underline=True),
            text_color=("#2b5b84", "#6fa8dc"),
            cursor="hand2",
        )
        self.github_link.grid(row=0, column=1, sticky="e")
        self.github_link.bind("<Button-1>", lambda _e: webbrowser.open(__github_url__))

        self._on_format_change(self.format_var.get())
        self._register_tooltips()

    def _add_tooltip(self, widget: tk.Misc, text: str) -> None:
        self._tooltips.append(ToolTip(widget, text))

    def _register_tooltips(self) -> None:
        self._add_tooltip(
            self.btn_add_files,
            "Selecciona uno o varios archivos PDF desde tu equipo para agregarlos a la lista.",
        )
        self._add_tooltip(
            self.btn_add_folder,
            "Busca y agrega automáticamente todos los archivos PDF dentro de una carpeta.",
        )
        self._add_tooltip(
            self.btn_remove,
            "Quita de la lista únicamente los archivos que tengas seleccionados.",
        )
        self._add_tooltip(
            self.btn_clear,
            "Limpia por completo la lista de archivos pendientes.",
        )
        self._add_tooltip(
            self.format_seg,
            "Elige el formato de salida:\n• PNG: sin pérdida (ideal para texto y gráficos).\n• JPG: archivo más ligero en alta calidad.",
        )
        self._add_tooltip(
            self.dpi_menu,
            "Define la resolución de salida (DPI). 300 DPI es ideal para lectura nítida e impresión.",
        )
        self._add_tooltip(
            self.dpi_entry,
            "DPI personalizado entre 36 y 1200 (activo al elegir 'Personalizado').",
        )
        self._add_tooltip(
            self.jpg_slider,
            "Ajusta la calidad de compresión JPG (60% a 100%). 95% mantiene máxima nitidez.",
        )
        self._add_tooltip(
            self.transparent_switch,
            "Exporta el fondo de la página como transparente en lugar de blanco (solo en formato PNG).",
        )
        self._add_tooltip(
            self.pages_entry,
            "Indica páginas específicas, ej: 1-3, 5.\nSi lo dejas vacío, se convertirán todas las páginas.",
        )
        self._add_tooltip(
            self.radio_same_dir,
            "Guarda las imágenes en la misma ubicación donde está cada archivo PDF original.",
        )
        self._add_tooltip(
            self.radio_custom_dir,
            "Guarda todas las imágenes dentro de la carpeta que tú elijas abajo.",
        )
        self._add_tooltip(
            self.btn_browse_out,
            "Abre el explorador de Windows para elegir la carpeta donde se guardarán las imágenes.",
        )
        self._add_tooltip(
            self.subfolder_check,
            "Si está activado, crea una subcarpeta con el nombre de cada PDF (ej. 'documento_imagenes').",
        )
        self._add_tooltip(
            self.btn_open_out,
            "Abre en el Explorador de Windows la carpeta donde se guardaron las imágenes.",
        )
        self._add_tooltip(
            self.btn_cancel,
            "Detiene el proceso de conversión de forma segura al terminar la página actual.",
        )
        self._add_tooltip(
            self.btn_convert,
            "Inicia la conversión local de todos los PDFs de la lista con la calidad elegida.",
        )
        self._add_tooltip(
            self.github_link,
            f"Abrir el perfil de GitHub de {__author__} en tu navegador.",
        )

    def _bind_dnd(self) -> None:
        if not self.dnd_enabled or DND_FILES is None:
            return
        try:
            self.drop_target_register(DND_FILES)  # type: ignore[attr-defined]
            self.dnd_bind("<<Drop>>", self._on_drop)  # type: ignore[attr-defined]
        except Exception:
            pass

    def _on_drop(self, event: Any) -> None:
        if self._is_running():
            return
        raw_paths = self.tk.splitlist(event.data)
        paths = [Path(p) for p in raw_paths]
        self.add_paths(paths)

    def _on_format_change(self, value: str) -> None:
        is_jpg = value.upper() == "JPG"
        if is_jpg:
            self.jpg_slider.configure(state="normal")
            self.jpg_label.configure(text_color=("gray10", "gray90"))
            self.transparent_switch.configure(state="disabled")
        else:
            self.jpg_slider.configure(state="disabled")
            self.jpg_label.configure(text_color=("gray50", "gray50"))
            self.transparent_switch.configure(state="normal")

    def _on_dpi_preset_change(self, choice: str) -> None:
        if choice.startswith("150"):
            self._set_dpi_entry("150", editable=False)
        elif choice.startswith("300"):
            self._set_dpi_entry("300", editable=False)
        elif choice.startswith("600"):
            self._set_dpi_entry("600", editable=False)
        else:
            self.dpi_entry.configure(state="normal")
            self.dpi_entry.focus_set()

    def _set_dpi_entry(self, value: str, editable: bool) -> None:
        self.dpi_entry.configure(state="normal")
        self.dpi_entry.delete(0, tk.END)
        self.dpi_entry.insert(0, value)
        if not editable:
            self.dpi_entry.configure(state="disabled")

    def _on_jpg_slider(self, value: float) -> None:
        q = int(round(value))
        self.jpg_label.configure(text=f"Calidad JPG: {q}% (4:4:4 Máx. nitidez)")

    def _on_output_mode_change(self) -> None:
        use_same = self.output_mode_var.get() == "same"
        state = "disabled" if use_same else "normal"
        self.out_dir_entry.configure(state=state)
        self.btn_browse_out.configure(state=state)
        if not use_same and not self.out_dir_entry.get().strip():
            self._pick_output_dir()

    def _pick_files(self) -> None:
        files = filedialog.askopenfilenames(
            title="Seleccionar archivos PDF",
            filetypes=[("Documentos PDF", "*.pdf"), ("Todos los archivos", "*.*")],
        )
        if files:
            self.add_paths([Path(f) for f in files])

    def _pick_folder(self) -> None:
        folder = filedialog.askdirectory(title="Seleccionar carpeta con PDFs")
        if folder:
            self.add_paths([Path(folder)])

    def _pick_output_dir(self) -> None:
        folder = filedialog.askdirectory(title="Seleccionar carpeta de salida")
        if folder:
            self.out_dir_entry.configure(state="normal")
            self.out_dir_entry.delete(0, tk.END)
            self.out_dir_entry.insert(0, folder)

    def add_paths(self, paths: list[Path]) -> None:
        existing = {item.path.resolve() for item in self.items}
        pdf_candidates: list[Path] = []

        for p in paths:
            if p.is_dir():
                pdf_candidates.extend(sorted(p.glob("*.pdf")))
            elif p.is_file() and p.suffix.lower() == ".pdf":
                pdf_candidates.append(p)

        added = 0
        for pdf in pdf_candidates:
            resolved = pdf.resolve()
            if resolved in existing:
                continue
            try:
                info = get_pdf_info(resolved)
            except Exception as exc:
                messagebox.showerror(
                    "Error al leer PDF",
                    f"No se pudo abrir '{pdf.name}':\n{exc}",
                )
                continue

            password: str | None = None
            if info.needs_password:
                password = simpledialog.askstring(
                    "PDF protegido",
                    f"Ingresa la contraseña para '{pdf.name}':",
                    show="*",
                    parent=self,
                )
                if password is None:
                    continue
                try:
                    import pymupdf

                    with pymupdf.open(resolved) as doc:
                        if not doc.authenticate(password):
                            messagebox.showerror(
                                "Contraseña incorrecta",
                                f"La contraseña ingresada para '{pdf.name}' no es válida.",
                            )
                            continue
                        info = PdfInfo(path=resolved, page_count=doc.page_count, needs_password=True)
                except Exception as exc:
                    messagebox.showerror("Error", str(exc))
                    continue

            self.items.append(QueueItem(path=resolved, info=info, password=password))
            existing.add(resolved)
            added += 1

        self._refresh_listbox()
        if added > 0:
            self.status_label.configure(
                text=f"{len(self.items)} archivo(s) en cola listos para convertir."
            )

    def _remove_selected(self) -> None:
        indices = list(self.file_listbox.curselection())
        if not indices:
            return
        for idx in reversed(indices):
            del self.items[idx]
        self._refresh_listbox()

    def _clear_files(self) -> None:
        self.items.clear()
        self._refresh_listbox()
        self.progress_bar.set(0)
        self.status_label.configure(text="Lista vacía. Agrega archivos PDF para convertir.")

    def _refresh_listbox(self) -> None:
        self.file_listbox.delete(0, tk.END)
        for item in self.items:
            pages_txt = f"{item.info.page_count} pág." if item.info.page_count else "? pág."
            self.file_listbox.insert(
                tk.END, f" {item.path.name}   [{pages_txt}]   —   {item.status}"
            )

    def _read_options(self) -> ConversionOptions:
        try:
            dpi = int(self.dpi_entry.get().strip())
        except ValueError as exc:
            raise ValueError("El valor de DPI debe ser un número entero (ej. 300).") from exc

        output_dir: Path | None = None
        if self.output_mode_var.get() != "same":
            raw_dir = self.out_dir_entry.get().strip()
            if not raw_dir:
                raise ValueError("Elige una carpeta de salida personalizada.")
            output_dir = Path(raw_dir)

        fmt = "PNG" if self.format_var.get().upper() == "PNG" else "JPG"
        options = ConversionOptions(
            output_format=fmt,
            dpi=dpi,
            jpg_quality=int(round(self.jpg_slider.get())),
            transparent_png=bool(self.transparent_var.get()),
            page_range=self.pages_entry.get().strip(),
            output_dir=output_dir,
            create_subfolder=bool(self.subfolder_var.get()),
        )
        options.validate()
        return options

    def _is_running(self) -> bool:
        return self.worker_thread is not None and self.worker_thread.is_alive()

    def _set_controls_running(self, running: bool) -> None:
        state = "disabled" if running else "normal"
        self.btn_add_files.configure(state=state)
        self.btn_add_folder.configure(state=state)
        self.btn_remove.configure(state=state)
        self.btn_clear.configure(state=state)
        self.btn_convert.configure(state=state)
        self.btn_cancel.configure(state="normal" if running else "disabled")

    def _start_conversion(self) -> None:
        if not self.items:
            messagebox.showinfo("Sin archivos", "Agrega al menos un archivo PDF primero.")
            return

        try:
            options = self._read_options()
        except ValueError as exc:
            messagebox.showerror("Configuración inválida", str(exc))
            return

        if options.dpi >= 600:
            confirm = messagebox.askyesno(
                "Resolución muy alta",
                f"Seleccionaste {options.dpi} DPI. Esto genera imágenes muy grandes y puede tardar más.\n\n¿Deseas continuar?",
            )
            if not confirm:
                return

        self.cancel_event.clear()
        for item in self.items:
            item.status = "En espera"
        self._refresh_listbox()
        self.progress_bar.set(0)
        self._set_controls_running(True)

        snapshot = list(self.items)
        self.worker_thread = threading.Thread(
            target=self._run_worker,
            args=(snapshot, options),
            daemon=True,
        )
        self.worker_thread.start()

    def _cancel_conversion(self) -> None:
        self.cancel_event.set()
        self.status_label.configure(text="Cancelando después de la página actual...")

    def _run_worker(self, items: list[QueueItem], base_options: ConversionOptions) -> None:
        total_files = len(items)
        completed_pages = 0
        last_dir: Path | None = None

        for file_idx, item in enumerate(items):
            if self.cancel_event.is_set():
                break

            self.ui_queue.put(("file_status", (file_idx, "Convirtiendo...")))

            file_options = ConversionOptions(
                output_format=base_options.output_format,
                dpi=base_options.dpi,
                jpg_quality=base_options.jpg_quality,
                transparent_png=base_options.transparent_png,
                page_range=base_options.page_range,
                output_dir=base_options.output_dir,
                create_subfolder=base_options.create_subfolder,
                password=item.password,
            )

            def on_page(cur_page: int, total_pages: int, out_path: Path) -> None:
                file_fraction = cur_page / max(1, total_pages)
                overall = (file_idx + file_fraction) / total_files
                self.ui_queue.put(
                    (
                        "progress",
                        (
                            overall,
                            f"[{file_idx + 1}/{total_files}] {item.path.name} — página {cur_page}/{total_pages}",
                        ),
                    )
                )

            try:
                result: ConversionResult = convert_pdf_to_images(
                    item.path,
                    file_options,
                    progress_cb=on_page,
                    cancel_event=self.cancel_event,
                )
                last_dir = result.output_dir
                completed_pages += result.total_pages_converted
                if result.cancelled:
                    self.ui_queue.put(("file_status", (file_idx, "Cancelado")))
                else:
                    self.ui_queue.put(
                        (
                            "file_status",
                            (
                                file_idx,
                                f"Listo ({result.total_pages_converted} págs en {result.elapsed_seconds:.1f}s)",
                            ),
                        )
                    )
            except Exception as exc:
                self.ui_queue.put(("file_status", (file_idx, f"Error: {exc}")))
                self.ui_queue.put(
                    ("error", f"Error al convertir '{item.path.name}':\n{exc}")
                )

        if last_dir is None and items:
            last_dir = resolve_output_dir(items[0].path, base_options)

        self.ui_queue.put(
            (
                "done",
                (self.cancel_event.is_set(), completed_pages, last_dir),
            )
        )

    def _process_ui_queue(self) -> None:
        try:
            while True:
                kind, payload = self.ui_queue.get_nowait()
                if kind == "file_status":
                    idx, status = payload
                    if 0 <= idx < len(self.items):
                        self.items[idx].status = status
                        self._refresh_listbox()
                elif kind == "progress":
                    fraction, text = payload
                    self.progress_bar.set(fraction)
                    self.status_label.configure(text=text)
                elif kind == "error":
                    messagebox.showerror("Error de conversión", payload)
                elif kind == "done":
                    cancelled, total_pages, last_dir = payload
                    self._set_controls_running(False)
                    if last_dir is not None and last_dir.exists():
                        self.last_opened_dir = last_dir
                        self.btn_open_out.configure(state="normal")

                    if cancelled:
                        self.status_label.configure(
                            text=f"Conversión cancelada. Se guardaron {total_pages} imagen(es)."
                        )
                    else:
                        self.progress_bar.set(1.0)
                        self.status_label.configure(
                            text=f"¡Completado! Se generaron {total_pages} imagen(es) en alta calidad."
                        )
        except queue.Empty:
            pass
        finally:
            self.after(80, self._process_ui_queue)

    def _open_last_output(self) -> None:
        if self.last_opened_dir and self.last_opened_dir.exists():
            os.startfile(str(self.last_opened_dir))  # type: ignore[attr-defined]

    def _on_close(self) -> None:
        if self._is_running():
            if not messagebox.askyesno(
                "Conversión en curso",
                "Hay una conversión en progreso. ¿Deseas cancelarla y salir?",
            ):
                return
            self.cancel_event.set()
        self.destroy()


def launch_gui(initial_files: list[Path] | None = None) -> int:
    _enable_windows_dpi_awareness()
    app = PdfConverterApp(initial_files=initial_files)
    app.mainloop()
    return 0
