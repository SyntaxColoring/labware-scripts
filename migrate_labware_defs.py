# Example usage:
#
# cd shared-data/python
# pipenv run python migrate_labware_defs.py ../labware/{definitions,fixtures}/3/**/*.json
# make -C .. format-js


import json
from pathlib import Path
import sys
from traceback import format_exception
import decimal

from opentrons_shared_data.labware.types import LabwareDefinition as LabwareDefinitionV2


PROBLEM_INDENT = " " * 2


class DecimalEncoder(json.JSONEncoder):
    """A JSON encoder that can encode decimal.Decimal objects."""

    def default(self, o: object) -> object:
        if isinstance(o, decimal.Decimal):
            return float(o)
        else:
            return super().default(o)


class WarningAccumulator:
    def __init__(self) -> None:
        self.messages: list[str] = []

    def warn(self, message: str) -> None:
        self.messages.append(message)


def migrate(definition: LabwareDefinitionV2) -> WarningAccumulator:
    warning_accumulator = WarningAccumulator()

    move_wells_to_quadrant_4(definition, warning_accumulator)
    remove_corner_offset_from_slot(definition, warning_accumulator)

    # To do: add extentCoordinates.

    return warning_accumulator


def remove_corner_offset_from_slot(
    definition: LabwareDefinitionV2, warning_accumulator: WarningAccumulator
) -> None:
    corner_offset_from_slot = definition["cornerOffsetFromSlot"]
    if corner_offset_from_slot == {"x": 0, "y": 0, "z": 0}:
        del definition["cornerOffsetFromSlot"]  # type: ignore
    else:
        warning_accumulator.warn(
            f"cornerOffsetFromSlot is non-zero: {corner_offset_from_slot}."
            f" Investigate the situation and delete cornerOffsetFromSlot manually."
        )


def move_wells_to_quadrant_4(
    definition: LabwareDefinitionV2, warning_accumulator: WarningAccumulator
) -> None:
    back_row_wells = [column[0] for column in definition["ordering"]]
    front_row_wells = [column[-1] for column in definition["ordering"]]
    back_row_inset_distances = [
        definition["dimensions"]["yDimension"] - definition["wells"][well]["y"]
        for well in back_row_wells
    ]
    front_row_inset_distances = [
        definition["wells"][well]["y"] for well in front_row_wells
    ]

    # The distance between wells is generally obvious, standard, and trustworthy.
    # The bounding box of the labware, and the inset distance from the walls of the
    # labware to the wells, less so.
    # When we're moving wells to quadrant 4, we have a choice for whether to trust the
    # existing inset distance from the front wall, or the existing inset distance from
    # the back wall.

    differences = [
        back_distance - front_distance
        for back_distance, front_distance in zip(
            back_row_inset_distances, front_row_inset_distances
        )
    ]
    all_columns_centered = all(difference == 0 for difference in differences)
    if all_columns_centered:
        for well in definition["wells"].values():
            well["y"] = -(definition["dimensions"]["yDimension"] - well["y"])
    else:
        warning_accumulator.warn(
            f"Wells are not centered in the y-direction within the labware bounding box."
            f" Investigate the situation and move the wells to quadrant 4 manually."
            f" Differences in back vs. front insets, per column: {differences}"
        )


if __name__ == "__main__":
    paths = [Path(arg) for arg in sys.argv[1:]]
    problematic_file_count = 0

    for path in paths:
        definition: LabwareDefinitionV2 = json.loads(
            path.read_text(encoding="utf-8"),
            parse_float=decimal.Decimal,
        )
        try:
            accumulated_warnings = migrate(definition)
        except Exception as e:
            print(f"Internal error migrating {path}. It has not been modified.")
            exception_strings = format_exception(e)
            for s in exception_strings:
                print(PROBLEM_INDENT + s, end="")
            problematic_file_count += 1
        else:
            path.write_text(
                json.dumps(
                    definition,
                    indent=2,
                    ensure_ascii=False,
                    cls=DecimalEncoder,
                ),
                encoding="utf-8",
            )
            if accumulated_warnings.messages:
                print(
                    f"Problems while migrating {path}. It has been partially migrated."
                )
                for message in accumulated_warnings.messages:
                    print(PROBLEM_INDENT + message)
                problematic_file_count += 1

    print(
        f"Processed {len(paths)} files, {problematic_file_count} of which need attention."
    )
