from PyQt5.QtWidgets import QFileDialog, QDialog, QPushButton, QGridLayout, QStackedWidget
import typing
from common_gui.algorithms_description import FormWidget
from partseg_utils.io_utils import SaveBase


class SaveProperty(typing.NamedTuple):
    save_destination: typing.Union[str, typing.List[str]]
    selected_filter: str
    save_class: SaveBase
    parameters: dict


class FormDialog(QDialog):
    def __init__(self, fields, values=None, image=None):
        super().__init__()
        self.widget = FormWidget(fields)
        if values is not None:
            self.widget.set_values(values)
        if image is not None:
            self.widget.image_changed(image)
        self.accept_btn = QPushButton("Save")
        self.accept_btn.clicked.connect(self.accept)
        self.reject_btn = QPushButton("Reject")
        self.reject_btn.clicked.connect(self.reject)
        layout = QGridLayout()
        layout.addWidget(self.widget, 0, 0, 1, 2)
        layout.addWidget(self.reject_btn, 1, 0)
        layout.addWidget(self.accept_btn, 1, 1)
        self.setLayout(layout)

    def get_values(self):
        return self.widget.get_values()

    def set_values(self, values):
        return self.widget.set_values(values)


class SaveDialog(QFileDialog):
    def __init__(self, save_register: typing.Dict[str, type(SaveBase)], system_widget=True,
                 base_values: typing.Optional[dict] = None, parent=None):
        super().__init__(parent)
        self.save_register = dict((x.get_name_with_suffix(), x) for x in save_register.values())
        self.setOption(QFileDialog.DontUseNativeDialog, not system_widget)
        self.setFileMode(QFileDialog.AnyFile)
        self.setAcceptMode(QFileDialog.AcceptSave)
        self.filterSelected.connect(self.change_filter)
        self.setNameFilters(self.save_register.keys())
        self.accepted_native = False
        self.values = {}
        self.names = []
        self.base_values = base_values if base_values is not None else {}
        if not system_widget:
            widget = QStackedWidget()
            for name, val in self.save_register.items():
                wi = FormWidget(val.get_fields())
                if name in self.base_values:
                    wi.set_values(self.base_values[name])
                widget.addWidget(wi)
                self.names.append(name)

            self.filterSelected.connect(self.change_parameters)

            layout = self.layout()
            if isinstance(layout, QGridLayout):
                print(layout.columnCount(), layout.rowCount())
                layout.addWidget(widget, 0, layout.columnCount(), layout.rowCount(), 1)
                self.stack_widget = widget

    def change_parameters(self, text):
        if not hasattr(self, "stack_widget"):
            return
        try:
            self.stack_widget.setCurrentIndex(self.names.index(text))
        except ValueError:
            pass

    def selectNameFilter(self, filter: str):
        try:
            self.change_parameters(filter)
        except IndexError:
            pass
        super().selectNameFilter(filter)
        try:
            ext = self.save_register[filter].get_default_extension()
            self.setDefaultSuffix(ext)
        except Exception:
            pass

    def change_filter(self, current_filter):
        ext = self.save_register[current_filter].get_default_extension()
        self.setDefaultSuffix(ext)

    def accept(self):
        self.accepted_native = True
        if hasattr(self, "stack_widget"):
            self.values = self.stack_widget.currentWidget().get_values()
            super().accept()
            return
        save_class = self.save_register[self.selectedNameFilter()]
        fields = save_class.get_fields()
        print(fields, len(fields))
        if len(fields) == 0:
            super().accept()
            return
        dial = FormDialog(fields)
        if self.selectedNameFilter() in self.base_values:
            dial.set_values(self.base_values[self.selectedNameFilter()])
        if dial.exec():
            self.values = dial.get_values()
            super().accept()
        else:
            super().reject()

    def get_result(self) -> SaveProperty:
        files = self.selectedFiles()
        return SaveProperty(files[0] if len(files) == 1 else files, self.selectedNameFilter(),
                            self.save_register[self.selectedNameFilter()], self.values)
