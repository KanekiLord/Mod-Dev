# Changelog

## 5.9.2 — 26/11/2026 (verificação completa do código, parte 2: código mais antigo)

### Segurança
- **A IA podia responder "sim" à própria confirmação** no modo "Meu computador": a resposta era um arquivo numa
  pasta que ela pode escrever. Agora a pergunta e a resposta passam por uma conexão local que só o Studio responde,
  com um código por tarefa que morre quando a tarefa termina ou quando você aperta Parar (perguntas pendentes viram
  "não"). Sem esse canal, a resposta é sempre "não".
- **Abrir arquivo/link podia executar programas sem perguntar** (.hta, .cpl, .url, `ms-msdt:`, `search-ms:`…):
  só documentos, mídia e links comuns abrem direto; o resto pede confirmação, e endereços perigosos são recusados.
- **Codex continuando uma conversa herdava as permissões da tarefa anterior** (uma pergunta só de leitura podia
  continuar uma sessão com permissão de escrita): o sandbox desta tarefa vale sempre.
- **Teclado na janela errada**: se o Windows não deixar trazer a janela permitida para a frente, nada é digitado.

### Robustez
- Tarefa enviada no instante em que a fila terminava ficava parada sem ninguém para executá-la.
- Tarefa em paralelo que falhou nunca podia ser reexecutada ("branch já existe"); pastas de trabalho se acumulavam.
- Live: depois de um "não respondeu a tempo", a resposta atrasada respondia a pergunta seguinte.
- Lembretes e timers podiam sumir quando a IA criava um no mesmo instante em que outro tocava.
- Segundo Cérebro: notas salvas com BOM (alguns editores do Windows) nunca podiam receber atualização; falhas na
  aprovação agora sempre dizem o motivo; nota com caracteres inválidos nunca é reescrita.
- Escuta por nome: desligar enquanto ainda ligava abria o microfone mesmo assim.

## 5.9.1 — 26/11/2026 (verificação completa do código, parte 1)

### Corrigido — erro grave que deixava telas "travadas"
- **Todo erro de tarefa em segundo plano era perdido.** O aviso de erro era entregue depois, na tela, por uma função
  que usava a variável do erro — que o Python apaga ao sair do bloco `except`. O aviso quebrava e a tela nunca saía
  do estado "trabalhando" ("Transcrevendo…", "Preparando…", escuta "ligando"…). Agora o erro chega sempre.

### Corrigido — achados da revisão
- Navegador: o botão "Apagar dados de navegação…" da janela de privacidade apagava sem perguntar; um site podia
  desligar o "HTTPS sempre" navegando para um link interno (agora só a página de aviso do Studio, com código de uso
  único); o cadeado vermelho de um certificado ruim continuava nas páginas seguintes; o aviso "site sem HTTPS"
  aparecia ao cancelar um carregamento; proxy inválido mudava as outras opções antes de ser recusado; navegador
  funciona também em Qt 6.6–6.7 (permissões pelo caminho antigo).
- Download do modelo de voz que falhava sumia sem mensagem.
- Aleatório: músicas colocadas na fila enquanto embaralhava sumiam ao desligar.
- Live: falar com a IA cuja verificação ainda não tinha terminado dava erro interno.
- "Mudar pasta…": tudo ou nada (desfaz se falhar no meio), não com o Live/escuta ligados, e o ambiente do Qwen
  continua funcionando depois de mudar de pasta.
- Cancelar à força também libera o que a tarefa travada segurava (arquivo 3D, acesso ao navegador, controle do PC).

## 5.9.0 — 26/11/2026 (Kaguya Browser reorganizado e protegido)

### Tela
- O navegador usa a largura toda: sem o cartão do projeto e sem a coluna da direita enquanto você navega (em
  1366×740 a área do site passou de ~830×370 para ~1140×590 px). **Tela cheia** com F11 (Esc sai).
- Uma única linha de controles: voltar/avançar/recarregar/início, endereço com o **cadeado de segurança**, favorito,
  escudo de proteção (mostra quantos rastreadores foram bloqueados), **IA** e o menu ⋮.
- Tudo de IA (compartilhar a aba, deixar controlar, perguntar, linha do tempo) fica numa gaveta que só abre no botão
  **IA**; o botão mostra quem vê a aba ("IA: Miwa vê"). Nenhuma função foi removida.
- Menu ⋮: nova aba, aba anônima, tela cheia, privacidade e segurança, apagar dados, favoritos, histórico, mecanismo
  de pesquisa. Atalhos: Ctrl+T, Ctrl+W, Ctrl+Shift+N, Ctrl+L, F5, F11.

### Proteção (Privacidade e segurança — o que cada opção faz está explicado na própria janela)
- **HTTPS sempre**: sites abrem com criptografia; se o site não tiver, aparece um aviso e ele só abre com o seu
  clique (só aquele site, até fechar o Studio).
- **Bloqueio de rastreadores conhecidos** (Google Analytics, pixels de anúncio, gravação de sessão…) e **cookies de
  terceiros bloqueados**; sinal de "não rastrear" (GPC/DNT) em todas as requisições.
- **DNS criptografado** (DNS over HTTPS) opcional: Quad9 ou Cloudflare.
- Sempre ligados: certificado inválido bloqueia a página; câmera, microfone, localização, notificações e gravação
  de tela sempre pedem permissão; WebRTC não expõe seus IPs locais; área de transferência fechada para os sites.
- **Apagar dados de navegação** (histórico, cookies, logins, cache; favoritos ficam).
- **VPN**: explicado com honestidade — o Studio não embute "VPN grátis" (seria um terceiro vendo tudo); o navegador
  segue a VPN do Windows e aceita um proxy só para ele (vale após reiniciar).

## 5.8.1 — 26/11/2026 (correções do relatório de uso real)

### Corrigido — travamentos
- **Live preso em "Preparando…", escuta por nome que não ligava e fila que não andava.** Causa no Windows: o
  Studio esperava sem limite um `claude`/`codex` que não respondia. O `subprocess.run(timeout=…)` do Python mata só o
  `cmd.exe` do `.cmd` e fica esperando o `node` (que segura a saída) para sempre. Agora toda chamada externa passa por
  `kaguya/procutil.py`: tempo limite real, mata a árvore de processos inteira e respeita o Cancelar.
