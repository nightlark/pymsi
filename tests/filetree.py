import pymsi

if __name__ == "__main__":
    with pymsi.Package("powertoys.msi") as package:
        msi = pymsi.Msi(package)
        msi.pretty_print()
