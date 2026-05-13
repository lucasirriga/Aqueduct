# Habilidades do Plugin Aqueduct para IA

Este documento define o catálogo de ferramentas e capacidades do plugin Aqueduct, servindo como um guia para que agentes de IA possam executar projetos de irrigação de forma autônoma ou assistida.

## 🌟 Objetivo Geral
Transformar dados geográficos e requisitos agronômicos em um projeto de irrigação completo, dimensionado hidraulicamente e com orçamento detalhado.

---

## 🏗️ Fluxo de Trabalho (Workflow) Recomendado

A IA deve seguir esta sequência lógica para um projeto do zero:

1.  **Configuração:** Definir dados do cliente e projeto (`info_projeto`).
2.  **Layout:** Gerar malhas de aspersores ou gotas (`grade_pontos` / `grade_linhas`).
3.  **Cálculo:** Definir vazões por setor e acumular no sistema (`vazao_setor` -> `acumulo_vazao`).
4.  **Bomba:** Selecionar a motobomba adequada pela curva Q-H (`selecionar_bomba`).
5.  **Detalhamento:** Inserir conexões automáticas e rotear comandos (`inserir_reducoes` -> `microtubo_comando`).
6.  **Fechamento:** Listar materiais e serviços para gerar o orçamento final (`lista_materiais` -> `gerar_orcamento`).

---

## 🛠️ Catálogo de Ferramentas (Skills)

### 1. Gestão e Fundamentos
-   **`info_projeto`**: (info_projeto.py) Captura e armazena metadados do projeto (Cliente, Data, Cultura). Essencial para o cabeçalho de relatórios.
-   **`termos_servico`**: (termos_servico.py) Gerencia as cláusulas legais e técnicas que acompanham o orçamento.
-   **`gerenciar_pecas`**: (gerenciar_pecas.py) Interface para cadastrar novos tubos, emissores e acessórios no banco de dados.
-   **`gerenciar_blocos`**: (gerenciar_blocos.py) Permite criar "Kits" ou "Blocos" (ex: Kit de Filtragem) para facilitar a inserção no orçamento.
-   **`somador_selecao`**: (somador_selecao.py) Ferramenta interativa que permite selecionar feições no mapa e somar automaticamente os valores de uma coluna específica (ex: somar comprimento de vários trechos selecionados).

### 2. Design de Layout e Geometria
-   **`grade_linhas`**: (grade_linhas.py) Gera as linhas laterais de irrigação dentro de um polígono com espaçamento definido.
-   **`grade_pontos`**: (grade_pontos.py) Gera a posição exata dos emissores (aspersores/gotejadores).
-   **`grade_poligonos`**: (grade_poligonos.py) Divide uma área maior em parcelas menores (setores).
-   **`recortar_camada`**: (recortar_camada.py) Ferramenta de limpeza para ajustar tubulações aos limites da propriedade.
-   **`calculo_area`**: (calculo_area.py) Atualiza o atributo de área em hectares/m² de camadas de polígono.
-   **`comprimento_linha`**: (comprimento_linha.py) Calcula o comprimento real das tubulações em metros.
-   **`inverter_linha`**: (inverter_linha.py) Inverte o sentido do vetor. Vital para garantir que o fluxo hidráulico flua da fonte para o destino.

