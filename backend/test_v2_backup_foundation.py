import contextlib
import io
import sys
import tempfile
import unittest
from pathlib import Path


SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from v2_backup_restore import parser, safe_files, verify_backup


class V2BackupFoundationTest(unittest.TestCase):
    def test_file_storage_symlink_is_rejected_before_resolution(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            real = root / "real"
            real.mkdir()
            link = root / "files"
            link.symlink_to(real, target_is_directory=True)
            with self.assertRaisesRegex(ValueError, "symlink"):
                safe_files(link)

    def test_backup_directory_symlink_is_rejected_before_manifest_read(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            real = root / "real"
            real.mkdir()
            link = root / "backup"
            link.symlink_to(real, target_is_directory=True)
            with self.assertRaisesRegex(ValueError, "symlink"):
                verify_backup(link)

    def test_verify_and_restore_require_a_concrete_backup_path(self):
        with contextlib.redirect_stderr(io.StringIO()):
            with self.assertRaises(SystemExit):
                parser().parse_args(["verify"])
            with self.assertRaises(SystemExit):
                parser().parse_args(["restore", "--confirmation", "RESTORE V2 BACKUP"])


if __name__ == "__main__":
    unittest.main()
