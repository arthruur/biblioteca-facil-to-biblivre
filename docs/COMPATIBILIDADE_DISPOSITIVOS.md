# Compatibilidade de Dispositivos e Recomendações de Hardware

Este documento detalha o comportamento do scanner de código de barras em diferentes sistemas operacionais móveis (Android vs iOS), as limitações físicas de câmeras (especificamente do iPhone 11) e as melhores práticas operacionais para catalogação por ISBN na biblioteca.

---

## 1. Comparativo de Motores: Android vs iOS

O leitor de código de barras utiliza uma arquitetura híbrida de alto desempenho:

| Característica | Android (Chrome / Chromium) | iOS (Safari / Chrome / Firefox) |
|---|---|---|
| **Motor de Detecção** | BarcodeDetector Nativo (C++) | Polyfill WebAssembly (zxing-wasm) |
| **Aceleração de Hardware** | Sim (GPU / NPU via Google Play Services) | Sim (compilado C++ via WebAssembly) |
| **Pipeline Inteligente (ROI)** | Ativo (scannerLoop.js) | Ativo (scannerLoop.js) |
| **Controle de Foco Manual** | Suportado em aparelhos compatíveis | Bloqueado pelo WebKit |
| **Controle de Lanterna (Torch)** | Suportado | Bloqueado pelo WebKit público |
| **Tolerância a Reflexo/Giro** | Muito Alta | Alta |

### Por que o Android com Chrome é tão rápido?
No Android, o Google Chrome implementa a especificação W3C [Shape Detection API](https://wicg.github.io/shape-detection-api/#barcode-detection-api). O reconhecimento roda em código binário otimizado do sistema operacional, processando imagens em alta resolução em menos de 15ms.

### Por que o iOS requer WebAssembly?
A Apple não implementou a API BarcodeDetector no WebKit. Como todos os navegadores no iOS (incluindo o Chrome e o Firefox para iPhone) são obrigados a utilizar o motor WebKit do sistema, nenhum navegador no iOS possui a API nativa.

Para garantir que o iPhone utilize **o mesmo pipeline de candidatos (ROI) e a mesma tela de depuração**, a aplicação carrega transparentemente o polyfill baseado em **WebAssembly (ZXing-C++ em WASM)**. Isso eleva a performance no iPhone a um nível muito próximo do nativo, superando em até 10× bibliotecas legadas em JavaScript puro.

---

## 2. Limitações Ópticas do iPhone 11

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

## 3. Guia Operacional para o Operador

Para garantir ritmo ágil de bipe contínuo na estante:

### Regra do Palmo (15–20 cm)
* **Nunca cole o celular no livro.**
* Mantenha o aparelho a aproximadamente **um palmo de distância (15 a 20 cm)**.
* O algoritmo de ROI localiza o código mesmo que ele ocupe uma porção menor da tela e recorta a região em alta resolução.

### Recomendações de Aparelhos para Volume Alto
* **Ideal:** Aparelhos Android com Google Chrome atualizado (leitura instantânea de múltiplos livros).
* **iPhones:** Funcionam bem com a regra dos 15–20 cm de distância. Se o livro estiver muito amassado ou com plástico brilhante reflexivo, utilizar o recurso de **Entrada Manual de ISBN** ou fotografar pela galeria.
