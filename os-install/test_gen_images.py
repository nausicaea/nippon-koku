#!/usr/bin/python3

import unittest
import gen_images


class TestParseEfiPartitionInfo(unittest.TestCase):
    def test_parse_efi_partition_info(self):
        fdisk_output = """Disk /cache/debian-13.1.0-arm64-netinst.iso: 736.29 MiB, 772059136 bytes, 1507928 sectors
Units: sectors of 1 * 512 = 512 bytes
Sector size (logical/physical): 512 bytes / 512 bytes
I/O size (minimum/optimal): 512 bytes / 512 bytes
Disklabel type: dos
Disk identifier: 0x00000000

Device                                  Boot   Start     End Sectors  Size Id Type
/cache/debian-13.1.0-arm64-netinst.iso1            0 1499135 1499136  732M 83 Linux
/cache/debian-13.1.0-arm64-netinst.iso2      1499136 1507327    8192    4M ef EFI (FAT-12/16/32)
"""

        start, sectors = gen_images.parse_efi_partition_info(fdisk_output)
        self.assertEqual(start, 1499136)
        self.assertEqual(sectors, 8192)


if __name__ == "__main__":
    unittest.main()
