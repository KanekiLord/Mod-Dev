# Instalador do Kaguya Studio

- Gerado no CI do Windows a cada versão (artefato **KaguyaStudio-Instalador**): `KaguyaStudio-Instalador-X.Y.Z.exe`.
- Instala em `%LOCALAPPDATA%\Programs\Kaguya Studio`, sem administrador. Seus dados ficam em
  `%LOCALAPPDATA%\KaguyaStudio` e não são tocados por atualizações nem pela desinstalação.
- **Atualizar** = executar o instalador da versão nova (ele fecha o Studio aberto e troca os arquivos).
- O instalador não é assinado digitalmente (assinatura custa caro): o Windows pode mostrar "O Windows protegeu o
  computador" — clique em "Mais informações" › "Executar assim mesmo".
- Para gerar localmente: instale o Inno Setup 6 e rode
  `iscc /DAppVersion=4.9.0 /DSourceDir=..\dist\KaguyaStudio instalador\KaguyaStudio.iss` depois de `python tools/build_windows.py`.
