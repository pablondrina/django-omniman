# Changelog

All notable changes to Django Omniman will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.1.0a1] - 2025-01-19

### Added
- First alpha release for PyPI distribution
- Headless omnichannel order management hub
- Session → Order → Directive workflow
- Protocol-based registry for extensibility
- Rev-based versioning for stale-safe writes
- REST API with DRF integration
- Django admin integration with django-unfold
- Contrib modules: stock, payment, pricing, notifications, refs

### Core Features
- Channel model for multi-origin order management
- Session model for mutable pre-commit state
- Order model for immutable snapshots
- Directive model for async tasks (at-least-once semantics)
- ModifyService for session operations
- CommitService for session-to-order conversion
- ResolveService for issue resolution

### Contrib Modules
- `omniman.contrib.stock` - Inventory management protocols and handlers
- `omniman.contrib.payment` - Payment processing (Stripe, PIX, Mock)
- `omniman.contrib.pricing` - Price calculation backends
- `omniman.contrib.notifications` - Notification system (email, webhook, SMS, WhatsApp)
- `omniman.contrib.refs` - External references and tagging

---

## Pre-release History

The following versions were internal development releases before PyPI publication.

## [0.5.9] - 2024-01-19 (Internal)

### Changed
- Extracted core framework from monorepo for pip distribution
- Improved thread safety in Registry with RLock
- Added database index to Session.state field
- Added transaction.atomic to ResolveService.resolve

### Fixed
- Thread safety issues in registry registration
- Silent error handling in Stockman adapter

## [0.5.8] - Previous Internal Release

### Added
- SessionItem model for normalized item storage
- ResolveService for issue resolution
- Status transition system with timestamps
- Order canonical status flow
- Admin integration with django-unfold

### Changed
- Items now stored in SessionItem instead of JSONField
- Improved admin UX with tabs and badges

## [0.5.7] and earlier

See git history for previous changes.
