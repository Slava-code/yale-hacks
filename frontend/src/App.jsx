import { useState } from 'react'
import ChatPanel from './components/ChatPanel'
import GraphPanel from './components/GraphPanel'
import './App.css'

function App() {
  const [selectedModel, setSelectedModel] = useState('claude')

  return (
    <div className="app-container">
      {/* Header */}
      <header className="app-header">
        <div className="logo">
          <span className="logo-icon">⚕</span>
          <span className="logo-text">MedGate</span>
        </div>
        <div className="header-subtitle">
          HIPAA-Compliant Clinical AI
        </div>
      </header>

      {/* Main content - 50/50 split */}
      <main className="main-content">
        <div className="panel-left">
          <ChatPanel
            selectedModel={selectedModel}
            onModelChange={setSelectedModel}
          />
        </div>
        <div className="panel-divider" />
        <div className="panel-right">
          <GraphPanel />
        </div>
      </main>
    </div>
  )
}

export default App
