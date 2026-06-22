"""OTP detection + message signature extraction.

A *signature* is a normalised fingerprint of an SMS template. We:
  1. Decide whether a message is an OTP (regex for codes + OTP keywords).
  2. Normalise the body into a template skeleton (mask the code, the digits,
     and trailing reference tokens) so that "Your HDFC code is 482915" and
     "Your HDFC code is 119284" collapse to the same skeleton.
  3. Hash the skeleton -> ``template_hash``. The pair
     ``(sender_id, template_hash)`` defines a brand/template signature.

The same brand/template appearing on a non-A2P route is the core bypass signal.
"""
from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass

_OTP_CODE = re.compile(r"\b(\d{4,8})\b")
_OTP_KEYWORDS = re.compile(
    r"\b(otp|one[\s-]?time|code|verification|verify|passcode|pin|secret)\b", re.I
)
_DIGITS = re.compile(r"\d")
_URL = re.compile(r"https?://\S+")


@dataclass
class Signature:
    is_otp: bool
    code: str | None
    template_skeleton: str
    template_hash: str


def is_otp_message(text: str) -> bool:
    return bool(_OTP_KEYWORDS.search(text) and _OTP_CODE.search(text))


def normalise_template(text: str) -> str:
    t = _URL.sub("<url>", text)
    t = _OTP_CODE.sub("<code>", t)
    t = _DIGITS.sub("#", t)
    t = re.sub(r"\s+", " ", t).strip().lower()
    return t


def extract_signature(text: str) -> Signature:
    is_otp = is_otp_message(text)
    code_match = _OTP_CODE.search(text)
    skeleton = normalise_template(text)
    thash = hashlib.sha1(skeleton.encode()).hexdigest()[:12]
    return Signature(
        is_otp=is_otp,
        code=code_match.group(1) if code_match else None,
        template_skeleton=skeleton,
        template_hash=thash,
    )
