"""Select the verified camera entry permanently after autoload capture succeeds."""
from pathlib import Path
import json
import os
import shutil
import subprocess

assert os.geteuid() == 0
assert Path('/sys/module/ov5647').exists()
assert Path('/dev/video0').exists()
assert Path('/sys/bus/i2c/devices/9-0036/driver').resolve().name == 'ov5647'
assert 'blacklist=ov5647' not in Path('/proc/cmdline').read_text()
result = json.loads(Path('/home/talos/ov5647-stage-a/autoload-photo/photo.json').read_text())
assert result['frames'] == 5 and result['unique'] > 4
config = Path('/boot/extlinux/extlinux.conf')
text = config.read_text()
assert 'DEFAULT primary\n' in text and '\nLABEL ov5647\n' in text
subprocess.run(['systemctl', 'disable', 'ov5647-autoload-reset-default.service'], check=True)
temporary = config.with_name('extlinux.conf.promote-new')
temporary.write_text(text.replace('DEFAULT primary\n', 'DEFAULT ov5647\n', 1))
shutil.copymode(config, temporary)
os.replace(temporary, config)
os.sync()
print('DEFAULT ov5647: automatic camera detection enabled for subsequent boots.')
