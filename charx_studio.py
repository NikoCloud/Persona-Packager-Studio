"""
CharX Studio — SillyTavern Character Card Editor & Packager
Builds .charx archives (V2 spec) from existing assets.
"""

from __future__ import annotations

import base64
import difflib
import json
import struct
import zipfile
import zlib
from pathlib import Path
from tkinter import filedialog, messagebox, simpledialog
import tkinter as tk

import customtkinter as ctk
from PIL import Image, ImageTk

# ── Constants ────────────────────────────────────────────────────────────────

APP_TITLE = "CharX Studio"
APP_VERSION = "1.0.0"
ACCENT = "#7B68EE"
ACCENT_HOVER = "#6A5ACD"

EXPRESSIONS = [
    "admiration", "amusement", "anger", "annoyance", "approval",
    "caring", "confusion", "curiosity", "desire", "disappointment",
    "disapproval", "disgust", "embarrassment", "excitement", "fear",
    "gratitude", "grief", "joy", "love", "nervousness",
    "optimism", "pride", "realization", "relief", "remorse",
    "sadness", "surprise", "neutral",
]

# Fuzzy keyword hints for auto-assign
EXPRESSION_KEYWORDS: dict[str, list[str]] = {
    "admiration":    ["admire", "admiration", "impressed"],
    "amusement":     ["amuse", "amusement", "entertained"],
    "anger":         ["anger", "angry", "mad", "rage", "furious", "irate"],
    "annoyance":     ["annoy", "annoyed", "irritat"],
    "approval":      ["approv", "agree", "thumbsup"],
    "caring":        ["care", "caring", "warm", "gentle"],
    "confusion":     ["confus", "confused", "puzzl", "huh"],
    "curiosity":     ["curious", "curiosity", "interest", "wonder"],
    "desire":        ["desire", "want", "longing"],
    "disappointment":["disappoint"],
    "disapproval":   ["disapprov", "disagree", "no"],
    "disgust":       ["disgust", "gross", "ew", "eww"],
    "embarrassment": ["embarrass", "blush", "flustered"],
    "excitement":    ["excit", "hyped", "eager"],
    "fear":          ["fear", "scared", "afraid", "terrif", "horror"],
    "gratitude":     ["grateful", "gratitude", "thankful", "thanks"],
    "grief":         ["grief", "grieve", "mourn"],
    "joy":           ["joy", "happy", "happi", "delight", "elat", "cheerful", "smile"],
    "love":          ["love", "affection", "adore", "heart"],
    "nervousness":   ["nervous", "anxiety", "anxious", "worried", "worry"],
    "optimism":      ["optimist", "hopeful", "positive"],
    "pride":         ["pride", "proud"],
    "realization":   ["realiz", "realise", "ahah", "epiphany"],
    "relief":        ["relief", "relieve", "phew"],
    "remorse":       ["remorse", "regret", "guilt", "sorry"],
    "sadness":       ["sad", "sadness", "cry", "crying", "upset", "depressed", "unhappy"],
    "surprise":      ["surpris", "shock", "gasp", "wow"],
    "neutral":       ["neutral", "blank", "default", "normal", "calm", "base"],
}

IMAGE_TYPES = [("Image files", "*.png *.jpg *.jpeg *.webp"), ("All files", "*.*")]
CARD_TYPES  = [("PNG card", "*.png"), ("JSON card", "*.json"), ("All files", "*.*")]

# ── PNG metadata helpers ──────────────────────────────────────────────────────

def _make_text_chunk(keyword: str, text: str) -> bytes:
    """Build a PNG tEXt chunk."""
    data = keyword.encode("latin-1") + b"\x00" + text.encode("latin-1")
    crc = zlib.crc32(b"tEXt" + data) & 0xFFFFFFFF
    return struct.pack(">I", len(data)) + b"tEXt" + data + struct.pack(">I", crc)


def _parse_png_chunks(raw: bytes) -> list[tuple[bytes, bytes]]:
    """Return list of (chunk_type, chunk_data) from raw PNG bytes."""
    chunks = []
    pos = 8  # skip PNG signature
    while pos < len(raw):
        length = struct.unpack(">I", raw[pos:pos+4])[0]
        ctype  = raw[pos+4:pos+8]
        data   = raw[pos+8:pos+8+length]
        chunks.append((ctype, data))
        pos += 12 + length
    return chunks


def read_png_card(path: Path) -> dict:
    """Extract V2/V3 character card JSON from PNG tEXt chunks.

    Parses raw PNG bytes directly instead of relying on Pillow's img.info,
    which doesn't reliably expose tEXt chunks from all PNG encoders.
    Checks ccv3 first (V3), falls back to chara (V2).
    """
    raw_bytes = path.read_bytes()
    if not raw_bytes.startswith(b"\x89PNG"):
        raise ValueError("File is not a valid PNG.")

    chunks = _parse_png_chunks(raw_bytes)
    found: dict[str, str] = {}
    for ctype, cdata in chunks:
        if ctype == b"tEXt":
            try:
                keyword, _, text = cdata.partition(b"\x00")
                kw = keyword.decode("latin-1").lower()
                if kw in ("chara", "ccv3"):
                    found[kw] = text.decode("latin-1")
            except Exception:
                continue

    raw = found.get("ccv3") or found.get("chara")
    if not raw:
        raise ValueError("No character card metadata found in this PNG.")
    return json.loads(base64.b64decode(raw).decode("utf-8"))


