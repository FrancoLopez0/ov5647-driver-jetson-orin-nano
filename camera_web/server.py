"""LAN camera calibration console. Uses the installed OV5647 RAW V4L2 driver."""
import argparse
from collections import deque
import json
import logging
import math
import os
from pathlib import Path
import selectors
import signal
import subprocess
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlsplit

import cv2
import numpy as np

HERE = Path(__file__).resolve().parent
MODES = {0: (2592, 1944, 15), 1: (1920, 1080, 30), 2: (1296, 972, 30),
         3: (640, 480, 90), 4: (1280, 720, 60)}
DEFAULTS = dict(mode=1, fps=30, exposure=30000, gain=64, black=1024,
                white=16000, gamma=2.2, red=1.0, green=1.0, blue=1.0,
                auto_levels=True, auto_wb=False, denoise=False, flip=False,
                preview_fps=10, jpeg_quality=85)
LIMITS = dict(fps=(2, 90), exposure=(131, 499500), gain=(16, 1023), black=(0, 65000),
              white=(64, 65535), gamma=(0.2, 4), red=(0.25, 4), green=(0.25, 4),
              blue=(0.25, 4), preview_fps=(1, 15), jpeg_quality=(40, 95))
INTEGER = {'mode', 'fps', 'exposure', 'gain', 'black', 'white', 'preview_fps', 'jpeg_quality'}
BOOL = {'auto_levels', 'auto_wb', 'denoise', 'flip'}
HARDWARE = {'fps', 'exposure', 'gain'}


def validate(current, change):
    if not isinstance(change, dict) or set(change) - set(DEFAULTS):
        raise ValueError('Unknown settings or invalid settings object')
    config = dict(current)
    for key, value in change.items():
        if key in BOOL:
            if type(value) is not bool:
                raise ValueError(f'{key} must be boolean')
        else:
            if type(value) not in (int, float) or not math.isfinite(value):
                raise ValueError(f'{key} must be a finite number')
            if key in INTEGER and value != int(value):
                raise ValueError(f'{key} must be an integer')
            value = int(value) if key in INTEGER else float(value)
            if key == 'mode':
                if value not in MODES:
                    raise ValueError('Invalid sensor mode')
            elif not LIMITS[key][0] <= value <= LIMITS[key][1]:
                raise ValueError(f'{key} must be in {LIMITS[key]}')
        config[key] = value
    config['fps'] = min(config['fps'], MODES[config['mode']][2])
    config['exposure'] = min(config['exposure'], int(1000000 / config['fps']) - 500)
    if config['white'] <= config['black'] + 32:
        raise ValueError('White level must exceed black level by more than 32')
    return config


