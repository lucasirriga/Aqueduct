from qgis.PyQt.QtWidgets import (
    QAction, QDialog, QVBoxLayout, QFormLayout, QComboBox, QDoubleSpinBox,
    QPushButton, QMessageBox, QLabel, QGroupBox, QHBoxLayout
)
from qgis.PyQt.QtGui import QIcon
from qgis.core import (
    QgsProject, QgsWkbTypes, QgsVectorLayer, QgsFeature, QgsGeometry,
    QgsPointXY, QgsField
)
from qgis.PyQt.QtCore import QVariant
import os
import math

from .ferramenta_base import AqueductTool

class CriarAspersoresDialog(QDialog):
    def __init__(self, iface, parent=None):
        super().__init__(parent)
        self.iface = iface
        self.setWindowTitle("Aqueduct - Criar Aspersores (Triângulo)")
        self.resize(400, 400)
        self.setup_ui()

    def setup_ui(self):
        layout = QVBoxLayout()

        # 1. Seleção de Polígono
        layout.addWidget(QLabel("<b>1. Área Alvo (Polígono):</b>"))
        self.combo_layer = QComboBox()
        self.populate_layers()
        layout.addWidget(self.combo_layer)

        # 2. Dimensões do Triângulo
        group_dims = QGroupBox("2. Dimensões do Triângulo (metros)")
        form_dims = QFormLayout()

        self.spin_base = QDoubleSpinBox()
        self.spin_base.setRange(0.1, 1000.0)
        self.spin_base.setValue(12.0)
        self.lbl_base = QLabel("Base (Distância Horizontal X):")

        self.spin_altura = QDoubleSpinBox()
        self.spin_altura.setRange(0.1, 1000.0)
        self.spin_altura.setValue(10.0)
        self.lbl_altura = QLabel("Altura (Distância Vertical Y):")

        form_dims.addRow(self.lbl_base, self.spin_base)
        form_dims.addRow(self.lbl_altura, self.spin_altura)

        group_dims.setLayout(form_dims)
        layout.addWidget(group_dims)

        # 3. Rotação / Alinhamento
        group_rot = QGroupBox("3. Alinhamento")
        form_rot = QFormLayout()

        self.spin_angle = QDoubleSpinBox()
        self.spin_angle.setRange(0.0, 360.0)
        self.spin_angle.setDecimals(3)
        self.spin_angle.setValue(0.0)
        self.spin_angle.setSuffix(" °")

        self.btn_get_angle = QPushButton("Pegar da Seleção")
        self.btn_get_angle.setToolTip("Calcula o ângulo da linha selecionada na camada ativa")
        self.btn_get_angle.clicked.connect(self.get_angle_from_selection)

        layout_angle = QHBoxLayout()
        layout_angle.addWidget(self.spin_angle)
        layout_angle.addWidget(self.btn_get_angle)

        form_rot.addRow("Ângulo (Azimute):", layout_angle)
        group_rot.setLayout(form_rot)
        layout.addWidget(group_rot)

        # Action
        self.btn_run = QPushButton("Gerar Aspersores")
        self.btn_run.clicked.connect(self.run_process)
        layout.addWidget(self.btn_run)

        self.setLayout(layout)

    def get_angle_from_selection(self):
        layer = self.iface.activeLayer()
        if not layer or layer.type() != QgsVectorLayer.VectorLayer:
            QMessageBox.warning(self, "Aviso", "Selecione uma camada vetorial de Linha (Ativa).")
            return

        if layer.geometryType() != QgsWkbTypes.LineGeometry:
            QMessageBox.warning(self, "Aviso", "A camada ativa deve ser de Linha.")
            return

        features = layer.selectedFeatures()
        if len(features) != 1:
            QMessageBox.warning(self, "Aviso", "Selecione exatamente UMA linha na camada ativa.")
            return

        feat = features[0]
        geom = feat.geometry()

        if geom.isMultipart():
            geom = geom.asMultiPolyline()[0]
            p1 = geom[0]
            p2 = geom[1]
        else:
            p1 = geom.vertexAt(0)
            p2 = geom.vertexAt(1)

        dx = p2.x() - p1.x()
        dy = p2.y() - p1.y()
        rad = math.atan2(dy, dx)
        deg = math.degrees(rad)

        if deg < 0:
            deg += 360

        self.spin_angle.setValue(deg)
        QMessageBox.information(self, "Ângulo Capturado", f"Ângulo definido para: {deg:.3f}°")

    def populate_layers(self):
        self.combo_layer.clear()
        layers = QgsProject.instance().mapLayers().values()
        for layer in layers:
            if layer.type() == layer.VectorLayer and layer.geometryType() == QgsWkbTypes.PolygonGeometry:
                self.combo_layer.addItem(layer.name(), layer)

    def run_process(self):
        layer = self.combo_layer.currentData()
        if not layer:
            QMessageBox.warning(self, "Erro", "Selecione uma camada de polígono.")
            return

        angle_deg = self.spin_angle.value()
        angle_rad = math.radians(angle_deg)

        # Parâmetros do Triângulo
        step_x = self.spin_base.value()
        step_y = self.spin_altura.value()
        offset_odd_row = step_x / 2.0

        # Create output layer
        crs = layer.crs()
        vl = QgsVectorLayer(f"Point?crs={crs.authid()}", "Aspersores", "memory")
        pr = vl.dataProvider()
        pr.addAttributes([QgsField("ID_Aspersor", QVariant.Int)])
        vl.updateFields()

        new_features = []
        feat_id = 1

        features = layer.selectedFeatures()
        if not features:
            features = layer.getFeatures()

        for feat in features:
            geom = feat.geometry()
            bbox = geom.boundingBox()

            center = bbox.center()
            cx, cy = center.x(), center.y()

            min_u, max_u = float('inf'), float('-inf')
            min_v, max_v = float('inf'), float('-inf')

            for v in geom.vertices():
                dx = v.x() - cx
                dy = v.y() - cy

                cos_a = math.cos(-angle_rad)
                sin_a = math.sin(-angle_rad)

                u = dx * cos_a - dy * sin_a
                v = dx * sin_a + dy * cos_a

                min_u = min(min_u, u)
                max_u = max(max_u, u)
                min_v = min(min_v, v)
                max_v = max(max_v, v)

            min_u -= step_x
            max_u += step_x
            min_v -= step_y
            max_v += step_y

            curr_v = min_v
            row_idx = 0

            while curr_v <= max_v:
                # O offset na linha ímpar faz a malha ficar triangular
                row_offset_x = 0.0
                if row_idx % 2 != 0:
                    row_offset_x = offset_odd_row

                curr_u = min_u + row_offset_x

                while curr_u <= max_u:
                    cos_a = math.cos(angle_rad)
                    sin_a = math.sin(angle_rad)

                    rot_x = curr_u * cos_a - curr_v * sin_a
                    rot_y = curr_u * sin_a + curr_v * cos_a

                    final_x = cx + rot_x
                    final_y = cy + rot_y

                    point = QgsPointXY(final_x, final_y)

                    f = QgsFeature()
                    f.setGeometry(QgsGeometry.fromPointXY(point))
                    f.setAttributes([feat_id])
                    new_features.append(f)
                    feat_id += 1

                    curr_u += step_x

                curr_v += step_y
                row_idx += 1

        if new_features:
            pr.addFeatures(new_features)
            QgsProject.instance().addMapLayer(vl)

            # Utilizar a ferramenta de recorte já existente
            try:
                from .recortar_camada import RecortarCamadaTool

                # Define a nova camada de aspersores como ativa
                self.iface.setActiveLayer(vl)

                # Instancia a ferramenta de recorte existente
                clipping_tool = RecortarCamadaTool(self.iface, None)
                clipping_tool.run()

            except Exception as e:
                QMessageBox.warning(self, "Aviso", f"Aspersores gerados, mas falha ao chamar a ferramenta de recorte: {e}")

        else:
            QMessageBox.warning(self, "Aviso", "Nenhum aspersor gerado. Verifique os parâmetros.")

class CriarAspersoresTool(AqueductTool):
    def initGui(self):
        icon_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'icons', 'icone_grade.svg')
        self.action = QAction(QIcon(icon_path), 'Criar Aspersores (Triângulo)', self.iface.mainWindow())
        self.action.triggered.connect(self.run)

        self.iface.addPluginToMenu('&Aqueduct', self.action)

        if self.toolbar:
            self.toolbar.addAction(self.action)
        else:
            self.iface.addToolBarIcon(self.action)

    def run(self):
        dlg = CriarAspersoresDialog(self.iface, self.iface.mainWindow())
        dlg.exec_()
