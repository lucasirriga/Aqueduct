from qgis.PyQt.QtWidgets import QAction
from qgis.PyQt.QtGui import QIcon
from qgis.core import (
    QgsWkbTypes, QgsSymbol, QgsRendererCategory, 
    QgsCategorizedSymbolRenderer
)
from qgis.PyQt.QtGui import QColor
import os

from .ferramenta_base import AqueductTool

class SimbologiaDnTool(AqueductTool):
    """
    Ferramenta para aplicar simbologia categorizada baseada no campo DN.
    Cores:
    50  - Verde
    75  - Laranja
    100 - Azul
    125 - Lilás
    150 - Roxo
    """

    def initGui(self):
        icon_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'icons', 'icone_simbologia.svg')
        
        self.action = QAction(QIcon(icon_path), 'Aplicar Simbologia DN', self.iface.mainWindow())
        self.action.triggered.connect(self.run)
        
        self.iface.addPluginToMenu('&Aqueduct', self.action)
        
        if self.toolbar:
            self.toolbar.addAction(self.action)
        else:
            self.iface.addToolBarIcon(self.action)

    def run(self):
        layer = self.iface.activeLayer()
        
        # 1. Validações
        if not layer or layer.type() != layer.VectorLayer:
            self.iface.messageBar().pushMessage("Aqueduct", "Selecione uma camada vetorial de LINHAS.", level=3)
            return

        if layer.geometryType() != QgsWkbTypes.LineGeometry:
            self.iface.messageBar().pushMessage("Aqueduct", "Operação permitida apenas em camadas de LINHA.", level=3)
            return

        idx_dn = layer.fields().indexOf("DN")
        if idx_dn == -1:
             self.iface.messageBar().pushMessage("Aqueduct", "Campo 'DN' não encontrado na camada.", level=3)
             return

        # 2. Definição das Categorias
        # Valor, Label, Cor (Hex)
        config = [
            (50,  "DN 50",  "#4CAF50"), # Verde
            (75,  "DN 75",  "#FF9800"), # Laranja
            (100, "DN 100", "#2196F3"), # Azul
            (125, "DN 125", "#E040FB"), # Lilás
            (150, "DN 150", "#9C27B0"), # Roxo
        ]
        
        categories = []
        
        for value, label, color_code in config:
            # Cria símbolo de linha padrão
            symbol = QgsSymbol.defaultSymbol(layer.geometryType())
            symbol.setColor(QColor(color_code))
            symbol.setWidth(0.4) # aprox 1 pixel dependendo da resolução, ou 1 (mm no qgis) ou pixel unit
            
            # Ajuste para pixel se possível, mas layer.renderer usa unidades de mapa ou mm.
            # O padrão do QGIS costuma ser Milímetros (mm). 
            # 1 pixel em tela é relativo. Vamos fixar uma espessura fina visível.
            # Se o usuário pediu "1 pixel", '0' costuma ser "hairline" (1px dispositivo).
            # Mas '0' pode ser muito fino para impressão. Vamos usar width 0.6mm padrão ou configurar unit.
            # Vou usar width 0.5 (padrão razoável) ou tentar configurar Unit = Pixel?
            # Para simplificar e atender "1 pixel", usaremos uma espessura fixa pequena.
            symbol.setWidth(0.26) # ~1px a 96dpi (1/96 inch = 0.26mm)
            
            category = QgsRendererCategory(value, symbol, label)
            categories.append(category)

        # 3. Aplicação do Renderizador
        renderer = QgsCategorizedSymbolRenderer("DN", categories)
        layer.setRenderer(renderer)
        layer.triggerRepaint()
        self.iface.layerTreeView().refreshLayerSymbology(layer.id())

        # 4. Relatório
        self.iface.messageBar().pushMessage("Aqueduct", "Simbologia aplicada com sucesso!", level=0, duration=3)