### 3. Engenharia Hidráulica
-   **`vazao_setor`**: (vazao_setor.py) Atribui a vazão necessária (m³/h) a um polígono de setor baseado na lâmina de irrigação.
-   **`acumulo_vazao`**: (acumulo_vazao.py) **Cérebro do plugin**. Percorre a rede, soma vazões, calcula perdas de carga e seleciona diâmetros (DN).
-   **`calculo_hf`**: (calculo_hf.py) Calculadora rápida para perdas de carga pontuais usando Hazen-Williams.
-   **`atribuir_vazao`**: (atribuir_vazao.py) Permite ajuste manual da vazão em trechos específicos para cenários atípicos.
-   **`atribuir_dn`**: (atribuir_dn.py) Permite fixar ou alterar manualmente o diâmetro de um tubo após o cálculo automático.
-   **`dimensionar_tubulacao`**: (dimensionar_tubulacao.py) Dimensiona uma tubulação selecionada em trechos, detectando mangueiras conectadas, acumulando vazões dos emissores e selecionando diâmetros por Hazen-Williams respeitando a perda de carga máxima informada.
-   **`selecionar_bomba`**: (selecionar_bomba.py) Lê a vazão do projeto em `dados_projeto.json`, solicita a pressão pretendida e busca modelos compatíveis no banco de dados (`data/bomba_database.json`). Exibe lista de modelos com gráfico interativo da curva Q-H e ponto de operação do projeto. Permite cadastrar o modelo escolhido nas Peças e adicioná-lo ao orçamento.

### 4. Conexões e Automação
-   **`inserir_reducoes`**: (inserir_reducoes.py) Identifica mudanças de diâmetro e insere automaticamente a peça de redução correspondente.
-   **`microtubo_comando`**: (microtubo_comando.py) Roteia tubos de pequena bitola para automação, utilizando algoritmos de caminho mínimo.

### 5. Quantitativo e Orçamento
-   **`contabilizar_tubos`**: (contabilizar_tubos.py) Soma as metragens de tubos, distinguindo entre barras (6m) e rolos (mangueiras).
-   **`contabilizar_materiais`**: (contabilizar_materiais.py) Gera a lista total de componentes para o projeto.
-   **`lista_materials`**: (lista_materiais.py) Interface final para revisão do usuário antes da exportação.
-   **`gerenciar_servicos`**: (gerenciar_servicos.py) Adiciona itens não materiais (instalação, frete, escavação).
-   **`analise_lucro`**: (analise_lucro.py) Proporciona uma visão financeira detalhada, mostrando lucro unitário, margem e impacto de cada item no orçamento total.
-   **`gerar_orcamento`**: (gerar_orcamento.py) Gera o documento PDF final com Tabelas de Materiais, Serviços e 2 Mapas (Satélite e Técnico).
-   **`gerar_relatorio_tecnico`**: (gerar_relatorio_tecnico.py) Gera o documento PDF com a Lista de Materiais e Serviços apenas com descrições e quantidades, sem valores financeiros, incluindo os 2 Mapas.

### 6. Visualização (Simbologia)
-   **`simbologia_dn`**: (simbologia_dn.py) Aplica cores padronizadas baseadas no diâmetro (ex: 20mm=Cinza, 50mm=Azul).
-   **`simbologia_vazao`**: (simbologia_vazao.py) Gradiente de cores baseado no volume de água.
-   **`simbologia_direcao`**: (simbologia_direcao.py) Adiciona setas de fluxo para auditoria rápida do sentido da água.
-   **`simbologia_hf`**: (simbologia_hf.py) Gradiente de cores (Laranjas) baseado na perda de carga unitária (HF) dos trechos.
-   **`simbologia_emissores`**: (simbologia_emissores.py) Aplica cor vermelha e tamanho reduzido (0.4) para destacar pontos de emissão.
-   **`simbologia_setores`**: (simbologia_setores.py) Define polígonos com contorno preto fino (0.16) e preenchimento transparente para visualização de setores.

---

## ⚠️ Restrições e Regras para a IA
-   **Direção do Fluxo:** Sempre verifique se as linhas estão desenhadas no sentido do fluxo antes de rodar o `acumulo_vazao`. Use `simbologia_direcao` para validar.
-   **Topologia:** As tubulações devem estar conectadas (snapped) para que o cálculo de rede funcione.
-   **Unidades:** Vazões em **m³/h**, Diâmetros em **mm**, Áreas em **ha**, Comprimentos em **m**.
