"""Forms for catalog models."""

from django import forms
from django.core.exceptions import ValidationError

from the_flip.apps.catalog.models import MachineInstance, MachineModel


class MachineInstanceForm(forms.ModelForm):
    """Form for editing machine instance details."""

    fieldsets = [
        ("Current State", ["operational_status", "location"]),
        ("Identification", ["name_override", "serial_number"]),
        ("Provenance", ["ownership_credit", "acquisition_notes"]),
    ]

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
            "name_override": forms.TextInput(
                attrs={"placeholder": "Leave blank to use the machine's model name"}
            ),
            "serial_number": forms.TextInput(attrs={"placeholder": "e.g., 12345"}),
            "acquisition_notes": forms.Textarea(
                attrs={
                    "rows": 4,
                    "placeholder": "Notes about how this machine was acquired, when, and any relevant details",
                }
            ),
            "ownership_credit": forms.TextInput(
                attrs={"placeholder": "e.g., On loan from John Doe"}
            ),
        }


class MachineModelForm(forms.ModelForm):
    """Form for editing a pinball machine model details."""

    fieldsets = [
        (
            "Basic Information",
            ["name", "manufacturer", "month", "year", "production_quantity", "factory_address"],
        ),
        ("Technical Specifications", ["era", "system", "scoring", "flipper_count"]),
        ("Credits", ["design_credit", "concept_and_design_credit", "art_credit", "sound_credit"]),
        (
            "Community",
            [
                "pinside_rating",
                "ipdb_id",
            ],
        ),
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
            "name": forms.TextInput(attrs={"placeholder": "e.g., Star Trek"}),
            "manufacturer": forms.TextInput(attrs={"placeholder": "e.g., Bally, Williams, Stern"}),
            "month": forms.NumberInput(attrs={"placeholder": "1-12", "style": "width: 4em;"}),
            "year": forms.NumberInput(attrs={"placeholder": "e.g., 1979", "style": "width: 6em;"}),
            "system": forms.TextInput(attrs={"placeholder": "e.g., WPC-95, System 11"}),
            "scoring": forms.TextInput(attrs={"placeholder": "e.g., Reel, 5 Digit, 7 Digit"}),
            "flipper_count": forms.NumberInput(
                attrs={"placeholder": "e.g., 2", "style": "width: 4em;"}
            ),
            "pinside_rating": forms.NumberInput(
                attrs={"placeholder": "0.00-10.00", "step": "0.01", "style": "width: 6em;"}
            ),
            "ipdb_id": forms.NumberInput(
                attrs={"placeholder": "e.g., 2355", "style": "width: 6em;"}
            ),
            "production_quantity": forms.TextInput(
                attrs={"placeholder": "e.g., ~50,000", "style": "width: 20em;"}
            ),
            "factory_address": forms.TextInput(attrs={"placeholder": "e.g., Chicago, Illinois"}),
            "design_credit": forms.TextInput(attrs={"placeholder": "e.g., Steve Ritchie"}),
            "concept_and_design_credit": forms.TextInput(attrs={"placeholder": "e.g., Pat Lawlor"}),
            "art_credit": forms.TextInput(attrs={"placeholder": "e.g., John Youssi"}),
            "sound_credit": forms.TextInput(attrs={"placeholder": "e.g., Dan Forden"}),
            "educational_text": forms.Textarea(
                attrs={
                    "rows": 6,
                    "placeholder": "Educational description for museum visitors about the history, significance, or unique features of this machine",
                }
            ),
            "illustration_filename": forms.TextInput(attrs={"placeholder": "e.g., star-trek.jpg"}),
            "sources_notes": forms.Textarea(
                attrs={
                    "rows": 4,
                    "placeholder": "Notes about where information was sourced from (e.g., IPDB, Pinside, manuals)",
                }
            ),
        }


class MachineQuickCreateForm(forms.Form):
    """Quick create form for adding a new machine instance and optionally a new model.

    This form allows maintainers to quickly add a machine by either:
    1. Selecting an existing model and providing a name_override
    2. Creating a new model with basic info (name, manufacturer, year)
    """

    model = forms.ModelChoiceField(
        queryset=MachineModel.objects.all().order_by("name"),
        required=False,
        empty_label="--- Create New Model ---",
        label="Machine Model",
    )

    # Fields for creating a new model (shown when "Create New Model" is selected)
    model_name = forms.CharField(
        max_length=100,
        required=False,
        label="Model Name",
        widget=forms.TextInput(attrs={"placeholder": "e.g., Star Trek"}),
    )

    manufacturer = forms.CharField(
        max_length=100,
        required=False,
        label="Manufacturer",
        widget=forms.TextInput(attrs={"placeholder": "e.g., Bally, Williams, Stern"}),
    )

    year = forms.IntegerField(
        required=False,
        label="Year",
        widget=forms.NumberInput(attrs={"placeholder": "e.g., 1979", "style": "width: 8em;"}),
    )

    # Field for naming an instance of an existing model
    name_override = forms.CharField(
        max_length=100,
        required=False,
        label="Machine Name",
        widget=forms.TextInput(attrs={"placeholder": "Give this specific machine a unique name"}),
        help_text="Required when selecting an existing model to distinguish this specific machine",
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Format model choices to show "Name (Manufacturer, Year)"
        self.fields["model"].label_from_instance = lambda obj: (
            f"{obj.name} ({obj.manufacturer}, {obj.year})"
            if obj.manufacturer and obj.year
            else f"{obj.name} ({obj.manufacturer or obj.year or 'Unknown'})"
        )

    def clean(self):
        """Validate that either an existing model is selected OR new model info is provided."""
        cleaned_data = super().clean()
        model = cleaned_data.get("model")
        model_name = cleaned_data.get("model_name")
        name_override = cleaned_data.get("name_override")

        # Check if either a model is selected or model_name is provided
        if not model and not model_name:
            raise ValidationError(
                "Please either select an existing model or provide a name for a new model."
            )

        # If existing model selected, name_override is required
        if model and not name_override:
            raise ValidationError(
                "When selecting an existing model, you must provide a unique name for this specific machine."
            )

        # If creating new model, model_name is required
        if not model and not model_name:
            raise ValidationError("Please provide a model name when creating a new model.")

        return cleaned_data
