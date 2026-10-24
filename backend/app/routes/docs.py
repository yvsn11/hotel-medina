from flask import Blueprint, Response, jsonify
from flask.typing import ResponseReturnValue

from app.openapi import build_spec

bp = Blueprint("docs", __name__, url_prefix="/api")

_PAGE = """<!doctype html>
<html lang="en"><head><meta charset="utf-8"><title>Hotel Medina API</title>
<meta name="viewport" content="width=device-width, initial-scale=1">
<link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/swagger-ui-dist@5.17.14/swagger-ui.css">
</head><body><div id="ui"></div>
<script src="https://cdn.jsdelivr.net/npm/swagger-ui-dist@5.17.14/swagger-ui-bundle.js"></script>
<script>SwaggerUIBundle({url: "/api/openapi.json", dom_id: "#ui"});</script>
</body></html>"""


@bp.get("/openapi.json")
def openapi() -> ResponseReturnValue:
    return jsonify(build_spec())


@bp.get("/docs")
def docs() -> ResponseReturnValue:
    return Response(_PAGE, mimetype="text/html")
