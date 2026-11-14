# SmartNet Wallet Collector (Android)

A dedicated Android phone companion for SmartNet's wallet-notification intake API.

## Build environment

- Android Studio Quail 4 (2026.1.4) or a compatible newer stable release.
- JDK 17.
- Android Gradle Plugin 9.4.0 with Gradle 9.6.0.
- Android SDK Platform 36.
- Kotlin Android plugin 2.2.10.
- Minimum Android API: 26; target API: 36.

Open this directory in Android Studio and sync the Gradle project. The repository does not currently include the Gradle wrapper JAR; use the IDE's Gradle 9.6.0 installation or generate a wrapper with `gradle wrapper --gradle-version 9.6.0` before command-line builds.

## Enrollment

1. Create a dedicated phone in SmartNet using `POST /api/v1/wallet-monitor/admin/devices`. The response contains a one-time `device_token`; transfer it through a private channel.
2. Register the provider and exact Android package name in SmartNet.
3. Create a receiving-wallet account bound to that device. The device config endpoint returns only packages allowlisted for active receiving-wallet accounts bound to this phone.
4. Install the APK, enter the HTTPS SmartNet API base URL and device token, then save.
5. Grant Notification Access in Android Settings and tap “مزامنة إعدادات الهاتف الآن”.
6. Confirm the heartbeat and package configuration from SmartNet.

## Security

- Device token and the offline notification queue are encrypted using an AES key generated in Android Keystore.
- Release builds reject cleartext HTTP. HTTPS uses Android's default certificate and hostname validation.
- The app does not request SMS, Accessibility, contacts, call-log, or wallet-account credential permissions.
- The listener filters by backend package allowlist and skips common OTP/security-code prompts.
- Events are queued encrypted locally and sent by Android JobScheduler. Temporary network errors retain events for retry; HTTP 401/403 stops sync and requires device-token review.
- The collector does not mark payments settled, approve payer wallets, activate subscriptions, or execute RouterOS commands.

## Current limits

No provider-specific parsers are registered yet. The collector can be configured and can forward notifications from allowlisted packages, but events remain pending review until a provider adapter is validated with sanitized real notification examples. Automatic activation remains disabled.
