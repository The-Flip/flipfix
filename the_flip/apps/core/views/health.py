"""Health check endpoint."""

from django.http import JsonResponse

from the_flip.apps.core.health import check_db_and_orm


def healthz(request):
    """Public health check endpoint for Railway."""
    try:
        details = check_db_and_orm()
    except Exception as exc:  # noqa: BLE001
        resp = JsonResponse({"status": "error", "error": str(exc)})
        resp.status_code = 503
        resp["Cache-Control"] = "no-store"
        return resp

    resp = JsonResponse({"status": "ok", "checks": details})
    resp["Cache-Control"] = "no-store"
    return resp