- **Tarefa "validada, verdinha" que segurava a fila.** Os testes do projeto (`gradlew test`) deixam o daemon do
  Gradle aberto segurando a saída, e o Studio esperava o fim dessa saída para sempre. A saída agora vai para arquivo
  temporário e o Studio espera o processo, não o daemon.
- **Cancelar sempre libera a fila**: interrompe também a tarefa em execução (botão "Interromper" na Fila) e, se algo
  externo não responder em 20 s, a tarefa é encerrada mesmo assim e a próxima pode começar. A mensagem "entrou na
  fila" diz qual tarefa está na frente, o que ela está fazendo e como interromper.
- **"Transcrevendo…" infinito.** O modelo de transcrição era baixado em silêncio (até 1,5 GB, sem progresso) e,
  mesmo já baixado, era conferido na internet a cada uso. Agora carrega só do disco; quando falta, o Studio pergunta,
  mostra o tamanho e o progresso, pode ser cancelado e para com uma explicação se o download travar. O botão mostra
  há quantos segundos está transcrevendo.
- O Live mostra o que está esperando ("Verificando o Claude Code… 12 s", "Carregando o reconhecimento de voz…"),
  verifica as duas IAs em paralelo e, se não der, diz por quê ("Não foi possível iniciar").

### Corrigido — voz lenta (minutos para começar a falar)
- Sem as vozes neurais baixadas, cada frase abria **dois** PowerShell (um só para listar as vozes). Agora a voz do
  Windows fica num único processo aberto e gera cada frase em frações de segundo; a escolha do motor não lista mais
  vozes por frase.

### Corrigido — Kaguya Music
- **Aleatório**: vale na hora (embaralha o que vem depois da música atual; desligar volta à ordem), fica dourado
  quando ligado e aceita voz ("modo aleatório", "desliga o aleatório"). No modo "App do Windows" o botão explica que o
  aleatório é do próprio app.

### Novo — pasta dos pacotes de voz e modelos
- No primeiro download o Studio pergunta onde guardar: pasta recomendada, **junto da instalação do Studio** (ou no
  mesmo disco dela) ou outra pasta, mostrando o espaço livre. Configurações › Voz › "Mudar pasta…" move o que já está
  instalado (nada é baixado de novo).

## 5.8.0 — 25/11/2026 (Kaguya Extension Hub)

Relatório completo, decisões, evidências reais, limitações e rollback: `docs/EXTENSION_HUB.md`.

### Novo — página **Extensões**
- **Descoberta automática (só leitura)** dos MCPs, plugins (com seus componentes), skills, agentes (mantendo a
  hierarquia de pastas), comandos e hooks do **Claude Code** (Miwa) e do **Codex** (Kaguya): usuário, projeto, local,
  plugin e builtin, por projeto. Usa os arquivos oficiais e as listagens oficiais (`claude plugin list --json`,
  `codex mcp list --json`, `codex plugin list --json`). Nada é alterado nem executado na varredura.
- **Estados reais e independentes**: descoberto → configurado → habilitado → carregado na sessão → conectado →
  capacidade verificada, mais `requer login/aprovação/reinício`, `falha`, `desabilitado`, `só na web`, `removido` —
  sempre com evidência, versão, escopo e data da última verificação. Configuração em disco nunca é mostrada como
  "disponível".
- **Sincronização automática** em segundo plano (com espera para arquivos sendo gravados): novas instalações,
  remoções, mudanças de versão e de configuração aparecem sozinhas, com aviso; histórico guardado.
- **Testar conexão** pelo teste oficial (`claude mcp get`) ou por handshake MCP que só **lista** as ferramentas
  (nada é executado); as **sessões reais** do Claude Code que o Studio abre registram o que conectou de verdade.
- **Delegação**: cada IA sabe o que ela e a outra têm; pedido de Blockbench para a Kaguya quando só a Miwa tem é
  oferecido à Miwa (com o MCP dela liberado naquela tarefa); uma IA pode pedir à outra com `[[DELEGAR:…]]` e o Studio
  cria a tarefa. Nada é copiado entre os clientes.
- **Instalação/ativação/remoção supervisionadas**: plano com o comando oficial (segredos ocultos), revisão de origem,
  permissões, custos (ex.: ElevenLabs), segredos e scripts que baixam código (npx/uvx), conflitos de nome e porta,
  como desfazer — e só roda depois de você marcar "revisei" e aprovar. Segredos vão só para o cliente oficial.
- **Blender/Blockbench**: um escritor por arquivo/aplicativo de cada vez e backup do `.blend`/`.bbmodel` antes.
- **Plugins só da web** (ChatGPT/Claude web) podem ser registrados e aparecem como não transferíveis.

### Corrigido
- Live: encerrar o Live no instante em que a Miwa estava abrindo o Claude Code podia deixar o processo aberto em
  segundo plano (achado pelo CI do Windows). Agora o encerramento espera a abertura e fecha o processo, e nada novo
  é aberto depois do fim.

## 5.7.0 — 25/11/2026 (Etapa D: Leitor Universal + motor de conhecimento)

### Novo — Leitor Universal (botão **Anexar** na Conversa)
- O Studio lê: texto, código, Markdown, JSON/YAML/CSV, **logs** (só as linhas de erro com contexto e o fim do
  arquivo, com números de linha), **Word** (títulos, parágrafos, tabelas), **Excel** (valores e **fórmulas como
  texto**, nunca calculadas), **PowerPoint** (slides e notas), **PDF** (camada de texto; escaneado é avisado),
  **ZIP/JAR/APK** (só o índice; mods de Minecraft mostram `mods.toml`/`fabric.mod.json`/`mcmod.info`, quantas classes
  e pacotes) e imagens (dimensões; a imagem vai anexada para a IA ver).
