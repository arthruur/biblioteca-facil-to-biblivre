import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'

/* Barlow / Barlow Condensed vêm empacotadas, não do CDN: o servidor roda na
   rede local da biblioteca e muitas vezes sem internet. Fonte que não carrega
   derruba a identidade da tela inteira para o system-ui. */
import '@fontsource/barlow/400.css'
import '@fontsource/barlow/500.css'
import '@fontsource/barlow/700.css'
import '@fontsource/barlow-condensed/400.css'
import '@fontsource/barlow-condensed/600.css'
import '@fontsource/barlow-condensed/700.css'

/* Antes do App: tokens e base precisam existir na folha antes das regras de
   componente que os consomem — a ordem do bundle segue a ordem dos imports. */
import './styles/base.css'

import App from './App'

createRoot(document.getElementById('raiz')).render(
  <StrictMode>
    <App />
  </StrictMode>
)
