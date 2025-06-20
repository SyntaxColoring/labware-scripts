# Example usage:
#
# cd shared-data/python
# pipenv run python script.py ../labware/{definitions,fixtures}/3/**/*.json
# make -C .. format-js


from copy import deepcopy
import json
from pathlib import Path
import sys
import decimal

class DecimalEncoder(json.JSONEncoder):
    """A JSON encoder that can encode decimal.Decimal objects."""

    def default(self, o: object) -> object:
        if isinstance(o, decimal.Decimal):
            return float(o)
        else:
            return super().default(o)


def migrate(context: str, definition: dict) -> dict:
    if "extents" in definition:
        print(f"{context}: already migrated, ignoring")
        return definition

    if definition["cornerOffsetFromSlot"] != {"x": 0, "y": 0, "z": 0}:
        print(
            f"{context}: cornerOffsetFromSlot is nonzero."
            " New extents will take this into account, but other vectors,"
            " like well coordinates and stacking offsets, will not,"
            " and will need manual review."
        )

    cofs = definition["cornerOffsetFromSlot"]
    x_dimension = definition["dimensions"]["xDimension"]
    y_dimension = definition["dimensions"]["yDimension"]
    z_dimension = definition["dimensions"]["zDimension"]

    cofs_y_inverse = -cofs["y"]
    y_inverse = -y_dimension

    x0 = cofs["x"]
    x1 = cofs["x"] + x_dimension
    y0 = cofs_y_inverse
    y1 = cofs_y_inverse + y_inverse
    z0 = cofs["z"]
    z1 = cofs["z"] + z_dimension

    new_extents = {
        "total": {
            "backLeftBottom": {"x": x0, "y": y0, "z": z0},
            "frontRightTop": {"x": x1, "y": y1, "z": z1},
        },
    }

    features = {
        "slotFootprintAsChild": {
            "z": 0,
            "backLeft": {"x": 0, "y": 0},
            "frontRight": {"x": x_dimension, "y": y_inverse},
        },
    }

    new_wells = {}
    for well_name, well_data in definition["wells"].items():
        new_well = deepcopy(well_data)
        new_well["y"] = -(y_dimension - well_data["y"])
        new_wells[well_name] = new_well

    definition["wells"] = new_wells

    # Delete cornerOffsetFromSlot and replace dimensions with extents,
    # then add features right after extents.
    # Do it in this way to preserve ordering and minimize the diff.
    new_definition = {}
    for original_key, original_value in definition.items():
        if original_key == "cornerOffsetFromSlot":
            continue
        elif original_key == "dimensions":
            new_definition["extents"] = new_extents
            new_definition["features"] = features
        else:
            new_definition[original_key] = original_value

    print(f"{context}: migrated")
    return new_definition


if __name__ == "__main__":
    paths = [Path(arg) for arg in sys.argv[1:]]

    for path in paths:
        definition = json.loads(
            path.read_text(encoding="utf-8"),
            parse_float=decimal.Decimal,
        )
        migrated_definition = migrate(str(path), definition)
        path.write_text(
            json.dumps(
                migrated_definition,
                indent=2,
                ensure_ascii=False,
                cls=DecimalEncoder,
            ),
            encoding="utf-8",
        )

    print(f"Processed {len(paths)} files.")