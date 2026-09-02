# Compatibilidade de Dispositivos e Recomendações de Hardware

Este documento detalha o comportamento do scanner de código de barras em diferentes sistemas operacionais móveis (Android vs iOS), as limitações físicas de câmeras (especificamente do iPhone 11) e as melhores práticas operacionais para catalogação por ISBN na biblioteca.

---

## 1. Comparativo de Recursos: Android vs iOS

O leitor de código de barras utiliza uma arquitetura híbrida de alto desempenho:

| Recurso | Android (Chrome / Chromium) | iOS (Safari / Chrome / Firefox) |
|---|---|---|
| **Motor de Detecção** | BarcodeDetector Nativo (C++) | Polyfill WebAssembly (zxing-wasm) |
| **Aceleração de Hardware** | Sim (GPU / NPU via Google Play Services) | Sim (compilado C++ via WebAssembly) |
| **Pipeline Inteligente (ROI)** | Ativo (scannerLoop.js) | Ativo (scannerLoop.js) |
| **Vibração Tátil (
avigator.vibrate)** | **Suportada** | **Bloqueada pelo iOS (não implementada pela Apple)** |
| **Bipe Sonoro (AudioContext)** | **Livre** | **Exige interação prévia e respeita chave silenciosa** |
| **Controle de Foco Manual** | Suportado em aparelhos compatíveis | Bloqueado pelo WebKit |
| **Controle de Lanterna (Torch)** | Suportado | Bloqueado pelo WebKit público |
| **Tolerância a Reflexo/Giro** | Muito Alta | Alta |

---

## 2. Limitações de Vibração e Som no iPhone / iOS

### A. Vibração (
avigator.vibrate)
* **A Apple nunca implementou a Vibration API na Web:** A função 
avigator.vibrate é simplesmente undefined em qualquer navegador no iOS (Safari, Chrome ou Firefox para iPhone).
* A política da Apple reserva o motor háptico (Taptic Engine) exclusivamente para apps nativos ou interações do próprio sistema operacional.
* **Comportamento no app:** O app tenta chamar a vibração com segurança, mas no iPhone ela falha silenciosamente. O retorno sensorial no iOS depende do **bipe sonoro** e do **feedback visual (flash verde no visor)**.

### B. Som / Bipe de Confirmação (AudioContext)
O som funciona no iOS, porém sujeito a duas regras rígidas do sistema:
1. **Chave de Modo Silencioso:** Se a chavinha física lateral do iPhone (ou o botão de Ação) estiver no modo silencioso, o iOS silencia completamente todo o áudio web (Web Audio API).
2. **Gesto Prévio do Usuário:** O iOS suspende a reprodução de áudio se a página não tiver recebido ao menos um toque físico na tela após carregar.
3. **Gerenciamento de Instâncias:** O Safari limita a quantidade de AudioContext abertos em simultâneo. Por isso, a aplicação reutiliza um AudioContext compartilhado (*singleton*) que é destravado com esume() assim que o usuário interage.

---

## 3. Limitações Ópticas do iPhone 11

Durante os testes de bancada, constatou-se que o iPhone 11 apresenta comportamento de foco sensivelmente diferente de aparelhos Android modernos. A causa é **física (óptica da lente)**:

1. **Ausência de Lente Macro:**
   - O iPhone 11 possui uma lente grande-angular padrão (26mm eq.) cuja **distância mínima de foco é de cerca de 12 a 15 cm**.
   - O modo macro da Apple só foi introduzido a partir da linha **iPhone 13 Pro**.
2. **O Erro do Usuário (Aproximação Excessiva):**
   - Ao tentar enquadrar o código no visor, o operador tende intuitivamente a aproximar o aparelho a 5–8 cm da lombada/capa.
   - Nessa distância, **a lente do iPhone 11 não consegue focar fisicamente**, gerando uma imagem borrada. Como qualquer decodificador exige barras nítidas, a leitura falha.
3. **Restrição de API de Câmera no Safari:**
   - O Safari não expõe a propriedade ocusMode: 'continuous' nem controle de distância de foco através da API MediaTrackCapabilities. O foco fica totalmente a cargo do algoritmo automático do iOS.

---

## 4. Guia Operacional para o Operador

Para garantir ritmo ágil de bipe contínuo na estante:

### Regra do Palmo (15–20 cm)
* **Nunca cole o celular no livro.**
* Mantenha o aparelho a aproximadamente **um palmo de distância (15 a 20 cm)**.
* O algoritmo de ROI localiza o código mesmo que ele ocupe uma porção menor da tela e recorta a região em alta resolução.

### Recomendações de Aparelhos para Volume Alto
* **Ideal:** Aparelhos Android com Google Chrome atualizado (vibração tátil ativa, bipe imediato e leitura instantânea de múltiplos livros).
* **iPhones:** Funcionam bem com a regra dos 15–20 cm de distância. O feedback de leitura no iPhone é dado principalmente pelo **flash verde no visor** e pelo **bipe** (se o aparelho não estiver na chave silenciosa).
