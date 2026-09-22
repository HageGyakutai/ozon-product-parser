from dotenv import load_dotenv

from alembic import context
from ozon_parser.storage import Base, database_engine

load_dotenv()

config = context.config
target_metadata = Base.metadata


def run_migrations_offline():
    context.configure(
        url=str(database_engine().url), target_metadata=target_metadata, literal_binds=True
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online():
    engine = database_engine()
    with engine.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()
    engine.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
