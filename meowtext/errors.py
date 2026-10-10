"""Errors a caller can catch and show."""


class MeowTextError(Exception):
    """Base error for banner rendering and export."""


class RenderError(MeowTextError):
    """The banner could not be rendered."""
