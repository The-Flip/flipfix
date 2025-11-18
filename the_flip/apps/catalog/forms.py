"""Forms for catalog models."""
from django import forms

from the_flip.apps.catalog.models import MachineInstance, MachineModel


class MachineInstanceForm(forms.ModelForm):
    """Form for editing machine instance details.

    Excludes the model field (cannot change a machine's model) and
    auto-generated fields (slug, audit fields).
    """

    class Meta:
        model = MachineInstance
        fields = [
            "operational_status",
            "location",
            "name_override",
            "serial_number",
            "ownership_credit",
            "acquisition_notes",
        ]
        widgets = {
            "name_override": forms.TextInput(attrs={
                "placeholder": "Leave blank to use the machine's model name"
            }),
            "serial_number": forms.TextInput(attrs={
                "placeholder": "e.g., 12345"
            }),
            "acquisition_notes": forms.Textarea(attrs={
                "rows": 4,
                "placeholder": "Notes about how this machine was acquired, when, and any relevant details"
            }),
            "ownership_credit": forms.TextInput(attrs={
                "placeholder": "e.g., On loan from John Doe"
            }),
        }


class MachineModelForm(forms.ModelForm):
    """Form for editing a pinball machine model details.
    """

    fieldsets = [
        ("Basic Information", ["name", "manufacturer", "month", "year", "production_quantity", "factory_address"]),
        ("Technical Specifications", ["era", "system", "scoring", "flipper_count"]),
        ("Credits", ["design_credit", "concept_and_design_credit", "art_credit", "sound_credit"]),
        ("Community", ["pinside_rating", "ipdb_id", ]),
        ("Website", ["illustration_filename", "educational_text", "sources_notes"]),
    ]

    class Meta:
        model = MachineModel
        fields = [
            "name",
            "manufacturer",
            "month",
            "year",
            "era",
            "system",
            "scoring",
            "flipper_count",
            "pinside_rating",
            "ipdb_id",
            "production_quantity",
            "factory_address",
            "design_credit",
            "concept_and_design_credit",
            "art_credit",
            "sound_credit",
            "educational_text",
            "illustration_filename",
            "sources_notes",
        ]
        widgets = {
            "name": forms.TextInput(attrs={
                "placeholder": "e.g., Star Trek"
            }),
            "manufacturer": forms.TextInput(attrs={
                "placeholder": "e.g., Bally, Williams, Stern"
            }),
            "month": forms.NumberInput(attrs={
                "placeholder": "1-12",
                "style": "width: 4em;"
            }),
            "year": forms.NumberInput(attrs={
                "placeholder": "e.g., 1979",
                "style": "width: 6em;"
            }),
            "system": forms.TextInput(attrs={
                "placeholder": "e.g., WPC-95, System 11"
            }),
            "scoring": forms.TextInput(attrs={
                "placeholder": "e.g., Reel, 5 Digit, 7 Digit"
            }),
            "flipper_count": forms.NumberInput(attrs={
                "placeholder": "e.g., 2",
                "style": "width: 4em;"
            }),
            "pinside_rating": forms.NumberInput(attrs={
                "placeholder": "0.00-10.00",
                "step": "0.01",
                "style": "width: 6em;"
            }),
            "ipdb_id": forms.NumberInput(attrs={
                "placeholder": "e.g., 2355",
                "style": "width: 6em;"
            }),
            "production_quantity": forms.NumberInput(attrs={
                "placeholder": "e.g., 5000",
                "style": "width: 8em;"
            }),
            "factory_address": forms.TextInput(attrs={
                "placeholder": "e.g., Chicago, Illinois"
            }),
            "design_credit": forms.TextInput(attrs={
                "placeholder": "e.g., Steve Ritchie"
            }),
            "concept_and_design_credit": forms.TextInput(attrs={
                "placeholder": "e.g., Pat Lawlor"
            }),
            "art_credit": forms.TextInput(attrs={
                "placeholder": "e.g., John Youssi"
            }),
            "sound_credit": forms.TextInput(attrs={
                "placeholder": "e.g., Dan Forden"
            }),
            "educational_text": forms.Textarea(attrs={
                "rows": 6,
                "placeholder": "Educational description for museum visitors about the history, significance, or unique features of this machine"
            }),
            "illustration_filename": forms.TextInput(attrs={
                "placeholder": "e.g., star-trek.jpg"
            }),
            "sources_notes": forms.Textarea(attrs={
                "rows": 4,
                "placeholder": "Notes about where information was sourced from (e.g., IPDB, Pinside, manuals)"
            }),
        }
