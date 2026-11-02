# Camera Lab

Live OV5647 streaming and calibration console on the Jetson's local network.

## Access

- http://192.168.1.35:8080/
- Alternative interface: http://192.168.1.36:8080/

The server listens on all IPv4 interfaces, port8080. These addresses were verified
on the current network and may change with DHCP. There is no login; clients that
can reach the service can view the camera and change shared settings.

## Controls

Hardware: all five sensor modes, frame rate, exposure in microseconds and analog
gain in units of1/16x. The API clamps frame rate to the mode maximum and exposure
below the frame period. Changing resolution restarts the capture process.

Software: black/white levels, gamma, RGB multipliers, gray-world auto white
balance, dynamic levels, light smoothing and180-degree rotation. Preview FPS and
JPEG quality trade off CPU/network use against motion and detail.

Auto levels change contrast per frame and can conceal the visible effect of an
exposure change. Disable them for repeatable brightness comparisons. RAW mean
and histogram are measured before preview processing and sample all Bayer phases.
This is an image-adjustment tool, not a calibrated ISP/radiometric measurement.

Save calibration explicitly to restore settings after a restart. Export JSON
downloads the current settings. Download photo returns the processed preview,
maximum1280pixels wide. View pause is per-browser and does not stop the sensor.

## Architecture

Python standard-library ThreadingHTTPServer, existing OpenCV4.8 and NumPy.
One v4l2-ctl process owns continuous RAW capture. A reader drains the pipe at
sensor rate; a separate worker debayers and JPEG-encodes the latest frame at
preview rate. MJPEG clients share the same JPEG without starting extra captures.
No frontend framework or external CDN is required.

The last frame replaces older frames, avoiding a growing latency queue. A capture
failure is reported in the UI and retried. Systemd owns the whole process group.

## Installed files and service

For a new installation, follow the root README and run
`sudo python3 scripts/install.py web --user "$USER" --port 8080` from the
repository root. `jetson-camera-web.service` is a template: the installer
substitutes the user, installation directory and port before installing it.

```text
/home/talos/camera-web/server.py
/home/talos/camera-web/index.html
/home/talos/camera-web/calibration.json
/etc/systemd/system/jetson-camera-web.service
```

```sh
sudo systemctl status jetson-camera-web
sudo systemctl restart jetson-camera-web
journalctl -u jetson-camera-web -n 50 --no-pager
```

The service runs as talos with video group access and is enabled at boot.
It streams continuously, including when no browser is viewing. Stop it before
using capture_raw.py or another application on video0:

```sh
sudo systemctl stop jetson-camera-web
# Run an independent camera application.
sudo systemctl start jetson-camera-web
```

To deploy updates, copy server.py and index.html into the installed directory,
then restart the service. The generated calibration.json is not overwritten.

## Verification

Ran `check_web.py http://192.168.1.35:8080` from the Windows PC:

- HTML reachable on LAN; two MJPEG reconnections delivered three valid JPEGs each.
- Resolution changes to all5 modes returned fresh frames of expected dimensions.
- Live exposure/gain update changed RAW brightness; driver control readback matched.
- Invalid settings returned HTTP400.
- Snapshot JPEG and JSON export succeeded.
- Original settings restored and saved after tests.
- Service restart loaded saved calibration and resumed streaming.
- Browser script syntax checked using Node; browser interaction/layout not automated.

Default verified operating point:1080p30 sensor capture, approximately10fps
preview. JSON status is at `/api/status`; settings changes use JSON POST to
`/api/settings`, persistence uses JSON POST to `/api/save`.
