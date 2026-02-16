from qgis.PyQt.QtCore import QObject
from qgis.PyQt.QtWidgets import QAction
from qgis.core import QgsProject
from qgis.utils import iface

class AqueductTool(QObject):
    """
    Classe base para todas as ferramentas do Aqueduct.
    As ferramentas devem herdar desta classe e implementar initGui e run.
    """

    def __init__(self, iface):
        super().__init__()
        self.iface = iface
        self.action = None

    def initGui(self):
        """
        Método responsável por criar a ação da ferramenta e adicioná-la à interface.
        Deve ser sobrescrito pelas subclasses.
        """
        raise NotImplementedError("O método initGui deve ser implementado nas subclasses.")

    def run(self):
        """
        Método principal da ferramenta. É chamado quando a ação é disparada.
        Deve ser sobrescrito pelas subclasses.
        """
        raise NotImplementedError("O método run deve ser implementado nas subclasses.")

    def unload(self):
        """
        Remove a ação da interface do QGIS.
        """
        if self.action:
            self.iface.removePluginMenu('&Aqueduct', self.action)
            self.iface.removeToolBarIcon(self.action)
            del self.action
