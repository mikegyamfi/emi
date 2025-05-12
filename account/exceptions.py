from rest_framework.views import exception_handler
from rest_framework import status
from rest_framework.response import Response
import logging

logger = logging.getLogger(__name__)

GENERIC_500 = {"detail": "Sorry, something went wrong. Please try again later."}


def custom_exception_handler(exc, context):
    """
    Wrap DRF’s default handler so *every* error becomes JSON and
    unexpected 5xx never leak stack traces to the client.
    """
    response = exception_handler(exc, context)
    if response is None:
        # Unhandled exception → 500
        logger.exception("Unhandled exception in %s", context.get("view"), exc_info=exc)
        return Response(GENERIC_500, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    # Optionally normalise all responses to {"detail": "..."} shape
    return response
