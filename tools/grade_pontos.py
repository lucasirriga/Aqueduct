import os
import math
from qgis.PyQt.QtWidgets import (
    QAction, QDialog, QVBoxLayout, QFormLayout, QComboBox, QDoubleSpinBox, 
    QPushButton, QMessageBox, QLabel, QRadioButton, QButtonGroup, QGroupBox,
    QHBoxLayout, QDialogButtonBox
)
from qgis.PyQt.QtGui import QIcon, QColor
from qgis.core import (
    QgsMapLayerType,
    QgsProject, QgsWkbTypes, QgsVectorLayer, QgsFeature, QgsGeometry, 
    QgsPointXY, QgsField, QgsMarkerSymbol, QgsSimpleMarkerSymbolLayer,
    QgsSymbol, Qgis
)
from qgis.PyQt.QtCore import QVariant, QTimer, Qt

from .ferramenta_base import AqueductTool

class GradePontosDialog(QDialog):
    def __init__(self, iface, parent=None):
        super().__init__(parent)
        self.iface = iface
        self.setWindowTitle("Aqueduct - Grade de Plantio")
        self.resize(400, 500)
        
        self.preview_layer = None
        self.preview_timer = QTimer()
        self.preview_timer.setSingleShot(True)
        self.preview_timer.timeout.connect(self.update_preview)
        
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
        self.btn_group.buttonToggled.connect(self.trigger_preview)
        
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
        
        # Conexões para Preview em tempo real
        self.combo_layer.currentIndexChanged.connect(self.trigger_preview)
        self.spin_lado_tri.valueChanged.connect(self.trigger_preview)
        self.spin_largura.valueChanged.connect(self.trigger_preview)
        self.spin_altura.valueChanged.connect(self.trigger_preview)
        self.spin_angle.valueChanged.connect(self.trigger_preview)
        
        # Action
        self.buttonBox = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        self.buttonBox.button(QDialogButtonBox.Ok).setText("Confirmar / Executar")
        self.buttonBox.button(QDialogButtonBox.Cancel).setText("Cancelar")
        self.buttonBox.accepted.connect(self.run_process)
        self.buttonBox.rejected.connect(self.reject)
        layout.addWidget(self.buttonBox)
        
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
        self.trigger_preview()

    def populate_layers(self):
        self.combo_layer.clear()
        layers = QgsProject.instance().mapLayers().values()
        for layer in layers:
            if layer.type() == QgsMapLayerType.VectorLayer and layer.geometryType() == QgsWkbTypes.PolygonGeometry:
                if layer.name() != "Prévia - Plantio":
                    self.combo_layer.addItem(layer.name(), layer)

    def toggle_inputs(self, _=None):
        is_tri = self.radio_tri.isChecked()
        
        self.lbl_lado_tri.setVisible(is_tri)
        self.spin_lado_tri.setVisible(is_tri)
        
        self.lbl_largura.setVisible(not is_tri)
        self.spin_largura.setVisible(not is_tri)
        self.lbl_altura.setVisible(not is_tri)
        self.spin_altura.setVisible(not is_tri)

    def trigger_preview(self):
        self.preview_timer.start(500)

    def clear_preview(self):
        if self.preview_layer:
            QgsProject.instance().removeMapLayer(self.preview_layer.id())
            self.preview_layer = None

    def setup_preview_layer(self, crs):
        self.clear_preview()
        self.preview_layer = QgsVectorLayer(f"Point?crs={crs.authid()}", "Prévia - Plantio", "memory")
        pr = self.preview_layer.dataProvider()
        pr.addAttributes([QgsField("ID_Ponto", QVariant.Int)])
        self.preview_layer.updateFields()
        
        # Estilo da Prévia (Pontos Laranja)
        marker_layer = QgsSimpleMarkerSymbolLayer()
        marker_layer.setColor(QColor("orange"))
        marker_layer.setStrokeColor(QColor("black"))
        marker_layer.setSize(1.5)
        
        symbol = QgsSymbol.defaultSymbol(self.preview_layer.geometryType())
        symbol.changeSymbolLayer(0, marker_layer)
        self.preview_layer.renderer().setSymbol(symbol)
        self.preview_layer.setCustomProperty("skipSelectOnDefault", 1)
        
        QgsProject.instance().addMapLayer(self.preview_layer, False)
        self.iface.mapCanvas().setLayers([self.preview_layer] + self.iface.mapCanvas().layers())

    def compute_points(self):
        layer = self.combo_layer.currentData()
        if not layer: return None
        
        is_tri = self.radio_tri.isChecked()
        angle_deg = self.spin_angle.value()
        angle_rad = math.radians(angle_deg)
        
        if is_tri:
            step_x = self.spin_lado_tri.value()
            step_y = step_x * math.sqrt(3) / 2.0
            offset_odd_row = step_x / 2.0
        else:
            step_x = self.spin_largura.value()
            step_y = self.spin_altura.value()
            offset_odd_row = 0.0
            
        features = layer.selectedFeatures()
        if not features:
            features = list(layer.getFeatures())
            
        new_geoms = []
        
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
                row_offset_x = 0.0
                if is_tri and (row_idx % 2 != 0):
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
                    
                    if geom.contains(point):
                        new_geoms.append(QgsGeometry.fromPointXY(point))
                    
                    curr_u += step_x
                
                curr_v += step_y
                row_idx += 1
                
        return new_geoms

    def update_preview(self):
        self.clear_preview()
        
        layer = self.combo_layer.currentData()
        if not layer: return
        
        self.setup_preview_layer(layer.crs())
        
        geoms = self.compute_points()
        if not geoms: return
        
        pr = self.preview_layer.dataProvider()
        feats = []
        for i, geom in enumerate(geoms):
            f = QgsFeature()
            f.setGeometry(geom)
            f.setAttributes([i + 1])
            feats.append(f)
            
        pr.addFeatures(feats)
        self.preview_layer.triggerRepaint()

    def run_process(self):
        layer = self.combo_layer.currentData()
        if not layer:
            QMessageBox.warning(self, "Erro", "Selecione uma camada de polígono.")
            return
            
        geoms = self.compute_points()
        if not geoms:
            QMessageBox.warning(self, "Aviso", "Nenhum ponto gerado. Verifique os parâmetros.")
            return
            
        crs = layer.crs()
        vl = QgsVectorLayer(f"Point?crs={crs.authid()}", "Grade Plantio", "memory")
        pr = vl.dataProvider()
        pr.addAttributes([QgsField("ID_Ponto", QVariant.Int)])
        vl.updateFields()
        
        feats = []
        for i, geom in enumerate(geoms):
            f = QgsFeature()
            f.setGeometry(geom)
            f.setAttributes([i + 1])
            feats.append(f)
            
        pr.addFeatures(feats)
        QgsProject.instance().addMapLayer(vl)
        self.accept()
        QMessageBox.information(self, "Sucesso", f"{len(feats)} pontos gerados.")

    def reject(self):
        self.clear_preview()
        if self.iface.mapCanvas():
            layers = [l for l in self.iface.mapCanvas().layers() if l.name() != "Prévia - Plantio"]
            self.iface.mapCanvas().setLayers(layers)
        super().reject()

class GradePontosTool(AqueductTool):
    def initGui(self):
        icon_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'icons', 'icone_grade_pontos.svg')
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
