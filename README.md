# OV5647 camera and LAN calibration console for Jetson

Adapted **tegracam OV5647 driver**, CAM0 device-tree overlay and a web console
for live streaming and camera adjustment. The driver was tested on a Jetson
Orin Nano Super with **Jetson Linux R36.4.7 / kernel 5.15.148-tegra**.

## Supported configuration

- P3767-0005 Super module on the P3768 developer-kit carrier.
- Raspberry Pi Camera v1 / Rev1.3-style OV5647 module.
- Camera in **CAM0**, using the correct 15-to-22-pin adapter cable.
- Sensor address0x36, CAM0 I2C mux channel0, two CSI lanes.
- R36.4.7 matching kernel and NVIDIA OOT headers/symbol metadata.

Other boards and releases require adaptation. The installer checks the tested
platform instead of silently applying a mismatched configuration. Connect or
reseat the camera cable with the Jetson powered off.

## Repository layout

```text
driver/
  ov5647.c                    Adapted, tested driver source
  ov5647_mode_tbls.h           Sensor register tables
  Makefile                    R36 external-module build
dt/orin/
  tegra234-p3767-ov5647-overlay.dts
scripts/
  build_driver.sh             Compile and validate, without installing
  install.py                  Manual driver setup, autoload promotion, web install
camera_web/
  server.py                   RAW capture, shared MJPEG feed and settings API
  index.html                  Calibration interface; no external CDN
  jetson-camera-web.service   Service template rendered by the installer
  check_web.py                Live HTTP/camera integration checks
capture_raw.py                Standalone RAW capture and JPEG conversion
validate_stage_a.py           Device-tree graph and module symbol checks
```

Driver origins and license: [THIRD_PARTY.md](THIRD_PARTY.md),
[OV5647-LICENSE](OV5647-LICENSE). No prebuilt module or DTB is needed: compile
against the target's matching headers. Runtime calibration and build products
are excluded by `.gitignore`.

## 1. Copy the repository to the Jetson

Clone the repository on the Jetson, or copy it from your PC. For example, from
PowerShell in this directory:

```powershell
ssh jetson 'mkdir -p ~/jetson_camera'
scp -r driver dt scripts camera_web validate_stage_a.py capture_raw.py OV5647-LICENSE README.md jetson:~/jetson_camera/
ssh jetson
```

The following commands run **on the Jetson**:

```sh
cd ~/jetson_camera
uname -r
cat /etc/nv_tegra_release
sudo apt update
sudo apt install -y build-essential device-tree-compiler kmod v4l-utils \
  nvidia-l4t-kernel-headers nvidia-l4t-kernel-oot-headers \
  python3-numpy python3-opencv
/usr/bin/python3 -c 'import cv2, numpy; print(cv2.__version__)'
```

Kernel headers must match the running kernel. If a package update installs a
new kernel, reboot and re-check the versions before building; this recipe is
validated only for R36.4.7 /5.15.148-tegra.

## 2. Build and validate the driver

Run as your regular user, without sudo:

```sh
bash scripts/build_driver.sh
```

This creates:

```text
driver/ov5647.ko
build/ov5647.dtbo
build/ov5647-merged.dtb
```

The overlay is merged onto
`/boot/dtb/kernel_tegra234-p3768-0000+p3767-0005-nv-super.dtb`.
The script checks reciprocal sensor/NVCSI/VI endpoints, GPIO/mux/lane settings,
module vermagic and imported symbol CRCs against installed build metadata.
It does not load a module or change boot settings.

`dtc` may report naming and single-child graph warnings; the exact overlay
with those warnings passed boot and capture tests. A successful build alone
does not prove runtime functionality.

## 3. Install for an initial manual-load test

Inspect the planned changes first:

```sh
sudo python3 scripts/install.py driver --dry-run
sudo python3 scripts/install.py driver
sudo reboot
```

Installation:

- Copies the module to `/lib/modules/5.15.148-tegra/updates/ov5647.ko`.
- Runs `depmod` and copies the merged tree to `/boot/dtb/ov5647-repo.dtb`.
- Backs up `/boot/extlinux/extlinux.conf` to a timestamped sibling file.
- Adds/replaces only the dedicated `ov5647-repo` entry and selects it as DEFAULT.
- Preserves the original `primary` entry for recovery.
- Adds `modprobe.blacklist=ov5647` to the test entry to prevent automatic loading.

After reboot, manually load and inspect the driver:

```sh
sudo modprobe ov5647
v4l2-ctl --list-devices
sudo dmesg | grep -i ov5647
python3 capture_raw.py ~/ov5647-first-photo --exposure 30000 --gain 64
```

Expect chip ID0x5647, `/dev/video0`, and `photo.jpg`, `photo.raw`, `photo.json`
inside the new output directory. Each capture directory must be new.
For a longer test:

```sh
v4l2-ctl -d /dev/video0 \
  --set-ctrl=sensor_mode=1,exposure=30000,gain=64 \
  --set-fmt-video=width=1920,height=1080,pixelformat=BG10 \
  --stream-mmap --stream-count=300 --stream-to=/dev/null
```

The standalone script requires camera device permissions. If needed:

```sh
sudo usermod -aG video "$USER"
```

Then log out and back in. Do not run standalone capture while the web service
or another application owns the camera.

