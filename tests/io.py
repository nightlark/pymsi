import mmap
from pathlib import Path

import pytest

import pymsi


def read_package(path_or_bytesio):
    with pymsi.Package(path_or_bytesio) as package:
        msi = pymsi.Msi(package)
        return msi


# Function to read a package using Path
def read_package_path(file_path):
    path = Path(file_path)
    return read_package(path)


# Function to read a package using with open
def read_package_with_open(file_path):
    with open(file_path, "rb") as f:
        return read_package(f)


# Function to read a package using mmap
def read_package_mmap(file_path):
    with open(file_path, "r+b") as f:
        mm = mmap.mmap(f.fileno(), 0)
        return read_package(mm)


# Test cases
@pytest.mark.parametrize(
    "read_package_func", [read_package_path, read_package_with_open, read_package_mmap]
)
def test_read_package(read_package_func):
    test_file = "powertoys.msi"

    msi = read_package_func(test_file)

    size = (msi.package.ole.nb_sect * msi.package.ole.sector_size) + 512

    print(size)


if __name__ == "__main__":
    pytest.main()
