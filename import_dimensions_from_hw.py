"""
Usage:

1. Download the entire "XY Spacing" sheet via File > Download > CSV.
   Make sure there are no filters enabled on the sheet, I guess?
2. cd shared-data/python
3. pipenv run /path/to/this/script.py ../labware/definitions/3 /path/to/csv.csv
4. cd .. && make format-js
"""

import csv
import dataclasses
import json
import sys
import typing
from decimal import Decimal
from pathlib import Path
from traceback import format_exception, format_exception_only

import pydantic


class DefinitionInfo(pydantic.BaseModel):
    """Info about a single labware definition extracted from a CSV file.

    Field aliases should match the text of the column header in the CSV.

    Fields that are typed like `Decimal | str` are to accommodate values like "N/A"
    in the CSV.
    """

    api_load_name: typing.Annotated[
        str,
        pydantic.Field(alias="api load name"),
    ]

    # Well dimensions:
    hw_depth: typing.Annotated[
        Decimal,
        pydantic.Field(alias="hw depth"),
    ]
    hw_diameter: typing.Annotated[
        Decimal | str,
        pydantic.Field(union_mode="left_to_right", alias="hw diameter"),
    ]
    hw_x_size: typing.Annotated[
        Decimal | str,
        pydantic.Field(union_mode="left_to_right", alias="hw x-size"),
    ]
    hw_y_size: typing.Annotated[
        Decimal | str,
        pydantic.Field(union_mode="left_to_right", alias="hw y-size"),
    ]

    # Labware dimensions:
    hw_length: typing.Annotated[
        Decimal | str,
        pydantic.Field(union_mode="left_to_right", alias="hw length"),
    ]
    hw_width: typing.Annotated[
        Decimal,
        pydantic.Field(alias="hw width"),
    ]
    hw_height: typing.Annotated[
        Decimal,
        pydantic.Field(alias="hw height"),
    ]

    # Well positions:
    hw_x_offset: typing.Annotated[
        Decimal,
        pydantic.Field(alias="hw x-offset"),
    ]
    hw_y_offset: typing.Annotated[
        Decimal,
        pydantic.Field(alias="hw y-offset"),
    ]
    hw_x_spacing: typing.Annotated[
        Decimal | str,
        pydantic.Field(union_mode="left_to_right", alias="hw x-spacing"),
    ]
    hw_y_spacing: typing.Annotated[
        Decimal | str,
        pydantic.Field(union_mode="left_to_right", alias="hw y-spacing"),
    ]


@dataclasses.dataclass
class CSVCoordinate:
    """A position within a CSV file. Indices are 0-based."""

    row_index: int
    col_index: int


def find_csv_header(csv_rows: list[list[str]], header_text: str) -> CSVCoordinate:
    """Find the location of a header within a CSV file."""

    def normalize_header(text: str) -> str:
        return text.lower().replace("\n", " ")

    matching_cells = [
        CSVCoordinate(row_index=row_index, col_index=col_index)
        for row_index, row in enumerate(csv_rows)
        for col_index, cell in enumerate(row)
        if normalize_header(cell) == normalize_header(header_text)
    ]

    if len(matching_cells) != 1:
        raise ValueError(
            f"Expected 1 cell to match {repr(header_text)} but got {len(matching_cells)}."
        )
    return matching_cells[0]


def extract_definition_info_from_csv(
    csv_rows: list[list[str]],
) -> list[tuple[int, DefinitionInfo | pydantic.ValidationError]]:
    """Extract info for all labware definitions mentioned in the CSV.

    Returns a list of (row_index, extraction_result) tuples.
    """
    numbered_rows = list(enumerate(csv_rows))

    header_names = (
        field.alias
        for field in DefinitionInfo.model_fields.values()
        if field.alias is not None
    )
    header_location_by_name = {
        target_header_name: find_csv_header(csv_rows, target_header_name)
        for target_header_name in header_names
    }

    header_row = next(iter(header_location_by_name.values())).row_index
    if not (
        all(
            header.row_index == header_row
            for header in header_location_by_name.values()
        )
    ):
        raise ValueError("Headers are not all on the same row.")
    numbered_rows = numbered_rows[header_row + 1 :]

    result: list[tuple[int, DefinitionInfo | pydantic.ValidationError]] = []
    for row_index, row in numbered_rows:
        values_by_header_name = {
            header_name: row[header_location.col_index]
            for header_name, header_location in header_location_by_name.items()
        }
        if not any(values_by_header_name.values()):
            # Empty row, probably just space at the bottom of the spreadsheet.
            # Silently drop it.
            continue
        try:
            row_result = DefinitionInfo.model_validate(values_by_header_name)
        except pydantic.ValidationError as e:
            row_result = e
        result.append((row_index, row_result))
    return result


