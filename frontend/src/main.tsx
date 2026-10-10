/** 应用入口：挂载 React 根节点。 */
import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import App from './App'
import './styles/tokens.css'
import './styles/base.css'

const container = document.getElementById('root')
if (!container) {
  throw new Error('找不到挂载节点 #root，请检查 index.html')
}

createRoot(container).render(
  <StrictMode>
    <App />
  </StrictMode>,
)
