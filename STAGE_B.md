# Stage B: DT-only boot validation

## Result

PASS: the Jetson rebooted with the Stage A merged DTB, returned over SSH,
and its live device tree passed the endpoint, GPIO, mux and lane checks.
The OV5647 module was not installed or loaded. Capture remains untested.

## Changes and recovery

- Added `/boot/dtb/ov5647-stage-b.dtb` (same content as Stage A merged artifact).
- Saved `/boot/extlinux/extlinux.conf.before-ov5647-stage-b`.
- Added `LABEL ov5647-stage-b`, with existing Image/initrd and the test DTB.
- Added `modprobe.blacklist=ov5647 module_blacklist=ov5647` to that entry only.
- Temporarily selected it as DEFAULT for this test.
- A oneshot service restored DEFAULT primary on reaching userspace.
  It completed successfully and was subsequently disabled:
  `/etc/systemd/system/ov5647-stage-b-reset-default.service`.
- Final diff against the backup contains only the additional test entry.
  Existing primary and JetsonIO entries remain unchanged.

Current running boot uses the OV5647 tree; the next ordinary reboot selects
the original primary entry. The oneshot is disabled, so selecting the test
entry as default again will not automatically reset that selection unless
the service is re-enabled.

## Evidence

- Previous boot ID: `e6f1e914-62a4-4592-b7d2-0f2212f57112`.
- Test boot ID: `05ef4b39-475a-4bf1-84ca-6d8c7c9841eb`.
- `/proc/cmdline` contains both OV5647 blacklist arguments.
- Live sensor compatible: `nvidia,ov5647`.
- Kernel creates the camera mux child adapter i2c-9 and device `9-0036`.
  This is device-tree enumeration, not proof that the sensor was probed.
- Device `9-0036` has no bound driver; `/sys/module/ov5647` is absent.
- NVCSI subdevice binds to tegra-capture-vi.
- Reciprocal graph, mux/GPIO and all five mode lane checks pass on
  `/sys/firmware/fdt` using `validate_stage_a.py --live`.
- SSH, nvargus-daemon and Docker report active.
- No Oops, kernel panic or BUG report appeared in the targeted kernel-log scan.
- Only `/dev/media0` exists, as expected without the sensor driver.

## Next boundary

Stage C requires driver execution. The current boot has the kernel-level
`module_blacklist=ov5647`, intentionally preventing manual loading too.
A separate controlled boot without that kernel-level block is required before
manual loading (keep userspace autoload suppression). Do not proceed by merely
running insmod on this boot. Runtime driver safety and capture are not established
by Stage B.
