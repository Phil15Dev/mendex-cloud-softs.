from fastapi import Request


def flash(request: Request, kind: str, message: str) -> None:
    request.session["flash"] = [kind, message]


def pop_flash(request: Request):
    return request.session.pop("flash", None)
