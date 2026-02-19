from qgis.core import (
    QgsPrintLayout, QgsLayoutItemMap, QgsLayoutItemLegend,
    QgsLayoutItemScaleBar, QgsLayoutItemMapGrid, QgsLayoutPoint, QgsLayoutSize, QgsUnitTypes,
    QgsLayoutItemLabel, QgsLayoutItemShape, QgsFillSymbol, QgsLegendStyle, QgsLayoutItemPicture,
    QgsProject, QgsWkbTypes
)
from qgis.PyQt.QtGui import QFont
import os
import json

class MapLayoutGenerator:
    """
    Classe responsável por criar o layout padronizado do mapa Aqueduct.
    Pode ser usada tanto para gerar o PDF simples quanto para gerar a imagem do orçamento.
    """
    def __init__(self, project):
        self.project = project

    def create_layout(self, area_layer=None, standalone=True):
        """
        Cria e retorna um QgsPrintLayout configurado.
        :param standalone: Se True, aplica margens de 10mm e título (modo PDF Mapa).
                           Se False, margens 0 e sem título (modo Imagem para Orçamento).
        """
        layout = QgsPrintLayout(self.project)
        layout.initializeDefaults()
        layout.setName("Aqueduct Layout Standard")
        
        # A4 Landscape (297mm width x 210mm height)
        pc = layout.pageCollection()
        page = pc.page(0)
        page.setPageSize(QgsLayoutSize(297, 210, QgsUnitTypes.LayoutMillimeters))
        
        # Configurações de layout
        # Se standalone (PDF Mapa): Margem 10mm. Se embutido (Orçamento): Margem 0 (Printer fará a margem).
        margin = 10 if standalone else 0
        
        page_width = 297
        page_height = 210
        
        # 1. Borda
        border_padding = 2 if standalone else 0
        
        border = QgsLayoutItemShape(layout)
        border.setShapeType(QgsLayoutItemShape.Rectangle)
        border.attemptMove(QgsLayoutPoint(border_padding, border_padding, QgsUnitTypes.LayoutMillimeters))
        border.attemptResize(QgsLayoutSize(page_width - 2*border_padding, page_height - 2*border_padding, QgsUnitTypes.LayoutMillimeters))
        
        symbol = QgsFillSymbol.createSimple({
            'color': 'transparent', 
            'outline_color': 'black', 
            'outline_width': '0.3'
        })
        border.setSymbol(symbol)
        border.setLocked(True)
        layout.addLayoutItem(border)
        
        # 2. Mapa Principal
        map_item = QgsLayoutItemMap(layout)
        map_item.setRect(20, 20, 20, 20)
        
        # Extensão
        if area_layer:
            extent = area_layer.extent()
            buffer_dist = extent.width() * 0.3
            buffered_extent = extent.buffered(buffer_dist)
            map_item.setExtent(buffered_extent)
        else:
            # Tenta achar layer de setores automaticamente se não passado
            found_layer = self._find_sector_layer()
            if found_layer:
                extent = found_layer.extent()
                buffer_dist = extent.width() * 0.3
                buffered_extent = extent.buffered(buffer_dist)
                map_item.setExtent(buffered_extent)
            else:
                # Fallback: Canvas Extent
                map_item.zoomToExtent(self.project.mapCanvas().extent())
        
        # Grade
        self._setup_grid(map_item)
        
        # Posicionamento do Mapa
        # Sidebar começa em 230.
        sidebar_start_x = 230
        
        # Se standalone: Margem 10. Mapa de 10 a 230 (W=220). Altura de 10 a 200 (H=190).
        # Se não: Margem 0. Mapa de 0 a 230 (W=230). Altura de 0 a 210 (H=210).
        
        map_x = margin
        map_y = margin
        map_width = sidebar_start_x - margin
        map_height = page_height - (2 * margin)
        
        map_item.attemptMove(QgsLayoutPoint(map_x, map_y, QgsUnitTypes.LayoutMillimeters))
        map_item.attemptResize(QgsLayoutSize(map_width, map_height, QgsUnitTypes.LayoutMillimeters))
        layout.addLayoutItem(map_item)
        
        # 3. Barra Lateral (Conteúdo)
        sidebar_width = 57 # 297 - 230 = 67? Não, 297 (Width page).
        # Espaço restante à direita: 297 - 230 = 67mm.
        # Original code used sidebar_width = 57 (com margem de 10 na direita).
        # Se standalone=False, podemos usar total? 
        # Vamos manter a logica da sidebar fixa em 230 para não quebrar alinhamento.
        
        right_margin = margin # 10 ou 0
        sidebar_width = (page_width - right_margin) - sidebar_start_x
        
        logo_width = 50
        
        # Logo
        logo_height = 25
        logo_y = margin
        # Centralizado na sidebar
        # Sidebar vai de 230 até (297-margin).
        # Centro = 230 + (largura_disponivel)/2
        
        logo_x = sidebar_start_x + (sidebar_width - logo_width) / 2
        
        logo_path = os.path.join(os.path.dirname(__file__), '..', 'img', 'logo tocantins agropecuária ltda.png')
        if os.path.exists(logo_path):
            logo = QgsLayoutItemPicture(layout)
            logo.setPicturePath(logo_path)
            logo.setResizeMode(QgsLayoutItemPicture.Zoom)
            logo.attemptMove(QgsLayoutPoint(logo_x, logo_y, QgsUnitTypes.LayoutMillimeters))
            logo.attemptResize(QgsLayoutSize(logo_width, logo_height, QgsUnitTypes.LayoutMillimeters))
            layout.addLayoutItem(logo)
            
            info_gap = -7
            info_y = logo_y + logo_height + info_gap
        else:
            info_y = margin
            
        # Informações Agronômicas
        self._add_info_label(layout, sidebar_start_x, info_y, sidebar_width)
        
        # Legenda
        legend_y = info_y + 50 - 5 # Info height hardcoded as 50 roughly
        self._add_legend(layout, map_item, sidebar_start_x + 5, legend_y)
        
        # Barra de Escala (canto inferior esquerdo do mapa)
        # X = map_x + 5. Y = map_y + map_height - 15
        self._add_scalebar(layout, map_item, map_x + 5, map_y + map_height - 25)
        
        return layout

    def _find_sector_layer(self):
        # Tenta ler do info_projeto
        project_home = self.project.homePath()
        json_path = os.path.join(project_home, 'dados_projeto.json')
        if os.path.exists(json_path):
            try:
                with open(json_path) as f:
                    data = json.load(f)
                    lname = data.get('layer_name')
                    if lname:
                        ls = self.project.mapLayersByName(lname)
                        if ls: return ls[0]
            except: pass
        
        # Fallback: Primeira polygon layer
        for l in self.project.mapLayers().values():
            if l.type() == l.VectorLayer and l.geometryType() == QgsWkbTypes.PolygonGeometry:
                return l
        return None

    def _setup_grid(self, map_item):
        grid = QgsLayoutItemMapGrid("Grade Principal", map_item)
        map_item.grids().addGrid(grid)
        
        grid.setStyle(QgsLayoutItemMapGrid.FrameAnnotationsOnly) 
        grid.setFrameStyle(QgsLayoutItemMapGrid.ExteriorTicks)
        grid.setFrameWidth(1.0)
        
        # Intervalo Dinâmico
        extent = map_item.extent()
        target_interval = extent.width() / 4.0
        grid.setIntervalX(target_interval)
        grid.setIntervalY(target_interval)
        
        grid.setAnnotationEnabled(True)
        grid.setAnnotationPosition(QgsLayoutItemMapGrid.OutsideMapFrame, QgsLayoutItemMapGrid.Left)
        grid.setAnnotationPosition(QgsLayoutItemMapGrid.OutsideMapFrame, QgsLayoutItemMapGrid.Right)
        grid.setAnnotationPosition(QgsLayoutItemMapGrid.OutsideMapFrame, QgsLayoutItemMapGrid.Top)
        grid.setAnnotationPosition(QgsLayoutItemMapGrid.OutsideMapFrame, QgsLayoutItemMapGrid.Bottom)
        
        grid.setAnnotationDirection(QgsLayoutItemMapGrid.Vertical, QgsLayoutItemMapGrid.Left)
        grid.setAnnotationDirection(QgsLayoutItemMapGrid.VerticalDescending, QgsLayoutItemMapGrid.Right)
        
        grid.setAnnotationFormat(QgsLayoutItemMapGrid.Decimal)
        grid.setAnnotationFont(QFont("Arial", 7))

    def _add_info_label(self, layout, x, y, width):
        project_home = self.project.homePath()
        json_path = os.path.join(project_home, 'dados_projeto.json')
        
        info_html = ""
        if os.path.exists(json_path):
            try:
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
                info_html = "Erro dados."
        else:
            info_html = "Sem dados calculados."

        label = QgsLayoutItemLabel(layout)
        label.setText(info_html)
        label.setMode(QgsLayoutItemLabel.ModeHtml)
        
        final_x = x + 5
        final_w = width - 10
        height = 50 
        
        label.attemptMove(QgsLayoutPoint(final_x, y, QgsUnitTypes.LayoutMillimeters))
        label.attemptResize(QgsLayoutSize(final_w, height, QgsUnitTypes.LayoutMillimeters))
        layout.addLayoutItem(label)

    def _add_legend(self, layout, map_item, x, y):
        legend = QgsLayoutItemLegend(layout)
        legend.setTitle("Legenda")
        legend.setLinkedMap(map_item)
        legend.setLegendFilterByMapEnabled(True)
        
        font_title = QFont("Arial", 13)
        font_title.setBold(True)
        legend.setStyleFont(QgsLegendStyle.Title, font_title)
        
        font_group = QFont("Arial", 11)
        legend.setStyleFont(QgsLegendStyle.Group, font_group)
        legend.setStyleFont(QgsLegendStyle.Subgroup, font_group)
        
        font_item = QFont("Arial", 10)
        legend.setStyleFont(QgsLegendStyle.SymbolLabel, font_item)
        
        legend.attemptMove(QgsLayoutPoint(x, y, QgsUnitTypes.LayoutMillimeters))
        layout.addLayoutItem(legend)

    def _add_scalebar(self, layout, map_item, x, y):
        scalebar = QgsLayoutItemScaleBar(layout)
        scalebar.setStyle('Single Box')
        scalebar.setLinkedMap(map_item)
        scalebar.applyDefaultSize()
        scalebar.attemptMove(QgsLayoutPoint(x, y, QgsUnitTypes.LayoutMillimeters))
        layout.addLayoutItem(scalebar)
