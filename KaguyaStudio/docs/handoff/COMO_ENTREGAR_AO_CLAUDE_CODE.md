# Como passar o projeto Kaguya Studio ao Claude Code

1. Baixe e extraia `KAGUYA_STUDIO_PACOTE_CLAUDE_CODE.zip` em uma pasta de trabalho nova do Windows.
2. A pasta extraída inclui o briefing completo, o ZIP do código atual (`Kaguya_Studio_V3_4_Dois_Mascotes_Windows.zip`), plano, catálogo de agentes, imagens de referência e sprites originais.
3. Extraia `Kaguya_Studio_V3_4_Dois_Mascotes_Windows.zip` dentro de outra pasta, por exemplo `Kaguya_Studio_Handoff\Codigo_V3_4`.
4. Abra o Claude Code nesse diretório de trabalho e envie a mensagem abaixo:

> Quero que você seja o engenheiro responsável por corrigir e evoluir o Kaguya Studio. Leia primeiro `BRIEFING_CLAUDE_CODE_KAGUYA_STUDIO.md`, depois `PLANO_KAGUYA_STUDIO_V3.md`, os catálogos dos 72 agentes e o código da V3.4. Não reinicie o projeto do zero e não sobrescreva minha hierarquia Claude/Obsidian. Hoje eu não consigo conectar as duas CLIs, vincular pastas de projeto ou Segundo Cérebro, nem trabalhar em equipe; a interface está ruim, falta voz e faltam visores reais de quota. Faça auditoria, reproduza os bugs, corrija os bloqueios de conexão e ofereça um redesenho realmente implementado com assets separados. Use as assinaturas oficiais sem API paga. Não invente resultados de testes, uso ou limites. Mostre os arquivos alterados, evidências de teste e como executar no Windows.

5. De preferência, faça uma cópia Git da pasta antes de editar. Não compartilhe `.env`, tokens, cookies, arquivos de autenticação ou documentos privados do Obsidian.
6. Para reproduzir o problema das pastas, faça o primeiro teste com um repositório temporário de exemplo e um vault de teste. Só então tente vincular a pasta real do Obsidian, com sua autorização.

**Observação:** o briefing descreve tanto funcionalidades já codificadas quanto requisitos ainda não entregues. Os testes anteriores não demonstram que tudo funciona no Windows do usuário.
