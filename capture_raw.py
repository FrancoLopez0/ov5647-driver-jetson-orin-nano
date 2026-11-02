"""Capture verified OV5647 RAW10 frames and render a software-processed JPEG."""
import argparse
import json
from pathlib import Path
import subprocess

import cv2
import numpy as np

MODES = [(2592, 1944), (1920, 1080), (1296, 972), (640, 480), (1280, 720)]


def capture(root, name, mode=1, exposure=16000, gain=16, frames=5):
    width, height = MODES[mode]
    stride = ((width * 2 + 63) // 64) * 64
    raw = root / (name + '.raw')
    if raw.exists():
        raise FileExistsError(raw)
    command = ['v4l2-ctl', '-d', '/dev/video0',
               f'--set-ctrl=sensor_mode={mode},exposure={exposure},gain={gain}',
               f'--set-fmt-video=width={width},height={height},pixelformat=BG10,bytesperline={stride}',
               '--get-fmt-video', '--stream-mmap', f'--stream-count={frames}', f'--stream-to={raw}']
    result = subprocess.run(['timeout', '-k', '5', '30', *command], capture_output=True, text=True, timeout=40)
    if result.returncode:
        raise RuntimeError(result.stdout + result.stderr)
    expected = stride * height * frames
    if raw.stat().st_size != expected:
        raise ValueError(f'Expected {expected} bytes, got {raw.stat().st_size}: {result.stdout}')
    data = np.fromfile(raw, dtype='<u2').reshape(frames, height, stride // 2)[:, :, :width]
    last = data[-1]
    stats = dict(name=name, mode=mode, width=width, height=height, stride=stride,
                 frames=frames, exposure=exposure, gain=gain, bytes=expected,
                 minimum=int(last.min()), maximum=int(last.max()), mean=float(last.mean()),
                 std=float(last.std()), unique=int(np.unique(last).size),
                 p01=float(np.percentile(last, 1)), p99=float(np.percentile(last, 99)))
    if stats['unique'] < 4 or stats['std'] < 1:
        raise ValueError(f'Frame lacks image variation: {stats}')
    # Jetson VI uses expanded 16-bit samples for this BG10 capture path.
    # The explicit BGGR alias avoids OpenCV's ambiguous short Bayer names.
    bgr = cv2.cvtColor(last, cv2.COLOR_BayerBGGR2BGR).astype(np.float32)
    black = float(np.percentile(bgr, 1))
    bgr = np.maximum(bgr - black, 0)
    means = bgr.mean(axis=(0, 1))
    bgr *= np.clip(means.mean() / np.maximum(means, 1), 0.5, 3.0)
    white = max(float(np.percentile(bgr, 99.5)), 1.0)
    image = (np.power(np.clip(bgr / white, 0, 1), 1 / 2.2) * 255).astype(np.uint8)
    if not cv2.imwrite(str(root / (name + '.jpg')), image):
        raise RuntimeError('JPEG encoding failed')
    (root / (name + '.json')).write_text(json.dumps(stats, indent=2) + '\n')
    print(json.dumps(stats), flush=True)
    return stats


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('directory', type=Path)
    parser.add_argument('--suite', action='store_true')
    parser.add_argument('--name', default='photo')
    parser.add_argument('--exposure', type=int, default=16000)
    parser.add_argument('--gain', type=int, default=16)
    args = parser.parse_args()
    args.directory.mkdir(exist_ok=False)
    if args.suite:
        results = []
        for mode in range(5):
            results.append(capture(args.directory, f'mode-{mode}', mode, frames=5))
        for n in range(5):
            results.append(capture(args.directory, f'repeat-{n}', frames=10))
        for name, exposure, gain in [('exposure-low', 2000, 16), ('exposure-high', 16000, 16),
                                     ('gain-high', 2000, 64)]:
            results.append(capture(args.directory, name, exposure=exposure, gain=gain, frames=10))
        controls = {x['name']: x['mean'] for x in results}
        assert controls['exposure-high'] > controls['exposure-low'], 'No exposure response'
        assert controls['gain-high'] > controls['exposure-low'], 'No gain response'
        (args.directory / 'results.json').write_text(json.dumps(results, indent=2) + '\n')
        print('PASS mode captures, repeated start/stop, exposure and gain response')
    else:
        capture(args.directory, args.name, exposure=args.exposure, gain=args.gain)
