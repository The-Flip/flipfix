# Forms Guide

This guide covers how to build forms for this project.

## Creating Form Classes

### Always Use StyledFormMixin

All forms should inherit from `StyledFormMixin` as the **first** parent class. This mixin automatically applies CSS classes to form widgets (`.form-input`, `.form-textarea`, `.checkbox`), ensuring consistent styling without manual widget configuration.

```python
from django import forms
from the_flip.apps.core.forms import StyledFormMixin

class MyForm(StyledFormMixin, forms.Form):
    name = forms.CharField()
    email = forms.EmailField()
```

Import from `the_flip.apps.core.forms`. Place `StyledFormMixin` first in the inheritance list so its `__init__` runs after Django's form initialization.

### Form vs ModelForm

| Use Case                                     | Base Class        |
| -------------------------------------------- | ----------------- |
| Editing an existing model instance           | `forms.ModelForm` |
| Creating a model with all/most of its fields | `forms.ModelForm` |
| Multi-step wizard (collecting partial data)  | `forms.Form`      |
| Actions that don't map to a single model     | `forms.Form`      |
| Creating multiple related objects at once    | `forms.Form`      |

**ModelForm** automatically generates fields from the model and provides a `save()` method. Use it when there's a direct 1:1 mapping between form and model.

**Form** gives full control over fields and validation. Use it for multi-step flows, search forms, or when the view needs to create multiple objects or do complex processing.

```python
# ModelForm: Direct model editing
class MachineInstanceForm(StyledFormMixin, forms.ModelForm):
    class Meta:
        model = MachineInstance
        fields = ["name", "serial_number"]

# Form: Custom creation flow (view handles object creation)
class MachineCreateModelDoesNotExistForm(StyledFormMixin, forms.Form):
    name = forms.CharField(max_length=100)
    manufacturer = forms.CharField(max_length=100, required=False)
    year = forms.IntegerField(required=False)
```

## Markdown Textareas

For fields that support markdown with `[[wiki links]]` and task list continuation, use `MarkdownTextarea` instead of `forms.Textarea`:

```python
from the_flip.apps.core.forms import MarkdownTextarea

class MyForm(StyledFormMixin, forms.ModelForm):
    class Meta:
        model = MyModel
        fields = ["content"]
        widgets = {
            "content": MarkdownTextarea(attrs={"rows": 10, "placeholder": "Write..."}),
        }
```

The widget provides these data attributes automatically:

- `data-text-textarea` — marks textarea for text editing features
- `data-link-autocomplete` — enables `[[link]]` autocomplete
- `data-link-api-url` — API endpoint for link suggestions (via `reverse_lazy`)
- `data-markdown-shortcuts` — enables smart wrapping, keyboard shortcuts, Tab indentation, and task list Enter continuation

Only specify per-field attrs like `rows` or `placeholder`. Custom attrs merge with and can override defaults.

Templates using this widget must include the companion scripts partial:

```html
{% include "core/partials/markdown_textarea_scripts.html" %}
```

## Rendering Forms in Templates

The project uses two approaches for rendering form fields:

