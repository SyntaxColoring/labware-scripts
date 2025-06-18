#!/usr/bin/env python3
"""
Script to add extents and features to module definitions.

Usage:
cd shared-data/python
pipenv run python update_module_defs.py ../module/definitions/3/**/*.json
make -C .. format-js
"""

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
    cofs = definition["cornerOffsetFromSlot"]
    dimensions = definition["dimensions"]

    x_dimension = dimensions["xDimension"]
    y_dimension = dimensions["yDimension"]
    z_dimension = dimensions["bareOverallHeight"]

    # Calculate extents
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

    footprint_x = dimensions.get("footprintXDimension", x_dimension)
    footprint_y = dimensions.get("footprintYDimension", y_dimension)
    footprint_y_inverse = -footprint_y

    features = {
        "slotFootprintAsChild": {
            "z": 0,
            "backLeft": {"x": 0, "y": 0},
            "frontRight": {"x": footprint_x, "y": footprint_y_inverse},
        },
    }

    new_definition = {}
    for original_key, original_value in definition.items():
        new_definition[original_key] = original_value

        if original_key == "dimensions":
            new_definition["extents"] = new_extents
            new_definition["features"] = features

    print(f"{context}: migrated")
    return new_definition


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python migrate_modules.py <module_file_1> [module_file_2] ...")
        sys.exit(1)

    paths = [Path(arg) for arg in sys.argv[1:]]

    for path in paths:
        try:
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
        except Exception as e:
            print(f"Error processing {path}: {e}")

    print(f"Processed {len(paths)} files.")