"""
Persona Packager Studio — SillyTavern Character Card Editor & Packager
Builds .charx archives (V2 spec) from existing assets.
"""

from __future__ import annotations

import base64
import difflib
import io
import json
import os
import struct
import sys
import threading
import urllib.request
import webbrowser
import zipfile
import zlib
from pathlib import Path
from tkinter import filedialog, messagebox
import tkinter as tk

import customtkinter as ctk
from PIL import Image, ImageTk

# ── Constants ────────────────────────────────────────────────────────────────

APP_TITLE     = "Persona Packager Studio"
APP_VERSION   = "1.0.4"
RELEASES_URL  = "https://github.com/NikoCloud/Persona-Packager-Studio/releases/latest"
RELEASES_API  = "https://api.github.com/repos/NikoCloud/Persona-Packager-Studio/releases/latest"
SETTINGS_FILE = os.path.join(os.path.expandvars('%APPDATA%'),
                             'PersonaPackagerStudio', 'settings.json')


def _load_settings() -> dict:
    try:
        with open(SETTINGS_FILE, 'r') as f:
            return json.load(f)
    except Exception:
        return {'check_updates': True}


def _save_settings(data: dict):
    try:
        os.makedirs(os.path.dirname(SETTINGS_FILE), exist_ok=True)
        with open(SETTINGS_FILE, 'w') as f:
            json.dump(data, f, indent=2)
    except Exception:
        pass


def _version_tuple(v: str) -> tuple:
    try:
        return tuple(int(x) for x in v.strip().lstrip('v').split('.'))
    except Exception:
        return (0,)


def _asset_path(name: str) -> Path:
    """Resolve asset path for both normal and PyInstaller-frozen execution."""
    base = Path(sys._MEIPASS) if getattr(sys, "frozen", False) else Path(__file__).parent
    return base / "assets" / name

LOGO_ICO  = _asset_path("logo.ico")
LOGO_PNG  = _asset_path("logo.png")
ACCENT      = "#7B68EE"
ACCENT_HOVER = "#6A5ACD"

# SillyTavern enforced avatar size (src/constants.js)
AVATAR_SIZE  = (512, 768)
AVATAR_RATIO = (2, 3)

# Expression community standard (not enforced by ST, but expected)
EXPR_SIZE  = (512, 512)
EXPR_RATIO = (1, 1)

EXPRESSIONS = [
    "admiration", "amusement",  "anger",      "annoyance",  "approval",
    "caring",     "confusion",  "curiosity",  "desire",     "disappointment",
    "disapproval","disgust",    "embarrassment","excitement","fear",
    "gratitude",  "grief",      "joy",        "love",       "nervousness",
    "optimism",   "pride",      "realization","relief",     "remorse",
    "sadness",    "surprise",   "neutral",
]

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
    "disapproval":   ["disapprov", "disagree"],
    "disgust":       ["disgust", "gross", "ew"],
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

SLOT_SIZE = 96
SLOT_COLS = 4

# ── PNG metadata helpers ──────────────────────────────────────────────────────

def _make_text_chunk(keyword: str, text: str) -> bytes:
    data = keyword.encode("latin-1") + b"\x00" + text.encode("latin-1")
    crc  = zlib.crc32(b"tEXt" + data) & 0xFFFFFFFF
    return struct.pack(">I", len(data)) + b"tEXt" + data + struct.pack(">I", crc)


def _parse_png_chunks(raw: bytes) -> list[tuple[bytes, bytes]]:
    chunks = []
    pos = 8
    while pos < len(raw):
        length = struct.unpack(">I", raw[pos:pos+4])[0]
        ctype  = raw[pos+4:pos+8]
        data   = raw[pos+8:pos+8+length]
        chunks.append((ctype, data))
        pos += 12 + length
    return chunks


def read_png_card(path: Path) -> dict:
    """Extract V2/V3 character card JSON directly from raw PNG tEXt chunks."""
    raw_bytes = path.read_bytes()
    if not raw_bytes.startswith(b"\x89PNG"):
        raise ValueError("File is not a valid PNG.")
    found: dict[str, str] = {}
    for ctype, cdata in _parse_png_chunks(raw_bytes):
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


def write_png_card_bytes(png_bytes: bytes, card: dict) -> bytes:
    """Inject card JSON into PNG bytes, return modified bytes."""
    if not png_bytes[:4] == b"\x89PNG":
        raise ValueError("Not a valid PNG.")
    chunks = _parse_png_chunks(png_bytes)
    chunks = [
        (ct, cd) for ct, cd in chunks
        if not (ct == b"tEXt" and cd.split(b"\x00", 1)[0].lower() in (b"chara", b"ccv3"))
    ]
    encoded = base64.b64encode(
        json.dumps(card, ensure_ascii=False).encode("utf-8")
    ).decode("latin-1")
    new_chunk = _make_text_chunk("chara", encoded)
    out = bytearray(b"\x89PNG\r\n\x1a\n")
    for ct, cd in chunks:
        if ct == b"IEND":
            out += new_chunk
        crc = zlib.crc32(ct + cd) & 0xFFFFFFFF
        out += struct.pack(">I", len(cd)) + ct + cd + struct.pack(">I", crc)
    return bytes(out)


# ── Image crop helpers ────────────────────────────────────────────────────────

# normalized_crop is (x1, y1, x2, y2) as fractions of image dimensions (0.0–1.0)
NormalizedCrop = tuple[float, float, float, float]


def _ratio_ok(size: tuple[int, int], ratio: tuple[int, int], tol: float = 0.02) -> bool:
    w, h = size
    rw, rh = ratio
    return abs(w / h - rw / rh) < tol


def _pil_crop_resize(img: Image.Image,
                     crop: NormalizedCrop | None,
                     target_size: tuple[int, int] | None) -> Image.Image:
    if crop:
        w, h = img.size
        x1, y1, x2, y2 = crop
        box = (int(x1*w), int(y1*h), int(x2*w), int(y2*h))
        img = img.crop(box)
    if target_size:
        tw, th = target_size
        iw, ih = img.size
        # Only downsample — never upsample. Upsampling with LANCZOS/bicubic
        # degrades quality worse than letting ST scale in CSS.
        # AI upscaling (Real-ESRGAN) planned for a future milestone.
        if iw > tw and ih > th:
            img = img.resize(target_size, Image.LANCZOS)
    return img


def _img_to_png_bytes(img: Image.Image) -> bytes:
    buf = io.BytesIO()
    img.convert("RGBA").save(buf, format="PNG")
    return buf.getvalue()


# ── .charx builder ────────────────────────────────────────────────────────────

