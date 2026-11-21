# LCD GUI design sources

Source files of the LCD GUI design canvas (Claude Design): https://claude.ai/artifact/7KPNGRSwvnVB6dZnkezoXJ

- One `.dc.html` file per screen, drawn at the real 320 × 240 px of the 2" ST7789 and shown at 2×. All coordinates and font sizes are real LCD pixels, so they carry straight over to the Pillow code in `melon-pedald`.
- `canvas.json` is the canvas layout (artboard positions and notes).
- The files need the canvas runtime to render, so view them on the canvas link above. They are kept here as the versioned record of the design.

Spec (principles, screens, colours, type scale, Pillow notes): [docs/lcd-gui-design.md](../../docs/lcd-gui-design.md)
