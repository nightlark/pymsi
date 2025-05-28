from pymsi.category import CATEGORIES_ALL, CATEGORY_IDENTIFIER, CATEGORY_TEXT
from pymsi.column import Column
from pymsi.table import Table

TABLE_COLUMNS = Table(
    "_Columns",
    [
        Column("Table").mark_primary_key().string(64),
        Column("Number").mark_primary_key().i16(),
        Column("Name").string(64),
        Column("Type").i16(),
    ],
)

TABLE_TABLES = Table(
    "_Tables",
    [
        Column("Name").mark_primary_key().string(64),
    ],
)

TABLEVAL_MIN = -0x7FFF_FFFF
TABLEVAL_MAX = 0x7FFF_FFFF
TABLE_VALIDATION = Table(
    "_Validation",
    [
        Column("Table").mark_primary_key().mark_category(CATEGORY_IDENTIFIER).string(32),
        Column("Column").mark_primary_key().mark_category(CATEGORY_IDENTIFIER).string(32),
        Column("Nullable").mark_enum_values(["Y", "N"]).string(4),
        Column("MinValue").mark_nullable().mark_range(TABLEVAL_MIN, TABLEVAL_MAX).i32(),
        Column("MaxValue").mark_nullable().mark_range(TABLEVAL_MIN, TABLEVAL_MAX).i32(),
        Column("KeyTable").mark_nullable().mark_category(CATEGORY_IDENTIFIER).string(255),
        Column("KeyColumn").mark_nullable().mark_range(1, 32).i16(),
        Column("Category").mark_nullable().mark_enum_values(CATEGORIES_ALL).string(32),
        Column("Set").mark_nullable().mark_category(CATEGORY_TEXT).string(255),
        Column("Description").mark_nullable().mark_category(CATEGORY_TEXT).string(255),
    ],
)