def build_charx(
    card: dict,
    avatar: Path | None,
    avatar_crop: NormalizedCrop | None,
    expressions: dict[str, Path | None],
    expr_crops: dict[str, NormalizedCrop | None],
    out: Path,
) -> Path:
    assets: list[dict] = []
    if avatar and avatar.exists():
        assets.append({
            "type": "icon", "name": "main",
            "uri": "embeded://assets/icon/images/avatar.png", "ext": "png",
        })
    for label, src in expressions.items():
        if src and src.exists():
            assets.append({
                "type": "emotion", "name": label,
                "uri": f"embeded://assets/emotion/images/{label}.png", "ext": "png",
            })

    card = json.loads(json.dumps(card))
    card["data"]["assets"] = assets

    charx_path = out.with_suffix(".charx")
    zip_path   = out.with_suffix(".zip")

    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("card.json", json.dumps(card, ensure_ascii=False, indent=2))

        if avatar and avatar.exists():
            img = Image.open(avatar).convert("RGBA")
            # Apply crop; if cropped, resize to ST's standard 512×768
            target = AVATAR_SIZE if avatar_crop else None
            img = _pil_crop_resize(img, avatar_crop, target)
            zf.writestr("assets/icon/images/avatar.png", _img_to_png_bytes(img))

        for label, src in expressions.items():
            if src and src.exists():
                img = Image.open(src).convert("RGBA")
                crop = expr_crops.get(label)
                target = EXPR_SIZE if crop else None
                img = _pil_crop_resize(img, crop, target)
                zf.writestr(f"assets/emotion/images/{label}.png", _img_to_png_bytes(img))

    zip_path.replace(charx_path)
    return charx_path


# ── Card template ─────────────────────────────────────────────────────────────

def empty_card() -> dict:
    return {
        "spec": "chara_card_v2",
        "spec_version": "2.0",
        "data": {
            "name": "", "description": "", "personality": "",
            "scenario": "", "first_mes": "", "mes_example": "",
            "creator_notes": "", "system_prompt": "",
            "post_history_instructions": "",
            "alternate_greetings": [], "tags": [],
            "creator": "", "character_version": "",
            "extensions": {}, "assets": [],
        },
    }


def normalize_card(raw: dict) -> dict:
    base = empty_card()
    data = raw.get("data") or raw
    base["data"].update({k: v for k, v in data.items() if k in base["data"]})
    return base


