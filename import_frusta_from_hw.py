# Instructions
#
# 1. Download "Frustum Definitions" sheet as CSV. Make sure there are no filters enabled, maybe?
# 2. From shared-data/python, run:
#    pipenv run python path/to/script.py ../labware/definitions/3/ path/to/csv.csv
# 3. Review output carefully.
#
# Known caveats:
# - Will not automatically find "sibling" labware, e.g. different tube rack configurations sharing the same tubes.
# - xCount and yCount will not be populated automatically.
# - Sometimes labware with bottom panels will have extra 0-height sections, depending on how they were written in the CSV.
#   They should be manually rewritten.


import csv
import dataclasses
import json
import sys
from typing import Any, Annotated, Iterator, Literal, Sequence, TypeVar
from decimal import Decimal
from pathlib import Path
from traceback import format_exception, format_exception_only
import itertools

from pydantic import BaseModel, Discriminator, Field, TypeAdapter, ValidationError

from opentrons_shared_data.labware.labware_definition import (
    WellSegment as SD_WellSegment,
    ConicalFrustum as SD_ConicalFrustum,
    CuboidalFrustum as SD_CuboidalFrustum,
    SquaredConeSegment as SD_SquaredConeSegment,
    RoundedCuboidSegment as SD_RoundedCuboidSegment,
    SphericalSegment as SD_SphericalSegment,
)


API_LOAD_NAME_HEADER = "API Load Name"
CROSS_SECTION_HEADER = "X-SECTION"


class SectionCommon(BaseModel):
    model_config = {"extra": "forbid"}

    dist_from_bottom: Annotated[Decimal, Field(alias="DIST FROM BOTTOM")]
    pattern_qty: Annotated[int | Literal[""], Field(alias="PATTERN QTY")]


class RectCrossSection(SectionCommon, BaseModel):
    type: Annotated[Literal["RECT"], Field(alias="TYPE")]

    x_dim: Annotated[Decimal, Field(alias="X DIM")]
    y_dim: Annotated[Decimal, Field(alias="Y DIM")]
    diameter: Annotated[Literal[""], Field(alias="DIAMETER")]
    sphere_height: Annotated[Literal[""], Field(alias="SPHERE HEIGHT")]
    sphere_diameter: Annotated[Literal[""], Field(alias="SPHERE DIAMETER")]


class SphericalSection(SectionCommon, BaseModel):
    type: Annotated[Literal["SEMI-SPH"], Field(alias="TYPE")]

    x_dim: Annotated[Literal[""], Field(alias="X DIM")]
    y_dim: Annotated[Literal[""], Field(alias="Y DIM")]
    diameter: Annotated[Literal[""], Field(alias="DIAMETER")]
    sphere_height: Annotated[Decimal, Field(alias="SPHERE HEIGHT")]
    sphere_diameter: Annotated[Decimal, Field(alias="SPHERE DIAMETER")]


class CircleCrossSection(SectionCommon, BaseModel):
    type: Annotated[Literal["CIRCLE"], Field(alias="TYPE")]

    x_dim: Annotated[Literal[""], Field(alias="X DIM")]
    y_dim: Annotated[Literal[""], Field(alias="Y DIM")]
    diameter: Annotated[Decimal, Field(alias="DIAMETER")]
    sphere_height: Annotated[Literal[""], Field(alias="SPHERE HEIGHT")]
    sphere_diameter: Annotated[Literal[""], Field(alias="SPHERE DIAMETER")]


Section = Annotated[
    RectCrossSection | SphericalSection | CircleCrossSection, Discriminator("type")
]
section_type_adapter = TypeAdapter[Section](Section)


def parse(
    csv_rows: list[list[str]],
) -> Iterator[tuple[str, list[Section] | ValidationError]]:
    def get_labware_bands(
        csv_rows: list[list[str]],
    ) -> Iterator[tuple[str, list[list[str]]]]:
        """Iterate over horizontal bands of the CSV that each correspond to a single labware.

        Returns (load_name, rows).
        """
        api_load_name_header = find_csv_header(csv_rows, API_LOAD_NAME_HEADER)
        labware_start_row_indices = [
            row_index
            for (row_index, row) in list(enumerate(csv_rows))[
                api_load_name_header.row_index + 1 :
            ]
            if not (
                row[api_load_name_header.col_index] == ""
                or row[api_load_name_header.col_index].isspace()
            )
        ]
        return (
            (band_rows[0][api_load_name_header.col_index], band_rows)
            for band_rows in split_at_indices(csv_rows, labware_start_row_indices)[1:]
        )

    cross_section_header = find_csv_header(csv_rows, CROSS_SECTION_HEADER)

    for load_name, labware_rows in get_labware_bands(csv_rows):
        labware_columns: list[tuple[str, ...]] = list(zip(*labware_rows))
        field_names = labware_columns[cross_section_header.col_index]
        # Start from the column containing field names, then go right until we reach an empty column.
        columns_to_parse = itertools.takewhile(
            lambda column: any(column),
            labware_columns[cross_section_header.col_index + 1 :],
        )
        try:
            parsed_sections = [
                section_type_adapter.validate_python(dict(zip(field_names, column)))
                for column in columns_to_parse
            ]
            yield load_name, parsed_sections
        except ValidationError as exception:
            yield load_name, exception


