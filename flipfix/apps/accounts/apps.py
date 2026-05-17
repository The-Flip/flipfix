from django.apps import AppConfig


class AccountsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "flipfix.apps.accounts"
    verbose_name = "Accounts"

    def ready(self) -> None:
        from flipfix.apps.core.models import register_media_model

        from . import signals  # noqa: F401
        from .models import MaintainerMedia

        register_media_model(MaintainerMedia)
        self._register_link_types()

    @staticmethod
    def _register_link_types() -> None:
        # Imports go inside ready()-called methods so the app registry is
        # fully loaded before we touch other apps' models.
        from django.db.models import F, Value
        from django.db.models.functions import Coalesce, Lower, NullIf

        from flipfix.apps.accounts.display import display_name_with_username
        from flipfix.apps.accounts.models import Maintainer
        from flipfix.apps.core.markdown_links import LinkType, register

        def _serialize_user(obj):
            return {
                "label": display_name_with_username(obj),
                "ref": obj.username,
            }

        # Scope: directory-visible maintainers only. Routing through the
        # existing queryset method keeps Maintainer.objects.in_user_directory()
        # as the single source of truth — if that predicate changes, save-time
        # validation, render-time resolution, and autocomplete all update.
        def _directory_users(model):
            return model.objects.filter(
                pk__in=Maintainer.objects.in_user_directory().values("user_id"),
            )

        register(
            LinkType(
                name="user",
                model_path="auth.User",
                slug_field="username",
                label="User",
                description="Link to a user's profile",
                url_name="user-profile",
                url_kwarg="username",
                url_field="username",
                get_label=display_name_with_username,
                target_queryset=_directory_users,
                autocomplete_search_fields=("username", "first_name", "last_name"),
                autocomplete_ordering=(
                    F("maintainer__last_active_at").desc(nulls_last=True),
                    Lower(Coalesce(NullIf("first_name", Value("")), "username")),
                ),
                autocomplete_serialize=_serialize_user,
                sort_order=80,
            )
        )
