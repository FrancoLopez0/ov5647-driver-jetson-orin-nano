"""Protect original boot entries when preparing or promoting camera entries."""
import importlib.util
from pathlib import Path
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location('camera_installer', Path(__file__).resolve().parents[1] / 'scripts/install.py')
installer = importlib.util.module_from_spec(spec)
spec.loader.exec_module(installer)

ORIGINAL = '''TIMEOUT 30
DEFAULT primary

LABEL primary
    LINUX /boot/Image
    INITRD /boot/initrd
    APPEND ${cbootargs} root=PARTUUID=example rw console=ttyTCU0,115200

LABEL custom-user-entry
    LINUX /boot/user-Image
    INITRD /boot/user-initrd
    FDT /boot/user.dtb
    APPEND root=PARTUUID=user custom=keep
'''


class BootConfigurationTests(unittest.TestCase):
    @patch.object(Path, 'is_file', return_value=True)
    def test_manual_install_preserves_existing_entries(self, _):
        result = installer.boot_config(ORIGINAL, manual=True)
        original_entries = ORIGINAL[ORIGINAL.index('LABEL primary'):].rstrip()
        self.assertIn(original_entries, result)
        self.assertIn('DEFAULT ov5647-repo\n', result)
        self.assertIn('${cbootargs} root=PARTUUID=example rw console=ttyTCU0,115200 modprobe.blacklist=ov5647', result)
        self.assertNotIn('module_blacklist=', result)

    @patch.object(Path, 'is_file', return_value=True)
    def test_reinstall_is_idempotent(self, _):
        first = installer.boot_config(ORIGINAL, manual=True)
        self.assertEqual(first, installer.boot_config(first, manual=True))
        self.assertEqual(first.count('LABEL ov5647-repo\n'), 1)

    @patch.object(Path, 'is_file', return_value=True)
    def test_promotion_removes_only_our_blacklist(self, _):
        text = ORIGINAL.replace('APPEND root=PARTUUID=user', 'APPEND modprobe.blacklist=other root=PARTUUID=user')
        manual = installer.boot_config(text, manual=True)
        enabled = installer.boot_config(manual, manual=False)
        self.assertNotIn('modprobe.blacklist=ov5647', enabled)
        self.assertIn('modprobe.blacklist=other', enabled)
        self.assertEqual(enabled.count('LABEL ov5647-repo\n'), 1)
        self.assertIn('FDT /boot/user.dtb', enabled)

    def test_missing_recovery_entry_rejected(self):
        with self.assertRaises(ValueError):
            installer.boot_config(ORIGINAL.replace('LABEL primary\n', 'LABEL renamed\n'), manual=True)


if __name__ == '__main__':
    unittest.main()
