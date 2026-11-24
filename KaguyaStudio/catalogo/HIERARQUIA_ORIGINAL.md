# Hierarquia dos subagentes

72 agents em 3 projetos. Hierarquia lida das descrições de cada agent e do fluxo do CLAUDE.md, não conferida chamada por chamada.

## NarutoCD (32)

### Coordenação

- `narutocd-coordenador`: Recebe a tarefa, escolhe os agents e junta os resultados.
  - `narutocd-auxiliar-logs`: Lê o log de teste e extrai erros e marcas da sessão.
  - `narutocd-auxiliar-versao`: Confere se a versão do mod é a mesma em todos os arquivos.
  - `narutocd-auxiliar-planejamento`: Transforma pedidos em etapas pequenas, com teste de cada uma.
  - `narutocd-explorador`: Encontra onde uma classe ou mecânica é usada, sem alterar.
  - `narutocd-revisor`: Revisa alterações de código antes de dar por concluídas.
  - `narutocd-juiz`: Dá o veredito: aprovada, reprovada ou pendente.
  - `narutocd-registro`: Registra o que foi feito no segundo cérebro.
  - `narutocd-categorizador`: Põe área, tipo e estado nas notas do projeto.
  - `narutocd-integrador-cerebro`: Liga as notas do projeto aos arquivos de código.
  - `narutocd-organizador`: Organiza a pasta do projeto. Só move com aprovação.

### Criação de personagem

- `narutocd-criacao-dev`: Implementa a tela de criação de personagem, uma etapa por vez.
- `narutocd-criacao-visual`: Analisa capturas da criação e aponta problemas de layout.
- `narutocd-criacao-fluxo`: Confere a ordem das telas e o envio ao servidor.

### Qualidade e dependências

- `narutocd-caca-erros-codigo`: Procura erros de lógica, nulos e uso de API errado. Não corrige.
- `narutocd-caca-erros-dev`: Procura versões divergentes, configurações faltando e disco cheio.
- `narutocd-deps-analista`: Lê os jars dos mods dependentes e diz como cada parte funciona.
- `narutocd-deps-api`: Confere se cada uso de dependência existe na versão instalada.

### Pesquisa e referências

- `narutocd-curador-referencias`: Organiza as referências das pesquisas e envia ao juiz.
  - `narutocd-juiz-referencias`: Julga licença, origem e relevância de cada referência.
  - `narutocd-pesquisa-mods`: Pesquisa como desenvolver mods 1.7.10 com Forge.
  - `narutocd-pesquisa-paineis`: Pesquisa telas e painéis de interface.
  - `narutocd-pesquisa-sons`: Pesquisa sons e trilhas, conferindo a licença antes.
  - `narutocd-pesquisa-texturas`: Pesquisa referências e técnicas de textura para o jogo.
  - `narutocd-pesquisa-entidades`: Pesquisa mobs e NPCs com Forge e GeckoLib.
  - `narutocd-pesquisa-efeitos-vfx`: Pesquisa partículas e efeitos visuais em 1.7.10.
  - `narutocd-pesquisa-referencias`: Pesquisa referências visuais de jogos e mods ninja.

### Imagens com IA

- `narutocd-imagem-ia-prompt`: Escreve briefings para o gerador e confere o resultado.
- `narutocd-imagem-ia-gerador`: Gera imagem com o Higgsfield. Pede aprovação do custo antes.
- `narutocd-imagem-ia-gravyx`: Gera imagem pelo Gravyx. Confere saldo e pede aprovação.
- `narutocd-imagem-ia-gratis`: Gera rascunho pelo Pollinations, sem custo e com marca d'água.
- `narutocd-imagem-ia-processador`: Recorta, aplica transparência e ajusta tamanho e paleta.

## Roupas (Blockbench) (32)

### Planejamento

