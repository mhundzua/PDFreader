"""Claude vision extraction for a single rendered PDF page image."""

import base64
import json

import anthropic

MODEL = "claude-opus-5"

EXTRACTION_SCHEMA = {
    "type": "object",
    "properties": {
        "form_number": {"anyOf": [{"type": "string"}, {"type": "null"}]},
        "serial_number": {"anyOf": [{"type": "string"}, {"type": "null"}]},
        "date": {
            "anyOf": [{"type": "string"}, {"type": "null"}],
            "description": (
                "The date found on the page, normalized to ISO 8601 (YYYY-MM-DD). "
                "Null if no date is present or it cannot be read confidently."
            ),
        },
    },
    "required": ["form_number", "serial_number", "date"],
    "additionalProperties": False,
}

SYSTEM_PROMPT = (
    "You are extracting structured data from a single page of a scanned form. "
    "Identify three fields if present on the page:\n"
    "- form_number: the form's own identifying number or code (e.g. 'DD-214', 'W-9', "
    "'Form 1040', 'AF Form 781').\n"
    "- serial_number: a serial, reference, or document control number printed on the "
    "page, distinct from the form number.\n"
    "- date: the date on the form (e.g. date signed, date issued), normalized to "
    "YYYY-MM-DD.\n"
    "Only report values you can actually read on the page. If a field is missing, "
    "illegible, or ambiguous, return null for it rather than guessing."
)


def extract_page_fields(client: anthropic.Anthropic, image_bytes: bytes) -> dict:
    """Send one page image to Claude and return the extracted fields as a dict."""
    b64 = base64.standard_b64encode(image_bytes).decode("utf-8")

    response = client.messages.create(
        model=MODEL,
        max_tokens=1024,
        system=SYSTEM_PROMPT,
        output_config={
            "effort": "low",
            "format": {"type": "json_schema", "schema": EXTRACTION_SCHEMA},
        },
        messages=[
            {
                "role": "user",
                "content": [
                    {
                        "type": "image",
                        "source": {
                            "type": "base64",
                            "media_type": "image/png",
                            "data": b64,
                        },
                    },
                    {
                        "type": "text",
                        "text": "Extract the form number, serial number, and date from this page.",
                    },
                ],
            }
        ],
    )

    if response.stop_reason == "refusal":
        raise RuntimeError("Claude declined to process this page")

    text = next((block.text for block in response.content if block.type == "text"), None)
    if text is None:
        raise RuntimeError("No text content returned for this page")

    return json.loads(text)
