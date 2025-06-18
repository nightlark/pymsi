# Based on MSI file format documentation/code from:
# https://github.com/GNOME/msitools/blob/4343c982665c8b2ae8c6791ade9f93fe92caf79c/libmsi/table.c
# https://github.com/mdsteele/rust-msi/blob/master/src/internal/streamname.rs
# https://stackoverflow.com/questions/9734978/view-msi-strings-in-binary


import sys
import traceback
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import List

import pymsi
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


def main():
    if len(sys.argv) < 2:
        print("Usage: pymsi <command> [path_to_msi_file] [output_folder]")
        exit()

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

            total_folders = len(folders)
            print(f"Found {total_folders} folders in .cab files")

            futures = {}
            executor = ThreadPoolExecutor()
            completed_count = 0
            try:
                for folder in folders:
                    future = executor.submit(folder.decompress)
                    futures[future] = folder

                for future in as_completed(futures):
                    try:
                        future.result()
                        completed_count += 1
                        folder = futures[future]
                        print(
                            f"\r{completed_count} / {total_folders} ({completed_count / total_folders * 100:.1f}%) Decompressed folder: {folder}",
                            end="",
                            flush=True,
                        )
                    except KeyboardInterrupt as e:
                        raise e
                    except Exception as e:
                        print(f"\nError decompressing folder {futures[future]}: {e}", flush=True)
            finally:
                for future in futures:
                    future.cancel()
                executor.shutdown(wait=False)

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


if __name__ == "__main__":
    main()