- Segurança: formato reconhecido pela assinatura; **macros nunca executadas**; ZIP **nunca extraído** — avisa caminhos
  que escapam da pasta (zip slip), compressão suspeita (zip bomb) e programas dentro; XML com entidades (ataque) não é
  lido; `.env`, chaves, credenciais e programas `.exe` são recusados; leitura em **processo separado com tempo
  máximo** (arquivo hostil não trava o Studio); fora das pastas autorizadas, nega (inclusive por atalho/symlink).
- **Prévia antes de enviar**: você vê exatamente o que vai, pode apagar qualquer parte; "só os trechos relevantes"
  para a sua pergunta e "ocultar o que parece senha/token" já vêm ligados. Vai para a IA como **dado**, cercado.
  Ex.: um log de 4.000 linhas virou 939 caracteres com o crash exato.

### Novo — motor de conhecimento (Segundo Cérebro)
- Notas no formato da spec 08: `tipo, projeto, tema, fonte_url, fonte_tipo, coletado_em, status, confianca,
  versao_contexto, encontrado_por` — a versão (ex.: "Forge 1.20.1", "GeckoLib 4.4") é detectada sozinha nos
  aprendizados das IAs.
- **Atualizar em vez de duplicar**: mesma fonte ou conteúdo já presente numa nota vira proposta de **acrescentar**
  àquela nota, com **diff colorido**; aprovar faz **backup** e só acrescenta (escrita atômica). Se a nota mudou depois
  da proposta, nada é alterado. Repetir a mesma pesquisa não cria nada ("já registrado").
- **Divergência**: versão diferente da que a nota registrava vira seção "⚠ Divergência" com as duas — nada é
  substituído.
- **Revisão do conhecimento** (botão no Segundo Cérebro): notas antigas sem validação, marcadas para revalidar, sem
  fonte, links quebrados e títulos duplicados — só relatório; "Propor revalidar as antigas" muda **só** o status,
  depois da sua aprovação.
- A memória enviada às IAs agora diz quanto confiar em cada nota (status, confiança, versão, fonte, data) e avisa
  quando ela precisa ser revalidada; as IAs são instruídas a citar o caminho da nota.
- **Sem vault conectado**, os aprendizados ficam na fila e podem ser aprovados depois de conectar.

### Novo — Observação ativa
- Indicador no topo que só aparece quando alguma IA pode ver ou ouvir algo (abas compartilhadas/controladas,
  microfone do Live ou da escuta por nome, controle do PC), com menu para parar cada um.

## 5.6.0 — 25/11/2026 (Live com chibis + Kaguya V3)

### Novo
- **Modo Live com chibi**: em vez da janela grande, um **chibi flutuante** da IA ativa (Kaguya ou Miwa), pequeno,
  transparente, sempre visível e arrastável (a posição é lembrada). Balão de fala com a última frase, nome e estado
  ("Ouvindo", "Pensando…", "Falando"), brilho que reage ao microfone e 4 botões redondos: mudo, trocar de IA,
  silenciar a voz e encerrar. A janela grande continua em Configurações › Voz › Visual do Modo Live.
- Animação de verdade conforme a conversa: acena ao começar (Miwa) / carinhosa (Kaguya), **pensando** enquanto entende
  e responde — a Miwa abre o notebook se demorar —, sequências de **fala** que só se mexem quando há voz no áudio (boca
  fecha nas pausas), atenta quando você fala, séria quando dá erro.
- Sprites: o pacote **kaguya_chibi_talk_v1** (7 sequências × 7 quadros) e as duas folhas da **Miwa chibi**
  (recortadas pelos espaços entre as figuras, com efeitos ?, !, ♥ junto da figura certa; as duas folhas desenham a
  personagem em tamanhos diferentes e foram igualadas para ela não "crescer" entre quadros). Originais guardados em
  `pacote_original/`. Ferramenta: `tools/recortar_chibis.py`.
- **Kaguya V3 (retrato, fala e gestos)**: as imagens transparentes enviadas viraram uma variante com 9 expressões e
  3 animações de fala (boca fechada no quadro 1), com bordas suaves. Escolha em Configurações › Mascotes › Visual da
  Kaguya (a V2 continua padrão).

## 5.5.0 — 25/11/2026 (Etapa C: Kaguya Browser + YouTube Intelligence)

### Novo — Navegador (menu › Navegador)
- Navegador de verdade dentro do Studio: **abas**, voltar/avançar, barra de endereço que também pesquisa
  (DuckDuckGo, Google, Bing ou YouTube), **favoritos** (☆), **histórico** com busca e "apagar", página inicial com os
  favoritos, **aba anônima** (não grava histórico nem login) e downloads sempre com "salvar como" (programas pedem
  confirmação). Seus logins ficam num perfil próprio na pasta de dados do Studio.
- **Toda aba é pessoal**: nenhuma IA vê nada até você clicar em *Compartilhar com: Kaguya / Miwa* — por aba e por IA,
  com moldura colorida, ● no título, faixa "compartilhada com Miwa desde 14:32" e **linha do tempo** de cada acesso.
- **Perguntar sobre esta aba**: a IA recebe só título, endereço, o **texto visível** e o trecho que você selecionou —
  nunca senhas, cookies, o que você digitou em formulários ou texto escondido na página. Vai como **dado não
  confiável**: se a página tentar dar ordens à IA ("ignore as instruções…"), o Studio avisa e registra. A resposta
  aparece no próprio navegador (e na Conversa).
- **Controle supervisionado** (*Pode controlar: Kaguya / Miwa*): a IA rola, clica, digita e abre páginas **só
  naquela aba**, uma IA por vez, pelas ferramentas `kaguya_browser` (servidor MCP do Studio, ponte só em 127.0.0.1
  com chave que morre ao fim da tarefa). Faixa "Miwa está controlando esta aba" com **Assumir controle** (ela espera
  até você devolver) e **Parar**; **Pausar tudo** também corta. **Nunca digita em campo de senha/cartão**; comprar,
  publicar, enviar, apagar, entrar e baixar programas **pedem sua confirmação**. A IA pode abrir a própria **aba de
  pesquisa** isolada (sem seus logins, fora do seu histórico), visível como "🔎 Miwa".

