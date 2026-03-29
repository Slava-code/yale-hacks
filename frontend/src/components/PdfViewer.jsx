import { useState, useCallback, useEffect, useRef } from 'react'
import { Document, Page, pdfjs } from 'react-pdf'
import 'react-pdf/dist/Page/AnnotationLayer.css'
import 'react-pdf/dist/Page/TextLayer.css'
import './PdfViewer.css'

// Set up PDF.js worker
pdfjs.GlobalWorkerOptions.workerSrc = `//unpkg.com/pdfjs-dist@${pdfjs.version}/build/pdf.worker.min.mjs`

function PdfViewer({ pdfPath, initialPage, citation, onClose }) {
  const [numPages, setNumPages] = useState(null)
  const [pageNumber, setPageNumber] = useState(initialPage || 1)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [isStubMode, setIsStubMode] = useState(false)
  const [isExiting, setIsExiting] = useState(false)
  const [pageTransition, setPageTransition] = useState(false)
  const containerRef = useRef(null)

  // Check for reduced motion preference
  const prefersReducedMotion = useRef(
    typeof window !== 'undefined' &&
    window.matchMedia?.('(prefers-reduced-motion: reduce)').matches
  )

  const onDocumentLoadSuccess = useCallback(({ numPages }) => {
    setNumPages(numPages)
    setLoading(false)
    setIsStubMode(false)
    // Ensure initialPage is valid
    if (initialPage && initialPage <= numPages) {
      setPageNumber(initialPage)
    }
  }, [initialPage])

  const onDocumentLoadError = useCallback((err) => {
    console.error('PDF load error:', err)
    // Check if this is a stub server response
    setIsStubMode(true)
    setError(null)
    setLoading(false)
  }, [])

  // Page navigation with transition animation
  const changePage = useCallback((newPage) => {
    const maxPages = numPages || (isStubMode ? 10 : 1)
    const validPage = Math.max(1, Math.min(newPage, maxPages))
    if (validPage !== pageNumber) {
      if (!prefersReducedMotion.current) {
        setPageTransition(true)
        setTimeout(() => setPageTransition(false), 200)
      }
      setPageNumber(validPage)
    }
  }, [pageNumber, numPages, isStubMode])

  const goToPrevPage = () => changePage(pageNumber - 1)
  const goToNextPage = () => changePage(pageNumber + 1)
  const goToPage = (page) => changePage(page)

  // Handle close with exit animation
  const handleClose = useCallback(() => {
    if (prefersReducedMotion.current) {
      onClose()
    } else {
      setIsExiting(true)
      setTimeout(onClose, 250)
    }
  }, [onClose])

  // Keyboard navigation
  useEffect(() => {
    const handleKeyDown = (e) => {
      // Don't capture if focused on input
      if (e.target.tagName === 'INPUT') return

      switch (e.key) {
        case 'ArrowLeft':
        case 'ArrowUp':
          e.preventDefault()
          goToPrevPage()
          break
        case 'ArrowRight':
        case 'ArrowDown':
        case ' ':
          e.preventDefault()
          goToNextPage()
          break
        case 'Escape':
          e.preventDefault()
          handleClose()
          break
        case 'Home':
          e.preventDefault()
          goToPage(1)
          break
        case 'End':
          e.preventDefault()
          goToPage(numPages || 10)
          break
        default:
          break
      }
    }

    window.addEventListener('keydown', handleKeyDown)
    return () => window.removeEventListener('keydown', handleKeyDown)
  }, [goToPrevPage, goToNextPage, handleClose, numPages])

  // Build the PDF URL
  const pdfUrl = `/api/pdf/${pdfPath}`

  // Extract document type and icon from filename for placeholder
  const getDocInfo = (filename) => {
    const docTypes = [
      { pattern: 'lab_report', type: 'Lab Report', icon: '🧪', color: 'var(--node-lab)' },
      { pattern: 'intake_form', type: 'Intake Form', icon: '📋', color: 'var(--node-visit)' },
      { pattern: 'progress_note', type: 'Progress Note', icon: '📝', color: 'var(--node-provider)' },
      { pattern: 'discharge_summary', type: 'Discharge Summary', icon: '🏥', color: 'var(--node-visit)' },
      { pattern: 'imaging_report', type: 'Imaging Report', icon: '🩻', color: 'var(--node-procedure)' },
      { pattern: 'referral_letter', type: 'Referral Letter', icon: '📨', color: 'var(--node-provider)' },
      { pattern: 'prescription', type: 'Prescription', icon: '💊', color: 'var(--node-medication)' },
      { pattern: 'diagnosis', type: 'Diagnosis Report', icon: '🔬', color: 'var(--node-condition)' },
    ]

    for (const doc of docTypes) {
      if (filename.includes(doc.pattern)) {
        return doc
      }
    }
    return { type: 'Clinical Document', icon: '📄', color: 'var(--node-patient)' }
  }

  const docInfo = getDocInfo(pdfPath)

  // Format filename for display
  const formatFilename = (path) => {
    const filename = path.split('/').pop()
    return filename.replace(/_/g, ' ').replace(/\.pdf$/i, '')
  }

  const maxPages = numPages || (isStubMode ? 10 : 1)

  return (
    <div
      className={`pdf-viewer ${isExiting ? 'pdf-viewer-exit' : ''}`}
      ref={containerRef}
    >
      {/* Header with breadcrumb */}
      <div className="pdf-header">
        <div className="pdf-title-section">
          <div className="pdf-breadcrumb">
            <span className="pdf-breadcrumb-icon" style={{ color: docInfo.color }}>
              {docInfo.icon}
            </span>
            <span className="pdf-breadcrumb-type">{docInfo.type}</span>
            <span className="pdf-breadcrumb-separator">›</span>
            <span className="pdf-breadcrumb-page">Page {pageNumber}</span>
          </div>
          {citation && (
            <span className="pdf-citation">{citation.display}</span>
          )}
        </div>
        <button className="pdf-close-btn" onClick={handleClose}>
          <span className="pdf-close-icon">×</span>
          <span className="pdf-close-text">Close</span>
          <span className="pdf-close-hint">esc</span>
        </button>
      </div>

      {/* PDF Content */}
      <div className={`pdf-content ${pageTransition ? 'page-transitioning' : ''}`}>
        {loading && !isStubMode && (
          <div className="pdf-loading">
            <div className="pdf-loading-skeleton">
              <div className="skeleton-header"></div>
              <div className="skeleton-line"></div>
              <div className="skeleton-line short"></div>
              <div className="skeleton-line"></div>
              <div className="skeleton-line medium"></div>
              <div className="skeleton-line"></div>
            </div>
          </div>
        )}

        {error && !isStubMode && (
          <div className="pdf-error">
            <span className="pdf-error-icon">⚠</span>
            <span>{error}</span>
          </div>
        )}

        {isStubMode ? (
          <div className="pdf-placeholder">
            <div className="pdf-placeholder-document">
              <div className="pdf-placeholder-corner"></div>
              <div className="pdf-placeholder-icon-wrapper" style={{ '--doc-color': docInfo.color }}>
                <span className="pdf-placeholder-emoji">{docInfo.icon}</span>
              </div>
              <div className="pdf-placeholder-lines">
                <div className="placeholder-line"></div>
                <div className="placeholder-line short"></div>
                <div className="placeholder-line medium"></div>
                <div className="placeholder-line"></div>
                <div className="placeholder-line short"></div>
              </div>
            </div>
            <div className="pdf-placeholder-info">
              <div className="pdf-placeholder-type">{docInfo.type}</div>
              <div className="pdf-placeholder-name">{formatFilename(pdfPath)}</div>
              <div className="pdf-placeholder-page-badge">
                <span className="page-badge-icon">📄</span>
                Page {pageNumber} of {maxPages}
              </div>
            </div>
            <div className="pdf-placeholder-note">
              <span className="note-icon">ℹ</span>
              Document preview in demo mode
            </div>
          </div>
        ) : (
          <Document
            file={pdfUrl}
            onLoadSuccess={onDocumentLoadSuccess}
            onLoadError={onDocumentLoadError}
            loading=""
            className="pdf-document"
          >
            <Page
              pageNumber={pageNumber}
              className="pdf-page"
              renderTextLayer={true}
              renderAnnotationLayer={true}
              width={Math.min(window.innerWidth * 0.45, 700)}
            />
          </Document>
        )}
      </div>

      {/* Footer Navigation */}
      {(numPages || isStubMode) && (
        <div className="pdf-footer">
          <div className="pdf-nav-group">
            <button
              className="pdf-nav-btn pdf-nav-prev"
              onClick={goToPrevPage}
              disabled={pageNumber <= 1}
              title="Previous page (←)"
            >
              <span className="nav-icon">‹</span>
              <span className="nav-text">Prev</span>
            </button>

            <div className="pdf-page-info">
              <input
                type="number"
                className="pdf-page-input"
                value={pageNumber}
                onChange={(e) => goToPage(parseInt(e.target.value, 10))}
                min={1}
                max={maxPages}
              />
              <span className="pdf-page-total">/ {maxPages}</span>
            </div>

            <button
              className="pdf-nav-btn pdf-nav-next"
              onClick={goToNextPage}
              disabled={pageNumber >= maxPages}
              title="Next page (→)"
            >
              <span className="nav-text">Next</span>
              <span className="nav-icon">›</span>
            </button>
          </div>

          {/* Page progress bar */}
          <div className="pdf-progress">
            <div
              className="pdf-progress-fill"
              style={{ width: `${(pageNumber / maxPages) * 100}%` }}
            ></div>
          </div>

          <div className="pdf-nav-hints">
            <span className="nav-hint">←→ navigate</span>
            <span className="nav-hint-separator">·</span>
            <span className="nav-hint">esc close</span>
          </div>
        </div>
      )}
    </div>
  )
}

export default PdfViewer
