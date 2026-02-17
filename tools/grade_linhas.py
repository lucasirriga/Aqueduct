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
        self.resize(400, 400)
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
        
        form_rot.addRow("Ângulo das Linhas:", layout_angle)
        group_rot.setLayout(form_rot)
        layout.addWidget(group_rot)
        
        # Action
        self.btn_run = QPushButton("Gerar Linhas Recortadas")
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
            
            # Inverse Rotation (Mundo -> Grade local alinhada com Eixos)
            # Queremos linhas horizontais (constantes em V) no sistema rotacionado.
            
            min_u, max_u = float('inf'), float('-inf')
            min_v, max_v = float('inf'), float('-inf')
            
            for v_pt in limit_geom.vertices():
                dx = v_pt.x() - cx
                dy = v_pt.y() - cy
                
                cos_a = math.cos(-angle_rad)
                sin_a = math.sin(-angle_rad)
                
                u = dx * cos_a - dy * sin_a
                v = dx * sin_a + dy * cos_a
                
                min_u = min(min_u, u)
                max_u = max(max_u, u)
                min_v = min(min_v, v)
                max_v = max(max_v, v)
                
            # Gera linhas
            # Começa do min_v ajustado
            # (Adiciona uma margem extra para garantir cobertura)
            # Margem de segurança para garantir que a linha atravesse todo o polígono
            # O bounding box calculado (min_u, max_u) é exato para os vértices, 
            # mas vamos dar uma folga extra de 1x o espaçamento para evitar problemas de precisão nas bordas.
            margin = spacing * 2
            start_line_u = min_u - margin
            end_line_u = max_u + margin
            
            # Ajuste do loop V
            # Começar um pouco antes e terminar um pouco depois
            curr_v = min_v - margin
            end_loop_v = max_v + margin

            cos_rot = math.cos(angle_rad)
            sin_rot = math.sin(angle_rad)
            
            while curr_v <= end_loop_v:
                # Linha no espaço U,V: (start_line_u, curr_v) -> (end_line_u, curr_v)
                
                # Transforma P1 (Inicio da linha)
                p1_u, p1_v = start_line_u, curr_v
                p1_x = cx + (p1_u * cos_rot - p1_v * sin_rot)
                p1_y = cy + (p1_u * sin_rot + p1_v * cos_rot)
                
                # Transforma P2 (Fim da linha)
                p2_u, p2_v = end_line_u, curr_v
                p2_x = cx + (p2_u * cos_rot - p2_v * sin_rot)
                p2_y = cy + (p2_u * sin_rot + p2_v * cos_rot)
                
                line_geom = QgsGeometry.fromPolylineXY([
                    QgsPointXY(p1_x, p1_y),
                    QgsPointXY(p2_x, p2_y)
                ])
                
                # Interseção
                if line_geom.intersects(limit_geom):
                    clipped_geom = line_geom.intersection(limit_geom)
                    
                    if not clipped_geom.isEmpty():
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
            QMessageBox.information(self, "Sucesso", f"{len(new_features)} segmentos de linha gerados.")
        else:
            QMessageBox.warning(self, "Aviso", "Nenhuma linha gerada.")

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
