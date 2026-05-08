import os
from qgis.PyQt.QtWidgets import QAction, QInputDialog, QMessageBox, QLineEdit
from qgis.PyQt.QtGui import QIcon, QColor
from qgis.PyQt.QtCore import Qt, QRect, QPoint
from qgis.gui import QgsMapTool, QgsRubberBand, QgsMapCanvas, QgsMapMouseEvent
from qgis.core import QgsProject, QgsRectangle, QgsGeometry, QgsWkbTypes, QgsFields
from .ferramenta_base import AqueductTool

class SelectionSumMapTool(QgsMapTool):
    """
    Ferramenta de mapa para seleção por retângulo que soma valores de um campo.
    """
    def __init__(self, canvas, layer, field_name):
        super().__init__(canvas)
        self.canvas = canvas
        self.layer = layer
        self.field_name = field_name
        self.rubber_band = QgsRubberBand(self.canvas, QgsWkbTypes.PolygonGeometry)
        self.rubber_band.setColor(QColor(0, 120, 215, 60))
        self.rubber_band.setWidth(2)
        self.start_point = None
        self.active = False

    def canvasPressEvent(self, e: QgsMapMouseEvent):
        if e.button() == Qt.LeftButton:
            self.start_point = e.pos()
            self.active = True
            self.rubber_band.reset(QgsWkbTypes.PolygonGeometry)
            self.rubber_band.show()

    def canvasMoveEvent(self, e: QgsMapMouseEvent):
        if self.active and self.start_point:
            rect = QRect(self.start_point, e.pos())
            self.rubber_band.setToCanvasRectangle(rect)

    def canvasReleaseEvent(self, e: QgsMapMouseEvent):
        if self.active:
            end_point = e.pos()
            
            # Determina o retângulo de busca
            rect = self.to_rectangle(self.start_point, end_point)
            
            # Se for apenas um clique (sem arrasto significativo), cria um pequeno buffer
            if rect.width() < 2 and rect.height() < 2:
                # Transforma ponto da tela em ponto do mapa
                map_point = self.canvas.getCoordinateTransform().toMapCoordinates(self.start_point.x(), self.start_point.y())
                # Pequeno buffer em unidades do mapa para capturar a feição no clique
                pixel_size = self.canvas.mapUnitsPerPixel()
                tolerance = 5 * pixel_size
                rect = QgsRectangle(map_point.x() - tolerance, map_point.y() - tolerance, 
                                   map_point.x() + tolerance, map_point.y() + tolerance)
            else:
                m2p = self.canvas.getCoordinateTransform()
                p1 = m2p.toMapCoordinates(rect.left(), rect.top())
                p2 = m2p.toMapCoordinates(rect.right(), rect.bottom())
                rect = QgsRectangle(p1, p2)

            # Seleciona na camada
            modifiers = e.modifiers()
            if modifiers & Qt.ShiftModifier:
                behavior = self.layer.AddToSelection
            elif modifiers & Qt.ControlModifier:
                behavior = self.layer.RemoveFromSelection
            else:
                behavior = self.layer.SetSelection

            self.layer.selectByRect(rect, behavior)
            
            self.rubber_band.hide()
            self.active = False
            self.start_point = None
            
            # Calcular a soma após a seleção
            self.calcular_soma()

    def to_rectangle(self, p1, p2):
        return QRect(min(p1.x(), p2.x()), min(p1.y(), p2.y()), 
                     abs(p1.x() - p2.x()), abs(p1.y() - p2.y()))

    def calcular_soma(self):
        if not self.layer: return
        
        selection = self.layer.selectedFeatures()
        total = 0.0
        count = len(selection)
        
        for feat in selection:
            val = feat[self.field_name]
            if val is not None:
                try:
                    total += float(val)
                except:
                    pass
        
        msg = f"<b>Soma de {self.field_name}:</b> {total:,.2f}  |  <b>Contagem:</b> {count} feições"
        from qgis.utils import iface
        iface.messageBar().pushMessage("Aqueduct - Seleção", msg, level=0, duration=0)

    def deactivate(self):
        self.rubber_band.hide()
        super().deactivate()

class SomadorSelecaoTool(AqueductTool):
    """
    Gerenciador da ferramenta Somador de Seleção no menu do Aqueduct.
    """
    def __init__(self, iface, toolbar=None):
        super().__init__(iface, toolbar)
        self.canvas = iface.mapCanvas()
        self.active_tool = None

    def initGui(self):
        icon_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'icons', 'icone_somador_selecao.svg') 
        if not os.path.exists(icon_path):
             icon_path = ""
             
        self.action = QAction(QIcon(icon_path), 'Somador de Seleção (Colunas)', self.iface.mainWindow())
        self.action.triggered.connect(self.run)
        
        self.iface.addPluginToMenu('&Aqueduct', self.action)
        
        if self.toolbar:
            self.toolbar.addAction(self.action)
        else:
            self.iface.addToolBarIcon(self.action)

    def run(self):
        print("Aqueduct Debug: Iniciando SomadorSelecaoTool.run()")
        layer = self.iface.activeLayer()
        
        if not layer:
            self.iface.messageBar().pushMessage("Aqueduct", "Nenhuma camada selecionada no painel de camadas.", level=1)
            return
            
        if layer.type() != 0: # 0 = VectorLayer
            QMessageBox.warning(self.iface.mainWindow(), "Aqueduct", f"A camada selecionada ('{layer.name()}') não é uma camada vetorial!")
            return

        # Filtrar campos numéricos
        numeric_fields = []
        for field in layer.fields():
            if field.isNumeric():
                numeric_fields.append(field.name())

        print(f"Aqueduct Debug: Campos numéricos encontrados: {len(numeric_fields)}")

        if not numeric_fields:
            QMessageBox.warning(self.iface.mainWindow(), "Aqueduct", "Esta camada não possui campos numéricos para somar!")
            return

        try:
            field, ok = QInputDialog.getItem(self.iface.mainWindow(), "Somador de Seleção", 
                                            "Escolha a coluna para somar:", numeric_fields, 0, False)
            
            if ok and field:
                print(f"Aqueduct Debug: Campo selecionado: {field}")
                self.active_tool = SelectionSumMapTool(self.canvas, layer, field)
                self.canvas.setMapTool(self.active_tool)
                self.iface.messageBar().pushMessage("Aqueduct", f"Ferramenta Ativa: Somando coluna '{field}'. Use o mouse para selecionar feições.", level=0, duration=5)
            else:
                print("Aqueduct Debug: Usuário cancelou seleção de campo.")
        except Exception as e:
            print(f"Aqueduct Debug: Erro no diálogo: {e}")
            self.iface.messageBar().pushMessage("Aqueduct Erro", f"Falha ao iniciar ferramenta: {e}", level=2)
