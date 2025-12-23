"""QR code generation views."""

from __future__ import annotations

from django.urls import reverse
from django.views.generic import DetailView, TemplateView

from the_flip.apps.catalog.models import MachineInstance
from the_flip.apps.core.mixins import CanAccessMaintainerPortalMixin
from the_flip.apps.core.qr import QR_BOX_SIZE_BULK, generate_qr_code_base64


class MachineQRView(CanAccessMaintainerPortalMixin, DetailView):
    """Generate and display a printable QR code for a machine's public info page."""

    model = MachineInstance
    template_name = "maintenance/machine_qr.html"
    context_object_name = "machine"
    slug_field = "slug"
    slug_url_kwarg = "slug"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        machine = self.object

        public_url = self.request.build_absolute_uri(
            reverse("public-problem-report-create", args=[machine.slug])
        )

        context["qr_code_data"] = generate_qr_code_base64(public_url)
        context["public_url"] = public_url

        return context


class MachineBulkQRCodeView(CanAccessMaintainerPortalMixin, TemplateView):
    """Printable grid of QR codes for all machines."""

    template_name = "maintenance/machine_qr_bulk.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        machines = MachineInstance.objects.visible()
        qr_entries = []

        for machine in machines:
            public_url = self.request.build_absolute_uri(
                reverse("public-problem-report-create", args=[machine.slug])
            )
            qr_entries.append(
                {
                    "machine": machine,
                    "qr_data": generate_qr_code_base64(public_url, box_size=QR_BOX_SIZE_BULK),
                    "public_url": public_url,
                }
            )

        context["qr_entries"] = qr_entries
        return context
