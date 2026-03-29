import { useState, useCallback, useEffect } from 'react'
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

  const goToPrevPage = () => {
    setPageNumber(prev => Math.max(prev - 1, 1))
  }

  const goToNextPage = () => {
    setPageNumber(prev => Math.min(prev + 1, numPages || 1))
  }

  const goToPage = (page) => {
    const validPage = Math.max(1, Math.min(page, numPages || 1))
    setPageNumber(validPage)
  }

  // Build the PDF URL
  const pdfUrl = `/api/pdf/${pdfPath}`

  // Extract document type from filename for placeholder
  const getDocType = (filename) => {
    if (filename.includes('lab_report')) return 'Lab Report'
    if (filename.includes('intake_form')) return 'Intake Form'
    if (filename.includes('progress_note')) return 'Progress Note'
    if (filename.includes('discharge_summary')) return 'Discharge Summary'
    if (filename.includes('imaging_report')) return 'Imaging Report'
    if (filename.includes('referral_letter')) return 'Referral Letter'
    return 'Clinical Document'
  }

  return (
    <div className="pdf-viewer">
      {/* Header */}
      <div className="pdf-header">
        <div className="pdf-title-section">
          <span className="pdf-title">{pdfPath}</span>
          {citation && (
            <span className="pdf-citation">{citation.display}</span>
          )}
        </div>
        <button className="pdf-close-btn" onClick={onClose}>
          Close
        </button>
      </div>

      {/* PDF Content */}
      <div className="pdf-content">
        {loading && !isStubMode && (
          <div className="pdf-loading">Loading PDF...</div>
        )}

        {error && !isStubMode && (
          <div className="pdf-error">{error}</div>
        )}

        {isStubMode ? (
          <div className="pdf-placeholder">
            <div className="pdf-placeholder-icon">PDF</div>
            <div className="pdf-placeholder-type">{getDocType(pdfPath)}</div>
            <div className="pdf-placeholder-name">{pdfPath}</div>
            <div className="pdf-placeholder-page">Page {initialPage || 1}</div>
            <div className="pdf-placeholder-note">
              PDF preview unavailable in demo mode
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
          <button
            className="pdf-nav-btn"
            onClick={goToPrevPage}
            disabled={pageNumber <= 1}
          >
            Prev
          </button>

          <div className="pdf-page-info">
            <input
              type="number"
              className="pdf-page-input"
              value={pageNumber}
              onChange={(e) => goToPage(parseInt(e.target.value, 10))}
              min={1}
              max={numPages || 10}
            />
            <span className="pdf-page-total">/ {numPages || '?'}</span>
          </div>

          <button
            className="pdf-nav-btn"
            onClick={goToNextPage}
            disabled={numPages ? pageNumber >= numPages : false}
          >
            Next
          </button>
        </div>
      )}
    </div>
  )
}

export default PdfViewer
