"""What a log line may say about a failed call made for a member.

Application logs are shipped to and kept by the log backend, so they must not
link a person to their meter: no sensor or device id at any level, and no user
id above DEBUG (celine-eu/celine-webapp#27).

An exception's own text is not safe either. A failed Digital Twin call raises an
`httpx` error whose message is the request URL, and that URL carries the
participant id. :func:`failure` keeps what diagnosis needs — the error type and
the HTTP status — and nothing the request was about.
"""

from __future__ import annotations


def failure(exc: BaseException) -> str:
    """`ErrorType` or `ErrorType 404`: never the exception's message."""
    status = getattr(exc, "status_code", None)
    if status is None:
        response = getattr(exc, "response", None)
        status = getattr(response, "status_code", None)
    name = type(exc).__name__
    return f"{name} {status}" if status is not None else name
