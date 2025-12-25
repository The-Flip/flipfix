"""Forms for catalog models."""

from django import forms
from django.core.exceptions import ValidationError

from the_flip.apps.catalog.models import MachineInstance, MachineModel
from the_flip.apps.core.forms import StyledFormMixin


class MachineInstanceForm(StyledFormMixin, forms.ModelForm):
    """Form for editing machine instance details."""

    fieldsets = [
        ("Identification", ["name_override", "serial_number"]),
        ("Provenance", ["ownership_credit", "acquisition_notes"]),
    ]

    class Meta:
        model = MachineInstance
        fields = [
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


class MachineModelForm(StyledFormMixin, forms.ModelForm):
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
            "month": forms.NumberInput(
                attrs={"placeholder": "1-12", "class": "form-input--width-6"}
            ),
            "year": forms.NumberInput(
                attrs={"placeholder": "e.g., 1979", "class": "form-input--width-8"}
            ),
            "system": forms.TextInput(attrs={"placeholder": "e.g., WPC-95, System 11"}),
            "scoring": forms.TextInput(attrs={"placeholder": "e.g., Reel, 5 Digit, 7 Digit"}),
            "flipper_count": forms.NumberInput(
                attrs={"placeholder": "e.g., 2", "class": "form-input--width-4"}
            ),
            "pinside_rating": forms.NumberInput(
                attrs={"placeholder": "0.00-10.00", "step": "0.01", "class": "form-input--width-6"}
            ),
            "ipdb_id": forms.NumberInput(
                attrs={"placeholder": "e.g., 2355", "class": "form-input--width-6"}
            ),
            "production_quantity": forms.TextInput(
                attrs={"placeholder": "e.g., ~50,000", "class": "form-input--width-20"}
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


class MachineCreateModelExistsForm(StyledFormMixin, forms.Form):
    """Add an instance of an existing machine model."""

    instance_name = forms.CharField(
        max_length=100,
        required=True,
        label="Machine Name",
        help_text="A unique name to distinguish this machine from others of the same model",
    )

    def __init__(self, *args, model_name=None, instance_count=0, **kwargs):
        super().__init__(*args, **kwargs)
        self.model_name = model_name
        # Generate suggested name based on model and existing instance count
        next_number = instance_count + 1
        if model_name:
            suggested_name = f"{model_name} #{next_number}"
        else:
            suggested_name = f"Machine #{next_number}"
        # Update placeholder on existing widget (don't replace it, or we lose CSS classes)
        self.fields["instance_name"].widget.attrs["placeholder"] = f"e.g., {suggested_name}"

    def clean_instance_name(self):
        """Validate the instance name is unique and won't create duplicate display names."""
        name = self.cleaned_data["instance_name"].strip()

        # Check if name matches any model name (would create duplicate display_name)
        # This catches both the current model and other models (e.g., naming a
        # "Godzilla (Premium)" instance as "Godzilla" when a "Godzilla" model exists)
        if MachineModel.objects.filter(name__iexact=name).exists():
            raise ValidationError(
                "This name matches an existing model name. Please use a different name "
                f"like '{self.model_name} #2' to distinguish this machine."
            )

        # Check if name matches any existing machine's name_override
        if MachineInstance.objects.filter(name_override__iexact=name).exists():
            raise ValidationError("A machine with this name already exists.")

        return name


class MachineCreateModelDoesNotExistForm(StyledFormMixin, forms.Form):
    """Create a new machine model (and first instance)."""

    name = forms.CharField(
        max_length=100,
        required=True,
        label="Model Name",
        widget=forms.TextInput(attrs={"placeholder": "e.g., Space Wizards"}),
        help_text="The official name of this pinball machine",
    )

    manufacturer = forms.CharField(
        max_length=100,
        required=False,
        label="Manufacturer",
        widget=forms.TextInput(attrs={"placeholder": "e.g., Bally, Williams, Stern"}),
        help_text="The company that made this machine",
    )

    year = forms.IntegerField(
        required=False,
        label="Year",
        widget=forms.NumberInput(
            attrs={"placeholder": "e.g., 1979", "class": "form-input--width-8"}
        ),
        help_text="The year this model was manufactured",
    )

    def clean_name(self):
        """Validate the model name is unique."""
        name = self.cleaned_data["name"].strip()

        if MachineModel.objects.filter(name__iexact=name).exists():
            raise ValidationError(
                "A model with this name already exists. Please go back and select it from the list."
            )

        return name
