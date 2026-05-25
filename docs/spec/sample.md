# Sample Specification

This document is a minimal Source Specs fixture for verifying spec-anchor end-to-end behavior in a real LLM + Qdrant environment.

## Authentication

Users authenticate with an email address and a password. A successful login establishes a session that expires after 24 hours of inactivity. The login endpoint rate-limits to 5 attempts per minute per remote IP. Multi-factor authentication is required for administrator accounts; service accounts are exempt.

## Authorization

Admin users may read, create, update, and delete any resource. Regular users may read and update only resources they own. Service accounts authenticate with API keys and never see the login UI.

## Session Termination

Logging out invalidates the current session immediately. Sessions that exceed the 24-hour inactivity window are automatically purged by a background sweep that runs every five minutes.

## Session Retention Policy

For compliance and audit purposes, all session records must be retained and kept active for a minimum of 30 days regardless of inactivity. Sessions must not be terminated before the 30-day retention window has elapsed.

## Account Lockout

After 3 consecutive failed login attempts, the account is locked for 30 minutes. During a lockout period, all further login attempts are rejected immediately without incrementing the rate-limit counter. Administrator accounts require manual unlock by a system operator.
