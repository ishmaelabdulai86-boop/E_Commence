# products/forms.py
from django import forms
from .models import Product, Category, ProductImage, ProductSpecification
from django.forms import inlineformset_factory

class ProductForm(forms.ModelForm):
    class Meta:
        model = Product
        fields = [
            'name', 'sku', 'category', 'description', 'full_description',
            'price', 'discount_price', 'cost_price', 'stock', 'low_stock_threshold',
            'is_active', 'is_featured', 'is_on_sale', 'weight', 'dimensions'
        ]
        widgets = {
            'description': forms.Textarea(attrs={'rows': 3, 'class': 'form-control'}),
            'full_description': forms.Textarea(attrs={'rows': 5, 'class': 'form-control'}),
            'price': forms.NumberInput(attrs={'step': '0.01', 'class': 'form-control'}),
            'discount_price': forms.NumberInput(attrs={'step': '0.01', 'class': 'form-control'}),
            'cost_price': forms.NumberInput(attrs={'step': '0.01', 'class': 'form-control'}),
            'weight': forms.NumberInput(attrs={'step': '0.01', 'class': 'form-control'}),
        }
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        optional_fields = ['full_description', 'discount_price', 'weight', 'dimensions']
        
        for field_name, field in self.fields.items():
            if field_name not in ['is_active', 'is_featured', 'is_on_sale']:
                field.widget.attrs.update({'class': 'form-control'})
            elif field_name in ['is_active', 'is_featured', 'is_on_sale']:
                field.widget.attrs.update({'class': 'form-check-input'})
            
            if field_name in optional_fields:
                field.required = False

class ProductEditForm(forms.ModelForm):
    """Form for editing products - all fields are optional"""
    class Meta:
        model = Product
        fields = [
            'name', 'sku', 'category', 'description', 'full_description',
            'price', 'discount_price', 'cost_price', 'stock', 'low_stock_threshold',
            'is_active', 'is_featured', 'is_on_sale', 'weight', 'dimensions'
        ]
        widgets = {
            'description': forms.Textarea(attrs={'rows': 3, 'class': 'form-control'}),
            'full_description': forms.Textarea(attrs={'rows': 5, 'class': 'form-control'}),
            'price': forms.NumberInput(attrs={'step': '0.01', 'class': 'form-control'}),
            'discount_price': forms.NumberInput(attrs={'step': '0.01', 'class': 'form-control'}),
            'cost_price': forms.NumberInput(attrs={'step': '0.01', 'class': 'form-control'}),
            'weight': forms.NumberInput(attrs={'step': '0.01', 'class': 'form-control'}),
        }
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field_name, field in self.fields.items():
            if field_name not in ['is_active', 'is_featured', 'is_on_sale']:
                field.widget.attrs.update({'class': 'form-control'})
            elif field_name in ['is_active', 'is_featured', 'is_on_sale']:
                field.widget.attrs.update({'class': 'form-check-input'})
            field.required = False

# Form for Product Images
class ProductImageForm(forms.ModelForm):
    class Meta:
        model = ProductImage
        fields = ['image', 'is_primary', 'order']
        widgets = {
            'image': forms.FileInput(attrs={'class': 'form-control'}),
            'is_primary': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'order': forms.NumberInput(attrs={'class': 'form-control', 'min': '0'}),
        }
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Make all fields optional
        self.fields['image'].required = False
        self.fields['is_primary'].required = False
        self.fields['order'].required = False
    
    def clean(self):
        cleaned_data = super().clean()
        # Don't validate if the form is empty
        if not cleaned_data.get('image') and not self.instance.pk:
            raise forms.ValidationError('')  # Skip validation
        return cleaned_data

# Form for Product Specifications
class ProductSpecificationForm(forms.ModelForm):
    class Meta:
        model = ProductSpecification
        fields = ['key', 'value', 'order']
        widgets = {
            'key': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'e.g., Color'}),
            'value': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'e.g., Black'}),
            'order': forms.NumberInput(attrs={'class': 'form-control', 'min': '0'}),
        }
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Make all fields optional
        self.fields['key'].required = False
        self.fields['value'].required = False
        self.fields['order'].required = False
    
    def clean(self):
        cleaned_data = super().clean()
        # Skip validation if both key and value are empty and no instance exists
        if not cleaned_data.get('key') and not cleaned_data.get('value') and not self.instance.pk:
            raise forms.ValidationError('')  # Skip validation
        return cleaned_data

# Custom formset for images that allows empty forms
class BaseProductImageFormSet(forms.BaseInlineFormSet):
    def clean(self):
        """Allow empty forms without errors"""
        # Only run the parent clean() for forms that aren't empty
        pass  # Skip validation entirely
    
    def _construct_form(self, i, **kwargs):
        """Mark all forms as having empty_permitted=True"""
        kwargs['empty_permitted'] = True
        return super()._construct_form(i, **kwargs)

# Custom formset for specifications that allows empty forms
class BaseProductSpecificationFormSet(forms.BaseInlineFormSet):
    def clean(self):
        """Allow empty forms without errors"""
        # Only run the parent clean() for forms that aren't empty
        pass  # Skip validation entirely
    
    def _construct_form(self, i, **kwargs):
        """Mark all forms as having empty_permitted=True"""
        kwargs['empty_permitted'] = True
        return super()._construct_form(i, **kwargs)

# Create formset factories
ProductImageFormSet = inlineformset_factory(
    Product,
    ProductImage,
    form=ProductImageForm,
    formset=BaseProductImageFormSet,
    extra=3,
    can_delete=True,
    max_num=10,
)

ProductImageFormSetEdit = inlineformset_factory(
    Product, 
    ProductImage, 
    form=ProductImageForm,
    formset=BaseProductImageFormSet,
    extra=1,
    can_delete=True,
    max_num=10,
)

ProductSpecificationFormSet = inlineformset_factory(
    Product,
    ProductSpecification,
    form=ProductSpecificationForm,
    formset=BaseProductSpecificationFormSet,
    extra=2,
    can_delete=True,
    max_num=20,
)

ProductSpecificationFormSetEdit = inlineformset_factory(
    Product,
    ProductSpecification,
    form=ProductSpecificationForm,
    formset=BaseProductSpecificationFormSet,
    extra=1,
    can_delete=True,
    max_num=20,
)

class CategoryForm(forms.ModelForm):
    class Meta:
        model = Category
        fields = ['name', 'description', 'image', 'icon', 'is_active', 'parent']
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control'}),
            'description': forms.Textarea(attrs={'rows': 3, 'class': 'form-control'}),
            'icon': forms.TextInput(attrs={'class': 'form-control'}),
            'parent': forms.Select(attrs={'class': 'form-control'}),
        }