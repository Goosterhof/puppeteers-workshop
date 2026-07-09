# The Framewright — exact-resolution cropper

Step 3 of the pipeline. SCAIL-2 motion transfer wants the driving video at the
**exact** generation resolution — this tool makes that mechanical instead of a
judgment call.

```bash
# See where the crop window lands before committing (writes a PNG with the box drawn)
./croptool.py /mnt/c/Users/<you>/Videos/take1.mp4 --preset wan-720p-portrait --preview 3.0

# Nudge and render (30fps to match the target generation)
./croptool.py /mnt/c/Users/<you>/Videos/take1.mp4 --preset wan-720p-portrait \
  --gravity center --shift-x 10 --fps 30
```

Rules it enforces so you don't have to:
- largest crop window of the target aspect (no stretching, no letterboxing)
- even-pixel window, lanczos scale to the exact WxH, `setsar=1`
- optional fixed fps for model pairing
- presets carry the model vocabulary: `wan-720p-portrait`, `ltx2-1080p-landscape`,
  `klein-1024`, … (`--size WxH` for anything else)

Windows source footage lives under `/mnt/c/...` — output lands next to the input
unless `-o` says otherwise, so results are visible from Windows/CapCut immediately.
