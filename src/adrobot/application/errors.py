class AppError(Exception):
    """An error with a safe message for the API client."""


class Missing(AppError):
    pass


class Conflict(AppError):
    pass


class Invalid(AppError):
    pass


class TrackerUnavailable(AppError):
    pass


class TrackerRejected(AppError):
    pass
