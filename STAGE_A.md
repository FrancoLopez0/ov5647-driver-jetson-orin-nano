# Stage A: OV5647 build and static validation

## Result

PASS on Jetson Linux R36.4.7 / kernel 5.15.148-tegra.
No module was loaded or installed, no boot files changed, and no reboot performed.
This does not establish runtime safety, successful boot with the overlay, or capture.

## Source and build

Repository: https://github.com/akandr/ov5647-jetson

Pinned commit: `6e26830e774c1e9904fb28f698a6fc813ddddea4`.

Remote checkout: `/home/talos/ov5647-stage-a` (detached HEAD).
The upstream C code, tables, overlay and Makefile were not edited.
R36 support for this build is supplied through explicit Makefile variables in
`build_stage_a.sh`: kernel build directory, NVIDIA OOT include directory and
OOT Module.symvers. The R39 compatibility header is not enabled.

Both local scripts were copied into the remote checkout. Reproduce with:

```sh
bash /home/talos/ov5647-stage-a/build_stage_a.sh
```

## Artifacts on the Jetson

| Relative to checkout | SHA-256 |
| --- | --- |
| `driver/ov5647.ko` | `2bf09dc5846ad0698a303ff88c35382f64483314006844b53b556689cfdfafe3` |
| `ov5647.dtbo` | `aa1f34705458b3d38bc8f0d702289350d8fd41627b14ad8e90cd28e7cac60f36` |
| `ov5647-merged.dtb` | `6f85ad997d7dc35a1830dcf9b41d3c2e82407e81bde87cbbd93d5da40110c0eb` |

The merged DTB was generated from the installed board-specific file
`/boot/dtb/kernel_tegra234-p3768-0000+p3767-0005-nv-super.dtb`.
It is a test artifact, not selected for boot.

## Checks performed

- C compilation, modpost and module linking succeeded.
- Module vermagic equals the installed tegra_camera module:
  `5.15.148-tegra SMP preempt mod_unload modversions aarch64`.
- All 57 imported symbol CRCs match installed kernel/OOT build metadata.
- Module dependencies: `tegra-camera,videodev`.
- Overlay compiled and fdtoverlay successfully resolved it against the board DTB.
- Both sensor-to-NVCSI and NVCSI-to-VI endpoint references are reciprocal.
- Mux parent, mux GPIO, enable GPIO, sensor address, CSI port and lane count match expectations.
- All five modes specify serial_b, two lanes and lane polarity 6.
- Upstream check-modes.py passed for mode ordering, geometry and table/overlay consistency.
- ov5647 is absent from lsmod; extlinux DEFAULT remains primary.

## Warnings and limits

- GCC identifies the same 11.4.0 version, but Ubuntu package revisions differ:
  kernel `11.4.0-1ubuntu1~22.04`, current compiler `11.4.0-1ubuntu1~22.04.3`.
  Kbuild emitted its compiler mismatch warning; no C source warnings appeared.
- dtc emitted unit_address_vs_reg and graph_child_address warnings. These concern
  fragment nodes, endpoint/lens naming and single-child graph containers. Merge
  and targeted graph checks passed; this is not a full dt-schema validation.
- Symbol CRC checks are against installed metadata, not a proof of runtime correctness.
- GPIO direction/ownership, register-cache behavior over power cycles, debugfs
  concurrency and cleanup remain review/test items before production use.
- The merged file uses the installed DTB, not a byte-for-byte copy of the live,
  firmware-fixed-up device tree. Boot behavior remains untested.

## Next boundary

Stage B requires a separate boot test entry and a recovery path, with automatic
OV5647 module loading suppressed. Do not run upstream install.sh: it targets R39
on Orin and changes the default entry. Stage A does not authorize Stage B.
