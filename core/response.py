from rest_framework.response import Response


def ok(message="OK", data=None, status=200):
    body = {"code": 1, "message": message}
    if data is not None:
        body["data"] = data
    return Response(body, status=status)


def fail(message, error_message="", field_errors=None, status=400):
    """
    field_errors is an optional dict of {field: [error, …]} that will be
    merged into the response for DRF-compatible clients.
    """
    body = {"code": 0, "message": message, "error_message": error_message}
    if field_errors:
        body["errors"] = field_errors
    return Response(body, status=status)
