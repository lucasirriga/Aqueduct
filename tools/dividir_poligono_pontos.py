import os
import math
from qgis.PyQt.QtWidgets import (
    QAction, QDialog, QVBoxLayout, QFormLayout, QComboBox, QDoubleSpinBox, 
    QSpinBox, QPushButton, QMessageBox, QLabel, QHBoxLayout, QGroupBox, QRadioButton, QButtonGroup, QDialogButtonBox,
    QFileDialog
)
from qgis.PyQt.QtGui import QIcon, QColor, QFont
from qgis.PyQt.QtCore import QVariant, QTimer, Qt
from qgis.core import (
    Qgis, QgsMapLayerType, QgsProject, QgsWkbTypes, QgsVectorLayer, QgsFeature, 
    QgsGeometry, QgsPointXY, QgsField, QgsSpatialIndex, QgsPalLayerSettings,
    QgsVectorLayerSimpleLabeling, QgsTextFormat, QgsProperty, QgsFillSymbol,
    QgsVectorFileWriter, QgsSymbol, QgsSingleSymbolRenderer, QgsSimpleFillSymbolLayer
)
from qgis.gui import QgsRubberBand

from .ferramenta_base import AqueductTool

class DividirPoligonoPontosDialog(QDialog):
    def __init__(self, iface, parent=None):
        super().__init__(parent)
        self.iface = iface
        self.setWindowTitle("Aqueduct - Dividir Polígono por Pontos (v0.1.2)")
        self.resize(450, 600)
        
        # Elementos de preview
        self.preview_layer = None
        
        # Debounce timer para atualização do preview
        self.preview_timer = QTimer()
        self.preview_timer.setSingleShot(True)
        self.preview_timer.timeout.connect(self.update_preview)
        
        self.setup_ui()
        
    def setup_ui(self):
        layout = QVBoxLayout()
        
        # 1. Seleção de Camadas
        group_layers = QGroupBox("1. Seleção de Camadas")
        form_layers = QFormLayout()
        
        self.combo_poly = QComboBox()
        self.combo_points = QComboBox()
        self.combo_line = QComboBox()
        self.combo_target = QComboBox()
        
        self.populate_layers()
        
        form_layers.addRow("Polígono Limite:", self.combo_poly)
        form_layers.addRow("Malha de Pontos:", self.combo_points)
        form_layers.addRow("Linha de Referência:", self.combo_line)
        form_layers.addRow("Camada de Destino:", self.combo_target)
        group_layers.setLayout(form_layers)
        layout.addWidget(group_layers)
        
        # 2. Parâmetros de Divisão
        group_params = QGroupBox("2. Parâmetros de Divisão")
        form_params = QFormLayout()
        
        self.spin_step = QDoubleSpinBox()
        self.spin_step.setRange(0.1, 10000.0)
        self.spin_step.setValue(5.0)
        self.spin_step.setSuffix(" m")
        
        self.spin_margin = QDoubleSpinBox()
        self.spin_margin.setRange(0.0, 100.0)
        self.spin_margin.setValue(5.0)
        self.spin_margin.setSuffix(" %")
        
        form_params.addRow("Espaçamento Fixo (Cortes):", self.spin_step)
        form_params.addRow("Margem de Erro Aceitável:", self.spin_margin)
        group_params.setLayout(form_params)
        layout.addWidget(group_params)
        
        # 3. Critério de Divisão
        group_crit = QGroupBox("3. Critério de Divisão")
        layout_crit = QVBoxLayout()
        
        self.radio_points = QRadioButton("A) Pontos por polígono (Alvo Fixo)")
        self.radio_points.setChecked(True)
        self.spin_target_points = QSpinBox()
        self.spin_target_points.setRange(1, 1000000)
        self.spin_target_points.setValue(400)
        
        layout_points = QHBoxLayout()
        layout_points.addWidget(self.radio_points)
        layout_points.addWidget(self.spin_target_points)
        layout_crit.addLayout(layout_points)
        
        self.radio_polys = QRadioButton("B) Quantidade de polígonos (Alvo Calculado)")
        self.spin_target_polys = QSpinBox()
        self.spin_target_polys.setRange(1, 1000)
        self.spin_target_polys.setValue(4)
        
        layout_polys = QHBoxLayout()
        layout_polys.addWidget(self.radio_polys)
        layout_polys.addWidget(self.spin_target_polys)
        layout_crit.addLayout(layout_polys)
        
        self.bg_crit = QButtonGroup()
        self.bg_crit.addButton(self.radio_points)
        self.bg_crit.addButton(self.radio_polys)
        
        group_crit.setLayout(layout_crit)
        layout.addWidget(group_crit)
        
        # 4. Tratamento da Sobra
        group_rem = QGroupBox("4. Tratamento da Sobra")
        layout_rem = QVBoxLayout()
        
        self.combo_remainder = QComboBox()
        self.combo_remainder.addItems(["Aceitar Resto (Ignora erro no último)", "Mesclar com Anterior", "Distribuir (Recalcula alvos)"])
        layout_rem.addWidget(self.combo_remainder)
        group_rem.setLayout(layout_rem)
        layout.addWidget(group_rem)
        
        # Conexões para Preview em tempo real
        self.combo_poly.currentIndexChanged.connect(self.trigger_preview)
        self.combo_points.currentIndexChanged.connect(self.trigger_preview)
        self.combo_line.currentIndexChanged.connect(self.trigger_preview)
        self.spin_step.valueChanged.connect(self.trigger_preview)
        self.spin_margin.valueChanged.connect(self.trigger_preview)
        self.spin_target_points.valueChanged.connect(self.trigger_preview)
        self.spin_target_polys.valueChanged.connect(self.trigger_preview)
        self.radio_points.toggled.connect(self.trigger_preview)
        self.combo_remainder.currentIndexChanged.connect(self.trigger_preview)
        
        # Botões Executar / Cancelar
        self.buttonBox = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        self.buttonBox.button(QDialogButtonBox.Ok).setText("Confirmar / Executar")
        self.buttonBox.button(QDialogButtonBox.Cancel).setText("Cancelar")
        self.buttonBox.accepted.connect(self.run_process)
        self.buttonBox.rejected.connect(self.reject)
        layout.addWidget(self.buttonBox)
        
        self.setLayout(layout)
        
    def populate_layers(self):
        self.combo_poly.clear()
        self.combo_points.clear()
        self.combo_line.clear()
        self.combo_target.clear()
        
        self.combo_target.addItem("[Criar Novo Arquivo]", None)
        
        layers = QgsProject.instance().mapLayers().values()
        for layer in layers:
            if layer.type() == QgsMapLayerType.VectorLayer:
                geom_type = layer.geometryType()
                if geom_type == QgsWkbTypes.PolygonGeometry:
                    self.combo_poly.addItem(layer.name(), layer)
                    if layer.name() != "Prévia - Divisão":
                        self.combo_target.addItem(layer.name(), layer)
                elif geom_type == QgsWkbTypes.PointGeometry:
                    self.combo_points.addItem(layer.name(), layer)
                elif geom_type == QgsWkbTypes.LineGeometry:
                    self.combo_line.addItem(layer.name(), layer)
                    
        idx = self.combo_target.findText("SETORES")
        if idx >= 0:
            self.combo_target.setCurrentIndex(idx)
                    
    def trigger_preview(self):
        # Reinicia o timer para 500ms
        self.preview_timer.start(500)
        
    def clear_preview(self):
        if self.preview_layer:
            QgsProject.instance().removeMapLayer(self.preview_layer.id())
            self.preview_layer = None
        
    def setup_preview_layer(self, crs):
        self.clear_preview()
        self.preview_layer = QgsVectorLayer(f"Polygon?crs={crs.authid()}", "Prévia - Divisão", "memory")
        pr = self.preview_layer.dataProvider()
        pr.addAttributes([QgsField("pontos", QVariant.Int)])
        self.preview_layer.updateFields()
        
        # Estilo do Polígono
        symbol = QgsFillSymbol.createSimple({'color': '0,0,255,50', 'outline_color': '0,0,255,255', 'outline_width': '0.5'})
        self.preview_layer.renderer().setSymbol(symbol)
        
        # Configurar Rótulos (Labels)
        settings = QgsPalLayerSettings()
        settings.fieldName = "pontos"
        settings.isExpression = True
        settings.fieldName = "tostring(\"pontos\") || ' pontos'"
        text_format = QgsTextFormat()
        text_format.setFont(QFont("Arial", 10, QFont.Bold))
        text_format.setColor(QColor("white"))
        settings.setFormat(text_format)
        settings.placement = Qgis.LabelPlacement.Horizontal
        
        labeling = QgsVectorLayerSimpleLabeling(settings)
        self.preview_layer.setLabelsEnabled(True)
        self.preview_layer.setLabeling(labeling)
        
        # Ocultar da legenda (opcional) para não poluir
        self.preview_layer.setCustomProperty("skipSelectOnDefault", 1)
        
        QgsProject.instance().addMapLayer(self.preview_layer, False) # Adiciona mas não na árvore de camadas
        self.iface.mapCanvas().setLayers([self.preview_layer] + self.iface.mapCanvas().layers())

    def compute_slices(self):
        """Motor de geometria: Retorna uma lista de tuplas (geom, point_count) ou None se erro."""
        poly_layer = self.combo_poly.currentData()
        pts_layer = self.combo_points.currentData()
        line_layer = self.combo_line.currentData()
        
        if not poly_layer or not pts_layer or not line_layer:
            return None
            
        step = self.spin_step.value()
        margin_pct = self.spin_margin.value()
        is_fixed_points = self.radio_points.isChecked()
        target_pts_val = self.spin_target_points.value()
        target_polys_val = self.spin_target_polys.value()
        remainder_opt = self.combo_remainder.currentIndex() # 0: Aceitar, 1: Mesclar, 2: Distribuir
        
        # Pega a geometria do polígono limite (usa o primeiro selecionado ou o primeiro da camada)
        poly_feat = None
        if poly_layer.selectedFeatureCount() > 0:
            poly_feat = poly_layer.selectedFeatures()[0]
        else:
            for f in poly_layer.getFeatures():
                poly_feat = f
                break
        if not poly_feat: return None
        poly_geom = poly_feat.geometry()
        
        # Pega a geometria da linha de referência
        line_feat = None
        if line_layer.selectedFeatureCount() > 0:
            line_feat = line_layer.selectedFeatures()[0]
        else:
            for f in line_layer.getFeatures():
                line_feat = f
                break
        if not line_feat: return None
        
        line_geom = line_feat.geometry()
        if line_geom.isMultipart():
            line_parts = line_geom.asMultiPolyline()
            if not line_parts: return None
            p1, p2 = line_parts[0][0], line_parts[0][-1]
        else:
            line_poly = line_geom.asPolyline()
            if not line_poly: return None
            p1, p2 = line_poly[0], line_poly[-1]
            
        dx = p2.x() - p1.x()
        dy = p2.y() - p1.y()
        angle = math.atan2(dy, dx) # Orientação da linha
        
        # Obter todos os pontos contidos no polígono limite
        pts_inside = []
        for p_feat in pts_layer.getFeatures():
            p_geom = p_feat.geometry()
            if poly_geom.contains(p_geom):
                pts_inside.append(p_geom.asPoint())
                
        total_pts = len(pts_inside)
        if total_pts == 0: return None
        
        # Definir Estratégia de Alvos (Erro Acumulado)
        if is_fixed_points:
            if remainder_opt == 2: # Distribuir ativo na Opção A
                num_polys = max(1, round(total_pts / target_pts_val))
                ideal_target = total_pts / num_polys
            else:
                num_polys = None # Indefinido, segue até acabar
                ideal_target = target_pts_val
        else:
            num_polys = target_polys_val if target_polys_val > 0 else 1
            ideal_target = total_pts / num_polys
            
        # Converter para coordenadas (U, V) relativas ao centro do bbox do polígono
        pivot = poly_geom.boundingBox().center()
        cos_a = math.cos(-angle)
        sin_a = math.sin(-angle)
        
        pts_v = []
        for p in pts_inside:
            v = (p.x() - pivot.x()) * sin_a + (p.y() - pivot.y()) * cos_a
            pts_v.append(v)
            
        # Encontrar min/max U e V do polígono
        poly_u = []
        poly_v = []
        for v in poly_geom.vertices():
            u = (v.x() - pivot.x()) * cos_a - (v.y() - pivot.y()) * sin_a
            vv = (v.x() - pivot.x()) * sin_a + (v.y() - pivot.y()) * cos_a
            poly_u.append(u)
            poly_v.append(vv)
            
        if not poly_u: return None
        min_u, max_u = min(poly_u), max(poly_u)
        min_v, max_v = min(poly_v), max(poly_v)
        
        # Algoritmo de Varredura
        slices_v = [] # guarda tuplas (start_v, end_v, pts_count)
        
        start_v = math.floor(min_v / step) * step
        curr_v = start_v + step
        
        best_v = None
        best_diff = float('inf')
        best_count = 0
        
        poly_index = 1
        accumulated_pts = 0
        
        while curr_v <= math.ceil(max_v / step) * step + step:
            
            # Calcular o alvo específico para a fatia atual (compensação de erro)
            if remainder_opt == 2 and num_polys is not None:
                # O alvo atual é a soma ideal esperada até aqui, menos o que já foi acumulado antes
                current_target = (ideal_target * poly_index) - accumulated_pts
            else:
                current_target = ideal_target
                
            margin = ideal_target * (margin_pct / 100.0)
            
            # Conta pontos na fatia atual (do start_v até curr_v)
            count = sum(1 for v in pts_v if start_v < v <= curr_v)
            diff = abs(count - current_target)
            
            if diff <= margin:
                # Atingiu o alvo perfeitamente dentro da margem
                slices_v.append((start_v, curr_v, count))
                accumulated_pts += count
                poly_index += 1
                
                start_v = curr_v
                best_v = None
                best_diff = float('inf')
            else:
                # Passou do alvo mas errou a margem, ou ainda nao chegou
                if count > current_target + margin:
                    # Overshoot. Usar o melhor candidato anterior se existir
                    if best_v is not None:
                        slices_v.append((start_v, best_v, best_count))
                        accumulated_pts += best_count
                        poly_index += 1
                        
                        start_v = best_v
                        best_v = None
                        best_diff = float('inf')
                        curr_v = start_v # retrocede para continuar do corte certo
                    else:
                        # Se passou do alvo no primeiro step, tem que aceitar
                        slices_v.append((start_v, curr_v, count))
                        accumulated_pts += count
                        poly_index += 1
                        
                        start_v = curr_v
                        best_v = None
                        best_diff = float('inf')
                else:
                    # Undershoot. Acompanha qual foi o melhor
                    if diff < best_diff:
                        best_v = curr_v
                        best_diff = diff
                        best_count = count
            
            curr_v += step
            
            # Se já achou todos os poligonos sob a estratégia Distribuir, 
            # não continua o while, joga o resto pra sobra.
            if num_polys is not None and poly_index > num_polys:
                break
            
        # Tratar a Sobra (o que ficou além do último start_v até o max_v)
        rem_count = sum(1 for v in pts_v if start_v < v <= max_v)
        if rem_count > 0:
            if (remainder_opt == 1 or remainder_opt == 2) and slices_v: 
                # Mesclar ou Distribuir (Distribuir funde a mini rebarba com o último alvo preenchido)
                last_slice = slices_v.pop()
                slices_v.append((last_slice[0], max_v + step, last_slice[2] + rem_count)) 
            else: 
                # Aceitar Resto (Gera um polígono final com a sobra, por menor que seja)
                slices_v.append((start_v, max_v + step, rem_count))
                
        # Gerar geometrias dos slices
        final_slices = []
        cos_rot = math.cos(angle)
        sin_rot = math.sin(angle)
        
        for sv, ev, c in slices_v:
            # Retângulo no espaço UV
            poly_uv = [
                (min_u - 100, sv), (max_u + 100, sv),
                (max_u + 100, ev), (min_u - 100, ev)
            ]
            
            # Rotacionar de volta para XY
            poly_xy = []
            for u, v in poly_uv:
                x = pivot.x() + u * cos_rot - v * sin_rot
                y = pivot.y() + u * sin_rot + v * cos_rot
                poly_xy.append(QgsPointXY(x, y))
            
            rect_geom = QgsGeometry.fromPolygonXY([poly_xy])
            slice_geom = rect_geom.intersection(poly_geom)
            
            if not slice_geom.isEmpty():
                final_slices.append((slice_geom, c))
                
        return final_slices

    def update_preview(self):
        self.clear_preview()
        
        poly_layer = self.combo_poly.currentData()
        if not poly_layer: return
        
        self.setup_preview_layer(poly_layer.crs())
        
        slices = self.compute_slices()
        if not slices: return
        
        pr = self.preview_layer.dataProvider()
        feats = []
        for geom, count in slices:
            f = QgsFeature()
            f.setGeometry(geom)
            f.setAttributes([count])
            feats.append(f)
            
        pr.addFeatures(feats)
        self.preview_layer.triggerRepaint()

    def run_process(self):
        poly_layer = self.combo_poly.currentData()
        if not poly_layer:
            QMessageBox.warning(self, "Aviso", "Selecione uma camada de polígono.")
            return
            
        slices = self.compute_slices()
        if not slices:
            QMessageBox.warning(self, "Aviso", "Não foi possível calcular os recortes. Verifique as camadas e parâmetros.")
            return
            
        target_layer = self.combo_target.currentData()
        if target_layer is not None:
            # Anexar à camada existente
            feats = []
            for geom, count in slices:
                f = QgsFeature(target_layer.fields())
                f.setGeometry(geom)
                idx = target_layer.fields().indexOf('pontos')
                if idx != -1:
                    f.setAttribute(idx, count)
                feats.append(f)
                
            target_layer.startEditing()
            pr = target_layer.dataProvider()
            success, _ = pr.addFeatures(feats)
            if success:
                target_layer.commitChanges()
                target_layer.updateExtents()
                target_layer.triggerRepaint()
                self.accept()
                QMessageBox.information(self, "Sucesso", f"{len(feats)} setores anexados com sucesso à camada '{target_layer.name()}'.")
            else:
                target_layer.rollBack()
                QMessageBox.critical(self, "Erro", "Erro ao anexar feições à camada existente.")
            return
            
        # Pede para o usuário escolher onde salvar
        save_path, _ = QFileDialog.getSaveFileName(
            self,
            "Salvar Camada de Setores",
            "SETORES.shp",
            "ESRI Shapefile (*.shp);;GeoPackage (*.gpkg)"
        )
        
        if not save_path:
            return
            
        # Cria camada temporária para popular
        crs = poly_layer.crs()
        vl = QgsVectorLayer(f"Polygon?crs={crs.authid()}", "SETORES", "memory")
        pr = vl.dataProvider()
        pr.addAttributes([QgsField("pontos", QVariant.Int)])
        vl.updateFields()
        
        feats = []
        for geom, count in slices:
            f = QgsFeature()
            f.setGeometry(geom)
            f.setAttributes([count])
            feats.append(f)
            
        pr.addFeatures(feats)
        
        # Salva o arquivo no disco
        save_options = QgsVectorFileWriter.SaveVectorOptions()
        save_options.driverName = "GPKG" if save_path.endswith(".gpkg") else "ESRI Shapefile"
        save_options.fileEncoding = "UTF-8"
        save_options.actionOnExistingFile = QgsVectorFileWriter.CreateOrOverwriteFile
        
        error, error_string = QgsVectorFileWriter.writeAsVectorFormatV2(
            vl,
            save_path,
            QgsProject.instance().transformContext(),
            save_options
        )
        
        if error == QgsVectorFileWriter.NoError:
            saved_layer = QgsVectorLayer(save_path, "SETORES", "ogr")
            if saved_layer.isValid():
                # Aplicar simbologia de setores (preto 0.16, sem preenchimento)
                fill_layer = QgsSimpleFillSymbolLayer()
                fill_layer.setBrushStyle(Qt.NoBrush)
                fill_layer.setStrokeColor(QColor("black"))
                fill_layer.setStrokeWidth(0.16)
                
                symbol = QgsSymbol.defaultSymbol(saved_layer.geometryType())
                symbol.changeSymbolLayer(0, fill_layer)
                
                renderer = QgsSingleSymbolRenderer(symbol)
                saved_layer.setRenderer(renderer)
                
                QgsProject.instance().addMapLayer(saved_layer)
                
            self.accept()
            QMessageBox.information(self, "Sucesso", f"{len(feats)} polígonos salvos com sucesso em:\n{save_path}")
        else:
            QMessageBox.critical(self, "Erro", f"Erro ao salvar arquivo:\n{error_string}")
        
    def reject(self):
        self.clear_preview()
        # Restaurar camadas do canvas sem a preview
        if self.iface.mapCanvas():
            layers = [l for l in self.iface.mapCanvas().layers() if l.name() != "Prévia - Divisão"]
            self.iface.mapCanvas().setLayers(layers)
        super().reject()

class DividirPoligonoPontosTool(AqueductTool):
    def initGui(self):
        icon_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'icons', 'icone_dividir_pontos.svg')
        self.action = QAction(QIcon(icon_path), 'Dividir Polígono por Pontos', self.iface.mainWindow())
        self.action.triggered.connect(self.run)
        
        self.iface.addPluginToMenu('&Aqueduct', self.action)
        
        if self.toolbar:
            self.toolbar.addAction(self.action)
        else:
            self.iface.addToolBarIcon(self.action)
            
    def run(self):
        dlg = DividirPoligonoPontosDialog(self.iface, self.iface.mainWindow())
        dlg.exec_()
