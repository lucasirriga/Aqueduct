import os
import math
from qgis.PyQt.QtWidgets import (
    QAction, QDialog, QVBoxLayout, QFormLayout, QComboBox, QDoubleSpinBox, 
    QSpinBox, QPushButton, QMessageBox, QHBoxLayout, QGroupBox, QDialogButtonBox,
    QFileDialog
)
from qgis.PyQt.QtGui import QIcon, QColor, QFont
from qgis.PyQt.QtCore import QVariant, QTimer, Qt
from qgis.core import (
    Qgis, QgsMapLayerType, QgsProject, QgsWkbTypes, QgsVectorLayer, QgsFeature, 
    QgsGeometry, QgsPointXY, QgsField, QgsSpatialIndex, QgsPalLayerSettings,
    QgsVectorLayerSimpleLabeling, QgsTextFormat, QgsProperty, QgsLineSymbol,
    QgsVectorFileWriter, QgsSymbol, QgsSingleSymbolRenderer, QgsSimpleLineSymbolLayer
)

from .ferramenta_base import AqueductTool

class CriarLinhasEixoDialog(QDialog):
    def __init__(self, iface, parent=None):
        super().__init__(parent)
        self.iface = iface
        self.setWindowTitle("Aqueduct - Criar Laterais (v0.1.3)")
        self.resize(450, 500)
        
        self.preview_layer = None
        self.preview_timer = QTimer()
        self.preview_timer.setSingleShot(True)
        self.preview_timer.timeout.connect(self.update_preview)
        
        self.setup_ui()
        
    def setup_ui(self):
        layout = QVBoxLayout()
        
        # 1. Seleção de Camadas
        group_layers = QGroupBox("1. Seleção de Camadas")
        form_layers = QFormLayout()
        
        self.combo_line = QComboBox()
        self.combo_poly = QComboBox()
        self.combo_points = QComboBox()
        self.combo_target = QComboBox()
        
        self.populate_layers()
        
        form_layers.addRow("Linha de Referência:", self.combo_line)
        form_layers.addRow("Polígonos:", self.combo_poly)
        form_layers.addRow("Pontos (Malha):", self.combo_points)
        form_layers.addRow("Camada de Destino:", self.combo_target)
        group_layers.setLayout(form_layers)
        layout.addWidget(group_layers)
        
        # 2. Parâmetros do Usuário
        group_params = QGroupBox("2. Parâmetros de Eixos")
        form_params = QFormLayout()
        
        self.spin_spacing = QDoubleSpinBox()
        self.spin_spacing.setRange(0.1, 1000.0)
        self.spin_spacing.setValue(5.0)
        self.spin_spacing.setSuffix(" m")
        
        self.spin_limit = QSpinBox()
        self.spin_limit.setRange(1, 100)
        self.spin_limit.setValue(11)
        
        self.spin_offset = QSpinBox()
        self.spin_offset.setRange(1, 100)
        self.spin_offset.setValue(1)
        self.spin_offset.setSuffix(" x Espaçamento")
        
        form_params.addRow("Espaçamento Base:", self.spin_spacing)
        form_params.addRow("Limite de Linhas Laterais:", self.spin_limit)
        form_params.addRow("Afastamento da Bifurcação:", self.spin_offset)
        group_params.setLayout(form_params)
        layout.addWidget(group_params)
        
        # Conexões para Preview em tempo real
        self.combo_poly.currentIndexChanged.connect(self.trigger_preview)
        self.combo_line.currentIndexChanged.connect(self.trigger_preview)
        self.spin_spacing.valueChanged.connect(self.trigger_preview)
        self.spin_limit.valueChanged.connect(self.trigger_preview)
        self.spin_offset.valueChanged.connect(self.trigger_preview)
        
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
                elif geom_type == QgsWkbTypes.PointGeometry:
                    self.combo_points.addItem(layer.name(), layer)
                elif geom_type == QgsWkbTypes.LineGeometry:
                    self.combo_line.addItem(layer.name(), layer)
                    # Não adicionar a camada de prévia como destino
                    if layer.name() != "Prévia - Laterais":
                        self.combo_target.addItem(layer.name(), layer)
                        
        idx = self.combo_target.findText("LATERAIS")
        if idx >= 0:
            self.combo_target.setCurrentIndex(idx)
                    
    def trigger_preview(self):
        self.preview_timer.start(500)
        
    def clear_preview(self):
        if self.preview_layer:
            QgsProject.instance().removeMapLayer(self.preview_layer.id())
            self.preview_layer = None
        
    def setup_preview_layer(self, crs):
        self.clear_preview()
        self.preview_layer = QgsVectorLayer(f"MultiLineString?crs={crs.authid()}", "Prévia - Laterais", "memory")
        pr = self.preview_layer.dataProvider()
        pr.addAttributes([QgsField("tipo", QVariant.String)])
        self.preview_layer.updateFields()
        
        # Estilo da Linha
        symbol = QgsLineSymbol.createSimple({'color': '255,0,0,255', 'width': '0.8', 'line_style': 'dash'})
        self.preview_layer.renderer().setSymbol(symbol)
        
        self.preview_layer.setCustomProperty("skipSelectOnDefault", 1)
        
        QgsProject.instance().addMapLayer(self.preview_layer, False)
        self.iface.mapCanvas().setLayers([self.preview_layer] + self.iface.mapCanvas().layers())

    def compute_axes(self):
        """Retorna uma lista de tuplas (geom, tipo)"""
        poly_layer = self.combo_poly.currentData()
        line_layer = self.combo_line.currentData()
        
        if not poly_layer or not line_layer:
            return None
            
        spacing = self.spin_spacing.value()
        limit = self.spin_limit.value()
        offset_multiplier = self.spin_offset.value()
        offset = offset_multiplier * spacing
        
        # Geometria da linha de referência
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
        angle = math.atan2(dy, dx)
        cos_a = math.cos(-angle)
        sin_a = math.sin(-angle)
        pivot = p1
        
        poly_features = poly_layer.selectedFeatures() if poly_layer.selectedFeatureCount() > 0 else list(poly_layer.getFeatures())
        
        final_lines = []
        
        for p_feat in poly_features:
            poly_geom = p_feat.geometry()
            if not poly_geom or poly_geom.isEmpty():
                continue
                
            centroid = poly_geom.centroid().asPoint()
            
            # Converter coordenadas do polígono e centroide para UV
            poly_u = []
            poly_v = []
            for v in poly_geom.vertices():
                uu = (v.x() - pivot.x()) * cos_a - (v.y() - pivot.y()) * sin_a
                vv = (v.x() - pivot.x()) * sin_a + (v.y() - pivot.y()) * cos_a
                poly_u.append(uu)
                poly_v.append(vv)
                
            if not poly_u: continue
            min_u, max_u = min(poly_u), max(poly_u)
            min_v, max_v = min(poly_v), max(poly_v)
            
            cent_u = (centroid.x() - pivot.x()) * cos_a - (centroid.y() - pivot.y()) * sin_a
            cent_v = (centroid.x() - pivot.x()) * sin_a + (centroid.y() - pivot.y()) * cos_a
            
            # Ajuste do centroide
            v_snap = round(cent_v / spacing) * spacing
            v_adj = v_snap + (spacing / 2.0)
            
            # Análise de capacidade
            qty_A = max(0, math.floor((max_v - v_adj) / spacing))
            qty_B = max(0, math.floor((v_adj - min_v) / spacing))
            
            # Rotacionar de volta função auxiliar
            def rotate_back(u, v):
                x = pivot.x() + u * math.cos(angle) - v * math.sin(angle)
                y = pivot.y() + u * math.sin(angle) + v * math.cos(angle)
                return QgsPointXY(x, y)
            
            lines_uv = []
            if qty_A < limit and qty_B < limit:
                # Condição 1: Eixo Único
                lines_uv.append([
                    (min_u - 100, v_adj),
                    (max_u + 100, v_adj)
                ])
                tipo = "Eixo Único"
            else:
                # Condição 2: Bifurcação
                lines_uv.append([
                    (min_u - 100, v_adj - offset/2.0),
                    (max_u + 100, v_adj - offset/2.0)
                ])
                lines_uv.append([
                    (min_u - 100, v_adj + offset/2.0),
                    (max_u + 100, v_adj + offset/2.0)
                ])
                # Transversal (Interligação)
                lines_uv.append([
                    (cent_u, v_adj - offset/2.0),
                    (cent_u, v_adj + offset/2.0)
                ])
                tipo = "Eixo Bifurcado"
                
            # Intersectar com o polígono original
            for l_uv in lines_uv:
                p1_xy = rotate_back(l_uv[0][0], l_uv[0][1])
                p2_xy = rotate_back(l_uv[1][0], l_uv[1][1])
                line_geom = QgsGeometry.fromPolylineXY([p1_xy, p2_xy])
                
                intersected = line_geom.intersection(poly_geom)
                if not intersected.isEmpty():
                    # Se for multipart (ex: polígono tem buracos), iterar
                    if intersected.isMultipart():
                        for part in intersected.asGeometryCollection():
                            final_lines.append((part, tipo))
                    else:
                        final_lines.append((intersected, tipo))
                        
        return final_lines

    def update_preview(self):
        self.clear_preview()
        
        poly_layer = self.combo_poly.currentData()
        if not poly_layer: return
        
        self.setup_preview_layer(poly_layer.crs())
        
        axes = self.compute_axes()
        if not axes: return
        
        pr = self.preview_layer.dataProvider()
        feats = []
        for geom, tipo in axes:
            f = QgsFeature()
            f.setGeometry(geom)
            f.setAttributes([tipo])
            feats.append(f)
            
        pr.addFeatures(feats)
        self.preview_layer.triggerRepaint()

    def run_process(self):
        poly_layer = self.combo_poly.currentData()
        if not poly_layer:
            QMessageBox.warning(self, "Aviso", "Selecione uma camada de polígonos.")
            return
            
        axes = self.compute_axes()
        if not axes:
            QMessageBox.warning(self, "Aviso", "Não foi possível calcular as laterais.")
            return
            
        target_layer = self.combo_target.currentData()
        
        if target_layer is not None:
            # Anexar à camada existente
            feats = []
            for geom, tipo in axes:
                f = QgsFeature(target_layer.fields())
                f.setGeometry(geom)
                idx = target_layer.fields().indexOf('tipo')
                if idx != -1:
                    f.setAttribute(idx, tipo)
                feats.append(f)
                
            target_layer.startEditing()
            pr = target_layer.dataProvider()
            success, _ = pr.addFeatures(feats)
            if success:
                target_layer.commitChanges()
                target_layer.updateExtents()
                target_layer.triggerRepaint()
                self.accept()
                QMessageBox.information(self, "Sucesso", f"{len(feats)} laterais anexadas com sucesso à camada '{target_layer.name()}'.")
            else:
                target_layer.rollBack()
                QMessageBox.critical(self, "Erro", "Erro ao anexar feições à camada existente.")
            return

        # Criar novo arquivo
        save_path, _ = QFileDialog.getSaveFileName(
            self,
            "Salvar Camada de Laterais",
            "LATERAIS.shp",
            "ESRI Shapefile (*.shp);;GeoPackage (*.gpkg)"
        )
        
        if not save_path:
            return
            
        crs = poly_layer.crs()
        vl = QgsVectorLayer(f"MultiLineString?crs={crs.authid()}", "LATERAIS", "memory")
        pr = vl.dataProvider()
        pr.addAttributes([QgsField("tipo", QVariant.String)])
        vl.updateFields()
        
        feats = []
        for geom, tipo in axes:
            f = QgsFeature()
            f.setGeometry(geom)
            f.setAttributes([tipo])
            feats.append(f)
            
        pr.addFeatures(feats)
        
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
            saved_layer = QgsVectorLayer(save_path, "LATERAIS", "ogr")
            if saved_layer.isValid():
                # Aplicar simbologia padrão para eixos/laterais
                line_layer = QgsSimpleLineSymbolLayer()
                line_layer.setColor(QColor("red"))
                line_layer.setWidth(0.8)
                line_layer.setCustomDashVector([4.0, 2.0])
                line_layer.setUseCustomDashPattern(True)
                
                symbol = QgsSymbol.defaultSymbol(saved_layer.geometryType())
                symbol.changeSymbolLayer(0, line_layer)
                
                renderer = QgsSingleSymbolRenderer(symbol)
                saved_layer.setRenderer(renderer)
                
                QgsProject.instance().addMapLayer(saved_layer)
                
            self.accept()
            QMessageBox.information(self, "Sucesso", f"{len(feats)} laterais salvas com sucesso em:\n{save_path}")
        else:
            QMessageBox.critical(self, "Erro", f"Erro ao salvar arquivo:\n{error_string}")
        
    def reject(self):
        self.clear_preview()
        if self.iface.mapCanvas():
            layers = [l for l in self.iface.mapCanvas().layers() if l.name() != "Prévia - Laterais"]
            self.iface.mapCanvas().setLayers(layers)
        super().reject()

class CriarLinhasEixoTool(AqueductTool):
    def initGui(self):
        icon_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'icons', 'icone_eixos.svg')
        self.action = QAction(QIcon(icon_path), 'Criar Laterais', self.iface.mainWindow())
        self.action.triggered.connect(self.run)
        
        self.iface.addPluginToMenu('&Aqueduct', self.action)
        
        if self.toolbar:
            self.toolbar.addAction(self.action)
        else:
            self.iface.addToolBarIcon(self.action)
            
    def run(self):
        dlg = CriarLinhasEixoDialog(self.iface, self.iface.mainWindow())
        dlg.exec_()
