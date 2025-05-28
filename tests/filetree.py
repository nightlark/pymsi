from typing import Dict, List

import pymsi
from pymsi.table import Table


class Directory:
    def __init__(self, id: str, parent_id: str, name: str):
        self.id = id
        self.parent_id = parent_id
        self.name = name
        self.children: List[Directory] = []  # List of child Directory objects
        self.files: List[File] = []     # List of File objects associated with this directory

    def add_child(self, child: "Directory"):
        self.children.append(child)

    def add_file(self, file: "File"):
        self.files.append(file)

    def print_tree(self, indent = 0):
        print(" " * indent + self.name)
        for file in self.files:
            print(" " * (indent + 4) + f"{file.name} ({humanize_size(file.file_size)})")
        for child in self.children:
            child.print_tree(indent + 4)

    def __repr__(self):
        return f"Directory(id={self.id}, name={self.name})"


class File:
    def __init__(self, id: str, component_id: str, name: str, file_size: int):
        self.id = id
        self.component_id = component_id
        self.name = name
        self.file_size = file_size

    def __repr__(self):
        return f"File(id={self.id}, name={self.name}, size={humanize_size(self.file_size)})"
    
def humanize_size(size: int) -> str:
    if size < 1024:
        return f"{size} B"
    elif size < 1024 ** 2:
        return f"{size / 1024:.2f} KiB"
    elif size < 1024 ** 3:
        return f"{size / (1024 ** 2):.2f} MiB"
    else:
        return f"{size / (1024 ** 3):.2f} GiB"


def build_directory_tree(directories: Table):
    # Create a mapping of id -> Directory object.
    dir_map: Dict[str, Directory] = {}
    for row in directories:
        dir_id = row["Directory"]
        parent_id = row["Directory_Parent"]
        name = row["DefaultDir"]
        if '|' in name:
            # If the name contains a pipe, we assume it's a localized name.
            name = name.split('|', 1)[1]
        dir_map[dir_id] = Directory(dir_id, parent_id, name)

    # Identify root directories and assign children.
    root_dirs: List[Directory] = []
    for current_dir in dir_map.values():
        if current_dir.parent_id is None or current_dir.parent_id not in dir_map:
            root_dirs.append(current_dir)
        else:
            dir_map[current_dir.parent_id].add_child(current_dir)

    return root_dirs, dir_map


def build_component_map(components: Table) -> Dict[str, str]:
    return dict([(row["Component"], row["Directory_"]) for row in components])


def assign_files_to_directories(files: Table, comp_map: Dict[str, str], dir_map: Dict[str, Directory]):
    for row in files:
        file_id = row["File"]
        comp_id = row["Component_"]
        file_name = row["FileName"]
        file_size = row["FileSize"]
        if '|' in file_name:
            # If the file name contains a pipe, we assume it's a localized name.
            file_name = file_name.split('|', 1)[1]
        
        file_obj = File(file_id, comp_id, file_name, file_size)
        # Look up the directory via the component mapping.
        if comp_id in comp_map:
            directory_id = comp_map[comp_id]
            if directory_id in dir_map:
                dir_obj = dir_map[directory_id]
                dir_obj.add_file(file_obj)
            else:
                print(f"Warning: Directory id {directory_id} not found in dir_map")
        else:
            print(f"Warning: Component id {comp_id} not mapped to any directory")


if __name__ == "__main__":
    with pymsi.Package("powertoys.msi") as msi:
        root_directories, directory_map = build_directory_tree(msi["Directory"])
        component_mapping = build_component_map(msi["Component"])
        assign_files_to_directories(msi["File"], component_mapping, directory_map)
        for root in root_directories:
            root.print_tree()