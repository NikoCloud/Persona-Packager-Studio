# CharX Studio — Milestones

## v1.0 — Current
- Full V2 character card editor (all spec fields)
- 28-slot expression grid with named slots, click/drag-and-drop/auto-assign
- Interactive cropper: free zoom/pan, ratio-locked (2:3 avatar, 1:1 expressions)
- Smart resize: downsample only — never upsample (preserves quality)
- `.charx` export: card + avatar + expressions in one file
- PNG export with embedded metadata

---

## v1.1 — Quality of Life
- [ ] Lorebook / character_book editor (nested entry UI)
- [ ] Unsaved changes warning on close / new card
- [ ] Recent files list
- [ ] Drag-and-drop onto avatar sidebar area

---

## v2.0 — AI Upscaling Integration

### Why
Current export never upsamples (correct behavior), but low-res source art
exports at its native size. AI upscaling produces dramatically better results
than bicubic/LANCZOS for character art and expression sprites.

### Approach — optional dependency, not bundled
The `.exe` stays lean. At startup, CharX Studio detects what's available:

```
Upscaling engines detected:
  ✓ Real-ESRGAN  (pip package found)
  ✗ Topaz Gigapixel AI  (not detected)
  ✗ waifu2x-ncnn  (not detected)
```

When exporting a low-res image that would normally be skipped for resize,
a prompt offers: "Upscale with [detected engine] before export?"

### Candidate engines

| Engine | Best for | Notes |
|--------|----------|-------|
| **Real-ESRGAN** (`realesrgan` pip) | Anime/art sprites | `RealESRGAN_x4plus_anime_6B` model is ideal for character art; runs on CPU or GPU via PyTorch |
| **waifu2x-ncnn-vulkan** | Anime art | Standalone binary, no Python deps, runs on any GPU via Vulkan (AMD/NVIDIA/Intel). Fast. |
| **Topaz Gigapixel AI** | Photorealistic | Proprietary, detect via registry/path |

### waifu2x-ncnn-vulkan — recommended first target
- Standalone `.exe`, cross-vendor GPU via Vulkan (no CUDA required)
- User installs it separately; CharX Studio detects it on PATH or configurable path
- Simple subprocess call: `waifu2x-ncnn-vulkan -i in.png -o out.png -n 2 -s 2`
- No Python/PyTorch overhead; fits the "lean exe" philosophy

### FSR (AMD FidelityFX Super Resolution)
FSR 1.0 is a spatial upscaler designed for real-time GPU rendering pipelines
(HLSL/GLSL shader passes). Not suitable for still image processing without
reimplementing the shader in software (numpy/CUDA). FSR 2/3 require temporal
data (motion vectors). **Not a viable path for this use case.**

### Real-ESRGAN via pip
Viable but adds PyTorch (~500MB) as a runtime dependency. Better as an
optional install than a bundled dep. Detection:
```python
try:
    from realesrgan import RealESRGANer
    HAS_REALESRGAN = True
except ImportError:
    HAS_REALESRGAN = False
```

---

## v2.1 — Lorebook Editor
- Full character_book entry editor
- Import/export standalone `.json` lorebook files
- Merge lorebook from external file into card

---

## v3.0 — Background & Audio Assets
- Background image slot (charx `background` asset type)
- Optional audio asset support
- Live2D placeholder slot (no editing, just packaging)
