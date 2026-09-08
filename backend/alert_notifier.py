"""
alert_notifier.py — Real-time notification channels for Component 4 alerts.

Channels:
  1. WebSocket broadcast — all connected dashboard clients receive alerts instantly
  2. Email (SMTP) — HIGH/CRITICAL alerts sent as formatted HTML
  3. SMS (Twilio) — CRITICAL alerts sent as concise text messages

All channels are fire-and-forget: failures are logged but never block alert processing.
"""

import asyncio
import json
import smtplib
import threading
from datetime import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Any, Dict, List, Set

import sys
import os
sys.path.insert(0, os.path.dirname(__file__))


# ─── WebSocket Connection Manager ─────────────────────────────────────────────

class WebSocketManager:
    """Manages active WebSocket connections for real-time alert push."""

    def __init__(self):
        self._connections: Set = set()
        self._lock = threading.Lock()

    def connect(self, websocket) -> None:
        """Register a new WebSocket connection."""
        with self._lock:
            self._connections.add(websocket)
        print(f"[WebSocket] Client connected. Total: {len(self._connections)}")

    def disconnect(self, websocket) -> None:
        """Remove a disconnected WebSocket."""
        with self._lock:
            self._connections.discard(websocket)
        print(f"[WebSocket] Client disconnected. Total: {len(self._connections)}")

    @property
    def connection_count(self) -> int:
        return len(self._connections)

    async def broadcast(self, message: Dict[str, Any]) -> int:
        """
        Broadcast a message to all connected clients.
        Returns count of successful deliveries.
        """
        if not self._connections:
            return 0

        payload = json.dumps(message)
        delivered = 0
        dead_connections = []

        with self._lock:
            connections = list(self._connections)

        for ws in connections:
            try:
                await ws.send_text(payload)
                delivered += 1
            except Exception:
                dead_connections.append(ws)

        # Clean up dead connections
        for ws in dead_connections:
            self.disconnect(ws)

        return delivered

    def broadcast_sync(self, message: Dict[str, Any]) -> None:
        """
        Synchronous wrapper for broadcast — runs in existing event loop or creates one.
        Used by the alert engine which runs in sync context.
        """
        try:
            loop = asyncio.get_running_loop()
            loop.create_task(self.broadcast(message))
        except RuntimeError:
            # No running event loop — create a temporary one
            try:
                asyncio.run(self.broadcast(message))
            except Exception as e:
                print(f"[WebSocket] Sync broadcast failed: {e}")


# ─── Email Notifier (SMTP) ────────────────────────────────────────────────────

class EmailNotifier:
    """Send formatted HTML alert emails via SMTP."""

    @staticmethod
    def send_alert_email(alert: Dict, config: Dict) -> bool:
        """
        Send an alert notification email.
        Returns True on success, False on failure (never raises).
        """
        if not config.get("email_enabled") or config.get("email_enabled") != "true":
            return False

        smtp_host = config.get("smtp_host", "")
        smtp_port = int(config.get("smtp_port", "587"))
        smtp_user = config.get("smtp_user", "")
        smtp_password = config.get("smtp_password", "")

        if not smtp_host or not smtp_user:
            print("[Email] SMTP not configured — skipping email notification")
            return False

        try:
            recipients_json = config.get("notification_recipients", "[]")
            recipients = json.loads(recipients_json)
            email_recipients = [r["email"] for r in recipients if r.get("email")]

            if not email_recipients:
                return False

            # Build HTML email
            subject = f"🚨 [{alert['priority']}] {alert['alert_type']} — {alert['plate_number']}"
            html_body = EmailNotifier._build_alert_html(alert)

            msg = MIMEMultipart("alternative")
            msg["Subject"] = subject
            msg["From"] = smtp_user
            msg["To"] = ", ".join(email_recipients)
            msg.attach(MIMEText(html_body, "html"))

            with smtplib.SMTP(smtp_host, smtp_port, timeout=10) as server:
                server.ehlo()
                server.starttls()
                server.login(smtp_user, smtp_password)
                server.send_message(msg)

            print(f"[Email] Alert email sent to {len(email_recipients)} recipients")
            return True

        except Exception as e:
            print(f"[Email] Failed to send alert email: {e}")
            return False

    @staticmethod
    def _build_alert_html(alert: Dict) -> str:
        """Generate formatted HTML for alert email."""
        priority_colors = {
            "CRITICAL": "#ef4444",
            "HIGH": "#f97316",
            "MEDIUM": "#f59e0b",
            "LOW": "#10b981",
        }
        color = priority_colors.get(alert.get("priority", "MEDIUM"), "#f59e0b")
        traj_link = alert.get("trajectory_link", "#")

        return f"""
        <div style="font-family: 'Inter', Arial, sans-serif; max-width: 600px; margin: 0 auto; background: #0b0f17; color: #f1f5f9; border-radius: 8px; overflow: hidden;">
            <div style="background: {color}; padding: 16px 24px;">
                <h2 style="margin: 0; color: #fff;">🚨 {alert.get('alert_type', 'ALERT')}</h2>
                <p style="margin: 4px 0 0; color: rgba(255,255,255,0.9);">Priority: {alert.get('priority', 'MEDIUM')}</p>
            </div>
            <div style="padding: 24px;">
                <table style="width: 100%; border-collapse: collapse;">
                    <tr><td style="padding: 8px 0; color: #94a3b8;">Plate Number</td><td style="padding: 8px 0; font-family: monospace; font-size: 18px; color: #00f0ff;">{alert.get('plate_number', 'N/A')}</td></tr>
                    <tr><td style="padding: 8px 0; color: #94a3b8;">Location</td><td style="padding: 8px 0;">{alert.get('location_name', 'N/A')} ({alert.get('camera_id', '')})</td></tr>
                    <tr><td style="padding: 8px 0; color: #94a3b8;">Confidence</td><td style="padding: 8px 0;">{alert.get('confidence', 0):.0%}</td></tr>
                    <tr><td style="padding: 8px 0; color: #94a3b8;">Timestamp</td><td style="padding: 8px 0;">{alert.get('timestamp', 'N/A')}</td></tr>
                    <tr><td style="padding: 8px 0; color: #94a3b8;">Trigger</td><td style="padding: 8px 0;">{json.dumps(alert.get('trigger_details', {}))}</td></tr>
                </table>
                <div style="margin-top: 20px;">
                    <a href="{traj_link}" style="display: inline-block; background: #3b82f6; color: #fff; padding: 10px 24px; border-radius: 6px; text-decoration: none;">View Vehicle Trajectory →</a>
                </div>
            </div>
        </div>
        """


