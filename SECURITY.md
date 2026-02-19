# Security Policy

## Supported Versions

| Version | Supported          |
| ------- | ------------------ |
| 0.1.x   | :white_check_mark: |

## Reporting a Vulnerability

If you discover a security vulnerability within Django Omniman, please send an email to **pablondrina@gmail.com**.

**Please do not report security vulnerabilities through public GitHub issues.**

### What to include

- A description of the vulnerability
- Steps to reproduce the issue
- Potential impact of the vulnerability
- Any possible mitigations you've identified

### What to expect

- **Acknowledgment**: We will acknowledge your report within 48 hours.
- **Updates**: We will keep you informed of the progress towards a fix.
- **Resolution**: We aim to resolve critical vulnerabilities within 7 days.
- **Credit**: We will credit you in the release notes (unless you prefer to remain anonymous).

## Security Best Practices

When using Django Omniman in production:

1. **Keep dependencies updated**: Regularly update Django, DRF, and Omniman.
2. **Use HTTPS**: Always use HTTPS in production.
3. **Configure rate limiting**: Use the built-in throttling configuration.
4. **Validate inputs**: Always validate data at API boundaries.
5. **Protect idempotency keys**: Treat idempotency keys as sensitive tokens.
6. **Secure webhooks**: Validate webhook signatures from payment providers.
7. **Audit logs**: Monitor OrderEvent logs for suspicious activity.

## Known Security Considerations

### Idempotency Keys

Idempotency keys are stored with their responses cached. Ensure:
- Keys are unique per client/session
- Keys expire appropriately (default: 24 hours)
- Run `cleanup_idempotency_keys` regularly

### Payment Data

Omniman does **not** store payment card data. However:
- Payment intent IDs are stored in session data
- Use your payment provider's security features (Stripe, etc.)
- Never log sensitive payment information

### Session Data

Session `data` field can store arbitrary JSON. Ensure:
- Validate allowed paths (enforced by default in API)
- Don't store sensitive PII in session data
- Use encryption at rest for your database
