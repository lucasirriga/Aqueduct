from qgis.PyQt.QtWidgets import QAction
from qgis.PyQt.QtGui import QIcon, QColor
from qgis.core import (
    QgsMapLayerType,
    QgsWkbTypes, QgsSymbol,
    QgsGraduatedSymbolRenderer, QgsGradientColorRamp, QgsStyle
)
import os

from .ferramenta_base import AqueductTool

class SimbologiaVazaoTool(AqueductTool):
    """
    Ferramenta para aplicar simbologia graduada baseada no campo V (Vazão)
    usando o modo Quantil (Quartis - 4 classes).
    """

    def initGui(self):
        icon_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'icons', 'icone_simbologia.svg')
        
        self.action = QAction(QIcon(icon_path), 'Aplicar Simbologia de Vazão', self.iface.mainWindow())
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

        idx_v = layer.fields().indexOf("V")
        if idx_v == -1:
             self.iface.messageBar().pushMessage("Aqueduct", "Campo 'V' (Vazão) não encontrado na camada.", level=3, duration=5)
             return
             
        # 2. Configurar a Rampa de Cores (Azul Claro para Azul Escuro)
        default_style = QgsStyle.defaultStyle()
        color_ramp = default_style.colorRamp("Blues")
        if not color_ramp:
            # Fallback caso 'Blues' não esteja presente no perfil local
            color_ramp = QgsGradientColorRamp(QColor(173, 216, 230), QColor(0, 0, 139))
            
        # Símbolo base com uma espessura razoável
        symbol = QgsSymbol.defaultSymbol(layer.geometryType())
        symbol.setWidth(0.6)
        
        # 3. Gerar Renderizador Graduado usando Quantil (4 classes para Quartis)
        renderer = QgsGraduatedSymbolRenderer.createRenderer(
            layer,
            "V",
            4, # 4 classes = Quartis
            QgsGraduatedSymbolRenderer.Quantile,
            symbol,
            color_ramp
        )
        
        if not renderer:
            self.iface.messageBar().pushMessage("Aqueduct", "Não foi possível gerar a simbologia. Verifique se há variação de valores no campo 'V'.", level=2, duration=5)
            return

        # 4. Aplicação do Renderizador
        layer.setRenderer(renderer)
        layer.triggerRepaint()
        self.iface.layerTreeView().refreshLayerSymbology(layer.id())

        # 5. Relatório
        self.iface.messageBar().pushMessage("Aqueduct", "Simbologia de Vazão (Quartis) aplicada com sucesso!", level=0, duration=3)
