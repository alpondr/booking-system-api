from sqlalchemy.orm import declarative_base

# All models inherit from this. SQLAlchemy uses it to track table
# metadata, and Alembic (step 5) reads it to autogenerate migrations.
Base = declarative_base()
