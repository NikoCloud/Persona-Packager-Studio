# Persona Packager Studio

**A standalone desktop app for creating, editing, and packaging SillyTavern character cards.**

Persona Packager Studio replaces manual tools like desune.moe with a dedicated editor that handles everything in one place — fill in your card metadata, assign expression sprites to named slots, and export a SillyTavern-ready `.charx` file in one click.

Part of the **Persona Workflow** — see the [sister app](#persona-workflow--sister-apps) below.

---

## Download

**[Download Persona Packager Studio v1.0.0 (.exe)](https://github.com/NikoCloud/CharX-Studio/releases/latest)**

No Python, no install — just download and run.

---

## Features

- **Full V2 card editor** — all metadata fields: Name, Description, Personality, Scenario, First Message, Example Messages, System Prompt, Post-History Instructions, Alternate Greetings, Tags, Creator, Character Version, Creator Notes
- **Avatar management** — set your character portrait; the app warns if the ratio is off (SillyTavern expects 2:3) and offers an interactive cropper
- **28-slot expression grid** — named slots for every SillyTavern expression; click to assign, drag-and-drop, or auto-assign from a folder
- **Auto-assign from folder** — fuzzy-matches your existing filenames to the correct expression names automatically; shows a confirmation preview before applying
- **Interactive cropper** — free zoom/pan, ratio-locked crop overlay; works for both avatar (2:3) and expressions (1:1)
- **Smart resize** — downsample only; never upsamples (preserves quality; no low-res blowup)
- **Export `.charx`** — single-file bundle containing card data + avatar + all expressions, ready for one-click SillyTavern import
- **Export PNG** — standalone character card PNG with embedded metadata (no expressions)
- **Import** — read existing cards from PNG (extracts embedded `chara`/`ccv3` metadata) or JSON
- **Token counter** — live estimate of your card's token usage shown in the sidebar
- **Dark / Light mode** toggle

---

## Supported Expressions (28)

| | | | |
|---|---|---|---|
| admiration | amusement | anger | annoyance |
| approval | caring | confusion | curiosity |
| desire | disappointment | disapproval | disgust |
| embarrassment | excitement | fear | gratitude |
| grief | joy | love | nervousness |
| optimism | pride | realization | relief |
| remorse | sadness | surprise | neutral |

---

## Usage

### 1 — Fill in card metadata

The **Basic Info** tab covers the fields you'll always fill in:

- **Name** — character's display name
- **Description** — character background and traits
- **Personality** — short personality summary
- **Scenario** — context/setting for the roleplay
- **First Message** — the character's opening message

The **Advanced** tab covers less common fields:

- Example Messages, System Prompt, Post-History Instructions, Creator Notes
- Alternate Greetings — add multiple opening messages with the `+` button
- Tags, Creator name, Character Version

### 2 — Set the avatar

Click the avatar area or **Browse** to pick an image. If the image isn't 2:3 ratio, the app will ask whether to crop or proceed as-is. The interactive cropper lets you drag and zoom to frame the image exactly how you want.

> The 2:3 portrait format matches SillyTavern's enforced `512×768` avatar size (`AVATAR_WIDTH`/`AVATAR_HEIGHT` in ST's `constants.js`).

### 3 — Assign expressions

Open the **Expressions** tab. You'll see 28 labeled slots — one for each supported SillyTavern expression.

**Options for assigning:**

| Method | How |
|--------|-----|
| Click a slot | Opens a file browser |
| Drag & drop | Drop an image file onto any slot |
| Auto-assign | Click **Auto-assign from folder**, pick the folder containing your expression sprites — the app fuzzy-matches filenames and shows a confirmation dialog |
| Right-click a slot | Opens context menu to clear it |

If a slot's image isn't 1:1 ratio, you'll be offered the cropper. A small `⚠ uncropped` badge appears on slots that were loaded with a ratio mismatch and left uncropped.

### 4 — Export

| Button | Output |
|--------|--------|
| **Export .charx** | Complete bundle: card JSON + avatar + all assigned expressions |
| **Export PNG** | Avatar PNG with embedded V2 card metadata (no expressions) |

After exporting `.charx`, import into SillyTavern via **Characters → Import → select your `.charx` file**.

---

## Crop Workflow

When loading an image that doesn't match the expected ratio, a dialog appears:

- **Crop** — opens the interactive cropper
- **Keep as-is** — uses the full image; a warning badge appears on the slot
- **Cancel** — aborts the load

In the cropper:
- **Drag** to pan
- **Scroll wheel** to zoom
- The colored overlay shows the final crop region
- Click **Confirm** to save the crop (applied at export time, not to the source file)

---

## SillyTavern Import

1. In SillyTavern, go to **Characters**
2. Click **Import**
3. Select your `.charx` file

The card data and all expressions are automatically extracted and registered.

---

## Persona Workflow — Sister Apps

Persona Packager Studio is the final step in a two-app workflow designed for character creators:

| App | Purpose |
|-----|---------|
| **[Persona Asset Forge](https://github.com/NikoCloud/Persona-Asset-Forge)** | Prepare your assets — remove backgrounds from character art and expression sprites, producing clean PNGs ready for packaging |
| **Persona Packager Studio** *(this app)* | Package your clean assets — fill in card metadata, assign expressions to named slots, export a SillyTavern-ready `.charx` file |

**Typical workflow:**
1. Generate or source character art and expression sprites
2. Open **Persona Asset Forge** → remove backgrounds → export clean PNGs
3. Open **Persona Packager Studio** → fill metadata → assign expressions → export `.charx`
4. Import into SillyTavern

---

## Build from Source

```bash
# Install dependencies
pip install -r requirements.txt

# Run from source
python charx_studio.py

# Build .exe (optional)
pip install pyinstaller
pyinstaller --onefile --windowed --name "Persona Packager Studio" charx_studio.py
```

Output: `dist/Persona Packager Studio.exe`

### Requirements

- Python 3.10+
- `customtkinter >= 5.2.0`
- `pillow >= 10.0.0`
- `tkinterdnd2 >= 0.3.0` *(optional — enables drag-and-drop; falls back to click-only without it)*

---

## Notes

- Expression names are always normalized to the correct SillyTavern label on export — your source filenames don't matter
- Crops are non-destructive: stored as normalized coordinates and applied only at export time
- PNG import parses raw `tEXt` chunks directly (not via Pillow's `img.info`) for reliable metadata extraction from all SillyTavern-compatible cards
- Built against the SillyTavern V2 card spec and `charx.js` implementation
- The `embeded://` URI prefix in exported `card.json` is an intentional misspelling preserved for RisuAI compatibility

---

## Roadmap

See [MILESTONES.md](MILESTONES.md) for the full roadmap. Highlights:

- **v1.1** — Lorebook editor, unsaved changes warning, recent files list
- **v2.0** — AI upscaling integration (waifu2x-ncnn-vulkan as first target)
- **v3.0** — Background image and audio asset packaging

---

## License

MIT
