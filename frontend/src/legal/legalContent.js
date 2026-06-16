/** Legal copy shown across the app. Not legal advice — have a lawyer review before production. */

export const PRODUCT_NAME = 'Agent Team'

export const SHORT_AI_WARNING =
  'AI-generated content may be inaccurate. You must review all outputs before use.'

export const SIGNUP_TERMS_LABEL =
  'I am at least 18 years old and agree to the Terms of Service, Privacy Policy, and AI Use Disclosures.'

export const FOOTER_LEGAL = `© ${new Date().getFullYear()} ${PRODUCT_NAME}. All rights reserved. This software is provided "as is" without warranties of any kind.`

export const LEGAL_SECTIONS = [
  {
    id: 'ai',
    title: 'AI-generated content',
    body: [
      'Outputs are produced by automated systems (local models and/or third-party AI providers such as Anthropic).',
      'AI can hallucinate, omit context, or produce biased or incorrect information.',
      'You are solely responsible for reviewing, editing, and approving every draft email, SMS, plan, or recommendation before sending or acting on it.',
      'Nothing in this product constitutes legal, tax, financial, investment, medical, or professional advice.',
    ],
  },
  {
    id: 'outreach',
    title: 'Outreach & compliance',
    body: [
      'You are responsible for compliance with CAN-SPAM, GDPR, TCPA, local telemarketing laws, and platform terms (email providers, SMS carriers, social networks).',
      'Do not send unsolicited messages where prohibited. Maintain opt-out and consent records yourself.',
      'SMS and Instagram scraping features depend on third-party services (e.g. Twilio, Apify). Their terms and outages apply.',
      'Mock modes store messages locally for testing only — they do not send real communications.',
    ],
  },
  {
    id: 'subscription',
    title: 'Subscriptions & billing',
    body: [
      'Paid plans (Pro, Team) are billed monthly through Stripe unless stated otherwise.',
      'Fees are non-refundable except where required by applicable law.',
      'Included "premium AI" usage is capped per plan; heavy use may downgrade to local models or stop cloud access until the next billing cycle.',
      'We may change pricing or features with reasonable notice. Continued use after changes constitutes acceptance.',
      'Cancel anytime via the billing portal; access continues until the end of the paid period, then reverts to Free tier limits.',
    ],
  },
  {
    id: 'data',
    title: 'Data & privacy',
    body: [
      'We store account data, leads, chat history, memories, and usage metrics in our database to operate the service.',
      'Do not submit sensitive personal data (health, financial account numbers, government IDs) unless you accept the risk.',
      'You are the data controller for lead/contact data you upload; ensure you have a lawful basis to process it.',
      'Back up important data; we are not liable for loss due to outages, bugs, or account termination.',
    ],
  },
  {
    id: 'liability',
    title: 'Limitation of liability',
    body: [
      'To the maximum extent permitted by law, we are not liable for lost revenue, lost leads, reputational harm, or indirect damages arising from use of this product.',
      'Our total liability for any claim related to the service is limited to the amount you paid us in the twelve (12) months before the claim.',
      'The service is experimental automation software — we do not guarantee sales results, deliverability, or uptime.',
    ],
  },
  {
    id: 'acceptable',
    title: 'Acceptable use',
    body: [
      'No spam, harassment, illegal activity, malware, or attempts to bypass rate limits or security.',
      'No reselling API access or scraping the service without permission.',
      'We may suspend or terminate accounts that violate these rules without refund.',
    ],
  },
]

export const CHAT_BANNER =
  'AI assistant — not human. Verify facts and review actions before sending emails or messages to real people.'

export const EMAIL_SEND_WARNING =
  'You are about to send this message to a real recipient. You confirm it is accurate, lawful, and approved by you.'

export const BILLING_FINE_PRINT =
  'By upgrading you authorize recurring charges via Stripe. Taxes may apply. See full Terms for cancellation and refund policy.'