def token_estimate(card: dict) -> int:
    fields = ["description", "personality", "scenario", "first_mes",
              "mes_example", "system_prompt", "post_history_instructions", "creator_notes"]
    text = " ".join(str(card["data"].get(f, "")) for f in fields)
    return max(0, len(text.encode("utf-8")) // 4)


# ── Auto-assign ───────────────────────────────────────────────────────────────

def _match_expression(stem: str) -> str | None:
    s = stem.lower()
    if s in EXPRESSIONS:
        return s
    for expr, kws in EXPRESSION_KEYWORDS.items():
        if any(k in s for k in kws):
            return expr
    matches = difflib.get_close_matches(s, EXPRESSIONS, n=1, cutoff=0.6)
    return matches[0] if matches else None


def auto_assign_from_folder(folder: Path) -> dict[str, Path]:
    result: dict[str, Path] = {}
    for f in sorted(folder.iterdir()):
        if f.suffix.lower() not in {".png", ".jpg", ".jpeg", ".webp"}:
            continue
        label = _match_expression(f.stem)
        if label and label not in result:
            result[label] = f
    return result


# ════════════════════════════════════════════════════════════════════════════
# Cropper Dialog
# ════════════════════════════════════════════════════════════════════════════

class CropperDialog(ctk.CTkToplevel):
    """
    Interactive crop tool. Fixed crop box, image pans/zooms freely beneath it.

    Design constraints:
    - No zoom floor tied to crop box coverage — user can zoom out to see the
      full image regardless of its dimensions
    - When image covers the crop box: normal crop (user selects a region)
    - When image is smaller than crop box (zoomed out fully): entire image is
      used as the crop; status line warns the user
    - Clamp: when image >= box axis, crop box stays within image;
             when image < box axis, image is centered within the box
    - MIN_SCALE is a tiny practical floor just to keep the image visible

    result: NormalizedCrop (x1,y1,x2,y2 as 0-1 fractions) or None if cancelled.
    """

    PAD           = 40
    MIN_SCALE     = 0.02        # practical floor — keeps image from vanishing
    OVERLAY_COLOR = "#000000"
    STIPPLE       = "gray50"
    BORDER_COLOR  = "#ffffff"
    GUIDE_COLOR   = "#ffffff"

    def __init__(self, parent, image_path: Path, ratio: tuple[int, int]):
        super().__init__(parent)
        rw, rh = ratio
        self.title(f"Crop  ·  {rw}:{rh}")
        self.grab_set()
        self.resizable(False, False)
        self.result: NormalizedCrop | None = None

        orig = Image.open(image_path).convert("RGBA")
        self._orig_size = orig.size
        MAX_DIM = 1200
        disp = orig.copy()
        if max(orig.size) > MAX_DIM:
            disp.thumbnail((MAX_DIM, MAX_DIM), Image.LANCZOS)
        self._disp_img  = disp
        self._disp_size = disp.size

        # Crop box: ~400px on the longer side, ratio-locked
        if rw >= rh:
            bw, bh = 400, max(1, int(400 * rh / rw))
        else:
            bh, bw = 400, max(1, int(400 * rw / rh))

        self.BOX_X, self.BOX_Y = self.PAD, self.PAD
        self.BOX_W, self.BOX_H = bw, bh
        canvas_w = bw + 2 * self.PAD
        canvas_h = bh + 2 * self.PAD

        # Start zoomed out: fit the entire image in the canvas so user
        # can see all pixels before choosing a crop region.
        dw, dh = self._disp_size
        self._scale    = min((canvas_w - 4) / dw, (canvas_h - 4) / dh)
        sw, sh         = dw * self._scale, dh * self._scale
        self._offset_x = (canvas_w - sw) / 2
        self._offset_y = (canvas_h - sh) / 2

        self._drag_start  = None
        self._tk_img      = None
        self._img_item    = None
        self._overlay_ids = []
        self._border_id   = None
        self._status_var  = tk.StringVar(value="")

        self._build(canvas_w, canvas_h)
        self._render()

    # ── build ─────────────────────────────────────────────────────────────

    def _build(self, cw: int, ch: int):
        self.geometry(f"{cw + 2}x{ch + 100}")

        ctk.CTkLabel(self, text="Scroll to zoom  ·  Drag to pan",
                     font=ctk.CTkFont(size=11), text_color="#888899").pack(pady=(8, 0))
        ctk.CTkLabel(self, textvariable=self._status_var,
                     font=ctk.CTkFont(size=10),
                     text_color="#ffaa44").pack(pady=(0, 2))

        self._canvas = tk.Canvas(self, width=cw, height=ch,
                                  bg="#111118", highlightthickness=0,
                                  cursor="fleur")
        self._canvas.pack()

        bar = ctk.CTkFrame(self, fg_color="transparent")
        bar.pack(fill="x", padx=16, pady=8)
        ctk.CTkButton(bar, text="Cancel", width=90,
                      fg_color="#2a2a40", hover_color="#3a3a58",
                      command=self.destroy).pack(side="left")
        ctk.CTkButton(bar, text="Crop & Use", width=110,
                      fg_color=ACCENT, hover_color=ACCENT_HOVER,
                      command=self._confirm).pack(side="right")

        self._canvas.bind("<ButtonPress-1>",   self._on_press)
        self._canvas.bind("<B1-Motion>",        self._on_drag)
        self._canvas.bind("<ButtonRelease-1>", lambda _: setattr(self, "_drag_start", None))
        self._canvas.bind("<MouseWheel>",       self._on_wheel)

    # ── helpers ───────────────────────────────────────────────────────────

    def _covers_box(self) -> bool:
        """True when the image fully covers the crop box at current transform."""
        dw, dh = self._disp_size
        sw, sh = dw * self._scale, dh * self._scale
        return (self._offset_x <= self.BOX_X and
                self._offset_x + sw >= self.BOX_X + self.BOX_W and
                self._offset_y <= self.BOX_Y and
                self._offset_y + sh >= self.BOX_Y + self.BOX_H)

    def _clamp(self):
        """
        Per-axis constraint:
        - If image >= box axis: keep crop box within image (can't pan out)
        - If image <  box axis: center image within the box (can't pan at all)
        """
        dw, dh = self._disp_size
        sw, sh = dw * self._scale, dh * self._scale
        bx, by, bw, bh = self.BOX_X, self.BOX_Y, self.BOX_W, self.BOX_H

        if sw >= bw:
            self._offset_x = min(float(bx), self._offset_x)
            self._offset_x = max(float(bx + bw - sw), self._offset_x)
        else:
            self._offset_x = bx + (bw - sw) / 2

        if sh >= bh:
            self._offset_y = min(float(by), self._offset_y)
            self._offset_y = max(float(by + bh - sh), self._offset_y)
        else:
            self._offset_y = by + (bh - sh) / 2

    # ── rendering ─────────────────────────────────────────────────────────

    def _render(self):
        dw, dh = self._disp_size
        nw, nh = max(1, int(dw * self._scale)), max(1, int(dh * self._scale))
        scaled = self._disp_img.resize((nw, nh), Image.LANCZOS)
        self._tk_img = ImageTk.PhotoImage(scaled)
        ox, oy = int(self._offset_x), int(self._offset_y)
        if self._img_item is None:
            self._img_item = self._canvas.create_image(ox, oy, anchor="nw",
                                                        image=self._tk_img)
        else:
            self._canvas.itemconfig(self._img_item, image=self._tk_img)
            self._canvas.coords(self._img_item, ox, oy)
        self._draw_overlay()
        # Status line
        if self._covers_box():
            self._status_var.set("")
        else:
            self._status_var.set("⚠  Zoomed out — entire image will be used as crop")

    def _draw_overlay(self):
        for i in self._overlay_ids:
            self._canvas.delete(i)
        if self._border_id:
            self._canvas.delete(self._border_id)
        self._overlay_ids.clear()

        cw = self._canvas.winfo_width()  or (self.BOX_W + 2 * self.PAD)
        ch = self._canvas.winfo_height() or (self.BOX_H + 2 * self.PAD)
        bx, by, bw, bh = self.BOX_X, self.BOX_Y, self.BOX_W, self.BOX_H

        for x1, y1, x2, y2 in [
            (0,      0,      cw,      by    ),
            (0,      by+bh,  cw,      ch    ),
            (0,      by,     bx,      by+bh ),
            (bx+bw,  by,     cw,      by+bh ),
        ]:
            if x2 > x1 and y2 > y1:
                self._overlay_ids.append(self._canvas.create_rectangle(
                    x1, y1, x2, y2,
                    fill=self.OVERLAY_COLOR, stipple=self.STIPPLE, outline=""))

        self._border_id = self._canvas.create_rectangle(
            bx, by, bx+bw, by+bh, outline=self.BORDER_COLOR, width=2, fill="")

        for i in (1, 2):
            x = bx + bw * i // 3
            y = by + bh * i // 3
            self._overlay_ids.append(self._canvas.create_line(
                x, by, x, by+bh, fill=self.GUIDE_COLOR, stipple=self.STIPPLE))
            self._overlay_ids.append(self._canvas.create_line(
                bx, y, bx+bw, y, fill=self.GUIDE_COLOR, stipple=self.STIPPLE))

    # ── interaction ───────────────────────────────────────────────────────

    def _on_press(self, event):
        self._drag_start = (event.x, event.y, self._offset_x, self._offset_y)

    def _on_drag(self, event):
        if not self._drag_start:
            return
        sx, sy, ox, oy = self._drag_start
        self._offset_x = ox + (event.x - sx)
        self._offset_y = oy + (event.y - sy)
        self._clamp()
        self._canvas.coords(self._img_item, int(self._offset_x), int(self._offset_y))
        self._draw_overlay()
        if self._covers_box():
            self._status_var.set("")
        else:
            self._status_var.set("⚠  Zoomed out — entire image will be used as crop")

    def _on_wheel(self, event):
        factor    = 1.12 if event.delta > 0 else 1 / 1.12
        new_scale = max(self.MIN_SCALE, self._scale * factor)
        mx, my    = event.x, event.y
        self._offset_x = mx - (mx - self._offset_x) * (new_scale / self._scale)
        self._offset_y = my - (my - self._offset_y) * (new_scale / self._scale)
        self._scale    = new_scale
        self._clamp()
        self._render()

    # ── result ────────────────────────────────────────────────────────────

    def _confirm(self):
        dw, dh = self._disp_size

        if not self._covers_box():
            # Entire image fits within the crop box — use the full image
            self.result = (0.0, 0.0, 1.0, 1.0)
            self.destroy()
            return

        cx = (self.BOX_X - self._offset_x) / self._scale
        cy = (self.BOX_Y - self._offset_y) / self._scale
        cw = self.BOX_W / self._scale
        ch = self.BOX_H / self._scale
        x1 = max(0.0, min(1.0, cx / dw))
        y1 = max(0.0, min(1.0, cy / dh))
        x2 = max(0.0, min(1.0, (cx + cw) / dw))
        y2 = max(0.0, min(1.0, (cy + ch) / dh))
        self.result = (x1, y1, x2, y2)
        self.destroy()


# ════════════════════════════════════════════════════════════════════════════
# Helpers
# ════════════════════════════════════════════════════════════════════════════

class _MultilineDialog(ctk.CTkToplevel):
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
        ctk.CTkButton(bar, text="OK", fg_color=ACCENT, hover_color=ACCENT_HOVER,
                      command=self._ok).pack(side="right", padx=4)
        ctk.CTkButton(bar, text="Cancel", command=self.destroy).pack(side="right")
        self.wait_window()

    def _ok(self):
        self.result = self._text.get("1.0", "end").rstrip("\n")
        self.destroy()


# ════════════════════════════════════════════════════════════════════════════
# Expression Slot
# ════════════════════════════════════════════════════════════════════════════

PLACEHOLDER_COLOR = "#3a3a4a"


class ExpressionSlot(ctk.CTkFrame):
    def __init__(self, parent, label: str, on_assign, on_clear, **kwargs):
        super().__init__(parent, width=SLOT_SIZE + 16, height=SLOT_SIZE + 38,
                         corner_radius=8, border_width=1,
                         border_color="#444458", **kwargs)
        self.label    = label
        self.on_assign = on_assign
        self.on_clear  = on_clear
        self._photo    = None
        self.grid_propagate(False)

        self._thumb = ctk.CTkLabel(self, text="+", width=SLOT_SIZE, height=SLOT_SIZE,
                                   corner_radius=6, fg_color=PLACEHOLDER_COLOR,
                                   font=ctk.CTkFont(size=22))
        self._thumb.grid(row=0, column=0, padx=8, pady=(8, 2))

        self._lbl = ctk.CTkLabel(self, text=label, font=ctk.CTkFont(size=10),
                                  text_color="#aaaacc")
        self._lbl.grid(row=1, column=0, padx=4, pady=(0, 2))

        self._warn_lbl = ctk.CTkLabel(self, text="", font=ctk.CTkFont(size=9),
                                       text_color="#ffaa44")
        self._warn_lbl.grid(row=2, column=0, padx=4, pady=(0, 4))

        for w in (self, self._thumb, self._lbl, self._warn_lbl):
            w.bind("<Button-1>",  self._click)
            w.bind("<Button-3>",  self._right_click)
            w.bind("<Enter>",     self._hover_on)
            w.bind("<Leave>",     self._hover_off)

        try:
            self._thumb.drop_target_register("DND_Files")  # type: ignore
            self._thumb.dnd_bind("<<Drop>>", self._on_drop)  # type: ignore
        except Exception:
            pass

    def _hover_on(self, _=None):
        self.configure(border_color=ACCENT)

    def _hover_off(self, _=None):
        self.configure(border_color=ACCENT if self._photo else "#444458")

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
        path = Path(event.data.strip("{}"))
        if path.suffix.lower() in {".png", ".jpg", ".jpeg", ".webp"}:
            self.on_assign(self.label, path)

    def set_image(self, pil_img: Image.Image | None, warn: bool = False):
        """Pass a PIL Image (already cropped/processed) or None to clear."""
        if pil_img is not None:
            try:
                thumb = pil_img.copy()
                thumb.thumbnail((SLOT_SIZE, SLOT_SIZE), Image.LANCZOS)
                self._photo = ctk.CTkImage(
                    light_image=thumb, dark_image=thumb,
                    size=thumb.size)
                self._thumb.configure(image=self._photo, text="")
                self.configure(border_color=ACCENT)
                self._warn_lbl.configure(text="⚠ uncropped" if warn else "")
                return
            except Exception:
                pass
        self._photo = None
        self._thumb.configure(image="", text="+")
        self.configure(border_color="#444458")
        self._warn_lbl.configure(text="")


# ════════════════════════════════════════════════════════════════════════════
# Main Application
# ════════════════════════════════════════════════════════════════════════════

ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")


class PersonaPackagerStudio(ctk.CTk):

    def __init__(self):
        super().__init__()
        self.title(APP_TITLE)
        self.geometry("1000x720")
        self.minsize(800, 600)

        # Window / taskbar icon (ICO required on Windows)
        if LOGO_ICO.exists():
            try:
                self.iconbitmap(str(LOGO_ICO))
            except Exception:
                pass

        self._card         = empty_card()
        self._avatar_path:  Path | None = None
        self._avatar_crop:  NormalizedCrop | None = None
        self._avatar_warn:  bool = False

        self._expressions:  dict[str, Path | None]            = {e: None for e in EXPRESSIONS}
        self._expr_crops:   dict[str, NormalizedCrop | None]  = {e: None for e in EXPRESSIONS}
        self._expr_warn:    dict[str, bool]                   = {e: False for e in EXPRESSIONS}
        self._expr_slots:   dict[str, ExpressionSlot]         = {}

        self._sidebar_w:    int = 170
        self._SIDEBAR_MIN:  int = 150
        self._SIDEBAR_MAX:  int = 520

        # Update-check state
        self._settings = _load_settings()
        self._check_updates_var = tk.BooleanVar(
            value=self._settings.get('check_updates', True))

        self._build_ui()
        self._refresh_sidebar()
        self.bind("<Configure>", self._on_window_resize)
        self._last_win_h = 0

        # Kick off update check after window is shown
        if self._check_updates_var.get():
            self.after(800, self._start_update_check)

    # ── UI ────────────────────────────────────────────────────────────────────

    def _build_ui(self):
        # col 0 = sidebar, col 1 = sash, col 2 = main
        self.grid_columnconfigure(2, weight=1)
        self.grid_rowconfigure(0, weight=1)
        self._build_sidebar()
        self._build_sash()
        self._build_main()
        self._build_bottom_bar()

    def _build_sidebar(self):
        sb = ctk.CTkFrame(self, width=self._sidebar_w, corner_radius=0, fg_color="#16162a")
        sb.grid(row=0, column=0, sticky="nsew")
        sb.grid_propagate(False)
        sb.grid_rowconfigure(6, weight=1)
        self._sidebar = sb

        aw = self._avatar_preview_w()
        ah = int(aw * 3 / 2)
        self._avatar_label = ctk.CTkLabel(
            sb, text="", width=aw, height=ah,
            corner_radius=10, fg_color=PLACEHOLDER_COLOR)
        self._avatar_label.grid(row=0, column=0, padx=20, pady=(20, 2))
        self._avatar_label.bind("<Button-1>", lambda _: self._browse_avatar())

        self._avatar_warn_label = ctk.CTkLabel(
            sb, text="", font=ctk.CTkFont(size=9), text_color="#ffaa44")
        self._avatar_warn_label.grid(row=1, column=0, padx=20)

        ctk.CTkButton(sb, text="Browse Avatar", width=130, height=26,
                      fg_color="#2a2a40", hover_color="#3a3a58",
                      command=self._browse_avatar).grid(row=2, column=0, padx=20, pady=(4, 12))

        ctk.CTkLabel(sb, text="Name", font=ctk.CTkFont(size=11),
                     text_color="#888899").grid(row=3, column=0, padx=20, sticky="w")
        self._sidebar_name = ctk.CTkLabel(sb, text="—",
                                          font=ctk.CTkFont(size=13, weight="bold"),
                                          wraplength=self._sidebar_w - 40, justify="left")
        self._sidebar_name.grid(row=4, column=0, padx=20, sticky="w")

        ctk.CTkLabel(sb, text="Est. tokens", font=ctk.CTkFont(size=11),
                     text_color="#888899").grid(row=5, column=0, padx=20, pady=(12, 0), sticky="w")
        self._sidebar_tokens = ctk.CTkLabel(sb, text="~0", font=ctk.CTkFont(size=12))
        self._sidebar_tokens.grid(row=5, column=0, padx=(90, 0), sticky="w")

        bf = ctk.CTkFrame(sb, fg_color="transparent")
        bf.grid(row=7, column=0, padx=16, pady=16, sticky="ew")
        ctk.CTkButton(bf, text="New", width=130, fg_color="#2a2a40",
                      hover_color="#3a3a58", command=self._new_card).pack(pady=4)
        ctk.CTkButton(bf, text="Import ▾", width=130, fg_color=ACCENT,
                      hover_color=ACCENT_HOVER, command=self._import_menu).pack(pady=4)

    def _build_sash(self):
        sash = tk.Frame(self, width=5, bg="#0f0f1e", cursor="size_we")
        sash.grid(row=0, column=1, sticky="nsew", rowspan=2)
        sash.bind("<ButtonPress-1>",  self._sash_press)
        sash.bind("<B1-Motion>",      self._sash_drag)
        # Highlight on hover so it's discoverable
        sash.bind("<Enter>", lambda _: sash.configure(bg="#3a3a5e"))
        sash.bind("<Leave>", lambda _: sash.configure(bg="#0f0f1e"))
        self._sash = sash
        self._sash_start_x = 0

    def _sash_press(self, event):
        self._sash_start_x = event.x_root - self._sidebar_w

    def _sash_drag(self, event):
        new_w = event.x_root - self._sash_start_x
        new_w = max(self._SIDEBAR_MIN, min(self._SIDEBAR_MAX, new_w))
        if new_w != self._sidebar_w:
            self._sidebar_w = new_w
            self._resize_sidebar()

    def _avatar_preview_w(self) -> int:
        """Avatar preview pixel width, capped so the avatar never eats the bottom buttons."""
        w = max(80, self._sidebar_w - 40)
        # Reserve ~220px for browse button + name + tokens + New/Import buttons + padding
        win_h = self.winfo_height() or 720
        max_h = max(80, win_h - 220)
        # If uncapped width would produce a taller avatar than fits, shrink width to match
        max_w_from_h = int(max_h * 2 / 3)
        return min(w, max_w_from_h)

    def _resize_sidebar(self):
        self._sidebar.configure(width=self._sidebar_w)
        self._sidebar_name.configure(wraplength=self._sidebar_w - 40)
        aw = self._avatar_preview_w()
        ah = int(aw * 3 / 2)
        self._avatar_label.configure(width=aw, height=ah)
        self._update_avatar_preview()

    def _on_window_resize(self, event):
        # Only react to the top-level window changing height, not every child widget
        if event.widget is not self:
            return
        if event.height != self._last_win_h:
            self._last_win_h = event.height
            self._resize_sidebar()

    def _build_main(self):
        main = ctk.CTkFrame(self, fg_color="transparent")
        main.grid(row=0, column=2, sticky="nsew")
        main.grid_columnconfigure(0, weight=1)
        main.grid_rowconfigure(1, weight=1)

        tb = ctk.CTkFrame(main, height=40, fg_color="#1a1a2e", corner_radius=0)
        tb.grid(row=0, column=0, sticky="ew")
        tb.grid_propagate(False)
        ctk.CTkLabel(tb, text=APP_TITLE,
                     font=ctk.CTkFont(size=14, weight="bold"),
                     text_color=ACCENT).pack(side="left", padx=16, pady=8)
        self._theme_btn = ctk.CTkButton(
            tb, text="◐ Light", width=80, height=26,
            fg_color="#2a2a40", hover_color="#3a3a58", command=self._toggle_theme)
        self._theme_btn.pack(side="right", padx=12, pady=7)

        self._tabs = ctk.CTkTabview(main, anchor="nw",
                                    segmented_button_selected_color=ACCENT,
                                    segmented_button_selected_hover_color=ACCENT_HOVER)
        self._tabs.grid(row=1, column=0, sticky="nsew", padx=12, pady=(4, 0))
        for t in ("Basic Info", "Advanced", "Expressions"):
            self._tabs.add(t)
        self._build_basic_tab(self._tabs.tab("Basic Info"))
        self._build_advanced_tab(self._tabs.tab("Advanced"))
        self._build_expressions_tab(self._tabs.tab("Expressions"))

    def _build_bottom_bar(self):
        bar = ctk.CTkFrame(self, height=48, corner_radius=0, fg_color="#16162a")
        bar.grid(row=1, column=0, columnspan=3, sticky="ew")
        bar.grid_propagate(False)

        # RIGHT side: export buttons
        ctk.CTkButton(bar, text="Export .charx", width=130, height=32,
                      fg_color=ACCENT, hover_color=ACCENT_HOVER,
                      font=ctk.CTkFont(weight="bold"),
                      command=self._export_charx).pack(side="right", padx=8, pady=8)
        ctk.CTkButton(bar, text="Export PNG", width=110, height=32,
                      fg_color="#2a2a40", hover_color="#3a3a58",
                      command=self._export_png).pack(side="right", padx=4, pady=8)

        # LEFT side: version + update check
        ctk.CTkLabel(bar, text=f"v{APP_VERSION}",
                     font=ctk.CTkFont(size=11),
                     text_color="#666677").pack(side="left", padx=(10, 4), pady=8)

        ctk.CTkLabel(bar, text="│",
                     font=ctk.CTkFont(size=11),
                     text_color="#333344").pack(side="left", padx=2, pady=8)

        ctk.CTkCheckBox(bar, text="Check for updates",
                        variable=self._check_updates_var,
                        font=ctk.CTkFont(size=11),
                        width=145, height=20,
                        command=self._on_update_check_toggled
                        ).pack(side="left", padx=(4, 4), pady=8)

        ctk.CTkLabel(bar, text="│",
                     font=ctk.CTkFont(size=11),
                     text_color="#333344").pack(side="left", padx=2, pady=8)

        self._update_status_lbl = ctk.CTkLabel(
            bar, text="", font=ctk.CTkFont(size=11),
            text_color="#666677")
        self._update_status_lbl.pack(side="left", padx=(4, 4), pady=8)

        self._update_dl_btn = ctk.CTkButton(
            bar, text="↓ Download Update", width=150, height=24,
            font=ctk.CTkFont(size=11),
            fg_color="#1a6fb5", hover_color="#155a94",
            command=lambda: webbrowser.open(RELEASES_URL))
        # packed only when an update is available

        # App status label (existing "Ready" / export feedback)
        self._status_var = tk.StringVar(value="Ready")
        ctk.CTkLabel(bar, textvariable=self._status_var,
                     font=ctk.CTkFont(size=11),
                     text_color="#888899").pack(side="left", padx=16, pady=8)

        # Set initial update status text
        if self._check_updates_var.get():
            self._set_update_status("checking")
        else:
            self._set_update_status("disabled")

    # ── Update check ─────────────────────────────────────────────────────────

    def _on_update_check_toggled(self):
        enabled = self._check_updates_var.get()
        self._settings['check_updates'] = enabled
        _save_settings(self._settings)
        if enabled:
            self._set_update_status("checking")
            self._start_update_check()
        else:
            self._set_update_status("disabled")

    def _start_update_check(self):
        threading.Thread(target=self._fetch_latest_version, daemon=True).start()

    def _fetch_latest_version(self):
        try:
            req = urllib.request.Request(
                RELEASES_API,
                headers={"User-Agent": f"PersonaPackagerStudio/{APP_VERSION}"})
            with urllib.request.urlopen(req, timeout=6) as resp:
                data = json.loads(resp.read())
            latest = data["tag_name"].lstrip("v")
            if _version_tuple(latest) > _version_tuple(APP_VERSION):
                self.after(0, lambda: self._set_update_status("available", latest))
            else:
                self.after(0, lambda: self._set_update_status("uptodate"))
        except Exception:
            self.after(0, lambda: self._set_update_status("offline"))

    def _set_update_status(self, state: str, version: str = ""):
        cfg = {
            "checking":  ("Checking for updates…",            "#666677"),
            "uptodate":  ("✓  Up to date",                    "#4CAF50"),
            "available": (f"⚠  Update available: v{version}", "#FF9800"),
            "offline":   ("●  No connection",                 "#888888"),
            "disabled":  ("○  Updates disabled",              "#555566"),
        }
        text, color = cfg.get(state, ("", "#666677"))
        self._update_status_lbl.configure(text=text, text_color=color)
        if state == "available":
            self._update_dl_btn.pack(side="left", padx=(4, 8), pady=8)
        else:
            self._update_dl_btn.pack_forget()

    # ── Tabs ──────────────────────────────────────────────────────────────────

    def _build_basic_tab(self, tab):
        tab.grid_columnconfigure(1, weight=1)
        self._basic_vars: dict[str, ctk.CTkTextbox | ctk.CTkEntry] = {}
        fields = [
            ("Name",          "name",     1),
            ("Description",   "description", 5),
            ("Personality",   "personality", 4),
            ("Scenario",      "scenario",    3),
            ("First Message", "first_mes",   5),
        ]
        for i, (lbl, key, rows) in enumerate(fields):
            ctk.CTkLabel(tab, text=lbl, font=ctk.CTkFont(size=12),
                         anchor="w").grid(row=i*2, column=0, columnspan=2,
                                          padx=12, pady=(10, 0), sticky="w")
            if rows == 1:
                w = ctk.CTkEntry(tab, height=32)
                w.grid(row=i*2+1, column=0, columnspan=2, padx=12, pady=(2, 0), sticky="ew")
            else:
                w = ctk.CTkTextbox(tab, height=rows*22, wrap="word")
                w.grid(row=i*2+1, column=0, columnspan=2, padx=12, pady=(2, 0), sticky="ew")
                tab.grid_rowconfigure(i*2+1, weight=1)
            self._basic_vars[key] = w

    def _build_advanced_tab(self, tab):
        tab.grid_columnconfigure(1, weight=1)
        self._adv_vars: dict[str, ctk.CTkTextbox | ctk.CTkEntry] = {}
        row = 0
        for lbl, key, rows in [
            ("Example Messages",          "mes_example",               3),
            ("System Prompt",             "system_prompt",             3),
            ("Post History Instructions", "post_history_instructions", 2),
            ("Creator Notes",             "creator_notes",             2),
        ]:
            ctk.CTkLabel(tab, text=lbl, font=ctk.CTkFont(size=12),
                         anchor="w").grid(row=row, column=0, columnspan=3,
                                          padx=12, pady=(10, 0), sticky="w")
            row += 1
            w = ctk.CTkTextbox(tab, height=rows*22, wrap="word")
            w.grid(row=row, column=0, columnspan=3, padx=12, pady=(2, 0), sticky="ew")
            tab.grid_rowconfigure(row, weight=1)
            self._adv_vars[key] = w
            row += 1

        ctk.CTkLabel(tab, text="Tags (comma-separated)", font=ctk.CTkFont(size=12),
                     anchor="w").grid(row=row, column=0, columnspan=3,
                                      padx=12, pady=(10, 0), sticky="w")
        row += 1
        self._adv_vars["tags"] = ctk.CTkEntry(tab, height=30)
        self._adv_vars["tags"].grid(row=row, column=0, columnspan=3,
                                    padx=12, pady=(2, 0), sticky="ew")
        row += 1

        mf = ctk.CTkFrame(tab, fg_color="transparent")
        mf.grid(row=row, column=0, columnspan=3, padx=8, pady=(8, 0), sticky="ew")
        mf.grid_columnconfigure((1, 3), weight=1)
        ctk.CTkLabel(mf, text="Creator").grid(row=0, column=0, padx=4)
        self._adv_vars["creator"] = ctk.CTkEntry(mf, height=30)
        self._adv_vars["creator"].grid(row=0, column=1, padx=4, sticky="ew")
        ctk.CTkLabel(mf, text="Version").grid(row=0, column=2, padx=(12, 4))
        self._adv_vars["character_version"] = ctk.CTkEntry(mf, height=30)
        self._adv_vars["character_version"].grid(row=0, column=3, padx=4, sticky="ew")
        row += 1

        ctk.CTkLabel(tab, text="Alternate Greetings", font=ctk.CTkFont(size=12),
                     anchor="w").grid(row=row, column=0, columnspan=3,
                                      padx=12, pady=(12, 0), sticky="w")
        row += 1
        agf = ctk.CTkFrame(tab, fg_color="transparent")
        agf.grid(row=row, column=0, columnspan=3, padx=12, pady=(2, 8), sticky="ew")
        agf.grid_columnconfigure(0, weight=1)
        self._greetings_list = tk.Listbox(agf, height=4,
                                          bg="#1e1e2e", fg="#ccccff",
                                          selectbackground=ACCENT, relief="flat",
                                          font=("Segoe UI", 10), activestyle="none")
        self._greetings_list.grid(row=0, column=0, sticky="ew")
        br = ctk.CTkFrame(agf, fg_color="transparent")
        br.grid(row=1, column=0, sticky="ew", pady=4)
        ctk.CTkButton(br, text="+ Add",  width=80, fg_color=ACCENT,
                      hover_color=ACCENT_HOVER, command=self._add_greeting).pack(side="left", padx=2)
        ctk.CTkButton(br, text="✎ Edit", width=80, fg_color="#2a2a40",
                      hover_color="#3a3a58", command=self._edit_greeting).pack(side="left", padx=2)
        ctk.CTkButton(br, text="✕",      width=40, fg_color="#883344",
                      hover_color="#661122", command=self._remove_greeting).pack(side="left", padx=2)

    def _build_expressions_tab(self, tab):
        tab.grid_columnconfigure(0, weight=1)
        tab.grid_rowconfigure(1, weight=1)

        tb = ctk.CTkFrame(tab, fg_color="transparent")
        tb.grid(row=0, column=0, sticky="ew", padx=8, pady=(8, 4))
        ctk.CTkButton(tb, text="Auto-assign from folder", fg_color=ACCENT,
                      hover_color=ACCENT_HOVER, command=self._auto_assign).pack(side="left", padx=4)
        ctk.CTkButton(tb, text="Clear All", fg_color="#2a2a40",
                      hover_color="#3a3a58", command=self._clear_all_expressions).pack(side="left", padx=4)
        ctk.CTkLabel(tb, text="Click slot to browse  ·  Right-click to clear  ·  Drag & drop supported",
                     font=ctk.CTkFont(size=10), text_color="#666677").pack(side="right", padx=8)

        sf = ctk.CTkScrollableFrame(tab, fg_color="transparent")
        sf.grid(row=1, column=0, sticky="nsew", padx=8, pady=4)
        for c in range(SLOT_COLS):
            sf.grid_columnconfigure(c, weight=1)
        for idx, expr in enumerate(EXPRESSIONS):
            r, c = divmod(idx, SLOT_COLS)
            slot = ExpressionSlot(sf, expr,
                                  on_assign=self._assign_expression,
                                  on_clear=self._clear_expression)
            slot.grid(row=r, column=c, padx=6, pady=6, sticky="n")
            self._expr_slots[expr] = slot

    # ── Ratio check & cropper ─────────────────────────────────────────────────

    def _check_ratio_prompt(
        self,
        path: Path,
        ratio: tuple[int, int],
        context: str,
    ) -> tuple[str, NormalizedCrop | None]:
        """
        Check image ratio. If non-standard, ask user.
        Returns ('ok'|'keep'|'cropped'|'cancel', crop_or_None).
        """
        try:
            img = Image.open(path)
            w, h = img.size
        except Exception:
            return ("ok", None)

        if _ratio_ok((w, h), ratio):
            return ("ok", None)

        rw, rh = ratio
        answer = messagebox.askyesnocancel(
            "Image Ratio",
            f"This image is {w}×{h} (ratio {w/h:.2f}).\n\n"
            f"SillyTavern expects {rw}:{rh} ({rw/rh:.2f}) for {context}.\n\n"
            f"Open the cropper to adjust it now?\n\n"
            f"• Yes  — open interactive cropper\n"
            f"• No   — use as-is (may display incorrectly)\n"
            f"• Cancel — don't use this image",
        )

        if answer is None:     # Cancel
            return ("cancel", None)
        if not answer:         # No — keep as-is
            return ("keep", None)

        # Yes — open cropper
        dlg = CropperDialog(self, path, ratio)
        self.wait_window(dlg)
        if dlg.result is not None:
            return ("cropped", dlg.result)
        return ("cancel", None)

    # ── Sidebar ───────────────────────────────────────────────────────────────

    def _refresh_sidebar(self):
        name = self._get_field("name", self._basic_vars) if hasattr(self, "_basic_vars") else ""
        self._sidebar_name.configure(text=name or "—")
        self._sidebar_tokens.configure(text=f"~{token_estimate(self._card):,}")

    def _get_field(self, key: str, var_dict: dict) -> str:
        if key not in var_dict:
            return ""
        w = var_dict[key]
        return w.get("1.0", "end").rstrip("\n") if isinstance(w, ctk.CTkTextbox) else w.get()

    # ── Card I/O ──────────────────────────────────────────────────────────────

    def _new_card(self):
        if not messagebox.askyesno("New Card", "Discard current card and start fresh?"):
            return
        self._card = empty_card()
        self._avatar_path = None
        self._avatar_crop = None
        self._avatar_warn = False
        self._expressions = {e: None for e in EXPRESSIONS}
        self._expr_crops  = {e: None for e in EXPRESSIONS}
        self._expr_warn   = {e: False for e in EXPRESSIONS}
        self._load_card_into_ui()
        self._set_status("New card created.")

    def _import_menu(self):
        path_str = filedialog.askopenfilename(title="Import character card",
                                               filetypes=CARD_TYPES)
        if not path_str:
            return
        path = Path(path_str)
        try:
            if path.suffix.lower() == ".png":
                raw = read_png_card(path)
                self._avatar_path = path
                self._avatar_crop = None
                self._avatar_warn = False
                self._update_avatar_preview()
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
                w.delete("1.0", "end"); w.insert("1.0", str(val or ""))
            else:
                w.delete(0, "end"); w.insert(0, str(val or ""))

        for k in ["name", "description", "personality", "scenario", "first_mes"]:
            if k in self._basic_vars:
                _set(self._basic_vars[k], d.get(k, ""))
        for k in ["mes_example", "system_prompt", "post_history_instructions", "creator_notes"]:
            if k in self._adv_vars:
                _set(self._adv_vars[k], d.get(k, ""))
        _set(self._adv_vars["tags"], ", ".join(d.get("tags", [])))
        _set(self._adv_vars["creator"], d.get("creator", ""))
        _set(self._adv_vars["character_version"], d.get("character_version", ""))

        self._greetings_list.delete(0, "end")
        for i, g in enumerate(d.get("alternate_greetings", [])):
            self._greetings_list.insert("end", f"{i+1}. {g[:60].replace(chr(10), ' ')}")

        # Reset expression slots
        for expr in EXPRESSIONS:
            self._expressions[expr] = None
            self._expr_crops[expr]  = None
            self._expr_warn[expr]   = False
            self._expr_slots[expr].set_image(None)

        self._refresh_sidebar()

    def _collect_card(self) -> dict:
        d = self._card["data"]
        def _get(w):
            return w.get("1.0", "end").rstrip("\n") if isinstance(w, ctk.CTkTextbox) else w.get().strip()
        for k in ["name", "description", "personality", "scenario", "first_mes"]:
            d[k] = _get(self._basic_vars[k])
        for k in ["mes_example", "system_prompt", "post_history_instructions", "creator_notes"]:
            d[k] = _get(self._adv_vars[k])
        d["creator"]           = _get(self._adv_vars["creator"])
        d["character_version"] = _get(self._adv_vars["character_version"])
        d["tags"] = [t.strip() for t in _get(self._adv_vars["tags"]).split(",") if t.strip()]
        self._refresh_sidebar()
        return self._card

    # ── Avatar ────────────────────────────────────────────────────────────────

    def _browse_avatar(self):
        path_str = filedialog.askopenfilename(title="Select avatar image",
                                               filetypes=IMAGE_TYPES)
        if not path_str:
            return
        path   = Path(path_str)
        action, crop = self._check_ratio_prompt(path, AVATAR_RATIO, "avatar images")
        if action == "cancel":
            return
        self._avatar_path = path
        self._avatar_crop = crop
        self._avatar_warn = (action == "keep")
        self._update_avatar_preview()

    def _update_avatar_preview(self):
        if not self._avatar_path or not self._avatar_path.exists():
            aw = self._avatar_preview_w()
            self._avatar_label.configure(image="", text="", fg_color=PLACEHOLDER_COLOR,
                                          width=aw, height=int(aw * 3 / 2))
            self._avatar_warn_label.configure(text="")
            return
        try:
            aw = self._avatar_preview_w()
            img = Image.open(self._avatar_path).convert("RGBA")
            img = _pil_crop_resize(img, self._avatar_crop, None)
            img.thumbnail((aw, int(aw * 3 / 2)), Image.LANCZOS)
            w, h = img.size
            self._avatar_photo = ctk.CTkImage(light_image=img, dark_image=img, size=(w, h))
            self._avatar_label.configure(image=self._avatar_photo, text="",
                                          fg_color="transparent", width=w, height=h)
            self._avatar_warn_label.configure(
                text="⚠ not 2:3, may display wrong" if self._avatar_warn else "")
        except Exception:
            pass

    # ── Greetings ─────────────────────────────────────────────────────────────

    def _greeting_list(self) -> list[str]:
        return list(self._card["data"].get("alternate_greetings", []))

    def _save_greetings(self, gl: list[str]):
        self._card["data"]["alternate_greetings"] = gl
        self._greetings_list.delete(0, "end")
        for i, g in enumerate(gl):
            self._greetings_list.insert("end", f"{i+1}. {g[:60].replace(chr(10), ' ')}")

    def _add_greeting(self):
        dlg = _MultilineDialog(self, "New Greeting", "")
        if dlg.result is not None:
            gl = self._greeting_list(); gl.append(dlg.result); self._save_greetings(gl)

    def _edit_greeting(self):
        sel = self._greetings_list.curselection()
        if not sel: return
        gl  = self._greeting_list()
        dlg = _MultilineDialog(self, "Edit Greeting", gl[sel[0]])
        if dlg.result is not None:
            gl[sel[0]] = dlg.result; self._save_greetings(gl)

    def _remove_greeting(self):
        sel = self._greetings_list.curselection()
        if sel:
            gl = self._greeting_list(); gl.pop(sel[0]); self._save_greetings(gl)

    # ── Expressions ───────────────────────────────────────────────────────────

    def _assign_expression(self, label: str, path: Path | None = None):
        if path is None:
            ps = filedialog.askopenfilename(title=f"Assign image for: {label}",
                                             filetypes=IMAGE_TYPES)
            if not ps: return
            path = Path(ps)

        action, crop = self._check_ratio_prompt(path, EXPR_RATIO, "expression images")
        if action == "cancel":
            return

        self._expressions[label] = path
        self._expr_crops[label]  = crop
        self._expr_warn[label]   = (action == "keep")
        self._refresh_expr_slot(label)
        self._set_status(f"Assigned {label} ← {path.name}")

    def _refresh_expr_slot(self, label: str):
        path = self._expressions[label]
        if not path:
            self._expr_slots[label].set_image(None)
            return
        try:
            img = Image.open(path).convert("RGBA")
            img = _pil_crop_resize(img, self._expr_crops.get(label), None)
            self._expr_slots[label].set_image(img, warn=self._expr_warn.get(label, False))
        except Exception:
            self._expr_slots[label].set_image(None)

    def _clear_expression(self, label: str):
        self._expressions[label] = None
        self._expr_crops[label]  = None
        self._expr_warn[label]   = False
        self._expr_slots[label].set_image(None)

    def _clear_all_expressions(self):
        if not messagebox.askyesno("Clear All", "Remove all assigned expression images?"):
            return
        for expr in EXPRESSIONS:
            self._clear_expression(expr)

    def _auto_assign(self):
        folder_str = filedialog.askdirectory(title="Select folder with expression images")
        if not folder_str: return
        matches = auto_assign_from_folder(Path(folder_str))
        if not matches:
            messagebox.showinfo("Auto-assign", "No matching expression images found."); return
        lines = [f"  {lbl:15} ← {src.name}" for lbl, src in sorted(matches.items())]
        if not messagebox.askyesno("Auto-assign Confirm",
                                    f"Found {len(matches)} matches:\n\n" +
                                    "\n".join(lines) + "\n\nApply?\n\n"
                                    "(Ratio checks skipped for bulk assign — "
                                    "click individual slots to crop if needed.)"):
            return
        for lbl, src in matches.items():
            self._expressions[lbl] = src
            self._expr_crops[lbl]  = None
            self._expr_warn[lbl]   = False
            self._refresh_expr_slot(lbl)
        self._set_status(f"Auto-assigned {len(matches)} expressions.")

    # ── Export ────────────────────────────────────────────────────────────────

    def _export_charx(self):
        card = self._collect_card()
        name = card["data"].get("name") or "character"
        ps   = filedialog.asksaveasfilename(
            title="Export .charx", defaultextension=".charx",
            initialfile=f"{name}.charx",
            filetypes=[("CharX archive", "*.charx"), ("All files", "*.*")])
        if not ps: return
        try:
            result = build_charx(
                card, self._avatar_path, self._avatar_crop,
                self._expressions, self._expr_crops, Path(ps))
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
        ps   = filedialog.asksaveasfilename(
            title="Export PNG card", defaultextension=".png",
            initialfile=f"{name}.png",
            filetypes=[("PNG", "*.png")])
        if not ps: return
        out = Path(ps)
        try:
            img = Image.open(self._avatar_path).convert("RGBA")
            # Apply crop; if cropped, resize to ST's standard
            target = AVATAR_SIZE if self._avatar_crop else None
            img    = _pil_crop_resize(img, self._avatar_crop, target)
            png_bytes = _img_to_png_bytes(img)
            out.write_bytes(write_png_card_bytes(png_bytes, card))
            self._set_status(f"Exported PNG: {out.name}")
            messagebox.showinfo("Export Complete", f"Saved to:\n{out}")
        except Exception as exc:
            messagebox.showerror("Export Error", str(exc))

    # ── Theme ─────────────────────────────────────────────────────────────────

    def _toggle_theme(self):
        if ctk.get_appearance_mode() == "Dark":
            ctk.set_appearance_mode("light")
            self._theme_btn.configure(text="◐ Dark")
        else:
            ctk.set_appearance_mode("dark")
            self._theme_btn.configure(text="◐ Light")

    def _set_status(self, msg: str):
        self._status_var.set(msg)
        self.after(5000, lambda: self._status_var.set("Ready"))


# ── Entry point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    try:
        from tkinterdnd2 import TkinterDnD
        class DnDApp(PersonaPackagerStudio, TkinterDnD.Tk):  # type: ignore
            pass
        app = DnDApp()
    except ImportError:
        app = PersonaPackagerStudio()
    app.mainloop()
