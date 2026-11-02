"""Install locally built OV5647 artifacts or the web service on the Jetson."""
import argparse
from datetime import datetime
import os
from pathlib import Path
import pwd
import re
import shutil
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parent.parent
EXT = Path('/boot/extlinux/extlinux.conf')
LABEL = 'ov5647-repo'
DTB = Path('/boot/dtb/ov5647-repo.dtb')
SERVICE = 'jetson-camera-web.service'


def run(*args):
    return subprocess.check_output(args, text=True).strip()


def boot_config(text, manual):
    # Only our dedicated LABEL is replaced; existing entries and defaults' data
    # are retained. primary is the original recovery entry on this devkit.
    primary = re.search(r'^LABEL primary\n(.*?)(?=^LABEL |\Z)', text, re.M | re.S)
    if not primary:
        raise ValueError('Expected original LABEL primary; configure recovery before installing')
    block = primary.group(1)
    def field(name):
        match = re.search(r'^\s+' + name + r'\s+(.+)$', block, re.M)
        if not match:
            raise ValueError(f'primary entry is missing {name}')
        return match.group(1)
    linux, initrd, append = field('LINUX'), field('INITRD'), field('APPEND')
    for path in (linux, initrd):
        if not Path(path).is_file():
            raise ValueError(f'Missing boot file: {path}')
    append = re.sub(r'\s+(?:modprobe\.blacklist|module_blacklist)=ov5647(?=\s|$)', '', append)
    if manual:
        append += ' modprobe.blacklist=ov5647'
    text = re.sub(r'^LABEL ' + LABEL + r'\n.*?(?=^LABEL |\Z)', '', text, flags=re.M | re.S)
    text, count = re.subn(r'^DEFAULT\s+\S+\s*$', f'DEFAULT {LABEL}', text, count=1, flags=re.M)
    if not count:
        raise ValueError('No DEFAULT entry found')
    return text.rstrip() + f'''

LABEL {LABEL}
    MENU LABEL OV5647 repository driver{' - manual load' if manual else ''}
    LINUX {linux}
    INITRD {initrd}
    FDT {DTB}
    APPEND {append}
'''


def write_boot(text):
    stamp = datetime.now().strftime('%Y%m%d-%H%M%S-%f')
    backup = EXT.with_name(f'extlinux.conf.backup-{stamp}')
    shutil.copy2(EXT, backup)
    temporary = EXT.with_name('extlinux.conf.repo-new')
    temporary.write_text(text)
    shutil.copymode(EXT, temporary)
    os.replace(temporary, EXT)
    os.sync()
    print(f'Boot backup: {backup}')


def require_platform():
    if run('uname', '-r') != '5.15.148-tegra':
        raise ValueError('Only kernel 5.15.148-tegra has been validated')
    release = Path('/etc/nv_tegra_release').read_text()
    if '# R36 ' not in release or 'REVISION: 4.7' not in release:
        raise ValueError('Only Jetson Linux R36.4.7 has been validated')
    if b'nvidia,p3768-0000+p3767-0005-super\0' not in Path('/proc/device-tree/compatible').read_bytes():
        raise ValueError('This installer is validated only on the P3767-0005 Super/P3768 devkit')


def driver(args):
    require_platform()
    # Re-run verification immediately before installation; do not trust a binary
    # copied from a different kernel or a stale merged device tree.
    subprocess.run(['python3', str(ROOT / 'validate_stage_a.py'), str(ROOT),
                    '--dtb', str(ROOT / 'build/ov5647-merged.dtb')], check=True)
    text = boot_config(EXT.read_text(), manual=True)
    module = Path('/lib/modules/5.15.148-tegra/updates/ov5647.ko')
    print(f'Install module: {module}\nInstall DTB: {DTB}\nSelect {LABEL} with automatic loading blocked')
    if args.dry_run:
        print(text)
        return
    if not module.parent.is_dir() or not DTB.parent.is_dir():
        raise ValueError('Expected module and DTB directories are missing')
    if module.exists():
        shutil.copy2(module, module.with_suffix('.ko.before-repo'))
    shutil.copy2(ROOT / 'driver/ov5647.ko', module)
    shutil.copy2(ROOT / 'build/ov5647-merged.dtb', DTB)
    subprocess.run(['depmod', '-a'], check=True)
    write_boot(text)
    print('Reboot when ready. Then load manually with: sudo modprobe ov5647')


