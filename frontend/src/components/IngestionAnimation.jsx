import { useState, useEffect, useRef, useCallback } from 'react'
import logoFilter from '../assets/logo-filter.svg'
import './IngestionAnimation.css'

// Sample PDF names for the animation (cycled through rapidly)
const SAMPLE_PDFS = [
  'intake_form_smith_2025_jun.pdf',
  'lab_report_smith_2025_jun.pdf',
  'progress_note_smith_2025_aug.pdf',
  'consult_note_smith_2025_oct.pdf',
  'imaging_report_smith_2025_oct.pdf',
  'referral_letter_smith_2025_oct.pdf',
  'progress_note_garcia_2025_mar.pdf',
  'lab_report_garcia_2025_apr.pdf',
  'discharge_summary_chen_2025_apr.pdf',
  'imaging_report_wilson_2025_may.pdf',
  'intake_form_reed_2025_sep.pdf',
  'progress_note_reed_2025_oct.pdf',
  'consult_note_reed_2026_jan.pdf',
  'lab_report_reed_2026_feb.pdf',
  'intake_form_torres_2026_mar.pdf',
  'progress_note_torres_2026_mar.pdf',
  'consult_note_torres_2026_mar.pdf',
  'lab_report_johnson_2025_jul.pdf',
  'progress_note_davis_2025_sep.pdf',
  'lab_report_chen_2025_oct.pdf',
]
const TOTAL_DOCS = 445  // actual number of PDFs in data/pdfs/

