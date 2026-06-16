import { LEGAL_SECTIONS, PRODUCT_NAME } from '../legal/legalContent'

export default function LegalModal({ onClose }) {
  return (
    <div className="legal-modal-backdrop" onClick={onClose} role="presentation">
      <div className="legal-modal" onClick={(e) => e.stopPropagation()} role="dialog" aria-labelledby="legal-title">
        <div className="legal-modal-header">
          <h2 id="legal-title">{PRODUCT_NAME} — Legal & disclosures</h2>
          <button type="button" className="legal-modal-close" onClick={onClose} aria-label="Close">×</button>
        </div>
        <p className="legal-modal-intro dim">
          Please read carefully. This summary does not replace independent legal advice.
          By using {PRODUCT_NAME} you acknowledge these terms.
        </p>
        <div className="legal-modal-body">
          {LEGAL_SECTIONS.map((sec) => (
            <section key={sec.id} className="legal-section">
              <h3>{sec.title}</h3>
              <ul>
                {sec.body.map((line, i) => (
                  <li key={i}>{line}</li>
                ))}
              </ul>
            </section>
          ))}
        </div>
        <div className="legal-modal-footer">
          <button type="button" className="primary" onClick={onClose}>I understand</button>
        </div>
      </div>
    </div>
  )
}
