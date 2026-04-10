from qgis.core import (
    QgsMapLayerType,
    QgsPrintLayout, QgsLayoutItemMap, QgsLayoutItemLegend,
    QgsLayoutItemScaleBar, QgsLayoutItemMapGrid, QgsLayoutPoint, QgsLayoutSize, QgsUnitTypes,
    QgsLayoutItemLabel, QgsLayoutItemShape, QgsFillSymbol, QgsLegendStyle, QgsLayoutItemPicture,
    QgsProject, QgsWkbTypes
)
from qgis.PyQt.QtGui import QFont
import os
import json


# Tamanhos de página disponíveis (largura x altura em mm, paisagem)
TAMANHOS_PAGINA = {
    'A4 Paisagem  (297 × 210 mm)':  (297, 210),
    'A3 Paisagem  (420 × 297 mm)':  (420, 297),
    'A2 Paisagem  (594 × 420 mm)':  (594, 420),
    'A1 Paisagem  (841 × 594 mm)':  (841, 594),
    'A0 Paisagem  (1189 × 841 mm)': (1189, 841),
}

# Tamanho base de referência (A4 Paisagem)
BASE_W = 297
BASE_H = 210


class MapLayoutGenerator:
    """
    Classe responsável por criar o layout padronizado do mapa Aqueduct.
    Pode ser usada tanto para gerar o PDF simples quanto para gerar a imagem do orçamento.

    O layout original foi projetado para A4 Paisagem (297 x 210 mm).
    Ao escolher um tamanho maior, todos os elementos são escalados proporcionalmente
    mantendo as mesmas proporções visuais do layout padrão.
    """

    def __init__(self, project):
        self.project = project

    def create_layout(self, area_layer=None, standalone=True, page_size_key='A4 Paisagem  (297 × 210 mm)'):
        """
        Cria e retorna um QgsPrintLayout configurado.

        :param standalone:    Se True, aplica margens de 10mm e título (modo PDF Mapa).
                              Se False, margens 0 e sem título (modo Imagem para Orçamento).
        :param page_size_key: Chave do dicionário TAMANHOS_PAGINA. Default: A4 Paisagem.
        """
        layout = QgsPrintLayout(self.project)
        layout.initializeDefaults()
        layout.setName("Aqueduct Layout Standard")

        # Dimensão real da página escolhida
        pw, ph = TAMANHOS_PAGINA.get(page_size_key, (BASE_W, BASE_H))

        # Fator de escala em relação ao A4 Paisagem
        # Usamos o fator de width para manter proporção horizontal consistente
        sx = pw / BASE_W   # escala horizontal
        sy = ph / BASE_H   # escala vertical

        # Definir página
        pc = layout.pageCollection()
        page = pc.page(0)
        page.setPageSize(QgsLayoutSize(pw, ph, QgsUnitTypes.LayoutMillimeters))

        # Margens
        margin = (10 * sx) if standalone else 0

        # ----------------------------------------------------------------
        # 1. Borda
        # ----------------------------------------------------------------
        bp = (2 * sx) if standalone else 0
        border = QgsLayoutItemShape(layout)
        border.setShapeType(QgsLayoutItemShape.Rectangle)
        border.attemptMove(QgsLayoutPoint(bp, bp, QgsUnitTypes.LayoutMillimeters))
        border.attemptResize(QgsLayoutSize(pw - 2*bp, ph - 2*bp, QgsUnitTypes.LayoutMillimeters))
        symbol = QgsFillSymbol.createSimple({
            'color': 'transparent',
            'outline_color': 'black',
            'outline_width': str(0.3 * sx)
        })
        border.setSymbol(symbol)
        border.setLocked(True)
        layout.addLayoutItem(border)

        # ----------------------------------------------------------------
        # 2. Mapa Principal
        # ----------------------------------------------------------------
        map_item = QgsLayoutItemMap(layout)
        map_item.setRect(20, 20, 20, 20)

        # Extensão
        if area_layer:
            extent = area_layer.extent()
            buffer_dist = extent.width() * 0.3
            map_item.setExtent(extent.buffered(buffer_dist))
        else:
            found_layer = self._find_sector_layer()
            if found_layer:
                extent = found_layer.extent()
                buffer_dist = extent.width() * 0.3
                map_item.setExtent(extent.buffered(buffer_dist))
            else:
                map_item.zoomToExtent(self.project.mapCanvas().extent())

        # Grade
        self._setup_grid(map_item, sx)

        # Posicionamento — sidebar começa no mesmo ponto proporcional (230/297 do A4)
        sidebar_start_x = 230 * sx
        gap_sidebar = 3 * sx
        map_x = margin
        map_y = margin
        map_width  = sidebar_start_x - margin - gap_sidebar
        map_height = ph - (2 * margin)

        map_item.attemptMove(QgsLayoutPoint(map_x, map_y, QgsUnitTypes.LayoutMillimeters))
        map_item.attemptResize(QgsLayoutSize(map_width, map_height, QgsUnitTypes.LayoutMillimeters))
        layout.addLayoutItem(map_item)

        # ----------------------------------------------------------------
        # 3. Barra Lateral
        # ----------------------------------------------------------------
        right_margin = margin
        sidebar_width = (pw - right_margin) - sidebar_start_x

        logo_width  = 50 * sx
        logo_height = 25 * sy
        logo_y = margin

        logo_x = sidebar_start_x + (sidebar_width - logo_width) / 2

        logo_path = os.path.join(
            os.path.dirname(__file__), '..', 'img', 'logo tocantins agropecuária ltda.png')
        if os.path.exists(logo_path):
            logo = QgsLayoutItemPicture(layout)
            logo.setPicturePath(logo_path)
            logo.setResizeMode(QgsLayoutItemPicture.Zoom)
            logo.attemptMove(QgsLayoutPoint(logo_x, logo_y, QgsUnitTypes.LayoutMillimeters))
            logo.attemptResize(QgsLayoutSize(logo_width, logo_height, QgsUnitTypes.LayoutMillimeters))
            layout.addLayoutItem(logo)
            info_gap = -7 * sy
            info_y = logo_y + logo_height + info_gap
        else:
            info_y = margin

        # Informações Agronômicas
        self._add_info_label(layout, sidebar_start_x, info_y, sidebar_width, sx, sy)

        # Legenda
        legend_y = info_y + 50 * sy - 5 * sy
        self._add_legend(layout, map_item, sidebar_start_x + 5 * sx, legend_y, sx)

        # Barra de Escala
        self._add_scalebar(layout, map_item, map_x + 5 * sx, map_y + map_height - 25 * sy, sx)

        return layout

    # ------------------------------------------------------------------
    def _find_sector_layer(self):
        project_home = self.project.homePath()
        json_path = os.path.join(project_home, 'dados_projeto.json')
        if os.path.exists(json_path):
            try:
                with open(json_path) as f:
                    data = json.load(f)
                    lname = data.get('layer_name')
                    if lname:
                        ls = self.project.mapLayersByName(lname)
                        if ls:
                            return ls[0]
            except Exception:
                pass

        for l in self.project.mapLayers().values():
            if (l.type() == QgsMapLayerType.VectorLayer and
                    l.geometryType() == QgsWkbTypes.PolygonGeometry):
                return l
        return None

    def _setup_grid(self, map_item, sx=1.0):
        grid = QgsLayoutItemMapGrid("Grade Principal", map_item)
        map_item.grids().addGrid(grid)

        grid.setStyle(QgsLayoutItemMapGrid.FrameAnnotationsOnly)
        grid.setFrameStyle(QgsLayoutItemMapGrid.ExteriorTicks)

        # Espessura do tick (traço externo da grade) proporcional
        grid.setFrameWidth(max(0.5, round(1.0 * sx, 1)))
        # Espessura da linha do frame (caneta) proporcional — base 0.3mm no A4
        grid.setFramePenSize(max(0.2, round(0.3 * sx, 2)))
        # Distância entre o frame e a anotação de coordenadas proporcional — base 1mm no A4
        grid.setAnnotationFrameDistance(max(0.5, round(1.0 * sx, 1)))

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
        # Fonte da grade proporcional: base 7pt no A4, escala linear com sx
        font_grade = QFont("Arial", max(5, round(7 * sx)))
        grid.setAnnotationFont(font_grade)

    def _add_info_label(self, layout, x, y, width, sx=1.0, sy=1.0):
        project_home = self.project.homePath()
        json_path = os.path.join(project_home, 'dados_projeto.json')

        # Fonte das informações aumentada para preencher bem a área disponível.
        # Base A4: corpo 9pt, título 10pt. Escala proporcionalmente com sx.
        fsize  = max(7, min(16, round(9.0 * sx, 1)))
        ftitle = max(8, min(18, round(10.0 * sx, 1)))

        info_html = ""
        if os.path.exists(json_path):
            try:
                with open(json_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                info_html = f"""
                <div style="font-family: Arial; font-size: {fsize}pt; color: black;">
                    <b style="font-size: {ftitle}pt;">INFORMAÇÕES AGRONÔMICAS</b><br>
                    <b>CLIENTE:</b> {data.get('cliente', '-').upper()}<br>
                    <b>LOCAL:</b> {data.get('local', '-').upper()}<br>
                    <b>ÁREA TOTAL:</b> {data.get('area_total', '-')} ha<br>
                    <b>VAZÃO PROJETO:</b> {data.get('vazao_projeto', '-')} m³/h<br>
                    <b>VAZÃO DIÁRIA:</b> {data.get('vazao_diaria', '-')} m³<br>
                    <b>TEMPO TOTAL:</b> {data.get('tempo_total', '-')} h<br>
                    <b>TEMPO/SETOR:</b> {data.get('tempo_setor', '-')} h<br>
                    <b>ENERGIA:</b> {(data.get('energia') or '-').upper()}<br>
                    <b>FONTE ÁGUA:</b> {(data.get('fonte_agua') or '-').upper()}<br>
                    <b>QTD. FONTES:</b> {data.get('qtd_fontes', '-')}
                </div>
                """
            except Exception:
                info_html = "Erro dados."
        else:
            info_html = "Sem dados calculados."

        label = QgsLayoutItemLabel(layout)
        label.setText(info_html)
        label.setMode(QgsLayoutItemLabel.ModeHtml)

        final_x = x + 5 * sx
        final_w = width - 10 * sx
        height = 80 * sy

        label.attemptMove(QgsLayoutPoint(final_x, y, QgsUnitTypes.LayoutMillimeters))
        label.attemptResize(QgsLayoutSize(final_w, height, QgsUnitTypes.LayoutMillimeters))
        layout.addLayoutItem(label)

    def _add_legend(self, layout, map_item, x, y, sx=1.0):
        legend = QgsLayoutItemLegend(layout)
        legend.setTitle("Legenda")
        legend.setLinkedMap(map_item)
        legend.setLegendFilterByMapEnabled(True)

        # Fontes reduzidas 36% do original (duas aplicações de −20%):
        #   Título:  13 → 10.4 → 8.3pt base
        #   Grupo:   11 →  8.8 → 7.0pt base
        #   Item:    10 →  8.0 → 6.4pt base
        font_title = QFont("Arial", max(5, round(8.3 * sx)))
        font_title.setBold(True)
        legend.setStyleFont(QgsLegendStyle.Title, font_title)

        font_group = QFont("Arial", max(5, round(7.0 * sx)))
        legend.setStyleFont(QgsLegendStyle.Group, font_group)
        legend.setStyleFont(QgsLegendStyle.Subgroup, font_group)

        font_item = QFont("Arial", max(4, round(6.4 * sx)))
        legend.setStyleFont(QgsLegendStyle.SymbolLabel, font_item)

        legend.attemptMove(QgsLayoutPoint(x, y, QgsUnitTypes.LayoutMillimeters))
        layout.addLayoutItem(legend)

    def _add_scalebar(self, layout, map_item, x, y, sx=1.0):
        scalebar = QgsLayoutItemScaleBar(layout)
        scalebar.setStyle('Single Box')
        scalebar.setLinkedMap(map_item)
        scalebar.applyDefaultSize()

        # Altura da caixa e fonte proporcionais ao tamanho da página
        # Base A4: altura 3mm, fonte 8pt
        box_height = max(2.0, round(3.0 * sx, 1))  # mm
        font_sb    = QFont("Arial", max(5, round(8 * sx)))

        scalebar.setHeight(box_height)
        scalebar.setFont(font_sb)

        scalebar.attemptMove(QgsLayoutPoint(x, y, QgsUnitTypes.LayoutMillimeters))
        layout.addLayoutItem(scalebar)
