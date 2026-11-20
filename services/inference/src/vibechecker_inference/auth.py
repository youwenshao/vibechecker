"""Authenticate exact HTTP bytes before parsing model inputs."""

import hashlib
import heapq
import hmac
import time
from uuid import UUID, uuid4

WINDOW = 60


def signature(
    secret: bytes, method: str, path: str, timestamp: str, nonce: str, body: bytes
) -> str:
    digest = hashlib.sha256(body).hexdigest()
    message = f"{method}\n{path}\n{timestamp}\n{nonce}\n{digest}"
    return hmac.new(secret, message.encode(), hashlib.sha256).hexdigest()


def signed_headers(secret: bytes, method: str, path: str, body: bytes) -> dict[str, str]:
    timestamp, nonce = str(int(time.time())), str(uuid4())
    return {
        "x-vibe-time": timestamp,
        "x-vibe-id": nonce,
        "x-vibe-signature": signature(secret, method, path, timestamp, nonce, body),
    }


class Authenticator:
    """One app process owns the replay window. Run one worker per GPU."""

    def __init__(self, secret: bytes):
        if len(secret) < 32:
            raise ValueError("INFERENCE_HMAC_SECRET requires at least 32 bytes")
        self.secret = secret
        self.seen: set[str] = set()
        self.expiry: list[tuple[int, str]] = []

    def verify(self, headers, method: str, path: str, body: bytes) -> bool:
        now = int(time.time())
        stamp, nonce = headers.get("x-vibe-time", ""), headers.get("x-vibe-id", "")
        try:
            timestamp = int(stamp)
            if (
                str(timestamp) != stamp
                or str(UUID(nonce)) != nonce
                or abs(now - timestamp) > WINDOW
            ):
                return False
        except (ValueError, OverflowError):
            return False
        expected = signature(self.secret, method, path, stamp, nonce, body)
        supplied = headers.get("x-vibe-signature", "")
        if not hmac.compare_digest(expected.encode(), supplied.encode()):
            return False
        while self.expiry and self.expiry[0][0] < now:
            _, old = heapq.heappop(self.expiry)
            self.seen.discard(old)
        if nonce in self.seen or len(self.seen) >= 32768:
            return False
        self.seen.add(nonce)
        heapq.heappush(self.expiry, (timestamp + WINDOW, nonce))
        return True
