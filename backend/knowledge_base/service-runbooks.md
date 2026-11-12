# SmartNet service operations knowledge

## Payment receipt versus verified funds
A receipt image is evidence supplied by a customer, not proof that funds settled. An operator must check the actual wallet or bank account, exact amount, currency and transaction reference. Store the verifier and external reference. Keep payment verification separate from subscription activation. A repeated transaction reference must be rejected and escalated for reconciliation.

## Subscription activation
The subscription is active only after the payment state is verified and a separate authorised approval succeeds. Do not infer successful payment from browser redirects, customer text, uploaded files or an AI response. Expired subscriptions must not regain access until renewed and approved.

## Backup and recovery
A database backup is not complete until a restore test is performed. Back up the MariaDB database and private uploads together, encrypt the backup at rest, copy it off-host, and record the backup checksum. Restore into a separate isolated MariaDB instance before using it for production recovery. Never overwrite a production database during a routine restore test.

## Incident reporting
For every service incident capture UTC time, affected router or customer group, symptoms, relevant snapshot IDs, recent change approvals, and observed recovery. Redact passwords, bearer tokens, payment details and personal identifiers from logs and support exports.