def enable(args):
    require_platform()
    if not DTB.is_file() or not Path('/sys/module/ov5647').exists() or not Path('/dev/video0').exists():
        raise ValueError('Boot and verify manual loading/capture before enabling automatic startup')
    if LABEL not in EXT.read_text():
        raise ValueError('Install the repository driver first')
    text = boot_config(EXT.read_text(), manual=False)
    print('Enable automatic OV5647 loading on the next boot')
    if args.dry_run:
        print(text)
    else:
        write_boot(text)


def web(args):
    account = pwd.getpwnam(args.user)
    if account.pw_uid == 0 or not re.fullmatch(r'[a-z_][a-z0-9_-]*', args.user):
        raise ValueError('Choose a regular non-root Linux user')
    target = Path(account.pw_dir) / 'camera-web'
    # Systemd paths are emitted without quoting; restrict deployment to ordinary
    # home paths to avoid whitespace/specifier expansion in unit directives.
    if not re.fullmatch(r'/[a-zA-Z0-9_./-]+', str(target)) or target.is_symlink():
        raise ValueError('Unsupported installation path')
    if not Path(account.pw_dir).is_dir():
        raise ValueError('User home does not exist')
    template = (ROOT / 'camera_web' / SERVICE).read_text()
    unit = template.replace('@USER@', args.user).replace('@INSTALL_DIR@', str(target)).replace('@PORT@', str(args.port))
    print(f'Install web files in {target}; service user {args.user}; HTTP port {args.port}')
    if args.dry_run:
        print(unit)
        return
    if subprocess.run(['systemctl', 'is-active', '--quiet', SERVICE]).returncode == 0:
        subprocess.run(['systemctl', 'stop', SERVICE], check=True)
    subprocess.run(['usermod', '-a', '-G', 'video', args.user], check=True)
    target.mkdir(exist_ok=True)
    os.chown(target, account.pw_uid, account.pw_gid)
    for name in ('server.py', 'index.html'):
        destination = target / name
        if destination.is_symlink():
            raise ValueError(f'Refusing symlink destination: {destination}')
        shutil.copy2(ROOT / 'camera_web' / name, destination)
        os.chown(destination, account.pw_uid, account.pw_gid)
    # Preserve calibration.json on updates.
    unit_path = Path('/etc/systemd/system') / SERVICE
    with tempfile.TemporaryDirectory(prefix='camera-unit-') as temporary:
        candidate = Path(temporary) / SERVICE
        candidate.write_text(unit)
        subprocess.run(['systemd-analyze', 'verify', str(candidate)], check=True)
    if unit_path.exists():
        shutil.copy2(unit_path, unit_path.with_suffix('.service.before-repo'))
    unit_path.write_text(unit)
    unit_path.chmod(0o644)
    subprocess.run(['systemctl', 'daemon-reload'], check=True)
    subprocess.run(['systemctl', 'enable', '--now', SERVICE], check=True)
    print(f'Open http://<jetson-lan-ip>:{args.port}/')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    for name in ('driver', 'enable', 'web'):
        command = commands.add_parser(name)
        command.add_argument('--dry-run', action='store_true')
        if name == 'web':
            command.add_argument('--user', required=True)
            command.add_argument('--port', type=int, default=8080)
    args = parser.parse_args()
    if os.geteuid() != 0 and not args.dry_run:
        parser.error('Run installation with sudo, or use --dry-run')
    if args.command == 'web' and not 1024 <= args.port <= 65535:
        parser.error('Port must be between 1024 and 65535')
    try:
        {'driver': driver, 'enable': enable, 'web': web}[args.command](args)
    except (ValueError, OSError, subprocess.CalledProcessError) as error:
        parser.exit(1, f'Installation failed: {error}\n')


if __name__ == '__main__':
    main()