# ─── SMS Notifier (Twilio) ────────────────────────────────────────────────────

class SMSNotifier:
    """Send alert SMS via Twilio REST API."""

    @staticmethod
    def send_alert_sms(alert: Dict, config: Dict) -> bool:
        """
        Send an alert SMS notification via Twilio.
        Returns True on success, False on failure (never raises).
        Only fires for CRITICAL alerts.
        """
        if not config.get("sms_enabled") or config.get("sms_enabled") != "true":
            return False

        sid = config.get("twilio_sid", "")
        token = config.get("twilio_token", "")
        from_number = config.get("twilio_from", "")

        if not sid or not token or not from_number:
            print("[SMS] Twilio not configured — skipping SMS notification")
            return False

        try:
            from twilio.rest import Client

            recipients_json = config.get("notification_recipients", "[]")
            recipients = json.loads(recipients_json)
            phone_recipients = [r["phone"] for r in recipients if r.get("phone")]

            if not phone_recipients:
                return False

            client = Client(sid, token)
            body = (
                f"🚨 ANPR ALERT [{alert.get('priority', '')}]\n"
                f"Type: {alert.get('alert_type', '')}\n"
                f"Plate: {alert.get('plate_number', '')}\n"
                f"Location: {alert.get('location_name', '')} ({alert.get('camera_id', '')})\n"
                f"Time: {alert.get('timestamp', '')}"
            )

            sent = 0
            for phone in phone_recipients:
                try:
                    client.messages.create(body=body, from_=from_number, to=phone)
                    sent += 1
                except Exception as e:
                    print(f"[SMS] Failed to send to {phone}: {e}")

            print(f"[SMS] Alert SMS sent to {sent}/{len(phone_recipients)} recipients")
            return sent > 0

        except ImportError:
            print("[SMS] Twilio library not installed — skipping SMS notification")
            return False
        except Exception as e:
            print(f"[SMS] Failed to send alert SMS: {e}")
            return False


# ─── Unified Alert Dispatcher ──────────────────────────────────────────────────

class AlertDispatcher:
    """
    Dispatches alerts across all configured channels.
    Channels are fire-and-forget — failures never block alert processing.
    """

    def __init__(self, ws_manager: WebSocketManager):
        self.ws_manager = ws_manager
        self.email_notifier = EmailNotifier()
        self.sms_notifier = SMSNotifier()
        self._notification_thread_pool: List[threading.Thread] = []

    def dispatch(self, alert: Dict, config: Dict) -> Dict[str, bool]:
        """
        Dispatch an alert to all configured channels.
        Returns a dict of channel → success status.
        """
        results = {"websocket": False, "email": False, "sms": False}

        # 1. WebSocket — always attempt (primary channel)
        try:
            ws_message = {
                "event": "NEW_ALERT",
                "alert": alert,
                "timestamp": datetime.utcnow().isoformat(),
            }
            self.ws_manager.broadcast_sync(ws_message)
            results["websocket"] = True
        except Exception as e:
            print(f"[Dispatcher] WebSocket broadcast error: {e}")

        # 2. Email — for HIGH and CRITICAL priority alerts
        priority = alert.get("priority", "MEDIUM")
        if priority in ("HIGH", "CRITICAL"):
            thread = threading.Thread(
                target=self._send_email_async,
                args=(alert, config),
                daemon=True,
            )
            thread.start()
            results["email"] = True  # Optimistic — actual send is async

        # 3. SMS — for CRITICAL alerts only
        if priority == "CRITICAL":
            thread = threading.Thread(
                target=self._send_sms_async,
                args=(alert, config),
                daemon=True,
            )
            thread.start()
            results["sms"] = True  # Optimistic

        return results

    def _send_email_async(self, alert: Dict, config: Dict) -> None:
        """Send email in background thread."""
        try:
            self.email_notifier.send_alert_email(alert, config)
        except Exception as e:
            print(f"[Dispatcher] Async email error: {e}")

    def _send_sms_async(self, alert: Dict, config: Dict) -> None:
        """Send SMS in background thread."""
        try:
            self.sms_notifier.send_alert_sms(alert, config)
        except Exception as e:
            print(f"[Dispatcher] Async SMS error: {e}")


# ─── Global WebSocket Manager Singleton ────────────────────────────────────────

ws_manager = WebSocketManager()
alert_dispatcher = AlertDispatcher(ws_manager)
