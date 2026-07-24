from PySide6.QtWidgets import QApplication, QLabel, QWidget, QVBoxLayout
from PySide6.QtCore import Qt

app = QApplication([])

# 测试 QLabel 是否继承父容器的边框样式
widget = QWidget()
widget.setStyleSheet("border: 2px solid red;")
layout = QVBoxLayout(widget)

label1 = QLabel("第一行")
label2 = QLabel("第二行")
layout.addWidget(label1)
layout.addWidget(label2)

widget.show()
print("Check if labels have borders - they should NOT if they don't have their own stylesheet")