### Novo — YouTube Intelligence (painel ao abrir um vídeo)
- Mostra sempre **o que a IA realmente tem**: **A — metadados** (título, canal, data, duração, descrição e capítulos;
  sem a página, o oEmbed oficial dá título e canal), **B — texto** (legendas que o próprio YouTube oferece, ou o painel
  "Mostrar transcrição" aberto; com tempos) e **C — visual** (só quadros que **você** captura, com o tempo). A IA é
  instruída a nunca dizer que viu/ouviu o vídeo.
- Capítulos clicáveis (pulam o vídeo), **Analisar o vídeo**, **Estudar este trecho** (±45 s do ponto atual),
  **Comparar com meu projeto** (versões, APIs, testes; sem alterar arquivos), **Criar nota** (rascunho em revisão no
  Segundo Cérebro, com links de tempo) e **Para depois**. Sem player escondido, sem baixar vídeo/áudio.
- Tarefas agora levam **anexos**: o conteúdo vai cercado como dado e as imagens chegam à IA (Codex `--image`,
  Claude com acesso só à pasta da imagem).

### Limitações conhecidas (honestas)
- O YouTube bloqueia servidores de nuvem ("tráfego incomum"): a leitura da página do YouTube foi testada com uma
  página que imita a estrutura de dados que ele entrega ao espectador, **não contra o YouTube real**. No seu PC ele
  abre normalmente; se algum dado não vier, o painel diz "indisponível" em vez de inventar.
- Alguns vídeos não entregam o texto das legendas para fora do player; aí o painel pede para abrir "Mostrar
  transcrição".

## 5.4.0 — 25/11/2026 (filtro de ruído: ventilador e vento no microfone)

### Novo
- **Filtro de ruído no microfone**, ligado por padrão no Live, no "chamar pelo nome" e no botão Falar
  (Configurações › Voz › Filtro de ruído: Desligado / Normal / Forte). Três camadas, tudo local e sem download:
  1. **Redução de ruído contínua**: aprende o som do ambiente nos momentos de silêncio e tira o zumbido do
     ventilador, ar-condicionado e chiado; corta o ronco grave (< 110–160 Hz); detecta **rajadas de vento** batendo
     no microfone e abafa os graves enquanto duram. Atraso ≈ 32 ms, ≈ 1% de um núcleo de CPU.
  2. **Detector de fala neural (Silero VAD)**, que já vinha junto com a transcrição: só conta como fala o que é
     voz de verdade — ventilador e vento não "começam a ouvir" nem interrompem a Kaguya/Miwa falando.
  3. **Checagem final** antes de transcrever: trecho sem voz é descartado (nunca vai para a IA), e frases que o
     Whisper inventa no ruído ("Legendas pela comunidade Amara.org", "Obrigado por assistir"…) são removidas.
- **Medir ruído do ambiente (5 s)**: mostra o ruído antes/depois do filtro em dB, quantos falsos inícios de fala
  aconteceriam com e sem filtro, se há vento no microfone, e dicas; **Ouvir sem filtro / com filtro**.

### Medido (ventilador + rajadas de vento simulados, com as amostras de fala do Studio e o Whisper real)
- Só ruído, 60 s: o sistema antigo disparava e, com ruído forte, **nunca encerrava a escuta** (nada era
  transcrito); o novo: **0 disparos falsos** nos três níveis.
- Fala no meio do ruído: antigo 0% transcrito; novo **91–98% das palavras certas**, cada frase inteira num trecho só.
- Ajustes medidos: pausa que encerra a fala 850 ms (era 750) para a frase não se partir no ruído.

### Corrigido
- Configurações tinha rolagem lateral em janelas de até ≈ 1.600 px (a linha dos mascotes era larga demais).

## 5.3.0 — 25/11/2026 (pacote "Vozes naturais", etapa 3: motor pesado)

### Novo
- **Qwen3-TTS 0.6B CustomVoice** como motor opcional, **instalado só se você confirmar** na página Vozes. Antes de
  baixar, o Studio mostra modelo, origem (Hugging Face/Qwen, PyPI, download.pytorch.org, uv do GitHub com checksum
  conferido), licença (Apache-2.0), tamanho (≈ 4 GB) e a pasta de destino. Tudo fica em
  `<dados>/vozes/qwen3/` (Python 3.12 e PyTorch **para CPU** isolados — o Studio nunca carrega PyTorch); **Cancelar**
  interrompe na hora, mesmo no meio de um download; **Remover** apaga tudo e devolve os perfis ao automático.
- O motor só aparece como instalado depois de **carregar o modelo de verdade e responder** (não por existir a pasta).
- 9 vozes do modelo selecionáveis por personagem, estilos viram instrução de fala ("com energia e alegria"…); entra no
  benchmark e no teste cego A/B. O modo Automático **nunca** escolhe o Qwen (lento demais para o Live) — só se você pedir.
- Processo de voz separado, com canal protegido: o que as bibliotecas imprimem não quebra a comunicação (bug real
  encontrado no teste e corrigido).
- Amostras `qwen3_serena.wav` e `qwen3_vivian.wav` em `docs/amostras_voz/` para comparar com o Kokoro.

### Medido de verdade (nuvem, 4 vCPU, sem GPU)
- Carga do modelo: **8,8 s** (com os arquivos já baixados). 7 frases: **RTF 3,75–4,13** (≈ 3× mais lento que o Kokoro
  aqui, RTF 1,25). Português reconhecido pelo Whisper em todas as vozes femininas (99–100%), mas **com sotaque**: as
  vozes do modelo são nativas de chinês/inglês/japonês/coreano.
- Conclusão honesta: com a GT 1030 (2 GB, sem suporte útil) roda na CPU; serve para ouvir e comparar, **não** para
  conversa em tempo real. O Kokoro continua o padrão.

### Corrigido
- **Biblioteca de músicas se recupera sozinha** se o arquivo for danificado (um teste no Windows encontrou o erro
  "database disk image is malformed" uma vez; não se repetiu e a causa não foi reproduzida). O arquivo antigo fica
  guardado como `musica.sqlite3.corrompido-<data>`, pastas, playlists e favoritas ainda legíveis são salvas, as músicas
  são reescaneadas e a página avisa. Suas músicas nunca são tocadas.

