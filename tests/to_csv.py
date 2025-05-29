import csv

import pymsi
from pymsi.table import Table


def export_to_csv(table: Table, filename: str):
    fieldnames = table[0].keys()

    with open(filename, "w", newline="") as csvfile:
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(list(table))


with pymsi.Package("powertoys.msi") as msi:
    print(f"MSI file: {msi.filename}")
    print(f"Summary info: {msi.summary}")

    for table in msi:
        print(f"\nTable: {table.name}")
        for column in table.columns:
            print(f"  {column}")

    file_table = msi["File"]
    component_table = msi["Component"]
    directory_table = msi["Directory"]
    export_to_csv(file_table, "file_table.csv")
    export_to_csv(component_table, "component_table.csv")
    export_to_csv(directory_table, "directory_table.csv")
