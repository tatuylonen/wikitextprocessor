import unittest
from unittest.mock import patch
from collections import namedtuple
from pathlib import Path

from wikitextprocessor.dumpparser import path_is_on_windows_partition

sdisktype = namedtuple('sdisktype', 'fstype mountpoint')

class DumpParserTests(unittest.TestCase):
    
    @patch('wikitextprocessor.dumpparser.disk_partitions')
    @patch('pathlib.Path.resolve', new = lambda x: x)
    def test_path_is_on_windows_partition_nix(self, mock_disk_partitions):
        partitions = [
            sdisktype("ext4", "/"),
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

    @patch('wikitextprocessor.dumpparser.disk_partitions')
    @patch('pathlib.Path.resolve', new = lambda x: x)
    def test_path_is_on_windows_partition_windows(self, mock_disk_partitions):
        partitions = [
            sdisktype("NTFS", "C:\\"),
            sdisktype("exFAT", "D:\\"),
        ]

        mock_disk_partitions.return_value = partitions
        self.assertTrue(path_is_on_windows_partition(Path("D:\\")))
        self.assertTrue(path_is_on_windows_partition(Path("C:\\Users\\user0")))


