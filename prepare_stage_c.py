"""Prepare a manual-load boot entry; does not install the sensor module."""
from pathlib import Path
import os
import re
import shutil
import subprocess

config = Path('/boot/extlinux/extlinux.conf')
backup = config.with_name('extlinux.conf.before-ov5647-stage-c')
service = Path('/etc/systemd/system/ov5647-stage-c-reset-default.service')
assert os.geteuid() == 0
assert not backup.exists() and not service.exists()
text = config.read_text()
assert 'DEFAULT primary\n' in text and 'LABEL ov5647-stage-c' not in text
block = re.search(r'^LABEL ov5647-stage-b\n(.*?)(?=^LABEL |\Z)', text, re.M | re.S).group(0)
block = block.replace('LABEL ov5647-stage-b', 'LABEL ov5647-stage-c')
block = block.replace('OV5647 Stage B - DT only, driver blocked', 'OV5647 Stage C - manual driver load')
block = block.replace(' module_blacklist=ov5647', '')
assert 'modprobe.blacklist=ov5647' in block
shutil.copy2(config, backup)
service.write_text('''[Unit]
Description=Restore original boot default after OV5647 manual-load test
After=local-fs.target
Before=multi-user.target
[Service]
Type=oneshot
ExecStart=/usr/bin/sed -i "s/^DEFAULT ov5647-stage-c$/DEFAULT primary/" /boot/extlinux/extlinux.conf
[Install]
WantedBy=multi-user.target
''')
subprocess.run(['systemd-analyze', 'verify', str(service)], check=True)
subprocess.run(['systemctl', 'daemon-reload'], check=True)
subprocess.run(['systemctl', 'enable', service.name], check=True)
new = config.with_name('extlinux.conf.stage-c-new')
new.write_text(text.replace('DEFAULT primary\n', 'DEFAULT ov5647-stage-c\n', 1) + '\n' + block)
shutil.copymode(config, new)
os.replace(new, config)
os.sync()
print(config.read_text())
