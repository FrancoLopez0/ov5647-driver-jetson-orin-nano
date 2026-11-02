"""Exercise the deployed camera API and MJPEG feed from another LAN machine."""
import argparse
import json
import time
from urllib.error import HTTPError
from urllib.request import Request, urlopen


def run(base):
    def get(path):
        with urlopen(base + path, timeout=10) as response:
            return json.load(response)

    def post(path, body):
        request = Request(base + path, data=json.dumps(body).encode(),
                          headers={'Content-Type': 'application/json'}, method='POST')
        with urlopen(request, timeout=10) as response:
            return json.load(response)

    def wait(predicate, timeout=20):
        until = time.monotonic() + timeout
        while time.monotonic() < until:
            state = get('/api/status')
            if predicate(state):
                return state
            time.sleep(.3)
        raise AssertionError(state)

    original = get('/api/status')['settings']
    try:
        with urlopen(base + '/', timeout=10) as response:
            assert b'Camera Lab' in response.read()
        print('PASS HTML served over LAN')
        for stream in range(2):
            with urlopen(base + '/stream.mjpg', timeout=15) as response:
                assert 'multipart/x-mixed-replace' in response.headers['Content-Type']
                for frame in range(3):
                    line = response.readline()
                    while not line.startswith(b'--frame'):
                        assert line, 'Stream ended'
                        line = response.readline()
                    headers = {}
                    while True:
                        line = response.readline()
                        if line == b'\r\n':
                            break
                        key, value = line.decode().strip().split(':', 1)
                        headers[key.lower()] = value.strip()
                    jpeg = response.read(int(headers['content-length']))
                    assert jpeg.startswith(b'\xff\xd8') and jpeg.endswith(b'\xff\xd9')
                    assert response.read(2) == b'\r\n'
            print(f'PASS MJPEG reconnect {stream + 1}: three complete JPEGs')
        for mode, width, height in [(0, 2592, 1944), (4, 1280, 720), (2, 1296, 972), (3, 640, 480), (1, 1920, 1080)]:
            before = get('/api/status')['sequence']
            post('/api/settings', {'mode': mode, 'fps': 15, 'exposure': 30000, 'gain': 64})
            state = wait(lambda s: not s['error'] and s['sequence'] > before + 2
                         and s['stats']['width'] == width and s['stats']['height'] == height)
            print(f'PASS resolution {width}x{height}, capture={state["capture_fps"]} fps')
        # Disable dynamic contrast to preserve the meaning of exposure changes.
        post('/api/settings', {'mode': 1, 'fps': 30, 'exposure': 2000, 'gain': 16, 'auto_levels': False})
        time.sleep(2)
        low = get('/api/status')['stats']['raw_mean']
        post('/api/settings', {'exposure': 30000, 'gain': 64})
        time.sleep(2)
        high = get('/api/status')['stats']['raw_mean']
        assert high > low * 1.1, (low, high)
        print(f'PASS live sensor response: RAW mean {low} -> {high}')
        for bad in ({'gain': 0}, {'gamma': 'invalid'}, {'mode': 99}, {'white': 100, 'black': 1000}, {'unknown': 1}):
            try:
                post('/api/settings', bad)
                raise AssertionError(f'Accepted invalid settings: {bad}')
            except HTTPError as error:
                assert error.code == 400
        print('PASS invalid settings rejected')
        with urlopen(base + '/snapshot.jpg', timeout=10) as response:
            assert response.read().startswith(b'\xff\xd8')
        assert isinstance(get('/api/calibration'), dict)
        print('PASS snapshot and calibration export')
    finally:
        post('/api/settings', original)
        post('/api/save', {})
        print('Restored and saved original settings')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('url')
    run(parser.parse_args().url.rstrip('/'))
