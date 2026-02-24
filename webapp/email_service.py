"""
Token generation and email delivery for account activation.

Uses Resend (https://resend.com) for transactional email when the
``RESEND_API_KEY`` environment variable is set.  Falls back to logging
the activation URL to the console when the key is absent.

Set the following env vars in Railway (or your hosting platform):
  RESEND_API_KEY     — your Resend API key (starts with ``re_``)
  RESEND_FROM_EMAIL  — sender address, e.g. ``Numiko <noreply@numiko.com>``
"""
import logging
from typing import Optional

import httpx
from flask import url_for
from itsdangerous import URLSafeTimedSerializer, SignatureExpired, BadSignature

from config import Config

logger = logging.getLogger(__name__)

_RESEND_SEND_URL = 'https://api.resend.com/emails'


def _get_serializer() -> URLSafeTimedSerializer:
    return URLSafeTimedSerializer(Config.SECRET_KEY)


def generate_activation_token(email: str) -> str:
    """Create a time-limited activation token for *email*."""
    s = _get_serializer()
    return s.dumps(email, salt=Config.ACTIVATION_TOKEN_SALT)


def verify_activation_token(token: str) -> Optional[str]:
    """Decode *token* and return the email address, or ``None`` on failure."""
    s = _get_serializer()
    try:
        email = s.loads(token, salt=Config.ACTIVATION_TOKEN_SALT,
                        max_age=Config.ACTIVATION_TOKEN_MAX_AGE)
        return email
    except (SignatureExpired, BadSignature):
        return None


def generate_password_reset_token(email: str) -> str:
    """Create a short-lived (15-minute) password reset token for *email*.

    Uses a different salt from activation tokens so they cannot be
    used interchangeably.
    """
    s = _get_serializer()
    return s.dumps(email, salt=Config.PASSWORD_RESET_TOKEN_SALT)


def verify_password_reset_token(token: str) -> Optional[str]:
    """Decode *token* and return the email address, or ``None`` on failure."""
    s = _get_serializer()
    try:
        email = s.loads(token, salt=Config.PASSWORD_RESET_TOKEN_SALT,
                        max_age=Config.PASSWORD_RESET_TOKEN_MAX_AGE)
        return email
    except (SignatureExpired, BadSignature):
        return None


def _send_via_resend(to_email: str, subject: str, html_body: str) -> bool:
    """Send an email via the Resend API.

    Returns ``True`` on success, ``False`` on failure (logged but not raised).
    """
    api_key = Config.RESEND_API_KEY
    from_email = Config.RESEND_FROM_EMAIL

    if not api_key:
        return False

    try:
        resp = httpx.post(
            _RESEND_SEND_URL,
            headers={
                'Authorization': f'Bearer {api_key}',
                'Content-Type': 'application/json',
            },
            json={
                'from': from_email,
                'to': [to_email],
                'subject': subject,
                'html': html_body,
            },
            timeout=10.0,
        )
        if resp.status_code in (200, 201):
            data = resp.json()
            logger.info('Activation email sent via Resend to %s (id=%s)',
                        to_email, data.get('id', '?'))
            return True
        else:
            logger.error('Resend API error %s: %s', resp.status_code, resp.text)
            return False
    except Exception:
        logger.exception('Failed to send email via Resend to %s', to_email)
        return False


