from qgis.PyQt.QtWidgets import (
    QAction, QDialog, QVBoxLayout, QFormLayout, QComboBox, QDoubleSpinBox, 
    QPushButton, QMessageBox, QLabel, QRadioButton, QButtonGroup, QGroupBox,
    QHBoxLayout
)
from qgis.PyQt.QtGui import QIcon
from qgis.core import (
    QgsMapLayerType,
    QgsProject, QgsWkbTypes, QgsVectorLayer, QgsFeature, QgsGeometry, 
    QgsPointXY, QgsField
)
from qgis.PyQt.QtCore import QVariant
import os
import math

from .ferramenta_base import AqueductTool

class GradePontosDialog(QDialog):
    def __init__(self, iface, parent=None):
        super().__init__(parent)
        self.iface = iface
        self.setWindowTitle("Aqueduct - Grade de Plantio")
        self.resize(400, 500)
        self.setup_ui()
        
    def setup_ui(self):
        layout = QVBoxLayout()
        
        # 1. Seleção de Polígono
        layout.addWidget(QLabel("<b>1. Área de Plantio (Polígono):</b>"))
        self.combo_layer = QComboBox()
        self.populate_layers()
        layout.addWidget(self.combo_layer)
        
        # 2. Tipo de Grade
        group_type = QGroupBox("2. Padrão de Plantio")
        vbox_type = QVBoxLayout()
        
        self.radio_tri = QRadioButton("Triângulo Equilátero")
        self.radio_rect = QRadioButton("Retângulo")
        self.radio_tri.setChecked(True)
        
        self.btn_group = QButtonGroup()
        self.btn_group.addButton(self.radio_tri)
        self.btn_group.addButton(self.radio_rect)
        
        vbox_type.addWidget(self.radio_tri)
        vbox_type.addWidget(self.radio_rect)
        group_type.setLayout(vbox_type)
        layout.addWidget(group_type)
        
        self.btn_group.buttonToggled.connect(self.toggle_inputs)
        
        # 3. Dimensões
        group_dims = QGroupBox("3. Espaçamento (metros)")
        form_dims = QFormLayout()
        
        self.spin_lado_tri = QDoubleSpinBox() # Lado / Entre Plantas
        self.spin_lado_tri.setRange(0.1, 1000.0)
        self.spin_lado_tri.setValue(3.0)
        self.lbl_lado_tri = QLabel("Lado (Entre Plantas):")
        
        self.spin_largura = QDoubleSpinBox() # Entre Linhas (Retangulo)
        self.spin_largura.setRange(0.1, 1000.0)
        self.spin_largura.setValue(3.0)
        self.lbl_largura = QLabel("Largura (X):")
        
        self.spin_altura = QDoubleSpinBox() # Entre Plantas (Retangulo)
        self.spin_altura.setRange(0.1, 1000.0)
        self.spin_altura.setValue(3.0)
        self.lbl_altura = QLabel("Altura (Y):")
        
        form_dims.addRow(self.lbl_lado_tri, self.spin_lado_tri)
        form_dims.addRow(self.lbl_largura, self.spin_largura)
        form_dims.addRow(self.lbl_altura, self.spin_altura)
        
        group_dims.setLayout(form_dims)
        layout.addWidget(group_dims)
        
        # 4. Rotação
        group_rot = QGroupBox("4. Alinhamento")
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
        self.btn_run = QPushButton("Gerar Grade de Pontos")
        self.btn_run.clicked.connect(self.run_process)
        layout.addWidget(self.btn_run)
        
        self.setLayout(layout)
        self.toggle_inputs()

    def get_angle_from_selection(self):
        layer = self.iface.activeLayer()
        if not layer or layer.type() != QgsMapLayerType.VectorLayer:
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
        
        # Pega o ângulo do primeiro segmento
        if geom.isMultipart():
            geom = geom.asMultiPolyline()[0]
            p1 = geom[0]
            p2 = geom[1]
        else:
            p1 = geom.vertexAt(0)
            p2 = geom.vertexAt(1)
            
        # Calcula azimute
        # math.atan2(y, x) retorna radianos.
        # QGIS Azimute geralmente é Norte=0, Clockwise?
        # A ferramenta de grade usa "math.cos(angle_rad)" onde 0=E, CounterClockwise (padrão trigonométrico).
        # Vamos manter o padrão trigonométrico (0 = Leste).
        
        dx = p2.x() - p1.x()
        dy = p2.y() - p1.y()
        rad = math.atan2(dy, dx)
        deg = math.degrees(rad)
        
        # Normaliza para 0-360
        if deg < 0:
            deg += 360
            
        self.spin_angle.setValue(deg)
        QMessageBox.information(self, "Ângulo Capturado", f"Ângulo definido para: {deg:.3f}°")


    def populate_layers(self):
        self.combo_layer.clear()
        layers = QgsProject.instance().mapLayers().values()
        for layer in layers:
            if layer.type() == QgsMapLayerType.VectorLayer and layer.geometryType() == QgsWkbTypes.PolygonGeometry:
                self.combo_layer.addItem(layer.name(), layer)

    def toggle_inputs(self, _=None):
        is_tri = self.radio_tri.isChecked()
        
        self.lbl_lado_tri.setVisible(is_tri)
        self.spin_lado_tri.setVisible(is_tri)
        
        self.lbl_largura.setVisible(not is_tri)
        self.spin_largura.setVisible(not is_tri)
        self.lbl_altura.setVisible(not is_tri)
        self.spin_altura.setVisible(not is_tri)

    def run_process(self):
        layer = self.combo_layer.currentData()
        if not layer:
            QMessageBox.warning(self, "Erro", "Selecione uma camada de polígono.")
            return
            
        is_tri = self.radio_tri.isChecked()
        angle_deg = self.spin_angle.value()
        angle_rad = math.radians(angle_deg)
        
        # Parameters
        if is_tri:
            step_x = self.spin_lado_tri.value()
            # Altura do triângulo equilátero: h = L * sqrt(3) / 2
            step_y = step_x * math.sqrt(3) / 2.0
            offset_odd_row = step_x / 2.0
        else:
            step_x = self.spin_largura.value()
            step_y = self.spin_altura.value()
            offset_odd_row = 0.0

        # Create output layer
        crs = layer.crs()
        vl = QgsVectorLayer(f"Point?crs={crs.authid()}", "Grade Plantio", "memory")
        pr = vl.dataProvider()
        pr.addAttributes([QgsField("ID_Ponto", QVariant.Int)])
        vl.updateFields()
        
        new_features = []
        feat_id = 1
        
        # Process selected feature or all features
        features = layer.selectedFeatures()
        if not features:
            features = layer.getFeatures()
            
        for feat in features:
            geom = feat.geometry()
            bbox = geom.boundingBox()
            
            # Rotation Logic:
            # We want rows aligned to 'angle'.
            # Instead of complex row logic, we rotate the polygon to become "flat" relative to the grid axes.
            # Grid axes (u, v).
            # Point P(x, y). 
            # Inverse Rotation: 
            # u = x cos(-a) - y sin(-a)
            # v = x sin(-a) + y cos(-a)
            
            # 1. Project Polygon Vertices to (u, v) space to find min/max U and V
            # We must account for the angle.
            
            # Simple approach: Create a grid large enough to cover the bounding circle of the polygon
            # and filter points.
            
            # Center of rotation (can be anything, let's use bbox center)
            center = bbox.center()
            cx, cy = center.x(), center.y()
            
            # Determine grid bounds in (u,v) space
            # Rotate polygon vertices to find min_u, max_u, min_v, max_v
            # u = (x-cx)cos(-a) - (y-cy)sin(-a)
            # v = (x-cx)sin(-a) + (y-cy)cos(-a)
            
            min_u, max_u = float('inf'), float('-inf')
            min_v, max_v = float('inf'), float('-inf')
            
            vertices = []
            # Extract all vertices from geometry to find efficient bounds
            # QgsGeometry.vertices() returns an iterator
            for v in geom.vertices():
                dx = v.x() - cx
                dy = v.y() - cy
                
                # Rotate by -angle to align with grid axes
                cos_a = math.cos(-angle_rad)
                sin_a = math.sin(-angle_rad)
                
                u = dx * cos_a - dy * sin_a
                v = dx * sin_a + dy * cos_a
                
                min_u = min(min_u, u)
                max_u = max(max_u, u)
                min_v = min(min_v, v)
                max_v = max(max_v, v)
            
            # Add some buffer
            min_u -= step_x
            max_u += step_x
            min_v -= step_y
            max_v += step_y
            
            # Generate Grid in U,V space
            curr_v = min_v
            row_idx = 0
            
            while curr_v <= max_v:
                # Calculate X offset for this row
                row_offset_x = 0.0
                if is_tri and (row_idx % 2 != 0):
                    row_offset_x = offset_odd_row
                
                curr_u = min_u + row_offset_x
                
                while curr_u <= max_u:
                    # Transform back to X,Y
                    # u = (x-cx)cos(-a) ... -> x-cx = u cos(a) - v sin(a)
                    # Coordinates relative to center
                    
                    # Rotate by +angle
                    cos_a = math.cos(angle_rad)
                    sin_a = math.sin(angle_rad)
                    
                    rot_x = curr_u * cos_a - curr_v * sin_a
                    rot_y = curr_u * sin_a + curr_v * cos_a
                    
                    final_x = cx + rot_x
                    final_y = cy + rot_y
                    
                    point = QgsPointXY(final_x, final_y)
                    
                    # Check if inside polygon
                    if geom.contains(point):
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
            QMessageBox.information(self, "Sucesso", f"{len(new_features)} pontos gerados.")
        else:
            QMessageBox.warning(self, "Aviso", "Nenhum ponto gerado. Verifique os parâmetros.")

class GradePontosTool(AqueductTool):
    def initGui(self):
        icon_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'icons', 'icone_grade.svg')
        self.action = QAction(QIcon(icon_path), 'Grade de Plantio', self.iface.mainWindow())
        self.action.triggered.connect(self.run)
        
        self.iface.addPluginToMenu('&Aqueduct', self.action)
        
        if self.toolbar:
            self.toolbar.addAction(self.action)
        else:
            self.iface.addToolBarIcon(self.action)
            
    def run(self):
        dlg = GradePontosDialog(self.iface, self.iface.mainWindow())
        dlg.exec_()
