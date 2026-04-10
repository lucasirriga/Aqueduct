from qgis.PyQt.QtWidgets import QAction, QInputDialog, QFileDialog
from qgis.PyQt.QtGui import QIcon
from qgis.core import QgsMapLayerType, QgsProject, QgsLayoutExporter, QgsWkbTypes
import os
import datetime

from .ferramenta_base import AqueductTool
from .gerar_layout_mapa import MapLayoutGenerator, TAMANHOS_PAGINA


class GerarPdfTool(AqueductTool):
    """
    Ferramenta para gerar um PDF simples do mapa, utilizando o MapLayoutGenerator padronizado.
    Permite escolher o tamanho da página (A4 a A0) mantendo as proporções do layout.
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
        valid_layers = [
            l for l in project.mapLayers().values()
            if l.type() == QgsMapLayerType.VectorLayer
            and l.geometryType() == QgsWkbTypes.PolygonGeometry
        ]

        if not valid_layers:
            self.iface.messageBar().pushMessage(
                "Aqueduct", "Nenhuma camada de polígono encontrada para definir a área.",
                level=3, duration=5)
            return

        layer_names = [l.name() for l in valid_layers]
        item_layer, ok = QInputDialog.getItem(
            self.iface.mainWindow(),
            "Aqueduct - Área do Mapa",
            "Selecione a camada de SETORES (define o zoom):",
            layer_names, 0, False
        )
        if not ok or not item_layer:
            return

        area_layer = next((l for l in valid_layers if l.name() == item_layer), None)

        # 2. Escolha do Tamanho da Página
        tamanhos = list(TAMANHOS_PAGINA.keys())
        item_size, ok = QInputDialog.getItem(
            self.iface.mainWindow(),
            "Aqueduct - Tamanho da Página",
            "Selecione o tamanho de página do PDF:\n"
            "(O layout e as proporções são mantidas automaticamente)",
            tamanhos, 0, False
        )
        if not ok or not item_size:
            return

        # 3. Caminho do Arquivo PDF
        timestamp = datetime.datetime.now().strftime("%Y-%m-%d_%H-%M")
        base_name = project.baseName() or "mapa_aqueduct"
        # Inclui o tamanho no nome do arquivo para identificação fácil
        size_short = item_size.split()[0]  # ex.: 'A4', 'A0'
        default_name = f"{base_name}_{size_short}_{timestamp}.pdf"

        pdf_path, _ = QFileDialog.getSaveFileName(
            self.iface.mainWindow(),
            "Salvar Mapa PDF",
            os.path.join(os.path.expanduser("~"), default_name),
            "Arquivos PDF (*.pdf)"
        )

        if not pdf_path:
            return
        if not pdf_path.endswith('.pdf'):
            pdf_path += '.pdf'

        # 4. Geração do Layout via Generator
        generator = MapLayoutGenerator(project)
        layout = generator.create_layout(area_layer, standalone=True, page_size_key=item_size)

        # 5. Exportação
        exporter = QgsLayoutExporter(layout)

        settings = QgsLayoutExporter.PdfExportSettings()
        settings.dpi = 300
        settings.writeGeoPdf = True

        result = exporter.exportToPdf(pdf_path, settings)

        if result == QgsLayoutExporter.Success:
            self.iface.messageBar().pushMessage(
                "Aqueduct", f"PDF {size_short} salvo em: {pdf_path}", level=0, duration=5)
            if os.name == 'nt':
                os.startfile(pdf_path)
        else:
            self.iface.messageBar().pushMessage(
                "Aqueduct", "Erro ao exportar PDF.", level=2, duration=5)
