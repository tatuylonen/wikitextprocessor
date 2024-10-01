import unittest
from collections import namedtuple
from pathlib import Path
from unittest.mock import patch

from wikitextprocessor import Wtp
from wikitextprocessor.dumpparser import (
    path_is_on_windows_partition,
    process_dump,
)

sdisktype = namedtuple("sdisktype", "fstype mountpoint")


class DumpParserTests(unittest.TestCase):
    def setUp(self):
        self.wtp = Wtp()

    def tearDown(self):
        self.wtp.close_db_conn()

    @patch("psutil.disk_partitions")
    @patch("pathlib.Path.resolve", new=lambda x: x)
    def test_path_is_on_windows_partition_nix(self, mock_disk_partitions):
        partitions = [
            sdisktype("fakelongfsname", "/"),
            sdisktype("ext4", "/home"),
            sdisktype("exfat", "/mnt/windows0"),
            sdisktype("fuseblk", "/mnt/windows1"),
        ]
        mock_disk_partitions.return_value = partitions
        self.assertFalse(path_is_on_windows_partition(Path("/")))
        self.assertFalse(path_is_on_windows_partition(Path("/home")))
        self.assertFalse(path_is_on_windows_partition(Path("/mnt")))
        self.assertTrue(path_is_on_windows_partition(Path("/mnt/windows0")))
        self.assertTrue(path_is_on_windows_partition(Path("/mnt/windows1/foo")))

    @patch("psutil.disk_partitions")
    @patch("pathlib.Path.resolve", new=lambda x: x)
    def test_path_is_on_windows_partition_windows(self, mock_disk_partitions):
        partitions = [
            sdisktype("NTFS", "C:\\"),
            sdisktype("exFAT", "D:\\"),
        ]
        mock_disk_partitions.return_value = partitions
        self.assertTrue(path_is_on_windows_partition(Path("D:\\")))
        self.assertTrue(path_is_on_windows_partition(Path("C:\\Users\\user0")))

    def test_process_dump(self):
        process_dump(
            self.wtp,
            "tests/test-pages-articles.xml.bz2",
            {0, 4, 10, 14, 100, 110, 118, 828},
        )
        self.assertGreater(self.wtp.saved_page_nums(), 0)

    def test_removing_includeonly(self):
        ...
