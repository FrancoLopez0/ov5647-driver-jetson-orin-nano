"""Prepare a reversible DT-only boot test; run as root on the target."""
from pathlib import Path
import hashlib
import os
import re
import shutil
import subprocess

config = Path('/boot/extlinux/extlinux.conf')
backup = config.with_name('extlinux.conf.before-ov5647-stage-b')
dtb = Path('/boot/dtb/ov5647-stage-b.dtb')
source = Path('/home/talos/ov5647-stage-a/ov5647-merged.dtb')
service = Path('/etc/systemd/system/ov5647-stage-b-reset-default.service')
assert os.geteuid() == 0
assert hashlib.sha256(source.read_bytes()).hexdigest() == '6f85ad997d7dc35a1830dcf9b41d3c2e82407e81bde87cbbd93d5da40110c0eb'
assert all(not p.exists() for p in (backup, dtb, service))
text = config.read_text()
assert re.search(r'^DEFAULT primary$', text, re.M)
assert 'LABEL ov5647-stage-b' not in text
primary = re.search(r'^LABEL primary\n(.*?)(?=^LABEL |\Z)', text, re.M | re.S).group(1)
append = re.search(r'^\s+APPEND (.+)$', primary, re.M).group(1)
assert Path('/boot/Image').is_file() and Path('/boot/initrd').is_file()
shutil.copy2(config, backup)
shutil.copy2(source, dtb)
# Once userspace starts, make the next boot select the original entry.
# This cannot recover a failure that occurs before systemd starts.
service.write_text('''[Unit]
Description=Restore original boot default after OV5647 DT-only test
After=local-fs.target
Before=multi-user.target

[Service]
Type=oneshot
ExecStart=/usr/bin/sed -i "s/^DEFAULT ov5647-stage-b$/DEFAULT primary/" /boot/extlinux/extlinux.conf

[Install]
WantedBy=multi-user.target
''')
subprocess.run(['systemd-analyze', 'verify', str(service)], check=True)
subprocess.run(['systemctl', 'daemon-reload'], check=True)
subprocess.run(['systemctl', 'enable', service.name], check=True)
entry = f'''
LABEL ov5647-stage-b
    MENU LABEL OV5647 Stage B - DT only, driver blocked
    LINUX /boot/Image
    INITRD /boot/initrd
    FDT {dtb}
    APPEND {append} modprobe.blacklist=ov5647 module_blacklist=ov5647
'''
updated = re.sub(r'^DEFAULT primary$', 'DEFAULT ov5647-stage-b', text, flags=re.M) + entry
temporary = config.with_name('extlinux.conf.stage-b-new')
temporary.write_text(updated)
shutil.copymode(config, temporary)
os.replace(temporary, config)
os.sync()
print(f'Backup: {backup}\nTest DTB: {dtb}\n{updated}')
