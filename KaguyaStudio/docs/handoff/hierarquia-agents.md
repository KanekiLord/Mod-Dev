# Hierarquia dos agents (NarutoCD, Blockbench, Segundo Cérebro)

Versão em texto para ler em qualquer ferramenta, inclusive o Codex. São 72 agents em três famílias. A hierarquia mostra quem delega a quem. Grupos são só organização, não agents.

Tipos:
- **coord**: coordena e delega
- **juiz**: aprova ou reprova com evidência, sem alterar o que avalia
- **leitura**: analisa, mede ou confere, sem alterar arquivos do projeto
- **grava**: escreve código, notas, planos ou índices
- **gera**: gera imagem com IA (pode gastar créditos; pede aprovação)
- **pesquisa**: busca e resume fontes na web

Fontes e limites: a estrutura veio das descrições dos agents carregados na sessão de 23/11/2026. As ferramentas exatas de cada agent não estão aqui. A hierarquia do Blockbench e do vault é inferida das descrições. Ficaram de fora os agents embutidos do Claude Code, os de plugins de terceiros e os de modernização de código.

---

## 1. Mod NarutoCD (32 agents)

```
narutocd-coordenador [coord] — recebe a tarefa, escolhe os agents, junta resultados, dá a resposta final
├── Auxiliares — estado atual antes de mexer
│   ├── narutocd-auxiliar-versao [leitura] — confere a versão em build.gradle, NarutoCD.java, mcmod.info, jar de teste e vault
│   ├── narutocd-auxiliar-logs [leitura] — lê o log do jogo e a lista de mods; extrai erros e marcas [NarutoCD]
│   └── narutocd-auxiliar-planejamento [grava] — transforma o pedido em etapas com critério de aceite; não edita código
├── Fluxo de alteração de código — depois da mudança, nesta ordem
│   ├── narutocd-explorador [leitura] — acha onde uma classe, método ou mecânica é usada
│   ├── narutocd-revisor [leitura] — revisa o diff (lógica, compatibilidade com Naruto C, JRMCore e Destination)
│   ├── narutocd-juiz [juiz] — veredito (aprovada, reprovada ou pendente) pelo critério de aceite e evidências
│   ├── narutocd-registro [grava] — grava no vault o que foi feito, versão, pendências e erros
│   ├── narutocd-categorizador [grava] — propõe e aplica tags por área, tipo e estado
│   ├── narutocd-integrador-cerebro [grava] — liga a nota do projeto aos arquivos; mantém índice e links
│   └── narutocd-organizador [grava] — acha arquivos soltos e duplicados; move só com aprovação
├── Erros — varreduras que só encontram e descrevem
│   ├── narutocd-caca-erros-codigo [leitura] — erros de lógica, nulos, índices, cliente e servidor, log excessivo
│   └── narutocd-caca-erros-dev [leitura] — versões divergentes, configuração faltando, disco C: baixo
├── Painel de criação — tela de criação de personagem
│   ├── narutocd-criacao-dev [grava] — implementa e corrige a tela, uma etapa por vez, a partir de um plano
│   ├── narutocd-criacao-visual [leitura] — analisa capturas: posição, texto cortado, contraste, sobreposição
│   └── narutocd-criacao-fluxo [leitura] — confere a ordem das telas e o que é enviado ao servidor
├── Imagem com IA — briefing, depois gerador, depois processamento; geração só com aprovação
│   ├── narutocd-imagem-ia-prompt [grava] — escreve o briefing a partir das referências; confere o resultado
│   ├── narutocd-imagem-ia-gerador [gera] — gera com o CLI do Higgsfield; consulta o custo antes
│   ├── narutocd-imagem-ia-gravyx [gera] — gera com o conector Gravyx; confere o saldo de tokens antes
│   ├── narutocd-imagem-ia-gratis [gera] — gera com Pollinations; gratuito, com marca d'água
│   └── narutocd-imagem-ia-processador [grava] — recorte, transparência, tamanhos e paleta; nunca sobrescreve o original
├── Dependências — Naruto C, JRMCore, JBRA, Destination, CustomNPC+, GeckoLib
│   ├── narutocd-deps-analista [leitura] — lê os jars com javap e entrega fatos sobre classes e métodos
│   └── narutocd-deps-api [leitura] — confere se os usos do NarutoCD existem na versão instalada
├── Pesquisa na web — cada um grava em .claude/pesquisa/<área>/
│   ├── narutocd-pesquisa-mods [pesquisa] — desenvolvimento de mod 1.7.10: eventos, GUI, rede, registro
│   ├── narutocd-pesquisa-paineis [pesquisa] — layout e interação de telas e criação de personagem
│   ├── narutocd-pesquisa-sons [pesquisa] — fontes de som com licença verificada; não baixa sem aprovação
│   ├── narutocd-pesquisa-texturas [pesquisa] — referências de textura para itens e blocos, com licença
│   ├── narutocd-pesquisa-entidades [pesquisa] — mobs e NPCs com Forge e GeckoLib
│   ├── narutocd-pesquisa-efeitos-vfx [pesquisa] — partículas, brilho e feixes, sem shaders
│   └── narutocd-pesquisa-referencias [pesquisa] — referências visuais de jogos e mods de ninja e anime
└── Referências — só o que o juiz aprova entra na fila de uso
    ├── narutocd-curador-referencias [grava] — organiza as pesquisas e envia ao juiz; não chama outros agents
    └── narutocd-juiz-referencias [juiz] — julga licença, origem, data e se o resumo confere com a fonte
```

---

## 2. Blockbench, roupas (32 agents)

