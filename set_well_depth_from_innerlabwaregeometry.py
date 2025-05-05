# Example usage:
#
# cd shared-data/python
# pipenv run this_script.py ../labware/{definitions,fixtures}/2/**/*.json
# make -C .. format-js


from copy import deepcopy
import json
from pathlib import Path
import sys
from traceback import format_exception
import decimal

from opentrons_shared_data.labware.types import LabwareDefinition2


PROBLEM_INDENT = " " * 2


class DecimalEncoder(json.JSONEncoder):
    """A JSON encoder that can encode decimal.Decimal objects."""

    def default(self, o: object) -> object:
        if isinstance(o, decimal.Decimal):
            return float(o)
        else:
            return super().default(o)


def process(definition: LabwareDefinition2) -> LabwareDefinition2:
    result = deepcopy(definition)
    inner_labware_geometry = result.get("innerLabwareGeometry", {})

    if len(inner_labware_geometry) != 1:
        return result

    [geometries] = inner_labware_geometry.values()
    top_section_height = geometries["sections"][0]["topHeight"]

    for well in result["wells"].values():
        well["depth"] = top_section_height

    return result


if __name__ == "__main__":
    paths = [Path(arg) for arg in sys.argv[1:]]

    for path in paths:
        input: LabwareDefinition2 = json.loads(
            path.read_text(encoding="utf-8"),
            parse_float=decimal.Decimal,
        )
        output = process(input)
        path.write_text(
            json.dumps(
                output,
                indent=2,
                ensure_ascii=False,
                cls=DecimalEncoder,
            ),
            encoding="utf-8",
        )

    print(f"Processed {len(paths)} paths")
