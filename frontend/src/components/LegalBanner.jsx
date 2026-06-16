import { SHORT_AI_WARNING } from '../legal/legalContent'

export default function LegalBanner({ text = SHORT_AI_WARNING, variant = 'warn' }) {
  return (
    <div className={`legal-banner legal-banner-${variant}`} role="note">
      {text}
    </div>
  )
}
