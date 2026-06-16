import { useState } from 'react'
import { api } from '../api/client'
import { BILLING_FINE_PRINT } from '../legal/legalContent'

export default function BillingUpgrade({ currentPlan = 'free', stripeEnabled = false, hasSubscription = false }) {
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState(null)

  async function checkout(plan) {
    setBusy(true)
    setErr(null)
    try {
      const { checkout_url } = await api.billingCheckout(plan)
      if (checkout_url) window.location.href = checkout_url
    } catch (e) {
      setErr(e.message)
    } finally {
      setBusy(false)
    }
  }

  async function portal() {
    setBusy(true)
    setErr(null)
    try {
      const { portal_url } = await api.billingPortal()
      if (portal_url) window.location.href = portal_url
    } catch (e) {
      setErr(e.message)
    } finally {
      setBusy(false)
    }
  }

  if (!stripeEnabled) {
    return (
      <div className="billing-upgrade dim" style={{ fontSize: 11.5, marginTop: 10 }}>
        Online billing is not configured on this server. Contact your administrator to change plans.
      </div>
    )
  }

  return (
    <div className="billing-upgrade" style={{ marginTop: 10 }}>
      <div className="dim" style={{ fontSize: 10.5, textTransform: 'uppercase', letterSpacing: '0.05em', marginBottom: 6 }}>
        Upgrade
      </div>
      {currentPlan !== 'pro' && currentPlan !== 'team' && (
        <button type="button" className="primary" style={{ width: '100%', marginBottom: 6 }}
                disabled={busy} onClick={() => checkout('pro')}>
          Pro — $39/mo
        </button>
      )}
      {currentPlan !== 'team' && (
        <button type="button" style={{ width: '100%', marginBottom: 6 }}
                disabled={busy} onClick={() => checkout('team')}>
          Team — $99/mo
        </button>
      )}
      {hasSubscription && (
        <button type="button" className="dim" style={{ width: '100%', fontSize: 11 }}
                disabled={busy} onClick={portal}>
          Manage subscription
        </button>
      )}
      <p className="billing-fine-print">{BILLING_FINE_PRINT}</p>
      {err && <div className="login-err" style={{ marginTop: 6 }}>{err}</div>}
    </div>
  )
}
