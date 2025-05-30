# Based on MSI file format documentation/code from:
# https://github.com/GNOME/msitools/blob/4343c982665c8b2ae8c6791ade9f93fe92caf79c/libmsi/table.c
# https://github.com/mdsteele/rust-msi/blob/master/src/internal/streamname.rs
# https://stackoverflow.com/questions/9734978/view-msi-strings-in-binary


from pathlib import Path
from typing import List

from pymsi.msi.directory import Directory
from pymsi.thirdparty.refinery.cab import CabFolder


def extract_root(root: Directory, output: Path, is_root: bool = True):
    if not output.exists():
        output.mkdir(parents=True, exist_ok=True)

    for component in root.components.values():
        for file in component.files.values():
            if file.media is None:
                continue
            cab_file = file.resolve()
            (output / file.name).write_bytes(cab_file.decompress())

    for child in root.children.values():
        folder_name = child.name
        if is_root:
            if "." in child.id:
                folder_name, guid = child.id.split(".", 1)
                if child.id != folder_name:
                    print(f"Warning: Directory ID '{child.id}' has a GUID suffix ({guid}).")
            else:
                folder_name = child.id
        extract_root(child, output / folder_name, False)


if __name__ == "__main__":
    import asyncio
    import sys
    import traceback

    import pymsi

    if len(sys.argv) < 2:
        print("Usage: python -m pymsi <command> [path_to_msi_file] [output_folder]")

    command = sys.argv[1].lower().strip()

    package = None
    if len(sys.argv) > 2:
        package = pymsi.Package(Path(sys.argv[2]))

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
            msi = pymsi.Msi(package, True)
            msi.pretty_print()
    elif command == "test":
        if package is None:
            print("No MSI file provided. Use 'test <path_to_msi_file>' to check validity.")
        else:
            try:
                pymsi.Msi(package, True)
            except Exception as e:
                print(f"Invalid .msi file: {package.path}")
                traceback.print_exc()
            else:
                print(f"Valid .msi file: {package.path}")
    elif command == "extract":
        if package is None:
            print(
                "No MSI file provided. Use 'extract <path_to_msi_file> [output_folder]' to extract files."
            )
        else:
            output_folder = Path(sys.argv[3]) if len(sys.argv) > 3 else Path.cwd()
            print(f"Loading MSI file: {package.path}")
            msi = pymsi.Msi(package, True)
            folders: List[CabFolder] = []
            for media in msi.medias.values():
                if media.cabinet and media.cabinet.disks:
                    for disk in media.cabinet.disks.values():
                        for directory in disk:
                            for folder in directory.folders:
                                if folder not in folders:
                                    folders.append(folder)
            print(f"Found {len(folders)} folders in .cab files")

            # for idx, folder in enumerate(folders):
            #     print(f"\r{idx + 1} / {total} ({(idx + 1) / total * 100:.1f}%) Decompressing folder: {folder}", end="")
            #     folder.decompress()
            async def decompress_folder(folder, idx, total):
                folder.decompress()
                print(
                    f"\r{idx + 1} / {total} ({(idx + 1) / total * 100:.1f}%) Decompressed folder: {folder}",
                    end="",
                )

            async def decompress_all_folders(folders):
                tasks = []
                for idx, folder in enumerate(folders):
                    task = asyncio.create_task(decompress_folder(folder, idx, len(folders)))
                    tasks.append(task)
                await asyncio.gather(*tasks)

            # Run the async decompression
            asyncio.run(decompress_all_folders(folders))

            print("\nDecompressing folders completed.")
            print(f"Extracting files from {package.path} to {output_folder}")
            extract_root(msi.root, output_folder)
            print(f"Files extracted from {package.path}")
    elif command == "help":
        print(f"pymsi version: {pymsi.__version__}")
        print("Available commands:")
        print("  tables - List all tables in the MSI file")
        print("  dump - Dump the contents of the MSI file")
        print("  test - Check if the file is a valid MSI file")
        print("  extract - Extract files from the MSI file")
        print("  help - Show this help message")
    else:
        print(f"Unknown command: {command}")
        print("Use 'help' to see available commands.")

    if package is not None:
        package.close()
