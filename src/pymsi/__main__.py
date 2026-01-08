# Based on MSI file format documentation/code from:
# https://github.com/GNOME/msitools/blob/4343c982665c8b2ae8c6791ade9f93fe92caf79c/libmsi/table.c
# https://github.com/mdsteele/rust-msi/blob/master/src/internal/streamname.rs
# https://stackoverflow.com/questions/9734978/view-msi-strings-in-binary

import argparse
import sys
import traceback
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import List

import pymsi
from pymsi.msi.directory import Directory
from pymsi.thirdparty.refinery.cab import CabFolder

# System Folder Properties: https://learn.microsoft.com/en-us/windows/win32/msi/property-reference#system-folder-properties
# Used to install files to special system locations
system_folder_properties = (
    "AdminToolsFolder",
    "AppDataFolder",
    "CommonAppDataFolder",
    "CommonFiles64Folder",
    "CommonFilesFolder",
    "DesktopFolder",
    "FavoritesFolder",
    "FontsFolder",
    "LocalAppDataFolder",
    "MyPicturesFolder",
    "NetHoodFolder",
    "PersonalFolder",
    "PrintHoodFolder",
    "ProgramFiles64Folder",
    "ProgramFilesFolder",
    "ProgramMenuFolder",
    "RecentFolder",
    "SendToFolder",
    "StartMenuFolder",
    "System16Folder",
    "System64Folder",
    "SystemFolder",
    "TempFolder",
    "TemplateFolder",
    "WindowsFolder",
)


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
                # By default, source directory name comes from DefaultDir (exposed here as child.name). If the id matches a known
                # system folder propertyuse the ID as the folder name instead to help users identify files installed to special locations.
                if child.id in system_folder_properties:
                    folder_name = child.id
        extract_root(child, output / folder_name, False)


def run_tables(args, package):
    for k in package.ole.root.kids:
        name, is_table = pymsi.streamname.decode_unicode(k.name)
        if is_table:
            print(f"Table: {name}")
        else:
            print(f"Stream: {repr(name)}")


def run_dump(args, package):
    msi = pymsi.Msi(package, load_data=True, strict=args.strict)
    msi.pretty_print()


def run_test(args, package):
    try:
        pymsi.Msi(package, load_data=True, strict=args.strict)
    except Exception as e:
        print(f"Invalid .msi file: {package.path}")
        traceback.print_exc()
    else:
        print(f"Valid .msi file: {package.path}")


def run_suminfo(args, package):
    summary = package.summary
    print(f"Title: {summary.title() or ''}")
    print(f"Subject: {summary.subject() or ''}")
    print(f"Author: {summary.author() or ''}")
    print(f"UUID: {summary.uuid() or ''}")
    print(f"Architecture: {summary.arch() or ''}")
    print(f"Languages: {summary.languages() or ''}")
    print(f"Creating Application: {summary.creating_application() or ''}")
    print(f"Creation Time: {summary.creation_time() or ''}")
    print(f"Comments: {summary.comments() or ''}")
    print(f"Word Count: {summary.word_count() or ''}")


def run_extract(args, package):
    print(f"Loading MSI file: {package.path}")
    msi = pymsi.Msi(package, load_data=True, strict=args.strict)

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

    msi_root_dir = msi.root
    if len(msi.roots) > 1:
        if not args.root_id:
            print(
                f"Warning: MSI file has multiple root directories: {[r.id for r in msi.roots]}. Defaulting to {msi_root_dir.id}"
            )
        else:
            found_matching_root = False
            for root in msi.roots:
                if root.id == args.root_id:
                    found_matching_root = True
                    msi_root_dir = root
                    break
            if not found_matching_root:
                print(
                    f"Error: Root directory with ID '{args.root_id}' not found. Available root directories: {[r.id for r in msi.roots]}"
                )
                sys.exit(1)

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
    print(f"Extracting files from {package.path} to {args.output_folder}")
    extract_root(msi_root_dir, args.output_folder)
    print(f"Files extracted from {package.path}")


def main():
    parser = argparse.ArgumentParser(description="Inspect and extract Windows MSI installer files")
    parser.add_argument("--version", action="version", version=f"pymsi {pymsi.__version__}")

    subparsers = parser.add_subparsers(
        dest="command",
        metavar="COMMAND",
        required=True,
        help="Description of the available commands",
    )

    # Parent parser for args common to all commands
    msi_parser = argparse.ArgumentParser(add_help=False)
    msi_parser.add_argument("msi_file", type=Path, help="Path to the MSI file")

    # Parent parser for strict mode options
    strict_parser = argparse.ArgumentParser(add_help=False)
    strict_parser.add_argument(
        "--strict",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Enforce strict MSI validation (use --no-strict to relax checks). Default is True.",
    )

    # tables
    tables_parser = subparsers.add_parser(
        "tables", parents=[msi_parser], help="List all tables in the MSI file"
    )
    tables_parser.set_defaults(func=run_tables)

    # dump
    dump_parser = subparsers.add_parser(
        "dump", parents=[msi_parser, strict_parser], help="Dump the contents of the MSI file"
    )
    dump_parser.set_defaults(func=run_dump)

    # test
    test_parser = subparsers.add_parser(
        "test", parents=[msi_parser, strict_parser], help="Check if the file is a valid MSI file"
    )
    test_parser.set_defaults(func=run_test)

    # suminfo
    suminfo_parser = subparsers.add_parser(
        "suminfo", parents=[msi_parser], help="Print summary information"
    )
    suminfo_parser.set_defaults(func=run_suminfo)

    # extract
    extract_parser = subparsers.add_parser(
        "extract",
        parents=[msi_parser, strict_parser],
        help="Extract files from the MSI file",
    )
    extract_parser.add_argument(
        "-o",
        "--output",
        dest="output_folder",
        type=Path,
        default=Path.cwd(),
        help="Output folder (default: current working directory)",
    )
    extract_parser.add_argument(
        "--root-id",
        type=str,
        default=None,
        help="ID of the root directory to extract if an MSI file has multiple root directories (default is TARGETDIR or the first root directory if TARGETDIR is not present)",
    )
    extract_parser.set_defaults(func=run_extract)

    if len(sys.argv) == 1:
        parser.print_help()
        sys.exit(0)

    args = parser.parse_args()

    # Common initialization for package loading
    if hasattr(args, "msi_file"):
        if not args.msi_file.exists():
            print(f"Error: File '{args.msi_file}' not found.")
            sys.exit(1)
        strict = getattr(args, "strict", False)
        package = pymsi.Package(args.msi_file, strict=strict)
        try:
            args.func(args, package)
        except KeyboardInterrupt:
            print("\nOperation cancelled by user.")
            sys.exit(130)
        finally:
            package.close()
    else:
        # Should be unreachable due to argparse's required subcommand enforcement, but just in case:
        parser.print_help()


if __name__ == "__main__":
    main()
