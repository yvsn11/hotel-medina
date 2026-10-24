from flask import Flask

from app.routes import auth, bookings, docs, health, payments, rooms


def register_routes(app: Flask) -> None:
    for module in (health, auth, rooms, bookings, payments, docs):
        app.register_blueprint(module.bp)
