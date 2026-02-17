from qgis.PyQt.QtWidgets import (
    QAction, QDialog, QVBoxLayout, QFormLayout, QComboBox, QDoubleSpinBox, 
    QPushButton, QMessageBox, QLabel, QHBoxLayout, QGroupBox
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

class GradeLinhasDialog(QDialog):
    def __init__(self, iface, parent=None):
        super().__init__(parent)
        self.iface = iface
        self.setWindowTitle("Aqueduct - Grade de Linhas")
        self.resize(400, 450)
        self.setup_ui()
        
    def setup_ui(self):
        layout = QVBoxLayout()
        
        # 1. Seleção de Polígono (Limite)
        layout.addWidget(QLabel("<b>1. Limite do Recorte (Polígono):</b>"))
        self.combo_layer = QComboBox()
        self.populate_layers()
        layout.addWidget(self.combo_layer)
        
        # 2. Espaçamento
        group_dims = QGroupBox("2. Espaçamento (metros)")
        form_dims = QFormLayout()
        
        self.spin_spacing = QDoubleSpinBox()
        self.spin_spacing.setRange(0.1, 10000.0)
        self.spin_spacing.setValue(10.0)
        
        form_dims.addRow("Distância entre Linhas:", self.spin_spacing)
        
        group_dims.setLayout(form_dims)
        layout.addWidget(group_dims)
        
        # 3. Alinhamento
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
        self.btn_run = QPushButton("Gerar Linhas")
        self.btn_run.clicked.connect(self.run_process)
        layout.addWidget(self.btn_run)
        
        self.setLayout(layout)

    def populate_layers(self):
        self.combo_layer.clear()
        layers = QgsProject.instance().mapLayers().values()
        for layer in layers:
            if layer.type() == layer.VectorLayer and layer.geometryType() == QgsWkbTypes.PolygonGeometry:
                self.combo_layer.addItem(layer.name(), layer)

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

    def run_process(self):
        layer = self.combo_layer.currentData()
        if not layer:
            QMessageBox.warning(self, "Erro", "Selecione uma camada de polígono limite.")
            return
            
        spacing = self.spin_spacing.value()
        angle_deg = self.spin_angle.value()
        angle_rad = math.radians(angle_deg)
        
        # Cria camada temporária
        crs = layer.crs()
        vl = QgsVectorLayer(f"LineString?crs={crs.authid()}", "Grade Linhas", "memory")
        pr = vl.dataProvider()
        pr.addAttributes([QgsField("ID_Line", QVariant.Int)])
        vl.updateFields()
        
        new_features = []
        feat_id = 1
        
        features = layer.selectedFeatures()
        if not features:
            features = layer.getFeatures()
            
        for feat in features:
            limit_geom = feat.geometry()
            bbox = limit_geom.boundingBox()
            
            center = bbox.center()
            cx, cy = center.x(), center.y()
            
            # --- Lógica de Varredura Robusta ---
            # 1. Definir extensão baseada na diagonal para garantir cobertura em qualquer rotação
            diag = math.sqrt(bbox.width()**2 + bbox.height()**2)
            extent = diag * 1.5
            
            # 2. Definir limites locais (u, v) centralizados
            min_local = -extent / 2
            max_local = extent / 2
            
            # 3. Iterar V (linhas)
            curr_v = min_local
            
            cos_rot = math.cos(angle_rad)
            sin_rot = math.sin(angle_rad)
            
            while curr_v <= max_local:
                # Criar Linha Horizontal no sistema Local: (min, v) -> (max, v)
                u1, v1 = min_local, curr_v
                u2, v2 = max_local, curr_v
                
                # Transformar para Global (Rotação + Translação)
                # x = cx + u*cos - v*sin
                # y = cy + u*sin + v*cos
                # Nota: Usei -v*sin e +v*cos na grade de pontos (rotação padrão).
                # Se grade_pontos usa:
                # rot_x = curr_u * cos_a - curr_v * sin_a
                # rot_y = curr_u * sin_a + curr_v * cos_a
                # Então aqui deve ser igual.
                
                p1_x = cx + (u1 * cos_rot - v1 * sin_rot)
                p1_y = cy + (u1 * sin_rot + v1 * cos_rot)
                
                p2_x = cx + (u2 * cos_rot - v2 * sin_rot)
                p2_y = cy + (u2 * sin_rot + v2 * cos_rot)
                
                line_geom = QgsGeometry.fromPolylineXY([
                    QgsPointXY(p1_x, p1_y),
                    QgsPointXY(p2_x, p2_y)
                ])
                
                # Clip / Interseção
                if line_geom.intersects(limit_geom):
                    clipped_geom = line_geom.intersection(limit_geom)
                    
                    if not clipped_geom.isEmpty():
                        # Lidar com multilinhas (polígono côncavo pode dividir a linha)
                        if clipped_geom.isMultipart():
                            parts = clipped_geom.asMultiPolyline()
                            for part in parts:
                                f = QgsFeature()
                                f.setGeometry(QgsGeometry.fromPolylineXY(part))
                                f.setAttributes([feat_id])
                                new_features.append(f)
                                feat_id += 1
                        else:
                            f = QgsFeature()
                            f.setGeometry(clipped_geom)
                            f.setAttributes([feat_id])
                            new_features.append(f)
                            feat_id += 1
                
                curr_v += spacing
                
        if new_features:
            pr.addFeatures(new_features)
            QgsProject.instance().addMapLayer(vl)
            QMessageBox.information(self, "Sucesso", f"{len(new_features)} linhas geradas.")
        else:
            QMessageBox.warning(self, "Aviso", "Nenhuma linha gerada no recorte.")

class GradeLinhasTool(AqueductTool):
    def initGui(self):
        icon_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'icons', 'icone_grade_linhas.svg')
        self.action = QAction(QIcon(icon_path), 'Grade de Linhas', self.iface.mainWindow())
        self.action.triggered.connect(self.run)
        
        self.iface.addPluginToMenu('&Aqueduct', self.action)
        
        if self.toolbar:
            self.toolbar.addAction(self.action)
        else:
            self.iface.addToolBarIcon(self.action)
            
    def run(self):
        dlg = GradeLinhasDialog(self.iface, self.iface.mainWindow())
        dlg.exec_()
