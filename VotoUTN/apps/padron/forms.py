from django import forms


class FormularioArchivoPadron(forms.Form):
    archivo = forms.FileField(widget=forms.ClearableFileInput(attrs={"accept": ".csv,.xlsx,.xls,text/csv,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"}))

    def clean_archivo(self):
        archivo = self.cleaned_data["archivo"]
        nombre = archivo.name.lower()
        if not nombre.endswith((".csv", ".xlsx", ".xls")):
            raise forms.ValidationError("Debe seleccionar un archivo CSV o Excel (.xlsx/.xls).")
        if archivo.size > 5 * 1024 * 1024:
            raise forms.ValidationError("El archivo no puede superar los 5 MB.")
        return archivo
