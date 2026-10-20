# Newzi 1.0 na App Store: o que foi feito e como terminar o envio

> Resumo da sessão de 2026-10-19 no Mac (iMac). Tudo daqui em diante se faz pelo navegador, no
> [App Store Connect](https://appstoreconnect.apple.com), e funciona igual no Windows. Detalhes técnicos ficam
> em `docs/IOS_SETUP.md` (seções 9.2 e 11).

## 1. O que foi feito

### Compra do Premium pela App Store (RevenueCat)
- Pods do RevenueCat instalados (`RNPurchases` 10.11.0, `RevenueCat` 5.92.0). In-App Purchase não precisa de
  nada no Xcode: já vem ligado no App ID `app.newzi.ios`.
- Webhook do RevenueCat confirmado na VPS (`https://api.newzi.app/api/v1/webhooks/revenuecat`).
- **Teste no sandbox (iPhone 8, iOS 16.7):** compra do mensal, renovação em 5 min e cancelamento apareceram no
  RevenueCat › Customers. O iPhone 8 foi registrado na conta de desenvolvedor.
- **Teste no TestFlight (iPhone 14 Pro Max):** compra com o Apple ID real, sem cobrança; a renovação de teste é
  diária (por isso a data de renovação ficou para o dia seguinte).

### Builds enviados ao App Store Connect
| Build | O que tem |
|---|---|
| 1.0 (6) | Compra pelo RevenueCat. Testado no TestFlight. |
| 1.0 (7) | **Build para a revisão.** Tudo do 6, mais as correções abaixo. |

Correções do build 7:
- **Barra de navegação:** vidro mais opaco (`regular` com 55% de tinta); os nomes das abas ficam legíveis.
- **Foto do perfil:** o ícone de câmera saiu de cima da foto (Perfil, Dados pessoais e Editar perfil). A foto só
  muda pelo botão **"Trocar foto"** em Editar perfil.
- **Manifesto de privacidade do widget** (`NewziWidgets/PrivacyInfo.xcprivacy`), que a Apple cobra pelo aviso
  ITMS-91053.
- **Idioma pt-BR declarado:** botões do sistema em português e a App Store lista o app como "Português".
- **Texto de "rede local"** (só usado em desenvolvimento) fora do build de produção.

### Regra do Premium (servidor)
O app não decide o que é Premium: ele pergunta ao servidor (`GET /me/entitlements`). Para ligar ou desligar os
cadeados basta o `.env` da VPS e reiniciar `newzi-api` e `newzi-worker`. Já configurado na VPS:
```
BILLING_ENABLED=true
PREMIUM_ENFORCED=true
TERMS_URL=https://newzi.app/termos.html
PRIVACY_URL=https://newzi.app/privacidade.html
```

### Dar Premium a alguém sem passar pela loja
Na VPS, em `/opt/newzi`, com o Python da API:
```bash
python backend/premium_test_account.py EMAIL grant --days 365   # Premium por 1 ano (padrão: 30 dias)
python backend/premium_test_account.py EMAIL status
python backend/premium_test_account.py EMAIL revoke             # não use em quem paga pela loja
```
O Premium manual não renova e vence sozinho. Se a pessoa assinar pela loja, a assinatura da loja passa a valer.

## 2. Checklist do envio para revisão

Já feito: assinaturas com preço, disponibilidade, print e nota; localização do grupo "Newzi Premium"; variáveis
na VPS; exclusão de conta funcionando.

Falta, na página **Distribuição › iOS › 1.0** e em **Informações do app**:
- [ ] **Build:** escolher **1.0 (7)** (aparece uns 10 a 30 min depois do envio; antes, vale abrir no TestFlight e
      conferir a barra de navegação nos temas claro e escuro).
- [ ] **Capturas de tela iPhone 6,9":** de 3 a 10 prints do **14 Pro Max** (1290 × 2796). Passe para o computador
      por AirDrop, iCloud ou cabo, ou pelo WhatsApp **como documento**; como foto o WhatsApp reduz para 738 × 1600 e
      a Apple recusa.
- [ ] **Descrição** com os links dos Termos e da Privacidade no fim (diretriz 3.1.2; é o motivo de recusa mais
      comum em app com assinatura). Rascunho na seção 3.
- [ ] **Palavras-chave**, **URL de suporte** (`https://newzi.app`) e **direitos autorais**.
- [ ] **Informações do app:** subtítulo, categoria **Notícias**, classificação etária (questionário) e URL de
      privacidade `https://newzi.app/privacidade.html`.
- [ ] **Privacidade do app:** rótulos (sugestão na seção 4; precisam bater com a política do site).
- [ ] **Preço e disponibilidade:** grátis; mesmos países das assinaturas.
- [ ] **Compras dentro do app e assinaturas:** as duas assinaturas anexadas à versão 1.0.
- [ ] **Informações para a revisão do app:** marcar "Login necessário" e informar o **e-mail e a senha** da conta
      de teste (criada pelo app com e-mail e senha, onboarding feito, **no plano Básico**; não excluir nem trocar a
      senha durante a revisão). Preencher contato e as notas abaixo.
- [ ] **Lançamento:** "Manualmente" (você escolhe o dia) ou "Automaticamente".
- [ ] **Adicionar para revisão** → **Enviar para revisão**. Criptografia já está declarada no build; IDFA: **Não**.

Nota sugerida para a revisão:
> Entre com o e-mail e a senha da conta de teste (também há login com Google e Apple). O Newzi Premium (assinatura
> mensal ou anual) fica em Perfil › Assinatura e plano; a conta de teste está no plano Básico para testar a compra.
> Os resumos em áudio são gerados todos os dias; o widget e a Live Activity de jogos aparecem com um time favorito
> em jogo.

Se a Apple perguntar sobre o conteúdo das notícias (diretriz 5.2): o app mostra resumos com o crédito do veículo e
um link para a matéria original.

## 3. Rascunho dos textos da loja

**Subtítulo** (até 30 caracteres):
```
Notícias no seu horário
```
> Alternativa: `Resumo diário em áudio` (22 caracteres).

**Texto promocional** (até 170 caracteres; pode mudar sem nova revisão):
```
As notícias que importam, resumidas e narradas no horário que você escolher. Siga seus assuntos e seus times, e ouça tudo em poucos minutos.
```

**Descrição:**
```
O Newzi reúne as notícias que importam para você e entrega um resumo diário, narrado em áudio, no horário que você escolher.

RESUMO DIÁRIO EM ÁUDIO
Escolha seus assuntos e receba todos os dias um resumo com as principais notícias, em texto e em áudio. Ouça com a tela bloqueada, ajuste a velocidade e pule entre os capítulos.

SEUS ASSUNTOS, SUA HOME
Política, economia, tecnologia, esportes, cultura e muito mais. A Home mostra o que está em alta e as últimas notícias dos temas que você segue, sempre com o crédito do veículo e o link para a matéria original.

FUTEBOL
Acompanhe seu time: início do jogo, gols, resultado e notícias, com alertas no celular.

ALERTAS E WIDGETS
Receba as notícias urgentes e as dos assuntos que você segue. Veja os destaques do dia na tela de início com o widget do Newzi.

SALVOS
Guarde matérias para ler depois e continue de onde parou.

NEWZI PREMIUM
Assine para ter o Newzi completo:
• Até 3 resumos por dia, cada um no seu horário e tema, e resumos gerados na hora
• Áudio para ouvir sem internet e fila contínua
• Widgets médio e grande, por assunto e por time, e placar ao vivo na tela de bloqueio
• Até 10 times, lembrete antes do jogo e resumo da partida em áudio
• Alertas por palavras-chave e acompanhamento de histórias
• Coleções, leitura offline e histórico completo

O Premium é uma assinatura mensal ou anual com renovação automática, cobrada na sua conta da App Store. A renovação acontece ao fim de cada período, a menos que seja cancelada até 24 horas antes. Cancele quando quiser nos ajustes da App Store.

Termos de uso: https://newzi.app/termos.html
Política de privacidade: https://newzi.app/privacidade.html
```

**Palavras-chave** (até 100 caracteres, sem espaços depois das vírgulas):
```
notícias,resumo,áudio,podcast,jornal,brasil,futebol,política,economia,tecnologia,manchetes
```

## 4. Sugestão de rótulos de privacidade

Tudo **vinculado à identidade do usuário** e **sem rastreamento** (o app não tem anúncios nem IDFA).

| Tipo de dado (App Store Connect) | O que é no Newzi | Finalidade |
|---|---|---|
| Informações de contato › Endereço de e-mail | login e conta | Funcionalidade do app |
| Informações de contato › Nome | nome do perfil | Funcionalidade do app |
| Conteúdo do usuário › Fotos ou vídeos | foto do perfil | Funcionalidade do app |
| Identificadores › ID do usuário | conta no servidor e no RevenueCat | Funcionalidade do app |
| Identificadores › ID do dispositivo | token de push | Funcionalidade do app |
| Compras › Histórico de compras | assinatura Premium | Funcionalidade do app |
| Uso › Interações com o produto | assuntos, salvos, avaliações, progresso de leitura | Funcionalidade e personalização do app |

## 5. Quando o Mac volta a ser necessário
- Se a Apple recusar por algo no app e for preciso gerar um build novo (próximo: 8).
- Para qualquer nova versão do iOS. Mudanças só no backend, na VPS ou nos textos do App Store Connect não
  precisam do Mac.
- Pendente para o Android (seção 9.2 do `IOS_SETUP.md`): chave do Google no RevenueCat e produtos na Play Console.
