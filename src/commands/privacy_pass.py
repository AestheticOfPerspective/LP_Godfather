import json
import re

COMMAND_NAME = "privacy_pass"
COMMAND_HELP = "Privacy scanner — checks text for personal data and secrets"
COMMAND_USAGE = "/privacy_pass <text>"

SYSTEM_PROMPT = """You are a privacy scanner. Analyze the text for any of the following:

RED (critical - MUST be removed before sharing):
- Email addresses
- Phone numbers
- Physical addresses
- Government IDs (SSN, passport, driver's license)
- Credit card numbers
- API keys, tokens, passwords
- Bank account numbers
- Private keys / crypto keys

YELLOW (warning - context-dependent risk):
- Usernames / real full names
- Birth dates
- IP addresses
- URLs with tokens or auth params
- Employer / school names combined with personal info
- Device IDs, MAC addresses

GREEN (safe - no issues):
- Nothing sensitive found

Return ONLY valid JSON with no markdown formatting or code fences:
{"level": "green", "findings": [], "summary": "No personal data detected.", "risk_score": 0}

For yellow:
{"level": "yellow", "findings": [{"type": "real name", "severity": "medium", "location": "context"}], "summary": "summary of risks", "risk_score": 40}

For red:
{"level": "red", "findings": [{"type": "email address", "severity": "high", "location": "context"}], "summary": "summary of critical risks", "risk_score": 90}

Use level: green (safe), yellow (caution), red (block).
risk_score: 0-100.
max 5 findings."""


async def execute(ollama, db, args, user_id=""):
    text = " ".join(args) if args else ""
    if not text:
        return "🔒 <b>Privacy Pass</b> — Usage:\n/privacy_pass &lt;text&gt;\n\nScans for: emails, phones, addresses, tokens, credentials, PII.\nResult: 🟢 GREEN = safe, 🟡 YELLOW = caution, 🔴 RED = block."

    response = await ollama.chat(
        user_id=user_id or "cmd_privacy",
        user_message=text,
        system_prompt=SYSTEM_PROMPT,
    )

    if not response.success:
        return f"❌ Ollama error: {response.content}"

    result = _parse_json(response.content)
    if result and "level" in result:
        return _format_result(result)
    return response.content


def _parse_json(text):
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    match = re.search(r'\{.*\}', text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group())
        except json.JSONDecodeError:
            pass
    return None


def _format_result(result):
    level = result.get("level", "green")
    findings = result.get("findings", [])
    summary = result.get("summary", "")
    risk_score = result.get("risk_score", 0)

    if level == "green":
        icon = "🟢"
        label = "GREEN — Safe"
    elif level == "yellow":
        icon = "🟡"
        label = "YELLOW — Caution"
    else:
        icon = "🔴"
        label = "RED — Block"

    lines = [f"{icon} <b>Privacy Pass — {label}</b>\n"]
    lines.append(f"<b>Risk Score:</b> {risk_score}/100\n")

    if findings:
        lines.append("<b>Findings:</b>")
        for f in findings[:5]:
            ftype = f.get("type", "Unknown")
            sev = f.get("severity", "unknown")
            sev_icon = {"high": "🔴", "medium": "🟡", "low": "🟢"}.get(sev, "⚪")
            loc = f.get("location", "")
            lines.append(f"  {sev_icon} <b>{ftype}</b> ({sev})")
            if loc:
                lines.append(f"     ↳ {loc}")
    else:
        lines.append("✅ No issues detected.")

    if summary:
        lines.append(f"\n<i>{summary}</i>")

    return "\n".join(lines)
