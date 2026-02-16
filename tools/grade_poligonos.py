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

class GradePoligonosDialog(QDialog):
    def __init__(self, iface, parent=None):
        super().__init__(parent)
        self.iface = iface
        self.setWindowTitle("Aqueduct - Grade de Polígonos")
        self.resize(400, 450)
        self.setup_ui()
        
    def setup_ui(self):
        layout = QVBoxLayout()
        
        # 1. Seleção de Polígono (Limite)
        layout.addWidget(QLabel("<b>1. Limite do Recorte (Polígono):</b>"))
        self.combo_layer = QComboBox()
        self.populate_layers()
        layout.addWidget(self.combo_layer)
        
        # 2. Dimensões
        group_dims = QGroupBox("2. Tamanho da Célula (metros)")
        form_dims = QFormLayout()
        
        self.spin_width = QDoubleSpinBox()
        self.spin_width.setRange(0.1, 10000.0)
        self.spin_width.setValue(10.0)
        
        self.spin_height = QDoubleSpinBox()
        self.spin_height.setRange(0.1, 10000.0)
        self.spin_height.setValue(10.0)
        
        form_dims.addRow("Largura (X):", self.spin_width)
        form_dims.addRow("Altura (Y):", self.spin_height)
        
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
        
        form_rot.addRow("Ângulo da Grade:", layout_angle)
        group_rot.setLayout(form_rot)
        layout.addWidget(group_rot)
        
        # Action
        self.btn_run = QPushButton("Gerar Grade Recortada")
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
        # Reutilizando lógica de grade_pontos.py
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
            
        width = self.spin_width.value()
        height = self.spin_height.value()
        angle_deg = self.spin_angle.value()
        angle_rad = math.radians(angle_deg)
        
        # Cria camada temporária
        crs = layer.crs()
        vl = QgsVectorLayer(f"Polygon?crs={crs.authid()}", "Grade Polígonos", "memory")
        pr = vl.dataProvider()
        pr.addAttributes([QgsField("ID_Cell", QVariant.Int)])
        vl.updateFields()
        
        new_features = []
        feat_id = 1
        
        # Processamento
        # Selecionados ou todos
        features = layer.selectedFeatures()
        if not features:
            features = layer.getFeatures()
            
        # Para evitar sobreposição massiva se houver muitos polígonos limites,
        # idealmente processamos um a um ou fazemos union?
        # O usuário disse "recorte da camada de polígono de grade...".
        # Vamos processar por feature de limite.
        
        limit_count = 0
        
        for feat in features:
            limit_geom = feat.geometry()
            bbox = limit_geom.boundingBox()
            limit_count += 1
            
            # Centro para rotação (origem da grade relativa)
            # Pode ser o centro do bbox ou um ponto fixo. Usar centro bbox é seguro.
            center = bbox.center()
            cx, cy = center.x(), center.y()
            
            # Precisamos cobrir TODO o polígono limite com a grade.
            # Convertendo bbox do limite para espaço (u, v) da grade.
            
            # Rotação inversa (Mundo -> Grade)
            # u = (x-cx)cos(-a) - (y-cy)sin(-a)
            # v = (x-cx)sin(-a) + (y-cy)cos(-a)
            
            min_u, max_u = float('inf'), float('-inf')
            min_v, max_v = float('inf'), float('-inf')
            
            # Percorre vértices do limite para achar extensão na grade
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
                
            # Arredonda / Espande para garantir cobertura
            # Alinha min_u ao múltiplo de width inferior
            start_u = math.floor(min_u / width) * width
            end_u = math.ceil(max_u / width) * width
            
            start_v = math.floor(min_v / height) * height
            end_v = math.ceil(max_v / height) * height
            
            # Loop da Grade
            curr_v = start_v
            while curr_v < end_v:
                curr_u = start_u
                while curr_u < end_u:
                    # Cria retângulo no espaço (u, v)
                    # p1(u, v), p2(u+w, v), p3(u+w, v+h), p4(u, v+h)
                    
                    poly_uv = [
                        (curr_u, curr_v),
                        (curr_u + width, curr_v),
                        (curr_u + width, curr_v + height),
                        (curr_u, curr_v + height)
                    ]
                    
                    # Converte para (x, y)
                    poly_xy = []
                    cos_rot = math.cos(angle_rad)
                    sin_rot = math.sin(angle_rad)
                    
                    for u, v in poly_uv:
                        rot_x = u * cos_rot - v * sin_rot
                        rot_y = u * sin_rot + v * cos_rot
                        poly_xy.append(QgsPointXY(cx + rot_x, cy + rot_y))
                    
                    # Fecha polígono
                    poly_xy.append(poly_xy[0])
                    
                    # Cria Geometria
                    cell_geom = QgsGeometry.fromPolygonXY([poly_xy])
                    
                    # Interseção/Clip
                    if cell_geom.intersects(limit_geom):
                        # intersection retorna a geometria da sobreposição
                        clipped_geom = cell_geom.intersection(limit_geom)
                        
                        if not clipped_geom.isEmpty():
                            # Pode resultar em MultiPolygon ou Polygon
                            if clipped_geom.isMultipart():
                                parts = clipped_geom.asMultiPolygon()
                                for part in parts:
                                    f = QgsFeature()
                                    f.setGeometry(QgsGeometry.fromPolygonXY(part))
                                    f.setAttributes([feat_id])
                                    new_features.append(f)
                                    feat_id += 1
                            else:
                                f = QgsFeature()
                                f.setGeometry(clipped_geom)
                                f.setAttributes([feat_id])
                                new_features.append(f)
                                feat_id += 1
                    
                    curr_u += width
                curr_v += height
                
        if new_features:
            pr.addFeatures(new_features)
            QgsProject.instance().addMapLayer(vl)
            QMessageBox.information(self, "Sucesso", f"{len(new_features)} polígonos gerados.")
        else:
            QMessageBox.warning(self, "Aviso", "Nenhum polígono gerado.")

class GradePoligonosTool(AqueductTool):
    def initGui(self):
        icon_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'icons', 'icone_grade_poligono.svg')
        self.action = QAction(QIcon(icon_path), 'Grade de Polígonos', self.iface.mainWindow())
        self.action.triggered.connect(self.run)
        
        self.iface.addPluginToMenu('&Aqueduct', self.action)
        
        if self.toolbar:
            self.toolbar.addAction(self.action)
        else:
            self.iface.addToolBarIcon(self.action)
            
    def run(self):
        dlg = GradePoligonosDialog(self.iface, self.iface.mainWindow())
        dlg.exec_()
