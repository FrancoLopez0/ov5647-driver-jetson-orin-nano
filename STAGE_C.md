# Stage C: OV5647 runtime and automatic startup

## Outcome

Successful manual loading, RAW capture tests and automatic loading after reboot
on Jetson Linux R36.4.7, kernel 5.15.148-tegra. The sensor appears at I2C 9-0036
and `/dev/video0`. The camera is available at boot; it does not stream continuously.

## Source changes

Based on akandr/ov5647-jetson commit
`6e26830e774c1e9904fb28f698a6fc813ddddea4` (GPL-2.0).
The adapted source is `driver/ov5647.c` locally and
`/home/talos/ov5647-stage-a/driver/ov5647.c` on the target.

- Use `devm_gpio_request_one(..., GPIOF_OUT_INIT_LOW, ...)` to establish enable
  direction and ownership, and release ownership on failed probe/unbind.
- Reject a busy enable GPIO instead of driving another consumer's line.
- Remove the global probe-time GPIO-ownership handoff.
- Use REGCACHE_NONE to prevent stale register reads across power-off/reset.
- Keep experimental register debugfs disabled by default (`enable_debugfs=N`).
  Opt-in debug access is not validated for concurrent streaming/power changes.
- R36 compilation uses explicit include/symbol paths in `build_stage_a.sh`.
  The upstream register tables and device-tree overlay are unchanged.

## Runtime evidence

- Identified chip ID 0x5647 and registered video0 using manual insmod.
- Five frames captured in each of five modes: 2592x1944, 1920x1080,
  1296x972, 640x480, 1280x720. Byte counts and nonconstant pixel content passed.
- Five additional 1080p start/stop cycles of ten frames each passed.
- Exposure response: mean RAW value approximately 987 at 2ms versus 1467 at
  16ms with gain16. Gain response: mean approximately1209 at 2ms with gain64.
  These are scene-dependent sanity checks, not radiometric calibration.
- Module unload/reload followed by capture succeeded.
- A 300-frame 1080p stream completed at approximately30.01fps.
- Autoload test boot ID: `40174d1c-0978-421e-a481-33436706dc9e`.
  No manual loading was performed on that boot; video0 appeared automatically.
- Five post-reboot frames captured at1080p, exposure30000us, gain64.
- SSH, Docker and nvargus-daemon active. Targeted kernel logs showed no capture
  timeout, Oops or panic. The unsigned external module produces a verification/
  kernel-taint warning; this did not prevent loading.

Local `capture_raw.py` records exact byte counts, per-frame statistics and renders
a JPEG. It uses explicit BGGR debayering, approximate black subtraction,
gray-world balance, percentile scaling and gamma. It is not calibrated ISP output.
The photo visibly shows a nearby light-colored surface with marks and image noise.
Only 1080p was visually inspected. LED illumination has not been visually confirmed.

## Installed configuration

- Module: `/lib/modules/5.15.148-tegra/updates/ov5647.ko`
- Module SHA256: `b2543d2841d1663bb4ecdf18af425fb5920d97ebd6a8866948ff2103dfaa4cc2`
- Source SHA256: `89a3a599a21c626cfe5de0eaa0e6a817e3669d5ecfd882a20188be98e476a55a`
- DTB: `/boot/dtb/ov5647-validated.dtb`
- DTB SHA256: `6f85ad997d7dc35a1830dcf9b41d3c2e82407e81bde87cbbd93d5da40110c0eb`
- `/boot/extlinux/extlinux.conf`: `DEFAULT ov5647`, a dedicated entry without
  module blacklists. Original `primary` entry retained.
- Module loaded through its device-tree alias; no capture or insmod startup script.
- Temporary stage B/C/autoload default-reset services are disabled.
- Added packages: v4l-utils and libv4l2rds0. Existing OpenCV4.8.0 used for conversion.

## Capture another photo

Run on the Jetson; choose a new output directory each time:

```sh
python3 /home/talos/ov5647-stage-a/capture_raw.py \
  /home/talos/ov5647-stage-a/my-photo --exposure 30000 --gain 64
```

Produces `photo.raw` (five frames), `photo.jpg` (last frame), and `photo.json`.
No sudo is necessary for user talos, who belongs to the video group.

Download from the host:

```sh
scp jetson:/home/talos/ov5647-stage-a/my-photo/photo.jpg ./photo.jpg
```

Evidence remains under remote `capture-tests/`, `reload-test/`, `autoload-photo/`.
Tests retained roughly half a gigabyte of RAW evidence on the target; remove
only if no longer needed.

## Recovery

At boot choose `primary` to use the original configuration without the OV5647 tree.
If SSH is available, change `DEFAULT ov5647` to `DEFAULT primary` in
`/boot/extlinux/extlinux.conf` and reboot. This leaves test files for diagnosis.
The original backup is `/boot/extlinux/extlinux.conf.before-ov5647-stage-b`;
later backups end in `before-ov5647-stage-c` and `before-ov5647-autoload`.

Do not run the old direct-GPIO probe while the driver is bound. A future kernel
or BSP update requires rebuilding against matching headers/symbols and checking
the device tree again. Argus/ISP capture, long-duration endurance and cold
power-cycle validation remain outside these completed checks.
