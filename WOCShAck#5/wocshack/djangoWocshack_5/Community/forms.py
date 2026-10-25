from django import forms
from django.forms import inlineformset_factory

from Community.models.content import Tutorial, TutorialStep


class FriendRequestActionForm(forms.Form):
    action = forms.ChoiceField(
        choices=(
            ("accepted", "Accepter"),
            ("rejected", "Refuser"),
        )
    )

class MessageForm(forms.Form):
    content = forms.CharField(
        widget=forms.Textarea(attrs={
            "rows": 2,
            "placeholder": "Write a message...",
            "class": "message-input",
            "id": "message-input"
        }),
        max_length=2000
    )


# ── Tutorial Steps ────────────────────────────────────────────────────────────

class TutorialStepForm(forms.ModelForm):
    class Meta:
        model = TutorialStep
        fields = ['order', 'title', 'content', 'code_example', 'has_interactive_editor']
        widgets = {
            'order': forms.NumberInput(attrs={
                'class': 'form-input', 'min': '1', 'placeholder': '#',
            }),
            'title': forms.TextInput(attrs={
                'class': 'form-input', 'maxlength': '255', 'placeholder': 'Step title',
            }),
            'content': forms.Textarea(attrs={
                'class': 'form-textarea', 'rows': '5', 'placeholder': 'Step content (Markdown supported)',
            }),
            'code_example': forms.Textarea(attrs={
                'class': 'form-textarea form-textarea--code', 'rows': '4', 'placeholder': 'Code snippet (optional)',
            }),
            'has_interactive_editor': forms.CheckboxInput(),
        }


TutorialStepFormSet = inlineformset_factory(
    Tutorial,
    TutorialStep,
    form=TutorialStepForm,
    extra=1,
    can_delete=True,
)