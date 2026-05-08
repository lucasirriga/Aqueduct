from qgis.PyQt.QtWidgets import QAction
from qgis.PyQt.QtGui import QIcon, QColor
from qgis.PyQt.QtCore import Qt
from qgis.core import (
    QgsMapLayerType,
    QgsWkbTypes, QgsSymbol, QgsSingleSymbolRenderer,
    QgsSimpleFillSymbolLayer
)
import os

from .ferramenta_base import AqueductTool

class SimbologiaSetoresTool(AqueductTool):
    """
    Ferramenta para aplicar simbologia em camadas de polígonos (setores).
    Linha: Preta, largura 0.16
    Preenchimento: Nenhum (Transparente)
    """

    def initGui(self):
        icon_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'icons', 'icone_simbologia_setores.svg')
        
        self.action = QAction(QIcon(icon_path), 'Aplicar Simbologia de Setores', self.iface.mainWindow())
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
            self.iface.messageBar().pushMessage("Aqueduct", "Selecione uma camada vetorial de POLÍGONOS.", level=3, duration=5)
            return

        if layer.geometryType() != QgsWkbTypes.PolygonGeometry:
            self.iface.messageBar().pushMessage("Aqueduct", "Operação permitida apenas em camadas de POLÍGONO.", level=3, duration=5)
            return

        # 2. Criação do Símbolo de Preenchimento Simples
        # Vamos criar a camada de símbolo manualmente para garantir o preenchimento transparente
        fill_layer = QgsSimpleFillSymbolLayer()
        fill_layer.setBrushStyle(Qt.NoBrush) # Sem preenchimento
        fill_layer.setStrokeColor(QColor("black"))
        fill_layer.setStrokeWidth(0.16)
        
        # Cria o símbolo e substitui a camada padrão
        symbol = QgsSymbol.defaultSymbol(layer.geometryType())
        symbol.changeSymbolLayer(0, fill_layer)
        
        # 3. Aplicação do Renderizador (Símbolo Único)
        renderer = QgsSingleSymbolRenderer(symbol)
        layer.setRenderer(renderer)
        layer.triggerRepaint()
        self.iface.layerTreeView().refreshLayerSymbology(layer.id())

        # 4. Relatório
        self.iface.messageBar().pushMessage("Aqueduct", "Simbologia de Setores aplicada (Contorno preto 0.16mm, Sem preenchimento)!", level=0, duration=3)
