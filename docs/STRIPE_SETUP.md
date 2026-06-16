# Stripe setup

Configure when you are ready to accept payments. Until these env vars are set, the app works with **admin-assigned plans** only.

## 1. Stripe Dashboard

1. Create account at https://dashboard.stripe.com
2. **Products** → create:
   - **Pro** — recurring $39/month
   - **Team** — recurring $99/month
3. Copy each **Price ID** (`price_...`)

## 2. Webhook

1. Developers → Webhooks → Add endpoint
2. URL: `https://YOUR_DOMAIN/api/billing/webhook`
3. Events:
   - `checkout.session.completed`
   - `customer.subscription.updated`
   - `customer.subscription.deleted`
4. Copy **Signing secret** (`whsec_...`)

Local testing:

```bash
stripe listen --forward-to localhost:8000/api/billing/webhook
```

## 3. Backend `.env`

```env
STRIPE_SECRET_KEY=sk_test_...
STRIPE_WEBHOOK_SECRET=whsec_...
STRIPE_PRICE_ID_PRO=price_...
STRIPE_PRICE_ID_TEAM=price_...
FRONTEND_BASE_URL=http://localhost:5173
```

## 4. Migration

```bash
python -m app.db.migrate_phase8
```

Adds `stripe_customer_id`, `stripe_subscription_id` on companies and `terms_accepted_at` on users.

## 5. Flow

1. User clicks **Pro** or **Team** on the Cost card
2. Redirect to Stripe Checkout
3. Webhook applies plan via `apply_plan_to_company`
4. **Manage subscription** opens Stripe Customer Portal

## Legal note

Frontend disclosures are not a substitute for lawyer-drafted Terms of Service and Privacy Policy for your jurisdiction.
