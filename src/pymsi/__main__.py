if __name__ == "__main__":
    import sys
    import traceback

    import pymsi

    if len(sys.argv) < 2:
        print("Usage: python -m pymsi <command> [path_to_msi_file]")

    command = sys.argv[1].lower().strip()

    package = None
    if len(sys.argv) > 2:
        package = pymsi.Package(sys.argv[2])

    if command == "tables":
        if package is None:
            print("No MSI file provided. Use 'tables <path_to_msi_file>' to list tables.")
        else:
            for k in package.ole.root.kids:
                name, is_table = pymsi.streamname.decode_unicode(k.name)
                if is_table:
                    print(f"Table: {name}")
                else:
                    print(f"Stream: {repr(name)}")
    elif command == "dump":
        if package is None:
            print("No MSI file provided. Use 'dump <path_to_msi_file>' to dump contents.")
        else:
            msi = pymsi.Msi(package)
            msi.pretty_print()
    elif command == "test":
        if package is None:
            print("No MSI file provided. Use 'test <path_to_msi_file>' to check validity.")
        else:
            try:
                pymsi.Msi(package)
            except Exception as e:
                print(f"Invalid .msi file: {package.filename}")
                traceback.print_exc()
            else:
                print(f"Valid .msi file: {package.filename}")
    elif command == "help":
        print("Available commands:")
        print("  tables - List all tables in the MSI file")
        print("  dump - Dump the contents of the MSI file")
        print("  test - Check if the file is a valid MSI file")
        print("  help - Show this help message")
    else:
        print(f"Unknown command: {command}")
        print("Use 'help' to see available commands.")

    if package is not None:
        package.close()
