"""Video/media component tags: video_player, video_thumbnail."""

from django import template

register = template.Library()


@register.inclusion_tag("components/video_player.html")
def video_player(media, model_name="LogEntryMedia"):
    """Render a video player with appropriate state handling.

    Handles three video states:
    - READY: Transcoded video with poster (web UI uploads)
    - Empty string: Original file without transcoding (Discord uploads)
    - PROCESSING/PENDING: Show processing status with polling
    - FAILED: Show error message

    Usage:
        {% video_player media=media model_name="LogEntryMedia" %}

    Args:
        media: Media object with transcode_status, media_type, and file fields
        model_name: Media model name for polling (default: "LogEntryMedia")
    """
    return {
        "media": media,
        "model_name": model_name,
    }


@register.inclusion_tag("components/video_thumbnail.html")
def video_thumbnail(media, model_name="LogEntryMedia"):
    """Render a video thumbnail for list views.

    Handles three video states:
    - READY: Show poster image
    - Empty string: Show video icon (Discord uploads have no poster)
    - PROCESSING/PENDING: Show processing status with polling
    - FAILED: Show error message

    Usage:
        {% video_thumbnail media=media model_name="LogEntryMedia" %}

    Args:
        media: Media object with transcode_status, poster_file fields
        model_name: Media model name for polling (default: "LogEntryMedia")
    """
    return {
        "media": media,
        "model_name": model_name,
    }
