import os
import json
from qgis.PyQt.QtCore import Qt, QVariant, QThread, pyqtSignal, QObject
from qgis.PyQt.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QTextBrowser, QLineEdit, 
    QPushButton, QLabel, QDockWidget, QAction, QMessageBox,
    QPlainTextEdit, QDialog, QDialogButtonBox
)
from qgis.PyQt.QtGui import QIcon, QFont
from qgis.core import QgsProject

from .ferramenta_base import AqueductTool
from .gerenciar_pecas import PecaManager
from .gerenciar_servicos import ServicoManager

# ---------------------------------------------------------------------------
class RobsonMemoryManager:
    """Gerencia a persistência da memória global e local do Robson."""
    
    def __init__(self, plugin_dir):
        self.plugin_dir = plugin_dir
        self.global_path = os.path.join(plugin_dir, "memoria_global_robson.json")
        self.global_memory = self._load(self.global_path)

    def _load(self, path):
        if os.path.exists(path):
            try:
                with open(path, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except:
                return {"preferencias": [], "aprendizados": []}
        return {"preferencias": [], "aprendizados": []}

    def save_global(self, data):
        self.global_memory = data
        with open(self.global_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=4, ensure_ascii=False)

    def get_project_memory_path(self):
        project_path = QgsProject.instance().fileName()
        if not project_path:
            return None
        return project_path.replace(".qgz", "_nei.json").replace(".qgs", "_nei.json")

    def load_project_memory(self):
        path = self.get_project_memory_path()
        if path and os.path.exists(path):
            try:
                with open(path, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except:
                return {"progresso": [], "notas": []}
        return {"progresso": [], "notas": []}

    def save_project_memory(self, data):
        path = self.get_project_memory_path()
        if path:
            with open(path, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=4, ensure_ascii=False)

# ---------------------------------------------------------------------------
class EditMemoryDialog(QDialog):
    """Dialogo simples para edicao manual da memoria global."""
    def __init__(self, manager, parent=None):
        super().__init__(parent)
        self.manager = manager
        self.setWindowTitle("Editar Memória Global - Robson")
        self.resize(500, 400)
        
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("Conteúdo da Memória Global (JSON):"))
        
        self.editor = QPlainTextEdit()
        curr_data = json.dumps(self.manager.global_memory, indent=4, ensure_ascii=False)
        self.editor.setPlainText(curr_data)
        layout.addWidget(self.editor)
        
        btns = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        btns.accepted.connect(self.accept)
        btns.rejected.connect(self.reject)
        layout.addWidget(btns)

    def get_data(self):
        try:
            return json.loads(self.editor.toPlainText())
        except Exception as e:
            QMessageBox.critical(self, "Erro", f"JSON Inválido: {e}")
            return None

# ---------------------------------------------------------------------------
class GemmaWorker(QThread):
    """Thread para comunicacao com LM Studio (Gemma 3 1B)."""
    finished = pyqtSignal(str)
    error = pyqtSignal(str)

    def __init__(self, prompt, context):
        super().__init__()
        self.prompt = prompt
        self.context = context
        self.url = "http://localhost:1234/v1/chat/completions"

    def run(self):
        import requests
        try:
            payload = {
                "model": "qwen2.5-coder-0.5b-instruct",
                "messages": [
                    {"role": "system", "content": self.context},
                    {"role": "user", "content": self.prompt}
                ],
                "temperature": 0.7
            }
            print(f"Robson: Enviando requisição para {self.url} usando modelo {payload['model']}...")
            response = requests.post(self.url, json=payload, timeout=60)
            if response.status_code == 200:
                text = response.json()['choices'][0]['message']['content']
                self.finished.emit(text)
            else:
                error_msg = response.text
                print(f"Robson: Erro do servidor (Status {response.status_code}): {error_msg}")
                self.error.emit(f"Servidor retornou erro {response.status_code}: {error_msg[:100]}")
                self.error.emit(f"Servidor retornou erro {response.status_code}")
        except Exception as e:
            self.error.emit(str(e))

# ---------------------------------------------------------------------------
class RobsonChatDock(QDockWidget):
    """Painel lateral do Assistente Robson."""
    def __init__(self, iface, manager, parent=None):
        super().__init__("Assistente Robson", parent)
        self.iface = iface
        self.manager = manager
        self.setObjectName("RobsonChatDock")
        self.tool_registry = {}
        self.pending_action = None # Armazena ação aguardando confirmação
        
        container = QWidget()
        layout = QVBoxLayout(container)
        
        # Area de conversa
        self.browser = QTextBrowser()
        self.browser.setOpenExternalLinks(False) # Capturamos anchorClicked
        self.browser.anchorClicked.connect(self._link_clicked)
        self.browser.setHtml("<p style='color: gray;'>Olá! Eu sou o <b>Robson</b>. Como posso ajudar com seu projeto de irrigação hoje?</p>")
        layout.addWidget(self.browser)
        
        # Entrada de texto
        input_row = QHBoxLayout()
        self.input = QLineEdit()
        self.input.setPlaceholderText("Pergunte ao Robson...")
        self.input.returnPressed.connect(self._enviar)
        input_row.addWidget(self.input)
        
        btn_send = QPushButton("Enviar")
        btn_send.clicked.connect(self._enviar)
        input_row.addWidget(btn_send)
        layout.addLayout(input_row)
        
        # Rodape com ferramentas
        footer = QHBoxLayout()
        btn_mem = QPushButton("⚙️ Memória Global")
        btn_mem.setFlat(True)
        btn_mem.clicked.connect(self._edit_memory)
        footer.addWidget(btn_mem)
        footer.addStretch()
        layout.addLayout(footer)
        
        self.setWidget(container)
        self.worker = None

    def _enviar(self):
        text = self.input.text().strip()
        if not text: return
        
        self.browser.append(f"<p align='right'><b>Você:</b> {text}</p>")
        self.input.clear()
        self.input.setEnabled(False)
        
        # Preparar contexto
        context = self._get_full_context()
        
        self.worker = GemmaWorker(text, context)
        self.worker.finished.connect(self._on_nei_response)
        self.worker.error.connect(self._on_nei_error)
        self.worker.start()

    def _get_project_summary(self):
        """Coleta métricas reais do projeto do QGIS."""
        summary = {
            "camadas": [l.name() for l in QgsProject.instance().mapLayers().values()],
            "projeto_arquivo": QgsProject.instance().fileName() or "Não salvo",
            "totais": {}
        }
        
        try:
            peca_mgr = PecaManager()
            summary["banco_pecas"] = peca_mgr.pecas
            servico_mgr = ServicoManager()
            summary["banco_servicos"] = servico_mgr.servicos
        except:
            pass
        
        # Tenta pegar totais de tubulação se a camada existir
        top_layer = QgsProject.instance().mapLayersByName("Topologia")
        if top_layer:
            layer = top_layer[0]
            summary["totais"]["segmentos"] = layer.featureCount()
            if "dn" in [f.name().lower() for f in layer.fields()]:
                idx = layer.fields().indexFromName("dn")
                dns = {}
                for f in layer.getFeatures():
                    v = f.attributes()[idx]
                    dns[v] = dns.get(v, 0) + f.geometry().length()
                summary["totais"]["distribuicao_dn"] = {str(k): f"{v:.2f}m" for k, v in dns.items()}

        return summary

    def _get_full_context(self):
        # 1. Identidade e Habilidades
        hab_path = os.path.join(self.manager.plugin_dir, "HABILIDADES_AQUEDUCT.md")
        habilidades = ""
        if os.path.exists(hab_path):
            with open(hab_path, 'r', encoding='utf-8') as f:
                habilidades = f.read()
        
        # 2. Memoria Global
        global_m = json.dumps(self.manager.global_memory, ensure_ascii=False)
        
        # 3. Memoria Projeto (Notas salvas)
        projeto_notas = self.manager.load_project_memory()
        
        # 4. Contexto Geométrico/Real
        real_context = self._get_project_summary()
        
        template = """
Você é o Robson, assistente especializado do plugin Aqueduct.
Seu objetivo é guiar o usuário no projeto de irrigação.

CAPACIDADES (FERRAMENTAS):
{habilidades}

NOVA CAPACIDADE (Banco de Dados):
Você pode ler e editar o banco de dados de Peças e Serviços.
- Para adicionar/atualizar peça: [EXECUTE: atualizar_peca, {"nome": "Tubo PVC...", "custo": 10.5, "lucro": 30.0}]
- Para remover peça: [EXECUTE: remover_peca, {"nome": "Tubo PVC..."}]
- Para adicionar/atualizar serviço: [EXECUTE: atualizar_servico, {"descricao": "Escavação...", "custo": 50.0, "lucro": 20.0}]
- Para remover serviço: [EXECUTE: remover_servico, {"descricao": "Escavação..."}]

PREFERÊNCIAS GLOBAIS (O QUE VOCÊ APRENDEU SOBRE O USUÁRIO):
{global_m}

ESTADO ATUAL DO PROJETO E BANCO DE DADOS:
{real_context}

NOTAS ESPECÍFICAS DESTE PROJETO:
{projeto_notas}

Instruções Cruciais:
1. Responda em Português Brasil.
2. Seja EXTREMAMENTE conciso (máximo 2 sentenças).
3. Se precisar agir, use SEMPRE no final da resposta: [EXECUTE: id, {{"param": val}}]
   Exemplos de IDs: acumulo_vazao, atualizar_peca, grade_linhas.
"""
        system = template.replace("{habilidades}", habilidades) \
                         .replace("{global_m}", global_m) \
                         .replace("{real_context}", json.dumps(real_context, ensure_ascii=False)) \
                         .replace("{projeto_notas}", json.dumps(projeto_notas, ensure_ascii=False))
        return system

    def _on_nei_response(self, text):
        # 1. Extrair Tags de Memória
        import re
        
        # Global
        m_global = re.findall(r"\[MEMORIA_GLOBAL:\s*(.*?)\]", text)
        for entry in m_global:
            if entry not in self.manager.global_memory["aprendizados"]:
                self.manager.global_memory["aprendizados"].append(entry)
                self.manager.save_global(self.manager.global_memory)
        
        # Projeto
        m_proj = re.findall(r"\[MEMORIA_PROJETO:\s*(.*?)\]", text)
        if m_proj:
            p_mem = self.manager.load_project_memory()
            for entry in m_proj:
                if entry not in p_mem["notas"]:
                    p_mem["notas"].append(entry)
            self.manager.save_project_memory(p_mem)

        # 2. Limpar tags do texto exibido
        clean_text = re.sub(r"\[MEMORIA_.*?\]", "", text)
        
        # 3. Processar EXECUTE (Regex robusta com re.DOTALL para JSON multi-linha)
        exe_match = re.search(r"\[EXECUTE:\s*([\w_]+)\s*,\s*(\{.*?\})\]", text, re.DOTALL)
        if exe_match:
            tool_id = exe_match.group(1).strip()
            params_json = exe_match.group(2).strip()
            try:
                params = json.loads(params_json)
                self._handle_execution(tool_id, params)
                # Remove a tag para não poluir o chat
                clean_text = re.sub(r"\[EXECUTE:.*?\]", "", clean_text, flags=re.DOTALL)
            except Exception as e:
                print(f"Robson Parser Error: {e} | JSON: {params_json}")
                self.browser.append(f"<p style='color: red;'><i>(Erro ao processar parâmetros: {e})</i></p>")
        
        self.browser.append(f"<p><b>Robson:</b> {clean_text}</p>")
        self.input.setEnabled(True)
        self.input.setFocus()

    def _handle_execution(self, tool_id, params):
        db_commands = ["atualizar_peca", "remover_peca", "atualizar_servico", "remover_servico"]
        if tool_id in db_commands:
            self.pending_action = (tool_id, params)
            self.browser.append(
                f"<div style='background: #fff3e0; padding: 10px; border-radius: 5px;'>"
                f"<b>⚠️ Ação no Banco de Dados:</b> O Robson quer executar <b>{tool_id}</b>.<br><br>"
                f"<a href='action:confirm' style='background: #4caf50; color: white; padding: 5px; text-decoration: none;'>✅ Confirmar</a> &nbsp; "
                f"<a href='action:cancel' style='background: #f44336; color: white; padding: 5px; text-decoration: none;'>❌ Cancelar</a>"
                f"</div>"
            )
            return

        if tool_id not in self.tool_registry:
            self.browser.append(f"<p style='color: orange;'>⚠️ Ferramenta '{tool_id}' não encontrada no registro.</p>")
            return
            
        tool = self.tool_registry[tool_id]
        
        if tool.is_destructive():
            # Ação permanente: Pede confirmação
            self.pending_action = (tool_id, params)
            self.browser.append(
                f"<div style='background: #fff3e0; padding: 10px; border-radius: 5px;'>"
                f"<b>⚠️ Ação Permanente:</b> O Robson quer alterar dados em <b>{tool_id}</b>.<br><br>"
                f"<a href='action:confirm' style='background: #4caf50; color: white; padding: 5px; text-decoration: none;'>✅ Confirmar</a> &nbsp; "
                f"<a href='action:cancel' style='background: #f44336; color: white; padding: 5px; text-decoration: none;'>❌ Cancelar</a>"
                f"</div>"
            )
        else:
            # Ação segura: Executa direto
            self.browser.append(f"<p style='color: blue;'>⚙️ Executando {tool_id} automaticamente...</p>")
            try:
                tool.run_automated(params)
                self.browser.append(f"<p style='color: green;'>✅ Concluído.</p>")
            except Exception as e:
                self.browser.append(f"<p style='color: red;'>❌ Erro na execução: {e}</p>")

    def _link_clicked(self, url):
        link = url.toString()
        if link == "action:confirm":
            if self.pending_action:
                tool_id, params = self.pending_action
                self.pending_action = None
                self.browser.append(f"<p style='color: blue;'>⚙️ Confirmado. Executando {tool_id}...</p>")
                
                db_commands = ["atualizar_peca", "remover_peca", "atualizar_servico", "remover_servico"]
                if tool_id in db_commands:
                    try:
                        if tool_id == "atualizar_peca":
                            PecaManager().add_update(params.get("nome"), {"custo": float(params.get("custo", 0)), "lucro": float(params.get("lucro", 30))})
                        elif tool_id == "remover_peca":
                            PecaManager().remove(params.get("nome"))
                        elif tool_id == "atualizar_servico":
                            c = float(params.get("custo", 0))
                            l = float(params.get("lucro", 20))
                            ServicoManager().add_update(params.get("descricao"), {"custo": c, "lucro": l, "valor": c * (1 + l/100)})
                        elif tool_id == "remover_servico":
                            ServicoManager().remove(params.get("descricao"))
                        self.browser.append(f"<p style='color: green;'>✅ Banco de dados atualizado com sucesso.</p>")
                    except Exception as e:
                        self.browser.append(f"<p style='color: red;'>❌ Erro no banco de dados: {e}</p>")
                    return

                try:
                    self.tool_registry[tool_id].run_automated(params)
                    self.browser.append(f"<p style='color: green;'>✅ Concluído com sucesso.</p>")
                except Exception as e:
                    self.browser.append(f"<p style='color: red;'>❌ Erro: {e}</p>")
        elif link == "action:cancel":
            self.pending_action = None
            self.browser.append("<p style='color: gray;'>🚫 Ação cancelada pelo usuário.</p>")

    def set_tool_registry(self, registry):
        self.tool_registry = registry


    def _on_nei_error(self, err):
        self.browser.append(f"<p style='color: red;'><b>Erro:</b> Não consegui falar com o LM Studio. Verifique se ele está rodando em localhost:1234. ({err})</p>")
        self.input.setEnabled(True)

    def _edit_memory(self):
        dlg = EditMemoryDialog(self.manager, self)
        if dlg.exec_():
            new_data = dlg.get_data()
            if new_data:
                self.manager.save_global(new_data)
                QMessageBox.information(self, "Sucesso", "Memória Global atualizada.")

# ---------------------------------------------------------------------------
class AssistenteRobsonTool(AqueductTool):
    """Ferramenta que ativa o painel do Assistente Robson."""
    
    def __init__(self, iface, toolbar=None):
        super().__init__(iface, toolbar)
        self.manager = RobsonMemoryManager(os.path.dirname(os.path.dirname(__file__)))
        self.dock = None
        self.tool_registry = {}

    def set_tool_registry(self, registry):
        self.tool_registry = registry
        if self.dock:
            self.dock.set_tool_registry(registry)

    def initGui(self):
        icon_path = os.path.join(
            os.path.dirname(os.path.dirname(__file__)), 'icons', 'icone_assistente_robson.svg')
        # Placeholder se não existir
        if not os.path.exists(icon_path): icon_path = ""
        
        self.action = QAction(QIcon(icon_path), "Assistente Robson", self.iface.mainWindow())
        self.action.triggered.connect(self.run)
        self.iface.addPluginToMenu('&Aqueduct', self.action)
        self.iface.addToolBarIcon(self.action)

    def run(self):
        if not self.dock:
            self.dock = RobsonChatDock(self.iface, self.manager, self.iface.mainWindow())
            self.dock.set_tool_registry(self.tool_registry)
        
        self.iface.addDockWidget(Qt.RightDockWidgetArea, self.dock)
        self.dock.show()
