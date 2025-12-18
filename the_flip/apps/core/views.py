from django.contrib.auth.decorators import login_required
from django.core.exceptions import ObjectDoesNotExist
from django.http import JsonResponse
from django.utils.decorators import method_decorator
from django.views import View
from django.views.generic import TemplateView

from the_flip.apps.core.health import check_db_and_orm
from the_flip.apps.core.models import get_media_model


class HomeView(TemplateView):
    template_name = "home.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        # Check if current user is a shared account
        is_shared_account = False
        if self.request.user.is_authenticated and hasattr(self.request.user, "maintainer"):
            is_shared_account = self.request.user.maintainer.is_shared_account
        context["is_shared_account"] = is_shared_account
        return context


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


@method_decorator(login_required, name="dispatch")
class TranscodeStatusView(View):
    """
    API endpoint for polling video transcode status.

    Accepts comma-separated media IDs and model names, returns status for each.
    Used by video_transcode_poll.js to update UI when transcoding completes.

    Query params:
        ids: comma-separated media IDs (e.g., "1,2,3")
        models: comma-separated model names (e.g., "LogEntryMedia,LogEntryMedia,PartRequestMedia")

    Response:
        {
            "1": {"status": "ready", "video_url": "...", "poster_url": "..."},
            "2": {"status": "processing"},
            "3": {"status": "failed"}
        }
    """

    def get(self, request):
        ids_param = request.GET.get("ids", "")
        models_param = request.GET.get("models", "")

        if not ids_param or not models_param:
            return JsonResponse({})

        ids = [i.strip() for i in ids_param.split(",") if i.strip()]
        model_names = [m.strip() for m in models_param.split(",") if m.strip()]

        if len(ids) != len(model_names):
            return JsonResponse({"error": "ids and models must have same length"}, status=400)

        results = {}
        for media_id, model_name in zip(ids, model_names, strict=True):
            result = self._get_media_status(media_id, model_name)
            results[media_id] = result

        response = JsonResponse(results)
        response["Cache-Control"] = "no-store"
        return response

    def _get_media_status(self, media_id: str, model_name: str) -> dict:
        """Get transcode status for a single media item."""
        try:
            media_model = get_media_model(model_name)
        except ValueError:
            return {"status": "failed", "message": "Unknown media type"}

        try:
            media = media_model.objects.get(id=media_id)
            return self._build_status_result(media, media_model)
        except (ValueError, TypeError):
            return {"status": "failed", "message": "Invalid media ID"}
        except ObjectDoesNotExist:
            return {"status": "failed", "message": "Media not found"}

    def _build_status_result(self, media, media_model) -> dict:
        """Build status result dict for a media item."""
        result = {"status": media.transcode_status}
        if media.transcode_status == media_model.STATUS_READY:
            if media.transcoded_file:
                result["video_url"] = media.transcoded_file.url
            if media.poster_file:
                result["poster_url"] = media.poster_file.url
        return result
