import os
import sys
from qtpy.QtWidgets import QWidget, QPushButton, QTreeWidget, QGridLayout, QFileDialog, QCheckBox, QInputDialog, \
    QTreeWidgetItem, QMessageBox
from qtpy.QtGui import QFontMetrics, QResizeEvent

from qtpy.QtCore import Qt
from typing import Callable, Any, Dict
from collections import defaultdict, Counter


from PartSeg.utils.io_utils import LoadBase, ProjectInfoBase
from .custom_load_dialog import CustomLoadDialog, LoadProperty
from .waiting_dialog import ExecuteFunctionDialog

class MultipleFileWidget(QWidget):
    def __init__(self, get_state: Callable[[], Any], set_state: Callable[[Any], Any], get_history, load_dict: Dict[str, LoadBase]):
        super().__init__()
        self.get_state = get_state
        self.set_state = set_state
        self.get_history = get_history
        self.state_dict = defaultdict(dict)
        self.state_dict_count = Counter()
        self.file_list = []
        self.load_register = load_dict
        self.file_view = QTreeWidget()
        self.file_view.header().close()
        self.save_state_btn = QPushButton("Save state")
        self.save_state_btn.setStyleSheet("QPushButton{font-weight: bold;}")
        self.load_files_btn = QPushButton("Load Files")
        self.forget_btn = QPushButton("Forget")

        self.save_state_btn.clicked.connect(self.save_state)
        self.forget_btn.clicked.connect(self.forget)
        self.load_files_btn.clicked.connect(self.load_files)
        self.file_view.itemDoubleClicked.connect(self.load_state)

        self.custom_names_chk = QCheckBox("Custom names")

        layout = QGridLayout()
        layout.addWidget(self.file_view, 0, 0, 1, 2)
        layout.addWidget(self.save_state_btn, 1, 0, 1, 2)
        layout.addWidget(self.load_files_btn, 2, 0)
        layout.addWidget(self.forget_btn, 2, 1)
        layout.addWidget(self.custom_names_chk, 3, 0)

        self.setLayout(layout)
        self.error_list = []

    def execute_load_files(self, load_data: LoadProperty, range_changed, step_changed):
        range_changed(0, len(load_data.load_location))
        for i, el in enumerate(load_data.load_location, 1):
            load_list = [el]
            while load_data.load_class.number_of_files() < len(load_list):
                load_list.append(load_data.load_class.get_next_file(load_list))
                if not os.path.exists(load_list[-1]):
                    self.error_list.append(el)
                    step_changed(i)
                    continue
            state: ProjectInfoBase = load_data.load_class.load(load_list)
            self.save_state_action(state, False)
            step_changed(i)

    def load_files(self):
        def exception_hook(exception):
            from qtpy.QtWidgets import QApplication
            from qtpy.QtCore import QMetaObject
            instance = QApplication.instance()
            if isinstance(exception, MemoryError):
                instance.warning = "Open error", f"Not enough memory to read this image: {exception}"
                QMetaObject.invokeMethod(instance, "show_warning", Qt.QueuedConnection)
            elif isinstance(exception, IOError):
                instance.warning = "Open error", f"Some problem with reading from disc: {exception}"
                QMetaObject.invokeMethod(instance, "show_warning", Qt.QueuedConnection)
            elif isinstance(exception, KeyError):
                instance.warning = "Open error", f"Some problem project file: {exception}"
                QMetaObject.invokeMethod(instance, "show_warning", Qt.QueuedConnection)
                print(exception, file=sys.stderr)
            else:
                raise exception
        dial = MultipleLoadDialog(self.load_register, self.get_history())
        self.error_list = []
        if dial.exec():
            result = dial.get_result()
            dial_fun = ExecuteFunctionDialog(self.execute_load_files, [result], exception_hook=exception_hook)
            dial_fun.exec()
            if self.error_list:
                errors_message = QMessageBox()
                errors_message.setText("There are errors during load files")
                errors_message.setInformativeText("During load files cannot found some of files on disc")
                errors_message.setStandardButtons(QMessageBox.Ok)
                text = "\n".join(["File: " + x[0] + "\n" + str(x[1]) for x in self.error_list])
                errors_message.setDetailedText(text)
                errors_message.exec()

    def load_state(self, item, _column):
        if item.parent() is None:
            return
        else:
            file_name = self.file_list[self.file_view.indexOfTopLevelItem(item.parent())]
            state_name = item.text(0)
            self.set_state(self.state_dict[file_name][state_name])

    def save_state(self):
        state: ProjectInfoBase = self.get_state()
        custom_name = self.custom_names_chk.isChecked()
        self.save_state_action(state, custom_name)


    def save_state_action(self, state: ProjectInfoBase, custom_name):
        #TODO left elipsis
        # state: ProjectInfoBase = self.get_state()
        sub_dict = self.state_dict[state.file_path]
        name = f"state {self.state_dict_count[state.file_path]+1}"
        if custom_name:
            name, ok = QInputDialog.getText(self, "Save name", "Save name:", text=name)
            if not ok:
                return
            while name in sub_dict:
                name, ok = QInputDialog.getText(self, "Save name", "Save name (previous in use):", text=name)
                if not ok:
                    return

        for i, text in enumerate(self.file_list):
            if text == state.file_path:
                item = self.file_view.topLevelItem(i)
                break
        else:
            metric = QFontMetrics(self.file_view.font())
            width = self.file_view.width() - 40
            clipped_text = metric.elidedText(state.file_path, Qt.ElideLeft, width)
            item = QTreeWidgetItem(self.file_view, [clipped_text])
            item.setToolTip(0, state.file_path)
            self.file_list.append(state.file_path)
        item.setExpanded(True)
        QTreeWidgetItem(item, [name])
        sub_dict[name] = state
        self.state_dict_count[state.file_path] += 1

    def forget(self):
        item: QTreeWidgetItem = self.file_view.currentItem()
        if item is None:
            return
        if isinstance(item.parent(), QTreeWidgetItem):
            del self.state_dict[item.parent().text(0)][item.text(0)]
            item.parent().removeChild(item)
        else:
            index = self.file_view.indexOfTopLevelItem(item)
            text = self.file_list[index]
            del self.state_dict[text]
            del self.state_dict_count[text]
            self.file_list.remove(text)
            self.file_view.takeTopLevelItem(index)

    def resizeEvent(self, event: QResizeEvent):
        metric = QFontMetrics(self.file_view.font())
        width = event.size().width() - 40
        for i, text in enumerate(self.file_list):
            clipped_text = metric.elidedText(text, Qt.ElideLeft, width)
            item: QTreeWidgetItem = self.file_view.topLevelItem(i)
            item.setText(0, clipped_text)



class MultipleLoadDialog(CustomLoadDialog):
    def __init__(self, load_register, history=None):
        super().__init__(load_register=load_register, history=history)
        self.setFileMode(QFileDialog.ExistingFiles)

    def accept(self):
        self.files_list.extend(self.selectedFiles())
        QFileDialog.accept(self)
