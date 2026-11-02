#!/usr/bin/env bash
# Build only. Does not install modules, modify boot configuration or reboot.
set -euo pipefail
ROOT=${1:-/home/talos/ov5647-stage-a}
COMMIT=6e26830e774c1e9904fb28f698a6fc813ddddea4
BASE=/boot/dtb/kernel_tegra234-p3768-0000+p3767-0005-nv-super.dtb
test "$(uname -r)" = 5.15.148-tegra
test "$(git -C "$ROOT" rev-parse HEAD)" = "$COMMIT"
test -f "$BASE"
make -C "$ROOT/driver" \
    KDIR=/lib/modules/5.15.148-tegra/build \
    NVINC=/usr/src/nvidia/nvidia-oot/include \
    EXTRA_SYMBOLS=/usr/src/nvidia/nvidia-oot/Module.symvers \
    COMPAT_INC= -j2
dtc -@ -I dts -O dtb -o "$ROOT/ov5647.dtbo" \
    "$ROOT/dt/orin/tegra234-p3767-ov5647-overlay.dts"
fdtoverlay -i "$BASE" -o "$ROOT/ov5647-merged.dtb" "$ROOT/ov5647.dtbo"
python3 "$ROOT/.github/scripts/check-modes.py"
python3 "$(dirname "$0")/validate_stage_a.py" "$ROOT"
