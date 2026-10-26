from datetime import UTC, date, datetime

from src.plaid.apps import DataExporter
from src.plaid.paths import get_records_dir


def run_data_export(
    start_date: date = date(2024, 1, 1),
    end_date: date | None = None,
    bank_filter: str | None = None,
    account_filter: list[str] | None = None,
    output_dir: str | None = None,
):
    """
    Run the full data export pipeline in one single call.

    Args:
        start_date (date): Start date for the export.
        end_date (date): End date for the export.
        bank_filter (str, optional): Bank name or Item ID filter.
        account_filter (List[str], optional): List of account names to include.
        output_dir (str, optional): Directory to save exported files. Defaults to get_records_dir().

    Returns:
        List[Dict]: List of results with file paths and metadata.
    """
    output_dir = output_dir or get_records_dir()
    end_date = end_date or datetime.now(UTC).date()

    print(f'--- Starting Data Export from {start_date} to {end_date} ---')

    try:
        results = DataExporter.run_export(
            start_date=start_date,
            end_date=end_date,
            bank_filter=bank_filter,
            account_filter=account_filter,
            output_dir=output_dir,
        )
    except Exception as e:
        print(f'Data export failed: {e}')
        return []

    if not results:
        print('No accounts matched the filter or no tokens found.')
        return []

    for res in results:
        print(f'Export successful! File created at: {res["file"]}')

    return results


if __name__ == '__main__':
    # Single function call
    run_data_export(
        start_date=date(2024, 1, 1),
        end_date=date(2024, 2, 23),
        bank_filter='Chase',
        account_filter=['Plaid Checking', 'Plaid Saving'],
    )
