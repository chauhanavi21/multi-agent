import { useState } from 'react'
import { FOOTER_LEGAL } from '../legal/legalContent'
import LegalModal from './LegalModal'

export default function LegalFooter({ compact = false }) {
  const [open, setOpen] = useState(false)

  return (
    <>
      <footer className={`legal-footer ${compact ? 'legal-footer-compact' : ''}`}>
        <p className="legal-footer-text">{FOOTER_LEGAL}</p>
        <button type="button" className="legal-link" onClick={() => setOpen(true)}>
          Terms · Privacy · AI disclosures
        </button>
      </footer>
      {open && <LegalModal onClose={() => setOpen(false)} />}
    </>
  )
}
