from qgis.PyQt.QtWidgets import QAction, QInputDialog, QFileDialog
from qgis.PyQt.QtGui import QIcon
from qgis.core import QgsProject, QgsLayoutExporter, QgsWkbTypes
import os
import datetime

from .ferramenta_base import AqueductTool
from .gerar_layout_mapa import MapLayoutGenerator

class GerarPdfTool(AqueductTool):
    """
    Ferramenta para gerar um PDF simples do mapa, utilizando o MapLayoutGenerator padronizado.
    """

    def initGui(self):
        icon_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'icons', 'icone_pdf.svg')
        
        self.action = QAction(QIcon(icon_path), 'Gerar Mapa PDF', self.iface.mainWindow())
        self.action.triggered.connect(self.run)
        
        self.iface.addPluginToMenu('&Aqueduct', self.action)
        
        if self.toolbar:
            self.toolbar.addAction(self.action)
        else:
            self.iface.addToolBarIcon(self.action)

    def run(self):
        project = QgsProject.instance()
        
        # 1. Seleção da Camada de Setores (Área Total)
        valid_layers = []
        for lid, layer in project.mapLayers().items():
            if layer.type() == layer.VectorLayer and layer.geometryType() == QgsWkbTypes.PolygonGeometry:
                valid_layers.append(layer)
        
        if not valid_layers:
            self.iface.messageBar().pushMessage("Aqueduct", "Nenhuma camada de polígono encontrada para definir a área.", level=3)
            return

        layer_names = [l.name() for l in valid_layers]
        item, ok = QInputDialog.getItem(
            self.iface.mainWindow(), 
            "Aqueduct - Área do Mapa", 
            "Selecione a camada de SETORES (define o zoom):", 
            layer_names, 
            0, 
            False
        )
        
        if not ok or not item:
            return
            
        area_layer = None
        for layer in valid_layers:
            if layer.name() == item:
                area_layer = layer
                break
        
        # 2. Caminho do Arquivo PDF
        timestamp = datetime.datetime.now().strftime("%Y-%m-%d_%H-%M")
        base_name = project.baseName() or "mapa_aqueduct"
        default_name = f"{base_name}_{timestamp}.pdf"
        
        pdf_path, _ = QFileDialog.getSaveFileName(
            self.iface.mainWindow(),
            "Salvar Mapa PDF",
            os.path.join(os.path.expanduser("~"), default_name),
            "Arquivos PDF (*.pdf)"
        )
        
        if not pdf_path: return
        if not pdf_path.endswith('.pdf'): pdf_path += '.pdf'

        # 3. Geração do Layout via Generator
        generator = MapLayoutGenerator(project)
        layout = generator.create_layout(area_layer)
        
        # 4. Exportação
        exporter = QgsLayoutExporter(layout)
        
        settings = QgsLayoutExporter.PdfExportSettings()
        settings.dpi = 300
        settings.writeGeoPdf = True
        
        result = exporter.exportToPdf(pdf_path, settings)
        
        if result == QgsLayoutExporter.Success:
            self.iface.messageBar().pushMessage("Aqueduct", f"PDF salvo em: {pdf_path}", level=0, duration=5)
            if os.name == 'nt':
                os.startfile(pdf_path)
        else:
            self.iface.messageBar().pushMessage("Aqueduct", "Erro ao exportar PDF.", level=2)