class Camera:
    def __init__(self, state_file):
        self.state_file = state_file
        self.cv = threading.Condition(threading.RLock())
        self.config = dict(DEFAULTS)
        if state_file.exists():
            self.config = validate(self.config, json.loads(state_file.read_text()))
        self.generation = 0
        self.hw_revision = 0
        self.raw = None
        self.raw_sequence = 0
        self.jpeg = None
        self.sequence = 0
        self.stats = {}
        self.error = 'Waiting for the first frame'
        self.capture_times = deque(maxlen=60)
        self.processing_times = deque(maxlen=30)
        self.last_frame = 0
        self.applied = None
        self.stop = threading.Event()
        self.threads = [threading.Thread(target=self.acquire, daemon=True),
                        threading.Thread(target=self.process, daemon=True)]

    def start(self):
        cv2.setNumThreads(2)
        for thread in self.threads:
            thread.start()

    def update(self, change):
        with self.cv:
            new = validate(self.config, change)
            if new['mode'] != self.config['mode']:
                self.generation += 1
                self.raw = None
                self.jpeg = None
                self.error = 'Switching sensor mode'
            if any(new[k] != self.config[k] for k in HARDWARE):
                self.hw_revision += 1
            self.config = new
            self.cv.notify_all()
            return self.status()

    def status(self):
        with self.cv:
            fps = lambda values: round((len(values) - 1) / (values[-1] - values[0]), 1) if len(values) > 1 and values[-1] > values[0] else 0
            return dict(settings=dict(self.config), applied=self.applied, defaults=DEFAULTS,
                        modes=[dict(id=i, width=m[0], height=m[1], max_fps=m[2]) for i, m in MODES.items()],
                        error=self.error, stats=dict(self.stats), sequence=self.sequence,
                        capture_fps=fps(self.capture_times), preview_fps=fps(self.processing_times),
                        frame_age=round(time.monotonic() - self.last_frame, 2) if self.last_frame else None)

    def save(self):
        with self.cv:
            temporary = self.state_file.with_suffix('.tmp')
            temporary.write_text(json.dumps(self.config, indent=2) + '\n')
            os.replace(temporary, self.state_file)

    @staticmethod
    def control(config):
        return f"frame_rate={config['fps'] * 1000000},exposure={config['exposure']},gain={config['gain']}"

    def acquire(self):
        while not self.stop.is_set():
            process = None
            selector = selectors.DefaultSelector()
            try:
                with self.cv:
                    config, generation, revision = dict(self.config), self.generation, self.hw_revision
                    self.applied = None
                    self.capture_times.clear()
                width, height, _ = MODES[config['mode']]
                stride = ((width * 2 + 63) // 64) * 64
                size = stride * height
                command = ['v4l2-ctl', '-d', '/dev/video0',
                           f"--set-ctrl=sensor_mode={config['mode']},override_enable=1,{self.control(config)}",
                           f'--set-fmt-video=width={width},height={height},pixelformat=BG10,bytesperline={stride}',
                           '--silent', '--stream-mmap=4', '--stream-to=-']
                process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=None, bufsize=0)
                selector.register(process.stdout, selectors.EVENT_READ)
                buffer = bytearray()
                last_data = time.monotonic()
                while not self.stop.is_set():
                    with self.cv:
                        if generation != self.generation:
                            break
                        current, new_revision = dict(self.config), self.hw_revision
                    if new_revision != revision:
                        subprocess.run(['v4l2-ctl', '-d', '/dev/video0',
                                        '--set-ctrl=' + self.control(current)], check=True, timeout=4)
                        revision, config = new_revision, current
                        with self.cv:
                            self.applied = {k: config[k] for k in ('mode', 'fps', 'exposure', 'gain')}
                    if not selector.select(timeout=0.25):
                        if process.poll() is not None:
                            raise RuntimeError(f'Capture exited with code {process.returncode}')
                        if time.monotonic() - last_data > 8:
                            raise RuntimeError('No RAW frames received for 8 seconds')
                        continue
                    chunk = os.read(process.stdout.fileno(), min(size - len(buffer), 1048576))
                    if not chunk:
                        raise RuntimeError(f'Capture pipe closed (code {process.poll()})')
                    buffer.extend(chunk)
                    last_data = time.monotonic()
                    if len(buffer) == size:
                        frame = np.frombuffer(buffer, dtype='<u2').reshape(height, stride // 2)[:, :width].copy()
                        buffer = bytearray()
                        with self.cv:
                            self.raw_sequence += 1
                            self.raw = (frame, generation, self.raw_sequence)
                            self.capture_times.append(last_data)
                            self.applied = {k: config[k] for k in ('mode', 'fps', 'exposure', 'gain')}
                            self.cv.notify_all()
            except Exception as error:
                logging.exception('Capture failure')
                with self.cv:
                    self.error = str(error)
                    self.applied = None
                    self.cv.notify_all()
                self.stop.wait(2)
            finally:
                selector.close()
                if process is not None:
                    if process.poll() is None:
                        process.terminate()
                        try:
                            process.wait(timeout=4)
                        except subprocess.TimeoutExpired:
                            process.kill()
                            process.wait(timeout=4)
                    process.stdout.close()

    def process(self):
        previous = 0
        while not self.stop.is_set():
            started = time.monotonic()
            with self.cv:
                self.cv.wait_for(lambda: self.stop.is_set() or (self.raw is not None and self.raw[2] != previous), timeout=1)
                if self.stop.is_set():
                    return
                if self.raw is None or self.raw[2] == previous:
                    continue
                frame, generation, previous = self.raw
                config = dict(self.config)
            try:
                # Debayer before resizing so the mosaic phase is preserved.
                bgr = cv2.cvtColor(frame, cv2.COLOR_BayerBGGR2BGR)
                if bgr.shape[1] > 1280:
                    bgr = cv2.resize(bgr, (1280, round(1280 * bgr.shape[0] / bgr.shape[1])), interpolation=cv2.INTER_AREA)
                image = bgr.astype(np.float32)
                # Odd sampling stride includes all four Bayer phases.
                sample = frame[::7, ::7]
                low, high = np.percentile(sample, (1, 99.5))
                black = float(low) if config['auto_levels'] else config['black']
                image = np.maximum(image - black, 0)
                weights = np.array([config['blue'], config['green'], config['red']], dtype=np.float32)
                if config['auto_wb']:
                    means = image.mean(axis=(0, 1))
                    weights *= np.clip(means.mean() / np.maximum(means, 1), 0.25, 4)
                image *= weights
                white = max(float(np.percentile(image[::4, ::4], 99.5)), 64) if config['auto_levels'] else config['white'] - black
                normalized = np.clip(image / white, 0, 1)
                rendered = (np.power(normalized, 1 / config['gamma']) * 255).astype(np.uint8)
                if config['denoise']:
                    rendered = cv2.GaussianBlur(rendered, (3, 3), 0)
                if config['flip']:
                    rendered = cv2.flip(rendered, -1)
                success, jpeg = cv2.imencode('.jpg', rendered, [cv2.IMWRITE_JPEG_QUALITY, config['jpeg_quality']])
                if not success:
                    raise RuntimeError('JPEG encoding failed')
                bins = np.histogram(sample, bins=64, range=(0, 65536))[0].tolist()
                with self.cv:
                    if generation == self.generation:
                        self.jpeg = jpeg.tobytes()
                        self.sequence += 1
                        self.stats = dict(raw_mean=round(float(sample.mean()), 1), raw_min=int(sample.min()),
                                          raw_max=int(sample.max()), black_used=round(black, 1),
                                          white_used=round(black + white, 1),
                                          clipped_percent=round(float(np.mean(sample >= 65000)) * 100, 3),
                                          histogram=bins, width=frame.shape[1], height=frame.shape[0],
                                          jpeg_bytes=len(self.jpeg))
                        self.error = None
                        self.last_frame = time.monotonic()
                        self.processing_times.append(self.last_frame)
                        self.cv.notify_all()
            except Exception as error:
                logging.exception('Preview failure')
                with self.cv:
                    self.error = str(error)
            self.stop.wait(max(0, 1 / config['preview_fps'] - (time.monotonic() - started)))


class Handler(BaseHTTPRequestHandler):
    protocol_version = 'HTTP/1.1'

    def respond(self, code, content, kind='application/json', headers=None):
        self.send_response(code)
        self.send_header('Content-Type', kind)
        self.send_header('Content-Length', str(len(content)))
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Content-Type-Options', 'nosniff')
        for key, value in (headers or {}).items():
            self.send_header(key, value)
        self.end_headers()
        self.wfile.write(content)

    def do_GET(self):
        camera = self.server.camera
        path = urlsplit(self.path).path
        try:
            if path == '/':
                self.respond(200, (HERE / 'index.html').read_bytes(), 'text/html; charset=utf-8')
            elif path == '/api/status':
                self.respond(200, json.dumps(camera.status()).encode())
            elif path == '/api/calibration':
                self.respond(200, json.dumps(camera.status()['settings'], indent=2).encode(),
                             headers={'Content-Disposition': 'attachment; filename="calibration.json"'})
            elif path == '/snapshot.jpg':
                with camera.cv:
                    jpeg = camera.jpeg
                if jpeg is None:
                    self.respond(503, b'{"error":"No frame available"}')
                else:
                    self.respond(200, jpeg, 'image/jpeg', {'Content-Disposition': 'attachment; filename="camera.jpg"'})
            elif path == '/stream.mjpg':
                self.connection.settimeout(15)
                self.send_response(200)
                self.send_header('Content-Type', 'multipart/x-mixed-replace; boundary=frame')
                self.send_header('Cache-Control', 'no-store')
                self.send_header('Connection', 'close')
                self.end_headers()
                self.close_connection = True
                sequence = -1
                while not camera.stop.is_set():
                    with camera.cv:
                        camera.cv.wait_for(lambda: camera.stop.is_set() or (camera.jpeg is not None and camera.sequence != sequence), timeout=5)
                        if camera.jpeg is None or sequence == camera.sequence:
                            continue
                        jpeg, sequence = camera.jpeg, camera.sequence
                    self.wfile.write(b'--frame\r\nContent-Type: image/jpeg\r\nContent-Length: ' + str(len(jpeg)).encode() + b'\r\n\r\n' + jpeg + b'\r\n')
                    self.wfile.flush()
            else:
                self.respond(404, b'{"error":"Not found"}')
        except (BrokenPipeError, ConnectionResetError, TimeoutError):
            pass

    def do_POST(self):
        try:
            # Prevent a different website from silently changing LAN settings.
            origin = self.headers.get('Origin')
            if origin and urlsplit(origin).netloc != self.headers.get('Host'):
                raise ValueError('Cross-origin changes are not allowed')
            if self.headers.get('Content-Type', '').split(';')[0] != 'application/json':
                raise ValueError('Content-Type must be application/json')
            size = int(self.headers.get('Content-Length', '0'))
            if not 0 < size <= 8192:
                raise ValueError('Invalid request size')
            data = json.loads(self.rfile.read(size))
            path = urlsplit(self.path).path
            if path == '/api/settings':
                result = self.server.camera.update(data)
            elif path == '/api/save':
                self.server.camera.save()
                result = dict(saved=True)
            else:
                self.respond(404, b'{"error":"Not found"}')
                return
            self.respond(200, json.dumps(result).encode())
        except (ValueError, json.JSONDecodeError) as error:
            self.respond(400, json.dumps(dict(error=str(error))).encode())
        except OSError as error:
            logging.exception('Save failed')
            self.respond(500, json.dumps(dict(error=str(error))).encode())

    def log_message(self, fmt, *args):
        if not self.path.startswith('/api/status'):
            logging.info('%s %s', self.client_address[0], fmt % args)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--host', default='0.0.0.0')
    parser.add_argument('--port', default=8080, type=int)
    parser.add_argument('--state', type=Path, default=HERE / 'calibration.json')
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')
    camera = Camera(args.state)
    server = ThreadingHTTPServer((args.host, args.port), Handler)
    server.daemon_threads = True
    server.camera = camera
    def shutdown(*_):
        camera.stop.set()
        with camera.cv:
            camera.cv.notify_all()
        threading.Thread(target=server.shutdown, daemon=True).start()
    signal.signal(signal.SIGTERM, shutdown)
    signal.signal(signal.SIGINT, shutdown)
    camera.start()
    logging.info('Camera console listening on %s:%d', args.host, args.port)
    try:
        server.serve_forever()
    finally:
        camera.stop.set()
        for thread in camera.threads:
            thread.join(timeout=10)
        server.server_close()


if __name__ == '__main__':
    main()
