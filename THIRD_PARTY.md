# Third-party source provenance

## OV5647 tegracam driver and device tree

Upstream: https://github.com/akandr/ov5647-jetson

Source commit: `6e26830e774c1e9904fb28f698a6fc813ddddea4`.

- `driver/ov5647.c`: upstream source with local GPIO ownership/direction,
  no-cache and debugfs-default changes documented in STAGE_C.md.
- `driver/ov5647_mode_tbls.h`: unmodified upstream register tables.
- `dt/orin/tegra234-p3767-ov5647-overlay.dts`: unmodified upstream overlay.
- `driver/Makefile`: local R36-specific build recipe.

The imported files retain their original copyright notices. They are licensed
under GPL-2.0; the license text is in `OV5647-LICENSE`. They include work by Artur
Andrzejczak, NVIDIA and Synopsys/Ramiro Oliveira, as described in their headers.

No precompiled module or DTB is required or distributed. Build against the
target's matching kernel and NVIDIA out-of-tree headers and symbol metadata.
