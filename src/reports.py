"""CSV export with spreadsheet formula protection for user-controlled text."""
import csv
from io import StringIO


def report_csv(case):
    result = case.result
    row = {
        'case_id': case.case_id, 'fund_name': case.fund_name, 'mode': case.mode,
        'claim': case.claim, 'status': case.status, 'revision': case.revision,
        'review_status': case.review_status,
        'fund_waci': result.fund_waci if result else None,
        'benchmark_waci': result.benchmark_waci if result else None,
        'claimed_reduction_pct': result.claimed_reduction_pct if result else None,
        'actual_reduction_pct': result.actual_reduction_pct if result else None,
        'coverage_pct': result.coverage_pct if result else None,
        'review_comments': '\n'.join(review.comment for review in case.reviews),
        'error': case.error,
    }
    for key, value in row.items():
        if isinstance(value, str) and value.lstrip().startswith(('=', '+', '-', '@')):
            row[key] = "'" + value
    stream = StringIO(newline='')
    writer = csv.DictWriter(stream, fieldnames=list(row))
    writer.writeheader()
    writer.writerow(row)
    return stream.getvalue().encode('utf-8-sig')
