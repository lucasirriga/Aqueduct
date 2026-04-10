from qgis.PyQt.QtWidgets import (
    QAction, QDialog, QVBoxLayout, QFormLayout, QComboBox, QDoubleSpinBox, 
    QPushButton, QMessageBox, QLabel, QGroupBox
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

class GradeLinhasDialog(QDialog):
    def __init__(self, iface, parent=None):
        super().__init__(parent)
        self.iface = iface
        self.setWindowTitle("Aqueduct - Grade de Linhas (Paralelas)")
        self.resize(400, 400)
        self.setup_ui()
        
    def setup_ui(self):
        layout = QVBoxLayout()
        
        # 1. Seleção de Polígono (Limite)
        layout.addWidget(QLabel("<b>1. Limite do Recorte (Polígono):</b>"))
        self.combo_poly = QComboBox()
        layout.addWidget(self.combo_poly)
        
        # 2. Seleção de Linha (Referência)
        layout.addWidget(QLabel("<b>2. Linha de Referência (Base):</b>"))
        self.combo_line = QComboBox()
        layout.addWidget(self.combo_line)
        
        self.populate_layers()
        
        # 3. Espaçamento
        group_dims = QGroupBox("3. Parâmetros")
        form_dims = QFormLayout()
        
        self.spin_spacing = QDoubleSpinBox()
        self.spin_spacing.setRange(0.0001, 10000.0)
        self.spin_spacing.setDecimals(4)
        self.spin_spacing.setValue(10.0)
        self.spin_spacing.setSuffix(" m")
        
        form_dims.addRow("Espaçamento entre Linhas:", self.spin_spacing)
        
        group_dims.setLayout(form_dims)
        layout.addWidget(group_dims)
        
        # Action
        self.btn_run = QPushButton("Gerar Linhas Paralelas")
        self.btn_run.clicked.connect(self.run_process)
        layout.addWidget(self.btn_run)
        
        self.setLayout(layout)

    def populate_layers(self):
        self.combo_poly.clear()
        self.combo_line.clear()
        
        layers = QgsProject.instance().mapLayers().values()
        for layer in layers:
            if layer.type() == QgsMapLayerType.VectorLayer:
                if layer.geometryType() == QgsWkbTypes.PolygonGeometry:
                    self.combo_poly.addItem(layer.name(), layer)
                elif layer.geometryType() == QgsWkbTypes.LineGeometry:
                    self.combo_line.addItem(layer.name(), layer)

    def run_process(self):
        poly_layer = self.combo_poly.currentData()
        line_layer = self.combo_line.currentData()
        
        if not poly_layer:
            QMessageBox.warning(self, "Erro", "Selecione uma camada de Polígono (Limite).")
            return
            
        if not line_layer:
            QMessageBox.warning(self, "Erro", "Selecione uma camada de Linha (Referência).")
            return
            
        spacing = self.spin_spacing.value()
        
        # 1. Obter a Linha de Referência (Apenas UMA)
        ref_features = line_layer.selectedFeatures()
        if not ref_features:
            # Se não houver seleção, avisa ou pega a primeira?
            # Usuário disse "pegue A LINHA que informei". Melhor exigir seleção ou pegar a única se só tiver uma.
            if line_layer.featureCount() == 1:
                ref_features = list(line_layer.getFeatures())
            else:
                QMessageBox.warning(self, "Aviso", "Selecione UMA linha na camada de referência para servir de base.")
                return

        if len(ref_features) != 1:
             QMessageBox.warning(self, "Aviso", "Selecione exatamente UMA linha na camada de referência.")
             return

        ref_feat = ref_features[0]
        ref_geom = ref_feat.geometry()
        
        # Simplificando para Single Line se for Multi
        if ref_geom.isMultipart():
            # Pega a parte mais longa? Ou a primeira. Vamos na primeira.
            ref_geom = QgsGeometry.fromPolylineXY(ref_geom.asMultiPolyline()[0])
            
        # 2. Setup Output
        crs = poly_layer.crs()
        vl = QgsVectorLayer(f"LineString?crs={crs.authid()}", "Linhas Paralelas", "memory")
        pr = vl.dataProvider()
        pr.addAttributes([QgsField("ID_Line", QVariant.Int)])
        vl.updateFields()
        
        new_features = []
        feat_id = 1
        
        # 3. Processamento por Polígono Limite
        limit_features = poly_layer.selectedFeatures()
        if not limit_features:
            limit_features = poly_layer.getFeatures()
            
        for limit_feat in limit_features:
            limit_geom = limit_feat.geometry()
            bbox = limit_geom.boundingBox()
            
            # Cálculo da Extensão Necessária (Diagonal do Polígono + Margem)
            diag = math.sqrt(bbox.width()**2 + bbox.height()**2)
            extension_len = diag * 1.5 # 1.5x a diagonal para garantir (corresponde ao 1km+ pedido)
            if extension_len < 1000: extension_len = 1000 # Mínimo 1km se o poli for pequeno
            
            # 4. Estender a Linha Base
            # Precisamos dos vetores da linha base.
            # Se for polilinha complexa, "estender" é ambíguo.
            # Vamos assumir que a 'direção' geral é dada pelo primeiro e último ponto ou segmento principal?
            # Ou fazemos offset da geometria inteira?
            # Usuário disse "aumente em 1km... depois copie paralelamente".
            # Isso sugere offset geométrico da linha inteira.
            # Mas para "estender", QgsGeometry.extendLine é útil se for linha reta.
            # Se for curva, extendemos os finais.
            
            # Vamos criar uma versão estendida da linha base.
            extended_base = QgsGeometry(ref_geom)
            extended_base.extendLine(extension_len, extension_len)
            
            # Agora geramos offsets paralelos para ambos os lados
            # Até cobrir o polígono.
            
            # Quantos offsets?
            # Podemos estimar pela diagonal do polígono / espaçamento
            max_lines_per_side = int((diag / spacing) * 1.5) + 5
            
            # Lista de geometrias para testar (Base + Offsets Positivos + Offsets Negativos)
            lines_to_process = [extended_base]
            
            # Lado Esquerdo (Distâncias Positivas)
            for i in range(1, max_lines_per_side):
                dist = i * spacing
                # offsetCurve(distance, segments, joinStyle, miterLimit)
                # JoinStyle: 0=Round, 1=Miter, 2=Bevel.
                # Precisamos passar o Enum, não int.
                off_geom = extended_base.offsetCurve(dist, 1, QgsGeometry.JoinStyle.Miter, 5.0)
                if off_geom and not off_geom.isEmpty():
                     lines_to_process.append(off_geom)
            
            # Lado Direito (Distâncias Negativas)
            for i in range(1, max_lines_per_side):
                dist = -i * spacing
                off_geom = extended_base.offsetCurve(dist, 1, QgsGeometry.JoinStyle.Miter, 5.0)
                if off_geom and not off_geom.isEmpty():
                     lines_to_process.append(off_geom)
                     
            # 5. Clipar
            for line in lines_to_process:
                if line.intersects(limit_geom):
                    clipped = line.intersection(limit_geom)
                    if not clipped.isEmpty():
                        if clipped.isMultipart():
                            parts = clipped.asMultiPolyline()
                            for part in parts:
                                f = QgsFeature()
                                f.setGeometry(QgsGeometry.fromPolylineXY(part))
                                f.setAttributes([feat_id])
                                new_features.append(f)
                                feat_id += 1
                        else:
                            f = QgsFeature()
                            f.setGeometry(clipped)
                            f.setAttributes([feat_id])
                            new_features.append(f)
                            feat_id += 1

        if new_features:
            pr.addFeatures(new_features)
            QgsProject.instance().addMapLayer(vl)
            QMessageBox.information(self, "Sucesso", f"{len(new_features)} linhas geradas.")
        else:
            QMessageBox.warning(self, "Aviso", "Nenhuma linha gerada. Verifique se a linha de referência está próxima ou se o espaçamento é adequado.")

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
