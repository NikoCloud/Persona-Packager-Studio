# CharX Studio

A standalone desktop app for creating and packaging SillyTavern character cards (`.charx` format).

## Features

- **Full V2 card editor** — all metadata fields: name, description, personality, scenario, first message, example messages, system prompt, alternate greetings, tags, and more
- **Avatar management** — set and preview your character portrait
- **28-slot expression grid** — named slots for every SillyTavern expression; click to assign, drag-and-drop, or auto-assign from a folder
- **Auto-assign** — fuzzy-matches your existing filenames to the correct expression names automatically
- **Export `.charx`** — single-file bundle containing card data + avatar + all expressions, ready for one-click SillyTavern import
- **Export PNG** — standalone character card with embedded metadata (no expressions)
- **Import** existing cards from PNG (extracts embedded metadata) or JSON
- **Dark / Light mode** toggle

## Setup

```bash
pip install -r requirements.txt
python charx_studio.py
```

## Build .exe

```bash
pip install pyinstaller
pyinstaller --onefile --windowed --name "CharX Studio" charx_studio.py
```

Output: `dist/CharX Studio.exe`

## Supported Expressions (28)

`admiration` `amusement` `anger` `annoyance` `approval` `caring` `confusion` `curiosity` `desire` `disappointment` `disapproval` `disgust` `embarrassment` `excitement` `fear` `gratitude` `grief` `joy` `love` `nervousness` `optimism` `pride` `realization` `relief` `remorse` `sadness` `surprise` `neutral`

## SillyTavern Import

Characters → Import → select your `.charx` file. The card data and all expressions are automatically extracted.

## Notes

- Expression names are always normalized to the correct SillyTavern label on export — your source filenames don't matter
- `tkinterdnd2` enables drag-and-drop; the app works without it (click-to-browse only)
- Built against the SillyTavern V2 card spec and `charx.js` implementation
