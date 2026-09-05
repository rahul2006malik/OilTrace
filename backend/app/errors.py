"""
Validation-error handling for the Integration+Frontend backend.

schemas.md, Cross-cutting rule 3:
  "/pipeline/run (Integration) validates each artifact against this file
  before passing it downstream and raises a specific, named-field error on
  mismatch — no silent broken frontend state."

Right now the only "artifact" /pipeline/run validates is its own request body
(there's no real upstream artifact yet — that's the whole point of the stub).
Same principle applies: a malformed request should fail loudly, with the exact
field and reason named, not a generic 500 or a silently-defaulted value.
"""

from fastapi import Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse


def _field_path(loc: tuple) -> str:
    """Turn a pydantic error location tuple into a dotted field path,
    dropping the leading 'body' segment FastAPI adds for request-body errors."""
    parts = [str(p) for p in loc if p != "body"]
    return ".".join(parts) if parts else "(request body)"


async def validation_exception_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    fields = [
        {
            "field": _field_path(err["loc"]),
            "message": err["msg"],
            "type": err["type"],
        }
        for err in exc.errors()
    ]
    return JSONResponse(
        status_code=422,
        content={
            "error": "validation_failed",
            "detail": "Input did not match the /pipeline/run contract. See 'fields' for exactly what failed.",
            "fields": fields,
        },
    )
