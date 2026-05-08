from qgis.PyQt.QtWidgets import QAction
from qgis.PyQt.QtGui import QIcon, QColor
from qgis.core import (
    QgsMapLayerType,
    QgsWkbTypes, QgsSymbol, QgsSingleSymbolRenderer
)
import os

from .ferramenta_base import AqueductTool

class SimbologiaEmissoresTool(AqueductTool):
    """
    Ferramenta para aplicar simbologia simples em camadas de pontos (emissores).
    Cor: Vermelha
    Tamanho: 0.4
    """

    def initGui(self):
        icon_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'icons', 'icone_simbologia_emissores.svg')
        
        self.action = QAction(QIcon(icon_path), 'Aplicar Simbologia de Emissores', self.iface.mainWindow())
        self.action.triggered.connect(self.run)
        
        self.iface.addPluginToMenu('&Aqueduct', self.action)
        
        if self.toolbar:
            self.toolbar.addAction(self.action)
        else:
            self.iface.addToolBarIcon(self.action)

    def run(self):
        layer = self.iface.activeLayer()
        
        # 1. Validações
        if not layer or layer.type() != QgsMapLayerType.VectorLayer:
            self.iface.messageBar().pushMessage("Aqueduct", "Selecione uma camada vetorial de PONTOS.", level=3, duration=5)
            return

        if layer.geometryType() != QgsWkbTypes.PointGeometry:
            self.iface.messageBar().pushMessage("Aqueduct", "Operação permitida apenas em camadas de PONTO.", level=3, duration=5)
            return

        # 2. Criação do Símbolo de Ponto
        symbol = QgsSymbol.defaultSymbol(layer.geometryType())
        symbol.setColor(QColor("red"))
        symbol.setSize(0.4) # Tamanho solicitado: 0.4
        
        # 3. Aplicação do Renderizador (Símbolo Único)
        renderer = QgsSingleSymbolRenderer(symbol)
        layer.setRenderer(renderer)
        layer.triggerRepaint()
        self.iface.layerTreeView().refreshLayerSymbology(layer.id())

        # 4. Relatório
        self.iface.messageBar().pushMessage("Aqueduct", "Simbologia de Emissores aplicada (Vermelho, 0.4mm)!", level=0, duration=3)
