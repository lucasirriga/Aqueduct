from qgis.PyQt.QtWidgets import QAction, QInputDialog, QFileDialog
from qgis.PyQt.QtGui import QIcon
from qgis.core import (
    QgsProject, QgsPrintLayout, QgsLayoutItemMap, QgsLayoutItemLegend,
    QgsLayoutItemScaleBar, QgsLayoutItemMapGrid, QgsLayoutPoint, QgsLayoutSize, QgsUnitTypes,
    QgsLayoutItemLabel, QgsReadWriteContext, QgsLayoutExporter, QgsWkbTypes,
    QgsLayoutItemShape, QgsFillSymbol, QgsLegendStyle, QgsLayoutItemPicture
)
from qgis.PyQt.QtGui import QIcon, QFont
import os
import json

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
        import datetime
        timestamp = datetime.datetime.now().strftime("%Y-%m-%d_%H-%M")
        base_name = project.baseName() or "mapa_aqueduct"
        default_name = f"{base_name}_{timestamp}.pdf"
        
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
        
        # --- Borda da Página (0.3mm com 2mm de padding) ---
        border_padding = 2
        border = QgsLayoutItemShape(layout)
        border.setShapeType(QgsLayoutItemShape.Rectangle)
        border.attemptMove(QgsLayoutPoint(border_padding, border_padding, QgsUnitTypes.LayoutMillimeters))
        border.attemptResize(QgsLayoutSize(page_width - 2*border_padding, page_height - 2*border_padding, QgsUnitTypes.LayoutMillimeters))
        
        # Estilo: Sem preenchimento, Borda Preta 0.3mm
        symbol = QgsFillSymbol.createSimple({
            'color': 'transparent', 
            'outline_color': 'black', 
            'outline_width': '0.3'
        })
        border.setSymbol(symbol)
        border.setLocked(True) # Travar para não atrapalhar
        layout.addLayoutItem(border)
        # -----------------------------
        
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
        
        # Reduzir fonte das labels da grade (30% menor)
        # Padrao costuma ser ~10. Vamos para 7.
        font_grid = QFont("Arial", 7)
        grid.setAnnotationFont(font_grid)
        # -------------------------------------
        
        # Ajusta tamanho do mapa (ocupa quase tudo, deixa espaço pra legenda na direita)
        # Largura mapa = 220mm, Altura = 190mm
        map_item.attemptMove(QgsLayoutPoint(margin, margin, QgsUnitTypes.LayoutMillimeters))
        map_item.attemptResize(QgsLayoutSize(220, 190, QgsUnitTypes.LayoutMillimeters))
        layout.addLayoutItem(map_item)
        
        # --- Logotipo ---
        logo_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'img', 'logo tocantins agropecuária ltda.png')
        
        # Centralizar na coluna lateral
        # Mapa vai até 10 (margin) + 220 (width) = 230
        # Página vai até 297. Margem direita 10 -> Área útil até 287.
        # Espaço lateral = 287 - 230 = 57mm.
        sidebar_start_x = 230
        sidebar_width = 57
        logo_width = 50
        
        # X centralizado com padding de 5mm a esquerda (desloca para direita)
        logo_x = sidebar_start_x + (sidebar_width - logo_width) / 2 + 5
        logo_y = margin
        
        if os.path.exists(logo_path):
            logo = QgsLayoutItemPicture(layout)
            logo.setPicturePath(logo_path)
            logo.setResizeMode(QgsLayoutItemPicture.Zoom)
            
            # Ajustando altura reservada para 25mm (para reduzir espaço em branco se o logo for wide)
            logo_height = 25
            logo.attemptMove(QgsLayoutPoint(logo_x, logo_y, QgsUnitTypes.LayoutMillimeters))
            logo.attemptResize(QgsLayoutSize(logo_width, logo_height, QgsUnitTypes.LayoutMillimeters))
            layout.addLayoutItem(logo)
            
            # Ajuste de Posição (Subir 10mm -> Gap negativo ou reduzido)
            # Logo Height = 25. 
            # Gap original = 3. 
            # Novo Gap = 3 - 10 = -7 (Sobreposição visual se houver branco, ou apenas compactação)
            info_gap = -7
            info_y = logo_y + logo_height + info_gap
        else:
            self.iface.messageBar().pushMessage("Aqueduct", f"Logo não encontrado em: {logo_path}", level=1)
            info_y = margin

        # --- Informações Agronômicas ---
        # Tenta ler dados_projeto.json
        project_home = QgsProject.instance().homePath()
        json_path = os.path.join(project_home, 'dados_projeto.json')
        
        info_html = ""
        # Fonts aumentadas em 30%
        # Normal: 8 -> 10.5pt
        # Bold: 10 -> 13pt
        if os.path.exists(json_path):
            try:
                import json
                with open(json_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    
                info_html = f"""
                <div style="font-family: Arial; font-size: 8.5pt; color: black;">
                    <b style="font-size: 9pt;">INFORMAÇÕES AGRONÔMICAS</b><br>
                    <b>CLIENTE:</b> {data.get('cliente', '-').upper()}<br>
                    <b>LOCAL:</b> {data.get('local', '-').upper()}<br>
                    <b>ÁREA TOTAL:</b> {data.get('area_total', '-')} ha<br>
                    <b>VAZÃO PROJETO:</b> {data.get('vazao_projeto', '-')} m³/h<br>
                    <b>VAZÃO DIÁRIA:</b> {data.get('vazao_diaria', '-')} m³<br>
                    <b>TEMPO TOTAL:</b> {data.get('tempo_total', '-')} h
                </div>
                """
            except:
                info_html = "Erro ao ler dados do projeto."
        else:
             info_html = """
             <div style="font-family: Arial; font-size: 8.5pt;">
                <b style="font-size: 9pt;">INFORMAÇÕES AGRONÔMICAS</b><br>
                Dados não calculados.<br>
             </div>
             """

        # Cria item de label (com renderização HTML)
        info_label = QgsLayoutItemLabel(layout)
        info_label.setText(info_html)
        info_label.setMode(QgsLayoutItemLabel.ModeHtml)
        
        # Posição X com 5mm de Padding Esquerdo
        info_x = sidebar_start_x + 5
        info_width = sidebar_width - 10 # Ajusta largura para caber no padding
        
        # Altura estimada (maior fonte = maior altura necessária)
        info_height = 50 
        
        info_label.attemptMove(QgsLayoutPoint(info_x, info_y, QgsUnitTypes.LayoutMillimeters))
        info_label.attemptResize(QgsLayoutSize(info_width, info_height, QgsUnitTypes.LayoutMillimeters))
        layout.addLayoutItem(info_label)
        
        # Legenda também sobe (gap reduzido em relação ao Info)
        legend_gap = -5
        legend_y = info_y + info_height + legend_gap
        
        # Legenda
        legend = QgsLayoutItemLegend(layout)
        legend.setTitle("Legenda")
        legend.setLinkedMap(map_item)
        # Filtra para mostrar apenas itens visíveis no mapa dentro da extensão
        legend.setLegendFilterByMapEnabled(True)
        
        # Reduzind fontes em ~20%
        # Padrão aprox: Title=16, Group=14, Item=12
        # Novos: Title=13, Group=11, Item=10
        
        font_title = QFont("Arial", 13)
        font_title.setBold(True)
        legend.setStyleFont(QgsLegendStyle.Title, font_title)
        
        font_group = QFont("Arial", 11)
        legend.setStyleFont(QgsLegendStyle.Group, font_group)
        legend.setStyleFont(QgsLegendStyle.Subgroup, font_group)
        
        font_item = QFont("Arial", 10)
        legend.setStyleFont(QgsLegendStyle.SymbolLabel, font_item)
        
        # Centralizar Legenda também? Ou alinhar à esquerda da coluna?
        # Geralmente centralizado fica melhor se o logo está centralizado.
        # Mas QgsLayoutItemLegend não tem alinhamento fácil sem saber a largura.
        # Vamos manter alinhado com o logo X ou padrão.
        # O usuário só pediu para centralizar a imagem. A legenda vou manter um pouco recuada ou alinhar com a imagem.
        # Vou usar sidebar_start_x + um pouco de padding (5mm) para a legenda não colar no mapa.
        legend_x = sidebar_start_x + 5
        
        legend.attemptMove(QgsLayoutPoint(legend_x, legend_y, QgsUnitTypes.LayoutMillimeters))
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
