from qgis.PyQt.QtWidgets import QAction, QInputDialog, QFileDialog
from qgis.PyQt.QtGui import QIcon
from qgis.core import (
    QgsProject, QgsPrintLayout, QgsLayoutItemMap, QgsLayoutItemLegend,
    QgsLayoutItemScaleBar, QgsLayoutItemMapGrid, QgsLayoutPoint, QgsLayoutSize, QgsUnitTypes,
    QgsLayoutItemLabel, QgsReadWriteContext, QgsLayoutExporter, QgsWkbTypes
)
import os

from .ferramenta_base import AqueductTool

class GerarPdfTool(AqueductTool):
    """
    Ferramenta para gerar um PDF simples do mapa.
    - Extensão baseada na camada de Setores (Polígonos).
    - Inclui Legenda (priorizando Tubulações).
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
        
        if not area_layer:
            return

        # 2. Caminho do Arquivo PDF
        pdf_path, _ = QFileDialog.getSaveFileName(
            self.iface.mainWindow(),
            "Salvar Mapa PDF",
            os.path.join(os.path.expanduser("~"), "mapa_aqueduct.pdf"),
            "Arquivos PDF (*.pdf)"
        )
        
        if not pdf_path:
            return
            
        if not pdf_path.endswith('.pdf'):
            pdf_path += '.pdf'

        # 3. Criação do Layout
        layout = QgsPrintLayout(project)
        layout.initializeDefaults()
        layout.setName("Aqueduct Layout")
        
        # A4 Landscape (297mm width x 210mm height)
        pc = layout.pageCollection()
        page = pc.page(0)
        page.setPageSize(QgsLayoutSize(297, 210, QgsUnitTypes.LayoutMillimeters))
        
        # Margem de 10mm
        margin = 10
        page_width = 297
        page_height = 210
        
        # Mapa
        map_item = QgsLayoutItemMap(layout)
        map_item.setRect(20, 20, 20, 20) # Dummy rect
        
        # Tenta definir a extensão para a camada de área com Padding (30%)
        extent = area_layer.extent()
        buffer_dist = extent.width() * 0.3
        buffered_extent = extent.buffered(buffer_dist)
        
        map_item.setExtent(buffered_extent)
        
        # --- Configuração da Grade (Grid) ---
        grid = QgsLayoutItemMapGrid("Grade Principal", map_item)
        map_item.grids().addGrid(grid)
        
        # Remove linhas internas (apenas moldura e anotações)
        grid.setStyle(QgsLayoutItemMapGrid.FrameAnnotationsOnly) 
        
        grid.setFrameStyle(QgsLayoutItemMapGrid.ExteriorTicks) # "Sticks" para fora
        grid.setFrameWidth(1.0)
        
        # Intervalo da Grade (Dinâmico: Largura / 4)
        target_interval = buffered_extent.width() / 4.0
        grid.setIntervalX(target_interval)
        grid.setIntervalY(target_interval)
        
        # Habilita Desenho de Coordenadas
        grid.setAnnotationEnabled(True)
        
        # Posição: OutsideFrame para todos
        grid.setAnnotationPosition(QgsLayoutItemMapGrid.OutsideMapFrame, QgsLayoutItemMapGrid.Left)
        grid.setAnnotationPosition(QgsLayoutItemMapGrid.OutsideMapFrame, QgsLayoutItemMapGrid.Right)
        grid.setAnnotationPosition(QgsLayoutItemMapGrid.OutsideMapFrame, QgsLayoutItemMapGrid.Top)
        grid.setAnnotationPosition(QgsLayoutItemMapGrid.OutsideMapFrame, QgsLayoutItemMapGrid.Bottom)
        
        # Rotação (Direções)
        # Esquerda: 90 graus Anti-Horário (Vertical Ascendente)
        grid.setAnnotationDirection(QgsLayoutItemMapGrid.Vertical, QgsLayoutItemMapGrid.Left)
        # Direita: 90 graus Horário (Vertical Descendente)
        grid.setAnnotationDirection(QgsLayoutItemMapGrid.VerticalDescending, QgsLayoutItemMapGrid.Right)
        # Topo e Base: Horizontal (Padrão)
        grid.setAnnotationDirection(QgsLayoutItemMapGrid.Horizontal, QgsLayoutItemMapGrid.Top)
        grid.setAnnotationDirection(QgsLayoutItemMapGrid.Horizontal, QgsLayoutItemMapGrid.Bottom)
        
        # Formato das Coordenadas
        grid.setAnnotationFormat(QgsLayoutItemMapGrid.Decimal)
        # -------------------------------------
        
        # Ajusta tamanho do mapa (ocupa quase tudo, deixa espaço pra legenda na direita)
        # Largura mapa = 220mm, Altura = 190mm
        map_item.attemptMove(QgsLayoutPoint(margin, margin, QgsUnitTypes.LayoutMillimeters))
        map_item.attemptResize(QgsLayoutSize(220, 190, QgsUnitTypes.LayoutMillimeters))
        layout.addLayoutItem(map_item)
        
        # Legenda
        legend = QgsLayoutItemLegend(layout)
        legend.setTitle("Legenda")
        legend.setLinkedMap(map_item)
        # Filtra para mostrar apenas itens visíveis no mapa dentro da extensão
        legend.setLegendFilterByMapEnabled(True)
        
        legend.attemptMove(QgsLayoutPoint(235, margin, QgsUnitTypes.LayoutMillimeters))
        layout.addLayoutItem(legend)
        
        # Barra de Escala
        scalebar = QgsLayoutItemScaleBar(layout)
        scalebar.setStyle('Single Box')
        scalebar.setLinkedMap(map_item)
        scalebar.applyDefaultSize()
        scalebar.attemptMove(QgsLayoutPoint(margin + 5, 185, QgsUnitTypes.LayoutMillimeters))
        layout.addLayoutItem(scalebar)
        
        # Título
        title = QgsLayoutItemLabel(layout)
        title.setText("Projeto Aqueduct")
        # title.setFont(...) removido para evitar DeprecationWarning e usar padrão.
        title.attemptMove(QgsLayoutPoint(margin, margin - 8, QgsUnitTypes.LayoutMillimeters)) # Acima do mapa? 
        # Vamos por simples.
        
        # Exportação
        exporter = QgsLayoutExporter(layout)
        
        settings = QgsLayoutExporter.PdfExportSettings()
        settings.dpi = 300
        
        # Habilita Georeferenciamento (GeoPDF)
        settings.writeGeoPdf = True
        
        result = exporter.exportToPdf(pdf_path, settings)
        
        if result == QgsLayoutExporter.Success:
            self.iface.messageBar().pushMessage("Aqueduct", f"PDF salvo em: {pdf_path}", level=0, duration=5)
            import subprocess
            # Tenta abrir o PDF
            if os.name == 'nt':
                os.startfile(pdf_path)
        else:
            self.iface.messageBar().pushMessage("Aqueduct", "Erro ao exportar PDF.", level=2)
