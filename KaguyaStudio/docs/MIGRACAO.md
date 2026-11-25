# Migração da V3.x para a 4.0

1. Extraia a V4 em uma **pasta nova** (ex.: `D:\Ferramentas\KaguyaStudio4`). Não precisa apagar a V3.
2. Use **uma** das formas:
   - **Executável** (`KaguyaStudio-4.0.0-windows.zip`): extraia e abra `KaguyaStudio.exe`. Não precisa de Python.
   - **Código-fonte**: rode `INSTALAR.bat` (cria `.venv` local e instala o PySide6) e depois `INICIAR_KAGUYA_STUDIO.bat`.
3. Na primeira abertura, o Studio procura `%LOCALAPPDATA%\KaguyaStudioV3\studio.sqlite3` e **copia** projetos e
   fila. O banco antigo é aberto somente para leitura. O vault mais usado vira o **vault global**.
   (Para repetir: Configurações › Importar dados da V3.x.)
4. Os dados da V4 ficam em `%LOCALAPPDATA%\KaguyaStudio\` (banco, índice do vault, rascunhos, logs).
   Nada é gravado no seu vault sem aprovação, e nada é gravado nos seus projetos sem a permissão "Alterar arquivos".
5. Preferências das mascotes da V3 não são importadas (posição/escala são novas).
6. Em **Diagnóstico**, clique em *Diagnosticar* para Codex e Claude. Se aparecer "Não autenticado", use *Entrar*.
   Depois, *Teste real* confirma a execução pela assinatura (consome uma fração mínima da cota).