def to_geometry_def(sections: list[Section]) -> Iterator[SD_WellSegment]:
    for below, above in itertools.pairwise(sections):
        # We can't infer xCount and yCount from a single pattern qty number.
        # Populate them with obvious placeholder values so a human can fix them.

        has_pattern = above.pattern_qty not in (
            "",
            1,
        ) or below.pattern_qty not in (
            "",
            1,
        )
        x_count, y_count = (99999, 99999) if has_pattern else (1, 1)

        match below, above:
            case RectCrossSection(), RectCrossSection():
                yield SD_CuboidalFrustum(
                    shape="cuboidal",
                    topXDimension=float(above.x_dim),
                    topYDimension=float(above.y_dim),
                    topHeight=float(above.dist_from_bottom),
                    bottomXDimension=float(below.x_dim),
                    bottomYDimension=float(below.y_dim),
                    bottomHeight=float(below.dist_from_bottom),
                    xCount=x_count,
                    yCount=y_count,
                )
            case CircleCrossSection(), CircleCrossSection():
                yield SD_ConicalFrustum(
                    shape="conical",
                    topDiameter=float(above.diameter),
                    topHeight=float(above.dist_from_bottom),
                    bottomDiameter=float(below.diameter),
                    bottomHeight=float(below.dist_from_bottom),
                    xCount=x_count,
                    yCount=y_count,
                )
            case CircleCrossSection(), RectCrossSection():
                # NOTE: Assuming squaredcone because that's correct for
                # usascientific_12_reservoir_22ml, the one labware that does this at
                # the time of writing. For other labware it could theoretically be
                # a roundedcuboid.
                yield SD_SquaredConeSegment(
                    shape="squaredcone",
                    bottomCrossSection="circular",
                    circleDiameter=float(below.diameter),
                    rectangleXDimension=float(above.x_dim),
                    rectangleYDimension=float(above.y_dim),
                    topHeight=float(above.dist_from_bottom),
                    bottomHeight=float(below.dist_from_bottom),
                    xCount=x_count,
                    yCount=y_count,
                )
            case SphericalSection(), _:
                yield SD_SphericalSegment(
                    shape="spherical",
                    radiusOfCurvature=float(below.sphere_diameter / 2),
                    topHeight=float(below.dist_from_bottom + below.sphere_height),
                    bottomHeight=float(below.dist_from_bottom),
                    xCount=x_count,
                    yCount=y_count,
                )
            case _:
                raise ValueError(f"Unhandled section pair:\n{above}\n{below}")


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


T = TypeVar("T")


def split_at_indices(source: list[T], indices: list[int]) -> list[list[T]]:
    return [
        source[begin:end]
        for (begin, end) in itertools.pairwise(itertools.chain([0], indices, [None]))
    ]


def find_latest_definition(definition_root_dir: Path, load_name: str) -> Path:
    definition_files = sorted(
        (definition_root_dir / load_name).glob("*.json"),
        key=lambda f: int(f.stem),
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

    successes: list[str] = []
    parse_failures: list[Exception] = []
    rewrite_failures: list[tuple[str, Exception]] = []

    for load_name, sections in parse(csv_rows):
        if isinstance(sections, Exception):
            parse_failures.append(sections)
            continue

        try:
            definition_path = find_latest_definition(definition_root_path, load_name)
            definition = json.loads(definition_path.read_bytes(), parse_float=Decimal)
            new_sections = list(
                reversed(
                    [
                        section.model_dump(exclude_defaults=True)
                        for section in to_geometry_def(sections)
                    ]
                )
            )
            for key in definition["innerLabwareGeometry"]:
                definition["innerLabwareGeometry"][key] = {"sections": new_sections}
            definition_path.write_text(
                json.dumps(
                    definition,
                    ensure_ascii=False,
                    indent=2,
                    cls=DecimalEncoder,
                ),
                encoding="utf-8",
            )
        except Exception as exception:
            rewrite_failures.append((load_name, exception))
            continue

        successes.append(load_name)

    print(f"{len(successes)} SUCCESSFUL PARSES AND REWRITES")
    for success in successes:
        print(" " * 2 + success)

    print()

    print(f"{len(parse_failures)} FAILED PARSES")
    for index, parse_failure in enumerate(parse_failures):
        print(" " * 2 + str(index + 1))
        print(indent_exception(format_exception(parse_failure), indentation=4))

    print()

    print(f"{len(rewrite_failures)} FAILED REWRITES")
    for index, (load_name, rewrite_failure) in enumerate(rewrite_failures):
        print(" " * 2 + str(index + 1) + " " + load_name)
        print(indent_exception(format_exception(rewrite_failure), indentation=4))
