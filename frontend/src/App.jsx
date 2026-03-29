import { useState, useCallback, useEffect } from 'react'
import ChatPanel from './components/ChatPanel'
import GraphPanel from './components/GraphPanel'
import PdfViewer from './components/PdfViewer'
import RedactedView from './components/RedactedView'
import IngestionAnimation from './components/IngestionAnimation'
import HeartsOverlay from './components/HeartsOverlay'
import logoFilter from './assets/logo-filter.svg'
import logoHeartRed from './assets/logo-heart-red.svg'
import logoArrow from './assets/logo-arrow.svg'
import './App.css'

// Model provider configurations
const MODEL_PROVIDERS = {
  claude: {
    name: 'Claude',
    provider: 'Anthropic',
    color: '#D97706',
    bgColor: 'rgba(217, 119, 6, 0.15)',
    icon: '◉',
  },
  gpt4: {
    name: 'GPT-4',
    provider: 'OpenAI',
    color: '#10A37F',
    bgColor: 'rgba(16, 163, 127, 0.15)',
    icon: '◈',
  },
  gemini: {
    name: 'Gemini',
    provider: 'Google',
    color: '#4285F4',
    bgColor: 'rgba(66, 133, 244, 0.15)',
    icon: '◇',
  },
}

function App() {
  const [selectedModel, setSelectedModel] = useState('claude')
  const [models, setModels] = useState([])

  // Connection status: 'connected' | 'streaming' | 'error' | 'idle'
  const [connectionStatus, setConnectionStatus] = useState('idle')

  // SSE event state - shared between panels
  const [traversalData, setTraversalData] = useState(null)
  const [sseEvents, setSseEvents] = useState([])

  // PDF viewer state
  const [pdfView, setPdfView] = useState(null)  // { pdf, page, citation }

  // Redacted view visibility
  const [showRedacted, setShowRedacted] = useState(false)

  // Ingestion animation state
  const [showAnimation, setShowAnimation] = useState(true)
  const [graphStats, setGraphStats] = useState(null)

  // Love mode - Yhack theme easter egg
  const [loveModeActive, setLoveModeActive] = useState(false)
  const [loveSplash, setLoveSplash] = useState(false)

  // Fetch available models on mount
  useEffect(() => {
    async function fetchModels() {
      try {
        const response = await fetch('/api/models')
        const data = await response.json()
        setModels(data.models || [])
        setConnectionStatus('connected')
      } catch (error) {
        console.error('Failed to fetch models:', error)
        setModels([
          { id: 'claude', name: 'Claude', available: true },
          { id: 'gpt4', name: 'GPT-4', available: true },
          { id: 'gemini', name: 'Gemini', available: true },
        ])
        // Still set to connected for stub mode
        setConnectionStatus('connected')
      }
    }
    fetchModels()
  }, [])

  // Fetch graph stats for ingestion animation
  useEffect(() => {
    async function fetchGraphStats() {
      try {
        const response = await fetch('/api/graph')
        const data = await response.json()
        setGraphStats({
          nodes: data.nodes?.length ?? 0,
          edges: data.edges?.length ?? 0,
        })
      } catch {
        // Animation will use its defaults
      }
    }
    fetchGraphStats()
  }, [])

  // Called by ChatPanel when SSE events arrive
  const handleSseEvent = (event) => {
    // Limit to last 200 events to prevent unbounded memory growth
    setSseEvents((prev) => [...prev.slice(-199), event])

    // Handle specific event types
    if (event.type === 'graph_traversal') {
      setTraversalData(event)
    }

    // Update connection status based on event type
    if (event.type === 'final_response' || event.type === 'error') {
      setConnectionStatus('connected')
    }
  }

  // Clear SSE state when starting a new query
  const handleQueryStart = () => {
    setTraversalData(null)
    setSseEvents([])
    setConnectionStatus('streaming')
  }

  // Open PDF viewer
  const handleOpenPdf = useCallback((pdf, page, citation = null) => {
    setPdfView({ pdf, page, citation })
  }, [])

  // Close PDF viewer
  const handleClosePdf = useCallback(() => {
    setPdfView(null)
  }, [])

  const currentModelConfig = MODEL_PROVIDERS[selectedModel] || MODEL_PROVIDERS.claude

  // Pink theme CSS variable overrides for love mode
  const loveModeStyles = loveModeActive ? {
    '--accent': '#ff6b9d',
    '--accent-muted': 'rgba(255, 107, 157, 0.20)',
    '--accent-subtle': 'rgba(255, 107, 157, 0.12)',
    '--border-accent': 'rgba(255, 107, 157, 0.4)',
    '--node-condition': '#ff6b9d',
    '--node-patient': '#ff9ec4',
    '--node-visit': '#ffb6d3',
    '--node-medication': '#ff85b3',
    '--node-lab': '#e080b0',
    '--bg-tertiary': '#301828',
    '--bg-elevated': '#3a1e32',
    '--bg-hover': '#45253c',
    '--border-default': 'rgba(255, 107, 157, 0.15)',
    '--border-strong': 'rgba(255, 107, 157, 0.25)',
  } : {}

  return (
    <div className={`app-container ${loveModeActive ? 'love-mode' : ''}`} style={loveModeStyles}>
      {showAnimation && (
        <IngestionAnimation
          onComplete={() => setShowAnimation(false)}
          graphStats={graphStats}
        />
      )}

      {/* Header */}
      <header className="app-header">
        <div className="logo">
          <div className="logo-icon">
            <div className={`logo-flipper ${loveModeActive ? 'flipped' : ''}`}>
              <img src={logoFilter} className="logo-img logo-front" alt="" />
              <img src={logoHeartRed} className="logo-img logo-back" alt="" />
            </div>
            {loveModeActive && <img src={logoArrow} className="logo-img logo-arrow" alt="" />}
          </div>
          <span className="logo-text">MedGate</span>
        </div>
        <div className="header-subtitle">
          HIPAA-compliant clinical AI
        </div>

        {/* Model Selector */}
        <div className="header-model-section">
          <div className="model-badge">
            <span className="model-badge-icon">●</span>
            <span className="model-badge-provider">{currentModelConfig.name}</span>
          </div>
          <select
            className="header-model-selector"
            value={selectedModel}
            onChange={(e) => setSelectedModel(e.target.value)}
            disabled={connectionStatus === 'streaming'}
          >
            {models.map((model) => (
              <option key={model.id} value={model.id} disabled={!model.available}>
                {model.name}
              </option>
            ))}
          </select>
        </div>

        {/* Connection Status */}
        <div className={`connection-status status-${connectionStatus}`}>
          <span className="status-dot"></span>
          <span className="status-text">
            {connectionStatus === 'streaming' && 'Processing'}
            {connectionStatus === 'connected' && 'Ready'}
            {connectionStatus === 'error' && 'Error'}
            {connectionStatus === 'idle' && 'Connecting'}
          </span>
        </div>

        <button
          className={`redacted-toggle ${showRedacted ? 'active' : ''}`}
          onClick={() => setShowRedacted(!showRedacted)}
          title="View PHI Pipeline"
        >
          <span className="redacted-toggle-icon">◇</span>
          <span className="redacted-toggle-text">PHI Pipeline</span>
        </button>
      </header>

      {/* Main content - 50/50 split */}
      <main className="main-content">
        <div className="panel-left">
          <ChatPanel
            selectedModel={selectedModel}
            onSseEvent={handleSseEvent}
            onQueryStart={handleQueryStart}
            onOpenPdf={handleOpenPdf}
            connectionStatus={connectionStatus}
            onLoveMode={() => {
              if (!loveModeActive && !loveSplash) {
                setLoveSplash(true)
                // After splash holds center, start shrinking to logo
                setTimeout(() => setLoveSplash('shrinking'), 1200)
                // After shrink animation, activate love mode
                setTimeout(() => {
                  setLoveSplash(false)
                  setLoveModeActive(true)
                }, 2200)
              }
            }}
          />
        </div>
        <div className="panel-divider" />
        <div className={`panel-right ${showRedacted ? 'with-redacted' : ''}`}>
          {/* GraphPanel stays mounted but hidden when PDF is open - prevents expensive re-initialization */}
          <GraphPanel
            traversalData={traversalData}
            sseEvents={sseEvents}
            onOpenPdf={handleOpenPdf}
            isVisible={!pdfView}
          />
          {pdfView && (
            <PdfViewer
              pdfPath={pdfView.pdf}
              initialPage={pdfView.page}
              citation={pdfView.citation}
              onClose={handleClosePdf}
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

      {/* Love splash — big heart center → shrinks to logo corner */}
      {loveSplash && (
        <div className={`love-splash-overlay ${loveSplash === 'shrinking' ? 'love-splash-shrink' : ''}`}>
          <div className="love-splash-heart">
            <img src={logoHeartRed} className="love-splash-img" alt="" />
            <img src={logoArrow} className="love-splash-arrow" alt="" />
          </div>
        </div>
      )}

      {/* Love mode hearts overlay - Yhack theme */}
      <HeartsOverlay isActive={loveModeActive} />
    </div>
  )
}

export default App