def write_png_card(src_png: Path, card: dict, dest: Path) -> None:
    """Write card JSON into PNG tEXt chunk, saving to dest."""
    raw = src_png.read_bytes()
    if not raw.startswith(b"\x89PNG"):
        raise ValueError("Source file is not a valid PNG.")

    chunks = _parse_png_chunks(raw)
    # Remove existing chara/ccv3 chunks
    chunks = [
        (ct, cd) for ct, cd in chunks
        if not (ct == b"tEXt" and cd.split(b"\x00", 1)[0].lower() in (b"chara", b"ccv3"))
    ]

    encoded = base64.b64encode(json.dumps(card, ensure_ascii=False).encode("utf-8")).decode("latin-1")
    new_chunk_v2 = _make_text_chunk("chara", encoded)

    # Build final PNG: signature + chunks (insert new tEXt before IEND)
    out = bytearray(b"\x89PNG\r\n\x1a\n")
    for ct, cd in chunks:
        if ct == b"IEND":
            out += new_chunk_v2
        crc = zlib.crc32(ct + cd) & 0xFFFFFFFF
        out += struct.pack(">I", len(cd)) + ct + cd + struct.pack(">I", crc)

    dest.write_bytes(bytes(out))


# ── .charx builder ────────────────────────────────────────────────────────────

def build_charx(
    card: dict,
    avatar: Path | None,
    expressions: dict[str, Path | None],
    out: Path,
) -> Path:
    """
    Package card JSON + avatar + expression images into a .charx file.
    Returns the final .charx path.
    """
    assets: list[dict] = []
    if avatar and avatar.exists():
        ext = avatar.suffix.lstrip(".").lower() or "png"
        assets.append({
            "type": "icon", "name": "main",
            "uri": "embeded://assets/icon/images/avatar." + ext,
            "ext": ext,
        })

    for label, src in expressions.items():
        if src and src.exists():
            assets.append({
                "type": "emotion", "name": label,
                "uri": f"embeded://assets/emotion/images/{label}.png",
                "ext": "png",
            })

    card = json.loads(json.dumps(card))  # deep copy
    card["data"]["assets"] = assets

    charx_path = out.with_suffix(".charx")
    zip_path   = out.with_suffix(".zip")

    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("card.json", json.dumps(card, ensure_ascii=False, indent=2))
        if avatar and avatar.exists():
            ext = avatar.suffix.lstrip(".").lower() or "png"
            zf.write(avatar, f"assets/icon/images/avatar.{ext}")
        for label, src in expressions.items():
            if src and src.exists():
                zf.write(src, f"assets/emotion/images/{label}.png")

    zip_path.replace(charx_path)
    return charx_path


# ── Card template ─────────────────────────────────────────────────────────────

def empty_card() -> dict:
    return {
        "spec": "chara_card_v2",
        "spec_version": "2.0",
        "data": {
            "name": "",
            "description": "",
            "personality": "",
            "scenario": "",
            "first_mes": "",
            "mes_example": "",
            "creator_notes": "",
            "system_prompt": "",
            "post_history_instructions": "",
            "alternate_greetings": [],
            "tags": [],
            "creator": "",
            "character_version": "",
            "extensions": {},
            "assets": [],
        },
    }


def normalize_card(raw: dict) -> dict:
    """Ensure imported card has all required V2 fields."""
    base = empty_card()
    data = raw.get("data") or raw  # handle V1 (flat) cards
    base["data"].update({k: v for k, v in data.items() if k in base["data"]})
    return base


# ── Token guestimate (byte length / 4) ───────────────────────────────────────