## 4. Enable automatic driver loading

Once manual captures are repeatable:

```sh
sudo python3 scripts/install.py enable --dry-run
sudo python3 scripts/install.py enable
sudo reboot
lsmod | grep ov5647
v4l2-ctl --list-devices
```

The enable command removes the userspace blacklist from the dedicated entry.
The device-tree alias then loads the module automatically. No startup `insmod`
script is required. Original `primary` remains available for recovery.

The installer never reboots automatically. A bad driver can hang the kernel;
the recovery entry must be selected physically if SSH becomes unavailable.

## 5. Install the streaming web console

With the camera working:

```sh
sudo python3 scripts/install.py web --user "$USER" --port 8080 --dry-run
sudo python3 scripts/install.py web --user "$USER" --port 8080
hostname -I
```

Open **`http://<jetson-lan-ip>:8080/`** from your PC.

On the currently configured Jetson, both addresses were verified:

- **http://192.168.1.35:8080/**
- **http://192.168.1.36:8080/**

The installer renders the service template for the selected user and home,
copies the web into `~/camera-web`, grants video-group access and enables
`jetson-camera-web.service`. Existing `calibration.json` is preserved during
updates. No pip packages or frontend build are needed.

### Web features

- Shared MJPEG preview; default1080p30 capture with approximately10fps preview.
- Five resolutions, sensor frame rate, exposure and analog gain.
- Software black/white levels, gamma, RGB gains, gray-world white balance,
  dynamic contrast, light smoothing and rotation.
- RAW histogram/statistics, composition grid, view pause and fullscreen.
- Photo download, JSON export and explicit **Save calibration**.

Exposure is in microseconds; gain16 is1x and64 is4x. Disable **Auto levels**
when comparing brightness during calibration: dynamic contrast can mask the
visual effect of exposure changes. Software image adjustments do not change
sensor RAW data. Saved settings load after service restart or reboot.

The service streams continuously and owns `/dev/video0`, even without viewers.
Preview/photo JPEGs are software processed and at most1280pixels wide.
The service has no login; reachable clients share its view and controls.

### Service management

```sh
sudo systemctl status jetson-camera-web
sudo systemctl restart jetson-camera-web
journalctl -u jetson-camera-web -n 50 --no-pager

# Release the camera for a standalone capture:
sudo systemctl stop jetson-camera-web
# ...run capture_raw.py...
sudo systemctl start jetson-camera-web
```

Run the web integration check from a PC with Python3:

```sh
python camera_web/check_web.py http://<jetson-lan-ip>:8080
```

This temporarily changes modes/exposure/gain, verifies streaming and restores
and saves the original settings. Avoid running it during someone else's calibration.

## Updating

For web changes, rerun `scripts/install.py web`; it preserves saved calibration.
For driver changes, stop the web, rebuild, and repeat the manual-load validation
before enabling automatic loading. An installed module already loaded into the
kernel is not replaced in memory by copying a new `.ko`; reboot or carefully
unload/reload while no camera application is running.

A kernel/BSP update requires matching headers, module rebuild and DTB
revalidation. Do not reuse this binary on a different kernel.

## Recovery and removal

To return to the original camera configuration, choose **primary** in the boot
menu. From a running system, edit `/boot/extlinux/extlinux.conf`, set
`DEFAULT primary`, disable the web and reboot:

```sh
sudo systemctl disable --now jetson-camera-web
sudoedit /boot/extlinux/extlinux.conf
sudo reboot
```

After booting `primary`, verify the module is not loaded. Optional removal:

```sh
sudo rm /lib/modules/5.15.148-tegra/updates/ov5647.ko
sudo depmod -a
```

Keep boot backups until the setup is stable. The current Jetson also retains
the historical `ov5647`, stage B and stage C entries and backups from bring-up;
the reproducible installer uses its own `ov5647-repo` entry.

## Validation and limitations

On the test Jetson: all five RAW modes captured, five additional start/stop
cycles passed, exposure/gain changed brightness, unload/reload succeeded,
300frames at1080p sustained about30fps, and automatic loading plus capture
passed after reboot. The web passed LAN HTTP/MJPEG, resolution switching,
live controls, input validation and settings persistence checks.

The adapted driver explicitly owns/sets the enable GPIO, rejects a busy GPIO,
avoids stale register caching after reset/power-off and disables experimental
register debug access by default.

The packaged build was re-run in an isolated checkout on the Jetson; module
linking, all57 symbol CRCs and device-tree graph checks passed. The new
installer was checked in dry-run mode against the real platform; its boot
configuration preservation, promotion and idempotency tests also passed:

```sh
python3 -m unittest discover -s tests -v
```

These packaging checks did not reinstall or interrupt the active camera/web setup.

Argus/ISP capture and calibrated color tuning are not validated. LED illumination
has not been visually confirmed. The external module is unsigned and generates
a kernel verification/taint warning on the test system.

Bring-up evidence: [STAGE_A.md](STAGE_A.md), [STAGE_B.md](STAGE_B.md),
[STAGE_C.md](STAGE_C.md), [capture-results.json](capture-results.json).
The old stage preparation/install scripts and `probe_camera.py` are retained as
historical diagnostics; use `scripts/` for new installations. Do not run the
direct-GPIO probe while the sensor driver is bound.