function IngestionAnimation({ onComplete, graphStats }) {
  const [phase, setPhase] = useState('intro') // intro, processing, building, complete
  const [processedDocs, setProcessedDocs] = useState([])
  const [docCount, setDocCount] = useState(0)
  const [particles, setParticles] = useState([])
  const [nodeCount, setNodeCount] = useState(0)
  const [edgeCount, setEdgeCount] = useState(0)
  const containerRef = useRef(null)

  // Target counts from graph stats
  const targetNodes = graphStats?.nodes || 34
  const targetEdges = graphStats?.edges || 45

  // Start the animation sequence
  useEffect(() => {
    const timers = []

    // Reset state in case the effect re-runs (e.g. graphStats changed)
    setProcessedDocs([])
    setParticles([])
    setNodeCount(0)
    setEdgeCount(0)
    setPhase('intro')

    // Phase 1: Intro (show title)
    timers.push(setTimeout(() => setPhase('processing'), 1500))

    // Phase 2: Process documents — rapid batch simulation
    const processingDuration = 4000  // 4 seconds for all docs
    const docSteps = 40  // number of visual updates
    for (let i = 1; i <= docSteps; i++) {
      timers.push(
        setTimeout(() => {
          const docIndex = Math.round((i / docSteps) * TOTAL_DOCS)
          const samplePdf = SAMPLE_PDFS[i % SAMPLE_PDFS.length]
          setProcessedDocs((prev) => {
            const next = [...prev, samplePdf]
            // Keep only last 6 visible in the list
            return next.slice(-6)
          })
          setDocCount(docIndex)
          createParticles(samplePdf, i)
        }, 1500 + (processingDuration / docSteps) * i)
      )
    }

    // Phase 3: Building graph
    const buildStart = 1500 + processingDuration + 500
    timers.push(setTimeout(() => setPhase('building'), buildStart))

    // Animate node/edge counts
    const countDuration = 2000
    const countSteps = 30
    const nodeStep = targetNodes / countSteps
    const edgeStep = targetEdges / countSteps

    for (let i = 1; i <= countSteps; i++) {
      timers.push(
        setTimeout(() => {
          setNodeCount(Math.min(Math.round(nodeStep * i), targetNodes))
          setEdgeCount(Math.min(Math.round(edgeStep * i), targetEdges))
        }, buildStart + (countDuration / countSteps) * i)
      )
    }

    // Phase 4: Complete
    const completeTime = buildStart + countDuration + 800
    timers.push(setTimeout(() => setPhase('complete'), completeTime))

    // Auto-dismiss after animation
    timers.push(setTimeout(() => onComplete?.(), completeTime + 1500))

    return () => timers.forEach((t) => clearTimeout(t))
  }, [targetNodes, targetEdges, onComplete])

  // Create particle effect
  const createParticles = (pdf, index) => {
    const newParticles = Array.from({ length: 5 }, (_, i) => ({
      id: `${pdf}-${i}`,
      startX: 100 + (index % 3) * 120,
      startY: 200 + Math.floor(index / 3) * 80,
      delay: i * 50,
    }))
    setParticles((prev) => [...prev, ...newParticles])
  }

  // Get document type icon - use subtle symbols
  const getDocIcon = (filename) => {
    if (filename.includes('lab_report')) return '◆'
    if (filename.includes('intake_form')) return '■'
    if (filename.includes('progress_note')) return '●'
    if (filename.includes('discharge_summary')) return '○'
    if (filename.includes('imaging_report')) return '◇'
    if (filename.includes('referral_letter')) return '▷'
    return '○'
  }

  return (
    <div className="ingestion-overlay" ref={containerRef}>
      <div className="ingestion-container">
        {/* Intro title — big centered, fades out */}
        {phase === 'intro' && (
          <div className="ingestion-title ingestion-title-intro">
            <span className="ingestion-logo"><img src={logoFilter} alt="" style={{ width: '100%', height: '100%', objectFit: 'contain' }} /></span>
            <span className="ingestion-name">MedGate</span>
            <span className="ingestion-subtitle">Initializing knowledge graph</span>
          </div>
        )}

        {/* Compact title — small top-left, fades in */}
        {phase !== 'intro' && (
          <div className="ingestion-title title-small ingestion-title-compact">
            <span className="ingestion-logo"><img src={logoFilter} alt="" style={{ width: '100%', height: '100%', objectFit: 'contain' }} /></span>
            <span className="ingestion-name">MedGate</span>
          </div>
        )}

        {/* Processing Phase */}
        {(phase === 'processing' || phase === 'building') && (
          <div className="ingestion-content">
            {/* Documents being processed */}
            <div className="ingestion-docs">
              <div className="docs-header">
                <span className="docs-icon">◫</span>
                <span className="docs-label">Processing Documents</span>
                <span className="docs-count">{docCount} / {TOTAL_DOCS}</span>
              </div>
              <div className="docs-list">
                {processedDocs.slice(-6).map((pdf, index) => (
                  <div
                    key={pdf}
                    className="doc-item"
                    style={{ animationDelay: `${index * 50}ms` }}
                  >
                    <span className="doc-icon">{getDocIcon(pdf)}</span>
                    <span className="doc-name">{pdf}</span>
                    <span className="doc-status">✓</span>
                  </div>
                ))}
              </div>
            </div>

            {/* Arrow / Flow indicator */}
            <div className="ingestion-flow">
              <div className="flow-arrow">→</div>
              <div className="flow-particles">
                {particles.slice(-15).map((p) => (
                  <div
                    key={p.id}
                    className="flow-particle"
                    style={{ animationDelay: `${p.delay}ms` }}
                  />
                ))}
              </div>
            </div>

            {/* Graph being built */}
            <div className="ingestion-graph">
              <div className="graph-header">
                <span className="graph-icon">◉</span>
                <span className="graph-label">Knowledge Graph</span>
              </div>
              <div className="graph-stats-anim">
                <div className="stat-item">
                  <span className="stat-value">{nodeCount}</span>
                  <span className="stat-label">nodes</span>
                </div>
                <div className="stat-divider">·</div>
                <div className="stat-item">
                  <span className="stat-value">{edgeCount}</span>
                  <span className="stat-label">edges</span>
                </div>
              </div>
              <div className="graph-preview">
                {/* Mini graph visualization */}
                <svg viewBox="0 0 200 100" className="mini-graph">
                  {/* Edges */}
                  <line x1="100" y1="50" x2="50" y2="30" className="mini-edge" />
                  <line x1="100" y1="50" x2="150" y2="30" className="mini-edge" />
                  <line x1="100" y1="50" x2="60" y2="75" className="mini-edge" />
                  <line x1="100" y1="50" x2="140" y2="75" className="mini-edge" />
                  <line x1="50" y1="30" x2="30" y2="50" className="mini-edge" />
                  <line x1="150" y1="30" x2="170" y2="50" className="mini-edge" />
                  {/* Nodes */}
                  <circle cx="100" cy="50" r="8" className="mini-node mini-node-patient" />
                  <circle cx="50" cy="30" r="5" className="mini-node mini-node-visit" />
                  <circle cx="150" cy="30" r="5" className="mini-node mini-node-visit" />
                  <circle cx="60" cy="75" r="4" className="mini-node mini-node-lab" />
                  <circle cx="140" cy="75" r="4" className="mini-node mini-node-condition" />
                  <circle cx="30" cy="50" r="4" className="mini-node mini-node-medication" />
                  <circle cx="170" cy="50" r="4" className="mini-node mini-node-provider" />
                </svg>
              </div>
            </div>
          </div>
        )}

        {/* Complete Phase */}
        {phase === 'complete' && (
          <div className="ingestion-complete">
            <div className="complete-icon">✓</div>
            <div className="complete-text">Ready</div>
            <div className="complete-stats">
              {targetNodes} nodes · {targetEdges} edges · {TOTAL_DOCS} docs
            </div>
          </div>
        )}

        {/* Progress bar */}
        <div className="ingestion-progress">
          <div
            className="progress-bar"
            style={{
              width:
                phase === 'intro'
                  ? '5%'
                  : phase === 'processing'
                  ? `${10 + (docCount / TOTAL_DOCS) * 60}%`
                  : phase === 'building'
                  ? `${70 + (nodeCount / targetNodes) * 25}%`
                  : '100%',
            }}
          />
        </div>

        {/* Skip button */}
        <button className="ingestion-skip" onClick={onComplete}>
          Skip Animation
        </button>
      </div>
    </div>
  )
}

export default IngestionAnimation