### Avaliado e adiado
- **Chatterbox Multilingual (pt-BR)**: projeto arquivado desde 08/2026 e carregador próprio para o checkpoint pt-BR;
  não instalado nem oferecido nesta versão.

## 5.2.0 — 25/11/2026 (pacote "Vozes naturais", etapas 1, 2 e 4)

### Novo
- **Página Vozes**: motores de voz com o **status real** deste PC (Kokoro-82M ONNX, vozes do Windows; Qwen3-TTS e
  Chatterbox listados como "não instalado — precisa da sua autorização", com licença, tamanho e avisos — Chatterbox
  está arquivado desde 08/2026). Nada é baixado sem você.
- **Perfil de voz por personagem**, independente da personalidade: motor (automático/Kokoro/Windows), voz, estilo
  (Natural, Suave, Animado, Formal), velocidade e **volume próprio**; "Ouvir Kaguya/Miwa" e Parar. Mudar a Miwa não
  mexe na Kaguya. A voz escolhida na 4.x continua.
- **Texto preparado para fala em pt-BR** sem mudar o chat: números por extenso (com "e" certo: "dois milhões e
  quinhentos mil"), datas, horas, porcentagens, reais, ordinais, versões ("um ponto sete ponto dez"), unidades
  (GB, ms…), siglas técnicas (GPU, VRAM, API…), nomes de arquivo ("main ponto pai"), identificadores de código e links.
- **Benchmark real**: TTFA (até o primeiro áudio, sem a latência da placa de som), tempo de síntese, duração e RTF com
  as frases de teste do pacote; p50/p95; resultados guardados no seu PC.
- **Teste cego A/B**: duas vozes em ordem sorteada, você vota sem saber qual é qual; placar local.
- **Boca guiada pelo áudio de verdade**: a mascote fecha a boca nas pausas da fala (energia do som tocando) e só
  anima enquanto há voz; para junto com o áudio. (Não é sincronização por fonemas.)
- Erros do motor de voz aparecem na tela (antes eram ignorados em silêncio); trecho atrasado nunca toca depois de
  uma interrupção.
- Amostras geradas localmente em `docs/amostras_voz/`.

### Medido (servidor de nuvem de 4 núcleos, sem GPU — não é o seu PC)
- Kokoro, 12 frases do pacote: **RTF p50 ≈ 1,25**, **TTFA p50 ≈ 3 s** (p95 ≈ 6 s), 0 erros.

## 5.1.0 — 25/11/2026 (Etapa B: Kaguya Music)

### Novo
- **Bandeja lateral de música**: uma lingueta fina presa na borda da tela (direita ou esquerda) que, ao clicar, **abre
  na horizontal** para dentro da tela com capa, título, artista, fonte, tempo/progresso (com busca), aleatório, anterior,
  tocar/pausar, próxima, repetir (fila/uma), volume e fila. Passar o mouse destaca e mostra o que está tocando; fecha
  sozinha ao sair (ou fica **fixada**); arraste a lingueta para cima/baixo; tudo é lembrado. Funciona com o Studio
  minimizado ou na bandeja do Windows. Mostrar/ocultar pela página ou pelo ícone perto do relógio.
- **Player local de verdade** (Qt Multimedia/FFmpeg, já incluso): MP3, FLAC, WAV, OGG/Opus, M4A/AAC, WMA. Biblioteca em
  SQLite com as pastas que você escolher (nada é copiado nem alterado), título/artista/capa lidos do arquivo, busca,
  favoritas, contagem de reprodução, **playlists** e fila. Página **Kaguya Music** no menu.
- **Comandos por texto e voz, sem gastar IA**: "toca Blue Bird", "toca a playlist Foco", "pausa a música", "próxima",
  "volume 30%", "abaixa a música", "que música é essa", "coloca X na fila". Funcionam na conversa, no Live e no
  "chamar pelo nome" ("Kaguya, pausa a música").
- **Ducking**: enquanto a Kaguya ou a Miwa falam, a música baixa (25% por padrão, ajustável) e **volta sempre** —
  fim normal, interrupção ou erro. Só o volume do player do Studio muda; o volume do Windows não é tocado.
- **YouTube, Spotify, Amazon Music**: "coloca uma abertura de Naruto no YouTube" abre a busca oficial para você escolher;
  na bandeja, a fonte "Windows" usa as teclas de mídia do próprio Windows (tocar/pausar, próxima, anterior) no app que
  estiver tocando. O Studio não toca vídeos escondidos, não lê o que esses apps tocam e não manda comandos de voz ao
  Spotify (regra da plataforma).

### Corrigido
- Mascotes e player agora pertencem à janela principal: nunca são destruídos fora da thread da interface (evitava um
  travamento raro ao fechar).

## 5.0.0 — 25/11/2026 (Etapa A do pacote de evolução)

Auditoria do pacote × código atual em `docs/AUDITORIA_PACOTE_2026-11-25.md` (matriz de lacunas com evidências).

### Novo
- **Página Personalidades** (spec 04): Kaguya e Miwa lado a lado — nome editável (vale na interface e no "chamar
  pelo nome"; o provedor Codex/Claude não muda), estilo (Kaguya/Miwa clássicas, profissional, descontraída,
  estrategista, professora, fofa, tsundere, gamer, personalizada), apelido, tratamento, saudação, terceira pessoa,
  iniciativa própria (só erros / marcos / conversa livre / silenciosa), **7 controles** (formalidade, humor,
  iniciativa, empatia, criatividade, objetividade, detalhe), emojis, texto livre, voz neural e visual.
  Perfil **global ou só do projeto atual**, **exportar/importar JSON** (aceita o formato do pacote), **restaurar padrão**,
  "Ouvir apresentação" (voz local) e **prévia do texto enviado à IA**. Em tarefas técnicas a personagem fica fora de
  comandos, código e relatórios. Perfis da 4.9.0 são convertidos automaticamente.
- **Início**: painel com estado real — IAs (diagnóstico e limite só se oficial), fila (executando, na fila, guardadas,
  para revisar, última concluída), projetos, Segundo Cérebro (notas indexadas, aprendizados em revisão), modos ativos
  e atalhos (Conversar, Live, Chamar pelo nome, Meu computador, Personalidades, ChatGPT/Claude).
- **Pausar tudo** (cabeçalho, bandeja e Ctrl+Shift+Pause): para todas as tarefas, o controle do PC, o Live, a escuta
  por nome e a fala de uma vez.
- **Segredos protegidos**: as IAs não leem nem alteram `.env`, chaves (`.pem`, `.key`, `id_rsa`…), `.ssh`, `.aws`,
  credenciais e arquivos de login das CLIs — bloqueado pelo próprio Claude Code (verificado de verdade) e pela regra
  no texto para o Codex. Conteúdo de sites/vídeos/arquivos é tratado como dado não confiável.
- `URGENTE:` (igual a `AGORA:`), `@kaguya:` e `@miwa:` na conversa.

### Corrigido
- Captura automática no `.exe` sem console: a proteção contra travamento escreve em arquivo (antes abria uma caixa de
  erro do PyInstaller e o CI ficava parado).

## 4.9.0 — 25/11/2026

### Novo
- **Instalador para Windows** (`KaguyaStudio-Instalador-4.9.0.exe`): instala só para o seu usuário, sem pedir
  administrador, com atalho no menu Iniciar, atalho opcional na área de trabalho, opção "iniciar com o Windows na
  bandeja" e desinstalador. **Para atualizar, rode o instalador da versão nova**: ele encontra a instalação, fecha o
  Studio aberto (mesmo na bandeja), troca os arquivos e mantém seus dados. Desinstalar não apaga seus dados.
- **Uma cópia só do Studio**: abrir de novo traz a janela que já está aberta (útil com a bandeja).
- **Boca e gestos ao falar**: a Kaguya (3 sequências: fala, explicando, acolhedora) e a Miwa (fala, explicando,
  pensando, acenando) mexem a boca e gesticulam enquanto a voz toca — no Live, nas mascotes flutuantes e nos cartões.
  Desliga em Configurações › Mascotes ou no menu da mascote.
  - Quadros da Kaguya refeitos a partir das folhas originais do pacote (o recorte do pacote deixava manchas do fundo e
    buracos no cabelo); o pacote original fica guardado intacto.
  - **Miwa V2 (fala e gestos)** virou o visual padrão (o desenho do pacote é outro, então ela usa o conjunto todo para
    não trocar de roupa no meio da fala); a Miwa V1 continua disponível.
- **Personalidade configurável** (Configurações › Personalidade): estilo (Kaguya/Miwa clássicas, fofa, séria,
  engraçada, tsundere, mentora, gamer ou só o seu texto), apelido para você, tratamento, humor, tamanho das respostas,
  emojis e texto livre. Vale na conversa, na voz, no "chamar pelo nome" e nas tarefas — muda só o jeito de falar.

### Corrigido
- Captura automática podia ficar aberta para sempre com a bandeja ativa (Qt 6 cancela o `quit()` quando uma janela
  recusa fechar); o CI ganhou limite de tempo por etapa.

## 4.8.0 — 25/11/2026

### Novo
- **Meu computador** (menu lateral): a Kaguya e a Miwa trabalham fora dos projetos, como assistentes pessoais —
  ler, criar e editar arquivos na sua pasta de usuário (Downloads, Documentos…), abrir arquivos, pastas, sites e apps,
  usar a tela/mouse/teclado (tela inteira), criar **timers, alarmes, lembretes** (a mascote avisa com voz e
  notificação, mesmo com o Studio na bandeja) e **eventos de agenda** (.ics aberto no seu calendário).
  - Pedidos por voz que são "no computador" ("Miwa, abre o WhatsApp e manda…", "Kaguya, vai na pasta Downloads…")
    viram tarefas de "Meu computador" automaticamente.
  - **Confirmação obrigatória (Sim/Não, com o texto exato)** antes de enviar mensagens/e-mails, apagar/mover/
    sobrescrever seus arquivos e executar programas; sem resposta = não. A mascote aparece, fala a pergunta e a janela
    fica por cima de tudo. Nunca digitam senhas nem fazem compras; apagar pastas inteiras pelo terminal é bloqueado.
  - Explicado e confirmado uma vez antes de ativar. Sem Git aqui: alterações fora de projetos não têm "Desfazer".
- Pesquisa sobre IA grátis, IA por voz e n8n em `docs/PESQUISA_VOZ_IA_N8N.md`.

## 4.7.0 — 25/11/2026

### Novo
- **Chamar pelo nome**: diga "Kaguya, olha isso pra mim" (Codex) ou "Miwa, vê isso pra mim" (Claude Code) — a
  mascote aparece na área de trabalho com um **balão de fala**, responde por voz e, se o pedido for trabalho, cria a
  tarefa (executa direto no modo autônomo; senão analisa sem alterar nada) e avisa por voz quando termina.
  - Escuta opcional (bandeja ou Configurações › Voz), explicada antes de ligar. A transcrição é local; **nada vai
    para a IA antes de ouvir o nome**. Usa o modelo "base" para reconhecer os nomes gastando pouco processador e o
    modelo principal para entender o pedido. Depois da resposta, alguns segundos para continuar sem repetir o nome.
  - Também funciona digitando: "Miwa, revise isso" na conversa vai para o Claude Code.
- A mascote do Claude Code agora se chama **Miwa**.
- **Conversa no estilo WhatsApp**: balões com cauda, suas mensagens à direita com ✓✓, as das IAs à esquerda com o
  rostinho da mascote, hora dentro do balão e avisos do Studio centralizados.
- **ChatGPT e Claude (chats normais)** dentro do Studio: os sites oficiais num navegador embutido, com o seu login,
  sem automação nem leitura das conversas; botão "Copiar contexto do projeto" e "Abrir no navegador".
  Aviso honesto: no Claude o chat e o Claude Code usam o **mesmo** limite; no ChatGPT, Codex e "ChatGPT Work" dividem
  o limite do plano e o chat comum tem limites próprios.
- **Segundo plano**: fechar (X) deixa o Studio rodando na **bandeja**, perto do relógio (opção para minimizar também);
  clique no ícone para abrir; menu com Chamar pelo nome, Live, mascotes e Sair. `--segundo-plano` abre direto na bandeja.

## 4.6.0 — 25/11/2026

### Novo
- **Usar o PC** (chave na conversa, lembrada por projeto): a Kaguya (Codex) e a Claude podem ver a tela e usar
  mouse e teclado durante as tarefas — por exemplo, abrir o Minecraft, entrar no mundo de teste e conferir o mod.
  - Feito com um servidor MCP **do próprio Studio**, passado só para essas tarefas (nada é instalado nas
    configurações das suas CLIs; o Claude roda com `--strict-mcp-config`, sem carregar seus outros MCPs).
  - **Somente a janela do Minecraft** por padrão (Configurações › Uso do computador): as capturas mostram só essa
    janela, cliques fora dela são recusados e a janela é trazida para a frente antes de digitar.
  - Aviso sempre visível com **Parar**; **Ctrl+Alt+End** e **mouse no canto superior esquerdo** também param na hora.
    Limite de ações por tarefa; atalhos do sistema (Ctrl+Alt+Del, Win+L) recusados; cada ação fica registrada na tarefa.
  - Ao ligar pela primeira vez o Studio explica que as capturas vão para a IA (OpenAI/Anthropic) pela sua assinatura.
  - Entrada pelo Windows (SendInput, Unicode para acentos), captura por GDI, coordenadas em pixels reais (DPI).
  - Com o modo autônomo, tarefas pedidas por voz no Live também podem usar o PC.

### Corrigido
- Fechar a janela do Live destruía a janela no meio do próprio evento de fechamento (risco de travar/fechar o app).
- Janelas eram destruídas fora de ordem ao sair do Studio (possível erro ao fechar).

## 4.5.0 — 25/11/2026

### Novo
- **Modo autônomo por projeto** (chave "Autônomo" em Permissões): a Kaguya (Codex) e a Claude editam arquivos,
  rodam comandos, builds e testes e terminam a tarefa **sem pedir confirmação**. Explicado e confirmado uma vez
  por projeto; fica lembrado ao reabrir o Studio; o cabeçalho mostra "Git ✓ • autônomo".
  - **Ponto de restauração Git** antes de cada tarefa (sem mexer no seu stage, branch ou stash) e botão
    **Desfazer** na Fila, que mostra os arquivos alterados e volta tudo como estava — inclusive se a IA fez commit.
  - Codex: sandbox `workspace-write` com rede liberada para builds (Gradle baixa dependências).
    Claude: edição e comandos liberados, com **push, remotes, configuração global, `gh`, instalações
    (npm -g, pip, winget, choco, scoop) e comandos destrutivos do sistema bloqueados** pela própria CLI.
  - Tarefas pedidas por voz no **Modo Live** passam a ser executadas direto quando o projeto está no modo autônomo.
  - Exige repositório Git (é o que permite desfazer); sem Git o Studio oferece criar o repositório.

### Corrigido
- Temporizadores de inicialização (limites, GitHub, áudio) podiam disparar depois de a janela fechar.

## 4.4.0 — 25/11/2026

### Novo
- **Modo Live** (botão "Live" ao lado de "Falar", ou Ctrl+Shift+L): conversa por voz contínua com a Kaguya
  (Codex) ou a Claude, numa janela própria com a mascote grande, legendas ao vivo e nível do microfone.
  - O microfone fica ouvindo com detecção de fala (VAD com ruído de fundo adaptativo); a fala é transcrita
    localmente (faster-whisper) e enviada a uma conversa que fica aberta — o Claude via
    `--input-format stream-json` e o Codex via `app-server` —, então só a primeira resposta tem a partida do processo.
  - A resposta começa a ser falada na primeira frase (voz neural Kokoro, se baixada; senão a voz do Windows).
  - **Interromper falando por cima** (barge-in): a fala para e o turno é cancelado na própria CLI.
  - Comandos falados: "falar com a Claude/Kaguya", "silêncio", "encerrar". Botões: Mudo, trocar IA,
    Silenciar voz, Encerrar.
  - Somente leitura: a IA pode consultar os arquivos do projeto, mas pedidos de alteração viram tarefas
    **DEPOIS** na fila (nada é executado durante a conversa).
  - Usa as assinaturas pelas CLIs oficiais (a voz realtime do Codex exige chave de API paga e não é usada).
  - Limites do Claude informados pela própria CLI durante a conversa aparecem em Uso e limites.

## 4.3.0 — 25/11/2026

### Novo
- **Vozes neurais locais (Kokoro)**, gratuitas e offline, baixadas só com sua autorização (≈ 120 MB,
  arquivos verificados por SHA-256). Uma voz para cada IA (Kaguya e Claude) com mistura de estilos, e
  "Ouvir amostra" em Configurações › Voz.
- **Fala fluida**: o texto é dividido em frases e a próxima é sintetizada enquanto a anterior toca; parar
  interrompe na hora. A voz do Windows continua como alternativa.

## 4.2.0 — 25/11/2026

### Novo
- **Microfone e fone**: escolha em Configurações › Voz (pelo nome, sobrevive a reconectar) e troca rápida no botão
  ao lado de "Falar". Detector automático avisa quando um microfone/fone é conectado ou desconectado e volta ao
  padrão do Windows se o escolhido sumir.
- **Testar microfone** com medidor de nível e **Testar som** no dispositivo escolhido.
- **Uma voz para cada IA** (Kaguya/Codex e Claude), escolhida entre as vozes instaladas no Windows.
- Gravação na taxa nativa do microfone com conversão para 16 kHz (evita erro em microfones de 44,1/48 kHz).

## 4.1.2 — 25/11/2026

### Corrigido
- **Voz no executável**: o .exe era gerado sem a transcrição local e mandava rodar INSTALAR.bat/pip, que não
  funcionam na versão executável. O build agora inclui faster-whisper e o acesso ao microfone, e o CI verifica
  que o próprio .exe consegue carregá-los (`--verificar-voz`). O modelo continua sendo baixado só com sua autorização.

## 4.1.1 — 25/11/2026

### Corrigido
- **Login do GitHub não abria** ("'\\"C:\\Program Files\\GitHub CLI\\gh.EXE\\"' não é reconhecido"): o terminal era aberto
  com aspas escapadas que o cmd.exe não entende. Afetaria também "Entrar" do Codex/Claude em pastas com espaços.
  Agora o comando usa a forma de aspas do cmd (`cmd /k ""C:\\...\\gh.exe" auth login"`), validada num Windows real no CI.
- **"Não está respondendo" ao criar o repositório Git**: o primeiro commit de uma pasta grande rodava na linha
  da interface. Agora roda em segundo plano com aviso de progresso.

## 4.1.0 — 25/11/2026

### Novo — integração com o GitHub (CLI oficial `gh`)
- Diagnóstico › **GitHub**: instalação, conta conectada e login oficial pelo navegador (`gh auth login --web`).
  O Studio nunca lê, mostra ou grava o token.
- Barra do projeto › **GitHub**: Publicar (repositório **privado** por padrão), Salvar versão (commit),
  Enviar (push), Atualizar (pull só *fast-forward*, recusa se houver alterações sem commit), Criar pull request
  de outro ramo (útil para os ramos do modo PARALELO) e Abrir no navegador. Mostra ↑ a enviar, ↓ a receber, ✎ sem commit.
- Nada vai para o GitHub sem o seu clique; as IAs continuam proibidas de fazer commit/push sozinhas.

## 4.0.2 — 25/11/2026

### Corrigido
- **Janela extra pequena** com "0": um selo sem lugar na tela virava janela própria. Removido; selos sem
  janela-mãe nunca mais são exibidos sozinhos.
- **Limites do Codex**: "invalid type: map, expected unit" — versões anteriores do Codex exigem a consulta sem
  parâmetros. Agora a consulta é compatível com versões antigas e novas e, se mesmo assim não houver resposta,
  usa o registro oficial que o Codex grava em `~/.codex/sessions`.
- **Limites não atualizavam**: Codex é consultado ao abrir, a cada 10 min e após cada tarefa (sem gastar cota);
  um dado antigo válido não é mais apagado por uma tentativa que falhou; o painel mostra hora e motivo da última tentativa.
- **Claude**: "Atualizar agora" envia uma mensagem mínima (pergunta antes) para obter a utilização oficial;
  durante tarefas continua automático.

### Novo
- Botão **Criar repositório Git** no projeto (git init, `.gitignore` para mods sem sobrescrever, commit inicial opcional).

## 4.0.1 — 25/11/2026

### Corrigido
- **Janela branca ao abrir o .exe**: o capturador de erros abria uma caixa de diálogo *modal*; um erro
  repetido em timer empilhava diálogos aninhados que nunca eram desenhados, congelando o app. Agora os
  erros vão para `%LOCALAPPDATA%\KaguyaStudio\logs\erros.log` com no máximo um aviso não bloqueante.
- Importação da V3: o vault global passa a ser o que existe no disco (antes podia escolher um inexistente);
  falha na importação não impede mais o Studio de abrir.
- Barra lateral compacta não espreme mais o texto "Nenhum projeto ainda".

### Novo
- Diagnóstico de inicialização: `logs/inicializacao.log` (cada etapa), `logs/travamento_*.txt` (pilhas de
  execução quando a interface para de responder por 12 s) e `logs/falha_grave.log`.
- `--sair-apos N` e teste de CI que abre o `.exe` em modo normal com dados da V3 para importar.
- **Kaguya V2** (9 expressões novas, incluindo *entediada* e *dormindo*) como visual padrão do Codex; a V1
  (18 expressões + animações) continua disponível em Configurações ou no clique direito da mascote.

## 4.0.0 — 25/11/2026

Reconstrução da camada de apresentação em PySide6 e correção dos bloqueios da V3.4, preservando o
núcleo de ideias (fila, DEPOIS/IDEIA, outbox create-only, inventário somente leitura).

### Corrigido (P0)
- Codex falhava fora de repositório Git confiável (`--skip-git-repo-check`).
- Execuções com erro eram marcadas como concluídas (Codex sai com código 0 após 401/limite).
- Instrução do Claude engolida por opção variádica; revisão em modo `plan` não executava.
- Variáveis de ambiente de nuvem bloqueavam todos os agentes.
- Vínculo de projeto e vault: vault global independente, edição, desvincular, colar caminho,
  verificação ao vivo, subpasta de Git, mensagens específicas.
- Diagnóstico das CLIs com estados, versão, executável, login, plano e correção sugerida.

### Novo
- Interface PySide6 com design system próprio, assets independentes (ícones SVG, ornamentos, fundos,
  estados, identidade visual, fontes OFL), layout responsivo 100–200% de DPI.
- Modo Equipe com ciclo de correção e veredito; modo PARALELO em Git worktrees com integração supervisionada.
- Sessões contínuas por projeto e histórico da conversa.
- Segundo Cérebro: índice FTS5 incremental (fora do vault), busca com fonte, outbox com detecção de
  duplicatas, leitura de `tasks/todo.md`, aprendizados extraídos automaticamente.
- Inventário real de agentes/skills/plugins/MCPs conciliado com o catálogo de 72.
- Painel de limites a partir de fontes oficiais (Codex app-server; eventos do Claude Code), nunca inventado.
- Voz local: leitura interrompível, push-to-talk com faster-whisper (opcional), comandos falados não interruptivos.
- Mascotes com transparência real por pixel, expressões por estado da própria IA, chat rápido.
- Migração automática dos projetos/fila da V3.x (somente leitura do banco antigo).
- Instalador local (`INSTALAR.bat`), executável Windows via CI (PyInstaller), testes no Windows.

### Mantido
- `legacy_v3_4/`: código da V3.4 para comparação e para os testes de regressão. Não é mais a versão principal.
