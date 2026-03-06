import os
import requests
import math
from qgis.PyQt.QtCore import Qt
from qgis.PyQt.QtWidgets import QAction, QDialog, QVBoxLayout, QFormLayout, QComboBox, QLineEdit, QPushButton, QMessageBox, QFileDialog, QProgressDialog, QCheckBox, QSpinBox
from qgis.PyQt.QtGui import QIcon
from qgis.core import QgsProject, QgsWkbTypes, QgsRasterLayer, QgsSettings, QgsVectorLayer

from .ferramenta_base import AqueductTool

class ColetarTopografiaDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Aqueduct - Coletar Topografia (Copernicus)")
        self.resize(400, 300)
        self.setup_ui()
        
    def setup_ui(self):
        layout = QVBoxLayout()
        form = QFormLayout()
        
        self.combo_layer = QComboBox()
        self.populate_layers()
        self.edit_api_key = QLineEdit()
        self.edit_api_key.setPlaceholderText("Insira sua API Key OpenTopography")
        self.load_api_key()
        
        self.edit_output = QLineEdit()
        self.btn_output = QPushButton("...")
        self.btn_output.clicked.connect(self.select_output)
        
        # Opções de Polígonos
        self.chk_polygons = QCheckBox("Gerar Polígonos de Nível")
        self.chk_polygons.setChecked(True)
        self.spin_interval = QSpinBox()
        self.spin_interval.setRange(1, 1000)
        self.spin_interval.setValue(5)
        self.spin_interval.setSuffix(" m")
        
        form.addRow("Camada de Área (Polígono):", self.combo_layer)
        form.addRow("API Key (OpenTopography):", self.edit_api_key)
        form.addRow("Salvar Raster em:", self.edit_output)
        form.addRow("", self.btn_output)
        form.addRow(self.chk_polygons)
        form.addRow("Intervalo de Elevação:", self.spin_interval)
        
        layout.addLayout(form)
        
        self.btn_run = QPushButton("Baixar e Processar")
        self.btn_run.clicked.connect(self.accept)
        layout.addWidget(self.btn_run)
        
        self.setLayout(layout)
        
    def populate_layers(self):
        self.combo_layer.clear()
        for layer in QgsProject.instance().mapLayers().values():
            if layer.type() == layer.VectorLayer and layer.geometryType() == QgsWkbTypes.PolygonGeometry:
                self.combo_layer.addItem(layer.name(), layer)
                
    def load_api_key(self):
        params = QgsSettings()
        key = params.value("Aqueduct/OpenTopographyKey", "51fb394db78d1c031a87162f07875002")
        self.edit_api_key.setText(key)

    def save_api_key(self):
        key = self.edit_api_key.text()
        if key:
            params = QgsSettings()
            params.setValue("Aqueduct/OpenTopographyKey", key)

    def select_output(self):
        path, _ = QFileDialog.getSaveFileName(self, "Salvar DEM", "", "GeoTIFF (*.tif)")
        if path:
            self.edit_output.setText(path)

    def get_parameters(self):
        self.save_api_key()
        return {
            'layer': self.combo_layer.currentData(),
            'api_key': self.edit_api_key.text(),
            'output_path': self.edit_output.text(),
            'generate_polygons': self.chk_polygons.isChecked(),
            'interval': self.spin_interval.value()
        }

