"""Flask extension singletons."""

from flask_cors import CORS
from flask_migrate import Migrate
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy.orm import Session

from app.models.base import Base

db = SQLAlchemy(model_class=Base)
migrate = Migrate()
cors = CORS()


def get_session() -> Session:
    """The request-scoped SQLAlchemy session (typed as a plain `Session`)."""
    return db.session()
