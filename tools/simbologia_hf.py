from qgis.PyQt.QtWidgets import QAction
from qgis.PyQt.QtGui import QIcon, QColor
from qgis.core import (
    QgsMapLayerType,
    QgsWkbTypes, QgsSymbol,
    QgsGraduatedSymbolRenderer, QgsGradientColorRamp, QgsStyle
)
import os

from .ferramenta_base import AqueductTool

class SimbologiaHfTool(AqueductTool):
    """
    Ferramenta para aplicar simbologia graduada baseada no campo HF (Perda de Carga)
    usando o modo Quantil com 6 classes.
    """

    def initGui(self):
        icon_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'icons', 'icone_simbologia_hf.svg')
        
        self.action = QAction(QIcon(icon_path), 'Aplicar Simbologia de HF (Perda de Carga)', self.iface.mainWindow())
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

        idx_hf = layer.fields().indexOf("HF")
        if idx_hf == -1:
             self.iface.messageBar().pushMessage("Aqueduct", "Campo 'HF' (Perda de Carga) não encontrado na camada.", level=3, duration=5)
             return
             
        # 2. Configurar a Rampa de Cores (Laranja para representar intensidade de perda)
        default_style = QgsStyle.defaultStyle()
        color_ramp = default_style.colorRamp("Oranges")
        if not color_ramp:
            # Fallback caso 'Oranges' não esteja presente
            color_ramp = QgsGradientColorRamp(QColor(255, 239, 219), QColor(255, 127, 0))
            
        # Símbolo base com largura padrão (0.6 conforme mantido para outras ferramentas)
        symbol = QgsSymbol.defaultSymbol(layer.geometryType())
        symbol.setWidth(0.6)
        
        # 3. Gerar Renderizador Graduado usando Quantil (6 classes conforme solicitado)
        renderer = QgsGraduatedSymbolRenderer.createRenderer(
            layer,
            "HF",
            6, # 6 classes
            QgsGraduatedSymbolRenderer.Quantile,
            symbol,
            color_ramp
        )
        
        if not renderer:
            self.iface.messageBar().pushMessage("Aqueduct", "Não foi possível gerar a simbologia. Verifique se há variação de valores no campo 'HF'.", level=2, duration=5)
            return

        # 4. Aplicação do Renderizador
        layer.setRenderer(renderer)
        layer.triggerRepaint()
        self.iface.layerTreeView().refreshLayerSymbology(layer.id())

        # 5. Relatório
        self.iface.messageBar().pushMessage("Aqueduct", "Simbologia de HF (6 classes) aplicada com sucesso!", level=0, duration=3)
