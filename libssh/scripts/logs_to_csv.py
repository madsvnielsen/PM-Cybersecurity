"""Convert case-labelled Docker Compose SSH logs to timestamp;case;activity.

Usage: python logs_to_csv.py input.log [output.csv]
Uses only the Python standard library. Preserves event order and repetitions.
"""
import argparse
import codecs
import csv
import re
import sys
from collections import Counter
from pathlib import Path


# Use libssh's UTC event timestamp, rather than Docker's later capture time.
# Match the complete service name so sshd-10 and other containers are excluded.
EVENT = re.compile(
    r"^sshd-1\s*\|\s*(?:\S+\s+)?"
    r"\[(?P<timestamp>\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d+Z),\s*\d+\]"
    r"\s+\[case=(?P<case>[^\]\s]+)\]\s+"
    r"(?P<key>[^:\s]+):\s*(?P<message>.*)$"
)
SERVICE = re.compile(r"^sshd-1\s*\|")
PM_ACTIVITIES = {
    "Session started": "pm_ses_start",
    "Session ended": "pm_ses_end",
    "Password authentication succeeded": "pm_auth_success",
    "Password authentication failed": "pm_auth_fail",
}


def activity_name(key, message):
    if key not in ("process_mining", "processmining"):
        return key
    if message in PM_ACTIVITIES:
        return PM_ACTIVITIES[message]
    # Keep future instrumentation events distinct instead of grouping them all
    # under process_mining. Existing pm_* keys also work without special handling.
    suffix = re.sub(r"[^a-z0-9]+", "_", message.lower()).strip("_")
    return "pm_" + (suffix or "unknown")


def input_encoding(path):
    with path.open("rb") as source:
        prefix = source.read(4)
    if prefix.startswith((codecs.BOM_UTF16_LE, codecs.BOM_UTF16_BE)):
        return "utf-16"  # Windows PowerShell's default Tee-Object output.
    return "utf-8-sig"  # Accept UTF-8 with or without a BOM.


def transform(input_path, output_path):
    input_path, output_path = Path(input_path), Path(output_path)
    if input_path.resolve() == output_path.resolve():
        raise ValueError("Input and output must be different files")
    counts = Counter()
    cases = set()
    with input_path.open(encoding=input_encoding(input_path)) as source:
        with output_path.open("w", encoding="utf-8", newline="") as target:
            writer = csv.writer(target, delimiter=";", lineterminator="\n")
            writer.writerow(("timestamp", "case", "activity"))
            for line in source:
                if not SERVICE.match(line):
                    counts["other_lines"] += 1
                    continue
                event = EVENT.fullmatch(line.rstrip("\r\n"))
                if event is None:
                    counts["malformed"] += 1
                    continue
                case = event["case"]
                if case == "server" or case.startswith("server-"):
                    counts["server_events"] += 1
                    continue
                writer.writerow((event["timestamp"], case,
                                 activity_name(event["key"], event["message"])))
                counts["events"] += 1
                cases.add(case)
    counts["cases"] = len(cases)
    return counts


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path, help="Case-labelled SSH log file")
    parser.add_argument("output", type=Path, nargs="?",
                        help="Output CSV (default: input filename with .csv extension)")
    args = parser.parse_args()
    output = args.output or args.input.with_suffix(".csv")
    try:
        counts = transform(args.input, output)
    except (OSError, UnicodeError, ValueError) as error:
        parser.exit(1, f"Error: {error}\n")
    print(f"Wrote {counts['events']} events in {counts['cases']} cases to {output}")
    print(f"Skipped: {counts['other_lines']} other/blank lines, "
          f"{counts['server_events']} server events, "
          f"{counts['malformed']} malformed sshd-1 lines.")
    if counts["malformed"]:
        print("Warning: malformed lines lack the expected timestamp, case, or activity key.",
              file=sys.stderr)
    if not counts["events"]:
        parser.exit(1, "No connection events found. Check the service prefix and case fields.\n")


if __name__ == "__main__":
    main()