```
Blockbench — três ciclos: modelagem, textura e aprovação; um portão de juízes fecha cada peça
├── Portão de aprovação — o juiz principal só aprova com os três auxiliares
│   ├── blockbench-juiz [juiz] — avaliação profunda de geometria, textura e processo; veredito com evidências
│   │   ├── blockbench-juiz-geometria [juiz] — ossos, pivôs, espessura de camada, interseções, UV de cubo
│   │   ├── blockbench-juiz-textura [juiz] — resolução em relação ao UV, paleta, sombra, face escura, detalhe
│   │   └── blockbench-juiz-processo [juiz] — confere se a peça seguiu o fluxo obrigatório antes da entrega
│   └── blockbench-juiz-solucoes [grava] — transforma reprovações em tarefas concretas para cada agent
├── Textura — prepara, pinta e ajusta a resolução
│   └── blockbench-coordenador-textura [coord] — define resolução, paleta e ordem de pintura; exporta o template UV
│       ├── blockbench-texturizador [grava] — pinta a textura (64, 128 ou 256) com paleta, sombra e detalhe
│       │   └── blockbench-editor-externo [grava] — passadas em PNG com Pillow e GIMP; não mexe na geometria
│       └── blockbench-resolucao [grava] — escolhe e ajusta a resolução da textura antes de pintar
├── Modelagem — cria a geometria e a revisa
│   └── blockbench-modelador [grava] — cria e corrige roupas pelo Blockbench MCP; UV por face; ossos armor*
│       └── blockbench-revisor [leitura] — confere interseções, espessuras, UV esticado e nomes de ossos; não modela
├── Análise (skill blockbench-analise) — medem e comparam; não alteram o modelo
│   ├── blockbench-analisador-elementos [leitura] — mede cada elemento e separa por osso; prepara o pacote para os juízes
│   ├── blockbench-comparador-exemplos [leitura] — compara lado, frente, proporção e espessura com o exemplo aprovado
│   ├── blockbench-analisador-textura [leitura] — analisa a textura pixel a pixel contra o exemplo e o mapa UV
│   ├── blockbench-mostrador [leitura] — gera fotos de projeção e capturas lado a lado com o exemplo
│   └── blockbench-referencias [leitura] — mede armaduras de mods de referência, com números reais
├── Planejamento — formulam planos; não executam nada
│   ├── blockbench-planejador [grava] — define etapas, responsável e critério de aceite da peça
│   │   └── blockbench-planejador-auxiliar [coord] — diz qual agent deve agir agora, com qual entrada, e o que esperar
│   ├── blockbench-planejador-itens [grava] — planos para itens com modelo 3D e portão de aprovação
│   ├── blockbench-planejador-entidades [grava] — planos para mobs e NPCs: modelo, textura, animação, spawn
│   ├── blockbench-planejador-efeitos [grava] — planos para efeitos visuais e sonoros, partículas e keyframes
│   └── blockbench-planejador-comidas [grava] — planos para comidas de Bedrock, com ícone 2D ou modelo pequeno
├── Pesquisa e aprendizado — gravam resumos próprios; não copiam material com direitos
│   ├── blockbench-pesquisador [pesquisa] — fontes sobre Blockbench, Bedrock, Molang e GeckoLib
│   ├── blockbench-aprendiz-modelagem [pesquisa] — aprende modelagem e textura na web e em vídeos
│   ├── blockbench-aprendiz-pintura [pesquisa] — técnicas de pintura e ferramentas de imagem
│   ├── blockbench-aprendiz-texturas [pesquisa] — estuda as texturas dos mods Narutoto e NinshuOrigins
│   ├── blockbench-buscador-referencias [pesquisa] — referências visuais e tutoriais, com índice de links
│   └── blockbench-pesquisador-segundo-cerebro [pesquisa] — busca no vault o material já clipado sobre roupas
└── Registro e vault — registram o que deu certo e errado
    ├── blockbench-sc-registro [grava] — registra erros, progresso e acertos em registro/
    │   └── blockbench-sc-relator [leitura] — resume o que deu certo e errado, com a ação recomendada
    ├── blockbench-sc-gestor [grava] — entrega informações do vault aos agents pelo índice
    └── blockbench-sc-organizador [grava] — organiza o vault e cria funções; não apaga nada
```

---

## 3. Segundo Cérebro, vault (8 agents)

Trabalham em `D:\Segundo Cerebro`, fora do mod.

```
Vault
├── sc-tarefas [grava] — gerencia tasks/todo.md, a fonte única de tarefas
├── sc-memoria [grava] — registra decisões e conclusões em memoria/agentes/; usado no fim de cada tarefa
├── sc-categorizador [grava] — propõe tags, tipo e pasta; aplica só o que for aprovado
├── sc-canvas [grava] — cria canvas do Obsidian para mapear fluxos e relações
├── sc-planilha [grava] — cria e confere planilhas em CSV e XLSX
├── sc-usar-plugins [grava] — usa os plugins já instalados (obsidian-git, Canvas, Bases, Templates)
├── sc-sugerir-plugins [pesquisa] — sugere a ferramenta certa: plugin instalado, nativo ou da comunidade; não instala
└── sc-plugins-obsidian [pesquisa] — avalia e configura plugins da comunidade; não instala sem aprovação
```

---

## Contagem

| Família | Agents | coord | juiz | leitura | grava | gera | pesquisa |
|---|---|---|---|---|---|---|---|
| Mod NarutoCD | 32 | 1 | 2 | 10 | 9 | 3 | 7 |
| Blockbench | 32 | 2 | 4 | 7 | 13 | 0 | 6 |
| Segundo Cérebro | 8 | 0 | 0 | 0 | 6 | 0 | 2 |