def send_activation_email(user, token: str) -> None:
    """Send the activation link for *user*.

    When ``RESEND_API_KEY`` is configured, sends a branded HTML email via
    Resend.  Always logs the activation URL to the console as a fallback.
    """
    activation_url = url_for('auth.activate', token=token, _external=True)

    # ── Console output (always — useful for dev and as a fallback) ────────
    logger.info(
        '\n'
        '╔══════════════════════════════════════════════════════════════╗\n'
        '║  ACTIVATION LINK for %s\n'
        '║  %s\n'
        '╚══════════════════════════════════════════════════════════════╝',
        user.email,
        activation_url,
    )

    # ── Send via Resend if configured ─────────────────────────────────────
    if Config.RESEND_API_KEY:
        html_body = f"""\
<div style="font-family: Arial, sans-serif; max-width: 520px; margin: 0 auto; padding: 32px 0;">
  <h2 style="color: #0F172A; margin-bottom: 8px;">Welcome to the SEO-GEO Toolkit</h2>
  <p style="color: #64748B; font-size: 15px; line-height: 1.6;">
    Hi {user.name},
  </p>
  <p style="color: #64748B; font-size: 15px; line-height: 1.6;">
    Click the button below to activate your account. This link expires in 48 hours.
  </p>
  <p style="margin: 28px 0;">
    <a href="{activation_url}"
       style="display: inline-block; background: #F46A1B; color: #fff;
              padding: 12px 28px; border-radius: 5px; font-weight: 600;
              font-size: 15px; text-decoration: none;">
      Activate Account
    </a>
  </p>
  <p style="color: #94A3B8; font-size: 13px; line-height: 1.5;">
    If the button doesn't work, copy and paste this link into your browser:<br>
    <a href="{activation_url}" style="color: #F46A1B;">{activation_url}</a>
  </p>
  <hr style="border: none; border-top: 1px solid #E2D5C8; margin: 28px 0;">
  <p style="color: #94A3B8; font-size: 12px;">
    Numiko SEO-GEO Toolkit &mdash; This email was sent because someone registered
    with this address. If that wasn't you, you can safely ignore this email.
  </p>
</div>"""
        _send_via_resend(
            to_email=user.email,
            subject='Activate your SEO-GEO Toolkit account',
            html_body=html_body,
        )
    else:
        logger.warning('RESEND_API_KEY not set — activation email not sent. '
                       'Use the console link above.')


def send_password_reset_email(user, token: str) -> None:
    """Send a password reset link to *user*.

    Link expires in 15 minutes.  Falls back to console logging when
    ``RESEND_API_KEY`` is not set.
    """
    reset_url = url_for('auth.reset_password', token=token, _external=True)

    # ── Console output (always) ───────────────────────────────────────────
    logger.info(
        '\n'
        '╔══════════════════════════════════════════════════════════════╗\n'
        '║  PASSWORD RESET LINK for %s\n'
        '║  %s\n'
        '╚══════════════════════════════════════════════════════════════╝',
        user.email,
        reset_url,
    )

    if Config.RESEND_API_KEY:
        html_body = f"""\
<div style="font-family: Arial, sans-serif; max-width: 520px; margin: 0 auto; padding: 32px 0;">
  <h2 style="color: #0F172A; margin-bottom: 8px;">Reset your password</h2>
  <p style="color: #64748B; font-size: 15px; line-height: 1.6;">
    Hi {user.name},
  </p>
  <p style="color: #64748B; font-size: 15px; line-height: 1.6;">
    We received a request to reset the password for your SEO-GEO Toolkit account.
    Click the button below to choose a new password. This link expires in
    <strong>15&nbsp;minutes</strong>.
  </p>
  <p style="margin: 28px 0;">
    <a href="{reset_url}"
       style="display: inline-block; background: #F46A1B; color: #fff;
              padding: 12px 28px; border-radius: 5px; font-weight: 600;
              font-size: 15px; text-decoration: none;">
      Reset Password
    </a>
  </p>
  <p style="color: #94A3B8; font-size: 13px; line-height: 1.5;">
    If the button doesn't work, copy and paste this link into your browser:<br>
    <a href="{reset_url}" style="color: #F46A1B;">{reset_url}</a>
  </p>
  <hr style="border: none; border-top: 1px solid #E2D5C8; margin: 28px 0;">
  <p style="color: #94A3B8; font-size: 12px;">
    If you didn't request a password reset, you can safely ignore this email.
    Your password will not change.
  </p>
</div>"""
        _send_via_resend(
            to_email=user.email,
            subject='Reset your SEO-GEO Toolkit password',
            html_body=html_body,
        )
    else:
        logger.warning('RESEND_API_KEY not set — password reset email not sent. '
                       'Use the console link above.')