1. **[Form components](#using-form-components)** (`{% form_field %}`, `{% form_fields %}`) - Use by default; handles label, input, help text, and errors automatically.

2. **[Manual markup](#manual-form-markup)** - For complex fields like autocomplete dropdowns, radio groups, and file uploads with preview.

### Using Form Components

**Render all fields at once:**

```html
{% load core_extras %}

<form method="post" class="form-main">
  {% csrf_token %} {% form_non_field_errors form %} {% form_fields form %}
  <div class="form-actions">
    <a href="{% url 'cancel' %}" class="btn btn--secondary">Cancel</a>
    <button type="submit" class="btn btn--primary">Save</button>
  </div>
</form>
```

**Render individual fields for more control:**

```html
{% load core_extras %}

<form method="post" class="form-main">
  {% csrf_token %} {% form_non_field_errors form %} {% form_field form.username %} {% form_field
  form.email %}
  <div class="form-actions">
    <a href="{% url 'cancel' %}" class="btn btn--secondary">Cancel</a>
    <button type="submit" class="btn btn--primary">Save</button>
  </div>
</form>
```

### Manual Form Markup

When `{% form_field %}` doesn't fit your needs (autocomplete, radio groups, file uploads, etc.), prefer helper tags over raw HTML. This keeps behavior consistent and makes future changes easier.

| Instead of                              | Use                           |
| --------------------------------------- | ----------------------------- |
| `<label class="form-label">...</label>` | `{% form_label field %}`      |
| `{{ field.label_tag }}`                 | `{% form_label field %}`      |
| Manual error checking                   | `{% field_errors field %}`    |
| Manual help text                        | `{% field_help_text field %}` |

Only use raw `<label>` when you need custom label text that differs from the Django field's label.

```html
<form method="post" class="form-main">
  {% csrf_token %} {% form_non_field_errors form %}

  <!-- Text field with extra elements -->
  <div class="form-field">
    {% form_label form.password %}
    <input
      type="password"
      id="{{ form.password.id_for_label }}"
      name="{{ form.password.html_name }}"
      class="form-input"
      required
    />
    {% field_errors form.password %}
    <label class="checkbox-label">
      <input type="checkbox" id="show-password" class="checkbox" />
      Show password
    </label>
  </div>

  <!-- Radio group - custom label text, so use raw <label> -->
  <div class="form-field">
    <label class="form-label">What type of problem?</label>
    <div class="radio-group">
      {% for radio in form.problem_type %}
      <label class="radio-label">
        {{ radio.tag }}
        <span>{{ radio.choice_label }}</span>
      </label>
      {% endfor %}
    </div>
    {% field_errors form.problem_type %}
  </div>

  <!-- Checkbox -->
  <label class="checkbox-label">
    <input type="checkbox" name="agree" class="checkbox" />
    <span>I agree to the terms</span>
  </label>

  <div class="form-actions">
    <a href="{% url 'cancel' %}" class="btn btn--secondary">Cancel</a>
    <button type="submit" class="btn btn--primary">Submit</button>
  </div>
</form>
```

## Required vs Optional Fields

**Do NOT label required fields with asterisks.** Instead, we label optional fields with "(optional)". This happens automatically when you use `{% form_field %}` or `{% form_label %}`.

Use HTML5 `required` attribute on inputs for browser validation.

## Form CSS Classes

| Class                   | Purpose                                                     |
| ----------------------- | ----------------------------------------------------------- |
| `.form-main`            | Form container with consistent spacing between fields       |
| `.form-field`           | Wrapper for label + input + help text + errors              |
| `.form-label`           | Field label styling                                         |
| `.form-input`           | Text inputs, selects, and textareas                         |
| `.form-input--width-4`  | Narrow width (4em) for single-digit inputs                  |
| `.form-input--width-6`  | Narrow width (6em) for small numbers                        |
| `.form-input--width-8`  | Narrow width (8em) for IDs                                  |
| `.form-input--width-10` | Narrow width (10em) for years                               |
| `.form-input--width-20` | Medium width (20em) for short text                          |
| `.form-textarea`        | Multi-line text input (extends `.form-input`)               |
| `.form-hint`            | Help text below inputs                                      |
| `.form-actions`         | Button container at form bottom (cancel left, submit right) |
| `.form-section`         | Fieldset with border for grouping related fields            |
| `.radio-group`          | Horizontal container for radio button options               |
| `.checkbox-label`       | Label wrapper for checkbox + text                           |

## Datetime Fields with Timezone Handling

When editing a timestamp that needs to be displayed in the user's local timezone and converted back to UTC on submit, use the following pattern:

### Template Structure

```html
<input type="hidden" name="browser_timezone" id="browser-timezone" />

<div class="form-group">
  <label for="{{ form.occurred_at.id_for_label }}" class="form-label">When</label>
  <input
    type="datetime-local"
    id="{{ form.occurred_at.id_for_label }}"
    name="{{ form.occurred_at.html_name }}"
    class="form-input"
    data-utc="{{ object.occurred_at.isoformat }}"
  />
  {% field_errors form.occurred_at %}
</div>
```

### JavaScript Initialization

```html
{% block extra_scripts %}
<script src="{% static 'core/core.js' %}" defer></script>
<script>
  document.addEventListener('DOMContentLoaded', function () {
    // Capture browser's IANA timezone (e.g., "America/Los_Angeles")
    document.getElementById('browser-timezone').value =
      Intl.DateTimeFormat().resolvedOptions().timeZone;

    // Convert UTC timestamp to local datetime-local value
    const input = document.getElementById('{{ form.occurred_at.id_for_label }}');
    if (input && input.dataset.utc) {
      const date = new Date(input.dataset.utc);
      input.value = toDateTimeLocalValue(date); // From core.js
    }
  });
</script>
{% endblock %}
```

### Server-Side Handling

```python
from zoneinfo import ZoneInfo

def form_valid(self, form):
    occurred_at = form.cleaned_data.get("occurred_at")
    if occurred_at:
        # Get user's timezone from hidden field
        tz_name = self.request.POST.get("browser_timezone", "UTC")
        try:
            user_tz = ZoneInfo(tz_name)
        except Exception:
            user_tz = ZoneInfo("UTC")

        # Convert naive datetime to UTC
        if occurred_at.tzinfo is None:
            local_dt = occurred_at.replace(tzinfo=user_tz)
            entry.occurred_at = local_dt.astimezone(ZoneInfo("UTC"))
```

**Why this pattern:**

- Uses IANA timezone names (e.g., `America/Los_Angeles`) instead of offsets, handling DST correctly
- The `datetime-local` input doesn't include timezone info, so we capture it separately
- `toDateTimeLocalValue()` from `core.js` formats a Date for the `datetime-local` input
