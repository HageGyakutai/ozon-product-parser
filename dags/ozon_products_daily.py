"""Daily Airflow DAG for loading Ozon products into PostgreSQL."""

from datetime import UTC, datetime, timedelta

from airflow.sdk import dag, task
from ozon_parser.airflow_task import run_daily_parser


@dag(
    dag_id="ozon_products_daily",
    schedule="0 6 * * *",
    start_date=datetime(2026, 1, 1, tzinfo=UTC),
    catchup=False,
    max_active_runs=1,
    default_args={
        "owner": "ozon-parser",
        "retries": 2,
        "retry_delay": timedelta(minutes=5),
    },
    tags=["ozon", "parser"],
)
def ozon_products_daily():
    """Parse configured Ozon SKU values once a day at 06:00 UTC."""

    @task
    def parse_products() -> None:
        run_daily_parser()

    parse_products()


ozon_products_daily()