def rewrite_definition(
    definition: dict[str, typing.Any], new_info: DefinitionInfo
) -> None:
    """Rewrite `definition` in-place to have dimensional data from `new_info`."""
    if definition["cornerOffsetFromSlot"] != {"x": 0, "y": 0, "z": 0}:
        raise ValueError(
            "Definition has a nonzero cornerOffsetFromSlot"
            " and this script isn't smart enough to account for that."
        )

    for col_index, col in enumerate(definition["ordering"]):
        for row_index, well_name in enumerate(col):
            well = definition["wells"][well_name]

            well["depth"] = new_info.hw_depth

            if "diameter" in well:
                well["diameter"] = new_info.hw_diameter
            elif "xDimension" in well and "yDimension" in well:
                well["xDimension"] = new_info.hw_x_size
                well["yDimension"] = new_info.hw_y_size
            else:
                raise ValueError(
                    "Expected well to either have diameter, or xDimension+yDimension."
                )

            col_count = len(definition["ordering"])
            row_count = len(col)
            if col_count == 1:
                x_spacing = 0
            elif isinstance(new_info.hw_x_spacing, Decimal):
                x_spacing = new_info.hw_x_spacing
            else:
                raise ValueError(
                    f"Labware has multiple columns but CSV did not provide valid x spacing: {new_info.hw_x_spacing}"
                )
            if row_count == 1:
                y_spacing = 0
            elif isinstance(new_info.hw_y_spacing, Decimal):
                y_spacing = new_info.hw_y_spacing
            else:
                raise ValueError(
                    f"Labware has multiple rows but CSV did not provide valid y spacing: {new_info.hw_y_spacing}"
                )

            well["x"] = new_info.hw_x_offset + x_spacing * col_index
            well["y"] = new_info.hw_width - new_info.hw_y_offset - y_spacing * row_index
            well["z"] = new_info.hw_height - new_info.hw_depth

    definition["dimensions"]["xDimension"] = new_info.hw_length
    definition["dimensions"]["yDimension"] = new_info.hw_width
    definition["dimensions"]["zDimension"] = new_info.hw_height


def find_latest_definition(definition_root_dir: Path, load_name: str) -> Path:
    def sort_key(p: Path) -> tuple[bool, int]:
        # 0 < 1 < 2 < ... < "draft"
        if p.stem == "draft":
            return True, 0
        else:
            return False, int(p.stem)

    definition_files = sorted(
        (definition_root_dir / load_name).glob("*.json"),
        key=lambda f: sort_key(f),
    )
    if len(definition_files) == 0:
        raise RuntimeError(f"No definitions found for {load_name}")
    return definition_files[-1]


class DecimalEncoder(json.JSONEncoder):
    """A JSON encoder supporting decimal.Decimal objects.

    Decimal(1.0) in Python -> 1 in JSON
    Decimal(1.1) in Python -> 1.1 in JSON
    """

    def default(self, o: object) -> object:
        if isinstance(o, Decimal):
            as_int = int(o)
            as_float = float(o)
            is_int = as_int == as_float
            return as_int if is_int else as_float
        return super().default(o)


def indent_exception(formatted_exception_parts: list[str], indentation: int) -> str:
    """Indent the output of traceback.format_exception() and related functions.

    Return a single string that can be passed to print(), containing internal newlines
    but no trailing newline.
    """
    lines = (line for part in formatted_exception_parts for line in part.splitlines())
    return "\n".join(" " * indentation + line for line in lines)


if __name__ == "__main__":
    definition_root_path = Path(sys.argv[1])
    csv_path = Path(sys.argv[2])

    with open(csv_path) as csv_file:
        csv_reader = csv.reader(csv_file)
        csv_rows = list(csv_reader)

    successes: list[tuple[int, DefinitionInfo]] = []
    failed_extractions: list[tuple[int, pydantic.ValidationError]] = []
    failed_rewrites: list[tuple[int, DefinitionInfo, Exception]] = []

    for row_index, extraction_result in extract_definition_info_from_csv(csv_rows):
        if isinstance(extraction_result, pydantic.ValidationError):
            failed_extractions.append((row_index, extraction_result))
            continue

        try:
            definition_path = find_latest_definition(
                definition_root_path, extraction_result.api_load_name
            )
            definition = json.loads(definition_path.read_bytes(), parse_float=Decimal)
            rewrite_definition(definition, extraction_result)
        except Exception as exception:
            failed_rewrites.append((row_index, extraction_result, exception))
            continue

        definition_path.write_text(
            json.dumps(
                definition,
                ensure_ascii=False,
                indent=2,
                cls=DecimalEncoder,
            ),
            encoding="utf-8",
        )
        successes.append((row_index, extraction_result))

    print(f"{len(successes)} SUCCESSFUL EXTRACTIONS AND REWRITES")
    for row_index, definition_info in successes:
        print(" " * 2 + definition_info.api_load_name)

    print()

    print(f"{len(failed_extractions)} FAILED EXTRACTIONS")
    for row_index, exception in failed_extractions:
        print(" " * 2 + f"CSV row {row_index+1}:")
        print(indent_exception(format_exception_only(exception), indentation=4))

    print()

    print(f"{len(failed_rewrites)} FAILED REWRITES")
    for row_index, definition_info, exception in failed_rewrites:
        print(" " * 2 + f"CSV row {row_index+1}, {definition_info.api_load_name}:")
        print(indent_exception(format_exception(exception), indentation=4))