def token_estimate(card: dict) -> int:
    fields = ["description", "personality", "scenario", "first_mes", "mes_example",
              "system_prompt", "post_history_instructions", "creator_notes"]
    text = " ".join(str(card["data"].get(f, "")) for f in fields)
    return max(0, len(text.encode("utf-8")) // 4)


# ── Auto-assign fuzzy match ───────────────────────────────────────────────────

def _match_expression(stem: str) -> str | None:
    """Return best matching expression name for a filename stem, or None."""
    stem_lower = stem.lower()
    # Exact match first
    if stem_lower in EXPRESSIONS:
        return stem_lower
    # Keyword scan
    for expr, keywords in EXPRESSION_KEYWORDS.items():
        if any(kw in stem_lower for kw in keywords):
            return expr
    # Difflib fallback
    matches = difflib.get_close_matches(stem_lower, EXPRESSIONS, n=1, cutoff=0.6)
    return matches[0] if matches else None


def auto_assign_from_folder(folder: Path) -> dict[str, Path]:
    """Return {expression_label: file_path} for best matches in folder."""
    result: dict[str, Path] = {}
    image_exts = {".png", ".jpg", ".jpeg", ".webp"}
    for f in sorted(folder.iterdir()):
        if f.suffix.lower() not in image_exts:
            continue
        label = _match_expression(f.stem)
        if label and label not in result:
            result[label] = f
    return result


# ════════════════════════════════════════════════════════════════════════════
# UI
# ════════════════════════════════════════════════════════════════════════════

ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")

PLACEHOLDER_COLOR = "#3a3a4a"
SLOT_SIZE = 96        # px per expression slot thumbnail
SLOT_COLS = 4


class ExpressionSlot(ctk.CTkFrame):
    """A single clickable expression card in the expressions grid."""

    def __init__(self, parent, label: str, on_assign, on_clear, **kwargs):
        super().__init__(parent, width=SLOT_SIZE + 16, height=SLOT_SIZE + 32,
                         corner_radius=8, border_width=1,
                         border_color="#444458", **kwargs)
        self.label = label
        self.on_assign = on_assign
        self.on_clear = on_clear
        self._img_path: Path | None = None
        self._photo = None
        self.grid_propagate(False)

        self._thumb = ctk.CTkLabel(self, text="+", width=SLOT_SIZE, height=SLOT_SIZE,
                                   corner_radius=6, fg_color=PLACEHOLDER_COLOR,
                                   font=ctk.CTkFont(size=22))
        self._thumb.grid(row=0, column=0, padx=8, pady=(8, 2))

        self._lbl = ctk.CTkLabel(self, text=label,
                                 font=ctk.CTkFont(size=10),
                                 text_color="#aaaacc")
        self._lbl.grid(row=1, column=0, padx=4, pady=(0, 6))

        # Bind click + right-click on all children
        for w in (self, self._thumb, self._lbl):
            w.bind("<Button-1>", self._click)
            w.bind("<Button-3>", self._right_click)
            w.bind("<Enter>",    self._hover_on)
            w.bind("<Leave>",    self._hover_off)

        # DnD support (optional)
        try:
            self._thumb.drop_target_register("DND_Files")  # type: ignore
            self._thumb.dnd_bind("<<Drop>>", self._on_drop)  # type: ignore
        except Exception:
            pass

    def _hover_on(self, _=None):
        self.configure(border_color=ACCENT)

    def _hover_off(self, _=None):
        assigned = self._img_path is not None
        self.configure(border_color=ACCENT if assigned else "#444458")

    def _click(self, _=None):
        self.on_assign(self.label)

    def _right_click(self, _=None):
        menu = tk.Menu(self, tearoff=0)
        menu.add_command(label="Clear", command=lambda: self.on_clear(self.label))
        try:
            menu.tk_popup(self.winfo_pointerx(), self.winfo_pointery())
        finally:
            menu.grab_release()

    def _on_drop(self, event):
        path_str = event.data.strip("{}")  # Windows wraps spaces in {}
        path = Path(path_str)
        if path.suffix.lower() in {".png", ".jpg", ".jpeg", ".webp"}:
            self.on_assign(self.label, path)

    def set_image(self, path: Path | None):
        self._img_path = path
        if path and path.exists():
            try:
                img = Image.open(path).convert("RGBA").resize(
                    (SLOT_SIZE, SLOT_SIZE), Image.LANCZOS)
                self._photo = ctk.CTkImage(light_image=img, dark_image=img,
                                           size=(SLOT_SIZE, SLOT_SIZE))
                self._thumb.configure(image=self._photo, text="")
                self.configure(border_color=ACCENT)
                return
            except Exception:
                pass
        self._photo = None
        self._thumb.configure(image="", text="+")
        self.configure(border_color="#444458")


class AlternateGreetingsEditor(ctk.CTkToplevel):
    """Modal for adding/editing alternate greetings."""

    def __init__(self, parent, greetings: list[str], on_save):
        super().__init__(parent)
        self.title("Alternate Greetings")
        self.geometry("600x400")
        self.grab_set()
        self._greetings = list(greetings)
        self._on_save = on_save
        self._selected = None
        self._build()

    def _build(self):
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)

        top = ctk.CTkFrame(self, fg_color="transparent")
        top.grid(row=0, column=0, padx=12, pady=(12, 4), sticky="ew")
        ctk.CTkButton(top, text="+ Add", width=80, fg_color=ACCENT,
                      hover_color=ACCENT_HOVER, command=self._add).pack(side="left", padx=4)
        ctk.CTkButton(top, text="✎ Edit", width=80, command=self._edit).pack(side="left", padx=4)
        ctk.CTkButton(top, text="✕ Remove", width=80, fg_color="#883344",
                      hover_color="#661122", command=self._remove).pack(side="left", padx=4)

        self._listbox = tk.Listbox(self, bg="#1e1e2e", fg="#ccccff",
                                   selectbackground=ACCENT, relief="flat",
                                   font=("Segoe UI", 10), activestyle="none")
        self._listbox.grid(row=1, column=0, padx=12, pady=4, sticky="nsew")
        self._refresh()

        ctk.CTkButton(self, text="Save & Close", fg_color=ACCENT,
                      hover_color=ACCENT_HOVER, command=self._save).grid(
            row=2, column=0, pady=12)

    def _refresh(self):
        self._listbox.delete(0, "end")
        for i, g in enumerate(self._greetings):
            preview = g[:80].replace("\n", " ")
            self._listbox.insert("end", f"{i+1}. {preview}")

    def _selected_index(self):
        sel = self._listbox.curselection()
        return sel[0] if sel else None

    def _add(self):
        dlg = _MultilineDialog(self, "New Greeting", "")
        if dlg.result is not None:
            self._greetings.append(dlg.result)
            self._refresh()

    def _edit(self):
        idx = self._selected_index()
        if idx is None:
            return
        dlg = _MultilineDialog(self, "Edit Greeting", self._greetings[idx])
        if dlg.result is not None:
            self._greetings[idx] = dlg.result
            self._refresh()

    def _remove(self):
        idx = self._selected_index()
        if idx is not None:
            self._greetings.pop(idx)
            self._refresh()

    def _save(self):
        self._on_save(self._greetings)
        self.destroy()


