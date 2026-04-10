from qgis.PyQt.QtWidgets import QAction
from qgis.PyQt.QtGui import QIcon
from qgis.core import (
    QgsMapLayerType,
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
        if not layer or layer.type() != QgsMapLayerType.VectorLayer:
            self.iface.messageBar().pushMessage("Aqueduct", "Selecione uma camada vetorial de LINHAS.", level=3, duration=5)
            return

        if layer.geometryType() != QgsWkbTypes.LineGeometry:
            self.iface.messageBar().pushMessage("Aqueduct", "Operação permitida apenas em camadas de LINHA.", level=3, duration=5)
            return

        idx_dn = layer.fields().indexOf("DN")
        if idx_dn == -1:
             self.iface.messageBar().pushMessage("Aqueduct", "Campo 'DN' não encontrado na camada.", level=3, duration=5)
             return

        # 2. Obter valores únicos de DN na camada
        unique_dns = set()
        for feat in layer.getFeatures():
            val = feat.attribute(idx_dn)
            if val is not None:
                try:
                    # Garantir que seja número para ordenar corretamente
                    unique_dns.add(int(float(val)))
                except (ValueError, TypeError):
                    pass
                    
        unique_dns = sorted(list(unique_dns))
        
        if not unique_dns:
             self.iface.messageBar().pushMessage("Aqueduct", "Nenhum valor válido de DN encontrado na camada.", level=2, duration=5)
             return

        # 3. Gerar Categorias com cores distintas uniformes
        categories = []
        total = len(unique_dns)
        
        for i, val in enumerate(unique_dns):
            # Distribuiçāo uniforme no espectro de cores HSV para garantir contraste
            hue = int((i * 360) / max(total, 1)) % 360
            color = QColor.fromHsv(hue, 230, 230)
            
            # Cria símbolo de linha padrão
            symbol = QgsSymbol.defaultSymbol(layer.geometryType())
            symbol.setColor(color)
            # Aumentando a espessura da linha um pouco para facilitar a visualização de longe
            symbol.setWidth(0.6) 
            
            label = f"DN {val}"
            category = QgsRendererCategory(val, symbol, label)
            categories.append(category)

        # 3. Aplicação do Renderizador
        renderer = QgsCategorizedSymbolRenderer("DN", categories)
        layer.setRenderer(renderer)
        layer.triggerRepaint()
        self.iface.layerTreeView().refreshLayerSymbology(layer.id())

        # 4. Relatório
        self.iface.messageBar().pushMessage("Aqueduct", "Simbologia aplicada com sucesso!", level=0, duration=3)
