"""Cron entry for window alert rules."""

from api.services.alerting.evaluate import evaluate_window_alerts


async def evaluate_window_alert_rules(_ctx) -> None:
    """Evaluate every active window rule. Runs every five minutes."""
    await evaluate_window_alerts()
