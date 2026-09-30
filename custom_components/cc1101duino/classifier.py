"""Collects unrecognized signals by type, and has Claude classify each type once."""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import time
from collections.abc import Mapping
from functools import partial
from typing import TYPE_CHECKING, Any

import anthropic
from homeassistant.components import persistent_notification
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.helpers.dispatcher import async_dispatcher_send
from homeassistant.helpers.storage import Store
from homeassistant.util import dt as dt_util

from .claude import AuthenticationFailed, ClassificationError, async_classify
from .const import (
    AUTOCREATE_MIN_GAP,
    CONF_API_KEY,
    CONF_CLASSIFY_AUTOMATICALLY,
    CONF_MAX_CLASSIFICATIONS_PER_DAY,
    CONF_MIN_TRANSMISSIONS,
    CONF_MODEL,
    DEFAULT_MAX_CLASSIFICATIONS_PER_DAY,
    DEFAULT_MIN_TRANSMISSIONS,
    DEFAULT_MODEL,
    DOMAIN,
    EVENT_UNKNOWN_SIGNAL_CLASSIFIED,
    signal_unknown,
)
from .protocol.fingerprint import Fingerprint

if TYPE_CHECKING:
    from .hub import ReceivedSignal

_LOGGER = logging.getLogger(__name__)

STORAGE_VERSION = 1
SAVE_DELAY = 30

# Samples sent to Claude, from separate transmissions where possible
MAX_SAMPLES = 8
MAX_INTERVALS = 20
# Types that have not been classified yet, mostly noise; the least recently heard are dropped
MAX_PENDING = 100
# Failed classifications are retried automatically after RETRY_DELAY, doubling each time
MAX_ATTEMPTS = 3
RETRY_DELAY = 3600
DAY = 86400
# Types listed in the sensor's attributes
MAX_SUMMARY = 20

STATUS_COLLECTING = "collecting"
STATUS_CLASSIFYING = "classifying"
STATUS_CLASSIFIED = "classified"
STATUS_FAILED = "failed"


def _signal_id(fingerprint: Fingerprint) -> str:
    return hashlib.sha1(json.dumps(fingerprint.as_dict()).encode()).hexdigest()[:8]


