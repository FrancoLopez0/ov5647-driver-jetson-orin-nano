"""Install tested artifacts and prepare an autoload verification boot."""
from pathlib import Path
import os
import re
import shutil
import subprocess

root = Path('/home/talos/ov5647-stage-a')
config = Path('/boot/extlinux/extlinux.conf')
backup = config.with_name('extlinux.conf.before-ov5647-autoload')
module = Path('/lib/modules/5.15.148-tegra/updates/ov5647.ko')
dtb = Path('/boot/dtb/ov5647-validated.dtb')
service = Path('/etc/systemd/system/ov5647-autoload-reset-default.service')
assert os.geteuid() == 0
assert subprocess.check_output(['uname', '-r'], text=True).strip() == '5.15.148-tegra'
assert all(not p.exists() for p in (backup, module, dtb, service))
assert module.parent.is_dir() and dtb.parent.is_dir()
text = config.read_text()
assert 'DEFAULT primary\n' in text
assert not re.search(r'^LABEL ov5647$', text, re.M)
block = re.search(r'^LABEL ov5647-stage-c\n(.*?)(?=^LABEL |\Z)', text, re.M | re.S).group(0)
block = block.replace('LABEL ov5647-stage-c', 'LABEL ov5647')
block = block.replace('OV5647 Stage C - manual driver load', 'OV5647 camera - validated RAW capture')
block = block.replace('/boot/dtb/ov5647-stage-b.dtb', str(dtb))
block = block.replace(' modprobe.blacklist=ov5647', '')
assert 'blacklist' not in block
shutil.copy2(config, backup)
shutil.copy2(root / 'driver/ov5647.ko', module)
shutil.copy2(root / 'ov5647-merged.dtb', dtb)
subprocess.run(['depmod', '-a', '5.15.148-tegra'], check=True)
# Reset the next default once during the verification boot. After successful
# remote verification the operator can disable this unit and promote ov5647.
service.write_text('''[Unit]
Description=Restore original boot default during OV5647 autoload validation
After=local-fs.target
Before=multi-user.target
[Service]
Type=oneshot
ExecStart=/usr/bin/sed -i "s/^DEFAULT ov5647$/DEFAULT primary/" /boot/extlinux/extlinux.conf
[Install]
WantedBy=multi-user.target
''')
subprocess.run(['systemd-analyze', 'verify', str(service)], check=True)
subprocess.run(['systemctl', 'daemon-reload'], check=True)
subprocess.run(['systemctl', 'enable', service.name], check=True)
new = config.with_name('extlinux.conf.autoload-new')
new.write_text(text.replace('DEFAULT primary\n', 'DEFAULT ov5647\n', 1) + '\n' + block)
shutil.copymode(config, new)
os.replace(new, config)
os.sync()
print('Installed module and DTB. Autoload verification boot is selected.')
