import { useState } from 'react'
import ChatPanel from './components/ChatPanel'
import GraphPanel from './components/GraphPanel'
import './App.css'

function App() {
  const [selectedModel, setSelectedModel] = useState('claude')

  // SSE event state - shared between panels
  const [traversalData, setTraversalData] = useState(null)
  const [sseEvents, setSseEvents] = useState([])

  // Called by ChatPanel when SSE events arrive
  const handleSseEvent = (event) => {
    setSseEvents((prev) => [...prev, event])

    // Handle specific event types
    if (event.type === 'graph_traversal') {
      setTraversalData(event)
    }
  }

  // Clear SSE state when starting a new query
  const handleQueryStart = () => {
    setTraversalData(null)
    setSseEvents([])
  }

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
            onSseEvent={handleSseEvent}
            onQueryStart={handleQueryStart}
          />
        </div>
        <div className="panel-divider" />
        <div className="panel-right">
          <GraphPanel
            traversalData={traversalData}
            sseEvents={sseEvents}
          />
        </div>
      </main>
    </div>
  )
}

export default App
