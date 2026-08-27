"""
Pluggable results-export formatters (§6 P2: "Recommend building the export
layer as a pluggable formatter interface from day one (CSV is just the
first formatter) so adding the ITRA/UTMB formatters later doesn't mean
rewriting the export path.") CSV is the only formatter implemented in v1;
`format=itra` / `format=utmb` are future additions that just register a
new class here.
"""

import csv
import io


class ResultsFormatter:
    content_type = "application/octet-stream"
    file_extension = "bin"

    def render(self, race, results):
        raise NotImplementedError


class CsvResultsFormatter(ResultsFormatter):
    content_type = "text/csv"
    file_extension = "csv"

    def render(self, race, results):
        buffer = io.StringIO()

        checkpoint_names = []
        if results:
            checkpoint_names = [split["checkpoint_name"] for split in results[0]["splits"]]

        writer = csv.writer(buffer)
        header = ["bib_number", "full_name", "category", "status"]
        for name in checkpoint_names:
            header.append(f"{name} time")
            header.append(f"{name} split (s)")
        header.append("total_elapsed_seconds")
        writer.writerow(header)

        for row in results:
            line = [row["bib_number"], row["full_name"], row["category"], row["status"]]
            for split in row["splits"]:
                line.append(split["timestamp"] or "")
                line.append(split["split_seconds"] if split["split_seconds"] is not None else "")
            line.append(row["total_elapsed_seconds"] if row["total_elapsed_seconds"] is not None else "")
            writer.writerow(line)

        return buffer.getvalue()


FORMATTERS = {
    "csv": CsvResultsFormatter,
}


def get_formatter(format_name):
    formatter_cls = FORMATTERS.get(format_name)
    if formatter_cls is None:
        return None
    return formatter_cls()