class UnknownSignalClassifier:
    """Groups unrecognized signals by fingerprint and asks Claude about each group once.

    A type is only sent after it was heard in several separate transmissions, so noise that
    never repeats costs nothing, and once classified (even as noise) it is never sent again.
    """

    def __init__(self, hass: HomeAssistant, entry_id: str, options: Mapping[str, Any]) -> None:
        self.hass = hass
        self.entry_id = entry_id
        self.api_key: str | None = options.get(CONF_API_KEY) or None
        self.model: str = options.get(CONF_MODEL) or DEFAULT_MODEL
        self.automatic: bool = options.get(CONF_CLASSIFY_AUTOMATICALLY, True)
        self.max_per_day: int = int(
            options.get(CONF_MAX_CLASSIFICATIONS_PER_DAY, DEFAULT_MAX_CLASSIFICATIONS_PER_DAY)
        )
        self.min_transmissions: int = int(
            options.get(CONF_MIN_TRANSMISSIONS, DEFAULT_MIN_TRANSMISSIONS)
        )
        self.records: dict[str, dict[str, Any]] = {}
        self._fingerprints: dict[str, Fingerprint] = {}
        # When classifications were requested, for the daily limit
        self._requested: list[float] = []
        self._store: Store[dict[str, Any]] = Store(
            hass, STORAGE_VERSION, f"{DOMAIN}.unknown_signals.{entry_id}"
        )
        self._client: anthropic.AsyncAnthropic | None = None
        self._lock = asyncio.Lock()
        self._tasks: dict[str, asyncio.Task[None]] = {}
        self._auth_failed = False

    async def async_load(self) -> None:
        data = await self._store.async_load() or {}
        self._requested = data.get("requested", [])
        for record in data.get("signals", []):
            if record["status"] == STATUS_CLASSIFYING:
                record["status"] = STATUS_COLLECTING
            self.records[record["id"]] = record
            self._fingerprints[record["id"]] = Fingerprint.from_dict(record["fingerprint"])

    async def async_unload(self) -> None:
        tasks = list(self._tasks.values())
        for task in tasks:
            task.cancel()
        if tasks:
            await asyncio.wait(tasks)
        await self._store.async_save(self._data())

    def _data(self) -> dict[str, Any]:
        return {"requested": self._requested, "signals": list(self.records.values())}

    @callback
    def _changed(self) -> None:
        self._store.async_delay_save(self._data, SAVE_DELAY)
        async_dispatcher_send(self.hass, signal_unknown(self.entry_id))

    @callback
    def async_add(self, received: ReceivedSignal) -> None:
        """Note an unrecognized signal, and classify its type once it was heard often enough."""
        fingerprint = Fingerprint.from_line(received.line)
        if fingerprint is None:
            return
        signal_id = next(
            (sid for sid, other in self._fingerprints.items() if other.similar(fingerprint)),
            None,
        )
        now = received.time.isoformat()
        sample = {"time": now, "rssi": received.rssi, "line": received.line}

        if signal_id is None:
            signal_id = _signal_id(fingerprint)
            self._prune()
            self.records[signal_id] = {
                "id": signal_id,
                "fingerprint": fingerprint.as_dict(),
                "first_seen": now,
                "last_seen": now,
                "count": 1,
                "transmissions": 1,
                "intervals": [],
                "samples": [sample],
                "status": STATUS_COLLECTING,
                "result": None,
                "error": None,
                "attempts": 0,
                "last_attempt": None,
            }
            self._fingerprints[signal_id] = fingerprint
        else:
            record = self.records[signal_id]
            last_seen = dt_util.parse_datetime(record["last_seen"])
            gap = (received.time - last_seen).total_seconds() if last_seen else 0
            record["count"] += 1
            record["last_seen"] = now
            # Lines within a moment of each other are repeats of one transmission
            if gap >= AUTOCREATE_MIN_GAP:
                record["transmissions"] += 1
                record["intervals"] = [*record["intervals"], round(gap, 1)][-MAX_INTERVALS:]
            samples = record["samples"]
            if (
                len(samples) < MAX_SAMPLES
                and all(other["line"] != received.line for other in samples)
                and (gap >= AUTOCREATE_MIN_GAP or len(samples) < 2)
            ):
                samples.append(sample)

        if self._should_classify(self.records[signal_id]):
            self._start(signal_id)
        self._changed()

    @callback
    def _prune(self) -> None:
        pending = [
            record for record in self.records.values() if record["status"] == STATUS_COLLECTING
        ]
        if len(pending) < MAX_PENDING:
            return
        oldest = min(pending, key=lambda record: record["last_seen"])
        self._remove(oldest["id"])

    @callback
    def _remove(self, signal_id: str) -> None:
        del self.records[signal_id]
        del self._fingerprints[signal_id]

    def _within_limit(self) -> bool:
        now = time.time()
        self._requested = [requested for requested in self._requested if now - requested < DAY]
        return len(self._requested) < self.max_per_day

    def _should_classify(self, record: dict[str, Any]) -> bool:
        if not self.api_key or not self.automatic or self._auth_failed:
            return False
        if record["id"] in self._tasks or record["transmissions"] < self.min_transmissions:
            return False
        if record["status"] == STATUS_FAILED:
            if record["attempts"] >= MAX_ATTEMPTS:
                return False
            last = dt_util.parse_datetime(record["last_attempt"] or "")
            delay = RETRY_DELAY * 2 ** (record["attempts"] - 1)
            if last is not None and (dt_util.utcnow() - last).total_seconds() < delay:
                return False
        elif record["status"] != STATUS_COLLECTING:
            return False
        return self._within_limit()

    @callback
    def _start(self, signal_id: str) -> asyncio.Task[None]:
        task = self.hass.async_create_background_task(
            self._async_classify(signal_id), f"{DOMAIN} classify {signal_id}"
        )
        self._tasks[signal_id] = task
        task.add_done_callback(lambda _: self._tasks.pop(signal_id, None))
        return task

    async def async_classify(self, signal_id: str) -> dict[str, Any]:
        """Classify a type now, even if classified before or heard only once."""
        if not self.api_key:
            raise ServiceValidationError("Set an Anthropic API key in the integration options")
        if signal_id not in self.records:
            raise ServiceValidationError(f"Unknown signal type {signal_id}")
        self._auth_failed = False
        task = self._tasks.get(signal_id) or self._start(signal_id)
        try:
            await asyncio.shield(task)
        except asyncio.CancelledError:
            # Only the classification being cancelled, by forgetting the type, is expected
            if not task.cancelled():
                raise
        record = self.records.get(signal_id)
        if record is None:
            raise HomeAssistantError(f"Signal type {signal_id} was forgotten meanwhile")
        if record["status"] == STATUS_FAILED:
            raise HomeAssistantError(f"Classifying {signal_id} failed: {record['error']}")
        return record

    async def _async_classify(self, signal_id: str) -> None:
        async with self._lock:
            record = self.records.get(signal_id)
            if record is None:
                return
            if self._client is None:
                # Creating the client loads certificates, which blocks
                self._client = await self.hass.async_add_executor_job(
                    partial(anthropic.AsyncAnthropic, api_key=self.api_key)
                )
            record["status"] = STATUS_CLASSIFYING
            record["attempts"] += 1
            record["last_attempt"] = dt_util.utcnow().isoformat()
            self._requested.append(time.time())
            self._changed()
            _LOGGER.info("Asking %s to classify unknown signal type %s", self.model, signal_id)
            try:
                result = await async_classify(self._client, self.model, record)
            except ClassificationError as err:
                _LOGGER.warning("Classifying unknown signal type %s failed: %s", signal_id, err)
                if isinstance(err, AuthenticationFailed):
                    # Stop until the key is changed or a classification is requested
                    self._auth_failed = True
                    persistent_notification.async_create(
                        self.hass,
                        f"{err}. Unknown signals are no longer classified automatically until "
                        "the API key is changed in the integration options.",
                        title="CC1101Duino: Anthropic API key rejected",
                        notification_id=f"{DOMAIN}_api_key",
                    )
                if signal_id in self.records:
                    record["status"] = STATUS_FAILED
                    record["error"] = str(err)
                self._changed()
                return
            except asyncio.CancelledError:
                record["status"] = STATUS_COLLECTING
                raise

            if signal_id not in self.records:
                # Forgotten meanwhile
                return
            record["status"] = STATUS_CLASSIFIED
            record["result"] = result
            record["error"] = None
            self._changed()
            self._announce(record)

    @callback
    def _announce(self, record: dict[str, Any]) -> None:
        result = record["result"]
        _LOGGER.info("Unknown signal type %s: %s", record["id"], result["summary"])
        self.hass.bus.async_fire(
            EVENT_UNKNOWN_SIGNAL_CLASSIFIED,
            {"config_entry_id": self.entry_id, "signal_id": record["id"], **result},
        )
        if result["is_noise"]:
            return
        persistent_notification.async_create(
            self.hass,
            f"**{result['device']}** ({result['category']}, {result['confidence']} "
            f"confidence)\n\n{result['summary']}\n\nSignal type `{record['id']}`, heard "
            f"{record['transmissions']} times. Details: action "
            "`cc1101duino.list_unknown_signals`.",
            title="CC1101Duino: unknown signal classified",
            notification_id=f"{DOMAIN}_unknown_{record['id']}",
        )

    @callback
    def async_forget(self, signal_id: str | None) -> None:
        """Forget one type, or all, so that it is collected and classified afresh."""
        if signal_id is None:
            signal_ids = list(self.records)
        elif signal_id in self.records:
            signal_ids = [signal_id]
        else:
            raise ServiceValidationError(f"Unknown signal type {signal_id}")
        for sid in signal_ids:
            if (task := self._tasks.get(sid)) is not None:
                task.cancel()
            self._remove(sid)
        self._changed()

    def confirmed(self) -> list[dict[str, Any]]:
        """Types heard often enough not to be noise, or classified, most recently heard first."""
        return sorted(
            (
                record
                for record in self.records.values()
                if record["status"] != STATUS_COLLECTING
                or record["transmissions"] >= self.min_transmissions
            ),
            key=lambda record: record["last_seen"],
            reverse=True,
        )

    def summary(self) -> list[dict[str, Any]]:
        """A short description of the confirmed types, for the sensor's attributes."""
        summary = []
        for record in self.confirmed()[:MAX_SUMMARY]:
            result = record["result"] or {}
            summary.append(
                {
                    "id": record["id"],
                    "status": record["status"],
                    "transmissions": record["transmissions"],
                    "last_seen": record["last_seen"],
                    "category": result.get("category"),
                    "device": result.get("device"),
                    "summary": result.get("summary") or record["error"],
                }
            )
        return summary
