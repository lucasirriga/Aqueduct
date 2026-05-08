from qgis.PyQt.QtWidgets import QAction
from qgis.PyQt.QtGui import QIcon, QColor
from qgis.core import (
    QgsMapLayerType,
    QgsWkbTypes, QgsSymbol, QgsSingleSymbolRenderer,
    QgsSimpleLineSymbolLayer, QgsMarkerLineSymbolLayer,
    QgsSimpleMarkerSymbolLayer, QgsProperty
)
import os

from .ferramenta_base import AqueductTool

class SimbologiaDirecaoTool(AqueductTool):
    """
    Ferramenta para aplicar simbologia de setas nas linhas para verificar a orientação (fluxo).
    Aplica uma linha simples + marcadores de seta no centro/intervalo.
    """

    def initGui(self):
        icon_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'icons', 'icone_simbologia_direcao.svg')
        
        self.action = QAction(QIcon(icon_path), 'Verificar Orientação (Direção)', self.iface.mainWindow())
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
            self.iface.messageBar().pushMessage("Aqueduct", "Selecione uma camada vetorial de LINHAS.", level=3, duration=5)
            return

        if layer.geometryType() != QgsWkbTypes.LineGeometry:
            self.iface.messageBar().pushMessage("Aqueduct", "Operação permitida apenas em camadas de LINHA.", level=3, duration=5)
            return

        # 2. Criação do Símbolo Composto
        
        # Camada 1: Linha Simples (Base)
        line_layer = QgsSimpleLineSymbolLayer()
        line_layer.setColor(QColor("#546E7A")) # Cinza Azulado
        line_layer.setWidth(0.6) # mm
        
        # Camada 2: Marcador (Seta)
        # Cria o marcador de seta (triângulo apontando pra direita = fluxo)
        marker_symbol = QgsSymbol.defaultSymbol(QgsWkbTypes.PointGeometry)
        simple_marker = QgsSimpleMarkerSymbolLayer()
        simple_marker.setShape(QgsSimpleMarkerSymbolLayer.ArrowHeadFilled)
        simple_marker.setColor(QColor("#FF5252")) # Vermelho
        simple_marker.setSize(5.0) # mm
        # Garantir que removeu camadas padrão e só tem o marker configurado
        marker_symbol.changeSymbolLayer(0, simple_marker)
        
        # Camada de Linha de Marcador (Repete o marcador ao longo da linha)
        marker_line = QgsMarkerLineSymbolLayer()
        marker_line.setSubSymbol(marker_symbol)
        
        # Configurar para aparecer no centro da linha ou em intervalos
        # Vamos colocar "Central Point" para simplificar, ou "Intervalo" se quiser ver em curvas.
        # "CentralPoint" é bom para saber a direção geral.
        marker_line.setPlacement(QgsMarkerLineSymbolLayer.CentralPoint)
        
        # Se quiser várias setas:
        # marker_line.setPlacement(QgsMarkerLineSymbolLayer.Interval)
        # marker_line.setInterval(30) # mm
        
        # Cria o símbolo de linha final combinando as camadas
        final_symbol = QgsSymbol.defaultSymbol(QgsWkbTypes.LineGeometry)
        
        # Remove a camada padrão que vem na inicialização
        final_symbol.deleteSymbolLayer(0)
        
        # Adiciona nossas camadas (ordem: linha embaixo, marcador em cima)
        final_symbol.appendSymbolLayer(line_layer)
        final_symbol.appendSymbolLayer(marker_line)

        # 3. Aplicação do Renderizador
        renderer = QgsSingleSymbolRenderer(final_symbol)
        layer.setRenderer(renderer)
        layer.triggerRepaint()
        self.iface.layerTreeView().refreshLayerSymbology(layer.id())

        # 4. Relatório
        self.iface.messageBar().pushMessage(
            "Aqueduct", 
            "Simbologia de orientação aplicada! Setas vermelhas indicam o fim da linha.", 
            level=0, 
            duration=4
        )
