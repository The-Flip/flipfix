from django.views.generic import TemplateView

from the_flip.apps.accounts.models import Maintainer
from the_flip.apps.catalog.models import MachineInstance


class HomeView(TemplateView):
    template_name = "home.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        # Get a sample machine for demonstrating the log entry link
        sample_machine = MachineInstance.objects.first()
        context["sample_machine"] = sample_machine
        # Get all maintainers
        context["maintainers"] = Maintainer.objects.select_related("user").all()
        return context