class ColetarTopografiaTool(AqueductTool):
    def initGui(self):
        icon_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'icons', 'icone_topo.svg')
        self.action = QAction(QIcon(icon_path), 'Coletar Topografia (Copernicus)', self.iface.mainWindow())
        self.action.triggered.connect(self.run)
        
        self.iface.addPluginToMenu('&Aqueduct', self.action)
        if self.toolbar:
            self.toolbar.addAction(self.action)
        else:
            self.iface.addToolBarIcon(self.action)
            
    def run(self):
        dlg = ColetarTopografiaDialog(self.iface.mainWindow())
        if dlg.exec_():
            params = dlg.get_parameters()
            self.download_dem(params)
            
    def download_dem(self, params):
        layer = params['layer']
        api_key = params['api_key']
        output_path = params['output_path']
        generate_polygons = params.get('generate_polygons', False)
        interval = params.get('interval', 5)
        
        if not layer or not api_key or not output_path:
            self.iface.messageBar().pushMessage("Aqueduct", "Preencha todos os campos.", level=2, duration=5)
            return

        # Obter extensão (Bbox) - WGS84 (EPSG:4326) é necessario para OpenTopography
        extent = layer.extent()
        crs = layer.crs()
        
        # Transformar para WGS84 se necessario
        from qgis.core import QgsCoordinateReferenceSystem, QgsCoordinateTransform
        dest_crs = QgsCoordinateReferenceSystem("EPSG:4326")
        tr = QgsCoordinateTransform(crs, dest_crs, QgsProject.instance())
        
        wgs_extent = tr.transformBoundingBox(extent)
        
        west = wgs_extent.xMinimum()
        south = wgs_extent.yMinimum()
        east = wgs_extent.xMaximum()
        north = wgs_extent.yMaximum()
        
        # URL Copernicus GLO-30 via OpenTopography
        url = "https://portal.opentopography.org/API/globaldem"
        payload = {
            'demtype': 'COP30',
            'south': south,
            'north': north,
            'west': west,
            'east': east,
            'outputFormat': 'GTiff',
            'API_Key': api_key
        }
        
        # Configurar Barra de Progresso
        progress = QProgressDialog("Iniciando download...", "Cancelar", 0, 100, self.iface.mainWindow())
        progress.setWindowTitle("Aqueduct - Topografia")
        progress.setWindowModality(Qt.WindowModal)
        progress.setMinimumDuration(0)
        progress.setValue(0)
        
        try:
            response = requests.get(url, params=payload, stream=True)
            
            if response.status_code == 200:
                total_size = int(response.headers.get('content-length', 0))
                progress.setLabelText("Baixando DEM Copernicus...")
                progress.setMaximum(total_size if total_size > 0 else 0)
                
                # Caminho temporário para o arquivo baixado (raw)
                raw_path = output_path.replace('.tif', '_raw.tif')
                
                downloaded_size = 0
                chunk_size = 8192
                
                with open(raw_path, 'wb') as f:
                    for chunk in response.iter_content(chunk_size=chunk_size):
                        if progress.wasCanceled():
                            f.close()
                            os.remove(raw_path)
                            self.iface.messageBar().pushMessage("Aqueduct", "Download cancelado.", level=1, duration=5)
                            return
                            
                        f.write(chunk)
                        downloaded_size += len(chunk)
                        if total_size > 0:
                            progress.setValue(downloaded_size)
                        else:
                            # Indeterminado se não tiver content-length
                            progress.setValue(0) 
                            
                progress.setLabelText("Refinando DEM (5m)...")
                progress.setRange(0, 0) # Indeterminado (Busy)
                
                # Reamostragem (Refinamento) para 5m usando Cubic Spline
                import processing
                
                # 1. Warp (Refinamento)
                params_warp = {
                    'INPUT': raw_path,
                    'SOURCE_CRS': 'EPSG:4326',
                    'TARGET_CRS': crs.authid(), 
                    'RESAMPLING': 2, # Cubic
                    'TARGET_RESOLUTION': 5, 
                    'NODATA': None,
                    'DATA_TYPE': 0, 
                    'OUTPUT': output_path
                }
                
                try:
                    result = processing.run("gdal:warpreproject", params_warp)
                    final_path = result['OUTPUT']
                    
                    if os.path.exists(final_path):
                        try:
                            os.remove(raw_path)
                        except:
                            pass
                            
                    # Carregar Raster
                    rlayer = QgsRasterLayer(final_path, f"DEM Refinado ({interval}m)")
                    if rlayer.isValid():
                        QgsProject.instance().addMapLayer(rlayer)
                        self.iface.messageBar().pushMessage("Aqueduct", "DEM refinado e carregado com sucesso!", level=0, duration=5)
                    else:
                         self.iface.messageBar().pushMessage("Aqueduct", "Falha ao carregar camada refinada.", level=1, duration=5)

                    # 2. Geração de Polígonos (Se Ativo)
                    if generate_polygons and rlayer.isValid():
                         progress.setLabelText("Gerando Polígonos de Nível...")
                         
                         import processing 
                         from qgis.core import QgsRasterBandStats
                         
                         # Calcular Estatísticas
                         prov = rlayer.dataProvider()
                         stats = prov.bandStatistics(1, QgsRasterBandStats.All, extent, 0)
                         z_min = stats.minimumValue
                         z_max = stats.maximumValue
                         
                         # Criar Tabela de Reclassificação
                         # Min <= value < Max. 
                         # Faixas: base, base+interval.
                         # Vamos arredondar o min para baixo múltiplo do intervalo.
                         start = math.floor(z_min / interval) * interval
                         end = math.ceil(z_max / interval) * interval
                         
                         reclass_table = []
                         # Formato: min, max, value
                         current = start
                         while current < end:
                             next_val = current + interval
                             # Usamos 'current' como o valor da classe (Min da faixa)
                             reclass_table.extend([current, next_val, current]) 
                             current = next_val

                         # Reclassificação
                         reclass_path = output_path.replace('.tif', '_reclass.tif')
                         params_reclass = {
                             'INPUT_RASTER': final_path,
                             'RASTER_BAND': 1,
                             'TABLE': reclass_table,
                             'NO_DATA': -9999,
                             'RANGE_BOUNDARIES': 1, # 1: min <= value < max (Padrão GDAL costuma ser lower inclusive)
                             'NODATA_FOR_MISSING': True,
                             'DATA_TYPE': 5, # Float32
                             'OUTPUT': reclass_path
                         }
                         
                         # qgis:reclassifybytable
                         # Nota: native:reclassifybytable requer QGIS >= 3.x
                         try:
                             # Verifica se existe native
                             reclass_res = processing.run("native:reclassifybytable", params_reclass)
                             path_reclass = reclass_res['OUTPUT']
                             
                             # Polygonize
                             poly_path_temp = output_path.replace('.tif', '_poly_temp.gpkg')
                             params_poly = {
                                 'INPUT': path_reclass,
                                 'BAND': 1,
                                 'FIELD': 'ELEV_MIN',
                                 'EIGHT_CONNECTEDNESS': False,
                                 'OUTPUT': poly_path_temp
                             }
                             poly_res = processing.run("gdal:polygonize", params_poly)
                             path_poly_temp = poly_res['OUTPUT']
                             
                             # Dissolve (Unificar Feições) - Processamento em GPKG para performance
                             poly_path_dissolved_gpkg = output_path.replace('.tif', '_classes_temp.gpkg')
                             params_dissolve = {
                                 'INPUT': path_poly_temp,
                                 'FIELD': ['ELEV_MIN'],
                                 'OUTPUT': poly_path_dissolved_gpkg
                             }
                             dissolve_res = processing.run("native:dissolve", params_dissolve)
                             path_dissolved_gpkg = dissolve_res['OUTPUT']
                             
                             # Converter para Shapefile Final (Apenas o resultado unificado)
                             poly_path_final_shp = output_path.replace('.tif', '_classes.shp')
                             params_save = {
                                 'INPUT': path_dissolved_gpkg,
                                 'OUTPUT': poly_path_final_shp
                             }
                             # Usando ogr2ogr via gdal:convertformat ou native:savefeatures
                             # native:savefeatures é mais simples mas pede layer input carregado as vezes ou string path
                             # gdal:convertformat é robusto para conversão de arquivo
                             processing.run("gdal:convertformat", params_save)
                             
                             path_final_shp = poly_path_final_shp
                             
                             # Limpeza dos temporários (GPKGs)
                             for p in [reclass_path, poly_path_temp, path_dissolved_gpkg]:
                                 if os.path.exists(p):
                                     try:
                                         # Tenta remover. GPKGs podem ter locks se algo segurar, mas no fluxo linear deve ir ok.
                                         os.remove(p)
                                     except: pass
                             
                             # Limpeza
                             for p in [reclass_path, poly_path_temp]:
                                 if os.path.exists(p):
                                     try:
                                         # Raster e SHP tem sidecars, melhor nao deletar agressivamente agora ou usar QgsVectorLayer delete?
                                         # Vamos deixar arquivos temp por segurança ou deletar extensões principais.
                                         pass 
                                     except: pass

                             # Carregar Shape
                             vlayer = QgsVectorLayer(path_final_shp, f"Faixas de Elevação ({interval}m)", "ogr")
                             if vlayer.isValid():
                                 QgsProject.instance().addMapLayer(vlayer)
                                 self.iface.messageBar().pushMessage("Aqueduct", "Polígonos gerados com sucesso!", level=0, duration=5)
                             else:
                                 self.iface.messageBar().pushMessage("Aqueduct", "Falha ao carregar camada de polígonos.", level=1, duration=5)
                             
                         except Exception as e_poly:
                             self.iface.messageBar().pushMessage("Aqueduct", f"Erro ao gerar polígonos: {e_poly}", level=1, duration=5)
                             import traceback
                             traceback.print_exc()

                except Exception as e_warp:
                     self.iface.messageBar().pushMessage("Aqueduct", f"Erro no processamento: {e_warp}", level=1, duration=5)
                     # Fallback
                     rlayer = QgsRasterLayer(raw_path, "Copernicus DEM (Raw)")
                     QgsProject.instance().addMapLayer(rlayer)

            else:
                self.iface.messageBar().pushMessage("Aqueduct", f"Erro API: {response.text}", level=2, duration=5)
                
        except Exception as e:
            self.iface.messageBar().pushMessage("Aqueduct", f"Erro Geral: {str(e)}", level=2, duration=5)
        finally:
            progress.close()
