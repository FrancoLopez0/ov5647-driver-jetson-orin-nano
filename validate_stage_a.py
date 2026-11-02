"""Validate build artifacts without loading a module or changing boot files."""
from pathlib import Path
import argparse
import subprocess
import sys

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('root', type=Path)
parser.add_argument('--live', action='store_true')
parser.add_argument('--dtb', type=Path)
args = parser.parse_args()
root = args.root.resolve()
dtb = Path('/sys/firmware/fdt') if args.live else (args.dtb or root / 'ov5647-merged.dtb')


def output(*args):
    return subprocess.check_output(args, text=True).strip()


def prop(node, name, kind="x"):
    return output("fdtget", "-t", kind, str(dtb), node, name)


sensor = "/bus@0/cam_i2cmux/i2c@0/rbpcv1_ov5647_a@36"
csi = "/bus@0/host1x@13e00000/nvcsi@15a00000/channel@0/ports"
pairs = [
    (sensor + "/ports/port@0/endpoint", csi + "/port@0/endpoint@0"),
    (csi + "/port@1/endpoint@1", "/tegra-capture-vi/ports/port@0/endpoint"),
]
for a, b in pairs:
    assert prop(a, "remote-endpoint") == prop(b, "phandle"), (a, b)
    assert prop(b, "remote-endpoint") == prop(a, "phandle"), (b, a)
    print(f"PASS reciprocal graph: {a} <-> {b}")

assert prop(sensor, "reg") == "36"
for endpoint in (pairs[0][0], pairs[0][1], pairs[1][1]):
    assert prop(endpoint, "port-index") == "1"
    assert prop(endpoint, "bus-width") == "2"
gpio = prop("/bus@0/gpio@2200000", "phandle")
aon = prop("/bus@0/gpio@c2f0000", "phandle")
assert prop(sensor, "reset-gpios").split() == [gpio, "3e", "0"]
assert prop("/bus@0/cam_i2cmux", "mux-gpios").split() == [aon, "13", "0"]
assert prop("/bus@0/cam_i2cmux", "i2c-parent") == prop("/bus@0/i2c@3180000", "phandle")
for i in range(5):
    mode = sensor + f"/mode{i}"
    assert prop(mode, "lane_polarity", "s") == "6"
    assert prop(mode, "tegra_sinterface", "s") == "serial_b"
    assert prop(mode, "num_lanes", "s") == "2"
print("PASS GPIO, mux, sensor address, CSI port and five mode lane definitions")

release = output("uname", "-r")
module = root / "driver/ov5647.ko"
assert output("modinfo", "-F", "vermagic", str(module)) == output("modinfo", "-F", "vermagic", "tegra_camera")
symbols = {}
for file in (Path(f"/lib/modules/{release}/build/Module.symvers"),
             Path("/usr/src/nvidia/nvidia-oot/Module.symvers")):
    for line in file.read_text().splitlines():
        fields = line.split()
        if len(fields) >= 2:
            symbols[fields[1]] = int(fields[0], 16)
versions = output("modprobe", "--show-modversions", str(module))
count = 0
for line in versions.splitlines():
    crc, name = line.split()
    assert symbols.get(name) == int(crc, 16), f"CRC mismatch: {name}"
    count += 1
print(f"PASS vermagic and {count} imported symbol CRCs against installed build metadata")
print("Static validation only: no module loaded, no runtime capture tested.")
