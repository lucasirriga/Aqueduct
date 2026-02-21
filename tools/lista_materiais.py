from qgis.PyQt.QtWidgets import (
    QAction, QDialog, QVBoxLayout, QHBoxLayout, QListWidget, QTableWidget, 
    QTableWidgetItem, QLabel, QLineEdit, QDoubleSpinBox, QPushButton, 
    QMessageBox, QWidget, QHeaderView, QAbstractItemView, QTabWidget,
    QInputDialog, QComboBox, QSplitter
)
from qgis.PyQt.QtGui import QIcon, QColor
from qgis.core import QgsProject, QgsApplication
import os
import json
import csv
import random
import copy

from .ferramenta_base import AqueductTool
from .gerenciar_pecas import PecaManager
from .gerenciar_blocos import BlocoManager, GerenciarBlocosDialog

class ProjectBOMManager:
    def __init__(self):
        self.project = QgsProject.instance()
        self.filepath = self.get_project_bom_path()
        
        # Estrutura:
        # self.budgets = {
        #    "Orçamento Base": {
        #        "items": [{'nome': 'Tubo', 'quantidade': 10, 'preco_unitario': 5.0}],  # Peças Avulsas
        #        "project_blocos": [{'nome': 'Kit Cavalete', 'quantidade': 2}]         # Blocos no Projeto
        #    }
        # }
        self.budgets = {} 
        self.current_budget = "Orçamento Base"
        
        self.load()

    def get_project_bom_path(self):
        project_home = self.project.homePath()
        if not project_home:
            return None
        return os.path.join(project_home, 'lista_materiais.json')

    def load(self):
        self.budgets = {}
        path = self.get_project_bom_path()
        if path and os.path.exists(path):
            try:
                with open(path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    
                # Migração: Lista Antiga -> Dict Novo
                if isinstance(data, list):
                    self.budgets = {"Orçamento Base": {"items": data, "project_blocos": []}}
                    self.current_budget = "Orçamento Base"
                
                # Formato Intermediário (só itens)
                elif isinstance(data, dict) and 'budgets' in data:
                    raw_budgets = data['budgets']
                    self.current_budget = data.get('current', "Orçamento Base")
                    
                    # Normalizar estrutura interna de cada budget
                    for name, content in raw_budgets.items():
                        if isinstance(content, list): # Era só lista de itens
                             self.budgets[name] = {"items": content, "project_blocos": []}
                        else:
                             self.budgets[name] = content
                             if "project_blocos" not in self.budgets[name]:
                                 self.budgets[name]["project_blocos"] = []
                else:
                    self.budgets = {"Orçamento Base": {"items": [], "project_blocos": []}}
                    self.current_budget = "Orçamento Base"
                    
            except Exception as e:
                print(f"Erro ao carregar BOM: {e}")
                self.budgets = {"Orçamento Base": {"items": [], "project_blocos": []}}
        else:
            self.budgets = {"Orçamento Base": {"items": [], "project_blocos": []}}

    def save(self):
        path = self.get_project_bom_path()
        if not path: return False
            
        data = {
            'budgets': self.budgets,
            'current': self.current_budget
        }
        try:
            with open(path, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=4, ensure_ascii=False)
            return True
        except Exception as e:
            print(f"Erro save: {e}")
            return False

    # --- Properties ---
    @property
    def active_data(self):
        if self.current_budget not in self.budgets:
            self.budgets[self.current_budget] = {"items": [], "project_blocos": []}
        return self.budgets[self.current_budget]
        
    @property
    def items(self):
        return self.active_data["items"]
        
    @property
    def project_blocos(self):
        return self.active_data["project_blocos"]

    # --- Version Management ---
    def create_budget(self, name, copy_from=None):
        if name in self.budgets: return False
        
        if copy_from and copy_from in self.budgets:
            self.budgets[name] = copy.deepcopy(self.budgets[copy_from])
        else:
            self.budgets[name] = {"items": [], "project_blocos": []}
        
        self.current_budget = name
        self.save()
        return True

    def rename_budget(self, old_name, new_name):
        if old_name not in self.budgets or new_name in self.budgets: return False
        self.budgets[new_name] = self.budgets.pop(old_name)
        if self.current_budget == old_name: self.current_budget = new_name
        self.save()
        return True

    def delete_budget(self, name):
        if name not in self.budgets: return False
        del self.budgets[name]
        if not self.budgets:
            self.budgets["Orçamento Base"] = {"items": [], "project_blocos": []}
            self.current_budget = "Orçamento Base"
        elif self.current_budget == name:
            self.current_budget = list(self.budgets.keys())[0]
        self.save()
        return True

    def set_current_budget(self, name):
        if name in self.budgets:
            self.current_budget = name
            self.save()

    # --- Item Management (Avulsas) ---
    def add_item(self, nome, preco_unitario, quantidade=1):
        found = False
        for item in self.items:
            if item['nome'] == nome:
                item['quantidade'] += quantidade
                found = True
                break
        if not found:
            self.items.append({'nome': nome, 'quantidade': quantidade, 'preco_unitario': preco_unitario})
        self.save()

    def remove_item(self, index):
        if 0 <= index < len(self.items):
            del self.items[index]
            self.save()
            
    def update_item(self, index, quantidade, preco_unitario):
        if 0 <= index < len(self.items):
            self.items[index]['quantidade'] = quantidade
            self.items[index]['preco_unitario'] = preco_unitario
            self.save()

    # --- Bloco Management (No Projeto) ---
    def add_bloco_project(self, nome_bloco, quantidade=1):
        found = False
        for pb in self.project_blocos:
            if pb['nome'] == nome_bloco:
                pb['quantidade'] += quantidade
                found = True
                break
        if not found:
            self.project_blocos.append({'nome': nome_bloco, 'quantidade': quantidade})
        self.save()
        
    def remove_bloco_project(self, index):
        if 0 <= index < len(self.project_blocos):
            del self.project_blocos[index]
            self.save()
            
    def update_bloco_project(self, index, quantidade):
        if 0 <= index < len(self.project_blocos):
            self.project_blocos[index]['quantidade'] = quantidade
            self.save()

    def clear_all(self):
        self.budgets[self.current_budget] = {"items": [], "project_blocos": []}
        self.save()


class ListaMateriaisDialog(QDialog):
    def __init__(self, global_manager, project_manager, bloco_manager, parent=None):
        super().__init__(parent)
        self.global_manager = global_manager
        self.project_manager = project_manager
        self.bloco_manager = bloco_manager
        
        self.setWindowTitle("Aqueduct - Lista de Materiais")
        self.resize(1100, 700)
        
        self.setup_ui()
        self.refresh_budget_combo()
        self.refresh_ui()

    def setup_ui(self):
        layout = QVBoxLayout()
        
        # --- Topo: Versionamento ---
        top_layout = QHBoxLayout()
        top_layout.addWidget(QLabel("<b>Orçamento:</b>"))
        self.combo_budgets = QComboBox()
        self.combo_budgets.currentIndexChanged.connect(self.on_budget_changed)
        top_layout.addWidget(self.combo_budgets, 1)
        
        btn_new = QPushButton("Novo")
        btn_new.clicked.connect(self.on_new)
        btn_ren = QPushButton("Renomear")
        btn_ren.clicked.connect(self.on_rename)
        btn_del = QPushButton("Excluir")
        btn_del.clicked.connect(self.on_delete)
        
        top_layout.addWidget(btn_new)
        top_layout.addWidget(btn_ren)
        top_layout.addWidget(btn_del)
        layout.addLayout(top_layout)
        
        # --- Conteúdo Principal (Splitter) ---
        splitter = QSplitter()
        
        # Lado Esquerdo: Catálogo (Peças e Blocos Disponíveis)
        left_widget = QWidget()
        left_vbox = QVBoxLayout()
        self.tab_catalog = QTabWidget()
        
        # Tab Peças Global
        tab_p = QWidget()
        v_p = QVBoxLayout()
        self.list_global_pecas = QListWidget()
        self.list_global_pecas.setSelectionMode(QAbstractItemView.ExtendedSelection)
        v_p.addWidget(QLabel("Catálogo de Peças"))
        v_p.addWidget(self.list_global_pecas)
        btn_add_p = QPushButton("Adicionar Peça(s) v")
        btn_add_p.clicked.connect(self.on_add_peca_to_project)
        v_p.addWidget(btn_add_p)
        tab_p.setLayout(v_p)
        
        # Tab Blocos Global
        tab_b = QWidget()
        v_b = QVBoxLayout()
        self.list_global_blocos = QListWidget()
        v_b.addWidget(QLabel("Blocos Disponíveis"))
        v_b.addWidget(self.list_global_blocos)
        
        h_b = QHBoxLayout()
        self.spin_add_bloco_qtd = QDoubleSpinBox()
        self.spin_add_bloco_qtd.setValue(1.0)
        self.spin_add_bloco_qtd.setPrefix("Qtd: ")
        
        btn_add_b = QPushButton("Adicionar Bloco v")
        btn_add_b.clicked.connect(self.on_add_bloco_to_project)
        
        h_b.addWidget(self.spin_add_bloco_qtd)
        h_b.addWidget(btn_add_b)
        v_b.addLayout(h_b)
        
        btn_manage = QPushButton("Gerenciar Blocos")
        btn_manage.clicked.connect(self.on_manage_blocos)
        v_b.addWidget(btn_manage)
        
        tab_b.setLayout(v_b)
        
        self.tab_catalog.addTab(tab_p, "Peças")
        self.tab_catalog.addTab(tab_b, "Blocos")
        
        left_vbox.addWidget(self.tab_catalog)
        left_widget.setLayout(left_vbox)
        splitter.addWidget(left_widget)
        
        # Lado Direito: Composição do Projeto
        right_widget = QWidget()
        right_vbox = QVBoxLayout()
        self.tab_project = QTabWidget()
        self.tab_project.currentChanged.connect(self.on_project_tab_changed)
        
        # Tab 1: Itens do Projeto (Editável)
        tab_comp = QWidget()
        v_comp = QVBoxLayout()
        
        # Tabela Blocos Utilizados
        v_comp.addWidget(QLabel("<b>Blocos no Projeto</b>"))
        self.table_proj_blocos = QTableWidget()
        self.table_proj_blocos.setColumnCount(3)
        self.table_proj_blocos.setHorizontalHeaderLabels(["Bloco", "Qtd", "Ações"])
        self.table_proj_blocos.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.table_proj_blocos.cellChanged.connect(self.on_proj_bloco_changed)
        self.table_proj_blocos.cellClicked.connect(self.on_proj_bloco_cell_clicked)
        v_comp.addWidget(self.table_proj_blocos)
        
        # Tabela Peças Avulsas
        v_comp.addWidget(QLabel("<b>Peças Avulsas</b>"))
        self.table_proj_items = QTableWidget()
        self.table_proj_items.setColumnCount(4)
        self.table_proj_items.setHorizontalHeaderLabels(["Peça", "Qtd", "Preço Unit", "Ações"])
        self.table_proj_items.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.table_proj_items.cellChanged.connect(self.on_proj_item_changed)
        self.table_proj_items.cellClicked.connect(self.on_proj_item_cell_clicked)
        v_comp.addWidget(self.table_proj_items)
        
        tab_comp.setLayout(v_comp)
        
        # Tab 2: Orçamento Final (Calculado)
        tab_final = QWidget()
        v_final = QVBoxLayout()
        self.table_final = QTableWidget()
        self.table_final.setColumnCount(4)
        self.table_final.setHorizontalHeaderLabels(["Item", "Qtd Total", "Preço Unit", "Total R$"])
        self.table_final.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        v_final.addWidget(self.table_final)
        
        self.lbl_total_final = QLabel("Total Estimado: R$ 0.00")
        self.lbl_total_final.setStyleSheet("font-size: 14pt; font-weight: bold;")
        v_final.addWidget(self.lbl_total_final)
        
        # Botões da Tab Final
        h_fin = QHBoxLayout()
        btn_update_prices = QPushButton("Atualizar Preços")
        btn_update_prices.clicked.connect(self.on_update_prices)
        btn_csv = QPushButton("Exportar CSV")
        btn_csv.clicked.connect(self.on_export)
        btn_clear = QPushButton("Limpar Tudo")
        btn_clear.setStyleSheet("color: red;")
        btn_clear.clicked.connect(self.on_clear)
        
        h_fin.addWidget(btn_update_prices)
        h_fin.addWidget(btn_clear)
        h_fin.addWidget(btn_csv)
        v_final.addLayout(h_fin)
        
        tab_final.setLayout(v_final)
        
        self.tab_project.addTab(tab_comp, "Composição")
        self.tab_project.addTab(tab_final, "Orçamento Final")
        
        right_vbox.addWidget(self.tab_project)
        right_widget.setLayout(right_vbox)
        splitter.addWidget(right_widget)
        
        # Ajuste proporção splitter
        splitter.setSizes([300, 700])
        layout.addWidget(splitter)
        
        self.setLayout(layout)
        
        self.refresh_catalog_lists()

    # --- Refresh Methods ---
    def refresh_budget_combo(self):
        self.combo_budgets.blockSignals(True)
        self.combo_budgets.clear()
        self.combo_budgets.addItems(list(self.project_manager.budgets.keys()))
        self.combo_budgets.setCurrentText(self.project_manager.current_budget)
        self.combo_budgets.blockSignals(False)

    def refresh_catalog_lists(self):
        self.list_global_pecas.clear()
        self.list_global_pecas.addItems(self.global_manager.list_names())
        
        self.list_global_blocos.clear()
        self.list_global_blocos.addItems(self.bloco_manager.list_names())

    def refresh_ui(self):
        self.refresh_comp_tables()
        if self.tab_project.currentIndex() == 1:
            self.refresh_final_table()

    def refresh_comp_tables(self):
        # 1. Blocos do Projeto
        self.table_proj_blocos.blockSignals(True)
        self.table_proj_blocos.setRowCount(0)
        for i, pb in enumerate(self.project_manager.project_blocos):
            self.table_proj_blocos.insertRow(i)
            
            # Nome (Read-only)
            item_name = QTableWidgetItem(pb['nome'])
            item_name.setFlags(item_name.flags() ^ 2)
            self.table_proj_blocos.setItem(i, 0, item_name)
            
            # Qtd (Editable)
            self.table_proj_blocos.setItem(i, 1, QTableWidgetItem(str(pb['quantidade'])))
            
            # Botão Excluir
            item_del = QTableWidgetItem("X Excluir")
            item_del.setFlags(item_del.flags() ^ 2)  # Read-only
            self.table_proj_blocos.setItem(i, 2, item_del)
            
        self.table_proj_blocos.blockSignals(False)
        
        # 2. Peças Avulsas
        self.table_proj_items.blockSignals(True)
        self.table_proj_items.setRowCount(0)
        for i, item in enumerate(self.project_manager.items):
            self.table_proj_items.insertRow(i)
            
            item_name = QTableWidgetItem(item['nome'])
            item_name.setFlags(item_name.flags() ^ 2)
            self.table_proj_items.setItem(i, 0, item_name)
            
            self.table_proj_items.setItem(i, 1, QTableWidgetItem(str(item['quantidade'])))
            self.table_proj_items.setItem(i, 2, QTableWidgetItem(str(item['preco_unitario'])))
            item_del = QTableWidgetItem("X Excluir")
            item_del.setFlags(item_del.flags() ^ 2)  # Read-only
            self.table_proj_items.setItem(i, 3, item_del)
            
        self.table_proj_items.blockSignals(False)

    def refresh_final_table(self):
        """Calcula a BOM consolidada"""
        consolidated = {} # {nome: {'qtd': 0, 'preco': 0}}
        
        # 1. Somar Avulsas
        for item in self.project_manager.items:
            nome = item['nome']
            if nome not in consolidated:
                consolidated[nome] = {'qtd': 0.0, 'preco': item['preco_unitario']}
            
            consolidated[nome]['qtd'] += item['quantidade']
            # Preço prevalece o último ou maior? Mantem o da lista
            
        # 2. Somar Blocos
        for pb in self.project_manager.project_blocos:
            b_nome = pb['nome']
            b_qtd = pb['quantidade']
            
            # Itens dentro do bloco
            itens_bloco = self.bloco_manager.get(b_nome)
            if itens_bloco:
                for ib in itens_bloco:
                    p_nome = ib['nome']
                    p_qtd = ib['quantidade']
                    
                    total_p_qtd = p_qtd * b_qtd
                    
                    if p_nome not in consolidated:
                        # Buscar preço no catalogo pois bloco não tem preço salvo, é dinâmico
                        peca_data = self.global_manager.get(p_nome)
                        custo = peca_data.get('custo', 0) if peca_data else 0
                        lucro = peca_data.get('lucro', 0) if peca_data else 0
                        preco = custo * (1+lucro/100)
                        
                        consolidated[p_nome] = {'qtd': 0.0, 'preco': preco}
                    
                    consolidated[p_nome]['qtd'] += total_p_qtd

        # Display
        self.table_final.setRowCount(0)
        total_geral = 0.0
        
        row = 0
        for nome, data in sorted(consolidated.items()):
            self.table_final.insertRow(row)
            
            self.table_final.setItem(row, 0, QTableWidgetItem(nome))
            self.table_final.setItem(row, 1, QTableWidgetItem(f"{data['qtd']:.2f}"))
            self.table_final.setItem(row, 2, QTableWidgetItem(f"R$ {data['preco']:.2f}"))
            
            subtotal = data['qtd'] * data['preco']
            total_geral += subtotal
            
            self.table_final.setItem(row, 3, QTableWidgetItem(f"R$ {subtotal:.2f}"))
            row += 1
            
        self.lbl_total_final.setText(f"Total Estimado: R$ {total_geral:.2f}")

    # --- Events ---
    def on_budget_changed(self):
        new = self.combo_budgets.currentText()
        if new:
            self.project_manager.set_current_budget(new)
            self.refresh_ui()

    def on_new(self):
        name, ok = QInputDialog.getText(self, "Novo", "Nome:")
        if ok and name:
            copy_curr = False
            if QMessageBox.question(self, "?", "Copiar dados atuais?", QMessageBox.Yes|QMessageBox.No) == QMessageBox.Yes:
                copy_curr = True
            
            src = self.project_manager.current_budget if copy_curr else None
            if self.project_manager.create_budget(name, src):
                self.refresh_budget_combo()
                self.refresh_ui()
    
    def on_rename(self):
        cur = self.project_manager.current_budget
        new, ok = QInputDialog.getText(self, "Renomear", "Novo nome:", text=cur)
        if ok and new:
            if self.project_manager.rename_budget(cur, new):
                self.refresh_budget_combo()

    def on_delete(self):
        cur = self.project_manager.current_budget
        if QMessageBox.question(self, "Del", f"Excluir '{cur}'?", QMessageBox.Yes|QMessageBox.No) == QMessageBox.Yes:
            self.project_manager.delete_budget(cur)
            self.refresh_budget_combo()
            self.refresh_ui()

    def on_add_peca_to_project(self):
        items = self.list_global_pecas.selectedItems()
        for i in items:
            nome = i.text()
            data = self.global_manager.get(nome)
            preco = 0
            if data:
                preco = data.get('custo',0) * (1 + data.get('lucro',0)/100)
            self.project_manager.add_item(nome, preco, 1)
        self.refresh_ui()

    def on_add_bloco_to_project(self):
        item = self.list_global_blocos.currentItem()
        if item:
            nome = item.text()
            qtd = self.spin_add_bloco_qtd.value()
            self.project_manager.add_bloco_project(nome, qtd)
            self.refresh_ui()

    def on_manage_blocos(self):
        dlg = GerenciarBlocosDialog(self)
        dlg.exec_()
        self.bloco_manager.load()
        self.refresh_catalog_lists()
        # Se blocos mudaram, o total final pode mudar
        if self.tab_project.currentIndex() == 1:
            self.refresh_final_table()

    def on_project_tab_changed(self, index):
        if index == 1:
            self.refresh_final_table()

    def on_update_prices(self):
        # Update avulsas
        count = 0 
        for item in self.project_manager.items:
             data = self.global_manager.get(item['nome'])
             if data:
                 p = data.get('custo',0)*(1+data.get('lucro',0)/100)
                 if abs(item['preco_unitario'] - p) > 0.01:
                     item['preco_unitario'] = p
                     count+=1
        if count > 0:
            self.project_manager.save()
            QMessageBox.information(self,"Ok", f"{count} preços atualizados.")
        self.refresh_final_table() # Recalc blocos prices too

    def on_export(self):
        path, _ = QFileDialog.getSaveFileName(self, "Exportar CSV", "orcamento.csv", "CSV (*.csv)")
        if path:
            try:
                with open(path, 'w', newline='', encoding='utf-8') as f:
                    writer = csv.writer(f, delimiter=';')
                    writer.writerow(["Item", "Qtd", "Preco Unit", "Total"])
                    
                    row_count = self.table_final.rowCount()
                    for r in range(row_count):
                        i = self.table_final.item(r,0).text()
                        q = self.table_final.item(r,1).text()
                        p = self.table_final.item(r,2).text()
                        t = self.table_final.item(r,3).text()
                        writer.writerow([i,q,p,t])
                QMessageBox.information(self,"Ok", "Exportado!")
            except Exception as e:
                QMessageBox.warning(self,"Erro", str(e))
                
    def on_clear(self):
        a = random.randint(1,10)
        b = random.randint(1,10)
        val, ok = QInputDialog.getInt(self, "Segurança", f"{a} + {b} = ?")
        if ok and val == (a+b):
            self.project_manager.clear_all()
            self.refresh_ui()

    def on_proj_bloco_changed(self, row, col):
        if col == 1:  # Alteração de Qtd
            try:
                val = float(self.table_proj_blocos.item(row, col).text())
                self.project_manager.update_bloco_project(row, val)
            except:
                pass

    def on_proj_item_changed(self, row, col):
        # Implementar update qtd (1) e preco (2)
        try:
             q = float(self.table_proj_items.item(row, 1).text())
             p = float(self.table_proj_items.item(row, 2).text())
             self.project_manager.update_item(row, q, p)
        except: pass

    def on_proj_bloco_cell_clicked(self, row, col):
        """Exclui o bloco do projeto ao clicar na coluna de ações (col 2)."""
        if col == 2:
            nome = self.table_proj_blocos.item(row, 0).text()
            resp = QMessageBox.question(
                self, 'Confirmar',
                f'Remover o bloco "{nome}" do projeto?',
                QMessageBox.Yes | QMessageBox.No
            )
            if resp == QMessageBox.Yes:
                self.project_manager.remove_bloco_project(row)
                self.refresh_comp_tables()

    def on_proj_item_cell_clicked(self, row, col):
        """Exclui a peça avulsa do projeto ao clicar na coluna de ações (col 3)."""
        if col == 3:
            nome = self.table_proj_items.item(row, 0).text()
            resp = QMessageBox.question(
                self, 'Confirmar',
                f'Remover a peça "{nome}" do projeto?',
                QMessageBox.Yes | QMessageBox.No
            )
            if resp == QMessageBox.Yes:
                self.project_manager.remove_item(row)
                self.refresh_comp_tables()

class ListaMateriaisTool(AqueductTool):
    def __init__(self, iface, toolbar):
        super().__init__(iface, toolbar)
        self.dlg = None

    def initGui(self):
        icon_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'icons', 'icone_lista_materiais.svg')
        self.action = QAction(QIcon(icon_path), 'Lista de Materiais', self.iface.mainWindow())
        self.action.triggered.connect(self.run)
        
        self.iface.addPluginToMenu('&Aqueduct', self.action)
        
        if self.toolbar:
            self.toolbar.addAction(self.action)
        else:
            self.iface.addToolBarIcon(self.action)
            
    def run(self):
        if self.dlg is None:
            global_mgr = PecaManager()
            project_mgr = ProjectBOMManager()
            bloco_mgr = BlocoManager()
            
            if not project_mgr.filepath:
                QMessageBox.warning(self.iface.mainWindow(), "Aviso", "Salve o projeto QGIS antes de criar uma lista de materiais!")
                return

            self.dlg = ListaMateriaisDialog(global_mgr, project_mgr, bloco_mgr, self.iface.mainWindow())
            self.dlg.finished.connect(self.on_dialog_close)
            self.dlg.setModal(False)
        
        self.dlg.show()
        self.dlg.raise_()
        self.dlg.activateWindow()

    def on_dialog_close(self):
        self.dlg = None
