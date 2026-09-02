import fs from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

const aqui = path.dirname(fileURLToPath(import.meta.url))
const RAIZ = path.resolve(aqui, '../..')
const CERTS = path.join(RAIZ, 'data', 'certs')

/**
 * O dev server precisa de HTTPS pelo mesmo motivo que o servidor de produção:
 * `getUserMedia` só funciona em contexto seguro, então sem TLS não há câmera no
 * celular — e é no celular que a tela de escanear é usada.
 *
 * Reusa o certificado autoassinado que o backend já gera em `data/certs`. Se
 * ainda não existir (primeira execução, antes de subir o servidor), cai para
 * HTTP: dá para trabalhar no layout pelo desktop, só não dá para bipar.
 */
function certificado() {
  const cert = path.join(CERTS, 'cert.pem')
  const key = path.join(CERTS, 'key.pem')
  if (fs.existsSync(cert) && fs.existsSync(key)) {
    return { cert: fs.readFileSync(cert), key: fs.readFileSync(key) }
  }
  console.warn(
    '\n  [vite] data/certs não encontrado — subindo em HTTP.\n' +
    '  A câmera do celular não vai funcionar. Rode o backend uma vez\n' +
    '  (python scripts/servidor.py) para gerar o certificado.\n'
  )
  return false
}

const API = process.env.BIBLIO_API || 'https://localhost:8000'

export default defineConfig({
  plugins: [react()],
  server: {
    // `host: true` expõe na LAN: é assim que o celular alcança o dev server.
    host: true,
    port: 5173,
    https: certificado(),
    proxy: {
      '/api': {
        target: API,
        changeOrigin: true,
        // O backend usa certificado autoassinado; sem isto o proxy recusa.
        secure: false,
      },
    },
  },
  build: {
    outDir: 'dist',
    // Sem sourcemap em produção: o bundle vai para um servidor de biblioteca,
    // não para um CDN, e o tamanho importa mais que o debug remoto.
    sourcemap: false,
  },
})