- `blockbench-planejador`: Monta o plano da peça: etapas, responsável e critério de aceite.
- `blockbench-planejador-auxiliar`: Diz qual agent age agora no fluxo de uma peça.
- `blockbench-planejador-itens`: Planeja itens e armas, com portão de aprovação.
- `blockbench-planejador-entidades`: Planeja mobs e NPCs do Bedrock.
- `blockbench-planejador-comidas`: Planeja comidas com ícone 2D ou modelo pequeno.
- `blockbench-planejador-efeitos`: Planeja efeitos visuais e sonoros de Bedrock.

### Pesquisa e aprendizado

- `blockbench-pesquisador`: Pesquisa Blockbench, Bedrock e GeckoLib e grava resumos próprios.
- `blockbench-buscador-referencias`: Procura referências visuais e tutoriais de pintura e modelagem.
- `blockbench-aprendiz-modelagem`: Aprende modelagem e textura e grava resumos próprios.
- `blockbench-aprendiz-texturas`: Estuda paleta, sombra e costuras dos mods de referência.
- `blockbench-aprendiz-pintura`: Estuda técnicas e ferramentas de pintura para o texturizador.
- `blockbench-referencias`: Mede armaduras de referência: espessura, UV, pivôs e cubos.
- `blockbench-pesquisador-segundo-cerebro`: Procura no Segundo Cérebro o material útil para a modelagem.

### Modelagem (G1)

- `blockbench-modelador`: Modela a roupa no Blockbench, com UV e nomes de ossos armor*.
- `blockbench-revisor`: Revisa interseções, espessura, UV e cubos de 0 a 1 pixel.

### Textura (G2)

- `blockbench-coordenador-textura`: Prepara a pintura: resolução, paleta, ordem e template UV.
  - `blockbench-texturizador`: Pinta a textura da peça com paleta e sombra.
    - `blockbench-editor-externo`: Faz passadas em PNG com Pillow e GIMP, sem tocar na geometria.
- `blockbench-resolucao`: Escolhe a resolução da textura antes de pintar.

### Comparação e fotos

- `blockbench-comparador-exemplos`: Compara lado, frente e proporção com o exemplo aprovado.
- `blockbench-analisador-elementos`: Compara peça a peça, osso a osso, com o exemplo.
- `blockbench-analisador-textura`: Varre a textura pixel a pixel e aponta cada problema.
- `blockbench-mostrador`: Gera as fotos de projeção e o pacote para os juízes.

### Portão de aprovação (G3)

- `blockbench-juiz`: Veredito geral da peça. Só aprova com foto lado a lado.
  - `blockbench-juiz-geometria`: Aprova ou reprova só a geometria.
  - `blockbench-juiz-textura`: Aprova ou reprova só a textura.
  - `blockbench-juiz-processo`: Confere se o fluxo obrigatório foi seguido.
  - `blockbench-juiz-solucoes`: Transforma reprovações em tarefas para cada agent.

### Segundo Cérebro (roupas)

- `blockbench-sc-gestor`: Leva ao projeto de roupas as informações novas do vault.
- `blockbench-sc-organizador`: Organiza o vault e cria funções novas, registrando cada mudança.
- `blockbench-sc-registro`: Registra erros, progresso e acertos das roupas.
- `blockbench-sc-relator`: Lê os registros e diz o que deu certo e o que deu errado.

## Segundo Cérebro (8)

### Vault geral

- `sc-memoria`: Grava decisões, fatos e relatórios na memória do vault.
- `sc-tarefas`: Gerencia as tarefas em tasks/todo.md.
- `sc-categorizador`: Propõe tags, tipo e pasta para as notas.
- `sc-canvas`: Cria canvas do Obsidian para visualizar estruturas.
- `sc-planilha`: Cria e confere planilhas CSV e XLSX.
- `sc-plugins-obsidian`: Avalia plugins da comunidade do Obsidian. Não instala.
- `sc-sugerir-plugins`: Sugere a melhor ferramenta para uma tarefa do vault.
- `sc-usar-plugins`: Usa os plugins já instalados para tarefas do vault.
