# Sample Service Spec

This Source Spec defines a small authentication service for E2E validation.

## Authentication

Users sign in with an email address and password. A successful login creates a session that expires after 24 hours of inactivity. Administrator accounts require multi-factor authentication.

## Authorization

Administrators may read, create, update, and delete any resource. Regular users may read and update only resources they own. Service accounts authenticate with API keys and do not use the login screen.

## Session Termination

Logging out invalidates the active session immediately. Expired sessions are removed by a background sweep every five minutes.

## Password Reset Clean Retest
Password reset requires a one-time token that expires after fifteen minutes.

## Codex E2E dirty mutation

Password reset must invalidate every active session.
