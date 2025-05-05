# Example usage:
#
# (ls -1 definitions/2 && ls -1 definitions/3) | sort | uniq | python3 detect_sibling_definitions.py
# Then manually fix up results.
#
# "Siblings":
# opentrons_24_aluminumblock_nest_0.5ml_screwcap
# opentrons_24_tuberack_nest_0.5ml_screwcap
#
# "Parent/child":
# opentrons_96_deep_well_adapter
# opentrons_96_deep_well_adapter_nest_wellplate_2ml_deep

from collections import defaultdict
import itertools
import json
import re
import sys

PARENT_SIGNIFIERS = {"aluminumblock", "tuberack", "adapter"}


def get_group_id(load_name: str) -> str:
    """Return a string heuristically identifying which group a labware should belong to.

    This tries to throw away info about the parent while retaining info about the child.
    """
    parts = load_name.split("_")

    # Throw away parts that are just integers, e.g. the "96" in "opentrons_96_flat_bottom_adapter".
    # They are problematic to deal with because they get deduplicated. For example, in
    # "opentrons_96_flat_bottom_adapter_nest_wellplate_200ul_flat", it
    # is "nest_wellplate", not "nest_96_wellplate", even though the plate's standalone
    # definition has "nest_96_wellplate".
    #
    # Also throw away certain keywords. e.g. "opentrons_96_aluminumblock_nest_wellplate_100ul"
    # should be in the same group as "opentrons_96_pcr_adapter_nest_wellplate_100ul_pcr_full_skirt".
    parts = [
        part
        for part in parts
        if not (part.isnumeric() or part in {"flat", "full", "skirt", "pcr"})
    ]

    # Everything to the left of the parent signifier is part of the parent
    # and everything to the right is part of the child.
    try:
        parent_signifier_index = next(
            index for index, part in enumerate(parts) if part in PARENT_SIGNIFIERS
        )
    except StopIteration:
        pass
    else:
        parts = parts[parent_signifier_index + 1 :]

    return "_".join(parts)


if __name__ == "__main__":
    groups = defaultdict[str, set[str]](set)
    load_names = [line.strip() for line in sys.stdin]
    for load_name in load_names:
        groups[get_group_id(load_name)].add(load_name)

    to_print = {
        **{
            # Sort group IDs and member lists for human readability.
            group_name: sorted(group_members)
            for group_name, group_members in sorted(groups.items(), key=lambda t: t[0])
            if len(group_members) > 1
        },
        **{
            "<no group>": sorted(
                itertools.chain.from_iterable(
                    group_members
                    for group_members in groups.values()
                    if len(group_members) == 1
                )
            )
        },
    }

    print(json.dumps(to_print, indent=2))
