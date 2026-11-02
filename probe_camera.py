"""Probe camera IDs using the CSI GPIO mapping from NVIDIA's installed overlays."""

import argparse
from pathlib import Path
import subprocess
import time


def probe():
    for address, register, sensor in (
        ("0x36", ("0x30", "0x0a"), "OV5647 (expected 56 47)"),
        ("0x10", ("0x00", "0x00"), "IMX219 (expected 02 19)"),
    ):
        result = subprocess.run(
            ["i2ctransfer", "-y", "2", f"w2@{address}", *register, "r2"],
            capture_output=True, text=True, timeout=5,
        )
        print(f"{sensor}: {result.stdout.strip() or result.stderr.strip()}", flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--hold-seconds", type=float, default=0)
    parser.add_argument("--capture", action="store_true")
    args = parser.parse_args()
    # DT GPIO PH.06 / PAC.00 are CAM0 / CAM1 reset; PCC.03 selects CSI I2C.
    power = subprocess.Popen(["gpioset", "-m", "signal", "gpiochip0", "49=1", "138=1"])
    try:
        time.sleep(1)
        for channel in (0, 1):
            mux = subprocess.Popen(["gpioset", "-m", "signal", "gpiochip1", f"15={channel}"])
            try:
                time.sleep(1)
                print(f"CSI I2C mux channel {channel}", flush=True)
                probe()
                if channel == 0 and args.hold_seconds > 0:
                    print(f"Holding camera enable high for {args.hold_seconds}s; inspect the LED visually.", flush=True)
                    time.sleep(args.hold_seconds)
                if channel == 0 and args.capture:
                    output = Path("/tmp/jetson-camera-attempt.jpg")
                    if output.exists():
                        raise FileExistsError(output)
                    try:
                        result = subprocess.run(
                            ["gst-launch-1.0", "-e", "nvarguscamerasrc", "num-buffers=1",
                             "!", "nvvidconv", "!", "jpegenc", "!", "filesink", f"location={output}"],
                            timeout=20,
                        )
                        valid = output.exists() and output.read_bytes().startswith(b"\xff\xd8")
                        print(f"Capture exit={result.returncode}; valid JPEG={valid}", flush=True)
                    finally:
                        if output.exists() and not output.read_bytes().startswith(b"\xff\xd8"):
                            output.unlink()
            finally:
                mux.terminate()
                mux.wait()
    finally:
        power.terminate()
        power.wait()
