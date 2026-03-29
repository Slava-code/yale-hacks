import { useState, useCallback } from 'react'
import ChatPanel from './components/ChatPanel'
import GraphPanel from './components/GraphPanel'
import PdfViewer from './components/PdfViewer'
import RedactedView from './components/RedactedView'
import './App.css'

function App() {
  const [selectedModel, setSelectedModel] = useState('claude')

  // SSE event state - shared between panels
  const [traversalData, setTraversalData] = useState(null)
  const [sseEvents, setSseEvents] = useState([])

  // PDF viewer state
  const [pdfView, setPdfView] = useState(null)  // { pdf, page, citation }

  // Redacted view visibility
  const [showRedacted, setShowRedacted] = useState(false)

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

  // Open PDF viewer
  const handleOpenPdf = useCallback((pdf, page, citation = null) => {
    setPdfView({ pdf, page, citation })
  }, [])

  // Close PDF viewer
  const handleClosePdf = useCallback(() => {
    setPdfView(null)
  }, [])

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
        <button
          className={`redacted-toggle ${showRedacted ? 'active' : ''}`}
          onClick={() => setShowRedacted(!showRedacted)}
          title="Toggle Redacted View"
        >
          <span className="redacted-toggle-icon">◈</span>
          <span className="redacted-toggle-text">Redacted View</span>
        </button>
      </header>

      {/* Main content - 50/50 split */}
      <main className="main-content">
        <div className="panel-left">
          <ChatPanel
            selectedModel={selectedModel}
            onModelChange={setSelectedModel}
            onSseEvent={handleSseEvent}
            onQueryStart={handleQueryStart}
            onOpenPdf={handleOpenPdf}
          />
        </div>
        <div className="panel-divider" />
        <div className={`panel-right ${showRedacted ? 'with-redacted' : ''}`}>
          {pdfView ? (
            <PdfViewer
              pdfPath={pdfView.pdf}
              initialPage={pdfView.page}
              citation={pdfView.citation}
              onClose={handleClosePdf}
            />
          ) : (
            <GraphPanel
              traversalData={traversalData}
              sseEvents={sseEvents}
              onOpenPdf={handleOpenPdf}
            />
          )}
        </div>
        {showRedacted && (
          <div className="panel-redacted">
            <RedactedView
              sseEvents={sseEvents}
              isVisible={showRedacted}
              onClose={() => setShowRedacted(false)}
            />
          </div>
        )}
      </main>
    </div>
  )
}

export default App