class _MultilineDialog(ctk.CTkToplevel):
    """Simple multiline text input dialog."""

    def __init__(self, parent, title: str, initial: str):
        super().__init__(parent)
        self.title(title)
        self.geometry("560x320")
        self.grab_set()
        self.result = None

        self._text = ctk.CTkTextbox(self, wrap="word")
        self._text.pack(fill="both", expand=True, padx=12, pady=(12, 4))
        self._text.insert("1.0", initial)

        bar = ctk.CTkFrame(self, fg_color="transparent")
        bar.pack(fill="x", padx=12, pady=8)
        ctk.CTkButton(bar, text="OK", fg_color=ACCENT,
                      hover_color=ACCENT_HOVER, command=self._ok).pack(side="right", padx=4)
        ctk.CTkButton(bar, text="Cancel", command=self.destroy).pack(side="right")
        self.wait_window()

    def _ok(self):
        self.result = self._text.get("1.0", "end").rstrip("\n")
        self.destroy()


# ── Main Application ──────────────────────────────────────────────────────────

class CharXStudio(ctk.CTk):

    def __init__(self):
        super().__init__()
        self.title(APP_TITLE)
        self.geometry("1000x720")
        self.minsize(800, 600)

        self._card = empty_card()
        self._avatar_path: Path | None = None
        self._avatar_photo = None
        self._expressions: dict[str, Path | None] = {e: None for e in EXPRESSIONS}
        self._expr_slots: dict[str, ExpressionSlot] = {}

        self._build_ui()
        self._refresh_sidebar()

    # ── Build UI ──────────────────────────────────────────────────────────────

    def _build_ui(self):
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)

        self._build_sidebar()
        self._build_main()
        self._build_bottom_bar()

    def _build_sidebar(self):
        sidebar = ctk.CTkFrame(self, width=170, corner_radius=0, fg_color="#16162a")
        sidebar.grid(row=0, column=0, sticky="nsew")
        sidebar.grid_propagate(False)
        sidebar.grid_rowconfigure(6, weight=1)

        # Avatar
        self._avatar_label = ctk.CTkLabel(
            sidebar, text="", width=128, height=128,
            corner_radius=10, fg_color=PLACEHOLDER_COLOR)
        self._avatar_label.grid(row=0, column=0, padx=20, pady=(20, 6))
        self._avatar_label.bind("<Button-1>", lambda _: self._browse_avatar())

        ctk.CTkButton(sidebar, text="Browse Avatar", width=130, height=26,
                      fg_color="#2a2a40", hover_color="#3a3a58",
                      command=self._browse_avatar).grid(row=1, column=0, padx=20, pady=(0, 12))

        ctk.CTkLabel(sidebar, text="Name", font=ctk.CTkFont(size=11),
                     text_color="#888899").grid(row=2, column=0, padx=20, sticky="w")
        self._sidebar_name = ctk.CTkLabel(sidebar, text="—",
                                          font=ctk.CTkFont(size=13, weight="bold"),
                                          wraplength=140, justify="left")
        self._sidebar_name.grid(row=3, column=0, padx=20, sticky="w")

        ctk.CTkLabel(sidebar, text="Est. tokens", font=ctk.CTkFont(size=11),
                     text_color="#888899").grid(row=4, column=0, padx=20, pady=(12, 0), sticky="w")
        self._sidebar_tokens = ctk.CTkLabel(sidebar, text="~0",
                                            font=ctk.CTkFont(size=12))
        self._sidebar_tokens.grid(row=5, column=0, padx=20, sticky="w")

        btn_frame = ctk.CTkFrame(sidebar, fg_color="transparent")
        btn_frame.grid(row=7, column=0, padx=16, pady=16, sticky="ew")
        ctk.CTkButton(btn_frame, text="New", width=130, fg_color="#2a2a40",
                      hover_color="#3a3a58", command=self._new_card).pack(pady=4)
        ctk.CTkButton(btn_frame, text="Import ▾", width=130, fg_color=ACCENT,
                      hover_color=ACCENT_HOVER, command=self._import_menu).pack(pady=4)

    def _build_main(self):
        main = ctk.CTkFrame(self, fg_color="transparent")
        main.grid(row=0, column=1, sticky="nsew", padx=0, pady=0)
        main.grid_columnconfigure(0, weight=1)
        main.grid_rowconfigure(0, weight=1)

        # Title bar
        titlebar = ctk.CTkFrame(main, height=40, fg_color="#1a1a2e", corner_radius=0)
        titlebar.grid(row=0, column=0, sticky="ew")
        titlebar.grid_propagate(False)
        ctk.CTkLabel(titlebar, text=APP_TITLE,
                     font=ctk.CTkFont(size=14, weight="bold"),
                     text_color=ACCENT).pack(side="left", padx=16, pady=8)
        self._theme_btn = ctk.CTkButton(
            titlebar, text="◐ Light", width=80, height=26,
            fg_color="#2a2a40", hover_color="#3a3a58",
            command=self._toggle_theme)
        self._theme_btn.pack(side="right", padx=12, pady=7)

        # Tabs
        self._tabs = ctk.CTkTabview(main, anchor="nw",
                                    segmented_button_selected_color=ACCENT,
                                    segmented_button_selected_hover_color=ACCENT_HOVER)
        self._tabs.grid(row=1, column=0, sticky="nsew", padx=12, pady=(4, 0))
        main.grid_rowconfigure(1, weight=1)

        for tab_name in ("Basic Info", "Advanced", "Expressions"):
            self._tabs.add(tab_name)

        self._build_basic_tab(self._tabs.tab("Basic Info"))
        self._build_advanced_tab(self._tabs.tab("Advanced"))
        self._build_expressions_tab(self._tabs.tab("Expressions"))

    def _build_bottom_bar(self):
        bar = ctk.CTkFrame(self, height=48, corner_radius=0, fg_color="#16162a")
        bar.grid(row=1, column=0, columnspan=2, sticky="ew")
        bar.grid_propagate(False)

        ctk.CTkButton(bar, text="Export .charx", width=130, height=32,
                      fg_color=ACCENT, hover_color=ACCENT_HOVER,
                      font=ctk.CTkFont(weight="bold"),
                      command=self._export_charx).pack(side="right", padx=8, pady=8)
        ctk.CTkButton(bar, text="Export PNG", width=110, height=32,
                      fg_color="#2a2a40", hover_color="#3a3a58",
                      command=self._export_png).pack(side="right", padx=4, pady=8)

        self._status_var = tk.StringVar(value="Ready")
        ctk.CTkLabel(bar, textvariable=self._status_var,
                     font=ctk.CTkFont(size=11), text_color="#888899").pack(
            side="left", padx=16)

    # ── Basic tab ─────────────────────────────────────────────────────────────

    def _build_basic_tab(self, tab):
        tab.grid_columnconfigure(1, weight=1)

        fields = [
            ("Name",          "name",          1),
            ("Description",   "description",   5),
            ("Personality",   "personality",   4),
            ("Scenario",      "scenario",      3),
            ("First Message", "first_mes",     5),
        ]
        self._basic_vars: dict[str, ctk.CTkTextbox | ctk.CTkEntry] = {}

        for i, (label, key, rows) in enumerate(fields):
            ctk.CTkLabel(tab, text=label, font=ctk.CTkFont(size=12),
                         anchor="w").grid(row=i*2, column=0, columnspan=2,
                                          padx=12, pady=(10, 0), sticky="w")
            if rows == 1:
                widget = ctk.CTkEntry(tab, height=32)
                widget.grid(row=i*2+1, column=0, columnspan=2,
                            padx=12, pady=(2, 0), sticky="ew")
            else:
                widget = ctk.CTkTextbox(tab, height=rows * 22, wrap="word")
                widget.grid(row=i*2+1, column=0, columnspan=2,
                            padx=12, pady=(2, 0), sticky="ew")
            self._basic_vars[key] = widget
            tab.grid_rowconfigure(i*2+1, weight=1 if rows > 1 else 0)

    # ── Advanced tab ──────────────────────────────────────────────────────────

    def _build_advanced_tab(self, tab):
        tab.grid_columnconfigure(1, weight=1)

        textbox_fields = [
            ("Example Messages",          "mes_example",                3),
            ("System Prompt",             "system_prompt",              3),
            ("Post History Instructions", "post_history_instructions",  2),
            ("Creator Notes",             "creator_notes",              2),
        ]
        self._adv_vars: dict[str, ctk.CTkTextbox | ctk.CTkEntry] = {}
        row = 0

        for label, key, rows in textbox_fields:
            ctk.CTkLabel(tab, text=label, font=ctk.CTkFont(size=12),
                         anchor="w").grid(row=row, column=0, columnspan=3,
                                          padx=12, pady=(10, 0), sticky="w")
            row += 1
            w = ctk.CTkTextbox(tab, height=rows * 22, wrap="word")
            w.grid(row=row, column=0, columnspan=3, padx=12, pady=(2, 0), sticky="ew")
            tab.grid_rowconfigure(row, weight=1)
            self._adv_vars[key] = w
            row += 1

        # Tags / Creator / Version in one row
        ctk.CTkLabel(tab, text="Tags (comma-separated)", font=ctk.CTkFont(size=12),
                     anchor="w").grid(row=row, column=0, padx=12, pady=(10, 0), sticky="w")
        row += 1
        self._adv_vars["tags"] = ctk.CTkEntry(tab, height=30)
        self._adv_vars["tags"].grid(row=row, column=0, columnspan=3,
                                    padx=12, pady=(2, 0), sticky="ew")
        row += 1

        meta_frame = ctk.CTkFrame(tab, fg_color="transparent")
        meta_frame.grid(row=row, column=0, columnspan=3, padx=8, pady=(8, 0), sticky="ew")
        meta_frame.grid_columnconfigure((1, 3), weight=1)
        ctk.CTkLabel(meta_frame, text="Creator").grid(row=0, column=0, padx=(4, 4))
        self._adv_vars["creator"] = ctk.CTkEntry(meta_frame, height=30)
        self._adv_vars["creator"].grid(row=0, column=1, padx=4, sticky="ew")
        ctk.CTkLabel(meta_frame, text="Version").grid(row=0, column=2, padx=(12, 4))
        self._adv_vars["character_version"] = ctk.CTkEntry(meta_frame, height=30)
        self._adv_vars["character_version"].grid(row=0, column=3, padx=4, sticky="ew")
        row += 1

        # Alternate greetings
        ctk.CTkLabel(tab, text="Alternate Greetings", font=ctk.CTkFont(size=12),
                     anchor="w").grid(row=row, column=0, columnspan=3,
                                      padx=12, pady=(12, 0), sticky="w")
        row += 1
        ag_frame = ctk.CTkFrame(tab, fg_color="transparent")
        ag_frame.grid(row=row, column=0, columnspan=3, padx=12, pady=(2, 8), sticky="ew")
        ag_frame.grid_columnconfigure(0, weight=1)

        self._greetings_list = tk.Listbox(ag_frame, height=4,
                                          bg="#1e1e2e", fg="#ccccff",
                                          selectbackground=ACCENT, relief="flat",
                                          font=("Segoe UI", 10), activestyle="none")
        self._greetings_list.grid(row=0, column=0, sticky="ew")
        btn_row = ctk.CTkFrame(ag_frame, fg_color="transparent")
        btn_row.grid(row=1, column=0, sticky="ew", pady=4)
        ctk.CTkButton(btn_row, text="+ Add", width=80, fg_color=ACCENT,
                      hover_color=ACCENT_HOVER,
                      command=self._add_greeting).pack(side="left", padx=2)
        ctk.CTkButton(btn_row, text="✎ Edit", width=80,
                      fg_color="#2a2a40", hover_color="#3a3a58",
                      command=self._edit_greeting).pack(side="left", padx=2)
        ctk.CTkButton(btn_row, text="✕", width=40,
                      fg_color="#883344", hover_color="#661122",
                      command=self._remove_greeting).pack(side="left", padx=2)

    # ── Expressions tab ───────────────────────────────────────────────────────

    def _build_expressions_tab(self, tab):
        tab.grid_columnconfigure(0, weight=1)
        tab.grid_rowconfigure(1, weight=1)

        toolbar = ctk.CTkFrame(tab, fg_color="transparent")
        toolbar.grid(row=0, column=0, sticky="ew", padx=8, pady=(8, 4))
        ctk.CTkButton(toolbar, text="Auto-assign from folder", fg_color=ACCENT,
                      hover_color=ACCENT_HOVER,
                      command=self._auto_assign).pack(side="left", padx=4)
        ctk.CTkButton(toolbar, text="Clear All", fg_color="#2a2a40",
                      hover_color="#3a3a58",
                      command=self._clear_all_expressions).pack(side="left", padx=4)
        ctk.CTkLabel(toolbar,
                     text="Click a slot to browse  ·  Right-click to clear  ·  Drag & drop supported",
                     font=ctk.CTkFont(size=10), text_color="#666677").pack(
            side="right", padx=8)

        # Scrollable grid
        scroll_frame = ctk.CTkScrollableFrame(tab, fg_color="transparent")
        scroll_frame.grid(row=1, column=0, sticky="nsew", padx=8, pady=4)
        for col in range(SLOT_COLS):
            scroll_frame.grid_columnconfigure(col, weight=1)

        for idx, expr in enumerate(EXPRESSIONS):
            row, col = divmod(idx, SLOT_COLS)
            slot = ExpressionSlot(
                scroll_frame, expr,
                on_assign=self._assign_expression,
                on_clear=self._clear_expression,
            )
            slot.grid(row=row, column=col, padx=6, pady=6, sticky="n")
            self._expr_slots[expr] = slot

    # ── Sidebar refresh ───────────────────────────────────────────────────────

    def _refresh_sidebar(self):
        name = self._read_field("name", self._basic_vars if hasattr(self, "_basic_vars") else {})
        self._sidebar_name.configure(text=name or "—")
        self._sidebar_tokens.configure(text=f"~{token_estimate(self._card):,}")

    def _read_field(self, key: str, var_dict: dict) -> str:
        if key not in var_dict:
            return ""
        w = var_dict[key]
        if isinstance(w, ctk.CTkTextbox):
            return w.get("1.0", "end").rstrip("\n")
        return w.get()

    # ── Card I/O ──────────────────────────────────────────────────────────────

    def _new_card(self):
        if not messagebox.askyesno("New Card", "Discard current card and start fresh?"):
            return
        self._card = empty_card()
        self._avatar_path = None
        self._expressions = {e: None for e in EXPRESSIONS}
        self._load_card_into_ui()
        self._set_status("New card created.")

    def _import_menu(self):
        path_str = filedialog.askopenfilename(
            title="Import character card",
            filetypes=CARD_TYPES,
        )
        if not path_str:
            return
        path = Path(path_str)
        try:
            if path.suffix.lower() == ".png":
                raw = read_png_card(path)
                self._avatar_path = path
                self._update_avatar_preview(path)
            else:
                raw = json.loads(path.read_text("utf-8"))
            self._card = normalize_card(raw)
            self._load_card_into_ui()
            self._set_status(f"Imported: {path.name}")
        except Exception as exc:
            messagebox.showerror("Import Error", str(exc))

    def _load_card_into_ui(self):
        d = self._card["data"]

        def _set(w, val):
            if isinstance(w, ctk.CTkTextbox):
                w.delete("1.0", "end")
                w.insert("1.0", str(val or ""))
            else:
                w.delete(0, "end")
                w.insert(0, str(val or ""))

        basic_keys = ["name", "description", "personality", "scenario", "first_mes"]
        for k in basic_keys:
            if k in self._basic_vars:
                _set(self._basic_vars[k], d.get(k, ""))

        adv_text_keys = ["mes_example", "system_prompt", "post_history_instructions", "creator_notes"]
        for k in adv_text_keys:
            if k in self._adv_vars:
                _set(self._adv_vars[k], d.get(k, ""))

        _set(self._adv_vars["tags"], ", ".join(d.get("tags", [])))
        _set(self._adv_vars["creator"], d.get("creator", ""))
        _set(self._adv_vars["character_version"], d.get("character_version", ""))

        self._greetings_list.delete(0, "end")
        for i, g in enumerate(d.get("alternate_greetings", [])):
            self._greetings_list.insert("end", f"{i+1}. {g[:60].replace(chr(10), ' ')}")

        # Reset expression slots (importing doesn't carry sprite files)
        for expr in EXPRESSIONS:
            self._expressions[expr] = None
            self._expr_slots[expr].set_image(None)

        self._refresh_sidebar()

    def _collect_card(self) -> dict:
        """Read all UI fields back into a card dict."""
        d = self._card["data"]

        def _get(w):
            if isinstance(w, ctk.CTkTextbox):
                return w.get("1.0", "end").rstrip("\n")
            return w.get().strip()

        for k in ["name", "description", "personality", "scenario", "first_mes"]:
            d[k] = _get(self._basic_vars[k])
        for k in ["mes_example", "system_prompt", "post_history_instructions", "creator_notes"]:
            d[k] = _get(self._adv_vars[k])
        d["creator"] = _get(self._adv_vars["creator"])
        d["character_version"] = _get(self._adv_vars["character_version"])
        raw_tags = _get(self._adv_vars["tags"])
        d["tags"] = [t.strip() for t in raw_tags.split(",") if t.strip()]

        self._refresh_sidebar()
        return self._card

    # ── Avatar ────────────────────────────────────────────────────────────────

    def _browse_avatar(self):
        path_str = filedialog.askopenfilename(
            title="Select avatar image",
            filetypes=IMAGE_TYPES,
        )
        if path_str:
            self._avatar_path = Path(path_str)
            self._update_avatar_preview(self._avatar_path)

    def _update_avatar_preview(self, path: Path):
        """Display avatar preserving aspect ratio, fitted within 128×192 (portrait-friendly)."""
        try:
            img = Image.open(path).convert("RGBA")
            max_w, max_h = 128, 192
            img.thumbnail((max_w, max_h), Image.LANCZOS)
            w, h = img.size
            self._avatar_photo = ctk.CTkImage(light_image=img, dark_image=img, size=(w, h))
            self._avatar_label.configure(image=self._avatar_photo, text="", width=w, height=h)
        except Exception:
            pass

    # ── Alternate greetings ───────────────────────────────────────────────────

    def _greeting_list(self) -> list[str]:
        return list(self._card["data"].get("alternate_greetings", []))

    def _save_greetings(self, greetings: list[str]):
        self._card["data"]["alternate_greetings"] = greetings
        self._greetings_list.delete(0, "end")
        for i, g in enumerate(greetings):
            self._greetings_list.insert("end", f"{i+1}. {g[:60].replace(chr(10), ' ')}")

    def _add_greeting(self):
        dlg = _MultilineDialog(self, "New Greeting", "")
        if dlg.result is not None:
            gl = self._greeting_list()
            gl.append(dlg.result)
            self._save_greetings(gl)

    def _edit_greeting(self):
        sel = self._greetings_list.curselection()
        if not sel:
            return
        idx = sel[0]
        gl = self._greeting_list()
        dlg = _MultilineDialog(self, "Edit Greeting", gl[idx])
        if dlg.result is not None:
            gl[idx] = dlg.result
            self._save_greetings(gl)

    def _remove_greeting(self):
        sel = self._greetings_list.curselection()
        if sel:
            gl = self._greeting_list()
            gl.pop(sel[0])
            self._save_greetings(gl)

    # ── Expressions ───────────────────────────────────────────────────────────

    def _assign_expression(self, label: str, path: Path | None = None):
        if path is None:
            path_str = filedialog.askopenfilename(
                title=f"Assign image for: {label}",
                filetypes=IMAGE_TYPES,
            )
            if not path_str:
                return
            path = Path(path_str)
        self._expressions[label] = path
        self._expr_slots[label].set_image(path)
        self._set_status(f"Assigned {label} ← {path.name}")

    def _clear_expression(self, label: str):
        self._expressions[label] = None
        self._expr_slots[label].set_image(None)

    def _clear_all_expressions(self):
        if not messagebox.askyesno("Clear All", "Remove all assigned expression images?"):
            return
        for expr in EXPRESSIONS:
            self._expressions[expr] = None
            self._expr_slots[expr].set_image(None)

    def _auto_assign(self):
        folder_str = filedialog.askdirectory(title="Select folder with expression images")
        if not folder_str:
            return
        folder = Path(folder_str)
        matches = auto_assign_from_folder(folder)
        if not matches:
            messagebox.showinfo("Auto-assign", "No matching expression images found.")
            return

        # Build confirmation message
        lines = [f"  {label:15} ← {src.name}" for label, src in sorted(matches.items())]
        msg = f"Found {len(matches)} matches:\n\n" + "\n".join(lines) + "\n\nApply?"
        if messagebox.askyesno("Auto-assign Confirm", msg):
            for label, src in matches.items():
                self._expressions[label] = src
                self._expr_slots[label].set_image(src)
            self._set_status(f"Auto-assigned {len(matches)} expressions.")

    # ── Export ────────────────────────────────────────────────────────────────

    def _export_charx(self):
        card = self._collect_card()
        name = card["data"].get("name") or "character"
        path_str = filedialog.asksaveasfilename(
            title="Export .charx",
            defaultextension=".charx",
            initialfile=f"{name}.charx",
            filetypes=[("CharX archive", "*.charx"), ("All files", "*.*")],
        )
        if not path_str:
            return
        out = Path(path_str)
        try:
            result = build_charx(card, self._avatar_path, self._expressions, out)
            self._set_status(f"Exported: {result.name}")
            messagebox.showinfo("Export Complete", f"Saved to:\n{result}")
        except Exception as exc:
            messagebox.showerror("Export Error", str(exc))

    def _export_png(self):
        if not self._avatar_path or not self._avatar_path.exists():
            messagebox.showwarning("No Avatar", "Please set an avatar image first.")
            return
        card = self._collect_card()
        name = card["data"].get("name") or "character"
        path_str = filedialog.asksaveasfilename(
            title="Export PNG card",
            defaultextension=".png",
            initialfile=f"{name}.png",
            filetypes=[("PNG", "*.png")],
        )
        if not path_str:
            return
        out = Path(path_str)
        try:
            write_png_card(self._avatar_path, card, out)
            self._set_status(f"Exported PNG: {out.name}")
            messagebox.showinfo("Export Complete", f"Saved to:\n{out}")
        except Exception as exc:
            messagebox.showerror("Export Error", str(exc))

    # ── Theme toggle ──────────────────────────────────────────────────────────

    def _toggle_theme(self):
        current = ctk.get_appearance_mode()
        if current == "Dark":
            ctk.set_appearance_mode("light")
            self._theme_btn.configure(text="◐ Dark")
        else:
            ctk.set_appearance_mode("dark")
            self._theme_btn.configure(text="◐ Light")

    # ── Status bar ────────────────────────────────────────────────────────────

    def _set_status(self, msg: str):
        self._status_var.set(msg)
        self.after(5000, lambda: self._status_var.set("Ready"))


# ── Entry point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    try:
        from tkinterdnd2 import TkinterDnD
        # Patch CTk to use TkinterDnD root
        class DnDCharXStudio(CharXStudio, TkinterDnD.Tk):  # type: ignore
            pass
        app = DnDCharXStudio()
    except ImportError:
        app = CharXStudio()

    app.mainloop()
