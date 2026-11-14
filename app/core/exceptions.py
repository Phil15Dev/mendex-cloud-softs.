class NeedLogin(Exception):
    """No valid admin session."""


class PermissionDenied(Exception):
    def __init__(self, message: str = "You do not have permission to do that."):
        self.message = message
