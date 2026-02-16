from qgis.PyQt.QtWidgets import QAction
from qgis.PyQt.QtGui import QIcon
import os

from .ferramenta_base import AqueductTool

class IrrigationCalcTool(AqueductTool):
    """
    Ferramenta de exemplo para cálculo de irrigação.
    Demonstra como herdar de AqueductTool e adicionar uma ação ao menu.
    """

    def initGui(self):
        icon_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'icons', 'icone_irrigacao.svg')
        
        self.action = QAction(QIcon(icon_path), 'Cálculo de Irrigação (Exemplo)', self.iface.mainWindow())
        self.action.triggered.connect(self.run)
        
        # Adiciona ao menu 'Aqueduct'
        # O self.iface.addPluginToMenu adiciona ao menu do plugin específico,
        # mas como queremos um menu 'Aqueduct' compartilhado, o main.py poderia gerenciar o menu.
        # No entanto, a API do QGIS facilita usar addPluginToMenu se o nome for consistente.
        # Vamos assumir que a base_tool ou main.py lida com o menu pai,
        # ou usamos addPluginToMenu com o nome do menu sendo o título do plugin.
        
        self.iface.addPluginToMenu('&Aqueduct', self.action)
        
        if self.toolbar:
            self.toolbar.addAction(self.action)
        else:
            self.iface.addToolBarIcon(self.action)

    def run(self):
        """Executa a lógica da ferramenta."""
        self.iface.messageBar().pushMessage(
            "Aqueduct",
            "Ferramenta de Cálculo de Irrigação carregada com sucesso! (Exemplo Modular)",
            level=0, # 0 = Info
            duration=5
        )
