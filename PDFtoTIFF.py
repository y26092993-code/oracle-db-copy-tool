from __future__ import annotations

import argparse
import csv
import sys
import threading
from pathlib import Path
from queue import Queue
from typing import Callable, Iterable

import fitz  # PyMuPDF
from PIL import Image
from tkinter import StringVar, Tk, ttk
from tkinter import filedialog, messagebox


def parse_args(argv: Iterable[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="PDFの各ページを1ページのTIFFに変換します。"
    )
    parser.add_argument("pdf", type=Path, help="入力PDFのパス")
    parser.add_argument("output_dir", type=Path, help="出力フォルダ")
    parser.add_argument(
        "--dpi", type=int, default=300, help="DPI（既定: 300）"
    )
    parser.add_argument(
        "--bilevel",
        action="store_true",
        help="2値(1bit)でTIFFを出力",
    )
    parser.add_argument(
        "--threshold",
        type=int,
        default=128,
        help="2値化のしきい値（0-255, 既定: 128）",
    )
    parser.add_argument(
        "--prefix",
        type=str,
        default=None,
        help="出力ファイル名の先頭（既定: PDF名）",
    )
    parser.add_argument(
        "--compression",
        type=str,
        default="tiff_deflate",
        help="TIFFの圧縮方式（既定: tiff_deflate）",
    )
    return parser.parse_args(argv)


def ensure_output_dir(path: Path) -> None:
    if path.exists() and not path.is_dir():
        raise NotADirectoryError(f"Output path is not a directory: {path}")
    path.mkdir(parents=True, exist_ok=True)


def render_page_to_tiff(
    page: fitz.Page,
    output_path: Path,
    dpi: int,
    compression: str,
    bilevel: bool,
    threshold: int,
) -> None:
    zoom = dpi / 72.0
    matrix = fitz.Matrix(zoom, zoom)
    pix = page.get_pixmap(matrix=matrix, alpha=False)
    image = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
    if bilevel:
        image = image.convert("L").point(
            lambda x: 255 if x >= threshold else 0, mode="1"
        )
    image.save(output_path, format="TIFF", compression=compression)


def resolve_log_path(
    pdf_path: Path,
    output_dir: Path,
    prefix: str | None,
    log_path: Path | None,
) -> Path:
    if log_path is not None:
        return log_path
    name_prefix = prefix or pdf_path.stem
    return output_dir / f"{name_prefix}_log.csv"


def convert_pdf_to_tiff(
    pdf_path: Path,
    output_dir: Path,
    dpi: int,
    prefix: str | None,
    compression: str,
    bilevel: bool = False,
    threshold: int = 128,
    progress: Callable[[int, int], None] | None = None,
    log_path: Path | None = None,
) -> list[Path]:
    if not pdf_path.is_file():
        raise FileNotFoundError(f"PDF not found: {pdf_path}")

    ensure_output_dir(output_dir)
    name_prefix = prefix or pdf_path.stem
    log_file = resolve_log_path(pdf_path, output_dir, prefix, log_path)

    output_files: list[Path] = []
    with log_file.open("w", newline="", encoding="utf-8") as csv_file:
        writer = csv.writer(csv_file)
        writer.writerow(["page", "output_file", "status", "message"])

        with fitz.open(pdf_path) as doc:
            total_pages = len(doc)
            for index, page in enumerate(doc, start=1):
                output_path = output_dir / f"{name_prefix}_{index:04d}.tif"
                try:
                    render_page_to_tiff(
                        page,
                        output_path,
                        dpi,
                        compression,
                        bilevel,
                        threshold,
                    )
                except Exception as exc:  # noqa: BLE001 - log and raise
                    writer.writerow([index, str(output_path), "failed", str(exc)])
                    raise
                else:
                    output_files.append(output_path)
                    writer.writerow([index, str(output_path), "ok", ""])
                    if progress is not None:
                        progress(index, total_pages)

    return output_files


def run_gui() -> None:
    root = Tk()
    root.title("PDFをTIFFに変換")

    def attach_tooltip(widget: ttk.Widget, text: str) -> None:
        tooltip: dict[str, Tk] = {"window": None}

        def show_tooltip(_event: object) -> None:
            if tooltip["window"] is not None:
                return
            window = Tk()
            window.wm_overrideredirect(True)
            window.attributes("-topmost", True)
            x = widget.winfo_rootx() + 20
            y = widget.winfo_rooty() + 20
            window.geometry(f"+{x}+{y}")
            label = ttk.Label(
                window,
                text=text,
                padding=6,
                background="#ffffe0",
                relief="solid",
                borderwidth=1,
            )
            label.pack()
            tooltip["window"] = window

        def hide_tooltip(_event: object) -> None:
            if tooltip["window"] is None:
                return
            tooltip["window"].destroy()
            tooltip["window"] = None

        widget.bind("<Enter>", show_tooltip)
        widget.bind("<Leave>", hide_tooltip)

    pdf_var = StringVar()
    output_var = StringVar()
    dpi_var = StringVar(value="300")
    prefix_var = StringVar()
    compression_var = StringVar(value="tiff_deflate")
    bilevel_var = StringVar(value="off")
    threshold_var = StringVar(value="128")

    status_var = StringVar(value="待機中")

    main_frame = ttk.Frame(root, padding=12)
    main_frame.grid(row=0, column=0, sticky="nsew")

    root.columnconfigure(0, weight=1)
    root.rowconfigure(0, weight=1)
    main_frame.columnconfigure(0, weight=7)
    main_frame.columnconfigure(1, weight=5)

    left_frame = ttk.Frame(main_frame)
    right_frame = ttk.Frame(main_frame)
    left_frame.grid(row=0, column=0, sticky="nsew", padx=(0, 8))
    right_frame.grid(row=0, column=1, sticky="nsew", padx=(8, 0))

    left_frame.columnconfigure(1, weight=1)
    right_frame.columnconfigure(1, weight=1)

    ttk.Label(left_frame, text="PDF").grid(row=0, column=0, sticky="w")
    pdf_entry = ttk.Entry(left_frame, textvariable=pdf_var)
    pdf_entry.grid(row=0, column=1, sticky="ew", padx=6)
    ttk.Button(
        left_frame,
        text="参照",
        command=lambda: pdf_var.set(
            filedialog.askopenfilename(
                title="PDFを選択",
                filetypes=[("PDF", "*.pdf")],
            )
        ),
    ).grid(row=0, column=2, sticky="ew")

    ttk.Label(left_frame, text="出力フォルダ").grid(row=1, column=0, sticky="w")
    output_entry = ttk.Entry(left_frame, textvariable=output_var)
    output_entry.grid(row=1, column=1, sticky="ew", padx=6)
    ttk.Button(
        left_frame,
        text="参照",
        command=lambda: output_var.set(
            filedialog.askdirectory(title="出力フォルダを選択")
        ),
    ).grid(row=1, column=2, sticky="ew")

    ttk.Label(left_frame, text="DPI").grid(row=2, column=0, sticky="w")
    dpi_combo = ttk.Combobox(
        left_frame,
        textvariable=dpi_var,
        state="readonly",
        width=10,
        values=("150", "300", "600"),
    )
    dpi_combo.grid(row=2, column=1, sticky="w", padx=6)
    attach_tooltip(dpi_combo, "解像度です。150(高速) / 300(標準) / 600(高精細)")

    ttk.Label(left_frame, text="出力名の先頭(任意)").grid(
        row=3, column=0, sticky="w"
    )
    prefix_entry = ttk.Entry(left_frame, textvariable=prefix_var)
    prefix_entry.grid(row=3, column=1, sticky="ew", padx=6)
    attach_tooltip(prefix_entry, "空欄ならPDF名が使われます。例: caseA_0001.tif")

    ttk.Label(right_frame, text="圧縮方式").grid(row=0, column=0, sticky="w")
    compression_combo = ttk.Combobox(
        right_frame,
        textvariable=compression_var,
        state="readonly",
        width=16,
        values=("tiff_deflate", "lzw", "group4", "none"),
    )
    compression_combo.grid(row=0, column=1, sticky="w", padx=6)
    attach_tooltip(
        compression_combo,
        "tiff_deflate: 標準 / lzw: 互換性 / group4: 2値向け / none: 無圧縮",
    )
    ttk.Button(
        right_frame,
        text="詳細",
        command=lambda: messagebox.showinfo(
            "圧縮方式の詳細",
            "tiff_deflate: 標準の可逆圧縮。画質を保ちつつ容量を削減します。\n"
            "lzw: 可逆圧縮。古い環境との互換性が高い方式です。\n"
            "group4: 2値(1bit)の白黒画像向け高圧縮。文字文書に適します。\n"
            "none: 無圧縮。容量は大きいが処理は最速です。",
        ),
    ).grid(row=0, column=2, sticky="w")

    bilevel_check = ttk.Checkbutton(
        right_frame,
        text="2値化(1bit)",
        variable=bilevel_var,
        onvalue="on",
        offvalue="off",
    )
    bilevel_check.grid(row=1, column=0, sticky="w")
    attach_tooltip(
        bilevel_check,
        "2値化すると白黒(1bit)で保存します。文字主体の書類に適します。",
    )

    ttk.Label(right_frame, text="しきい値").grid(row=1, column=1, sticky="w")
    threshold_entry = ttk.Entry(right_frame, textvariable=threshold_var, width=10)
    threshold_entry.grid(row=1, column=2, sticky="w")
    attach_tooltip(threshold_entry, "0〜255。値が低いほど黒が増えます。")

    progress = ttk.Progressbar(main_frame, mode="determinate")
    progress.grid(row=1, column=0, columnspan=2, sticky="ew", pady=(8, 0))
    status_label = ttk.Label(main_frame, textvariable=status_var)
    status_label.grid(row=2, column=0, columnspan=2, sticky="w", pady=(6, 0))

    run_button = ttk.Button(main_frame, text="変換")
    run_button.grid(row=3, column=0, columnspan=2, pady=(10, 0))

    queue: Queue[tuple[str, int | str | None]] = Queue()

    def set_busy(is_busy: bool) -> None:
        state = "disabled" if is_busy else "normal"
        run_button.configure(state=state)
        pdf_entry.configure(state=state)
        output_entry.configure(state=state)

    def start_conversion() -> None:
        pdf_text = pdf_var.get().strip()
        output_text = output_var.get().strip()
        dpi_text = dpi_var.get().strip()
        threshold_text = threshold_var.get().strip()

        if not pdf_text:
            messagebox.showerror("エラー", "PDFファイルを選択してください。")
            return
        if not output_text:
            messagebox.showerror("エラー", "出力フォルダを選択してください。")
            return

        try:
            dpi_value = int(dpi_text)
        except ValueError:
            messagebox.showerror("エラー", "DPIは整数で指定してください。")
            return

        try:
            threshold_value = int(threshold_text)
        except ValueError:
            messagebox.showerror("エラー", "しきい値は整数で指定してください。")
            return

        if not 0 <= threshold_value <= 255:
            messagebox.showerror("エラー", "しきい値は0〜255で指定してください。")
            return

        bilevel_enabled = bilevel_var.get() == "on"
        compression_value = compression_var.get().strip() or "tiff_deflate"
        if bilevel_enabled and compression_value == "tiff_deflate":
            compression_value = "group4"

        set_busy(True)
        progress.configure(value=0, maximum=100)
        status_var.set("変換中...")

        log_path = resolve_log_path(
            Path(pdf_text),
            Path(output_text),
            prefix_var.get().strip() or None,
            None,
        )

        def progress_callback(current: int, total: int) -> None:
            queue.put(("progress", current * 100 // max(total, 1)))

        def worker() -> None:
            try:
                files = convert_pdf_to_tiff(
                    pdf_path=Path(pdf_text),
                    output_dir=Path(output_text),
                    dpi=dpi_value,
                    prefix=prefix_var.get().strip() or None,
                    compression=compression_value,
                    bilevel=bilevel_enabled,
                    threshold=threshold_value,
                    progress=progress_callback,
                    log_path=log_path,
                )
            except Exception as exc:  # noqa: BLE001 - show error to user
                queue.put(("error", f"{exc}\nLog: {log_path}"))
                return

            queue.put(("done", len(files)))

        threading.Thread(target=worker, daemon=True).start()

    def poll_queue() -> None:
        while not queue.empty():
            message, payload = queue.get()
            if message == "progress" and isinstance(payload, int):
                progress.configure(value=payload)
                status_var.set(f"変換中... {payload}%")
            elif message == "done" and isinstance(payload, int):
                progress.configure(value=100)
                status_var.set(
                    f"完了: {payload}ページ変換しました。ログ: {log_path}"
                )
                set_busy(False)
                messagebox.showinfo(
                    "完了",
                    f"{payload}ページの変換が完了しました。\nログ: {log_path}",
                )
            elif message == "error" and isinstance(payload, str):
                progress.configure(value=0)
                status_var.set("エラー")
                set_busy(False)
                messagebox.showerror("エラー", payload)

        root.after(200, poll_queue)

    run_button.configure(command=start_conversion)
    poll_queue()
    root.mainloop()


def main(argv: Iterable[str] | None = None) -> int:
    args_list = list(argv) if argv is not None else sys.argv[1:]
    if not args_list:
        run_gui()
        return 0

    args = parse_args(args_list)
    try:
        if not 0 <= args.threshold <= 255:
            raise ValueError("Threshold must be 0-255.")
        log_path = resolve_log_path(args.pdf, args.output_dir, args.prefix, None)
        output_files = convert_pdf_to_tiff(
            pdf_path=args.pdf,
            output_dir=args.output_dir,
            dpi=args.dpi,
            prefix=args.prefix,
            compression=args.compression,
            bilevel=args.bilevel,
            threshold=args.threshold,
            log_path=log_path,
        )
    except (FileNotFoundError, NotADirectoryError, RuntimeError, OSError, ValueError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    print(f"Converted {len(output_files)} pages to {args.output_dir}")
    print(f"Log file: {log_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
