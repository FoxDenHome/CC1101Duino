#!/usr/bin/env python3
"""Collects SIGNALduino test data into tests/fixtures/signalduino.json.

  git clone https://github.com/RFD-FHEM/RFFHEM.git
  curl -LO https://raw.githubusercontent.com/RFD-FHEM/SIGNALduino_TOOL/master/FHEM/lib/SD_Device_ProtocolList.json
  scripts/import_signalduino_testdata.py RFFHEM SD_Device_ProtocolList.json \
    > tests/fixtures/signalduino.json

Each case pairs a raw firmware message (rmsg) and/or the demodulated message (dmsg) with the
readings the FHEM client module produced for it.
"""

import json
import sys
from pathlib import Path

KEEP = ("comment", "rmsg", "dmsg", "readings", "attributes", "internals")


def cases(test_sets, source):
    for test_set in test_sets:
        for entry in test_set.get("data", []):
            case = {key: entry[key] for key in KEEP if entry.get(key)}
            # Attributes the FHEM test sets on the device, e.g. a model it cannot detect
            for test in entry.get("tests", []):
                if test.get("attributes"):
                    case["attributes"] = {**case.get("attributes", {}), **test["attributes"]}
            # Cases expected to be rejected by the client module
            if any(test.get("returns", {}).get("ParseFn") == "" for test in entry.get("tests", [])):
                case["rejected"] = True
            if "rmsg" in case or "dmsg" in case:
                yield {
                    "source": source,
                    "id": str(test_set["id"]),
                    "module": test_set.get("module", ""),
                    **case,
                }


def main() -> None:
    rffhem = Path(sys.argv[1])
    device_list = json.loads(Path(sys.argv[2]).read_text())

    result = []
    for test_file in sorted(rffhem.glob("t/FHEM/*/testData.json")):
        result.extend(cases(json.loads(test_file.read_text()), test_file.parent.name))
    result.extend(cases(device_list["protocols"], "SD_Device_ProtocolList"))

    json.dump(result, sys.stdout, indent=1, ensure_ascii=False, sort_keys=True)
    sys.stdout.write("\n")


if __name__ == "__main__":
    main()
