#!/usr/bin/env bash
# Build only: no module installation, boot changes, or reboot.
set -euo pipefail
ROOT=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
BASE=${1:-/boot/dtb/kernel_tegra234-p3768-0000+p3767-0005-nv-super.dtb}
[[ $(uname -r) == 5.15.148-tegra ]] || { echo 'This build is validated only for kernel 5.15.148-tegra.' >&2; exit 1; }
grep -q 'REVISION: 4.7' /etc/nv_tegra_release
grep -q '# R36 ' /etc/nv_tegra_release
[[ -f "$BASE" && -f /usr/src/nvidia/nvidia-oot/Module.symvers ]]
[[ -d "$ROOT" ]]
mkdir -p "$ROOT/build"
make -C "$ROOT/driver" -j2
dtc -@ -I dts -O dtb -o "$ROOT/build/ov5647.dtbo" \
    "$ROOT/dt/orin/tegra234-p3767-ov5647-overlay.dts"
fdtoverlay -i "$BASE" -o "$ROOT/build/ov5647-merged.dtb" "$ROOT/build/ov5647.dtbo"
python3 "$ROOT/validate_stage_a.py" "$ROOT" --dtb "$ROOT/build/ov5647-merged.dtb"
printf 'Build complete. No driver installed. Artifacts: %s/driver/ov5647.ko and %s/build/\n' "$ROOT" "$ROOT"
